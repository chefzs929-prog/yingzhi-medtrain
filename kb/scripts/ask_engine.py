"""RadHearing 问答引擎（Python 唯一实现）。

与 kb/app/ask-core.js 逐行对齐：norm / bigrams / dice / parseRegion / scoreOf / best / classify。
两边的结果由 kb/scripts/crosscheck.py 在 69 条用例上做交叉验证。

用途：
- 网页端：由 ask-core.js 承担（同一算法）
- DeepWorks 技能端：由本模块承担
"""

from __future__ import annotations

import json
import re
from pathlib import Path

STOP = {"有没有", "什么", "这张", "片子", "问题", "吗", "有吗", "怎样", "怎么"}
THR_ANSWER = 0.32
THR_REFUSE = 0.25
ZONE_KEY = {"RUL": "右上", "RML": "右中", "RLL": "右下",
            "LUL": "左上", "LML": "左中", "LLL": "左下"}


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


def parse_region(q):
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
    pool = [it for it in items if case_id is None
            or it.get("case_id") is None or it["case_id"] == case_id]
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


class Bank:
    def __init__(self, path):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf8"))
        self.data = data
        self.items = data["items"]
        self.corpus = data.get("corpus", "")
        self.corpus_sha1 = data.get("corpus_sha1", "")

    def cases(self):
        seen = {}
        for it in self.items:
            cid = it.get("case_id")
            if not cid:
                continue
            if cid not in seen:
                title = ((it.get("region") or {}).get("case_title") or "")
                seen[cid] = {"id": cid, "title": title, "n": 0}
            seen[cid]["n"] += 1
        return list(seen.values())

    def resolve_case(self, q, case_id=None):
        """没指定病例时，用问题里的实体找最可能的病例。"""
        if case_id:
            return case_id
        pool = [it for it in self.items if it.get("case_id")]
        scored = {}
        for it in pool:
            s = score_of(q, it)
            if s > 0:
                scored[it["case_id"]] = max(scored.get(it["case_id"], 0), s)
        if not scored:
            return None
        return max(scored.items(), key=lambda x: x[1])[0]

    def answer(self, question, case_id=None):
        cid = self.resolve_case(question, case_id)
        kind, score, item = classify(question, cid, self.items)
        if kind == "unknown" or item is None:
            return {"status": "unknown", "question": question, "case_id": cid,
                    "score": round(score, 3), "item": None, "markdown": render_unknown(self, question, cid)}
        if kind == "refusal":
            return {"status": "refusal", "question": question, "case_id": cid,
                    "score": round(score, 3), "item": item, "markdown": render_refusal(item)}
        return {"status": "answer", "question": question, "case_id": cid,
                "score": round(score, 3), "item": item, "markdown": render_answer(self, item)}


def _conf_cn(v):
    return {"high": "高", "low": "低（来源未描述）", "medium": "中"}.get(v, "中")


def render_answer(bank, item):
    lines = []
    lines.append(f"**可以回答**　·　置信度 {_conf_cn(item.get('confidence'))}")
    lines.append("")
    lines.append(item["answer"])
    lines.append("")

    reg = item.get("region")
    if reg:
        lines.append("**影像区域**")
        lines.append(f"- 分区：{reg.get('label')}（{reg.get('zone_id')}）")
        lines.append(f"- 病例：{reg.get('case_id')}　{reg.get('case_title') or ''}")
        c = reg.get("coords")
        if c and len(c) == 4:
            lines.append(f"- 归一化坐标：left={c[0]} top={c[1]} w={c[2]} h={c[3]}")
        lines.append(f"- 影像：{reg.get('image') or '（无）'}")
        lines.append("")

    cit = item.get("citation")
    if cit:
        lines.append("**依据原文**")
        lines.append("")
        lines.append(f"> {cit.get('quote')}")
        lines.append("")
        lines.append(f"— {cit.get('topic_cn')} · `{cit.get('kp_id')}` · 第 {cit.get('offset')} 字起 · 校验 `{str(cit.get('sha1'))[:8]}`")
        lines.append("")
        lines.append(f"指南语料 {len(bank.corpus)} 字 · 全文校验 `{bank.corpus_sha1[:12]}` · 仅要点转述，非逐字引用")
        lines.append("")

    lines.append(f"**出处**：{item.get('basis') or '库内逐区标注'}　·　问题 {item.get('qid')}")
    return "\n".join(lines)


def render_refusal(item):
    r = item["refusal"]
    soft = r.get("level") == "soft"
    head = "**不给结论 · 但可给依据**" if soft else "**不能回答**"
    title = "这个我不下结论。" if soft else "这个我不能答。"
    return "\n".join([
        f"{head}　·　{r.get('type_cn')}",
        "",
        title,
        "",
        r.get("reason", ""),
        "",
        f"**你可以问**：{r.get('suggestion') or '换一种问法'}",
    ])


def render_unknown(bank, question, case_id):
    pool = [i for i in bank.items if i["answerable"] and (case_id is None or i.get("case_id") == case_id)]
    tips = "\n".join(f"- {i['question']}" for i in pool[:3])
    return "\n".join([
        "**没匹配到**　·　库内无对应问答",
        "",
        "我没理解这个问题。",
        "",
        "我只会回答与当前病例相关、且库内有据可依的问题。与其编一个答案，不如直接说没对上。",
        "",
        "**可以试试**：",
        tips if tips else "- （当前病例没有可用的示例问题）",
    ])


def default_bank_path():
    here = Path(__file__).resolve()
    for parent in [here.parent.parent.parent, here.parent.parent, here.parent]:
        cand = parent / "kb" / "data" / "ask_bank.json"
        if cand.exists():
            return cand
    return None


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--case", default=None)
    ap.add_argument("--bank", default=None)
    a = ap.parse_args()
    bp = Path(a.bank) if a.bank else default_bank_path()
    if bp is None:
        raise SystemExit("找不到 ask_bank.json，请用 --bank 指定")
    b = Bank(bp)
    res = b.answer(a.question, a.case)
    print(res["markdown"])
