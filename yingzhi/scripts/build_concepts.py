#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 signs.jsonl 的 may_see_in 反向生成「疾病/病理 → 征象」概念索引。

为什么需要它：库里只有 60 条「征象」词条，用户却常按疾病提问（例如「肺水肿的征象」）。
肺水肿不是征象，按词条名检索必然未命中；但它的相关征象其实散落在 may_see_in 里。
本脚本把这些反向关系聚合成 concepts.jsonl，让检索能按疾病名落到真实 SIGN id。

口径分两层，回答时必须区分：
- sign_ids        may_see_in 原文直接支持，属于库内证据。
- related_sign_ids 人工补充的病理关联，只在回答里标「关联」，
                    不能算作 may_see_in 的原文依据。

用法：
    python3 yingzhi/scripts/build_concepts.py            # 生成 kb/data/concepts.jsonl
    python3 yingzhi/scripts/build_concepts.py --check    # 只校验，不写文件
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "kb", "data")
SIGN_FILE = os.path.join(DATA, "signs.jsonl")
OUT_FILE = os.path.join(DATA, "concepts.jsonl")

# 人工种子：只补名称、英文、别名、关联征象与提示，不替代 may_see_in 的自动聚合。
# related_sign_ids 必须能在 signs.jsonl 里找到，脚本会校验。
SEED = {
    "肺水肿": {
        "en": "pulmonary edema",
        "aliases": ["肺水", "心源性肺水肿", "肺水肿征象", "pulmonary edema"],
        "related_sign_ids": ["SIGN-007", "SIGN-010"],
        "note": "心源性者常见心影增大伴胸腔积液；分布与病程用于与非心源性鉴别。",
    },
    "肺出血": {
        "en": "pulmonary hemorrhage",
        "aliases": ["肺内出血", "咯血", "肺泡出血"],
        "related_sign_ids": ["SIGN-001"],
        "note": "磨玻璃影与实变可并存，需结合临床与实验室检查。",
    },
    "感染性病变": {
        "en": "infection",
        "aliases": ["感染", "炎症", "炎性病变", "肺炎"],
        "related_sign_ids": ["SIGN-017"],
        "note": "树芽征提示小气道播散，属于感染性病变的常见模式。",
    },
    "肿瘤性病变": {
        "en": "neoplasm",
        "aliases": ["肿瘤", "肺癌", "占位", "恶性"],
        "related_sign_ids": ["SIGN-055", "SIGN-056"],
        "note": "毛刺征与纵横比常用于乳腺结节的风险分层，不构成良恶性诊断。",
    },
    "肺结核": {
        "en": "pulmonary tuberculosis",
        "aliases": ["结核", "结核球", "TB"],
        "related_sign_ids": ["SIGN-003", "SIGN-004", "SIGN-017"],
        "note": "树芽征、空洞与结核球可同时出现；确诊依赖病原学。",
    },
    "间质性肺病": {
        "en": "interstitial lung disease",
        "aliases": ["间质性病变", "肺纤维化", "ILD", "纤维化"],
        "related_sign_ids": ["SIGN-012", "SIGN-018"],
        "note": "蜂窝影提示纤维化；铺路石征需结合病程判断。",
    },
    "肺栓塞": {
        "en": "pulmonary embolism",
        "aliases": ["PE", "肺动脉栓塞"],
        "related_sign_ids": ["SIGN-019"],
        "note": "库内无直接征象词条，仅能由肺不张等间接表现提示，确诊需增强 CT 血管成像。",
    },
    "气胸": {
        "en": "pneumothorax",
        "aliases": ["自发性气胸", "张力性气胸"],
        "related_sign_ids": ["SIGN-008"],
        "note": "张力性气胸属急症，影像提示后需立即临床处理。",
    },
    "胸腔积液": {
        "en": "pleural effusion",
        "aliases": ["胸水", "胸膜腔积液"],
        "related_sign_ids": ["SIGN-007"],
        "note": "与肺实变的区别在于是否可见空气支气管征。",
    },
    "支气管扩张": {
        "en": "bronchiectasis",
        "aliases": ["支扩", "支气管扩张症"],
        "related_sign_ids": ["SIGN-013"],
        "note": "印戒征与轨道征是典型表现，需薄层 CT 评估。",
    },
    "肺不张": {
        "en": "atelectasis",
        "aliases": ["肺萎陷", "膨胀不全"],
        "related_sign_ids": ["SIGN-019"],
        "note": "需区分阻塞性与压迫性因素。",
    },
    "肝硬化": {
        "en": "liver cirrhosis",
        "aliases": ["肝纤维化", "cirrhosis"],
        "related_sign_ids": ["SIGN-026"],
        "note": "形态改变与门脉高压征象需结合临床与实验室检查。",
    },
    "胆囊炎": {
        "en": "cholecystitis",
        "aliases": ["急性胆囊炎", "慢性胆囊炎"],
        "related_sign_ids": ["SIGN-031", "SIGN-034"],
        "note": "胆囊壁增厚需结合临床症状与实验室检查。",
    },
    "胆道梗阻": {
        "en": "biliary obstruction",
        "aliases": ["胆管梗阻", "梗阻性黄疸"],
        "related_sign_ids": ["SIGN-025", "SIGN-033"],
        "note": "双管征提示胰头区或壶腹部占位可能。",
    },
    "胰腺炎": {
        "en": "pancreatitis",
        "aliases": ["急性胰腺炎", "慢性胰腺炎"],
        "related_sign_ids": ["SIGN-032"],
        "note": "胰腺钙化更支持慢性病程；急性期以周围渗出为主。",
    },
    "肾积水": {
        "en": "hydronephrosis",
        "aliases": ["肾盂积水", "尿路梗阻"],
        "related_sign_ids": ["SIGN-033"],
        "note": "需寻找梗阻原因，单纯肾积水不提示病因。",
    },
    "脑梗死": {
        "en": "cerebral infarction",
        "aliases": ["脑梗", "缺血性卒中", "缺血"],
        "related_sign_ids": ["SIGN-041", "SIGN-046"],
        "note": "急性期 CT 可能阴性，弥散受限更敏感。",
    },
    "脑出血": {
        "en": "intracerebral hemorrhage",
        "aliases": ["脑出血", "出血性卒中", "ICH"],
        "related_sign_ids": ["SIGN-045"],
        "note": "CT 高密度是急性期主要表现，需评估占位效应与中线移位。",
    },
    "脑水肿": {
        "en": "cerebral edema",
        "aliases": ["脑肿胀", "水肿带"],
        "related_sign_ids": ["SIGN-040", "SIGN-044"],
        "note": "水肿带分布有助判断病变性质，但不构成病因诊断。",
    },
    "骨关节炎": {
        "en": "osteoarthritis",
        "aliases": ["退行性骨关节病", "骨关节退变", "OA"],
        "related_sign_ids": ["SIGN-052", "SIGN-053"],
        "note": "关节积液与软骨信号改变需结合症状与负重位片。",
    },
    "骨折": {
        "en": "fracture",
        "aliases": ["骨裂", "病理性骨折", "应力性骨折"],
        "related_sign_ids": ["SIGN-048", "SIGN-054"],
        "note": "骨髓水肿可见于应力性改变，需与感染和肿瘤鉴别。",
    },
    "乳腺结节": {
        "en": "breast lesion",
        "aliases": ["乳腺肿块", "BI-RADS", "乳腺占位"],
        "related_sign_ids": ["SIGN-057", "SIGN-058"],
        "note": "分类以 BI-RADS 为准，影像征象只作描述。",
    },
    "甲状腺结节": {
        "en": "thyroid nodule",
        "aliases": ["甲状腺占位", "TI-RADS"],
        "related_sign_ids": ["SIGN-057", "SIGN-059"],
        "note": "分类以 TI-RADS 为准，需结合超声特征综合判断。",
    },
}

