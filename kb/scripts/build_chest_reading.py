#!/usr/bin/env python3
"""生成胸片阅片数据集（kb/data/chest_reading.json）。

设计原则：
1. 只收录 CR 胸部；多图拼接影像不进入阅片队列。
2. 每个分区必须有独立文本与状态：abnormal / normal / unmentioned / limited。
3. 公开来源没有逐区描述时写 unmentioned，绝不把“未提及”渲染成“正常”。
4. 出处只到“病例来源页 / 原图标注 / 本库结构化校正 / 征象词条”，不硬挂不适用的指南。
5. 同时计算影像 SHA-256，供纯静态上传做精确匹配。

用法：
  python3 kb/scripts/build_chest_reading.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb" / "data"
OUT = DATA / "chest_reading.json"
BUILD_OUT = ROOT / "outputs" / "medtrain" / "data" / "chest" / "chest_reading.json"

PA_ZONES = [
    {"id": "RUL", "name": "右肺上野", "side": "right", "coords": [0.06, 0.08, 0.30, 0.25],
     "note": "肺尖至第 2 前肋下缘水平；图像左侧为患者右侧。"},
    {"id": "RML", "name": "右肺中野", "side": "right", "coords": [0.06, 0.33, 0.30, 0.24],
     "note": "第 2 至第 4 前肋下缘之间；图像左侧为患者右侧。"},
    {"id": "RLL", "name": "右肺下野", "side": "right", "coords": [0.06, 0.57, 0.30, 0.25],
     "note": "第 4 前肋下缘至膈面，含右侧肋膈角。"},
    {"id": "LUL", "name": "左肺上野", "side": "left", "coords": [0.64, 0.08, 0.30, 0.25],
     "note": "肺尖至第 2 前肋下缘水平；图像右侧为患者左侧。"},
    {"id": "LML", "name": "左肺中野", "side": "left", "coords": [0.64, 0.33, 0.30, 0.24],
     "note": "第 2 至第 4 前肋下缘之间；含心影左缘。"},
    {"id": "LLL", "name": "左肺下野", "side": "left", "coords": [0.64, 0.57, 0.30, 0.25],
     "note": "第 4 前肋下缘至膈面，含左侧肋膈角。"},
    {"id": "MED", "name": "纵隔与心影", "side": "midline", "coords": [0.36, 0.08, 0.28, 0.74],
     "note": "气管、纵隔轮廓与心影；不推断具体心腔。"},
    {"id": "SUB", "name": "膈下", "side": "midline", "coords": [0.10, 0.84, 0.80, 0.12],
     "note": "膈面以下，含胃泡与肝影上部。"},
]

LAT_ZONES = [
    {"id": "ANT", "name": "胸骨后间隙", "side": "midline", "coords": [0.08, 0.10, 0.30, 0.80],
     "note": "胸骨后方至升主动脉前缘；侧位片不推断左右。"},
    {"id": "MID", "name": "肺门与中区", "side": "midline", "coords": [0.38, 0.10, 0.30, 0.80],
     "note": "肺门结构重叠区；侧位片不推断左右。"},
    {"id": "POST", "name": "后肺野与后肋膈角", "side": "midline", "coords": [0.68, 0.10, 0.28, 0.80],
     "note": "后肺野与后肋膈角；少量积液最早在此显示。"},
]

SYSTEM_ITEMS = [
    ("airway", "气管与纵隔"),
    ("lungs", "肺野"),
    ("hila", "肺门"),
    ("heart", "心影"),
    ("pleura", "膈肌与肋膈角"),
    ("bones", "骨骼与软组织"),
    ("devices", "导管与植入物"),
]

NORMAL_TEXT = {
    "RUL": "肺野透亮度正常，未见明确局灶性密度增高影。",
    "RML": "肺野透亮度正常，未见明确局灶性密度增高影。",
    "RLL": "肺野透亮度正常，未见明确局灶性密度增高影。",
    "LUL": "肺野透亮度正常，未见明确局灶性密度增高影。",
    "LML": "肺野透亮度正常，未见明确局灶性密度增高影。",
    "LLL": "肺野透亮度正常，未见明确局灶性密度增高影。",
    "MED": "纵隔居中，心影大小与形态未见明显异常。",
    "SUB": "膈下未见游离气体。",
    "ANT": "胸骨后间隙清晰，未见明确异常密度。",
    "MID": "肺门区结构重叠，未见明确异常密度。",
    "POST": "后肺野透亮度正常，后肋膈角锐利。",
}

NORMAL_SYSTEM = {
    "airway": "气管居中，纵隔未见明显移位。",
    "lungs": "双肺野清晰，未见明确异常密度影。",
    "hila": "双侧肺门大小、位置未见明显异常。",
    "heart": "心影大小与形态未见明显异常。",
    "pleura": "双侧膈面光滑，肋膈角锐利。",
    "bones": "胸廓对称，骨骼与软组织未见明确异常。",
    "devices": "未见导管、导线或植入物。",
}

UNMENTIONED = "公开来源未逐区描述该分区；本工具不作正常或异常的推断。"
UNMENTIONED_SYSTEM = "公开来源未提及；未作判断。"


def z(status, text, signs=None, basis="公开来源说明"):
    return (status, text, signs or [], basis)


def s(status, text, basis="公开来源说明"):
    return (status, text, basis)


def all_normal(pose="PA", lung_text=None):
    zones = {}
    for zdef in (PA_ZONES if pose == "PA" else LAT_ZONES):
        text = NORMAL_TEXT[zdef["id"]]
        if lung_text and zdef["id"] in ("RUL", "RML", "RLL", "LUL", "LML", "LLL"):
            text = lung_text
        zones[zdef["id"]] = z("normal", text)
    return zones


def all_normal_system(**overrides):
    out = {k: s("normal", v) for k, v in NORMAL_SYSTEM.items()}
    out.update(overrides)
    return out


CURATION = {
    "CASE-001": {
        "quality": "标准后前位（PA）",
        "zones": all_normal("PA"),
        "system": all_normal_system(),
        "signs": [],
        "teaching": [
            "正常胸片是分区与系统顺序的解剖对照。",
            "阅片顺序：气管与纵隔 → 肺野 → 肺门 → 心影 → 膈肌与肋膈角 → 骨骼与软组织。",
        ],
    },
    "CASE-002": {
        "quality": "标准侧位（LAT）",
        "zones": all_normal("LAT"),
        "system": all_normal_system(pleura=s("normal", "后肋膈角锐利。")),
        "signs": [],
        "teaching": ["与正位片配对，用于理解胸骨后间隙、心后间隙与膈肌形态。", "侧位片不推断左右侧别。"],
    },
    "CASE-003": {
        "quality": "解剖标注版；欠吸气、轻度旋转",
        "zones": {
            **{k: z("normal", "肺野透亮度正常；欠吸气使肺野显得较短，判读时需注意。")
               for k in ("RUL", "RML", "RLL", "LUL", "LML", "LLL")},
            "MED": z("limited", "心影大小在欠吸气条件下评估受限。"),
            "SUB": z("normal", "膈下未见游离气体。"),
        },
        "system": all_normal_system(
            airway=s("normal", "气管居中；可见轻度旋转。"),
            lungs=s("normal", "双肺野透亮度正常；欠吸气。"),
            heart=s("limited", "心影大小评估受限（欠吸气）。"),
            pleura=s("normal", "膈面位置偏高，肋膈角可见。"),
            bones=s("normal", "图中标注棘突、锁骨内侧端、主动脉结与右侧第 5 前肋。"),
        ),
        "signs": [],
        "caveats": ["欠吸气与轻度旋转会影响心影比例、肺野透亮度与膈肌位置的判断。"],
        "teaching": ["同一张片子可以同时讲正常解剖与投照条件对判读的影响。"],
    },
    "CASE-005": {
        "quality": "带标注正位片（含中心静脉导管）",
        "zones": {
            **{k: z("abnormal", "双肺气腔影，伴肺不张；公开说明未逐区定位。", ["SIGN-002", "SIGN-019"])
               for k in ("RUL", "RML", "RLL", "LUL", "LML", "LLL")},
            "MED": z("unmentioned", "纵隔旁可见中心静脉导管影；纵隔轮廓未见明显移位（公开说明未提及）。"),
            "SUB": z("unmentioned", UNMENTIONED),
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "双肺气腔影伴肺不张（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("abnormal", "可见中心静脉导管，尖端位置需结合原始影像核对。"),
        },
        "signs": ["SIGN-002", "SIGN-019"],
        "caveats": [
            "公开说明未逐区定位，分区所见按双肺弥漫性改变处理。",
            "导管尖端位置未在本库标注，需人工核对。",
        ],
    },
    "CASE-006": {
        "quality": "正位片（原图红箭头）",
        "zones": {
            "RML": z("abnormal", "右肺中野大片实变，红箭头指向病灶边缘。", ["SIGN-002"], "原图箭头 + 公开说明"),
            "RLL": z("abnormal", "右肺下野可见实变影向下延伸。", ["SIGN-002"], "公开说明 + 原图"),
            **{k: z("unmentioned", UNMENTIONED) for k in ("RUL", "LUL", "LML", "LLL", "MED", "SUB")},
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "右肺中下野大片实变（公开说明与图注）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-002"],
        "caveats": [
            "红箭头为原图标注；未标注分区不作推断。",
            "公开说明未指明肺叶；分区按图中箭头与密度增高范围标注为右肺中野、下野。",
        ],
    },
    "CASE-007": {
        "quality": "正位片",
        "zones": {
            "RLL": z("abnormal", "双侧下肺野气腔影，密度增高。", ["SIGN-002"]),
            "LLL": z("abnormal", "双侧下肺野气腔影，密度增高。", ["SIGN-002"]),
            **{k: z("unmentioned", UNMENTIONED) for k in ("RUL", "RML", "LUL", "LML", "MED", "SUB")},
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "双侧下肺野气腔影（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-002"],
    },
    "CASE-008": {
        "quality": "侧位片（与正位配对）",
        "zones": {
            "POST": z("abnormal", "侧位片示下肺野/后部气腔影。", ["SIGN-002"]),
            **{k: z("unmentioned", UNMENTIONED) for k in ("ANT", "MID")},
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "下肺野/后部气腔影（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-002"],
    },
    "CASE-015": {
        "quality": "正位片",
        "zones": {
            "RUL": z("abnormal", "右中上肺野斑片状密度增高。", ["SIGN-002"]),
            "RML": z("abnormal", "右中上肺野斑片状密度增高。", ["SIGN-002"]),
            **{k: z("unmentioned", UNMENTIONED) for k in ("RLL", "LUL", "LML", "LLL", "MED", "SUB")},
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "右中上肺野斑片状密度增高（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-002"],
    },
    "CASE-016": {
        "quality": "正位片",
        "zones": {
            **{k: z("abnormal", "双肺弥漫粟粒样细小结节。", ["SIGN-003"])
               for k in ("RUL", "RML", "RLL", "LUL", "LML", "LLL")},
            "MED": z("unmentioned", UNMENTIONED),
            "SUB": z("unmentioned", UNMENTIONED),
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "双肺弥漫粟粒样细小结节（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-003"],
        "caveats": ["粟粒样结节的逐区分布未在公开说明中量化；分区所见为弥漫性描述。"],
    },
    "CASE-017": {
        "quality": "正位片",
        "zones": {
            "RLL": z("abnormal", "双侧下肺野密度增高，肋膈角变钝。", ["SIGN-007"]),
            "LLL": z("abnormal", "双侧下肺野密度增高，肋膈角变钝。", ["SIGN-007"]),
            **{k: z("unmentioned", UNMENTIONED) for k in ("RUL", "RML", "LUL", "LML", "MED", "SUB")},
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "双侧下肺野密度增高（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("abnormal", "双侧肋膈角变钝，公开说明为胸腔积液相关改变。"),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-007"],
    },
    "CASE-018": {
        "quality": "侧位片（原图箭头）",
        "zones": {
            "POST": z("abnormal", "后肋膈角变钝，可见液体分布；箭头为原图标注。", ["SIGN-007"], "原图箭头 + 公开说明"),
            **{k: z("unmentioned", UNMENTIONED) for k in ("ANT", "MID")},
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("unmentioned", UNMENTIONED_SYSTEM),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("abnormal", "后肋膈角变钝，公开说明为大量胸腔积液侧位片。"),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-007"],
        "caveats": ["箭头为原图标注；侧位片不推断左右侧别。"],
    },
    "CASE-019": {
        "enabled": False,
        "disabled_reason": "A/B/C 多图拼接，无法对应单一解剖分区；不纳入胸片阅片队列。",
    },
    "CASE-033": {
        "quality": "解剖标注版（意大利语标注）",
        "zones": all_normal("PA"),
        "system": all_normal_system(bones=s("normal", "图上有原图自带的解剖标注，可用于解剖对照。")),
        "signs": [],
        "caveats": ["标注为原图自带，非本库添加。"],
        "teaching": ["适合做肺野、肺门、心影、膈面的解剖对照。"],
    },
    "CASE-034": {
        "quality": "标准正位片",
        "zones": all_normal("PA"),
        "system": all_normal_system(),
        "signs": [],
    },
    "CASE-036": {
        "quality": "正位片（原图气胸标注）",
        "description_public": "原图标注为右侧气胸（Pneumothorax / Collapsed right lung）；来源页文字描述为健康男性，二者冲突。本页以图注与影像标注为准，建议人工复核。",
        "zones": {
            **{k: z("abnormal", "右侧胸腔可见气胸，右肺压缩，肺纹理消失（原图标注 Pneumothorax / Collapsed right lung）。",
                    ["SIGN-008"], "原图标注") for k in ("RUL", "RML", "RLL")},
            **{k: z("unmentioned", "原图仅标注右侧气胸；左侧未标注，本工具不作推断。")
               for k in ("LUL", "LML", "LLL")},
            "MED": z("unmentioned", UNMENTIONED),
            "SUB": z("unmentioned", UNMENTIONED),
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "右侧气胸，右肺压缩（原图标注）。", "原图标注"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("abnormal", "右侧胸膜腔积气（原图标注）。", "原图标注"),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-008"],
        "caveats": [
            "来源页文字描述为健康男性，与图注气胸冲突；本页以图注和影像标注为准，建议人工复核。",
            "未判断张力性气胸；如疑张力性气胸需结合纵隔移位与临床。",
        ],
        "teaching": ["气胸的直接征象：脏层胸膜线，其外肺纹理消失。"],
    },
    "CASE-041": {
        "quality": "正位片（软组织对照）",
        "zones": all_normal("PA"),
        "system": all_normal_system(
            bones=s("normal", "可见双侧胸大肌影，为正常软组织投影，勿误为病变。"),
        ),
        "signs": [],
        "teaching": ["胸大肌影可模拟肺尖/中野密度增高，注意与病变区分。"],
    },
    "CASE-047": {
        "quality": "正位片",
        "zones": all_normal("PA", lung_text="双肺清晰，未见气胸或积液（公开说明）。"),
        "system": all_normal_system(
            lungs=s("normal", "双肺清晰，未见气胸或积液（公开说明）。"),
            heart=s("normal", "心影与肺血管未见明显异常（公开说明）。"),
            pleura=s("limited", "膈肌轻度变平，公开说明提示可能与 COPD 相关，需结合临床。"),
        ),
        "signs": [],
        "caveats": ["轻度膈肌变平不是诊断，需结合肺功能与临床。"],
    },
    "CASE-153": {
        "quality": "正位片",
        "zones": {
            "RLL": z("abnormal", "下肺野可见 Kerley B 线，肺血管影增粗（公开说明）。", ["SIGN-011"]),
            "LLL": z("abnormal", "下肺野可见 Kerley B 线，肺血管影增粗（公开说明）。", ["SIGN-011"]),
            "MED": z("abnormal", "心影增大（公开说明）。", ["SIGN-010"]),
            **{k: z("unmentioned", UNMENTIONED) for k in ("RUL", "RML", "LUL", "LML", "SUB")},
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "下肺野 Kerley B 线，肺血管增粗（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("abnormal", "心影增大（公开说明）。"),
            "pleura": s("abnormal", "少量胸腔积液（公开说明）。"),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-010", "SIGN-011", "SIGN-007"],
        "caveats": ["Kerley B 线与心影增大提示间质性肺水肿可能，但本页只作征象对照，不输出诊断。"],
    },
    "CASE-162": {
        "quality": "正位片",
        "zones": {
            **{k: z("abnormal", "双肺弥漫网结节影（公开说明）。", ["SIGN-003", "SIGN-011"])
               for k in ("RUL", "RML", "RLL", "LUL", "LML", "LLL")},
            "MED": z("unmentioned", UNMENTIONED),
            "SUB": z("unmentioned", UNMENTIONED),
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "双肺弥漫网结节影（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-003", "SIGN-011"],
        "caveats": ["与 CASE-016 同为粟粒性结核不同病程，可作对照。"],
    },
    "CASE-201": {
        "enabled": False,
        "disabled_reason": "同一病例两幅并排，无法对应单一解剖分区；不纳入胸片阅片队列。",
        "quality": "双图对照（同一病例两幅）",
        "zones": {
            **{k: z("abnormal", "双肺弥漫磨玻璃样密度增高，以肺门周围及中下野为主。", ["SIGN-001"])
               for k in ("RUL", "RML", "RLL", "LUL", "LML", "LLL")},
            "MED": z("unmentioned", UNMENTIONED),
            "SUB": z("unmentioned", UNMENTIONED),
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "双肺弥漫磨玻璃样密度增高（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-001"],
        "caveats": ["图为双幅对照，分区框为整图近似，不区分左右幅。"],
    },
    "CASE-202": {
        "quality": "正位片（原图红箭头）",
        "description_public": "公开说明称“右肺上叶大片实变”；图中红箭头与密度增高区位于右肺中野，二者不一致。本页以图为准，建议人工复核。",
        "zones": {
            "RML": z("abnormal", "右肺中野大片实变，红箭头指向病灶边缘。", ["SIGN-002"], "原图箭头 + 公开说明"),
            "RLL": z("abnormal", "右肺下野可见实变影向下延伸。", ["SIGN-002"], "公开说明 + 原图"),
            **{k: z("unmentioned", UNMENTIONED) for k in ("RUL", "LUL", "LML", "LLL", "MED", "SUB")},
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "右肺中下野大片实变（原图箭头与公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-002"],
        "caveats": [
            "公开说明称“右肺上叶”，但图中箭头位于右肺中野；本页以图为准，建议人工复核。",
            "红箭头为原图标注；未标注分区不作推断。",
        ],
    },
    "CASE-203": {
        "quality": "历史影像（正位片）",
        "zones": {
            "RUL": z("abnormal", "双肺上野斑片状、结节状密度增高（公开说明）。", ["SIGN-002", "SIGN-003"]),
            "LUL": z("abnormal", "双肺上野斑片状、结节状密度增高（公开说明）。", ["SIGN-002", "SIGN-003"]),
            **{k: z("unmentioned", UNMENTIONED) for k in ("RML", "RLL", "LML", "LLL", "MED", "SUB")},
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "双肺上野斑片状、结节状密度增高（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-002", "SIGN-003"],
        "caveats": ["历史影像，图像质量与投照条件受限。"],
    },
    "CASE-204": {
        "quality": "正位片",
        "zones": {
            **{k: z("abnormal", "双肺弥漫小结节影，以中上野为著。", ["SIGN-003"])
               for k in ("RUL", "RML", "RLL", "LUL", "LML", "LLL")},
            "MED": z("unmentioned", UNMENTIONED),
            "SUB": z("unmentioned", UNMENTIONED),
        },
        "system": {
            "airway": s("unmentioned", UNMENTIONED_SYSTEM),
            "lungs": s("abnormal", "双肺弥漫小结节影，以中上野为著（公开说明）。"),
            "hila": s("unmentioned", UNMENTIONED_SYSTEM),
            "heart": s("unmentioned", UNMENTIONED_SYSTEM),
            "pleura": s("unmentioned", UNMENTIONED_SYSTEM),
            "bones": s("unmentioned", UNMENTIONED_SYSTEM),
            "devices": s("unmentioned", UNMENTIONED_SYSTEM),
        },
        "signs": ["SIGN-003"],
    },
}


def load_jsonl(name):
    path = DATA / name
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    cases = {c["id"]: c for c in load_jsonl("cases.jsonl")}
    signs = load_jsonl("signs.jsonl")
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf8"))

    chest_ids = [
        cid for cid, c in cases.items()
        if c.get("modality") == "CR" and c.get("body_part") == "胸部"
    ]
    chest_ids.sort()

    # 同源裁切提示：同一张 Wikimedia 原图被裁成多例时，明确写出“不是独立病例”。
    src_count = {}
    for cid in chest_ids:
        src = cases[cid].get("source_page", "")
        if src:
            src_count[src] = src_count.get(src, 0) + 1

    out_cases = []
    for cid in chest_ids:
        c = cases[cid]
        cur = CURATION.get(cid)
        if not cur:
            print("missing curation:", cid)
            continue
        pose = "LAT" if c.get("pose_class") == "chest_lat" else "PA"
        zones_def = LAT_ZONES if pose == "LAT" else PA_ZONES
        image_rel = c["image"]
        image_path = ROOT / "kb" / image_rel
        served_path = ROOT / "outputs" / "medtrain" / image_rel
        sha_source = sha256_file(image_path) if image_path.exists() else ""
        sha_served = sha256_file(served_path) if served_path.exists() else sha_source
        item = {
            "id": cid,
            "title": c["title"],
            "modality": c["modality"],
            "body_part": c["body_part"],
            "pose": pose,
            "pose_label": "侧位（LAT）" if pose == "LAT" else "正位（PA）",
            "image": image_rel,
            "sha256": sha_served,
            "sha256_source": sha_source,
            "quality": cur.get("quality", ""),
            "enabled": cur.get("enabled", True),
            "disabled_reason": cur.get("disabled_reason", ""),
            "source_page": c.get("source_page", ""),
            "source_note": (
                "与同源病例共用同一张原图的不同裁切，不是独立病例。"
                if src_count.get(c.get("source_page", ""), 0) > 1 else ""
            ),
            "license": c.get("license", ""),
            "artist": c.get("artist", ""),
            "description_public": cur.get("description_public", c.get("description_public", "")),
            "teaching_note": c.get("teaching_note", ""),
            "signs": cur.get("signs", []),
            "caveats": cur.get("caveats", []),
            "teaching": cur.get("teaching", []),
            "zones": [],
            "system": [],
        }
        for zd in zones_def:
            zid = zd["id"]
            if not item["enabled"]:
                continue
            status, text, sign_ids, basis = cur["zones"].get(zid, z("unmentioned", UNMENTIONED))
            item["zones"].append({
                **zd,
                "status": status,
                "text": text,
                "sign_ids": sign_ids,
                "basis": basis,
            })
        if item["enabled"]:
            for key, label in SYSTEM_ITEMS:
                status, text, basis = cur["system"].get(key, s("unmentioned", UNMENTIONED_SYSTEM))
                item["system"].append({
                    "id": key, "name": label, "status": status, "text": text, "basis": basis,
                })
        out_cases.append(item)

    enabled = [c for c in out_cases if c["enabled"]]
    sign_index = {s["id"]: s for s in signs}
    payload = {
        "version": "2026-11-20",
        "scope": "CR 胸部（胸片）",
        "method": "逐区结构化校正（AI 辅助，待医学审核）；状态四值；未提及不推断为正常",
        "disclaimer": "仅用于医学影像教学与研究，不构成诊断意见，不替代临床决策。",
        "zone_status": {
            "abnormal": "公开来源/图注明确描述异常",
            "normal": "公开来源明确为正常，或正常病例的解剖对照",
            "unmentioned": "公开来源没有逐区描述，本工具不作推断",
            "limited": "投照条件或图像质量导致判读受限",
        },
        "counts": {
            "chest_cr_total": len(out_cases),
            "enabled": len(enabled),
            "disabled": len(out_cases) - len(enabled),
        },
        "cases": out_cases,
        "sign_index": sign_index,
        "sources": sources,
    }

    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    BUILD_OUT.parent.mkdir(parents=True, exist_ok=True)
    BUILD_OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.1f} KB)")
    print(f"wrote {BUILD_OUT} ({BUILD_OUT.stat().st_size/1024:.1f} KB)")
    print(f"cases={len(out_cases)} enabled={len(enabled)} disabled={len(out_cases)-len(enabled)}")


if __name__ == "__main__":
    main()
