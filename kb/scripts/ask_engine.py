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

# 越界范围：与 kb/app/student-lab.js 的 SCOPE_WORDS / SCOPE_RULES 保持一致。
# 提问页、DeepWorks 技能、课堂影像问答必须共用同一套拒答边界，不能一个答一个拒。
SCOPE_WORDS = [
    "治疗", "怎么治", "如何治", "治吗", "手术", "用药", "药物", "吃什么药", "用什么药",
    "抗生素", "抗结核", "剂量", "化疗", "放疗", "靶向", "免疫治疗",
    "预后", "生存期", "能活多久", "活多久", "分期", "处方", "急救", "抢救",
    "住院", "出院", "引流", "穿刺", "抽水", "抽液", "置管", "闭式引流",
    "活检", "要不要做", "需要做", "建议做", "固定", "复位", "石膏",
    "气管插管", "插管", "机械通气", "疫苗", "接种", "护理", "康复", "预防",
    "严重吗", "会死吗",
]
SCOPE_RULES = [
    ("分期判断", ["分期", "早期还是晚期", "晚期还是早期", "几期", "tnm"]),
    ("病因判断", ["细菌还是病毒", "病毒还是细菌", "细菌感染", "病毒感染", "什么原因引起", "病因", "病原体"]),
    ("检查方式（本工具只判胸片）", ["ct上", "ct片", "核磁", "mri", "磁共振", "超声", "b超", "彩超", "pet"]),
    ("患者隐私", ["叫什么名字", "叫什么", "姓名", "多大年纪", "身份证", "电话号码", "住址", "哪家医院"]),
    ("准确性保证", ["100%", "百分之百", "保证准确", "一定能确诊", "包准", "保证不出错"]),
    ("非医学任务", ["写代码", "python", "翻译成", "写作文", "做表格", "写一段代码"]),
    ("就诊指引", ["挂哪个科", "看哪个科", "挂号", "去哪个医院"]),
    ("特殊人群与放射防护", ["儿童拍", "孕妇拍", "辐射剂量", "防护"]),
    ("骨骼与关节系统", ["骨折", "退变", "骨质疏松", "骨破坏"]),
]
NON_CHEST = ["甲状腺", "乳腺", "肝脏", "胆囊", "胰腺", "脾脏", "肾脏", "肾上腺",
             "盆腔", "子宫", "卵巢", "前列腺", "头颅", "大脑", "脊柱", "脊髓", "骨盆",
             "髋关节", "膝关节", "踝关节", "肩关节", "腕关节", "肘关节"]
CHEST_WORDS = ["胸", "肺", "心", "纵隔", "膈", "肋", "气胸", "实变", "积液"]
TOO_BROAD = ["胸片", "片子", "影像", "图片", "看看", "这个"]
SCOPE_SUGGESTIONS = ["气胸在胸片上怎么找", "实变和胸腔积液怎么区分", "这个分区标注的依据是什么"]


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


def _scope_text(q):
    """去空白后的规范化文本；与 JS 的 norm() 保持同一口径。"""
    return norm(q)


def scope_reason(q):
    """返回越界类别；空串表示在范围内。与 student-lab.js 的 scopeReason 对齐。"""
    s = _scope_text(q)
    if not s:
        return ""
    if any(w in s for w in (norm(x) for x in SCOPE_WORDS)):
        return "治疗 / 预后 / 操作建议"
    for label, words in SCOPE_RULES:
        if any(norm(w) in s for w in words):
            return label
    if re.search(r"(诊断|确诊|是不是.{0,4}(癌|肿瘤|病)|什么病|良性还是恶性|恶性还是良性)", s) \
            and not re.search(r"(依据|标准|怎么找|表现|征象|鉴别|区分)", s):
        return "诊断结论"
    return ""


def non_chest_reason(q):
    """非胸部部位：出现非胸部词且没有任何胸部词。"""
    s = _scope_text(q)
    if not s:
        return ""
    if not any(norm(w) in s for w in NON_CHEST):
        return ""
    return "" if any(norm(w) in s for w in CHEST_WORDS) else "非胸部部位"


def too_broad_reason(q):
    s = _scope_text(q)
    return "问句过于宽泛" if s in {norm(w) for w in TOO_BROAD} else ""


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
    # 先过范围门：治疗/预后/操作/非胸部/过宽问句一律不进入检索，
    # 避免“气胸怎么治疗”被“气胸”词条命中后当成可答问题。
    scope = scope_reason(q) or non_chest_reason(q) or too_broad_reason(q)
    if scope:
        return "refusal", 1.0, {"scope": scope, "answerable": False, "question": q}
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
            if item.get("scope"):
                return {"status": "refusal", "question": question, "case_id": cid,
                        "score": round(score, 3), "item": item,
                        "markdown": render_scope_refusal(item["scope"], question)}
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


def render_scope_refusal(label, question):
    """范围外拒答：先说类别，再说为什么，最后给替代问法。"""
    reason = {
        "治疗 / 预后 / 操作建议": "治疗、用药、手术、引流、住院与预后判断需要结合临床、实验室与患者整体情况；本工具只转述影像教学标注，不提供这类建议。",
        "非胸部部位": "本工具只做胸部 X 线（CR/DR）教学，不跨部位回答；其他部位的分区与征象不在库内。",
        "问句过于宽泛": "问句里没有具体的征象、疾病或分区；请给出具体对象，才能回到库内证据。",
        "诊断结论": "仅凭胸片分区描述不能下诊断或良恶性结论；需要病理、增强 CT 或多学科会诊。",
        "分期判断": "分期需要病理与系统影像资料，单张胸片不足以判断。",
        "病因判断": "病原学判断需要实验室、痰检与培养，影像只能描述表现。",
        "检查方式（本工具只判胸片）": "本工具的数据与标注全部是胸部 X 线正侧位片，不包含 CT、MRI、超声或核医学影像。",
        "患者隐私": "不提供患者身份信息，也不推断拍摄医院。",
        "准确性保证": "不能保证 100% 准确；库内是教学标注，不是临床性能承诺。",
        "非医学任务": "本工具只回答胸部 X 线的教学问题，不处理代码、翻译或文书任务。",
        "就诊指引": "就诊科室与挂号指引需要结合临床，本工具不提供。",
        "特殊人群与放射防护": "儿童、孕妇的检查选择与辐射防护属于临床决策，本工具不提供。",
        "骨骼与关节系统": "分区标注只覆盖肺野、心影与纵隔轮廓、膈面与肋膈角、膈下；骨骼与关节不在范围内。",
    }.get(label, "该问题超出本工具的能力范围。")
    return "\n".join([
        f"**不能回答**　·　{label}",
        "",
        "这个我不能答。",
        "",
        reason,
        "",
        f"**你可以问**：{'；'.join(SCOPE_SUGGESTIONS)}",
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
