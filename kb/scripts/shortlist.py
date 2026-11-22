#!/usr/bin/env python3
"""候选初筛：按标题与描述剔除人物照、标本、病理、图表，保留医学影像。"""
import json
import re
from pathlib import Path

CAND = Path(__file__).resolve().parent.parent / "_candidates2"
m = json.loads((CAND / "manifest.json").read_text(encoding="utf8"))

BAD = re.compile(
    r"\b(nurse|doctor|physician|technician|portrait|specimen|gross|histolog|autopsy|"
    r"diagram|chart|logo|icon|poster|cover|bedside)\b",
    re.I,
)
GOOD = re.compile(r"(radiograph|x-?ray|ct\b|mri|mr\b|ultrasound|sonograph|mammogra|scan|tomograph)", re.I)

kept, dropped = [], []
for i, it in enumerate(m, 1):
    blob = (it["title"] + " " + it.get("description", ""))
    if not it.get("file"):
        continue
    if BAD.search(blob):
        dropped.append((i, "文字初筛：" + BAD.search(blob).group(0), it))
    elif it["group_id"] == "GRP-NORMAL" and not GOOD.search(blob):
        dropped.append((i, "正常组缺少影像关键词", it))
    else:
        kept.append((i, it))

print(f"kept {len(kept)} / dropped {len(dropped)}")
for i, it in kept:
    print(f"{i:03d} {it['group_id']:24s} {it['modality']:3s} {it['license_short'][:14]:14s} {it['title'][5:80]}")
print("--- dropped ---")
for i, why, it in dropped[:12]:
    print(f"{i:03d} {why:16s} {it['title'][5:70]}")

(CAND / "shortlist.json").write_text(
    json.dumps({"kept": [i for i, _ in kept], "dropped": [{"idx": i, "reason": w} for i, w, _ in dropped]},
               ensure_ascii=False, indent=2), encoding="utf8")
