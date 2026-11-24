"""生成「报告—指南」双源对照数据。

做三件事：
1. 把每例的逐区描述拼成一份「报告」
2. 按主题匹配到指南要点
3. 逐条核查：指南要求报告写清的要素，报告是否真的写了

产物：kb/data/dual_source.json

注意：指南侧是转述摘要，不是逐字引用；报告侧是库内逐区标注拼合。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHEST = ROOT / "kb/data/chest_reading.json"
GUIDE = ROOT / "kb/data/guideline_digest.json"
OUT = ROOT / "kb/data/dual_source.json"


def pick_topic(title: str, zones, topics):
    """按标题优先、分区文本兜底来匹配主题。"""
    best, best_score = None, 0
    for t in topics:
        hits = sum(1 for k in t["match_keywords"] if k in title)
        if hits > best_score:
            best, best_score = t, hits
    if best:
        return best
    # 标题太泛时，只看「异常分区」的描述，避免被正常区的措辞带偏
    blob = " ".join(
        (z.get("text") or "") for z in zones if z.get("status") == "abnormal"
    )
    for t in topics:
        hits = sum(1 for k in t["match_keywords"] if k in blob)
        if hits > best_score:
            best, best_score = t, hits
    return best


def check_elements(report_text: str, elements):
    out = []
    for e in elements:
        hit = [k for k in e["keywords"] if k in report_text]
        out.append(
            {
                "label": e["label"],
                "covered": bool(hit),
                "matched": hit[:3],
            }
        )
    return out


def main() -> None:
    chest = json.loads(CHEST.read_text(encoding="utf8"))
    guide = json.loads(GUIDE.read_text(encoding="utf8"))
    topics = guide["topics"]

    cases = []
    for c in chest["cases"]:
        if c.get("enabled") is False:
            continue
        zones = c.get("zones") or []
        report_parts = []
        zlist = []
        for z in zones:
            if z.get("status") == "abnormal" and (z.get("text") or "").strip():
                report_parts.append(z["text"])
                zlist.append({"id": z["id"], "name": z["name"], "text": z["text"]})
        report_text = " ".join([c.get("title", "")] + report_parts)

        topic = pick_topic(c.get("title", ""), zones, topics)

        item = {
            "case_id": c["id"],
            "title": c.get("title", ""),
            "image": c.get("image", ""),
            "topic_id": topic["topic_id"] if topic else "UNMAPPED",
            "topic_cn": topic["topic_cn"] if topic else "未覆盖主题",
            "report": {"text": report_text.strip(), "zones": zlist},
            "guideline": (
                {
                    "sources": topic["sources"],
                    "key_points": topic["key_points"],
                    "required_count": len(topic["required_elements"]),
                }
                if topic
                else {"sources": [], "key_points": [], "required_count": 0}
            ),
            "elements": [],
            "coverage": None,
            "missing": [],
            "report_available": len(zlist) > 0,
        }

        if topic:
            elems = check_elements(report_text, topic["required_elements"])
            covered = sum(1 for e in elems if e["covered"])
            item["elements"] = elems
            # 没有逐区异常描述时不做要素核查，避免把「简注」当成「完整报告」打分
            if zlist:
                item["coverage"] = round(covered / len(elems), 3)
                item["missing"] = [e["label"] for e in elems if not e["covered"]]

        cases.append(item)

    mapped = [c for c in cases if c["topic_id"] != "UNMAPPED"]
    covs = [c["coverage"] for c in mapped if c["coverage"] is not None]
    avg = round(sum(covs) / len(covs), 3) if covs else 0

    out = {
        "version": "0.1.0",
        "notice": guide["notice"],
        "cases": cases,
        "summary": {
            "cases": len(cases),
            "mapped": len(mapped),
            "unmapped": len(cases) - len(mapped),
            "avg_coverage": avg,
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    print("wrote", OUT)
    print(out["summary"])
    for c in cases:
        if c["topic_id"] == "UNMAPPED":
            print("  %s  %-18s UNMAPPED" % (c["case_id"], c["title"][:16]))
        elif c["coverage"] is None:
            print(
                "  %s  %-18s %-12s 无异常描述，不做要素核查"
                % (c["case_id"], c["title"][:16], c["topic_id"])
            )
        else:
            print(
                "  %s  %-18s %-6s coverage=%.2f missing=%s"
                % (c["case_id"], c["title"][:16], c["topic_id"], c["coverage"], ",".join(c["missing"])[:40])
            )


if __name__ == "__main__":
    main()
