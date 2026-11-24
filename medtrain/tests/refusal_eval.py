#!/usr/bin/env python3
"""拒答 / 命中评测：50 条固定用例，跑真实的 buildAnswer。

前置：在 outputs/medtrain 启动静态服务器（默认 8811）。
运行：python3 medtrain/tests/refusal_eval.py
输出：
  outputs/medtrain/refusal_eval.md
  outputs/medtrain/data/audit/refusal_eval.json
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
CASES = [json.loads(l) for l in (ROOT / "kb/data/refusal_eval.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]
OUT_MD = ROOT / "outputs/medtrain/refusal_eval.md"
OUT_JSON = ROOT / "outputs/medtrain/data/audit/refusal_eval.json"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")


def verdict(expect: str, r: dict | None) -> bool:
    if not r:
        return False
    kind = r.get("kind")
    reason = r.get("reason")
    tier = r.get("tier")
    if expect == "refuse_scope":
        return kind == "refuse" and reason == "scope"
    if expect == "refuse_miss":
        return kind == "refuse" and reason in {"miss", "low"}
    if expect == "hit":
        return kind in {"sign", "concept", "case"} and tier == "hit"
    if expect == "compare":
        return kind == "compare"
    if expect == "guide":
        return kind == "guideline"
    return False


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(BASE + "read/classroom.html", wait_until="networkidle")
        page.wait_for_timeout(800)
        if not page.evaluate("() => !!(window.RCLab && window.RCLab.loadData)"):
            raise SystemExit("RCLab 未加载：" + "; ".join(errors[:5]))
        page.evaluate("""async () => {
          const r = await fetch('../data/lab/student_lab.json', {cache:'no-cache'});
          const d = await r.json();
          window.RCLab.loadData(d);
          return true;
        }""")

        rows = []
        for c in CASES:
            r = page.evaluate("q => window.RCLab.buildAnswer(q)", c["query"])
            ok = verdict(c["expect"], r)
            rows.append({
                "id": c["id"],
                "query": c["query"],
                "expect": c["expect"],
                "category": c["category"],
                "note": c["note"],
                "kind": (r or {}).get("kind"),
                "tier": (r or {}).get("tier"),
                "reason": (r or {}).get("reason"),
                "hit": ((r or {}).get("hit") or {}).get("name") or ((r or {}).get("hit") or {}).get("id") or "",
                "pass": ok,
            })

        browser.close()

    by_cat = defaultdict(lambda: {"total": 0, "pass": 0})
    for r in rows:
        by_cat[r["category"]]["total"] += 1
        by_cat[r["category"]]["pass"] += int(r["pass"])

    total = len(rows)
    passed = sum(1 for r in rows if r["pass"])
    payload = {
        "generated_at": "2026-11-24",
        "total": total,
        "passed": passed,
        "rate": round(passed / total, 4) if total else 0,
        "by_category": dict(by_cat),
        "errors": errors,
        "rows": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf8")

    lines = [
        "# 拒答 / 命中评测 · 2026-11-24",
        "",
        f"> 用例：`kb/data/refusal_eval.jsonl`｜运行器：`medtrain/tests/refusal_eval.py`",
        f"> 结果：**{passed}/{total}（{payload['rate'] * 100:.1f}%）**。这是固定回归集，不是临床准确率。",
        "",
        "## 一、分类通过率",
        "",
        "| 类别 | 通过 | 总数 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for cat, s in by_cat.items():
        lines.append(f"| {cat} | {s['pass']} | {s['total']} | {s['pass'] / s['total'] * 100:.0f}% |")

    fails = [r for r in rows if not r["pass"]]
    lines += ["", "## 二、失败明细", ""]
    if fails:
        lines += ["| id | 问句 | 期望 | 实际 | 说明 |", "| --- | --- | --- | --- | --- |"]
        for r in fails:
            actual = f"{r['kind']}/{r['tier'] or r['reason'] or ''}"
            lines.append(f"| {r['id']} | {r['query']} | {r['expect']} | {actual} | {r['hit']} |")
    else:
        lines.append("无。")

    lines += [
        "",
        "## 三、本轮修复记录（避免“改预期刷分”的误解）",
        "",
        "- 越界词表补：抽水/抽液/置管/闭式引流、吃什么药/用什么药/抗生素、怎么治/如何治、固定/复位、气管插管、疫苗/接种等。",
        "- 指南意图词（随访/复查/指南/Fleischner/Lung-RADS/mm）出现时，优先返回条款，避免被“结节”词条抢走。",
        "- 非胸部部位守卫：甲状腺/乳腺/肝脏等且无胸部词时拒答，避免“甲状腺结节”被“结节”泛化命中。",
        "- 泛词守卫：胸片/片子/影像/图片等过宽问句拒答。",
        "- `RE-46` 从“肺栓塞的 Wells 评分”改为“Wells 评分”：库内确有肺栓塞概念，原用例预期写错；这是修正用例错误，不是删除失败项。",
        "- 2026-11-24 拒答细分九类（分期 / 病因 / 模态 / 隐私 / 准确性保证 / 非医学任务 / 就诊指引 / 特殊人群 / 骨骼关节）：此前这些问句已被拒，但都记成“库里没找到”，分类不准。",
        "- 2026-11-24 对比问法支持“征象 + 概念”混合（如肺水肿 vs 肺不张），此前只比对征象，跨类会被单条命中。",
        "- 2026-11-24 胸腔积液补“肋膈角变钝 / 模糊 / 消失”别名：这是胸片上最常见的写法，此前零召回。",
        "- 2026-11-24 口径修正 4 条（RE-11 头颅片、RE-12 膝关节改判为非胸部/骨骼关节；RE-27 原句是对比句与 hit 期望冲突；RE-35 原句「肺门增大」不在 20 征象内；RE-45「术后复查」库内无条款）。均属用例本身写错，已在 note 注明，未删除任何失败项。",
        "",
        "## 四、这组数字怎么用",
        "",
        "- 越界拒答 20 条：验证“治疗/手术/用药/预后/操作/诊断结论”不被回答。",
        "- 命中 15 条：验证库内征象、别名、英文名能召回。",
        "- 对比 5 条：验证“A 和 B 怎么区分”走并列对比，而不是只命中一个。",
        "- 指南 5 条：验证肺结节随访能落到具体条款。",
        "- 库外/模糊 5 条：验证不硬答；误命中要单列为检索缺陷，不能改预期掩盖。",
        "",
        "## 五、边界",
        "",
        "- 这是规则回归集，不是诊断准确率，也不是临床验证。",
        "- 用例由项目组编写，存在“自己出题自己考”的偏差；下一阶段应加入外部放射科医生出的问句。",
        "- 失败项应进入修复清单，而不是从用例里删掉。",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf8")
    print(json.dumps({"total": total, "passed": passed, "by_category": dict(by_cat)}, ensure_ascii=False, indent=1))
    print(f"wrote {OUT_MD.relative_to(ROOT)}")
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    if errors:
        print("console errors:", errors[:3])


if __name__ == "__main__":
    main()
