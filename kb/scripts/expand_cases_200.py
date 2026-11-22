#!/usr/bin/env python3
"""把病例从 120 扩到 200：用已下载的公开许可候选影像 + 现有体位模板。

只做"可追溯的扩容"：
  - 影像来自 kb/_candidates(_2) 的 manifest，许可为 CC0/PD/CC-BY/CC-BY-SA
  - 分区套用现有 17 套体位模板，不新造解剖
  - 新病例标记 corpus=expanded_200、privacy_check=auto_screened_pending_human
  - 不覆盖原库，输出 kb/data/v3/

输出：v3/cases.jsonl（200）、v3/regions.jsonl、v3/images/（复制的新图）
"""
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "kb"
DATA = KB / "data"
OUT = DATA / "v3"
TODAY = "2026-11-18"
TARGET = 200

load = lambda n: [json.loads(l) for l in (DATA / n).read_text(encoding="utf8").splitlines() if l.strip()]
cases = load("cases.jsonl")
regions = load("regions.jsonl")
signs = load("signs.jsonl")

# ---------- 体位模板（与 build_corpus_120.py 同源，只取必要字段） ----------
TEMPLATES = {
    "chest_pa": ("ATLAS-CHEST-PA-6", "胸部", "pa_chest: image_left = patient_right", [
        ("RUL", "右肺上野", "right upper lung zone", [0.115, 0.09, 0.36, 0.26], "right", "肺尖至第 2 前肋下缘水平。", "lung"),
        ("RML", "右肺中野", "right middle lung zone", [0.115, 0.35, 0.36, 0.26], "right", "第 2 至第 4 前肋下缘之间。", "lung"),
        ("RLL", "右肺下野", "right lower lung zone", [0.115, 0.61, 0.36, 0.26], "right", "第 4 前肋下缘至膈面。", "lung"),
        ("LUL", "左肺上野", "left upper lung zone", [0.525, 0.09, 0.36, 0.26], "left", "肺尖至第 2 前肋下缘水平。", "lung"),
        ("LML", "左肺中野", "left middle lung zone", [0.525, 0.35, 0.36, 0.26], "left", "第 2 至第 4 前肋下缘之间。", "lung"),
        ("LLL", "左肺下野", "left lower lung zone", [0.525, 0.61, 0.36, 0.26], "left", "第 4 前肋下缘至膈面。", "lung"),
        ("MED", "纵隔区", "mediastinum", [0.40, 0.14, 0.20, 0.52], "midline", "脊柱旁开至心影右缘，含气管与肺门区。", "mediastinum"),
        ("SUBD", "膈下区", "subdiaphragmatic", [0.12, 0.87, 0.76, 0.10], "midline", "膈面以下，含胃泡与肝右叶顶部。", "subdiaph"),
    ]),
    "chest_ct_ax": ("ATLAS-CHEST-CT-5", "胸部", "axial_ct: image_left = patient_right", [
        ("RUL", "右肺上叶", "right upper lobe", [0.08, 0.10, 0.34, 0.34], "right", "气管分叉以上层面的右肺。", "lung"),
        ("RLL", "右肺下叶", "right lower lobe", [0.08, 0.46, 0.34, 0.44], "right", "斜裂后方的右肺。", "lung"),
        ("LUL", "左肺上叶", "left upper lobe", [0.58, 0.10, 0.34, 0.34], "left", "斜裂前方的左肺。", "lung"),
        ("LLL", "左肺下叶", "left lower lobe", [0.58, 0.46, 0.34, 0.44], "left", "斜裂后方的左肺。", "lung"),
        ("MED", "纵隔窗区", "mediastinal window", [0.40, 0.12, 0.20, 0.50], "midline", "纵隔结构、血管与淋巴结。", "mediastinum"),
    ]),
    "abd_ct_ax": ("ATLAS-ABD-CT-4", "腹部", "axial_ct: image_left = patient_right", [
        ("LIVER", "肝区", "liver", [0.10, 0.10, 0.40, 0.34], "right", "肝右叶与左叶大部。", "abdomen"),
        ("SPLEEN", "脾区", "spleen", [0.66, 0.12, 0.22, 0.24], "left", "脾脏与脾门。", "abdomen"),
        ("KIDNEY", "肾区", "kidney", [0.12, 0.48, 0.34, 0.28], "bilateral", "双肾实质与肾盂。", "abdomen"),
        ("BOWEL", "肠管区", "bowel", [0.46, 0.34, 0.30, 0.38], "midline", "小肠与结肠肠管。", "abdomen"),
    ]),
    "us_local": ("ATLAS-US-LOCAL-3", "甲状腺", "us_local: no_laterality_inference", [
        ("RIGHT", "右侧腺叶", "right lobe", [0.10, 0.20, 0.36, 0.58], "right", "右侧甲状腺腺叶。", "thyroid"),
        ("LEFT", "左侧腺叶", "left lobe", [0.54, 0.20, 0.36, 0.58], "left", "左侧甲状腺腺叶。", "thyroid"),
        ("ISTHMUS", "峡部", "isthmus", [0.44, 0.30, 0.12, 0.36], "midline", "连接两侧腺叶的峡部。", "thyroid"),
    ]),
    "breast_mlo": ("ATLAS-BREAST-MLO-4", "乳腺", "mlo: image_left = patient_right", [
        ("UOQ", "上外象限", "upper outer quadrant", [0.10, 0.08, 0.38, 0.34], "unknown", "乳腺上外象限。", "breast"),
        ("UIQ", "上内象限", "upper inner quadrant", [0.52, 0.08, 0.38, 0.34], "unknown", "乳腺上内象限。", "breast"),
        ("LOQ", "下外象限", "lower outer quadrant", [0.10, 0.44, 0.38, 0.30], "unknown", "乳腺下外象限。", "breast"),
        ("LIQ", "下内象限", "lower inner quadrant", [0.52, 0.44, 0.38, 0.30], "unknown", "乳腺下内象限。", "breast"),
    ]),
    "knee_ap": ("ATLAS-KNEE-AP-4", "膝关节", "knee_ap: image_left = patient_right", [
        ("FEMUR", "股骨远端", "distal femur", [0.26, 0.04, 0.48, 0.32], "unknown", "股骨内外髁及髁间窝。", "bone"),
        ("TIBIA", "胫骨近端", "proximal tibia", [0.26, 0.52, 0.46, 0.36], "unknown", "胫骨平台与近端干骺端。", "bone"),
        ("FIBULA", "腓骨近端", "proximal fibula", [0.72, 0.50, 0.16, 0.34], "unknown", "腓骨头与腓骨颈。", "bone"),
        ("JOINT", "关节间隙", "joint space", [0.26, 0.38, 0.48, 0.14], "midline", "股胫关节间隙，含髁间嵴。", "joint"),
    ]),
    "head_mr_ax": ("ATLAS-HEAD-MR-4", "头颅", "axial_mr: image_left = patient_right", [
        ("FRONT", "额叶区", "frontal lobe", [0.14, 0.10, 0.34, 0.34], "unknown", "额叶皮层与白质。", "brain"),
        ("PARIET", "顶叶区", "parietal lobe", [0.50, 0.10, 0.34, 0.34], "unknown", "顶叶皮层与白质。", "brain"),
        ("TEMP", "颞叶区", "temporal lobe", [0.14, 0.46, 0.30, 0.34], "unknown", "颞叶与海马区。", "brain"),
        ("VENT", "脑室区", "ventricles", [0.40, 0.36, 0.22, 0.30], "midline", "侧脑室与第三脑室。", "brain"),
    ]),
    "cspine_lat": ("ATLAS-CSPINE-LAT-3", "颈椎", "lateral: no_laterality_inference", [
        ("UPPER", "上颈段", "upper cervical", [0.20, 0.08, 0.56, 0.28], "midline", "C1—C3 椎体与寰枢关节。", "bone"),
        ("MID", "中颈段", "mid cervical", [0.20, 0.36, 0.56, 0.28], "midline", "C4—C5 椎体与椎间隙。", "bone"),
        ("LOWER", "下颈段", "lower cervical", [0.20, 0.64, 0.56, 0.28], "midline", "C6—C7 椎体与颈胸交界。", "bone"),
    ]),
    "limb_local": ("ATLAS-LIMB-LOCAL-3", "骨", "local: no_laterality_inference", [
        ("PROX", "近端", "proximal", [0.16, 0.10, 0.68, 0.26], "unknown", "骨近端与关节面。", "bone"),
        ("SHAFT", "骨干", "diaphysis", [0.16, 0.36, 0.68, 0.28], "unknown", "骨干皮质与髓腔。", "bone"),
        ("DIST", "远端", "distal", [0.16, 0.64, 0.68, 0.26], "unknown", "骨远端与关节面。", "bone"),
    ]),
}

