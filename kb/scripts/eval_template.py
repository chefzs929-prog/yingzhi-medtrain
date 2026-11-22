#!/usr/bin/env python3
"""留一法评测：用「其他病例」的模板，定位「当前病例」的人工标注分区。

这不是端到端读片准确率，只回答一个问题：
当陌生影像只有模板、没有该病例标注时，模板几何能不能把它指到正确分区。

    python3 kb/scripts/eval_template.py
    python3 kb/scripts/eval_template.py --json .deepworks/tmp/eval_template.json
"""
import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB.parent / "yingzhi" / "serve"))
sys.path.insert(0, str(KB / "scripts"))

import atlas  # noqa: E402


def read_jsonl(name):
    p = KB / "data" / name
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf8").splitlines()
            if line.strip()]


def aggregate(rows):
    """与 build_atlas_templates 相同的聚合口径：中位数 + 标准差。"""
    out = []
    for name, group in sorted(collections.defaultdict(list, {
            n: [r for r in rows if r["name"] == n] for n in {r["name"] for r in rows}
    }).items()):
        if not group:
            continue
        coords = [round(statistics.median([r["coords"][i] for r in group]), 4) for i in range(4)]
        sd = ([round(statistics.pstdev([r["coords"][i] for r in group]), 4) for i in range(4)]
              if len(group) > 1 else [0.0, 0.0, 0.0, 0.0])
        sample = group[0]
        out.append({
            "name": name,
            "name_en": sample.get("name_en") or "",
            "coords": coords,
            "sd": sd,
            "n": len(group),
            "level": sample.get("level"),
            "parent_region_id": sample.get("parent_region_id"),
            "patient_side": sample.get("patient_side"),
            "image_side": sample.get("image_side"),
            "note": sample.get("note") or "",
            "sign_ids": sorted({s for r in group for s in (r.get("sign_ids") or [])}),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--min-cases", type=int, default=3)
    args = ap.parse_args()

    rows = [r for r in read_jsonl("regions.jsonl")
            if r.get("status") == "active" and len(r.get("coords") or []) == 4]

    by_atlas = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        by_atlas[r["atlas_id"]][r["image_id"]].append(r)

    T = atlas.AtlasTemplates()
    total = collections.Counter()
    per_atlas = []

    for atlas_id, cases in sorted(by_atlas.items()):
        if len(cases) < args.min_cases:
            continue
        stat = collections.Counter()
        for case_id, regs in cases.items():
            others = [r for cid, rs in cases.items() if cid != case_id for r in rs]
            tmpl = aggregate(others)
            T.atlases = {atlas_id: {
                "id": atlas_id, "name": atlas_id, "n_cases": len(cases) - 1,
                "regions": tmpl,
            }}
            for r in regs:
                res = T.locate(atlas_id, r["coords"])
                if res.get("status") == "single":
                    top = (res.get("primary") or {}).get("region") or {}
                    if top.get("name") == r["name"]:
                        stat["hit"] += 1
                    else:
                        stat["wrong"] += 1
                elif res.get("status") == "cross":
                    stat["cross"] += 1
                else:
                    stat["miss"] += 1
        n = sum(stat.values())
        if not n:
            continue
        total.update(stat)
        per_atlas.append({
            "atlas": atlas_id, "cases": len(cases), "n": n,
            "hit": stat["hit"], "wrong": stat["wrong"],
            "cross": stat["cross"], "miss": stat["miss"],
            "hit_rate": round(stat["hit"] / n, 4),
        })

    n = sum(total.values())
    summary = {
        "method": "leave-one-case-out",
        "note": "用其他病例的模板定位当前病例人工框；不是端到端读片准确率",
        "min_cases": args.min_cases,
        "n": n,
        "hit": total["hit"], "wrong": total["wrong"],
        "cross": total["cross"], "miss": total["miss"],
        "hit_rate": round(total["hit"] / n, 4) if n else 0,
        "cross_rate": round(total["cross"] / n, 4) if n else 0,
        "miss_rate": round(total["miss"] / n, 4) if n else 0,
        "per_atlas": per_atlas,
    }

    print("leave-one-case-out  n=%d  hit=%d (%.1f%%)  wrong=%d  cross=%d  miss=%d"
          % (n, total["hit"], 100.0 * total["hit"] / n if n else 0,
             total["wrong"], total["cross"], total["miss"]))
    for a in per_atlas:
        print("  %-28s cases=%-2d n=%-4d hit=%.1f%% cross=%d miss=%d"
              % (a["atlas"], a["cases"], a["n"], a["hit_rate"] * 100, a["cross"], a["miss"]))

    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf8")
        print("wrote", p)


if __name__ == "__main__":
    main()
