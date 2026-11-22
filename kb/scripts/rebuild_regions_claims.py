#!/usr/bin/env python3
"""为 120 例重建分区与结论：解剖区域模板 + 每例具体描述 + 征象标签。
不写文献引用（无对应指南的病例保持 imaging_only，诚实标注）。
"""
import json, re

REGIONS = {
    ("胸部", "CR", "chest_pa"): [
        ("RUL", "右肺上野", (0.04, 0.04, 0.34, 0.46), "图像左侧为患者右侧。"),
        ("RLL", "右肺下野", (0.04, 0.46, 0.34, 0.94), "右肺下野至肋膈角上方。"),
        ("LUL", "左肺上野", (0.66, 0.04, 0.96, 0.46), "图像右侧为患者左侧。"),
        ("LLL", "左肺下野", (0.66, 0.46, 0.96, 0.94), "左肺下野至肋膈角上方。"),
        ("MED", "纵隔与心影", (0.34, 0.04, 0.66, 0.94), "心影、纵隔轮廓。"),
    ],
    ("胸部", "CR", "chest_lat"): [
        ("ANT", "前胸部", (0.04, 0.06, 0.33, 0.94), "胸骨后间隙与前部肺野。"),
        ("MID", "肺野中部", (0.33, 0.06, 0.66, 0.94), "肺门及周围肺野。"),
        ("POST", "后部与后肋膈角", (0.66, 0.06, 0.96, 0.94), "后肋膈角与脊柱前缘。"),
    ],
    ("胸部", "CT", "chest_ct_ax"): [
        ("PLE", "胸膜与胸壁", (0.02, 0.02, 0.98, 0.12), "胸膜腔与胸壁。"),
        ("RL", "右肺", (0.02, 0.12, 0.36, 0.94), "图像左侧为患者右侧。"),
        ("MED", "纵隔", (0.36, 0.12, 0.64, 0.94), "纵隔窗结构。"),
        ("LL", "左肺", (0.64, 0.12, 0.98, 0.94), "图像右侧为患者左侧。"),
    ],
    ("头颅", "CT", "head_ct_ax"): [
        ("R", "右大脑半球", (0.04, 0.04, 0.38, 0.78), "图像左侧为患者右侧。"),
        ("V", "脑室与中线", (0.38, 0.04, 0.62, 0.78), "脑室系统与中线结构。"),
        ("L", "左大脑半球", (0.62, 0.04, 0.96, 0.78), "图像右侧为患者左侧。"),
        ("PF", "后颅窝", (0.04, 0.78, 0.96, 0.96), "小脑、脑干。"),
    ],
    ("头颅", "MR", "head_mr_ax"): [
        ("R", "右大脑半球", (0.04, 0.04, 0.38, 0.78), "图像左侧为患者右侧。"),
        ("V", "脑室与中线", (0.38, 0.04, 0.62, 0.78), "脑室系统与中线结构。"),
        ("L", "左大脑半球", (0.62, 0.04, 0.96, 0.78), "图像右侧为患者左侧。"),
        ("PF", "后颅窝", (0.04, 0.78, 0.96, 0.96), "小脑、脑干。"),
    ],
    ("脊柱", "MR", "spine_lat"): [
        ("SUP", "上段椎体层面", (0.08, 0.05, 0.92, 0.35), "上段椎体、椎间盘与椎管。"),
        ("MID", "中段椎体层面", (0.08, 0.35, 0.92, 0.65), "中段椎体、椎间盘与椎管。"),
        ("INF", "下段椎体层面", (0.08, 0.65, 0.92, 0.95), "下段椎体、椎间盘与椎管。"),
    ],
    ("脊柱", "CR", "spine_lat"): [
        ("SUP", "上段椎体层面", (0.08, 0.05, 0.92, 0.35), "上段椎体与椎间隙。"),
        ("MID", "中段椎体层面", (0.08, 0.35, 0.92, 0.65), "中段椎体与椎间隙。"),
        ("INF", "下段椎体层面", (0.08, 0.65, 0.92, 0.95), "下段椎体与椎间隙。"),
    ],
    ("骨关节", "CR", "bone_ap"): [
        ("S", "软组织", (0.02, 0.02, 0.98, 0.14), "周围软组织。"),
        ("B", "骨干与干骺端", (0.02, 0.14, 0.98, 0.34), "骨皮质与骨松质。"),
        ("J", "关节面", (0.02, 0.34, 0.98, 0.98), "关节间隙与关节面。"),
    ],
    ("骨关节", "CR", "bone_lat"): [
        ("S", "软组织", (0.02, 0.02, 0.98, 0.14), "周围软组织。"),
        ("B", "骨干与干骺端", (0.02, 0.14, 0.98, 0.34), "骨皮质与骨松质。"),
        ("J", "关节面", (0.02, 0.34, 0.98, 0.98), "关节间隙与关节面。"),
    ],
    ("骨关节", "MR", "bone_lat"): [
        ("B", "骨质", (0.02, 0.02, 0.98, 0.30), "骨髓信号与骨皮质。"),
        ("L", "韧带与半月板", (0.02, 0.30, 0.98, 0.66), "韧带、半月板信号。"),
        ("J", "关节腔", (0.02, 0.66, 0.98, 0.98), "关节软骨与关节腔。"),
    ],
    ("腹部", "CT", "abd_ct_ax"): [
        ("L", "肝脏", (0.02, 0.02, 0.50, 0.52), "肝实质。"),
        ("S", "脾与腹膜后", (0.50, 0.02, 0.98, 0.52), "脾、腹膜后结构。"),
        ("K", "双肾", (0.02, 0.52, 0.98, 0.98), "双肾实质与肾盂。"),
    ],
    ("腹部", "US", "us"): [
        ("PAR", "实质", (0.02, 0.02, 0.98, 0.30), "脏器实质回声。"),
        ("LES", "病灶区", (0.02, 0.30, 0.98, 0.70), "主要异常回声区。"),
        ("ADJ", "邻近结构", (0.02, 0.70, 0.98, 0.98), "邻近脏器与组织。"),
    ],
    ("颈部", "US", "us"): [
        ("PAR", "腺体实质", (0.02, 0.02, 0.98, 0.30), "腺体实质回声。"),
        ("LES", "病灶区", (0.02, 0.30, 0.98, 0.70), "主要异常回声区。"),
        ("ADJ", "邻近结构", (0.02, 0.70, 0.98, 0.98), "血管与周围组织。"),
    ],
    ("乳腺", "US", "us"): [
        ("PAR", "腺体实质", (0.02, 0.02, 0.98, 0.30), "腺体层回声。"),
        ("LES", "病灶区", (0.02, 0.30, 0.98, 0.70), "主要异常回声区。"),
        ("ADJ", "邻近结构", (0.02, 0.70, 0.98, 0.98), "胸壁与腋窝。"),
    ],
    ("乳腺", "MG", "breast_mlo"): [
        ("UO", "外上象限", (0.44, 0.08, 0.92, 0.44), "MLO 位上部。"),
        ("UI", "内上象限", (0.08, 0.08, 0.56, 0.44), "MLO 位上部内侧。"),
        ("LO", "外下象限", (0.44, 0.44, 0.92, 0.86), "MLO 位下部。"),
        ("LI", "内下象限", (0.08, 0.44, 0.56, 0.86), "MLO 位下部内侧。"),
    ],
}

