"""量化评测：检索准确率、拒答混淆矩阵、模型一致性。

匹配算法与 kb/app/ask.html 中的 JS 版本逐行对齐（norm / bigrams / dice / scoreOf / 阈值）。

产物：kb/data/eval_report.json
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BANK = ROOT / "kb/data/ask_bank.json"
REFUSALS = ROOT / "kb/data/refusals.json"
EVAL = ROOT / "kb/data/eval_cases.json"
MODEL = ROOT / "kb/data/model_probe.json"
OUT = ROOT / "kb/data/eval_report.json"

STOP = {"有没有", "什么", "这张", "片子", "问题", "吗", "有吗", "怎样", "怎么"}
THR_ANSWER = 0.32
THR_REFUSE = 0.25
SEED = 20261124


def norm(s) -> str:
    return re.sub(r"[，。？！、；：\s\"'“”‘’]", "", str(s or "")).lower()


def bigrams(s):
    return [s[i:i + 2] for i in range(len(s) - 1)]


def dice(a, b):
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    m = {}
    for x in A:
        m[x] = m.get(x, 0) + 1
    hit = 0
    for x in B:
        c = m.get(x, 0)
        if c > 0:
            hit += 1
            m[x] = c - 1
    return 2 * hit / (len(A) + len(B))


ZONE_KEY = {"RUL": "右上", "RML": "右中", "RLL": "右下", "LUL": "左上", "LML": "左中", "LLL": "左下"}


def parse_region(q):
    """与 ask-core.js / ask_engine.py 保持一致：保留左右侧，别让「左肺中野」退化成「中」。"""
    side = "右" if "右" in q else ("左" if "左" in q else "")
    m = re.search(r"(上|中|下)\s*(野|部|叶|面|头|半|方|肺野|间|段)", q)
    if not m:
        return side
    return side + m.group(1)


def score_of(q, item):
    nq = norm(q)
    text = norm(item["question"] + " " + " ".join(item.get("keywords") or []))
    s = dice(nq, text)
    for k in item.get("keywords") or []:
        nk = norm(k)
        if len(nk) >= 2 and nk not in STOP and nk in nq:
            s += 0.18
    for a in item.get("aliases") or []:
        na = norm(a)
        if len(na) >= 2 and na in nq:
            s += 0.5
            break
    qk = parse_region(nq)
    if qk:
        zk = ZONE_KEY.get(((item.get("region") or {}).get("zone_id") or ""), "")
        if zk and all(ch in zk for ch in qk):
            s += 0.45
    reg = item.get("region")
    if reg and reg.get("label"):
        nl = norm(reg["label"])
        if nl and nl in nq:
            s += 0.28
    return s


def best(q, case_id, items):
    pool = [it for it in items if it.get("case_id") is None or it["case_id"] == case_id]
    top, ts = None, 0.0
    for it in pool:
        s = score_of(q, it)
        if s > ts:
            ts, top = s, it
    return top, ts


def classify(q, case_id, items):
    top, ts = best(q, case_id, items)
    if top is None:
        return "unknown", ts, top
    if not top["answerable"]:
        return ("refusal" if ts >= THR_REFUSE else "unknown"), ts, top
    if ts < THR_ANSWER:
        return "unknown", ts, top
    return top["kind"], ts, top


def main() -> None:
    bank = json.loads(BANK.read_text(encoding="utf8"))
    items = bank["items"]
    ev = json.loads(EVAL.read_text(encoding="utf8"))
    case_id = ev["case"]
    rng = random.Random(SEED)

    # ---- 1. 检索准确率（kind 级，允许多个可接受答案） ----
    def run_set(rows):
        groups = defaultdict(lambda: {"n": 0, "ok": 0})
        fails = []
        for v in rows:
            got, ts, top = classify(v["q"], case_id, items)
            ok = got in v["accept"]
            # 可选：校验命中的分区，防止「左肺中野」被解析成右中/中。
            want_zone = v.get("expect_zone")
            got_zone = ((top or {}).get("region") or {}).get("zone_id")
            if ok and want_zone and got_zone != want_zone:
                ok = False
            g = groups[v["accept"][0]]
            g["n"] += 1
            if ok:
                g["ok"] += 1
            else:
                fails.append({
                    "q": v["q"], "expect": v["accept"], "got": got,
                    "expect_zone": want_zone, "got_zone": got_zone,
                    "score": round(ts, 3),
                    "matched": (top or {}).get("question", ""),
                    "matched_kind": (top or {}).get("kind", ""),
                    "note": v.get("note", ""),
                })
        n = sum(g["n"] for g in groups.values())
        ok = sum(g["ok"] for g in groups.values())
        return {
            "n": n, "ok": ok,
            "accuracy": round(ok / n, 3) if n else None,
            "by_group": {k: {"n": v["n"], "ok": v["ok"],
                             "acc": round(v["ok"] / v["n"], 3) if v["n"] else None}
                         for k, v in sorted(groups.items())},
            "failures": fails,
        }

    dev = run_set(ev["variants"])
    holdout = run_set(ev.get("holdout", [])) if ev.get("holdout") else None
    final = run_set(ev.get("final", [])) if ev.get("final") else None
    failures = dev["failures"]

    # ---- 2. 拒答混淆矩阵 ----
    refuse_data = json.loads(REFUSALS.read_text(encoding="utf8"))
    pos_qs = [r["question"] for r in refuse_data["items"]]
    # 变体里只接受 refusal 的问法，也算该拒
    pos_qs += [v["q"] for v in ev["variants"] if v["accept"] == ["refusal"]]

    answerable = [it for it in items if it["answerable"]]
    # 负样本：每个病例抽 2 条标准问法，固定 seed，可复现
    by_case = defaultdict(list)
    for it in answerable:
        by_case[it["case_id"]].append(it)
    neg = []
    for cid in sorted(by_case):
        pool = by_case[cid]
        rng.shuffle(pool)
        neg.extend(pool[:2])
    neg = neg[:60]

    tp = fn = 0
    for q in pos_qs:
        got, _, _ = classify(q, case_id, items)
        if got == "refusal":
            tp += 1
        else:
            fn += 1

    fp = tn = 0
    for it in neg:
        got, _, _ = classify(it["question"], it["case_id"], items)
        if got == "refusal":
            fp += 1
        else:
            tn += 1

    recall = tp / (tp + fn) if (tp + fn) else 0.0
    miss_rate = fn / (tp + fn) if (tp + fn) else 0.0
    false_refusal = fp / (fp + tn) if (fp + tn) else 0.0

    # ---- 3. 模型一致性（用已有探针结果） ----
    model = {"available": False}
    if MODEL.exists():
        mp = json.loads(MODEL.read_text(encoding="utf8"))
        s = mp.get("summary") or {}
        # 主口径只统计 eligible（排除侧位/解剖标注图）；旧数据没有该字段时回退到全量。
        n = s.get("eligible") or s.get("cases", 0)
        agree = s.get("consistent", 0)
        partial = s.get("partial", 0)
        model = {
            "available": True,
            "method": mp.get("method", ""),
            "cases": s.get("cases", 0),
            "eligible": n,
            "excluded": s.get("excluded", 0),
            "consistent": agree,
            "conflict": s.get("conflict", 0),
            "partial": partial,
            "silent": s.get("silent", 0),
            "strict_rate": s.get("strict_rate") if s.get("strict_rate") is not None else (round(agree / n, 3) if n else None),
            "weighted_rate": s.get("weighted_rate") if s.get("weighted_rate") is not None else (round((agree + 0.5 * partial) / n, 3) if n else None),
            "threshold": s.get("threshold"),
            "thresholds": s.get("thresholds") or {},
            "note": s.get("note", ""),
        }

    report = {
        "version": "0.1.0",
        "notice": "评测集与库内标准问法措辞不同；指标用于说明边界，不是对外承诺。",
        "retrieval": {
            "case": case_id,
            "dev": {k: dev[k] for k in ("n", "ok", "accuracy", "by_group", "failures")},
            "holdout": {k: holdout[k] for k in ("n", "ok", "accuracy", "by_group", "failures")} if holdout else None,
            "final": {k: final[k] for k in ("n", "ok", "accuracy", "by_group", "failures")} if final else None,
            "note": "dev 集用于调参；holdout 未参与调参，是泛化指标。",
        },
        "refusal": {
            "positives": tp + fn,
            "negatives": fp + tn,
            "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "recall": round(recall, 3),
            "miss_rate": round(miss_rate, 3),
            "false_refusal_rate": round(false_refusal, 3),
            "note": "负样本用的是库内标准问法，因此误拒率偏保守（偏低）。漏拒率才是关键指标。",
        },
        "model": model,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print("wrote", OUT)
    print(json.dumps({
        "dev": report["retrieval"]["dev"]["accuracy"],
        "holdout": (report["retrieval"]["holdout"] or {}).get("accuracy"),
        "final": (report["retrieval"]["final"] or {}).get("accuracy"),
        "dev_by_group": report["retrieval"]["dev"]["by_group"],
        "holdout_by_group": (report["retrieval"]["holdout"] or {}).get("by_group"),
        "refusal": {k: report["refusal"][k] for k in ("tp", "fn", "fp", "tn", "recall", "miss_rate", "false_refusal_rate")},
        "model": model,
    }, ensure_ascii=False, indent=2))
    for label in ("dev", "holdout", "final"):
        blk = report["retrieval"].get(label)
        if blk and blk["failures"]:
            print(f"\n[{label}] 未通过 {len(blk['failures'])} 条:")
            for f in blk["failures"]:
                print(f"  {f['q']}  期望 {f['expect']} 实得 {f['got']} ({f['score']}) 命中: {f['matched'][:26]}")


if __name__ == "__main__":
    main()
