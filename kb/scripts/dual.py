#!/usr/bin/env python3
"""双线判断：影像线（征象 + 公开影像）与指南线（条款 + 适用条件）分别召回，
再输出可解释的对齐结论。

边界：
- 判断的是「库内证据是否对齐」，不是病情判断；
- 条款给出的处理方向只作原文摘录展示，不转述为建议；
- 条件不足时明确列出缺什么，不猜测。
"""
import re

NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:—|－|-|~|至)\s*(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)")
OP_NUM = re.compile(r"(≥|<=|≤|<|>)\s*(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)")
CAT = re.compile(
    r"(TR\s*[1-5][abc]?|BI-?RADS\s*[0-6]|[0-6]\s*类|LR-?[1-5]|Bosniak\s*(?:IIF|I{1,3}|IV)|"
    r"PI-?RADS\s*[1-5]|O-?RADS\s*[0-5]|类别\s*[1-4]X?)",
    re.I,
)


def to_mm(v, unit):
    return float(v) * 10 if unit.lower() in ("cm", "厘米") else float(v)


def norm_cat(s):
    s = re.sub(r"[\s\-]", "", s.upper())
    s = s.replace("BIRADS", "BI-RADS").replace("PIRADS", "PI-RADS").replace("ORADS", "O-RADS")
    s = s.replace("LR", "LR-") if s.startswith("LR") and not s.startswith("LR-") else s
    s = re.sub(r"^类别", "类别", s)
    return s


def cats(text):
    return {norm_cat(m.group(0)) for m in CAT.finditer(text or "")}


def numbers(text):
    out = []
    for m in RANGE.finditer(text or ""):
        out.append(("range", to_mm(m.group(1), m.group(3)), to_mm(m.group(2), m.group(3))))
    for m in OP_NUM.finditer(text or ""):
        out.append(("op", m.group(1), to_mm(m.group(2), m.group(3))))
    for m in NUM.finditer(text or ""):
        out.append(("val", to_mm(m.group(1), m.group(2))))
    return out


FLOW = re.compile(r"已完成|完成超声|完成多参数|完成初始|具备五个维度|属于筛查人群|属于高危人群|有可比较|测量方法一致|评估主胰管|信息不足|偶然发现")

STD_HINTS = [
    ("STD-TIRADS", ("ti-rads", "tirads", "甲状腺")),
    ("STD-BIRADS", ("bi-rads", "birads", "乳腺")),
    ("STD-LIRADS", ("li-rads", "lirads", "肝")),
    ("STD-BOSNIAK", ("bosniak", "肾")),
    ("STD-PIRADS", ("pi-rads", "pirads", "前列腺")),
    ("STD-ORADS", ("o-rads", "orads", "卵巢")),
    ("STD-LUNGRADS", ("lung-rads", "lungrads", "筛查")),
    ("STD-FLEISCHNER", ("fleischner",)),
]

SYN = [("囊肿", "囊性"), ("囊性病变", "囊性"), ("占位", "肿块"), ("低密度", "低密度")]


def std_context(q):
    ql = (q or "").lower()
    for sid, keys in STD_HINTS:
        if any(k in ql for k in keys):
            return sid
    return None


def core_cat(text):
    out = set()
    t = text or ""
    for m in re.finditer(r"TR\s*([1-5])", t, re.I):
        out.add(m.group(1))
    for m in re.finditer(r"BI-?RADS\s*([0-6])", t, re.I):
        out.add(m.group(1))
    for m in re.finditer(r"LR-?\s*([1-5])", t, re.I):
        out.add(m.group(1))
    for m in re.finditer(r"Bosniak\s*(IIF|I{1,3}|IV)", t, re.I):
        out.add(m.group(1).upper())
    for m in re.finditer(r"PI-?RADS\s*([1-5])", t, re.I):
        out.add(m.group(1))
    for m in re.finditer(r"O-?RADS\s*([0-5])", t, re.I):
        out.add(m.group(1))
    for m in re.finditer(r"(IIF|IV|III|II|I)\s*类", t):
        out.add(m.group(1).upper())
    for m in re.finditer(r"([0-6])\s*类", t):
        out.add(m.group(1))
    for m in re.finditer(r"类别\s*([1-4])X?", t):
        out.add(m.group(1))
    return out


def syn(text):
    for a, b in SYN:
        text = text.replace(a, b)
    return text


def bigrams(text):
    t = re.sub(r"[^\u4e00-\u9fffa-z0-9]", "", (text or "").lower())
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else {t}