SIGN_GROUP = {"lung": {"肺"}, "pleura": {"胸膜"}, "mediastinum": {"纵隔"},
              "subdiaph": {"腹腔", "腹部"}, "bone": {"骨"}, "joint": {"关节", "骨"},
              "brain": {"脑"}, "abdomen": {"腹部", "肝脏", "胰胆", "肾脏", "胆囊", "胰腺", "腹腔", "肠道"},
              "breast": {"乳腺"}, "thyroid": {"甲状腺"}, "soft": {"全身"}}
signs_by_part = defaultdict(list)
for s in signs:
    signs_by_part[s.get("body_part", "")].append(s["id"])

def pick_signs(key, n=3):
    pool = []
    for p in SIGN_GROUP.get(key, {"全身"}):
        pool.extend(signs_by_part.get(p, []))
    return list(dict.fromkeys(pool))[:n]

# ---------- 候选影像 ----------
BP = {"肺": "胸部", "胸膜": "胸部", "胸": "胸部", "胸部": "胸部", "头颅": "头颅",
      "甲状腺": "甲状腺", "乳腺": "乳腺", "肝": "腹部", "肾": "腹部", "胆囊": "腹部",
      "腹部": "腹部", "膝": "膝关节", "膝关节": "膝关节", "脊柱": "颈椎", "骨": "骨"}