# 这些 may_see_in 值过于泛化，单独立概念没有检索价值；只作为其它概念的补充。
GENERIC = {
    "部分肿瘤性病变", "部分良性病变", "部分炎性病变", "部分实性肿瘤",
    "其他部位结节性病变", "部分甲状腺结节", "部分富血供病变", "良性病变",
    "恶性病变", "病变", "正常血管", "血管腔", "液体", "气体", "脂肪组织",
    "骨皮质", "钙化", "积液", "囊肿",
}

SPLIT_RE = re.compile(r"[或和与]")


def load_signs():
    rows = []
    with open(SIGN_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def split_term(term):
    """把「肺水肿或出血」拆成两个概念；过短的片段丢弃。"""
    parts = [p.strip() for p in SPLIT_RE.split(str(term)) if p.strip()]
    return [p for p in parts if len(p) >= 2]


def build():
    signs = load_signs()
    sign_ids = {s["id"] for s in signs}
    buckets = {}

    for sign in signs:
        for term in sign.get("may_see_in") or []:
            for name in split_term(term):
                if name in GENERIC:
                    continue
                buckets.setdefault(name, set()).add(sign["id"])

    # 人工种子即使没有被 may_see_in 命中，也保留（related 单独标注）。
    for name in SEED:
        buckets.setdefault(name, set())

    ordered = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out = []
    for idx, (name, ids) in enumerate(ordered, start=1):
        seed = SEED.get(name, {})
        direct = sorted(ids)
        related = [i for i in seed.get("related_sign_ids", []) if i not in ids]
        missing = [i for i in related if i not in sign_ids]
        if missing:
            raise SystemExit("概念「%s」的 related_sign_ids 不存在：%s" % (name, missing))
        if not direct and not related:
            continue
        out.append({
            "id": "CON-%03d" % idx,
            "name": name,
            "en": seed.get("en", ""),
            "aliases": seed.get("aliases", []),
            "sign_ids": direct,
            "related_sign_ids": related,
            "guideline_ids": seed.get("guideline_ids", []),
            "note": seed.get("note", ""),
            "derived_from": "signs.may_see_in",
        })
    return out, signs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    concepts, signs = build()
    names = [c["name"] for c in concepts]
    if len(names) != len(set(names)):
        raise SystemExit("概念名重复")

    # 覆盖率自检：每个 sign 至少被一个概念引用，否则说明聚合漏了。
    covered = set()
    for c in concepts:
        covered.update(c["sign_ids"])
    uncovered = sorted({s["id"] for s in signs} - covered)

    print("词条 %d 条，概念 %d 个" % (len(signs), len(concepts)))
    print("未被任何概念覆盖的征象：%s" % (", ".join(uncovered) or "无"))
    for c in concepts[:8]:
        print("  %s %s → %s%s" % (
            c["id"], c["name"], ",".join(c["sign_ids"]) or "-",
            (" +关联 " + ",".join(c["related_sign_ids"])) if c["related_sign_ids"] else ""))

    if args.check:
        return
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        for c in concepts:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    print("已写入 %s" % OUT_FILE)


if __name__ == "__main__":
    sys.exit(main())
