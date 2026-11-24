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
             "髋关节", "膝关节", "踝关节", "肩关节", "腕关节", "肘关节", "腹部", "阑尾", "肠道"]
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


LAB_INTENT_COMPARE = re.compile(r"区分|鉴别|区别|不同|vs|对比")
LAB_INTENT_KNOW = re.compile(r"怎么找|如何识别|怎么识别|怎么看出|怎么看|是什么|什么是|定义|表现|长什么样|影像表现|胸片表现|x线表现|征象|特点")


def _lab_entities(lab, q):
    """按出现位置找库内实体；征象优先于疾病，同名去重。"""
    pool = [("sign", s) for s in lab.get("signs", [])] + \
           [("concept", c) for c in lab.get("concepts", [])]
    hits, seen = [], set()
    for kind, x in pool:
        names = [x.get("name"), x.get("en")] + list(x.get("aliases") or [])
        pos = -1
        for n in names:
            nn = norm(n)
            if len(nn) < 2:
                continue
            i = q.find(nn)
            if i >= 0 and (pos < 0 or i < pos):
                pos = i
        if pos < 0:
            continue
        key = norm(x.get("name"))
        if key in seen:
            continue
        seen.add(key)
        hits.append((pos, kind, x))
    hits.sort(key=lambda t: t[0])
    return [(k, x) for _, k, x in hits]


def _lab_cases(lab, sign_ids, limit=6):
    wanted = set(sign_ids or [])
    out, seen, per = [], set(), {}
    for c in lab.get("cases", []):
        zones = [z for z in c.get("zones", []) if wanted & set(z.get("sign_ids") or [])]
        for z in zones:
            if per.get(c["id"], 0) >= 2:
                continue
            per[c["id"]] = per.get(c["id"], 0) + 1
            key = (c["id"], z["id"])
            if key in seen:
                continue
            seen.add(key)
            out.append((c, z))
        if not zones and wanted & set(c.get("signs") or []):
            z = next((x for x in c.get("zones", []) if x.get("status") == "abnormal"), None)
            key = (c["id"], z["id"] if z else "none")
            if key not in seen:
                seen.add(key)
                out.append((c, z))
    return out[:limit]


def _lab_sources(lab, sign_ids):
    by_id = {s["id"]: s for s in lab.get("signs", [])}
    out, seen = [], set()
    for sid in sign_ids or []:
        s = by_id.get(sid)
        if not s:
            continue
        for src in s.get("sources") or []:
            if not src or src.get("id") in seen:
                continue
            seen.add(src["id"])
            out.append(src)
    return out[:8]


def _lab_modality_note(s):
    m = s.get("modality") or []
    if not m:
        return ""
    if any(x in ("CR", "X线", "DR") for x in m):
        return ""
    if "CT" in m:
        return "该征象的定义主要来自 CT 术语；胸片上的可辨识度有限，需结合 CT 判断。"
    return f"该征象的定义来自 {' / '.join(m)}；不是胸片征象，本工具只作术语对照。"


def _lab_entity_view(s):
    return {
        "name": s.get("name", ""),
        "appearance": s.get("appearance") or s.get("note") or "该词条暂无形态描述",
        "pitfalls": list(s.get("pitfalls") or [])[:3],
        "modality": list(s.get("modality") or []),
    }


def _lab_markdown(kind, conclusion, cases, sources, missing):
    label = {"sign": "征象解释", "concept": "疾病解释", "compare": "对比"}.get(kind, "知识库")
    lines = [f"**可以回答**　·　{label}", "", conclusion, ""]
    if cases:
        c, z = cases[0]
        if z:
            lines += [
                "**影像区域**",
                f"- 分区：{z.get('name', '')}（{z.get('id', '')}）",
                f"- 病例：{c.get('id', '')}　{c.get('title', '')}",
                f"- 影像：{c.get('image', '')}",
                "",
            ]
    if sources:
        lines.append("**文献来源**")
        for s in sources:
            lines.append(f"- {s.get('title', '')} — {s.get('publisher', '')} — {s.get('url', '')}")
        lines.append("")
    if missing:
        lines.append("**边界**")
        for m in missing:
            lines.append(f"- {m}")
        lines.append("")
    return "\n".join(lines)