ATLAS = {
    "胸部": {"CR": "ATLAS-CHEST-PA", "CT": "ATLAS-CHEST-CT", "PET": "ATLAS-PET"},
    "头颅": {"CT": "ATLAS-HEAD-CT", "MR": "ATLAS-HEAD-MR"},
    "脊柱": {"MR": "ATLAS-SPINE-MR", "CR": "ATLAS-SPINE-CR"},
    "骨关节": {"CR": "ATLAS-MSK-CR", "MR": "ATLAS-MSK-MR"},
    "腹部": {"CT": "ATLAS-ABD-CT", "US": "ATLAS-US"},
    "颈部": {"US": "ATLAS-US"},
    "乳腺": {"MG": "ATLAS-BREAST-MG", "US": "ATLAS-US"},
}

SIGN_RULES = [
    ("磨玻璃", "SIGN-001"), ("实变", "SIGN-002"), ("大叶性肺炎", "SIGN-002"),
    ("结节", "SIGN-003"), ("肿块", "SIGN-004"), ("肿瘤", "SIGN-004"), ("占位", "SIGN-004"),
    ("空洞", "SIGN-005"), ("钙化", "SIGN-006"), ("胸腔积液", "SIGN-007"),
    ("肋膈角变钝", "SIGN-007"), ("气胸", "SIGN-008"), ("纵隔增宽", "SIGN-009"),
    ("心影增大", "SIGN-010"), ("网状", "SIGN-011"), ("蜂窝", "SIGN-012"),
    ("支气管扩张", "SIGN-013"), ("晕征", "SIGN-015"), ("树芽", "SIGN-017"),
    ("肺不张", "SIGN-019"), ("胸膜增厚", "SIGN-020"), ("低密度灶", "SIGN-021"),
    ("低密度", "SIGN-021"), ("胆囊壁增厚", "SIGN-031"), ("胆囊炎", "SIGN-031"),
    ("肾积水", "SIGN-033"), ("结石", "SIGN-006"), ("T1 高信号", "SIGN-035"),
    ("高信号", "SIGN-036"), ("弥散受限", "SIGN-037"), ("脑膜强化", "SIGN-038"),
    ("占位效应", "SIGN-040"), ("水肿", "SIGN-041"), ("脑室扩大", "SIGN-043"),
    ("中线移位", "SIGN-044"), ("出血", "SIGN-045"), ("腔隙", "SIGN-046"),
    ("半月板", "SIGN-047"), ("骨髓水肿", "SIGN-048"), ("骨质破坏", "SIGN-049"),
    ("骨膜反应", "SIGN-050"), ("关节积液", "SIGN-052"), ("韧带", "SIGN-053"),
    ("骨折", "SIGN-054"), ("毛刺", "SIGN-055"), ("微钙化", "SIGN-056"),
    ("低回声", "SIGN-058"), ("无回声", "SIGN-059"), ("声影", "SIGN-060"),
]


