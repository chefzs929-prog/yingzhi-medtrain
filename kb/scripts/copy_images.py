#!/usr/bin/env python3
"""按 cases.jsonl 复制已核验图像，并生成署名文件与排除记录。"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAND = ROOT / "_candidates"
IMG = ROOT / "images"
IMG.mkdir(exist_ok=True)

MAP = {
    "CASE-001": "cand-001.jpg",
    "CASE-002": "cand-002.jpg",
    "CASE-003": "cand-003.jpg",
    "CASE-004": "cand-004.jpg",
    "CASE-005": "cand-005.jpg",
    "CASE-006": "cand-006.jpg",
    "CASE-007": "cand-007.jpg",
    "CASE-008": "cand-008.jpg",
    "CASE-009": "cand-009.jpg",
    "CASE-010": "cand-010.jpg",
    "CASE-011": "cand-024.jpg",
    "CASE-012": "cand-025.jpg",
    "CASE-013": "cand-026.jpg",
    "CASE-014": "cand-030.png",
}

REJECTED = [
    {"candidate": "cand-027.jpg", "reason": "人物检查照片，含可识别人脸与身体，不属医学影像"},
    {"candidate": "cand-032.jpg", "reason": "图像边缘含年龄标记与检查日期，隐私风险，排除"},
    {"candidate": "cand-011.jpg", "reason": "窗位异常导致图像信息丢失，不适合教学对照"},
    {"candidate": "cand-028.jpg", "reason": "统计图表而非影像，不属于阅片素材"},
]

cases = [json.loads(l) for l in (ROOT / "data" / "cases.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]
copied = []
for c in cases:
    src = CAND / MAP[c["id"]]
    if not src.exists():
        print("MISSING", c["id"], src.name)
        continue
    dst = ROOT / c["image"]
    shutil.copyfile(src, dst)
    copied.append(c)

lines = [
    "# 图像署名与许可（ATTRIBUTION）",
    "",
    "本目录图像均来自 Wikimedia Commons，仅使用 CC0、CC BY 或 CC BY-SA 许可。",
    "每张图仅按宽 900 px 生成缩略图，未裁剪、未修改影像内容；衍生版本沿用原许可。",
    "已逐张人工核验：不包含患者姓名、ID、检查日期等可识别信息。",
    "",
    "| 文件 | 标题 | 作者 | 许可 | 来源 |",
    "| --- | --- | --- | --- | --- |",
]
for c in copied:
    lines.append(
        f"| {c['image']} | {c['title']} | {c['artist']} | {c['license']} | {c['source_page']} |"
    )
lines += [
    "",
    "## 排除记录",
    "",
    "| 候选文件 | 排除原因 |",
    "| --- | --- |",
]
for r in REJECTED:
    lines.append(f"| {r['candidate']} | {r['reason']} |")
lines += [
    "",
    "## 使用边界",
    "",
    "- 图像仅用于教学对照与征象观察，不用于诊断，不对个体影像给出结论。",
    "- CC BY-SA 图像若被再分发，须保留作者署名、许可标识与来源链接。",
    "- 如权利人提出异议，删除对应文件并从索引中移除。",
    "",
]
(ROOT / "licenses" / "ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf8")
(ROOT / "data" / "rejected.json").write_text(
    json.dumps(REJECTED, ensure_ascii=False, indent=2), encoding="utf8"
)
print("copied", len(copied), "images")
