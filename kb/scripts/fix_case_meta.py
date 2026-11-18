#!/usr/bin/env python3
"""修正两例元数据/素材错配的病例（CASE-105、CASE-122）。

- CASE-105：图片是腰椎 MRI T2 矢状位，原数据标成「头颅 / CR」，分区是
  「图像前部/中部/后部/周边带」，结论还挂在「脑膜强化」上。这里改为
  腰椎矢状位的前柱/中柱/后柱/周边分区，结论改成解剖定位与序列信号对照。
- CASE-122：图片是「患者做乳腺摄影」的检查场景照片，不是乳腺影像，
  无法承载四象限标注。改用同库真实 MLO 钼靶图，并重写象限坐标与结论。

只改这两例；其它扩容病例的元数据核验见 docs/病例元数据体检.md。
"""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb" / "data"
IMAGES = ROOT / "kb" / "images"


def load(name):
    return [json.loads(line) for line in (DATA / f"{name}.jsonl").read_text(encoding="utf8").splitlines() if line.strip()]


def save(name, rows):
    (DATA / f"{name}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf8")


def sha(text):
    return hashlib.sha256((text or "").encode("utf8")).hexdigest()


def set_doc_hash(claim):
    for cite in claim.get("cites", []):
        if cite.get("kind") != "doc":
            continue
        anchor = cite.get("anchor") or {}
        excerpt = anchor.get("excerpt", "")
        if anchor.get("excerpt_sha256"):
            anchor["excerpt_sha256"] = sha(excerpt)


cases = load("cases")
regions = load("regions")
claims = load("claims")

# ---------- CASE-122：换真实钼靶图 ----------
src = IMAGES / "case-027.jpg"
dst = IMAGES / "case-122.jpg"
if src.exists():
    shutil.copyfile(src, dst)

c122 = next(c for c in cases if c["id"] == "CASE-122")
c122.update({
    "title": "乳腺 MLO 位高密度肿块（公开影像）",
    "modality": ["MG"],
    "license": "CC BY-SA 4.0",
    "description_public": "来源公开说明为左乳高密度肿块，MLO 位。原「乳腺公开影像 122」为检查场景照片，已替换为同库真实钼靶影像。",
    "teaching_note": "用于乳腺四象限定位与高密度肿块边缘对照；影像为公开钼靶图，非诊断用途。",
})

# 四象限坐标按 MLO 腺体区域重新贴合（上外 / 上内 / 下外 / 下内）
q122 = {
    "REG-122-UOQ": ([0.10, 0.08, 0.40, 0.36], "乳腺上外象限。"),
    "REG-122-UIQ": ([0.52, 0.08, 0.36, 0.36], "乳腺上内象限。"),
    "REG-122-LOQ": ([0.10, 0.46, 0.40, 0.34], "乳腺下外象限。"),
    "REG-122-LIQ": ([0.52, 0.46, 0.36, 0.34], "乳腺下内象限。"),
}
for r in regions:
    if r["image_id"] == "CASE-122" and r["id"] in q122:
        r["coords"], r["note"] = q122[r["id"]]

# ---------- CASE-105：腰椎 MRI 元数据与分区 ----------
c105 = next(c for c in cases if c["id"] == "CASE-105")
c105.update({
    "title": "腰椎 MRI T2 矢状位（10/12）",
    "body_part": "腰椎",
    "modality": ["MR"],
    "license": "CC0",
    "description_public": "腰椎 MRI T2 加权矢状位，系列第 10/12 幅；L5-S1 小关节附近可见高信号。原数据误标为「头颅 / CR」，已按影像内容更正。",
    "teaching_note": "用于腰椎前柱/中柱/后柱分区定位与 T2 序列信号对照；不提供诊断结论。",
})

