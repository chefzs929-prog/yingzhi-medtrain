"""生成前端「今日查房」所需的最小数据集。

只保留条款与描述逐字对应（relevance_score >= 2）的条目及其对照条目，
体积约 30KB，足以让页面在任何时间、任何设备上确定性算出当天内容。

用法：python3 kb/scripts/build_daily_src.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BANK = ROOT / "kb/data/ask_bank.json"
READING = ROOT / "kb/data/chest_reading.json"
OUT = ROOT / "kb/data/daily_src.json"

CONFUSION = {
    "PNEUMONIA": "EFFUSION",
    "EFFUSION": "PNEUMONIA",
    "NODULE": "TB",
    "TB": "NODULE",
    "PNEUMOTHORAX": "EFFUSION",
    "CARDIOMEGALY": "EFFUSION",
}
TOPIC_CN = {
    "PNEUMONIA": "肺炎 / 肺实变",
    "NODULE": "肺结节 / 粟粒样结节",
    "EFFUSION": "胸腔积液",
    "PNEUMOTHORAX": "气胸",
    "CARDIOMEGALY": "心影增大",
    "TB": "肺结核",
}
TOPIC_ORDER = ["PNEUMONIA", "EFFUSION", "NODULE", "PNEUMOTHORAX", "CARDIOMEGALY", "TB"]


def _rel(it: dict) -> int:
    return (it.get("citation") or {}).get("relevance_score", 0)


def slim(it: dict, main: bool = True) -> dict:
    region = it.get("region") or {}
    return {
        "qid": it["qid"],
        "main": main,
        "case_id": it["case_id"],
        "topic_id": it.get("topic_id"),
        "answer": it.get("answer"),
        "zone": region.get("label"),
        "zone_id": region.get("zone_id"),
        "coords": region.get("coords"),
        "status": region.get("status"),
        "citation": {
            "cite_id": (it.get("citation") or {}).get("kp_id") or (it.get("citation") or {}).get("cite_id"),
            "quote": (it.get("citation") or {}).get("quote"),
            "offset": (it.get("citation") or {}).get("offset"),
            "sha1": ((it.get("citation") or {}).get("sha1") or "")[:8],
            "relevance_score": _rel(it),
        },
    }


def main() -> None:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    abnormal = [
        i for i in bank["items"]
        if i.get("answerable") and (i.get("region") or {}).get("status") == "abnormal"
    ]
    pool = [i for i in abnormal if _rel(i) >= 2]
    if not pool:
        pool = [i for i in abnormal if _rel(i) >= 1]

    main_qids = {it["qid"] for it in pool}
    keep: dict[str, dict] = {}
    for it in pool:
        keep[it["qid"]] = it
    # 对照条目也带上，保证前端算得出的和大家看到的一致
    for topic in {i["topic_id"] for i in pool}:
        ct = CONFUSION.get(topic)
        for it in abnormal:
            if it.get("topic_id") == ct and it.get("citation"):
                keep.setdefault(it["qid"], it)

    reading = json.loads(READING.read_text(encoding="utf-8"))
    cases = {}
    for c in (reading.get("cases") or []):
        cid = c.get("id") or c.get("case_id")
        if cid:
            cases[cid] = {"title": c.get("title") or c.get("name") or cid, "image": c.get("image")}

    # 主池主题（不含只作为对照出现的主题），决定轮转顺序
    main_topics = [t for t in TOPIC_ORDER if any(i["topic_id"] == t for i in pool)]
    data = {
        "epoch": "2026-11-24",
        "topics": main_topics,
        "topic_order": TOPIC_ORDER,
        "confusion": CONFUSION,
        "topic_cn": TOPIC_CN,
        "cases": cases,
        "items": [slim(keep[k], k in main_qids) for k in sorted(keep, key=lambda q: int(q[1:]))],
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}  {len(data['items'])} 条  {OUT.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