def cond_met(cond, q, q_cats, q_nums, guideline=None, q_std=None):
    """条件是否被查询覆盖：分类优先，其次数值，最后关键词重叠。"""
    if "部分实性" in cond and "部分" not in q:
        return False
    if "磨玻璃" in cond and "磨玻璃" not in q:
        return False
    if "单发" in cond and "多发" in q:
        return False
    if "分类" in cond and guideline:
        gc = core_cat(guideline.get("category", ""))
        qc = core_cat(q)
        same_std = q_std is None or q_std == guideline.get("standard_id")
        if gc and qc and same_std and (gc & qc):
            return True
        if gc and not qc:
            return False
    c_cats = cats(cond)
    if c_cats:
        return bool(c_cats & q_cats)
    c_nums = numbers(cond)
    if c_nums and q_nums:
        for c in c_nums:
            if c[0] == "range":
                if any(n[0] == "val" and c[1] <= n[1] <= c[2] for n in q_nums):
                    return True
                if any(n[0] == "op" and c[1] <= n[2] <= c[2] for n in q_nums):
                    return True
            elif c[0] == "op":
                op, v = c[1], c[2]
                for n in q_nums:
                    qv = n[2] if n[0] == "op" else (n[1] if n[0] == "val" else None)
                    if qv is None:
                        continue
                    if op in ("≥",) and qv >= v:
                        return True
                    if op in ("≤", "<=") and qv <= v:
                        return True
                    if op == "<" and qv < v:
                        return True
                    if op == ">" and qv > v:
                        return True
        return False
    cg = bigrams(syn(cond))
    qg = bigrams(syn(q))
    if not cg:
        return False
    if len(cg & qg) / len(cg) >= 0.6:
        return True
    if len(cond) <= 4 and (cg & qg):
        return True
    return False


def assess(kb, query, modality=None, part=None):
    imaging = kb.search(query, modality=modality, part=part)
    guidelines = kb.search_guidelines(query, modality=modality, part=part, limit=6)

    q_cats = cats(query)
    q_nums = numbers(query)
    q_std = std_context(query)

    scored = []
    for g in guidelines:
        conds = [c for c in g.get("conditions", []) if not FLOW.search(c)]
        matched = [c for c in conds if cond_met(c, query, q_cats, q_nums, g, q_std)]
        missing = [c for c in conds if c not in matched]
        coverage = len(matched) / len(conds) if conds else 0.0
        scored.append({"g": g, "matched": matched, "missing": missing, "coverage": coverage})
    scored.sort(key=lambda x: -x["coverage"])

    if not imaging["signs"] and not guidelines:
        level, note = "insufficient", "影像线与指南线都未命中，库内没有可对照的证据。"
        best = None
    elif not imaging["signs"]:
        level, note = "insufficient", "影像线未命中征象条目，无法与指南条款建立对应关系。"
        best = scored[0] if scored else None
    elif not guidelines:
        level, note = "insufficient", "指南线未命中同部位条款，暂不做对应判断。"
        best = None
    else:
        best = scored[0] if scored[0]["coverage"] > 0 else None
        if best is None:
            cand = [x for x in scored if core_cat(x["g"].get("category", ""))] or scored
            best = cand[0] if cand else None
            if best:
                miss = []
                gc = core_cat(best["g"].get("category", ""))
                if gc and not core_cat(query):
                    miss.append("分类等级（" + best["g"].get("standard_name", "") + "）")
                if any(numbers(c) for c in best["g"].get("conditions", [])) and not q_nums:
                    miss.append("病灶尺寸")
                best["missing"] = miss or ["条款适用条件"]
                best["matched"] = []
                best["coverage"] = 0.0
        if best["coverage"] >= 1.0:
            level = "aligned"
            note = "影像线已覆盖该条款的全部适用条件，两线在描述维度上对应。条款的处理方向仅为原文摘录，不构成对你的建议。"
        elif best["coverage"] > 0:
            level = "partial"
            note = "指南线缺少关键条件，尚不能定位到具体条款。需补充：" + "、".join(best["missing"]) + "。"
        else:
            level = "partial"
            note = "影像线已命中征象，但指南线缺少定位条件。需补充：" + "、".join(best["missing"]) + "。"

    # 同一分类下出现不同处理方向时，标记来源差异，不裁决
    divergent = []
    if best:
        same = [x for x in scored if x["g"]["category"] == best["g"]["category"] and x["coverage"] >= 0.5]
        actions = {x["g"]["action"] for x in same}
        if len(actions) > 1:
            divergent = [{"id": x["g"]["id"], "action": x["g"]["action"], "source": x["g"]["standard_name"]} for x in same]

    if best:
        order = [best["g"]["id"]] + [g["id"] for g in guidelines if g["id"] != best["g"]["id"]]
        rank = {gid: i for i, gid in enumerate(order)}
        guidelines.sort(key=lambda g: rank.get(g["id"], 99))

    signs = imaging["signs"]
    if signs:
        top_part = signs[0].get("body_part", "")
        same = [x for x in signs if kb.same_family(x.get("body_part", ""), top_part)]
        signs = (same or signs)[:3]

    return {
        "query": query,
        "imaging": {
            "signs": signs,
            "cases": imaging["cases"],
            "confidence": imaging["confidence"],
        },
        "guidelines": guidelines,
        "alignment": {
            "level": level,
            "coverage": round(best["coverage"], 2) if best else 0.0,
            "best_id": best["g"]["id"] if best else None,
            "matched": best["matched"] if best else [],
            "missing": best["missing"] if best else [],
            "note": note,
            "action": best["g"]["action"] if best else "",
            "action_source": "处理方向摘自公开条款摘要，仅供对照，不是本工具给出的建议。" if best else "",
            "divergent": divergent,
        },
        "disclaimer": "双线判断表示库内影像证据与指南条款的对齐情况，不构成诊断意见，也不替代临床决策。",
    }
