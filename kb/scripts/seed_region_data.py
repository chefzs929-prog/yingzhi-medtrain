#!/usr/bin/env python3
"""生成 v1.1 区域定位的正式标注数据。

输出：
  kb/data/atlases.jsonl   分区模板（2 套）
  kb/data/regions.jsonl   解剖分区（21 个）
  kb/data/claims.jsonl    影像-文献绑定的结论（7 条）

设计要点：
- 坐标全部归一化 [x, y, w, h]，与分辨率解耦
- image_side 与 patient_side 是两个字段，由 laterality_rule 声明映射
- doc 锚点存 excerpt + sha256 前 8 位；校验器实算比对，不一致即 broken
- CLM-007 故意保留「摘录被改写」的失败样本，用于演示门禁拦截

重新生成：python3 kb/scripts/seed_region_data.py
"""
import hashlib
import json
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
DATA = KB / "data"

ATLASES = [
    {
        "id": "ATLAS-CHEST-PA-6",
        "name": "胸片六分区（PA）",
        "level": "global",
        "modality": ["CR"],
        "body_part": "胸部",
        "method": "人工标注",
        "laterality_rule": "pa_chest: image_left = patient_right",
        "note": "第 2/4 前肋下缘水平线划分上中下野；纵隔与膈下单独成区。同一套模板复用于所有 PA 胸片。",
        "annotator": "human",
        "annotated_at": "2026-11-15",
        "images": ["CASE-001", "CASE-006"],
    },
    {
        "id": "ATLAS-THY-US-LOCAL",
        "name": "甲状腺超声 · 探头相对分区",
        "level": "local",
        "modality": ["US"],
        "body_part": "甲状腺",
        "method": "人工标注",
        "laterality_rule": "us_local: no_laterality_inference",
        "note": "超声仅有局部视野，无全身解剖参考，不给出左叶/右叶判断，只给图像内相对位置。",
        "annotator": "human",
        "annotated_at": "2026-11-15",
        "images": ["CASE-011"],
    },
]

# 通用征象集（按部位）
CHEST_UPPER = ["SIGN-003", "SIGN-005", "SIGN-004"]
CHEST_MID = ["SIGN-002", "SIGN-014", "SIGN-019"]
CHEST_LOWER = ["SIGN-007", "SIGN-019", "SIGN-020"]
CHEST_LOWER_L = ["SIGN-007", "SIGN-008", "SIGN-019"]
MEDIASTINUM = ["SIGN-009", "SIGN-028"]
SUBDIAPH = ["SIGN-026"]