def lab_answer(question, lab):
    """把“X 是什么 / 怎么找 / A 和 B 怎么区分”接到学生实验室同一套词条上。"""
    q = norm(question)
    if not q or not lab:
        return None
    entities = _lab_entities(lab, q)
    if LAB_INTENT_COMPARE.search(q):
        if len(entities) < 2 or norm(entities[0][1].get("name")) == norm(entities[1][1].get("name")):
            return None
        (_, a), (_, b) = entities[0], entities[1]
        av, bv = _lab_entity_view(a), _lab_entity_view(b)
        ids = []
        for x in (a, b):
            for sid in (x.get("sign_ids") or [x.get("id")]):
                if sid not in ids:
                    ids.append(sid)
        cases = _lab_cases(lab, ids, 6)
        sources = _lab_sources(lab, ids)
        missing = []
        for v in (av, bv):
            note = _lab_modality_note({"modality": v["modality"]})
            if note:
                missing.append(f"{v['name']}：{note}")
        missing += [
            "对比只并列知识库中的定义、位置与易错点，不是诊断路径。",
            "同一病例可能同时挂两个征象；以该区逐区标注和原始出处为准。",
        ]
        conclusion = (
            f"{av['name']}：{av['appearance']} {bv['name']}：{bv['appearance']} "
            f"鉴别时不要只看一个征象：{av['name']} 的易错点——{'；'.join(av['pitfalls']) or '暂未列出'}；"
            f"{bv['name']} 的易错点——{'；'.join(bv['pitfalls']) or '暂未列出'}。"
        )
        return {
            "kind": "compare",
            "conclusion": conclusion,
            "cases": cases,
            "sources": sources,
            "missing": missing,
            "markdown": _lab_markdown("compare", conclusion, cases, sources, missing),
        }
    if not LAB_INTENT_KNOW.search(q) or not entities:
        return None
    kind, x = entities[0]
    if kind == "sign":
        note = _lab_modality_note(x)
        missing = [note] if note else []
        cases = _lab_cases(lab, [x["id"]], 6)
        if not cases:
            missing.append("当前影像库中暂时没有直接标注该征象的分区，只能给出词条与文献。")
        sources = _lab_sources(lab, [x["id"]])
        if not sources:
            missing.append("相关词条没有登记可引用的文献来源，因此不补造出处。")
        conclusion = f"{x.get('name', '')}：{x.get('appearance') or '该词条暂无形态描述'}"
        return {
            "kind": "sign",
            "conclusion": conclusion,
            "cases": cases,
            "sources": sources,
            "missing": missing,
            "markdown": _lab_markdown("sign", conclusion, cases, sources, missing),
        }
    by_id = {s["id"]: s for s in lab.get("signs", [])}
    direct = [by_id[i] for i in (x.get("sign_ids") or []) if i in by_id]
    related = [by_id[i] for i in (x.get("related_sign_ids") or []) if i in by_id]
    ids = [s["id"] for s in direct] + [s["id"] for s in related if s["id"] not in {d["id"] for d in direct}]
    names = [s["name"] for s in direct]
    rel_names = [s["name"] for s in related]
    missing = []
    if not direct:
        missing.append("该疾病在知识库中没有直接对应的征象，只有关联征象；关联只作参考，不作为直接依据。")
    sources = _lab_sources(lab, ids)
    if not sources:
        missing.append("相关词条没有登记可引用的文献来源，因此不补造出处。")
    conclusion = (
        f"{x.get('name', '')} 在知识库中对应的征象：{'、'.join(names)}"
        if names else f"{x.get('name', '')} 在知识库中没有直接对应的征象"
    )
    if rel_names:
        conclusion += f"；可参考关联征象：{'、'.join(rel_names)}（仅作参考，不作为直接依据）"
    if x.get("note"):
        conclusion += f"。{x['note']}"
    cases = _lab_cases(lab, ids, 6)
    return {
        "kind": "concept",
        "conclusion": conclusion,
        "cases": cases,
        "sources": sources,
        "missing": missing,
        "markdown": _lab_markdown("concept", conclusion, cases, sources, missing),
    }


class Bank:
    def __init__(self, path):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf8"))
        self.data = data
        self.items = data["items"]
        self.corpus = data.get("corpus", "")
        self.corpus_sha1 = data.get("corpus_sha1", "")
        self._lab = None

    def lab(self):
        if self._lab is None:
            p = self.path.parent / "student_lab.json"
            self._lab = json.loads(p.read_text(encoding="utf8")) if p.exists() else {}
        return self._lab

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
        # “X 是什么 / 怎么找 / A 和 B 怎么区分”先走知识库词条，避免落到“本片没有 X”。
        lab = lab_answer(question, self.lab())
        if lab:
            region = None
            if lab["cases"]:
                c, z = lab["cases"][0]
                if z:
                    region = {
                        "zone_id": z.get("id", ""),
                        "label": z.get("name", ""),
                        "coords": z.get("coords"),
                        "image": c.get("image", ""),
                        "case_id": c.get("id", ""),
                        "case_title": c.get("title", ""),
                        "status": z.get("status", ""),
                    }
            item = {"qid": "LAB", "kind": lab["kind"], "region": region}
            return {"status": "answer", "question": question, "case_id": cid,
                    "score": 1.0, "item": item, "markdown": lab["markdown"]}
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
    if cit and cit.get("source") == "claim":
        lines.append("**依据原文**")
        lines.append("")
        lines.append(f"> {cit.get('quote')}")
        lines.append("")
        lines.append(
            f"— {cit.get('case_id')} · {cit.get('zone_name')}（{cit.get('zone_id')}）"
            " · 库内逐区标注（无指南锚点）"
        )
        lines.append("")
    elif cit:
        lines.append("**依据原文**")
        lines.append("")
        lines.append(f"> {cit.get('quote')}")
        lines.append("")
        lines.append(f"— {cit.get('topic_cn')} · `{cit.get('kp_id')}` · 第 {cit.get('offset')} 字起 · 校验 `{str(cit.get('sha1'))[:8]}`")
        lines.append("")
        lines.append(f"指南语料 {len(bank.corpus)} 字 · 全文校验 `{bank.corpus_sha1[:12]}` · 仅要点转述，非逐字引用")
        lines.append("")
    elif item.get("kind") == "zone":
        lines.append("**依据原文**")
        lines.append("")
        lines.append("> 该分区只有库内逐区标注，没有可回溯的指南原文；请以影像区域为准，不要据此补造文献出处。")
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
