"""构建可核对的问答库：从逐区标注 + 指南要点生成问答对，并生成拒答样例。

设计原则：
1. 每个「能答」的问题，答案文本直接来自库内逐区标注（zone.text），不重写、不润色；
2. 每个答案都带出处：影像区域（分区 + 归一化坐标）+ 指南原文（key_point + 字符 offset + sha1）；
3. 每个「不能答」的问题，拒答理由是真实的规则判定，不是演的；
4. 指南原文拼成一份确定语料，offset 与 sha1 可复算。

产物：kb/data/ask_bank.json
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHEST = ROOT / "kb/data/chest_reading.json"
DIGEST = ROOT / "kb/data/guideline_digest.json"
DUAL = ROOT / "kb/data/dual_source.json"
OUT = ROOT / "kb/data/ask_bank.json"

STATE_NOTE = {
    "abnormal": "异常",
    "normal": "未见异常",
    "unmentioned": "未提及",
    "limited": "判读受限",
}


def sha1_of(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def build_corpus(digest):
    """把指南要点拼成一份确定语料，并记录每条的字符区间。"""
    parts = []
    spans = {}
    pos = 0
    for topic in digest["topics"]:
        header = f"【{topic['topic_cn']}】\n"
        parts.append(header)
        pos += len(header)
        for kp in topic["key_points"]:
            line = f"[{kp['id']}] {kp['text']}\n"
            spans[kp["id"]] = {
                "topic_id": topic["topic_id"],
                "topic_cn": topic["topic_cn"],
                "start": pos,
                "end": pos + len(kp["text"]),
                "text": kp["text"],
            }
            parts.append(line)
            pos += len(line)
        parts.append("\n")
        pos += 1
    corpus = "".join(parts)
    return corpus, spans


def cite(spans, kp_id):
    s = spans[kp_id]
    return {
        "kp_id": kp_id,
        "topic_id": s["topic_id"],
        "topic_cn": s["topic_cn"],
        "quote": s["text"],
        "offset": s["start"],
        "sha1": sha1_of(s["text"]),
    }


def pick_kp(topic, sign_ids):
    """按征象匹配挑最相关的一条指南要点，匹配不到就取第一条。"""
    if not topic:
        return None
    kps = topic.get("key_points") or []
    if not kps:
        return None
    # 简单规则：实变/气腔影 → 第 2 条（支气管充气征），否则第 1 条
    if sign_ids and "SIGN-002" in sign_ids and len(kps) >= 2:
        return kps[1]["id"]
    return kps[0]["id"]


def main() -> None:
    chest = json.loads(CHEST.read_text(encoding="utf8"))
    digest = json.loads(DIGEST.read_text(encoding="utf8"))
    dual_raw = json.loads(DUAL.read_text(encoding="utf8")) if DUAL.exists() else {"cases": []}

    corpus, spans = build_corpus(digest)

    topic_by_id = {t["topic_id"]: t for t in digest["topics"]}
    dual_map = {c["case_id"]: c for c in dual_raw.get("cases", [])}

    items = []
    n = 0

    for case in chest["cases"]:
        if case.get("enabled") is False:
            continue
        cid = case["id"]
        topic_id = dual_map.get(cid, {}).get("topic_id", "")
        topic = topic_by_id.get(topic_id)
        zones = case.get("zones") or []
        ab = [z for z in zones if z["status"] == "abnormal"]
        sign_ids = case.get("signs") or []

        # 1) 分区问：每个异常分区一个问题
        for z in ab:
            n += 1
            kp_id = pick_kp(topic, z.get("sign_ids") or sign_ids)
            items.append({
                "qid": f"A{n:04d}",
                "kind": "zone",
                "case_id": cid,
                "topic_id": topic_id,
                "question": f"{z['name']}有什么问题？",
                "keywords": [z["name"], z["id"], (topic or {}).get("topic_cn", ""), "有什么", "问题", "异常"],
                "answerable": True,
                "answer": z["text"],
                "confidence": "high" if case.get("quality") != "limited" else "medium",
                "region": {
                    "zone_id": z["id"],
                    "label": z["name"],
                    "coords": z.get("coords"),
                    "image": case.get("image", ""),
                    "case_id": cid,
                    "case_title": case.get("title", ""),
                    "status": z["status"],
                },
                "citation": cite(spans, kp_id) if kp_id else None,
                "basis": z.get("basis") or "库内逐区标注",
            })

        # 2) 有无问：每个指南主题一个问题
        for tid, t in topic_by_id.items():
            n += 1
            kw = t.get("match_keywords") or []
            tz = [z for z in zones if _zone_hits_topic(z, t)]
            hit = any(z["status"] == "abnormal" for z in tz)
            if tid == "NORMAL":
                q = "这张片子是正常胸片吗？"
                ab_all = [z for z in zones if z["status"] == "abnormal"]
                if ab_all:
                    ans = f"不是。库内逐区标注在{_compact(ab_all)}记录了异常，原文为：{_join_texts(ab_all)}"
                    conf = "high"
                else:
                    ans = "库内逐区标注没有异常分区；但「没有标注异常」不等于影像完全正常，仍以原始报告与临床为准。"
                    conf = "medium"
            else:
                q = f"这张片子有没有{t['topic_cn'].split(' / ')[0]}？"
                if hit:
                    ans = f"有。库内逐区标注在{_compact([z for z in tz if z['status'] == 'abnormal'])}记录了与「{t['topic_cn']}」相符的异常，原文为：{_join_texts(tz)}"
                    conf = "high"
                elif tz and all(z["status"] == "unmentioned" for z in tz):
                    ans = f"不能确认。公开来源没有逐区描述与「{t['topic_cn']}」相关的分区，本工具不作正常或异常的推断。"
                    conf = "low"
                else:
                    ans = f"库内逐区标注中，本片没有「{t['topic_cn']}」的明确描述。这表示来源未写，不等于排除。"
                    conf = "medium"
            kp_id = (t.get("key_points") or [{}])[0].get("id")
            items.append({
                "qid": f"A{n:04d}",
                "kind": "topic",
                "case_id": cid,
                "topic_id": tid,
                "question": q,
                "keywords": [t["topic_cn"], tid] + kw + ["有没有", "吗", "有吗"],
                "answerable": True,
                "answer": ans,
                "confidence": conf,
                "region": _region_of(tz, case),
                "citation": cite(spans, kp_id) if kp_id else None,
                "basis": "库内逐区标注 + 指南要点",
            })

        # 3) 整体问：一例一条
        if ab:
            n += 1
            names = "、".join(z["name"] for z in ab[:3])
            items.append({
                "qid": f"A{n:04d}",
                "kind": "overview",
                "case_id": cid,
                "topic_id": topic_id,
                "question": "这张片子主要异常是什么？",
                "keywords": ["主要异常", "怎么", "整体", "概括", "小结", "什么病", "看出什么"],
                "answerable": True,
                "answer": f"{case.get('title','')}。库内标注的异常分区为{names}。" + (
                    f"其中{ab[0]['name']}：{ab[0]['text']}" if ab else ""),
                "confidence": "high",
                "region": _region_of(ab, case),
                "citation": cite(spans, pick_kp(topic, sign_ids)) if (topic and (topic.get("key_points") or [])) else None,
                "basis": "库内逐区标注",
            })

    # 4) 拒答样例：真实规则判定，不是演的
    refusals = [
        ("这张片子是不是肺癌？", "out_of_scope_diagnosis", "超出诊断范围",
         "库内是教学分区标注，不包含病理或恶性诊断依据。仅凭胸片分区描述不能判断良恶性，需要病理、增强 CT 或多学科会诊。",
         "可以问：这张片子有没有结节？结节的部位和大小来源是怎么描述的？"),
        ("病灶是早期还是晚期？", "out_of_scope_diagnosis", "超出分期范围",
         "分期依赖 TNM 系统、影像分期与病理结果，本工具只做分区阅片描述，不做分期。",
         "可以问：这张片子主要异常是什么？"),
        ("需要做手术吗？", "out_of_scope_treatment", "超出治疗建议范围",
         "治疗决策需要结合临床、实验室与患者整体情况，本工具不提供治疗建议。",
         "可以问：这份报告缺哪些要素？"),
        ("帮我写一份正式诊断报告", "out_of_scope_report", "超出报告签发范围",
         "本工具输出的是教学分区所见与出处，不是可直接签发的诊断报告，也没有经过医师审核。",
         "可以看：报告—指南双源对照，它只提示离规范报告还差哪几项。"),
        ("这个病人预后怎么样？", "out_of_scope_prognosis", "超出预后判断范围",
         "预后需要纵向随访数据与临床资料，单张胸片的分区描述不足以支撑预后判断。",
         "可以问：这张片子有没有胸腔积液？"),
        ("右肺上野有没有骨折？", "out_of_scope_topic", "超出覆盖主题",
         "本工具的分区标注针对肺野、心影、纵隔、膈肌等胸部 X 线教学分区，不包含肋骨骨折的系统判读。",
         "可以问：右肺上野有什么问题？"),
        ("胸腔积液大概有多少毫升？", "out_of_scope_quantify", "超出定量范围",
         "胸片只能提示积液的存在与大致范围，精确容量需要超声或 CT 评估，本工具不做容量估算。",
         "可以问：这张片子有没有胸腔积液？"),
        ("这张片子是肺炎还是肺结核？", "out_of_scope_differential", "不做鉴别结论",
         "可以分别告诉你两种病变在库内的描述，但不下「二者之一」的鉴别结论——鉴别需要临床、实验室与随访。",
         "可以分别问：有没有肺炎？有没有结核？"),
    ]
    for i, (q, t, tcn, reason, sug) in enumerate(refusals, 1):
        items.append({
            "qid": f"R{i:04d}",
            "kind": "refusal",
            "case_id": None,
            "topic_id": "",
            "question": q,
            "keywords": [q[:6]] + _split_kw(q),
            "answerable": False,
            "refusal": {"type": t, "type_cn": tcn, "reason": reason, "suggestion": sug},
        })

    for it in items:
        it.setdefault("answerable", True)

    out = {
        "version": "0.1.0",
        "notice": "答案文本来自库内逐区标注；指南引用带字符 offset 与 sha1，可复算；拒答为规则判定。",
        "corpus": corpus,
        "corpus_sha1": sha1_of(corpus),
        "corpus_length": len(corpus),
        "items": items,
        "summary": {
            "total": len(items),
            "answerable": sum(1 for i in items if i["answerable"]),
            "refusal": sum(1 for i in items if not i["answerable"]),
            "cases": len({i["case_id"] for i in items if i["case_id"]}),
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    print("wrote", OUT)
    print(out["summary"])
    print("corpus length:", len(corpus), "sha1:", out["corpus_sha1"][:12])


def _signs_for_topic(tid, digest):
    # 主题 → 征象 ID 的映射放在 digest 可选字段；没有就返回空
    for t in digest["topics"]:
        if t["topic_id"] == tid:
            return t.get("sign_ids") or []
    return []


def _zone_hits_topic(zone, topic):
    kws = topic.get("match_keywords") or []
    txt = (zone.get("text") or "") + " " + (zone.get("name") or "")
    return any(k in txt for k in kws)


def _compact(zones):
    names = [z["name"] for z in zones]
    if not names:
        return "库内标注"
    if len(names) > 2:
        return f"{len(names)}个分区（{'、'.join(names[:2])}等）"
    return "、".join(names)


def _join_texts(zones):
    seen = []
    for z in zones:
        if z["status"] == "abnormal" and z.get("text"):
            t = z["text"].rstrip("。；; ")
            if t and t not in seen:
                seen.append(t)
    return ("；".join(seen[:2]) + "。") if seen else "（无）"


def _region_of(zones, case):
    ab = [z for z in zones if z["status"] == "abnormal"]
    if not ab:
        return None
    z = ab[0]
    return {
        "zone_id": z["id"],
        "label": z["name"],
        "coords": z.get("coords"),
        "image": case.get("image", ""),
        "case_id": case["id"],
        "case_title": case.get("title", ""),
        "status": z["status"],
    }


def _split_kw(q):
    import re
    return [w for w in re.split(r"[，。？、\s]+", q) if len(w) >= 2][:6]


if __name__ == "__main__":
    main()