REGIONS = [
    # ---------- CASE-001 正常 PA 胸片 ----------
    dict(id="REG-001-RUL", image_id="CASE-001", atlas_id="ATLAS-CHEST-PA-6",
         name="右肺上野", name_en="right upper lung zone", coords=[0.115, 0.09, 0.360, 0.26],
         image_side="left", patient_side="right", sign_ids=CHEST_UPPER,
         note="肺尖至第 2 前肋下缘水平。"),
    dict(id="REG-001-RML", image_id="CASE-001", atlas_id="ATLAS-CHEST-PA-6",
         name="右肺中野", name_en="right middle lung zone", coords=[0.115, 0.35, 0.360, 0.23],
         image_side="left", patient_side="right", sign_ids=CHEST_MID,
         note="第 2 至第 4 前肋下缘之间。"),
    dict(id="REG-001-RLL", image_id="CASE-001", atlas_id="ATLAS-CHEST-PA-6",
         name="右肺下野", name_en="right lower lung zone", coords=[0.115, 0.58, 0.360, 0.24],
         image_side="left", patient_side="right", sign_ids=CHEST_LOWER,
         note="第 4 前肋下缘至膈面。"),
    dict(id="REG-001-LUL", image_id="CASE-001", atlas_id="ATLAS-CHEST-PA-6",
         name="左肺上野", name_en="left upper lung zone", coords=[0.535, 0.09, 0.360, 0.26],
         image_side="right", patient_side="left", sign_ids=CHEST_UPPER,
         note="肺尖至第 2 前肋下缘水平。"),
    dict(id="REG-001-LML", image_id="CASE-001", atlas_id="ATLAS-CHEST-PA-6",
         name="左肺中野", name_en="left middle lung zone", coords=[0.535, 0.35, 0.360, 0.23],
         image_side="right", patient_side="left", sign_ids=["SIGN-002", "SIGN-014", "SIGN-010"],
         note="第 2 至第 4 前肋下缘之间，含心影左缘。"),
    dict(id="REG-001-LLL", image_id="CASE-001", atlas_id="ATLAS-CHEST-PA-6",
         name="左肺下野", name_en="left lower lung zone", coords=[0.535, 0.58, 0.360, 0.24],
         image_side="right", patient_side="left", sign_ids=CHEST_LOWER_L,
         note="第 4 前肋下缘至膈面，含左侧肋膈角。"),
    dict(id="REG-001-MED", image_id="CASE-001", atlas_id="ATLAS-CHEST-PA-6",
         name="纵隔", name_en="mediastinum", coords=[0.475, 0.09, 0.060, 0.71],
         image_side="midline", patient_side="midline", sign_ids=MEDIASTINUM,
         note="脊柱旁开至心影右缘，含气管与肺门区。"),
    dict(id="REG-001-SUB", image_id="CASE-001", atlas_id="ATLAS-CHEST-PA-6",
         name="膈下", name_en="subdiaphragmatic", coords=[0.200, 0.82, 0.600, 0.16],
         image_side="midline", patient_side="midline", sign_ids=SUBDIAPH,
         note="膈面以下，含胃泡与肝影上部。"),

    # ---------- CASE-006 大叶性肺炎 ----------
    dict(id="REG-006-RUL", image_id="CASE-006", atlas_id="ATLAS-CHEST-PA-6",
         name="右肺上野", name_en="right upper lung zone", coords=[0.090, 0.07, 0.390, 0.25],
         image_side="left", patient_side="right", sign_ids=CHEST_UPPER,
         note="肺尖至第 2 前肋下缘水平。"),
    dict(id="REG-006-RML", image_id="CASE-006", atlas_id="ATLAS-CHEST-PA-6",
         name="右肺中野", name_en="right middle lung zone", coords=[0.090, 0.32, 0.390, 0.24],
         image_side="left", patient_side="right", sign_ids=CHEST_MID,
         note="第 2 至第 4 前肋下缘之间；本例箭头所指实变位于此区。"),
    dict(id="REG-006-RLL", image_id="CASE-006", atlas_id="ATLAS-CHEST-PA-6",
         name="右肺下野", name_en="right lower lung zone", coords=[0.090, 0.56, 0.390, 0.24],
         image_side="left", patient_side="right", sign_ids=["SIGN-002", "SIGN-007", "SIGN-019"],
         note="第 4 前肋下缘至膈面。"),
    dict(id="REG-006-LUL", image_id="CASE-006", atlas_id="ATLAS-CHEST-PA-6",
         name="左肺上野", name_en="left upper lung zone", coords=[0.560, 0.07, 0.370, 0.25],
         image_side="right", patient_side="left", sign_ids=["SIGN-003", "SIGN-004"],
         note="肺尖至第 2 前肋下缘水平。"),
    dict(id="REG-006-LML", image_id="CASE-006", atlas_id="ATLAS-CHEST-PA-6",
         name="左肺中野", name_en="left middle lung zone", coords=[0.560, 0.32, 0.370, 0.24],
         image_side="right", patient_side="left", sign_ids=["SIGN-002", "SIGN-014"],
         note="第 2 至第 4 前肋下缘之间。"),
    dict(id="REG-006-LLL", image_id="CASE-006", atlas_id="ATLAS-CHEST-PA-6",
         name="左肺下野", name_en="left lower lung zone", coords=[0.560, 0.56, 0.370, 0.24],
         image_side="right", patient_side="left", sign_ids=["SIGN-007", "SIGN-008"],
         note="第 4 前肋下缘至膈面。"),
    dict(id="REG-006-MED", image_id="CASE-006", atlas_id="ATLAS-CHEST-PA-6",
         name="纵隔", name_en="mediastinum", coords=[0.480, 0.07, 0.080, 0.73],
         image_side="midline", patient_side="midline", sign_ids=MEDIASTINUM,
         note="脊柱旁开至心影右缘。"),
    dict(id="REG-006-SUB", image_id="CASE-006", atlas_id="ATLAS-CHEST-PA-6",
         name="膈下", name_en="subdiaphragmatic", coords=[0.150, 0.80, 0.700, 0.18],
         image_side="midline", patient_side="midline", sign_ids=SUBDIAPH,
         note="膈面以下。"),

    # ---------- CASE-011 甲状腺超声（local 级） ----------
    dict(id="REG-011-CENTER", image_id="CASE-011", atlas_id="ATLAS-THY-US-LOCAL",
         name="图像中央低回声区", name_en="central hypoechoic zone", coords=[0.300, 0.280, 0.440, 0.380],
         image_side="unknown", patient_side="unknown",
         sign_ids=["SIGN-058", "SIGN-057", "SIGN-060"],
         note="图像内相对位置，不代表解剖左叶或右叶。"),
    dict(id="REG-011-UP", image_id="CASE-011", atlas_id="ATLAS-THY-US-LOCAL",
         name="上方腺体", name_en="superior glandular band", coords=[0.060, 0.140, 0.860, 0.140],
         image_side="unknown", patient_side="unknown", sign_ids=["SIGN-058"],
         note="图像内相对位置。"),
    dict(id="REG-011-DOWN", image_id="CASE-011", atlas_id="ATLAS-THY-US-LOCAL",
         name="下方腺体", name_en="inferior glandular band", coords=[0.060, 0.660, 0.860, 0.200],
         image_side="unknown", patient_side="unknown", sign_ids=["SIGN-060", "SIGN-059"],
         note="图像内相对位置，含后方声影带。"),
    dict(id="REG-011-LEFT", image_id="CASE-011", atlas_id="ATLAS-THY-US-LOCAL",
         name="左侧腺体", name_en="left image-side band", coords=[0.060, 0.280, 0.240, 0.380],
         image_side="unknown", patient_side="unknown", sign_ids=["SIGN-060"],
         note="图像内相对位置，不推断患者侧别。"),
    dict(id="REG-011-RIGHT", image_id="CASE-011", atlas_id="ATLAS-THY-US-LOCAL",
         name="右侧腺体", name_en="right image-side band", coords=[0.740, 0.280, 0.180, 0.380],
         image_side="unknown", patient_side="unknown", sign_ids=["SIGN-058"],
         note="图像内相对位置，不推断患者侧别。"),
]

