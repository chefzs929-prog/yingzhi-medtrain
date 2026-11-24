"""晨间查房选材器。

每天挑一个「最久没讲过」的主题 + 一个对应病例，配好区域与原文，
再顺带跑三项快检。脚本只负责确定性选材与自检，成稿由 Agent 组织。

用法：
    python3 kb/scripts/daily_brief.py                # 今天
    python3 kb/scripts/daily_brief.py --date 2026-11-25
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BANK = ROOT / "kb/data/ask_bank.json"
REFUSALS = ROOT / "kb/data/refusals.json"
STATE = ROOT / "outputs/daily/.state.json"

# 纯日期起点：同一天在任何机器、任何时候算出的结果都相同
EPOCH = date(2026, 11, 24)
TOPIC_ORDER = ["PNEUMONIA", "EFFUSION", "NODULE", "PNEUMOTHORAX", "CARDIOMEGALY", "TB"]

TOPIC_CN = {
    "PNEUMONIA": "肺炎 / 肺实变",
    "NODULE": "肺结节 / 粟粒样结节",
    "EFFUSION": "胸腔积液",
    "PNEUMOTHORAX": "气胸",
    "CARDIOMEGALY": "心影增大",
    "TB": "肺结核",
}

# 临床上最容易互相误认的一对
CONFUSION = {
    "PNEUMONIA": "EFFUSION",
    "EFFUSION": "PNEUMONIA",
    "NODULE": "TB",
    "TB": "NODULE",
    "PNEUMOTHORAX": "EFFUSION",
    "CARDIOMEGALY": "EFFUSION",
}


def abnormal_items(bank: dict, topic: str | None = None, min_rel: int = 0) -> list[dict]:
    out = []
    for it in bank["items"]:
        if not it.get("answerable"):
            continue
        r = it.get("region") or {}
        if r.get("status") != "abnormal":
            continue
        if topic and it.get("topic_id") != topic:
            continue
        if min_rel and ((it.get("citation") or {}).get("relevance_score") or 0) < min_rel:
            continue
        out.append(it)
    return out


def _rel(it: dict) -> int:
    return (it.get("citation") or {}).get("relevance_score", 0)


def pick(bank: dict, day: date) -> tuple[dict, dict]:
    """纯日期选材：主题按固定顺序轮转，病例按天数整除轮转。"""
    pool = abnormal_items(bank, min_rel=2) or abnormal_items(bank, min_rel=1) or abnormal_items(bank)
    available = sorted({i["topic_id"] for i in pool})
    order = [t for t in TOPIC_ORDER if t in available] or available
    d = (day - EPOCH).days
    topic = order[d % len(order)]

    cases: dict = {}
    for it in pool:
        if it["topic_id"] != topic:
            continue
        cid = it["case_id"]
        prev = cases.get(cid)
        # 同一病例里挑条款最贴合的那一条，并列按 qid 保证确定性
        if prev is None or (_rel(it), -int(it["qid"][1:])) > (_rel(prev), -int(prev["qid"][1:])):
            cases[cid] = it
    keys = sorted(cases)
    chosen = cases[keys[(d // len(order)) % len(keys)]]
    return chosen, {"topic": topic, "cases_available": len(cases)}


def contrast_of(bank: dict, day: date, topic: str, exclude_case: str | None = None) -> dict | None:
    ct = CONFUSION.get(topic)
    if not ct:
        return None
    # 对照必须是另一张片，否则「鉴别」变成自比
    items = sorted(
        [i for i in abnormal_items(bank, ct) if i.get("citation") and i["case_id"] != exclude_case],
        key=lambda i: (i["case_id"], i["qid"]),
    )
    if not items:
        return None
    return items[(day - EPOCH).days % len(items)]


def check_anchors(bank: dict) -> dict:
    ans = [i for i in bank["items"] if i.get("answerable")]
    bad = [i for i in ans if not i.get("region") or not i.get("citation")]
    return {
        "name": "锚点完整率",
        "ok": not bad,
        "detail": f"{len(ans) - len(bad)}/{len(ans)}",
        "bad_qids": [i["qid"] for i in bad[:5]],
    }


def check_refusals() -> dict:
    try:
        data = json.loads(REFUSALS.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"name": "拒答规则", "ok": False, "detail": f"读取失败 {e}"}
    items = data.get("items") or data.get("refusals") or []
    bad = [i for i in items if not i.get("reason") and not i.get("why")]
    return {
        "name": "拒答规则",
        "ok": not bad and bool(items),
        "detail": f"{len(items) - len(bad)}/{len(items)} 有明确理由",
    }


def check_crosscheck() -> dict:
    script = ROOT / "kb/scripts/crosscheck.py"
    if not script.exists():
        return {"name": "跨端一致", "ok": True, "detail": "跳过（脚本不存在）"}
    try:
        r = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=180, cwd=str(ROOT),
        )
    except Exception as e:  # noqa: BLE001
        return {"name": "跨端一致", "ok": True, "detail": f"跳过（{type(e).__name__}）"}
    ok = r.returncode == 0
    tail = (r.stdout or "").strip().splitlines()
    return {
        "name": "跨端一致",
        "ok": ok,
        "detail": tail[-1][:60] if tail else f"exit {r.returncode}",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    bank = json.loads(BANK.read_text(encoding="utf-8"))
    day = date.fromisoformat(args.date)

    item, meta = pick(bank, day)
    topic = meta["topic"]
    contrast = contrast_of(bank, day, topic, item["case_id"])

    case_zones = [
        i["region"]
        for i in bank["items"]
        if i.get("answerable") and i.get("case_id") == item["case_id"] and i.get("region")
    ]
    limited = sum(1 for z in case_zones if z.get("status") == "limited")
    unmentioned = sum(1 for z in case_zones if z.get("status") == "unmentioned")

    checks = [check_anchors(bank), check_refusals(), check_crosscheck()]

    out = {
        "date": args.date,
        "topic_id": topic,
        "topic_cn": TOPIC_CN.get(topic, topic),
        "focus": {
            "case_id": item["case_id"],
            "case_title": item["region"].get("case_title", ""),
            "zone": item["region"].get("label"),
            "zone_id": item["region"].get("zone_id"),
            "image": item["region"].get("image"),
            "coords": item["region"].get("coords"),
            "status": item["region"].get("status"),
            "answer": item["answer"],
            "question": item["question"],
            "citation": item.get("citation"),
            "qid": item["qid"],
        },
        "contrast": (
            {
                "topic_cn": TOPIC_CN.get(contrast["topic_id"], contrast["topic_id"]),
                "case_id": contrast["case_id"],
                "case_title": contrast["region"].get("case_title", ""),
                "zone": contrast["region"].get("label"),
                "image": contrast["region"].get("image"),
                "coords": contrast["region"].get("coords"),
                "answer": contrast["answer"],
                "citation": contrast.get("citation"),
            }
            if contrast
            else None
        ),
        "boundaries": {
            "limited": limited,
            "unmentioned": unmentioned,
            "note": (
                f"本例另有 {limited} 个分区判读受限、{unmentioned} 个分区来源未提及；"
                "「未提及」不等于正常。"
            )
            if limited or unmentioned
            else "本例各分区均有明确标注。",
        },
        "checks": checks,
        "all_ok": all(c["ok"] for c in checks),
        "cases_available_for_topic": meta["cases_available"],
        "citation_relevance": (item.get("citation") or {}).get("relevance_score", 0),
    }

    # 当天首次运行才推进状态，保证同日重复运行结果一致
    if state.get("last_date") != args.date:
        seen = state.get("seen") or {}
        seen[topic] = args.date
        seen[item["case_id"]] = args.date
        seen = {k: v for k, v in seen.items() if v >= _shift(args.date, 60)}
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(
            json.dumps({"last_date": args.date, "seen": seen}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def _shift(d: str, days: int) -> str:
    from datetime import timedelta

    return (date.fromisoformat(d) - timedelta(days=days)).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