MOD = {"CR": "CR", "CT": "CT", "US": "US", "MR": "MR", "MRI": "MR", "MG": "MG"}

def to_pose(bp, mod):
    b = BP.get(bp)
    m = MOD.get(str(mod).split(",")[0].strip("[]' "))
    if b == "胸部":
        return "chest_pa" if m == "CR" else ("chest_ct_ax" if m == "CT" else None)
    if b == "头颅":
        return "head_mr_ax" if m == "MR" else None
    if b == "甲状腺":
        return "us_local" if m == "US" else None
    if b == "乳腺":
        return "breast_mlo" if m == "MG" else None
    if b == "腹部":
        return "abd_ct_ax" if m == "CT" else None
    if b == "膝关节":
        return "knee_ap" if m in ("CR", "MR") else None
    if b == "颈椎":
        return "cspine_lat"
    if b == "骨":
        return "limb_local"
    return None

cands = []
for d in ("_candidates", "_candidates2"):
    p = KB / d / "manifest.json"
    if not p.exists():
        continue
    for x in json.loads(p.read_text(encoding="utf8")):
        if not x.get("file"):
            continue
        pose = to_pose(x.get("body_part"), x.get("modality"))
        src = KB / d / x["file"]
        if not pose or not src.exists():
            continue
        cands.append({**x, "_dir": d, "_src": src, "_pose": pose})

# 去重：同一描述前 60 字 + 部位
seen, uniq = set(), []
for c in cands:
    key = (re.sub(r"\W+", "", (c.get("description") or "")[:60]), c.get("body_part"))
    if key in seen:
        continue
    seen.add(key)
    uniq.append(c)

# 排序：许可更宽松优先，再按部位均衡
LIC_RANK = {"cc0": 0, "pd": 0, "public domain": 0, "cc-by-4.0": 1, "cc-by-2.0": 1,
            "cc-by-sa-4.0": 2, "cc-by-sa-3.0": 2}
uniq.sort(key=lambda c: (LIC_RANK.get(str(c.get("license_code")).lower(), 9), c["_pose"]))

by_pose = defaultdict(list)
for c in uniq:
    by_pose[c["_pose"]].append(c)

need = TARGET - len(cases)
chosen = []
poses = sorted(by_pose, key=lambda p: -len(by_pose[p]))
while len(chosen) < need and any(by_pose[p] for p in poses):
    for p in poses:
        if by_pose[p] and len(chosen) < need:
            chosen.append(by_pose[p].pop(0))

print(f"候选可映射 {len(uniq)}，需要 {need}，选中 {len(chosen)}")
print("选中分布", dict(Counter(c["_pose"] for c in chosen)))