LUNGRADS_URL = "https://www.acr.org/Clinical-Resources/Reporting-and-Data-Systems/Lung-Rads"
TIRADS_URL = "https://www.acr.org/Clinical-Resources/Reporting-and-Data-Systems/TI-RADS"

# doc 锚点：(doc_kind, doc_id, 标题, 版本, 定位符, 摘录, url)
DOC_LUNGRADS_01 = ("guideline", "GL-LUNGRADS-01", "ACR Lung-RADS", "2022",
                   "类别 1 · 筛查随访",
                   "未见肺结节或仅见良性表现者，按年度低剂量 CT 继续筛查。", LUNGRADS_URL)
DOC_LUNGRADS_06 = ("guideline", "GL-LUNGRADS-06", "ACR Lung-RADS", "2022",
                   "通用 · 比较原则",
                   "判读时应与既往检查比较，结节大小变化与类别调整需记录依据。", LUNGRADS_URL)
DOC_TIRADS_03 = ("guideline", "GL-TIRADS-03", "ACR TI-RADS", "2017",
                 "TR4 · 穿刺与随访",
                 "TR4 类结节最大径达到约 1.5 cm 时可考虑穿刺；1.0—1.5 cm 以随访为主。", TIRADS_URL)
DOC_TIRADS_06 = ("guideline", "GL-TIRADS-06", "ACR TI-RADS", "2017",
                 "通用 · 描述要素",
                 "报告应记录成分、回声、形态、边缘与强回声灶五个维度，再给出分类。", TIRADS_URL)
DOC_SIGN_002 = ("sign", "SIGN-002", "征象词条 · 实变", "v2026-11-15",
                "SIGN-002 / 影像表现",
                "肺泡内气体被渗出物、细胞或组织替代，表现为密度增高的片状影，可伴空气支气管征。",
                "https://radiopaedia.org/articles/consolidation")
