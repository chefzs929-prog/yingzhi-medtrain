#!/usr/bin/env python3
"""按影像说明批量修正 modality / body_part，并停用非影像素材。

只处理有明确文字证据的病例：
  - 说明写 MRI / CT / 超声，modality 却是 CR 的；
  - 说明写腰椎 / 鼻骨 / 头颅，body_part 明显跨大部位的；
  - 检查场景照片、大体标本照片（无法承载分区标注）→ status=inactive。

不做的事：不重写这些病例的分区与结论（那需要逐例看图 + 医学核验）。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb" / "data"

INACTIVE = {
    "CASE-111": "乳腺摄影技师摆位照片，非影像素材",
    "CASE-114": "乳腺影像中心诊室照片，非影像素材",
    "CASE-125": "肝脏大体标本照片，非影像素材",
    "CASE-131": "乳腺摄影技师摆位照片，非影像素材",
    "CASE-139": "乳腺影像中心门口照片，非影像素材",
}

MR = re.compile(r"(\bMRI\b|magnetic\s+resonance|T1[- ]weighted|T2[- ]weighted|FLAIR|DWI)", re.I)
CT = re.compile(r"(\bCT\b|computed\s+tomography|PET/CT)", re.I)
US = re.compile(r"(\bultrasound\b|\bUS\b|sonograph|B-mode|\bSWE\b)", re.I)
XR = re.compile(r"(radiograph|\bX-?ray\b|chest film|plain film)", re.I)


def main():
    path = DATA / "cases.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
    changed = []
    for c in cases:
        if c["id"] in INACTIVE:
            c["status"] = "inactive"
            c["material_note"] = INACTIVE[c["id"]]
            changed.append((c["id"], "停用", INACTIVE[c["id"]]))
            continue

        text = f"{c.get('title', '')} {c.get('description_public', '')}"
        mods = set(m.upper() for m in (c.get("modality") if isinstance(c.get("modality"), list) else [c.get("modality")]))
        want = set()
        if MR.search(text):
            want.add("MR")
        if CT.search(text):
            want.add("CT")
        if US.search(text):
            want.add("US")
        if XR.search(text):
            want.add("CR")
        if not want:
            continue
        # 只修「明显缺项」：说明里出现的模态没有出现在 modality 中
        if not (want & mods):
            new = sorted(want, key=lambda x: ["CT", "MR", "US", "CR"].index(x) if x in ["CT", "MR", "US", "CR"] else 9)
            changed.append((c["id"], "模态", f"{sorted(mods)} → {new}"))
            c["modality"] = new
            continue
        # 说明里同时出现多种模态时补齐
        if len(want) > 1 and not want <= mods:
            new = sorted(mods | want, key=lambda x: ["CT", "MR", "US", "CR"].index(x) if x in ["CT", "MR", "US", "CR"] else 9)
            changed.append((c["id"], "模态补齐", f"{sorted(mods)} → {new}"))
            c["modality"] = new

    # 部位错配：说明写腰椎/鼻骨，body_part 却跨到头颅/颈椎/胸部
    for c in cases:
        text = f"{c.get('title', '')} {c.get('description_public', '')}"
        if re.search(r"(lumbar|L1|L2|L3|L4|L5|S1)", text, re.I) and c.get("body_part") in ("头颅", "颈椎", "胸部"):
            changed.append((c["id"], "部位", f"{c['body_part']} → 腰椎"))
            c["body_part"] = "腰椎"
        elif re.search(r"(nose|nasal)", text, re.I) and c.get("body_part") in ("胸部", "头颅"):
            changed.append((c["id"], "部位", f"{c['body_part']} → 骨"))
            c["body_part"] = "骨"
        elif re.search(r"(head ct|ct head|brain)", text, re.I) and c.get("body_part") == "腹部":
            changed.append((c["id"], "部位", "腹部 → 头颅"))
            c["body_part"] = "头颅"

    path.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf8")
    print(f"changed {len(changed)}")
    for row in changed:
        print("  ", row)


if __name__ == "__main__":
    main()
