#!/usr/bin/env python3
"""从逐病例标注聚合出「通用分区模板」。

陌生影像没有人工标注的 coords，`RegionKB.locate()` 会返回 no_atlas。
这里把同一 atlas 下同名分区的坐标取中位数，得到一套与具体病例无关的
模板几何，供陌生影像做「模板推断」。

诚实边界：
- 模板只描述「这个位置通常属于哪个分区」，不代表该病例已被人工标注；
- PA 胸片的模板带 sd（病例间构图差异），其余 atlas 的 sd 为 0；
- 输出必须带 source=atlas_template，前端不得显示成人工标注。

    python3 kb/scripts/build_atlas_templates.py
"""
import collections
import json
import statistics
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
DATA = KB / "data"
OUT = DATA / "atlas_templates.json"

# atlas_id 里没有结构化的投照位。先走显式映射，再按 token 兜底推断。
VIEW = {
    "ATLAS-CHEST-PA-6": "PA",
    "ATLAS-CHEST-LAT-6": "LAT",
    "ATLAS-CHEST-CT-5": "CT-AXIAL",
    "ATLAS-CHEST-CT-LOCAL": "CT-LOCAL",
    "ATLAS-HEAD-MR-LOCAL": "MR-LOCAL",
    "ATLAS-BREAST-MLO-4": "MLO",
    "ATLAS-BREAST-MLO-LOCAL": "MLO-LOCAL",
    "ATLAS-US-LOCAL": "US",
    "ATLAS-ABD-CT-LOCAL": "CT-LOCAL",
}

_TOKEN_VIEW = (
    ("-CT-LOCAL", "CT-LOCAL"), ("-MR-LOCAL", "MR-LOCAL"), ("-US-LOCAL", "US-LOCAL"),
    ("-CT-", "CT-AXIAL"), ("-MR-", "MR"), ("-US-", "US"),
    ("-MLO-", "MLO"), ("-PA-", "PA"), ("-LAT-", "LAT"), ("-AP-", "AP"),
    ("-SAG", "SAG"),
)


def infer_view(atlas_id):
    if atlas_id in VIEW:
        return VIEW[atlas_id]
    for token, view in _TOKEN_VIEW:
        if token in atlas_id:
            return view
    return ""


def read_jsonl(name):
    p = DATA / name
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf8").splitlines()
            if line.strip()]


def clean_modality(value):
    """atlases.jsonl 里有 ["CR", "['CR']"] 这种脏数据，统一成字符串列表。"""
    out = []
    for v in value or []:
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("[") and s.endswith("]"):
                try:
                    inner = json.loads(s.replace("'", '"'))
                    for x in inner:
                        if x not in out:
                            out.append(x)
                    continue
                except Exception:
                    pass
            if s and s not in out:
                out.append(s)
    return out


def median_coords(rows):
    return [round(statistics.median([r["coords"][i] for r in rows]), 4) for i in range(4)]


def stdev_coords(rows):
    if len(rows) < 2:
        return [0.0, 0.0, 0.0, 0.0]
    return [round(statistics.pstdev([r["coords"][i] for r in rows]), 4) for i in range(4)]


def main():
    atlases = {a["id"]: a for a in read_jsonl("atlases.jsonl")}
    regions = [r for r in read_jsonl("regions.jsonl")
               if r.get("status") == "active" and len(r.get("coords") or []) == 4]

    grouped = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in regions:
        grouped[r["atlas_id"]][r["name"]].append(r)

    out = {
        "version": "2026-11-19",
        "source": "kb/data/regions.jsonl",
        "method": "同 atlas 同名分区坐标取中位数；sd 为病例间标准差",
        "note": "模板推断，不是人工标注。陌生影像使用本模板时必须标注 source=atlas_template。",
        "atlases": {},
    }

    for atlas_id, names in sorted(grouped.items()):
        meta = atlases.get(atlas_id, {})
        case_ids = {r["image_id"] for rows in names.values() for r in rows}
        tmpl_regions = []
        for name, rows in sorted(names.items(), key=lambda kv: -len(kv[1])):
            sample = rows[0]
            tmpl_regions.append({
                "name": name,
                "name_en": sample.get("name_en") or "",
                "coords": median_coords(rows),
                "sd": stdev_coords(rows),
                "n": len(rows),
                "level": sample.get("level"),
                "parent_region_id": sample.get("parent_region_id"),
                "patient_side": sample.get("patient_side"),
                "image_side": sample.get("image_side"),
                "note": sample.get("note") or "",
                "sign_ids": sorted({s for r in rows for s in (r.get("sign_ids") or [])}),
            })
        out["atlases"][atlas_id] = {
            "id": atlas_id,
            "name": meta.get("name") or atlas_id,
            "modality": clean_modality(meta.get("modality")),
            "body_part": meta.get("body_part") or "",
            "view": infer_view(atlas_id),
            "laterality_rule": meta.get("laterality_rule") or "",
            "note": meta.get("note") or "",
            "n_cases": len(case_ids),
            "n_regions": sum(len(v) for v in names.values()),
            "regions": tmpl_regions,
        }

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf8")
    print("wrote", OUT)
    for aid, a in out["atlases"].items():
        print("  %-28s %-10s %2d regions  %2d cases" %
              (aid, a["view"] or "-", len(a["regions"]), a["n_cases"]))


if __name__ == "__main__":
    main()
