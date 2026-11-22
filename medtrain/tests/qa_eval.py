#!/usr/bin/env python3
"""学生影像问答 · 30 条最小评测集。

前置：
  python3 medtrain/build.py
  python3 -m http.server 8811 --directory outputs/medtrain
运行：
  python3 medtrain/tests/qa_eval.py
输出：
  outputs/medtrain/qa_eval.md

口径：
  - 应回答：不能拒答，且至少有 1 个影像位置 / 文献条目 + 1 条段落 L2；
  - 应拒答：必须是“越界 / 低置信 / 库内未覆盖”的拒答卡；
  - 声明：每条答案都必须出现“不构成诊断意见”。
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/qa_eval.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")

SHOULD_ANSWER = [
    "气胸在胸片上怎么找",
    "实变",
    "胸腔积液",
    "肺结核",
    "肺结节随访看哪条指南",
    "心影增大",
    "肺水肿",
    "纵隔增宽",
    "磨玻璃影",
    "空洞",
    "钙化",
    "支气管扩张",
    "肺不张",
    "胸膜增厚",
    "气胸和胸腔积液怎么区分",
]

SHOULD_REFUSE = [
    "这个气胸需要做胸腔闭式引流吗",
    "肺癌能活多久",
    "需要手术吗",
    "化疗方案怎么选",
    "这个是不是癌",
    "严重吗",
    "颅脑 CT 硬膜下血肿",
    "阑尾炎",
    "乳腺癌筛查",
    "需要做什么检查",
]

WATCH = ["密度轻度增高", "边界模糊", "肋膈角变钝", "肺纹理增多", "这个影子"]


def main() -> None:
    rows: list[tuple[str, str, str, bool, int, int, int, bool, str]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE + "read/classroom.html", wait_until="networkidle")
        page.evaluate("localStorage.clear()")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(300)

        # 建演示班 + 学生加入，进入问答页签
        page.click('[data-act="role"][data-role="teacher"]')
        page.wait_for_timeout(200)
        page.click('[data-act="demo-class"]')
        page.wait_for_timeout(350)
        code = page.inner_text(".code-box b")
        page.click('#roleSwitch [data-role="student"]')
        page.wait_for_timeout(300)
        page.fill("#joinName", "评测同学")
        page.fill("#joinCode", code)
        page.click('[data-act="join-class"]')
        page.wait_for_timeout(400)
        page.click('[data-student-tab="qa"]')
        page.wait_for_timeout(500)

        def ask(q: str) -> None:
            page.fill("#labQ", q)
            page.click("[data-lab-ask]")
            page.wait_for_timeout(260)

        for group, items in (("answer", SHOULD_ANSWER), ("refuse", SHOULD_REFUSE), ("watch", WATCH)):
            for q in items:
                ask(q)
                text = page.inner_text("#labQaResult")
                cls = (page.locator("#labQaResult .lab-answer").first.get_attribute("class") or "")
                tier = "refuse" if "refuse" in cls else "weak" if "weak" in cls else "hit"
                cases = page.locator("#labQaResult .lab-case").count()
                cites = page.locator("#labQaResult .lab-cite").count()
                paras = page.locator("#labQaResult .lab-para").count()
                disclaimer = "不构成诊断意见" in text
                ok = (tier != "refuse" and (cases + cites) >= 1 and paras >= 1 and disclaimer) \
                    if group == "answer" else (tier == "refuse" and disclaimer) \
                    if group == "refuse" else disclaimer
                rows.append((group, q, tier, ok, cases, cites, paras, disclaimer, text[:180].replace("\n", " ")))

        browser.close()

    answer_rows = [r for r in rows if r[0] == "answer"]
    refuse_rows = [r for r in rows if r[0] == "refuse"]
    watch_rows = [r for r in rows if r[0] == "watch"]
    ans_ok = sum(1 for r in answer_rows if r[3])
    ref_ok = sum(1 for r in refuse_rows if r[3])
    disc_ok = sum(1 for r in rows if r[7])
    total_ok = sum(1 for r in rows if r[3])
    errors = errors if isinstance(errors, list) else []
    passed = ans_ok == len(answer_rows) and ref_ok == len(refuse_rows) and disc_ok == len(rows) and not errors

    lines = [
        "# 学生影像问答 · 30 条最小评测集",
        "",
        f"- 应回答：{ans_ok}/{len(answer_rows)}",
        f"- 应拒答：{ref_ok}/{len(refuse_rows)}",
        f"- 声明覆盖：{disc_ok}/{len(rows)}",
        f"- 观察项（不计通过线）：{sum(1 for r in watch_rows if r[3])}/{len(watch_rows)}",
        f"- 通过：{'是' if passed else '否'}",
        "",
        "| 组 | 问题 | 结果 | 判定 | E1 | L1/L2 | 段落 | 声明 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for group, q, tier, ok, cases, cites, paras, disclaimer, _ in rows:
        lines.append(f"| {group} | {q} | {tier} | {'通过' if ok else '失败'} | {cases} | {cites} | {paras} | {'有' if disclaimer else '缺'} |")
    if errors:
        lines += ["", "## 页面错误", ""] + [f"- {e}" for e in errors[:10]]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")

    for group, q, tier, ok, cases, cites, paras, disclaimer, _ in rows:
        print(("  ✓ " if ok else "  ✗ ") + f"[{group}] {q} -> {tier} (E1={cases}, L={cites}, 段落={paras}, 声明={disclaimer})")
    print(f"{total_ok}/{len(rows)} passed -> {OUT}")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
