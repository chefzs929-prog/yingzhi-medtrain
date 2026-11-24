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
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHEST = ROOT / "kb/data/chest_reading.json"
DIGEST = ROOT / "kb/data/guideline_digest.json"
DUAL = ROOT / "kb/data/dual_source.json"
REFUSALS = ROOT / "kb/data/refusals.json"
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

        # 1) 分区问：每个分区都生成，非异常区明确说清边界
        for z in zones:
            n += 1
            kp_id = pick_kp(topic, z.get("sign_ids") or sign_ids)
            st = z["status"]
            if st == "abnormal":
                ans_text, conf = z["text"], ("high" if case.get("quality") != "limited" else "medium")
            elif st == "normal":
                ans_text, conf = f"来源明确描述该区未见异常。{z.get('text') or ''}", "medium"
            elif st == "limited":
                ans_text, conf = f"该区判读受限：{z.get('text') or '图像质量或体位不允许判读。'}", "low"
            else:
                ans_text, conf = "公开来源未逐区描述该区。未提及不等于正常，不能据此排除病变。", "low"
            items.append({
                "qid": f"A{n:04d}",
                "kind": "zone",
                "case_id": cid,
                "topic_id": topic_id,
                "question": f"{z['name']}有什么问题？",
                "keywords": [z["name"], z["id"], (topic or {}).get("topic_cn", ""), "有什么", "问题", "异常"],
                "aliases": region_aliases(z["name"]),
                "answerable": True,
                "answer": ans_text,
                "confidence": conf,
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
                "aliases": topic_aliases(tid, t),
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
                "aliases": ["主要异常", "整体", "概括", "总结", "小结", "看看", "怎么看", "什么问题", "主要问题", "主要病灶", "说说", "讲一下", "发现", "怎么读", "结论", "有阴影"],
                "answerable": True,
                "answer": f"{case.get('title','')}。库内标注的异常分区为{names}。" + (
                    f"其中{ab[0]['name']}：{ab[0]['text']}" if ab else ""),
                "confidence": "high",
                "region": _region_of(ab, case),
                "citation": cite(spans, pick_kp(topic, sign_ids)) if (topic and (topic.get("key_points") or [])) else None,
                "basis": "库内逐区标注",
            })

    # 4) 拒答样例：从数据文件读取，每条都是真实规则判定
    refuse_data = json.loads(REFUSALS.read_text(encoding="utf8"))
    for r in refuse_data["items"]:
        items.append({
            "qid": r["id"].replace("REF-", "R"),
            "kind": "refusal",
            "case_id": None,
            "topic_id": "",
            "question": r["question"],
            "keywords": _split_kw(r["question"]),
            "answerable": False,
            "aliases": r.get("aliases", []),
            "refusal": {
                "type": r["type"],
                "type_cn": r["type_cn"],
                "level": r.get("level", "hard"),
                "reason": r["reason"],
                "suggestion": re.sub(r"^可以(问|看)[：:]\s*", "", r["suggestion"]),
            },
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


EXTRA_REGION = {
    "心影": ["心影", "心脏", "心影增大", "心脏增大", "心影大", "心胸比"],
    "纵隔": ["纵隔", "纵隔影"],
    "膈肌": ["膈肌", "膈面", "横膈"],
    "右肋膈角": ["右肋膈角", "右侧肋膈角"],
    "左肋膈角": ["左肋膈角", "左侧肋膈角"],
}

TOPIC_ALIASES = {
    "PNEUMONIA": ["肺炎", "炎症", "实变", "气腔影", "浸润", "感染", "发炎", "渗出"],
    "NODULE": ["结节", "肺结节", "小结节", "长东西", "肿块", "占位"],
    "EFFUSION": ["积液", "胸腔积液", "胸水", "胸腔有水", "胸腔", "积水"],
    "PNEUMOTHORAX": ["气胸", "肺压缩", "漏气", "破了"],
    "TB": ["结核", "肺结核", "结核病"],
    "NORMAL": ["正常", "正常胸片", "没问题", "没毛病"],
    "CARDIOMEGALY": ["心影增大", "心脏增大", "心影大", "心胸比", "心脏大", "心脏"],
}


def region_aliases(name):
    al = [name]
    m = re.match(r"([左右])(肺)?([上中下])(野)$", name)
    if m:
        side, _, part, _ = m.groups()
        al += [f"{side}{part}肺野", f"{side}侧{part}野", f"{side}{part}野", f"{side}{part}肺", f"{side}边{part}"]
    al += EXTRA_REGION.get(name, [])
    return list(dict.fromkeys(al))


def topic_aliases(tid, t):
    al = [tid] + list(TOPIC_ALIASES.get(tid, []))
    al.append(t["topic_cn"].split(" / ")[0])
    return list(dict.fromkeys(al))


def _split_kw(q):
    import re
    return [w for w in re.split(r"[，。？、\s]+", q) if len(w) >= 2][:6]


if __name__ == "__main__":
    main()
