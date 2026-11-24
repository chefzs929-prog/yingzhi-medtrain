#!/usr/bin/env python3
"""第四态（unmentioned）分层抽检。

从 153 个教学分区中抽取 20 个 unmentioned，覆盖尽可能多的病例与解剖区；
优先抽“text 含具体描述但状态仍为 unmentioned”的分区，因为这类最容易自相矛盾。

输出：
  outputs/medtrain/data/audit/unmentioned_sample.json
  docs/第四态抽检_2026-11-23.md（初审列由 apply_unmentioned_review.py 回填）

用法：
  python3 kb/scripts/sample_unmentioned.py
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHEST = ROOT / "kb/data/chest_reading.json"
OUT_JSON = ROOT / "outputs/medtrain/data/audit/unmentioned_sample.json"
OUT_MD = ROOT / "docs/第四态抽检_2026-11-23.md"

TEMPLATE = "公开来源未逐区描述该分区"


def main() -> None:
    data = json.loads(CHEST.read_text(encoding="utf8"))
    pool = []
    for c in data["cases"]:
        if not c.get("enabled"):
            continue
        for z in c.get("zones", []):
            if z.get("status") != "unmentioned":
                continue
            pool.append({
                "case_id": c["id"],
                "title": c.get("title"),
                "zone_id": z.get("id"),
                "zone_name": z.get("name"),
                "zone_text": z.get("text"),
                "zone_note": z.get("note"),
                "basis": z.get("basis"),
                "case_description": c.get("description_public"),
                "teaching_note": c.get("teaching_note"),
                "caveats": c.get("caveats") or [],
                "source_page": c.get("source_page"),
                "license": c.get("license"),
                "is_template": TEMPLATE in str(z.get("text") or ""),
            })

    # 优先非模板（更可能自相矛盾），再按病例轮转，保证覆盖
    by_case = defaultdict(list)
    for row in pool:
        by_case[row["case_id"]].append(row)
    for rows in by_case.values():
        rows.sort(key=lambda r: (r["is_template"], r["zone_id"]))

    rng = random.Random(42)
    case_ids = sorted(by_case)
    rng.shuffle(case_ids)
    picked = []
    round_no = 0
    while len(picked) < 20:
        added = False
        for cid in case_ids:
            rows = by_case[cid]
            if round_no < len(rows):
                picked.append(rows[round_no])
                added = True
                if len(picked) == 20:
                    break
        if not added:
            break
        round_no += 1

    sample = {
        "generated_at": date.today().isoformat(),
        "pool_size": len(pool),
        "sample_size": len(picked),
        "cases_covered": len({r["case_id"] for r in picked}),
        "selection": "按病例轮转 + 非模板优先 + 固定种子 42；只抽 enabled 病例",
        "items": picked,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf8")

    rows = []
    for i, r in enumerate(picked, 1):
        rows.append(
            f"| {i} | {r['case_id']} | {r['zone_name']}（{r['zone_id']}） | "
            f"{'模板句' if r['is_template'] else '**含具体描述**'} | "
            f"{(r['zone_text'] or '').replace('|', '/')[:70]} | "
            f"{(r['case_description'] or '').replace('|', '/')[:60]} | 待初审 |"
        )

    md = f"""# 第四态（unmentioned）抽检 · {date.today().isoformat()}

> 样本：{len(picked)} / {len(pool)} 个 unmentioned 分区，覆盖 {len({r['case_id'] for r in picked})} 例
> 机器可读：`outputs/medtrain/data/audit/unmentioned_sample.json`
> 抽检脚本：`kb/scripts/sample_unmentioned.py`

## 0. 结论

- 58 个 unmentioned 分区里，绝大多数是模板句“公开来源未逐区描述该分区”，**不是“来源完全没提这个病例”**。
- 抽检优先纳入“text 含具体描述但仍标 unmentioned”的分区（如 CASE-005 纵隔），这类最可能自相矛盾。
- 因此对外话术必须精确：**第四态 = “来源未逐区描述”，不是“来源完全未提及该病例”。**
- 本轮为 **AI 文本证据初审**：只看病例公开说明 + 分区文本 + 教学备注，**不看像素**；最终以专家复核为准。

## 1. 判据 SOP（1 页版）

### 1.1 四个状态

| 状态 | 判据 | 允许的界面文案 |
| --- | --- | --- |
| `normal` | 来源明确写该区正常/未见异常；或正常对照病例且该区属于正常解剖 | “来源描述为正常” |
| `abnormal` | 来源明确写该区异常，且有征象或描述可对应 | “来源描述为异常” |
| `limited` | 来源说明质量受限（遮挡、体位、分辨率、伪影），不能判断 | “来源质量受限，不作推断” |
| `unmentioned` | 来源只有病例级描述/诊断，没有逐区描述；不能无歧义推断该区 | “来源未逐区描述，不作推断” |

### 1.2 三步判定

1. **直接提及？** 来源句子是否直接点名该分区？
   - 是 → `normal` / `abnormal`（记录原句）。
   - 否 → 第 2 步。
2. **病例级可无歧义推断？** 例如“正常后前位胸片”可推断各肺野正常；“双肺弥漫粟粒结节”可推断双肺各野异常。
   - 能，且推断唯一 → `normal` / `abnormal`，并在 `basis` 写“病例级推断”。
   - 不能，或存在多个解释 → 第 3 步。
3. **质量受限？** 遮挡、体位、分辨率、伪影导致无法判断 → `limited`；否则 → `unmentioned`。

### 1.3 禁止事项

- 禁止把 `unmentioned` 默认成 `normal`。
- 禁止用“通常如此”的解剖常识替代来源描述。
- 禁止在 `unmentioned` 分区上渲染异常框或正常勾选。
- 禁止把病例级诊断直接拆成逐区诊断（如“大叶性肺炎”不能自动推出每个肺野都异常）。

### 1.4 双 AI + 专家流程

- **AI-A（保守）**：只认直接提及；病例级推断必须唯一且写明依据。
- **AI-B（宽松）**：允许病例级推断，但必须给出推断链。
- **分歧处理**：A/B 不一致 → 进入专家复核队列；专家可“采纳 A / 采纳 B / 修改 / 保留 unmentioned”。
- **一致率**：报告 A/B 原始一致率与 Cohen's kappa；不一致项不得静默合并。

## 2. 抽检样本（AI 初审待回填）

| # | 病例 | 分区 | 文本类型 | 分区文本 | 病例公开说明 | AI 初审 |
| --- | --- | --- | --- | --- | --- | --- |
""" + "\n".join(rows) + f"""

## 3. 复核入口

- 专家复核页面：`outputs/medtrain/read/review.html`（待接入本样本）
- 复核导出：JSON / CSV，字段含 `item_id / ai_a / ai_b / expert_decision / note / reviewer / at`
- 复核完成后，把专家结论回写 `kb/data/chest_reading.json` 的 `zones[].status` 与 `basis`，并重跑引用审计。

---

*本页为 AI 文本证据初审，不替代影像专家判读；所有分歧保留原始 A/B 记录。*
"""
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md, encoding="utf8")
    print(json.dumps({k: sample[k] for k in ("pool_size", "sample_size", "cases_covered")}, ensure_ascii=False))
    print(f"written: {OUT_JSON.relative_to(ROOT)}")
    print(f"written: {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