# ---------- 建病例 ----------
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "images").mkdir(exist_ok=True)
new_cases, new_regions = [], []
for i, c in enumerate(chosen, 1):
    num = len(cases) + i
    cid = f"CASE-{num:03d}"
    ext = Path(c["file"]).suffix.lower()
    fname = f"case-{num:03d}{ext}"
    shutil.copy2(c["_src"], OUT / "images" / fname)
    atlas_id, body_part, lat_rule, rlist = TEMPLATES[c["_pose"]]
    desc = (c.get("description") or "").strip()
    title = f"{body_part}公开影像 {num:03d}"
    new_cases.append({
        "id": cid, "title": title, "modality": MOD.get(str(c.get("modality")).split(",")[0].strip("[]' "), str(c.get("modality"))),
        "body_part": body_part, "image": f"images/{fname}",
        "source_id": "SRC-COMMONS", "source_page": c.get("original") or c.get("source_page") or "",
        "license": c.get("license_short") or c.get("license_code") or "",
        "artist": c.get("artist") or "", "description_public": desc[:300],
        "sign_tags": [], "teaching_note": f"公开影像，用于{body_part}区位对照。",
        "privacy_check": "auto_screened_pending_human", "verified_at": TODAY,
        "status": "active", "group_id": "", "chapter": body_part, "pose_class": c["_pose"],
        "level": "global", "evidence_level": "C", "corpus": "expanded_200",
    })
    for key, name, name_en, coords, side, note, skey in rlist:
        new_regions.append({
            "id": f"REG-{num:03d}-{key}", "image_id": cid, "atlas_id": atlas_id,
            "name": name, "name_en": name_en, "coords": coords,
            "image_side": "", "patient_side": side, "sign_ids": pick_signs(skey),
            "note": note, "level": 2, "parent_region_id": f"REG-{body_part}",
            "shape": "rect", "atlas_level": "global", "laterality_rule": lat_rule,
            "annotator": "template", "annotated_at": TODAY, "group_ids": [], "status": "active",
        })

# ---------- 不足 200 时：同图分区聚焦视角（明确标注共享影像） ----------
shared = 0
if len(cases) + len(new_cases) < TARGET:
    regs_by_case = defaultdict(list)
    for r in regions:
        regs_by_case[r["image_id"]].append(r)
    pool = [c for c in cases if c.get("status") == "active" and len(regs_by_case[c["id"]]) >= 4]
    pool.sort(key=lambda c: (-len(regs_by_case[c["id"]]), c["id"]))
    for c in pool:
        if len(cases) + len(new_cases) >= TARGET:
            break
        num = len(cases) + len(new_cases) + 1
        cid = f"CASE-{num:03d}"
        rs = sorted(regs_by_case[c["id"]], key=lambda r: r["coords"][1])
        keep = rs[::2][:4] or rs[:4]
        new_cases.append({
            **{k: c.get(k) for k in ("modality", "body_part", "pose_class", "license", "artist",
                                      "description_public", "chapter", "level", "evidence_level")},
            "id": cid, "title": f"{c['title']}（分区聚焦视角）",
            "image": c["image"], "source_id": c.get("source_id"), "source_page": c.get("source_page"),
            "sign_tags": c.get("sign_tags") or [], "teaching_note": "同一影像的分区聚焦视角，用于对比不同区域的读片顺序。",
            "privacy_check": c.get("privacy_check"), "verified_at": TODAY, "status": "active",
            "group_id": c.get("group_id") or "", "corpus": "expanded_200_shared",
            "shared_image_of": c["id"],
        })
        for r in keep:
            new_regions.append({
                **{k: r.get(k) for k in ("atlas_id", "name", "name_en", "coords", "image_side",
                                          "patient_side", "sign_ids", "note", "level", "parent_region_id",
                                          "shape", "atlas_level", "laterality_rule", "group_ids")},
                "id": f"REG-{num:03d}-{r['id'].split('-')[-1]}", "image_id": cid,
                "annotator": r.get("annotator", "template"), "annotated_at": TODAY, "status": "active",
            })
        shared += 1

(OUT / "cases.jsonl").write_text(
    "\n".join(json.dumps(x, ensure_ascii=False) for x in cases + new_cases) + "\n", encoding="utf8")
(OUT / "regions.jsonl").write_text(
    "\n".join(json.dumps(x, ensure_ascii=False) for x in regions + new_regions) + "\n", encoding="utf8")

print(f"病例 {len(cases)} -> {len(cases)+len(new_cases)}")
print(f"分区 {len(regions)} -> {len(regions)+len(new_regions)}")
print("新图", len(chosen), "张，写入", OUT / "images")
print("许可", dict(Counter(c.get("license_code") for c in chosen)))
print("共享影像视角", shared, "例")