r105 = {
    "REG-105-ANT": ([0.06, 0.08, 0.44, 0.84], "前柱：椎体与终板。", "前柱 · 椎体与终板"),
    "REG-105-MID": ([0.50, 0.08, 0.20, 0.84], "中柱：椎管、硬膜囊与马尾。", "中柱 · 椎管与硬膜囊"),
    "REG-105-POST": ([0.70, 0.08, 0.24, 0.84], "后柱：棘突、关节突与椎旁肌。", "后柱 · 棘突与关节突"),
    "REG-105-EDGE": ([0.02, 0.02, 0.96, 0.96], "整幅影像的周边范围，用作整体定位，不代替具体分区。", "周边范围（整体）"),
}
for r in regions:
    if r["image_id"] == "CASE-105" and r["id"] in r105:
        coords, note, name = r105[r["id"]]
        r["coords"], r["note"], r["name"] = coords, note, name
        r["sign_ids"] = ["SIGN-036"] if r["id"] != "REG-105-ANT" else ["SIGN-048", "SIGN-036"]
        r["atlas_id"] = "ATLAS-LUMBAR-MR-SAG"

# 结论：改成解剖定位 + T2 信号对照，避免「脑膜强化」这类部位错配
c105_text = {
    "REG-105-ANT": "腰椎 MRI T2 矢状位 · 前柱（椎体与终板）：椎体骨髓在 T2 上呈中等信号，终板为低信号线。库内暂无腰椎专用结论，本条仅作解剖定位与序列信号对照，不作征象判断。",
    "REG-105-MID": "腰椎 MRI T2 矢状位 · 中柱（椎管与硬膜囊）：硬膜囊内脑脊液呈明显高信号，马尾神经根呈点条状低信号。本条仅作解剖定位与序列信号对照。",
    "REG-105-POST": "腰椎 MRI T2 矢状位 · 后柱（棘突、关节突与椎旁肌）：棘突骨髓与椎旁肌呈中等信号，小关节间隙可见。本条仅作解剖定位，不判断关节病变。",
    "REG-105-EDGE": "腰椎 MRI T2 矢状位 · 周边范围：用于整体定位与图像边界参照，不代替前柱/中柱/后柱的具体分区。",
}
for cl in claims:
    if cl["image_id"] != "CASE-105":
        continue
    rid = cl["region_id"]
    if rid not in c105_text:
        continue
    cl["text"] = c105_text[rid]
    cl["sign_ids"] = ["SIGN-048", "SIGN-036"] if rid == "REG-105-ANT" else ["SIGN-036"]
    for cite in cl.get("cites", []):
        anchor = cite.get("anchor") or {}
        if cite.get("kind") == "spatial":
            anchor["bbox"] = r105[rid][0]
            anchor["atlas_id"] = "ATLAS-LUMBAR-MR-SAG"
        if cite.get("kind") == "doc":
            anchor["doc_id"] = "SIGN-036"
            anchor["doc_title"] = "T2 高信号"
            anchor["locator"] = "SIGN-036 / 影像表现"
            anchor["excerpt"] = "T2 加权像上信号高于周围组织，常见于液体、水肿、炎症或部分顺磁性物质。"
            anchor["excerpt_sha256"] = sha(anchor["excerpt"])
    cl["dual_status"] = "dual"

# CASE-122 结论文本同步新标题
for cl in claims:
    if cl["image_id"] == "CASE-122":
        cl["text"] = cl["text"].replace("乳腺公开影像 122", "乳腺 MLO 位高密度肿块（公开影像）")
        for cite in cl.get("cites", []):
            anchor = cite.get("anchor") or {}
            if cite.get("kind") == "spatial" and cl["region_id"] in q122:
                anchor["bbox"] = q122[cl["region_id"]][0]

for cl in claims:
    if cl["image_id"] in ("CASE-105", "CASE-122"):
        set_doc_hash(cl)

save("cases", cases)
save("regions", regions)
save("claims", claims)
print("fixed CASE-105 / CASE-122")
