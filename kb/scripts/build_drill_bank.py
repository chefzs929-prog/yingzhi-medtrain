"""从库内标注自动生成练习题库（可追溯、可复现）。

三类题型，全部由真实标注生成，不靠模型编：
1. localize  定位题：这张片上哪一区被标注为异常
2. state     判读题：某分区的标注状态是什么（重点考「未提及 ≠ 正常」）
3. report    报告要素题：这份报告缺少指南要求的哪一项

每道题都带：
- kp       知识点标识，用于错题归因与自适应调度
- explain  讲解
- source   出处（病例 / 分区 / 依据）

产物：kb/data/drill_bank.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHEST = ROOT / "kb/data/chest_reading.json"
DUAL = ROOT / "kb/data/dual_source.json"
OUT = ROOT / "kb/data/drill_bank.json"

STATES = ["abnormal", "normal", "unmentioned", "limited"]
STATE_CN = {"abnormal": "异常", "normal": "未见异常", "unmentioned": "未提及", "limited": "判读受限"}

SEED = 20261124


def build_localize_normal(case, rng):
    """正常例也能出定位题：正确项是「未见明确异常分区」，避免 9/21 例没有定位题。"""
    zones = case.get("zones") or []
    if len(zones) < 3:
        return None
    pool = list(zones)
    rng.shuffle(pool)
    opts = [{"name": "未见明确异常分区", "id": "NONE"}] + pool[:3]
    rng.shuffle(opts)
    keys = "ABCD"
    options = []
    answer = None
    for i, z in enumerate(opts):
        options.append({"key": keys[i], "text": z["name"]})
        if z["id"] == "NONE":
            answer = keys[i]
    topic = case.get("topic_id", "")
    return {
        "type": "localize",
        "case_id": case["id"],
        "title": case.get("title", ""),
        "image": case.get("image", ""),
        "kp": f"KP-LOC-{topic or 'GEN'}",
        "kp_cn": f"{topic or '通用'} · 分区定位",
        "stem": "这张片子上，哪一区被标注为异常？",
        "options": options,
        "answer": answer,
        "explain": "本片所有教学分区均标注为未见明确异常，没有异常分区。",
        "source": f"{case['id']} · 全部分区 · 库内标注",
    }


def build_localize(case, rng):
    ab = [z for z in case["zones"] if z["status"] == "abnormal"]
    if not ab:
        return build_localize_normal(case, rng)
    correct = ab[0]
    pool = [z for z in case["zones"] if z["id"] != correct["id"]]
    # 干扰项优先选「未提及 / 未见异常」，比选另一处异常更有区分度
    pool.sort(key=lambda z: 0 if z["status"] in ("unmentioned", "normal") else 1)
    distractors = pool[:3]
    # 侧位片只有 3 个分区（ANT/MID/POST），用「未见明确异常分区」补足第 4 个选项。
    if len(distractors) < 3:
        distractors = distractors + [{"id": "NONE", "name": "未见明确异常分区"}]
    opts = [correct] + distractors
    rng.shuffle(opts)
    keys = "ABCD"
    options = []
    answer = None
    for i, z in enumerate(opts):
        options.append({"key": keys[i], "text": z["name"]})
        if z["id"] == correct["id"]:
            answer = keys[i]
    topic = case.get("topic_id", "")
    return {
        "type": "localize",
        "case_id": case["id"],
        "title": case.get("title", ""),
        "image": case.get("image", ""),
        "kp": f"KP-LOC-{topic or 'GEN'}",
        "kp_cn": f"{topic or '通用'} · 分区定位",
        "stem": "这张片子上，哪一区被标注为异常？",
        "options": options,
        "answer": answer,
        "explain": f"{correct['name']}标注为异常：{correct.get('text') or '（无文本）'}",
        "source": f"{case['id']} · {correct['id']} · {correct.get('basis') or '库内标注'}",
    }


def build_state(case, rng):
    # 优先考最容易混淆的两类
    cand = [z for z in case["zones"] if z["status"] in ("unmentioned", "limited")]
    if not cand:
        cand = case["zones"]
    if not cand:
        return None
    z = rng.choice(cand)
    keys = "ABCD"
    opts = STATES[:]
    rng.shuffle(opts)
    options = [{"key": keys[i], "text": STATE_CN[s]} for i, s in enumerate(opts)]
    answer = keys[opts.index(z["status"])]
    if z["status"] == "unmentioned":
        explain = "来源没有描述这一区，属于「未提及」。未提及不等于正常，不能当作阴性结论。"
    elif z["status"] == "limited":
        explain = "图像质量或体位不允许判读，属于「判读受限」。"
    elif z["status"] == "normal":
        explain = "来源明确写了该区正常，属于「未见异常」。"
    else:
        explain = f"该区有明确异常描述：{z.get('text') or ''}"
    return {
        "type": "state",
        "case_id": case["id"],
        "title": case.get("title", ""),
        "image": case.get("image", ""),
        "kp": f"KP-STATE-{z['status'].upper()}",
        "kp_cn": f"状态判读 · {STATE_CN[z['status']]}",
        "stem": f"{z['name']}（{z['id']}）的标注状态是？",
        "options": options,
        "answer": answer,
        "explain": explain,
        "source": f"{case['id']} · {z['id']} · {z.get('basis') or '库内标注'}",
    }


def build_report(dual_case, rng):
    if dual_case.get("topic_id") == "UNMAPPED" or not dual_case.get("report_available"):
        return None
    elems = dual_case.get("elements") or []
    missing = [e for e in elems if not e["covered"]]
    covered = [e for e in elems if e["covered"]]
    if not missing or len(covered) < 2:
        return None
    correct = missing[0]
    picks = rng.sample(covered, 3) if len(covered) >= 3 else list(covered)
    keys = "ABCD"
    opts = [correct] + picks
    rng.shuffle(opts)
    options = []
    answer = None
    for i, e in enumerate(opts):
        options.append({"key": keys[i], "text": e["label"]})
        if e["label"] == correct["label"]:
            answer = keys[i]
    return {
        "type": "report",
        "case_id": dual_case["case_id"],
        "title": dual_case.get("title", ""),
        "image": dual_case.get("image", ""),
        "kp": f"KP-REPORT-{dual_case['topic_id']}",
        "kp_cn": f"报告要素 · {dual_case.get('topic_cn','')}",
        "stem": "指南要求这份报告写清若干要素，下列哪一项是报告里没有写到的？",
        "options": options,
        "answer": answer,
        "explain": f"缺少「{correct['label']}」。指南要求报告写明该要素，但本报告的逐区描述中未出现对应表述。",
        "source": f"{dual_case['case_id']} · 指南主题 {dual_case['topic_id']}",
    }


def main() -> None:
    rng = random.Random(SEED)
    chest = json.loads(CHEST.read_text(encoding="utf8"))
    dual = json.loads(DUAL.read_text(encoding="utf8")) if DUAL.exists() else {"cases": []}
    dual_map = {c["case_id"]: c for c in dual.get("cases", [])}

    questions = []
    for case in chest["cases"]:
        if case.get("enabled") is False:
            continue
        c = dict(case)
        c["topic_id"] = dual_map.get(case["id"], {}).get("topic_id", "")

        q = build_localize(c, rng)
        if q:
            questions.append(q)
        q = build_state(c, rng)
        if q:
            questions.append(q)

    for dc in dual.get("cases", []):
        q = build_report(dc, rng)
        if q:
            questions.append(q)

    for i, q in enumerate(questions, 1):
        q["qid"] = f"Q{i:04d}"

    # 知识点汇总，供前端做掌握度
    kps = {}
    for q in questions:
        kps.setdefault(q["kp"], {"kp": q["kp"], "kp_cn": q["kp_cn"], "count": 0})
        kps[q["kp"]]["count"] += 1

    out = {
        "version": "0.1.0",
        "seed": SEED,
        "notice": "题目由库内逐区标注自动生成，答案可追溯到具体病例与分区；不是模型出题。",
        "questions": questions,
        "kps": sorted(kps.values(), key=lambda x: x["kp"]),
        "summary": {
            "questions": len(questions),
            "localize": sum(1 for q in questions if q["type"] == "localize"),
            "state": sum(1 for q in questions if q["type"] == "state"),
            "report": sum(1 for q in questions if q["type"] == "report"),
            "kps": len(kps),
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    print("wrote", OUT)
    print(out["summary"])
    for k in out["kps"]:
        print("  %-26s %-22s %d" % (k["kp"], k["kp_cn"], k["count"]))


if __name__ == "__main__":
    main()
