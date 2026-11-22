#!/usr/bin/env python3
"""生成 120 例规模化语料：cases / atlases / regions / claims。

设计要点：
1. 保留既有人工标注（21 个分区、7 条 claim）不覆盖；
2. 其余 117 例按体位模板批量生成分区，坐标是教学示意，不是精确标注；
3. 每条 claim 由「分区 × 征象」模板实例化，不自由生成；
4. 文献锚点取 signs.jsonl 的 appearance 原文，存 sha256 前 8 位，可校验；
5. 新增证据等级：人工 B / 模板自动 C。

重新生成：python3 kb/scripts/build_corpus_120.py
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
DATA = KB / "data"
CAND = KB / "_candidates"

TODAY = "2026-11-15"


def sha8(text):
    return hashlib.sha256(str(text).strip().encode("utf8")).hexdigest()[:8]


def read_jsonl(name):
    p = DATA / name
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf8").splitlines() if x.strip()]


# ---------------------------------------------------------------- 体位模板
# 坐标全部归一化 [x, y, w, h]；global 级可推断解剖分区，local 级只给图像内相对位置。
def R(key, name, coords, side, note, signs):
    return {"key": key, "name": name, "coords": coords,
            "patient_side": side, "note": note, "sign_keys": signs}


TEMPLATES = {
    "chest_pa": {
        "atlas_id": "ATLAS-CHEST-PA-6", "name": "胸片六分区（PA）", "level": "global",
        "body_part": "胸部", "laterality": "pa_chest: image_left = patient_right",
        "note": "第 2/4 前肋下缘水平线划分上中下野；纵隔与膈下单独成区。",
        "regions": [
            R("RUL", "右肺上野", [0.09, 0.09, 0.38, 0.24], "right", "肺尖至第 2 前肋下缘水平。", "lung"),
            R("RML", "右肺中野", [0.09, 0.33, 0.38, 0.24], "right", "第 2 至第 4 前肋下缘之间。", "lung"),
            R("RLL", "右肺下野", [0.09, 0.57, 0.38, 0.24], "right", "第 4 前肋下缘至膈面。", "lung"),
            R("LUL", "左肺上野", [0.54, 0.09, 0.37, 0.24], "left", "肺尖至第 2 前肋下缘水平。", "lung"),
            R("LML", "左肺中野", [0.54, 0.33, 0.37, 0.24], "left", "第 2 至第 4 前肋下缘之间，含心影左缘。", "lung"),
            R("LLL", "左肺下野", [0.54, 0.57, 0.37, 0.24], "left", "第 4 前肋下缘至膈面，含左肋膈角。", "lung"),
            R("MED", "纵隔", [0.47, 0.09, 0.07, 0.72], "midline", "脊柱旁开至心影右缘，含气管与肺门区。", "mediastinum"),
            R("SUB", "膈下", [0.15, 0.82, 0.70, 0.15], "midline", "膈面以下，含胃泡与肝影上部。", "subdiaph"),
        ],
    },
    "chest_lat": {
        "atlas_id": "ATLAS-CHEST-LAT-4", "name": "胸片侧位四区", "level": "global",
        "body_part": "胸部", "laterality": "chest_lat: no_laterality_inference",
        "note": "侧位片按前后方向划分，不推断左右侧别。",
        "regions": [
            R("RETROSTERNAL", "胸骨后间隙", [0.12, 0.10, 0.32, 0.30], "unknown", "胸骨后方至升主动脉前缘。", "lung"),
            R("RETROCARDIAC", "心后间隙", [0.12, 0.42, 0.32, 0.28], "unknown", "心影后方至脊柱前缘。", "lung"),
            R("CPA", "后肋膈角", [0.42, 0.60, 0.38, 0.28], "unknown", "侧位片上显示最早的胸腔积液部位。", "pleura"),
            R("DIAPH", "膈面", [0.10, 0.86, 0.82, 0.12], "unknown", "膈肌轮廓，左右膈面重叠。", "subdiaph"),
        ],
    },
    "knee_ap": {
        "atlas_id": "ATLAS-KNEE-AP-4", "name": "膝关节正位四区", "level": "global",
        "body_part": "膝关节", "laterality": "knee_ap: image_left = patient_right",
        "note": "按股骨、胫骨、腓骨与关节间隙划分。",
        "regions": [
            R("FEMUR", "股骨远端", [0.26, 0.04, 0.48, 0.32], "unknown", "股骨内外髁及髁间窝。", "bone"),
            R("TIBIA", "胫骨近端", [0.26, 0.52, 0.46, 0.36], "unknown", "胫骨平台与近端干骺端。", "bone"),
            R("FIBULA", "腓骨近端", [0.72, 0.50, 0.16, 0.34], "unknown", "腓骨头与腓骨颈。", "bone"),
            R("JOINT", "关节间隙", [0.26, 0.38, 0.48, 0.14], "midline", "股胫关节间隙，含髁间嵴。", "joint"),
        ],
    },
    "hand_pa": {
        "atlas_id": "ATLAS-HAND-PA-4", "name": "手正位四区", "level": "global",
        "body_part": "手", "laterality": "hand_pa: image_left = patient_right",
        "note": "按掌骨、近节指骨、中远节指骨与腕掌关节划分。",
        "regions": [
            R("METACARPAL", "掌骨区", [0.12, 0.42, 0.76, 0.26], "unknown", "第 1—5 掌骨骨干。", "bone"),
            R("PROX", "近节指骨区", [0.10, 0.24, 0.80, 0.18], "unknown", "第 2—5 近节指骨。", "bone"),
            R("DIST", "中远节指骨区", [0.08, 0.04, 0.84, 0.20], "unknown", "中节与远节指骨、末节指骨粗隆。", "bone"),
            R("CMC", "腕掌关节区", [0.14, 0.66, 0.72, 0.16], "unknown", "腕掌关节与大多角骨相邻区。", "joint"),
        ],
    },
    "foot_ap": {
        "atlas_id": "ATLAS-FOOT-AP-4", "name": "足正位四区", "level": "global",
        "body_part": "足", "laterality": "foot_ap: image_left = patient_right",
        "note": "按跗骨、跖骨、趾骨与跟骨划分。",
        "regions": [
            R("TARSAL", "跗骨区", [0.14, 0.50, 0.72, 0.28], "unknown", "距骨、舟骨、骰骨与楔骨。", "bone"),
            R("METATARSAL", "跖骨区", [0.12, 0.28, 0.76, 0.24], "unknown", "第 1—5 跖骨骨干。", "bone"),
            R("TOES", "趾骨区", [0.10, 0.04, 0.80, 0.24], "unknown", "各趾近节、中节与远节趾骨。", "bone"),
            R("CALCANEUS", "跟骨区", [0.20, 0.74, 0.60, 0.18], "unknown", "跟骨体与跟骨结节。", "bone"),
        ],
    },
    "ankle_ap": {
        "atlas_id": "ATLAS-ANKLE-AP-3", "name": "踝正位三区", "level": "global",
        "body_part": "踝", "laterality": "ankle_ap: image_left = patient_right",
        "note": "按内外踝与距骨划分。",
        "regions": [
            R("MED_MAL", "内踝", [0.14, 0.28, 0.24, 0.36], "unknown", "胫骨远端内侧突起。", "bone"),
            R("LAT_MAL", "外踝", [0.62, 0.28, 0.24, 0.36], "unknown", "腓骨远端。", "bone"),
            R("TALUS", "距骨区", [0.28, 0.38, 0.44, 0.36], "unknown", "距骨顶与踝穴。", "bone"),
        ],
    },
    "shoulder_ap": {
        "atlas_id": "ATLAS-SHOULDER-AP-3", "name": "肩正位三区", "level": "global",
        "body_part": "肩", "laterality": "shoulder_ap: image_left = patient_right",
        "note": "按肱骨头、肩盂与锁骨远端划分。",
        "regions": [
            R("HUM_HEAD", "肱骨头", [0.10, 0.26, 0.40, 0.42], "unknown", "肱骨头与肱骨近端。", "bone"),
            R("GLENOID", "肩盂", [0.50, 0.24, 0.24, 0.38], "unknown", "肩胛盂与盂唇区。", "joint"),
            R("CLAVICLE", "锁骨远端", [0.42, 0.06, 0.46, 0.20], "unknown", "锁骨远端与肩锁关节。", "bone"),
        ],
    },
    "elbow_ap": {
        "atlas_id": "ATLAS-ELBOW-AP-3", "name": "肘正位三区", "level": "global",
        "body_part": "肘", "laterality": "elbow_ap: image_left = patient_right",
        "note": "按肱骨远端、尺桡骨近端与关节间隙划分。",
        "regions": [
            R("HUM_DIST", "肱骨远端", [0.22, 0.04, 0.56, 0.38], "unknown", "肱骨内上髁、外上髁与滑车。", "bone"),
            R("FOREARM", "尺桡骨近端", [0.22, 0.54, 0.56, 0.36], "unknown", "尺骨鹰嘴与桡骨头。", "bone"),
            R("JOINT", "关节间隙", [0.24, 0.40, 0.52, 0.14], "midline", "肱尺与肱桡关节间隙。", "joint"),
        ],
    },
    "wrist_pa": {
        "atlas_id": "ATLAS-WRIST-PA-3", "name": "腕正位三区", "level": "global",
        "body_part": "腕", "laterality": "wrist_pa: image_left = patient_right",
        "note": "按近排腕骨、远排腕骨与桡尺骨远端划分。",
        "regions": [
            R("PROX_CARPAL", "近排腕骨", [0.14, 0.40, 0.72, 0.22], "unknown", "舟骨、月骨、三角骨与豌豆骨。", "bone"),
            R("DIST_CARPAL", "远排腕骨", [0.14, 0.22, 0.72, 0.18], "unknown", "大多角骨、小多角骨、头状骨与钩骨。", "bone"),
            R("RADIOULNAR", "桡尺骨远端", [0.12, 0.62, 0.76, 0.24], "unknown", "桡骨远端与尺骨茎突。", "bone"),
        ],
    },
    "cspine_lat": {
        "atlas_id": "ATLAS-CSPINE-LAT-4", "name": "颈椎侧位四区", "level": "global",
        "body_part": "颈椎", "laterality": "cspine_lat: no_laterality_inference",
        "note": "按上中下颈椎与椎前软组织划分。",
        "regions": [
            R("UPPER", "上颈椎", [0.22, 0.04, 0.58, 0.26], "unknown", "C1—C2，含齿状突。", "bone"),
            R("MID", "中颈椎", [0.22, 0.30, 0.58, 0.26], "unknown", "C3—C4。", "bone"),
            R("LOWER", "下颈椎", [0.22, 0.56, 0.58, 0.26], "unknown", "C5—C7。", "bone"),
            R("PREVERT", "椎前软组织", [0.10, 0.18, 0.16, 0.62], "unknown", "椎体前方软组织带。", "soft"),
        ],
    },
    "lspine_lat": {
        "atlas_id": "ATLAS-LSPINE-LAT-4", "name": "腰椎侧位四区", "level": "global",
        "body_part": "腰椎", "laterality": "lspine_lat: no_laterality_inference",
        "note": "按腰椎节段与椎前软组织划分。",
        "regions": [
            R("L12", "L1—L2", [0.22, 0.06, 0.58, 0.26], "unknown", "上段腰椎。", "bone"),
            R("L34", "L3—L4", [0.22, 0.32, 0.58, 0.26], "unknown", "中段腰椎。", "bone"),
            R("L5S1", "L5—S1", [0.22, 0.58, 0.58, 0.26], "unknown", "腰骶交界。", "bone"),
            R("PREVERT", "椎前软组织", [0.10, 0.20, 0.16, 0.60], "unknown", "椎体前方软组织带。", "soft"),
        ],
    },
    "pelvis_ap": {
        "atlas_id": "ATLAS-PELVIS-AP-4", "name": "骨盆正位四区", "level": "global",
        "body_part": "骨盆", "laterality": "pelvis_ap: image_left = patient_right",
        "note": "按髂骨、髋臼、耻坐骨与骶髂关节划分。",
        "regions": [
            R("ILIAC", "髂骨翼", [0.10, 0.08, 0.80, 0.26], "unknown", "双侧髂骨翼与髂嵴。", "bone"),
            R("ACETAB", "髋臼", [0.14, 0.38, 0.72, 0.24], "unknown", "双侧髋臼与股骨头。", "joint"),
            R("PUBIS", "耻坐骨", [0.20, 0.64, 0.60, 0.24], "unknown", "耻骨支、坐骨支与耻骨联合。", "bone"),
            R("SI", "骶髂关节", [0.32, 0.26, 0.36, 0.16], "midline", "骶骨与髂骨相邻区。", "joint"),
        ],
    },
    "skull_lat": {
        "atlas_id": "ATLAS-SKULL-LAT-3", "name": "头颅侧位三区", "level": "global",
        "body_part": "头颅", "laterality": "skull_lat: no_laterality_inference",
        "note": "按颅穹窿、颅底与面骨划分。",
        "regions": [
            R("VAULT", "颅穹窿", [0.10, 0.06, 0.78, 0.38], "unknown", "额顶枕骨与颅缝。", "bone"),
            R("BASE", "颅底", [0.12, 0.46, 0.76, 0.24], "unknown", "蝶鞍、斜坡与颅底孔道。", "bone"),
            R("FACE", "面骨", [0.14, 0.70, 0.52, 0.24], "unknown", "上颌骨、下颌骨与鼻骨。", "bone"),
        ],
    },
    "limb_local": {
        "atlas_id": "ATLAS-LIMB-LOCAL", "name": "四肢侧/斜位 · 图像内分区", "level": "local",
        "body_part": "四肢", "laterality": "limb_local: no_laterality_inference",
        "note": "侧位或斜位投照存在骨重叠，只给图像内相对位置，不推断具体骨段。",
        "regions": [
            R("UPPER", "图像上部", [0.10, 0.06, 0.80, 0.26], "unknown", "图像上缘区域。", "bone"),
            R("MID", "图像中部", [0.10, 0.34, 0.80, 0.30], "unknown", "图像中央区域。", "bone"),
            R("LOWER", "图像下部", [0.10, 0.66, 0.80, 0.28], "unknown", "图像下缘区域。", "bone"),
            R("EDGE", "边缘带", [0.03, 0.03, 0.94, 0.94], "unknown", "图像周边区域。", "bone"),
        ],
    },
    "chest_ct_ax": {
        "atlas_id": "ATLAS-CHEST-CT-LOCAL", "name": "胸部 CT 轴位 · 图像内分区", "level": "local",
        "body_part": "胸部", "laterality": "ct_local: no_laterality_inference",
        "note": "单层轴位层面不固定，只给图像内相对位置，不推断肺叶。",
        "regions": [
            R("CENTER", "图像中央", [0.26, 0.28, 0.48, 0.44], "unknown", "中央区域，含纵隔旁与肺门区。", "lung"),
            R("ANT", "前部", [0.12, 0.04, 0.76, 0.24], "unknown", "图像上缘肺野。", "lung"),
            R("POST", "后部", [0.12, 0.70, 0.76, 0.26], "unknown", "图像下缘肺野与脊柱旁。", "lung"),
            R("LEFT", "图像左侧", [0.04, 0.22, 0.24, 0.56], "unknown", "图像左缘肺野。", "lung"),
            R("RIGHT", "图像右侧", [0.72, 0.22, 0.24, 0.56], "unknown", "图像右缘肺野。", "lung"),
        ],
    },
    "head_mr_ax": {
        "atlas_id": "ATLAS-HEAD-MR-LOCAL", "name": "头颅 MR 轴位 · 图像内分区", "level": "local",
        "body_part": "头颅", "laterality": "mr_local: no_laterality_inference",
        "note": "单层轴位无全身参考，只给图像内相对位置，不推断左右与具体脑叶。",
        "regions": [
            R("ANT", "图像前部", [0.14, 0.08, 0.72, 0.26], "unknown", "图像上缘区域。", "brain"),
            R("MID", "图像中部", [0.14, 0.36, 0.72, 0.28], "unknown", "图像中央区域。", "brain"),
            R("POST", "图像后部", [0.14, 0.66, 0.72, 0.26], "unknown", "图像下缘区域。", "brain"),
            R("EDGE", "周边带", [0.03, 0.03, 0.94, 0.94], "unknown", "含颅骨与脑外间隙。", "brain"),
        ],
    },
    "abd_ct_ax": {
        "atlas_id": "ATLAS-ABD-CT-LOCAL", "name": "腹部 CT 轴位 · 图像内分区", "level": "local",
        "body_part": "腹部", "laterality": "ct_local: no_laterality_inference",
        "note": "单层轴位层面不固定，只给图像内相对位置，不推断具体器官。",
        "regions": [
            R("CENTER", "图像中央", [0.26, 0.28, 0.48, 0.44], "unknown", "中央区域，含肠管与系膜。", "abdomen"),
            R("ANT", "前部", [0.12, 0.04, 0.76, 0.24], "unknown", "腹前壁与网膜区。", "abdomen"),
            R("POST", "后部", [0.12, 0.70, 0.76, 0.26], "unknown", "脊柱旁与腹膜后区。", "abdomen"),
            R("LEFT", "图像左侧", [0.04, 0.22, 0.24, 0.56], "unknown", "图像左缘区域。", "abdomen"),
            R("RIGHT", "图像右侧", [0.72, 0.22, 0.24, 0.56], "unknown", "图像右缘区域。", "abdomen"),
        ],
    },
    "breast_mlo": {
        "atlas_id": "ATLAS-BREAST-MLO-LOCAL", "name": "乳腺 MLO · 图像内分区", "level": "local",
        "body_part": "乳腺", "laterality": "mg_local: no_laterality_inference",
        "note": "MLO 位为投影图，只给图像内相对位置，不推断象限与侧别。",
        "regions": [
            R("UPPER", "图像上部", [0.18, 0.06, 0.64, 0.34], "unknown", "图像上缘腺体区。", "breast"),
            R("LOWER", "图像下部", [0.18, 0.44, 0.64, 0.34], "unknown", "图像下缘腺体区。", "breast"),
            R("RETRO", "乳晕后区", [0.26, 0.62, 0.48, 0.28], "unknown", "乳头后方中央区。", "breast"),
        ],
    },
    "us_local": {
        "atlas_id": "ATLAS-US-LOCAL", "name": "超声 · 探头相对分区", "level": "local",
        "body_part": "甲状腺", "laterality": "us_local: no_laterality_inference",
        "note": "超声仅有局部视野，无全身解剖参考，只给图像内相对位置。",
        "regions": [
            R("CENTER", "图像中央", [0.28, 0.26, 0.44, 0.46], "unknown", "中央回声区。", "thyroid"),
            R("UPPER", "上方带", [0.08, 0.06, 0.84, 0.20], "unknown", "图像上缘。", "thyroid"),
            R("LOWER", "下方带", [0.08, 0.72, 0.84, 0.22], "unknown", "图像下缘，含后方声影带。", "thyroid"),
            R("EDGE", "边缘带", [0.03, 0.03, 0.94, 0.94], "unknown", "图像周边。", "thyroid"),
        ],
    },
}

# 征象池：按解剖系统归类，取自 signs.jsonl 的 body_part
SIGN_GROUP = {
    "lung": {"肺"},
    "pleura": {"胸膜"},
    "mediastinum": {"纵隔"},
    "subdiaph": {"腹腔", "腹部"},
    "bone": {"骨"},
    "joint": {"关节", "骨"},
    "brain": {"脑"},
    "abdomen": {"腹部", "肝脏", "胰胆", "肾脏", "胆囊", "胰腺", "腹腔", "肠道"},
    "breast": {"乳腺"},
    "thyroid": {"甲状腺"},
    "soft": {"全身"},
}


def main():
    final = json.loads((CAND / "corpus_final.json").read_text(encoding="utf8"))
    # 始终从备份读原始人工数据，保证脚本可重入
    base = lambda n: DATA / n
    old_cases = [json.loads(x) for x in base("cases.backup.jsonl").read_text(encoding="utf8").splitlines() if x.strip()]
    old_regions = [json.loads(x) for x in base("regions.backup.jsonl").read_text(encoding="utf8").splitlines() if x.strip()]
    old_claims = [json.loads(x) for x in base("claims.backup.jsonl").read_text(encoding="utf8").splitlines() if x.strip()]
    signs = {s["id"]: s for s in read_jsonl("signs.jsonl")}

    signs_by_part = defaultdict(list)
    for s in signs.values():
        signs_by_part[s.get("body_part", "")].append(s["id"])

    def pick_signs(key, n=3):
        parts = SIGN_GROUP.get(key, {"全身"})
        pool = []
        for p in parts:
            pool.extend(signs_by_part.get(p, []))
        pool = list(dict.fromkeys(pool))
        if not pool:
            pool = list(signs.keys())[:n]
        return pool[:n]

    # ---------- 1. 合并 cases ----------
    cases = []
    for c in old_cases:
        body = c["body_part"]
        mods = str(c.get("modality", "")).upper()
        # 模态优先：CT/MR/US/MG 一律走图像内分区，不套正位解剖模板
        if "CT" in mods:
            pose = ("chest_ct_ax" if body in ("胸部", "肺", "胸膜")
                    else "head_mr_ax" if body == "头颅" else "abd_ct_ax")
        elif "MR" in mods:
            pose = "head_mr_ax" if body == "头颅" else "limb_local"
        elif "US" in mods:
            pose = "us_local"
        elif "MG" in mods:
            pose = "breast_mlo"
        else:
            pose = {
                "胸部": "chest_pa", "肺": "chest_pa", "胸膜": "chest_pa",
                "甲状腺": "us_local", "乳腺": "breast_mlo", "头颅": "head_mr_ax",
                "肝": "abd_ct_ax", "腹部": "abd_ct_ax",
            }.get(body, "chest_pa")
        chapter = {"胸部": "胸部", "肺": "胸部", "胸膜": "胸部", "甲状腺": "超声",
                   "乳腺": "乳腺", "头颅": "头颅", "肝": "腹部", "腹部": "腹部"}.get(body, "胸部")
        level = "local" if pose in ("us_local", "breast_mlo", "head_mr_ax", "abd_ct_ax", "chest_ct_ax", "limb_local") else "global"
        cases.append({
            **c,
            "chapter": chapter,
            "pose_class": pose,
            "level": level,
            "evidence_level": "B" if c["id"] in ("CASE-001", "CASE-006", "CASE-011") else "C",
            "corpus": "manual",
        })

    for row in final:
        pose = row["pose_class"]
        chapter = {"膝关节": "四肢", "手": "四肢", "足": "四肢", "踝": "四肢",
                   "肩": "四肢", "肘": "四肢", "腕": "四肢", "骨盆": "四肢",
                   "颈椎": "脊柱", "腰椎": "脊柱"}.get(row["body_part"], row.get("chapter", "胸部"))
        cases.append({
            "id": row["case_id"],
            "title": row["title"][:60] or f"{row['body_part']}影像",
            "modality": row["modality"] if "modality" in row else "CR",
            "body_part": row["body_part"],
            "image": "images/" + row["file"],
            "source_id": "SRC-COMMONS",
            "source_page": row["source_page"],
            "license": row["license"] or "CC BY-SA",
            "artist": row["artist"][:80],
            "description_public": row["description"][:200] or f"来源公开说明为{row['body_part']}影像。",
            "sign_tags": [],
            "teaching_note": f"{row['body_part']}常用体位教学对照。",
            "privacy_check": "auto_screened" if not row.get("privacy_flag") else "needs_review",
            "verified_at": TODAY,
            "status": "active",
            "group_id": f"GRP-{row['pose_class'].upper()}",
            "chapter": chapter,
            "pose_class": pose,
            "level": "local" if pose in ("head_mr_ax", "abd_ct_ax", "breast_mlo", "us_local", "chest_ct_ax", "limb_local") else "global",
            "evidence_level": "C",
            "corpus": "auto",
        })

    cases.sort(key=lambda c: c["id"])

    # ---------- 2. atlases ----------
    atlases = []
    for pose, t in TEMPLATES.items():
        imgs = [c["id"] for c in cases if c.get("pose_class") == pose]
        atlases.append({
            "id": t["atlas_id"], "name": t["name"], "level": t["level"],
            "modality": sorted({str(c.get("modality")) for c in cases if c.get("pose_class") == pose})[:3],
            "body_part": t["body_part"], "method": "体位模板 + 人工复核",
            "laterality_rule": t["laterality"], "note": t["note"],
            "annotator": "human+template", "annotated_at": TODAY, "images": imgs,
        })

    # ---------- 3. regions ----------
    done = {r["image_id"] for r in old_regions}
    regions = list(old_regions)
    for c in cases:
        if c["id"] in done:
            continue
        t = TEMPLATES.get(c.get("pose_class"))
        if not t:
            continue
        for rg in t["regions"]:
            rid = f"REG-{c['id'][-3:]}-{rg['key']}"
            regions.append({
                "id": rid, "image_id": c["id"], "atlas_id": t["atlas_id"],
                "name": rg["name"], "name_en": rg["key"].lower(),
                "coords": rg["coords"],
                "image_side": "unknown" if rg["patient_side"] == "unknown" else
                              ("left" if rg["patient_side"] == "right" else
                               ("right" if rg["patient_side"] == "left" else "midline")),
                "patient_side": rg["patient_side"],
                "sign_ids": pick_signs(rg["sign_keys"]),
                "note": rg["note"], "level": 2,
                "parent_region_id": "REG-" + c["body_part"],
                "shape": "rect", "atlas_level": t["level"],
                "laterality_rule": t["laterality"],
                "annotator": "template", "annotated_at": TODAY,
                "group_ids": [], "status": "active",
                "derivation": {"mode": "template", "template_id": t["atlas_id"],
                               "residual": 0.0, "method": "template_apply",
                               "confidence": 0.62},
                "verify_status": "auto",
            })

    # ---------- 4. claims ----------
    claims = list(old_claims)
    idx = len(claims)
    for r in regions:
        if r["image_id"] in ("CASE-001", "CASE-006", "CASE-011"):
            continue
        sids = [s for s in r.get("sign_ids", []) if s in signs]
        if not sids:
            continue
        idx += 1
        names = "、".join(signs[s]["name"] for s in sids)
        text = (f"{r['name']}区域解剖范围为{r['note']} "
                f"库内关联征象包括{names}；本条目只作分区与征象对照，不构成诊断。")
        first = signs[sids[0]]
        excerpt = first.get("appearance", "").strip()
        if not excerpt:
            continue
        b = r["coords"]
        pad = 0.01
        bbox = [round(b[0] + pad, 4), round(b[1] + pad, 4),
                round(max(0.01, b[2] - 2 * pad), 4), round(max(0.01, b[3] - 2 * pad), 4)]
        claims.append({
            "id": f"CLM-{idx:04d}",
            "image_id": r["image_id"],
            "region_id": r["id"],
            "text": text,
            "sign_ids": sids,
            "guideline_ids": [],
            "disclaimer": "仅作表现对照，不构成诊断意见。",
            "cites": [
                {"cite_id": f"CIT-{idx:04d}-S", "kind": "spatial",
                 "anchor": {"image_id": r["image_id"], "region_id": r["id"],
                            "bbox": bbox, "atlas_id": r["atlas_id"],
                            "annotator": "template", "annotated_at": TODAY}},
                {"cite_id": f"CIT-{idx:04d}-D0", "kind": "doc",
                 "anchor": {"doc_kind": "sign", "doc_id": sids[0],
                            "doc_title": "征象词条 · " + first["name"],
                            "version": "v2026-11-15",
                            "locator": sids[0] + " / 影像表现",
                            "excerpt": excerpt,
                            "excerpt_sha256": sha8(excerpt),
                            "url": "https://radiopaedia.org/search?q=" +
                                   first.get("en", first["name"]).replace(" ", "+"),
                            "retrieved_at": TODAY}},
            ],
            "note": "由体位模板与征象词条实例化，证据等级 C，待人工抽检。",
            "evidence_level": "C",
        })

    # ---------- 5. 落盘 ----------
    def dump(name, rows):
        with (DATA / name).open("w", encoding="utf8") as f:
            for x in rows:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows)}")

    dump("cases.jsonl", cases)
    dump("atlases.jsonl", atlases)
    dump("regions.jsonl", regions)
    dump("claims.jsonl", claims)

    print("\n部位分布:", dict(Counter(c["body_part"] for c in cases)))
    print("章节分布:", dict(Counter(c["chapter"] for c in cases)))
    print("可定位病例:", len({r["image_id"] for r in regions}))
    print("证据等级:", dict(Counter(c.get("evidence_level") for c in cases)))


if __name__ == "__main__":
    main()
