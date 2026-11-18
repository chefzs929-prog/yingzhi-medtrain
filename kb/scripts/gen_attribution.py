#!/usr/bin/env python3
"""根据 cases.jsonl 与 rejected.json 重新生成署名文件。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cases = [json.loads(l) for l in (ROOT / "data" / "cases.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]
rej = json.loads((ROOT / "data" / "rejected.json").read_text(encoding="utf8"))
groups = {g["id"]: g["name"] for g in
          (json.loads(l) for l in (ROOT / "data" / "groups.jsonl").read_text(encoding="utf8").splitlines() if l.strip())}

lines = [
    "# 图像署名与许可（ATTRIBUTION）",
    "",
    "本目录图像均来自 Wikimedia Commons，仅使用 CC0、CC BY 或 CC BY-SA 许可。",
    "每张图仅按宽 900 px 生成缩略图，未裁剪、未修改影像内容；衍生版本沿用原许可。",
    "已逐张人工核验：不包含患者姓名、ID、检查日期等可识别信息。",
    "",
    f"共 {len(cases)} 张，按影像组归类。",
    "",
    "| 文件 | 标题 | 影像组 | 作者 | 许可 | 来源 |",
    "| --- | --- | --- | --- | --- | --- |",
]
for c in cases:
    lines.append(
        f"| {c['image']} | {c['title']} | {groups.get(c.get('group_id', ''), '未分组')} | "
        f"{c['artist']} | {c['license']} | {c['source_page']} |"
    )

lines += ["", "## 排除记录", "", "| 候选文件 | 排除原因 |", "| --- | --- |"]
for r in rej:
    lines.append(f"| {r['candidate']} | {r['reason']} |")

lines += [
    "",
    "## 使用边界",
    "",
    "- 图像仅用于教学对照与征象观察，不用于诊断，不对个体影像给出结论。",
    "- 同一影像组按影像表现或公开描述归类，不代表同一疾病。",
    "- CC BY-SA 图像若被再分发，须保留作者署名、许可标识与来源链接。",
    "- 如权利人提出异议，删除对应文件并从索引中移除。",
    "",
]
(ROOT / "licenses" / "ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf8")
print("attribution rows", len(cases), "rejected", len(rej))