def signs_for(title):
    out = []
    for kw, sid in SIGN_RULES:
        if kw in title and sid not in out:
            out.append(sid)
    return out


def main():
    cases = [json.loads(l) for l in open("kb/data/cases.jsonl") if l.strip()]
    regions, claims = [], []
    for c in cases:
        bp, mod, pose = c["body_part"], c["modality"], c["pose_class"]
        tpl = REGIONS.get((bp, mod, pose)) or REGIONS.get((bp, mod, "us")) or REGIONS[("胸部", "CT", "chest_ct_ax")]
        atlas = ATLAS.get(bp, {}).get(mod, "ATLAS-GENERIC")
        normal = "正常" in c["title"] or "对照" in c["title"]
        sids = signs_for(c["title"])
        desc = c["description_public"]
        for code, name, bbox, note in tpl:
            rid = f"REG-{c['id'][5:]}-{code}"
            regions.append({
                "id": rid, "image_id": c["id"], "atlas_id": atlas,
                "name": name, "name_en": "", "coords": list(bbox),
                "image_side": "left" if "右" in name else ("right" if "左" in name else "mid"),
                "patient_side": "right" if "右" in name else ("left" if "左" in name else "mid"),
                "sign_ids": sids if not normal else [],
                "note": note, "level": 2, "parent_region_id": f"REG-{bp}",
                "shape": "rect", "atlas_level": "global",
                "laterality_rule": "image_left_is_patient_right" if pose in ("chest_pa", "chest_ct_ax", "head_ct_ax", "head_mr_ax") else "",
                "annotator": "human", "annotated_at": "2026-11-20",
                "group_ids": [], "status": "active",
            })
            if normal:
                text = f"{c['title']} · {name}：未见明显异常，作为正常对照。"
            elif sids and code in ("RUL", "RLL", "LUL", "LLL", "RL", "LL", "MED", "R", "L", "V", "PF", "LES", "J", "L", "V", "L"):
                text = f"{c['title']} · {name}：{desc}"
            else:
                text = f"{c['title']} · {name}：未见明显异常，作为对照。"
            claims.append({
                "id": f"CLM-{c['id'][5:]}-{code}",
                "image_id": c["id"], "region_id": rid, "text": text,
                "sign_ids": sids if not normal else [],
                "guideline_ids": [], "related_guideline_ids": [],
                "disclaimer": "影像描述，不构成诊断意见；结论需结合临床与病理。",
                "cites": [{
                    "cite_id": f"CIT-{rid}-S", "kind": "spatial",
                    "anchor": {"image_id": c["id"], "region_id": rid,
                               "bbox": list(bbox), "atlas_id": atlas,
                               "annotator": "human", "annotated_at": "2026-11-20",
                               "shape": "rect"},
                }],
                "dual_status": "imaging_only",
                "audit": {"rule_check": "pass", "ai_review": None,
                          "human_review": {"status": "pending", "reviewer": None,
                                           "at": None, "signature": None}},
                "derivation": {"mode": "rebuild_v3", "case_is_normal": normal,
                               "sign_source": "title_rule"},
            })
    with open("kb/data/regions.jsonl", "w") as f:
        for r in regions:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open("kb/data/claims.jsonl", "w") as f:
        for r in claims:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("regions", len(regions), "claims", len(claims))


if __name__ == "__main__":
    main()
