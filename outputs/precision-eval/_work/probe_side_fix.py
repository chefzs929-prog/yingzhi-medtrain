#!/usr/bin/env python3
"""探针 3：侧别校验到底卡在哪——是报告抽错，还是分区元数据缺失？

结论导向：先分清"数据错"与"校验噪声"，再决定要不要上语义解析。

三分类：
  patient_side  患者右/左（"右肺""右叶""右侧甲状腺"）
  image_side    图像右/左（"图像左侧""画面右缘"）
  anatomical_ref 解剖参照（"心影右缘""脊柱旁"），不参与侧别判定
"""
import json
import re
from collections import Counter
from pathlib import Path

KB = Path(__file__).resolve().parents[3] / "kb" / "data"
load = lambda n: [json.loads(l) for l in (KB / n).read_text(encoding="utf8").splitlines() if l.strip()]

regions = load("regions.jsonl")
claims = load("claims.jsonl")
rm = {r["id"]: r for r in regions}

IMAGE_SIDE = re.compile(r"(图像|画面|图)[的]?\s*[左右](侧|边|缘|半|部)?")
ANATOMY_REF = re.compile(r"(心影|纵隔|气管|脊柱|肺门|膈|胸膜|肋膈角|主动脉|食管)[^，。；]{0,6}?[左右](缘|侧|旁|方)?")
PATIENT_SIDE = re.compile(r"([左右])(肺|叶|侧|肾|乳|甲状腺|肾上腺|卵巢|半|上野|中野|下野|上带|下带|中央区|周边)")


def extract(text):
    masked = text
    img, ana = [], []
    for m in IMAGE_SIDE.finditer(text):
        img.append(m.group(0))
        masked = masked.replace(m.group(0), "□" * len(m.group(0)))
    for m in ANATOMY_REF.finditer(text):
        ana.append(m.group(0))
        masked = masked.replace(m.group(0), "□" * len(m.group(0)))
    pat = [("right" if m.group(1) == "右" else "left") for m in PATIENT_SIDE.finditer(masked)]
    side = pat[0] if len(set(pat)) == 1 else (None if not pat else "ambiguous")
    return side, img, ana


dist = Counter(r.get("patient_side") for r in regions)
print("分区侧别元数据分布:", dict(dist))
known = dist["right"] + dist["left"]
print(f"可用于侧别校验的分区: {known}/{len(regions)} = {known/len(regions):.1%}")

conflict_known = 0
noise_unknown = 0
noise_examples = []
for c in claims:
    t = c["text"]
    r = rm.get(c["region_id"], {})
    ps = r.get("patient_side")
    naive = "right" if "右" in t else ("left" if "左" in t else None)
    if not naive:
        continue
    if ps in ("right", "left"):
        if naive != ps:
            conflict_known += 1
    else:
        side, img, ana = extract(t)
        if img or ana:
            noise_unknown += 1
            if len(noise_examples) < 5:
                noise_examples.append((c["id"], t[:40], ps, img[:1], ana[:1]))

print(f"\n已知侧别分区上的真冲突: {conflict_known}")
print(f"unknown/midline 分区上，被图像侧/解剖参照污染的句子: {noise_unknown}")
for x in noise_examples:
    print("  ", x)

# 三分类后，患者侧可判定率
cov = sum(1 for c in claims if extract(c["text"])[0] in ("right", "left"))
print(f"\n三分类后患者侧可判定: {cov}/{len(claims)} = {cov/len(claims):.1%}")