DOC_SIGN_058 = ("sign", "SIGN-058", "征象词条 · 低回声结节", "v2026-11-15",
                "SIGN-058 / 影像表现",
                "结节回声低于周围正常甲状腺实质，可为实性低回声灶；需结合形态、边缘与强回声灶综合描述。",
                "https://radiopaedia.org/articles/thyroid-nodule")
DOC_GROUP_CONSOL = ("group", "GRP-LUNG-CONSOLIDATION", "影像组 · 肺部实变与气腔影", "2026-11-15",
                    "GRP-LUNG-CONSOLIDATION / criteria",
                    "归类依据：来源公开描述含 pneumonia / consolidation / air-space opacity / atelectasis 等关键词，或图中自带标注。",
                    "https://commons.wikimedia.org/wiki/Category:Pneumonia_on_X-rays")

CLAIMS = [
    {
        "id": "CLM-001", "image_id": "CASE-001", "region_id": "REG-001-RML",
        "text": "右肺中野透亮度均匀，未见明确局灶性密度增高、结节或空洞影。",
        "sign_ids": ["SIGN-002", "SIGN-003"], "guideline_ids": ["GL-LUNGRADS-01"],
        "disclaimer": "仅作表现对照，不构成诊断意见。",
        "spatial_bbox": [0.135, 0.365, 0.320, 0.200],
        "docs": [DOC_LUNGRADS_01],
        "note": "正常对照：该分区无阳性表现，文献侧给出类别 1 的随访口径。",
    },
    {
        "id": "CLM-002", "image_id": "CASE-006", "region_id": "REG-006-RML",
        "text": "右肺中野见片状密度增高影，边界不清，其内可见支气管充气征。",
        "sign_ids": ["SIGN-002", "SIGN-014"], "guideline_ids": [],
        "disclaimer": "仅作表现对照，不构成诊断意见。",
        "spatial_bbox": [0.130, 0.440, 0.310, 0.300],
        "docs": [DOC_SIGN_002],
        "note": "文献锚点为征象词条定义（非指南条款）：库内无「实变」为适用条件的条款，故不套用 Lung-RADS。",
    },
    {
        "id": "CLM-003", "image_id": "CASE-006", "region_id": "REG-006-RML",
        "text": "该分区表现归入「肺部实变与气腔影」对照组，可与同组公开影像并排对照。",
        "sign_ids": ["SIGN-002", "SIGN-014", "SIGN-019"],
        "guideline_ids": [],
        "disclaimer": "仅作表现对照，不构成诊断意见。",
        "spatial_bbox": [0.130, 0.440, 0.310, 0.300],
        "docs": [DOC_GROUP_CONSOL],
        "note": "组内病因不同，仅按影像表现归类，不代表同一疾病。",
    },
    {
        "id": "CLM-004", "image_id": "CASE-006", "region_id": "REG-006-RML",
        "text": "若需按 Lung-RADS 归类，还需结节最大径、实性成分比例与既往片比较。",
        "sign_ids": [], "guideline_ids": ["GL-LUNGRADS-06"],
        "disclaimer": "仅作条件提示，不构成诊断意见。",
        "spatial_bbox": None,
        "docs": [DOC_LUNGRADS_06],
        "note": "单引用降级：文献侧有依据，但无法指到图上某一块，因此不显示为双引用。",
        "gate_reason": "缺少空间锚点：该条为条件提示，未绑定具体分区。",
    },
    {
        "id": "CLM-005", "image_id": "CASE-011", "region_id": "REG-011-CENTER",
        "text": "图像中央可见边界较清的低回声结节，内部回声不均，后方伴声影。",
        "sign_ids": ["SIGN-058", "SIGN-060"], "guideline_ids": [],
        "disclaimer": "仅作表现对照，不构成诊断意见。",
        "spatial_bbox": [0.310, 0.290, 0.420, 0.360],
        "docs": [DOC_SIGN_058],
        "note": "该模态为 local 级定位：只说明「图像中央」，不推断左叶或右叶。",
    },
    {
        "id": "CLM-006", "image_id": "CASE-011", "region_id": "REG-011-CENTER",
        "text": "按 TI-RADS 描述要素，报告需记录成分、回声、形态、边缘与强回声灶五个维度后再分类。",
        "sign_ids": ["SIGN-058", "SIGN-057"], "guideline_ids": ["GL-TIRADS-06"],
        "disclaimer": "仅作要素提示，不构成诊断意见。",
        "spatial_bbox": [0.310, 0.290, 0.420, 0.360],
        "docs": [DOC_TIRADS_06],
        "note": "条款只给「要记录哪些维度」，不给分类结论；分类需完整五维输入。",
    },
    {
        "id": "CLM-007", "image_id": "CASE-011", "region_id": "REG-011-CENTER",
        "text": "TI-RADS 4 类结节最大径达 1.0 cm 时可考虑穿刺。",
        "sign_ids": ["SIGN-058"], "guideline_ids": ["GL-TIRADS-03"],
        "disclaimer": "该条引用未通过校验，不进入回答。",
        "spatial_bbox": [0.310, 0.290, 0.420, 0.360],
        # 故意篡改：excerpt 写 1.0 cm，但 hash 记录的是原文 1.5 cm 版本
        "docs": [DOC_TIRADS_03],
        "excerpt_override": "TR4 类结节最大径达到约 1.0 cm 时可考虑穿刺；1.0—1.5 cm 以随访为主。",
        "note": "失败案例：模型把阈值从 1.5 cm 改写成 1.0 cm，校验不通过，整条不进入回答。",
    },
]


