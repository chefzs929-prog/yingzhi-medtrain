#!/usr/bin/env python3
"""探针 1：现有 582 条分区结论（报告风格句子）能被结构化到什么程度。

只回答一个问题：把"报告句子 -> 侧别/分区/征象/极性/尺寸"做成规则层，
在真实数据上覆盖率是多少、和 region 元数据打架多少条。

纯标准库，只读 kb/data，不写任何库文件。
"""
import json
import re
from collections import Counter
from pathlib import Path

KB = Path(__file__).resolve().parents[3] / "kb" / "data"


def load(name):
    return [json.loads(l) for l in (KB / name).read_text(encoding="utf8").splitlines() if l.strip()]


claims = load("claims.jsonl")
regions = {r["id"]: r for r in load("regions.jsonl")}
signs = load("signs.jsonl")

# ---------- 槽位词典 ----------
ZONE = [
    "上野", "中野", "下野", "上带", "下带", "中央区", "周边区",
    "前部", "中部", "后部", "乳晕后", "肺尖", "肺门", "纵隔", "膈下",
    "上叶", "中叶", "下叶", "右叶", "左叶", "峡部",
]
SIDE = {"右": "right", "左": "left", "双": "bilateral"}
NEG = ["未见", "未发现", "无明确", "未见明确", "未显示", "阴性", "不存在"]
POS = ["可见", "显示", "见", "存在", "呈"]
DEGREE = ["轻度", "明显", "大片", "局灶", "弥漫", "斑片", "条索", "均匀", "不均匀"]
SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)", re.I)


def sign_hits(text):
    hit = []
    for s in signs:
        names = [s["name"]] + list(s.get("aliases") or []) + ([s["en"]] if s.get("en") else [])
        for n in names:
            if n and len(n) >= 2 and n in text:
                hit.append(s["id"])
                break
    return sorted(set(hit))


rows = []
for c in claims:
    t = c.get("text", "")
    r = regions.get(c.get("region_id"), {})
    side = next((v for k, v in SIDE.items() if k in t), None)
    zone = [z for z in ZONE if z in t]
    neg = [n for n in NEG if n in t]
    deg = [d for d in DEGREE if d in t]
    size = SIZE.findall(t)
    sh = sign_hits(t)
    conflict = bool(side and r.get("patient_side") and side != "bilateral" and side != r["patient_side"])
    zone_ok = None
    if zone and r.get("name"):
        zone_ok = any(z in r["name"] for z in zone)
    rows.append({
        "id": c["id"], "text": t, "region": r.get("name"), "patient_side": r.get("patient_side"),
        "side": side, "zone": zone, "neg": bool(neg), "degree": deg, "size": size,
        "signs": sh, "conflict": conflict, "zone_ok": zone_ok,
    })

n = len(rows)
cov = lambda f: sum(1 for x in rows if f(x))
print(f"样本 {n} 条分区结论")
print(f"  侧别可抽        {cov(lambda x: x['side']):4d}  {cov(lambda x: x['side'])/n:6.1%}")
print(f"  分区词可抽      {cov(lambda x: x['zone']):4d}  {cov(lambda x: x['zone'])/n:6.1%}")
print(f"  征象可抽        {cov(lambda x: x['signs']):4d}  {cov(lambda x: x['signs'])/n:6.1%}")
print(f"  极性可判(阴性)  {cov(lambda x: x['neg']):4d}  {cov(lambda x: x['neg'])/n:6.1%}")
print(f"  程度词可抽      {cov(lambda x: x['degree']):4d}  {cov(lambda x: x['degree'])/n:6.1%}")
print(f"  尺寸可抽        {cov(lambda x: x['size']):4d}  {cov(lambda x: x['size'])/n:6.1%}")
print()
print("侧别冲突（文字 vs region.patient_side）:", cov(lambda x: x['conflict']))
print("分区词与 region.name 不一致:", cov(lambda x: x['zone_ok'] is False))
print("既无侧别也无分区词（无法落到图上）:", cov(lambda x: not x['side'] and not x['zone']))
print()
print("分区词命中分布:", Counter(z for x in rows for z in x["zone"]).most_common(12))
print("尺寸样例:", [x["size"] for x in rows if x["size"]][:6])

print("\n--- 抽 5 条看槽位质量 ---")
for x in rows[:5]:
    print(json.dumps({k: x[k] for k in ("id", "text", "region", "patient_side", "side", "zone", "neg", "degree")},
                     ensure_ascii=False))