def sha8(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf8")).hexdigest()[:8]


def build_claim(c: dict, idx: int) -> dict:
    cites = []
    if c.get("spatial_bbox"):
        cites.append({
            "cite_id": f"CIT-{idx:04d}-S",
            "kind": "spatial",
            "anchor": {
                "image_id": c["image_id"],
                "region_id": c["region_id"],
                "bbox": c["spatial_bbox"],
                "atlas_id": next(r["atlas_id"] for r in REGIONS if r["id"] == c["region_id"]),
                "annotator": "human",
                "annotated_at": "2026-11-15",
            },
        })
    for j, d in enumerate(c["docs"]):
        kind, doc_id, title, ver, locator, excerpt, url = d
        cites.append({
            "cite_id": f"CIT-{idx:04d}-D{j}",
            "kind": "doc",
            "anchor": {
                "doc_kind": kind,
                "doc_id": doc_id,
                "doc_title": title,
                "version": ver,
                "locator": locator,
                "excerpt": c.get("excerpt_override") or excerpt,
                # hash 始终按库内原文计算：excerpt 被改写时必然不匹配
                "excerpt_sha256": sha8(excerpt),
                "url": url,
                "retrieved_at": "2026-11-15",
            },
        })
    out = {
        "id": c["id"],
        "image_id": c["image_id"],
        "region_id": c["region_id"],
        "text": c["text"],
        "sign_ids": c["sign_ids"],
        "guideline_ids": c["guideline_ids"],
        "disclaimer": c["disclaimer"],
        "cites": cites,
        "note": c["note"],
    }
    if c.get("gate_reason"):
        out["gate_reason"] = c["gate_reason"]
    return out


def dump(name: str, rows: list) -> None:
    p = DATA / name
    with p.open("w", encoding="utf8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{p.relative_to(KB.parent)}  {len(rows)} 条")


def main() -> None:
    for r in REGIONS:
        r.setdefault("level", 2)
        r.setdefault("parent_region_id", {"胸部": "REG-CHEST", "甲状腺": "REG-THYROID"}[
            next(a["body_part"] for a in ATLASES if a["id"] == r["atlas_id"])])
        r.setdefault("shape", "rect")
        r.setdefault("atlas_level", next(a["level"] for a in ATLASES if a["id"] == r["atlas_id"]))
        r.setdefault("laterality_rule", next(a["laterality_rule"] for a in ATLASES if a["id"] == r["atlas_id"]))
        r.setdefault("annotator", "human")
        r.setdefault("annotated_at", "2026-11-15")
        r.setdefault("group_ids", ["GRP-LUNG-CONSOLIDATION"] if r["id"] in ("REG-006-RML", "REG-006-RLL") else [])
        r.setdefault("status", "active")

    claims = [build_claim(c, i + 1) for i, c in enumerate(CLAIMS)]

    dump("atlases.jsonl", ATLASES)
    dump("regions.jsonl", REGIONS)
    dump("claims.jsonl", claims)


if __name__ == "__main__":
    main()
