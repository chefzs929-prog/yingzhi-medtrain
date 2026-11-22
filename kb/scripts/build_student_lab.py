#!/usr/bin/env python3
"""构建学生端「影像实验室」数据。

输入（只读）：
    kb/data/chest_reading.json   21 例 CR 胸部逐区数据
    kb/data/signs.jsonl          征象词条
    kb/data/concepts.jsonl       疾病 / 病理概念
    kb/data/guidelines.jsonl     指南条款（胸部当前为空）
    kb/data/sources.json         来源登记表

输出：
    kb/data/student_lab.json
        - signs / concepts / guidelines / sources：问答检索索引
        - cases：21 例精简病例，含分区框
        - questions：定位 / 判读 / 征象三类规则题，带影像与文献引用

边界：
    - 只覆盖 21 例已启用的 CR 胸部，不扩部位。
    - 题目由库内逐区标注规则生成，不是考试真题；答案只代表库内标注。
    - 文献引用只到来源级（标题 / 发布方 / 链接），不复制受版权保护全文。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
KB = ROOT / "kb"
DATA = KB / "data"
OUT = DATA / "student_lab.json"

CHEST_SIGNS = [f"SIGN-{i:03d}" for i in range(1, 21)]
STATUS_LABEL = {
    "abnormal": "异常",
    "normal": "未见异常",
    "unmentioned": "来源未提及",
    "limited": "判读受限",
}
STATUS_OPTIONS = ["异常", "未见异常", "来源未提及", "判读受限"]


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def stable_hash(text: str) -> int:
    h = 2166136261
    for ch in str(text):
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def pick_options(correct: str, pool: list[str], seed: str, n: int = 4) -> list[str]:
    """稳定地选出 n 个选项，包含 correct。"""
    others = [x for x in dict.fromkeys(pool) if x and x != correct]
    others.sort(key=lambda x: (stable_hash(seed + "|" + x) % 100000, x))
    out = [correct] + others[: max(0, n - 1)]
    out.sort(key=lambda x: (stable_hash(seed + "|opt|" + x) % 100000, x))
    return out


def source_map(raw: dict) -> dict[str, dict]:
    return {s["id"]: s for s in raw.get("sources", []) if s.get("id")}


def main() -> None:
    chest = json.loads((DATA / "chest_reading.json").read_text(encoding="utf8"))
    raw_sources = json.loads((DATA / "sources.json").read_text(encoding="utf8"))
    smap = source_map(raw_sources)
    sign_rows = {s["id"]: s for s in read_jsonl(DATA / "signs.jsonl")}
    concept_rows = read_jsonl(DATA / "concepts.jsonl")
    guideline_rows = read_jsonl(DATA / "guidelines.jsonl")

    cases = [c for c in chest["cases"] if c.get("enabled")]
    case_ids = {c["id"] for c in cases}

    # ---- 征象索引：只收胸部 20 条 ----
    signs = []
    for sid in CHEST_SIGNS:
        s = sign_rows.get(sid)
        if not s:
            continue
        source_ids = [x for x in s.get("sources", []) if x in smap]
        signs.append({
            "id": s["id"],
            "name": s["name"],
            "en": s.get("en", ""),
            "aliases": s.get("aliases", []),
            "modality": s.get("modality", []),
            "body_part": s.get("body_part", ""),
            "appearance": s.get("appearance", ""),
            "may_see_in": s.get("may_see_in", []),
            "pitfalls": s.get("pitfalls", []),
            "tags": s.get("tags", []),
            "source_ids": source_ids,
            "sources": [smap[x] for x in source_ids],
        })
    sign_ids = {s["id"] for s in signs}
    sign_name = {s["id"]: s["name"] for s in signs}

    # ---- 概念索引：与胸部征象有交集 ----
    concepts = []
    for c in concept_rows:
        direct = [x for x in c.get("sign_ids", []) if x in sign_ids]
        related = [x for x in c.get("related_sign_ids", []) if x in sign_ids]
        if not direct and not related:
            continue
        concepts.append({
            "id": c["id"],
            "name": c["name"],
            "en": c.get("en", ""),
            "aliases": c.get("aliases", []),
            "sign_ids": direct,
            "related_sign_ids": related,
            "note": c.get("note", ""),
        })
    concepts.sort(key=lambda x: x["id"])

    # ---- 指南：胸部 / 肺 / 胸膜 / 纵隔 / 心脏 ----
    chest_words = ("胸", "肺", "纵隔", "心脏", "心影", "胸膜")
    guidelines = []
    for g in guideline_rows:
        body = str(g.get("body_part", ""))
        if any(w in body for w in chest_words):
            guidelines.append({
                "id": g["id"],
                "standard_id": g.get("standard_id", ""),
                "standard_name": g.get("standard_name", ""),
                "body_part": body,
                "category": g.get("category", ""),
                "section": g.get("section", ""),
                "statement": g.get("statement", ""),
                "conditions": g.get("conditions", []),
                "action": g.get("action", ""),
                "version_year": g.get("version_year", ""),
                "source_url": g.get("source_url", ""),
                "license_note": g.get("license_note", ""),
            })
    guidelines.sort(key=lambda x: x["id"])

    # ---- 病例精简：保留页面需要的字段 ----
    out_cases = []
    zone_name_pool = {}
    for c in cases:
        zones = []
        for z in c.get("zones", []):
            zones.append({
                "id": z["id"],
                "name": z["name"],
                "side": z.get("side", ""),
                "coords": z.get("coords", []),
                "status": z.get("status", "unmentioned"),
                "status_label": STATUS_LABEL.get(z.get("status"), "未标注"),
                "text": z.get("text", ""),
                "note": z.get("note", ""),
                "sign_ids": [x for x in z.get("sign_ids", []) if x in sign_ids],
                "basis": z.get("basis", ""),
            })
            zone_name_pool.setdefault(c.get("pose", ""), []).append(z["name"])
        out_cases.append({
            "id": c["id"],
            "title": c["title"],
            "modality": c.get("modality", "CR"),
            "body_part": c.get("body_part", "胸部"),
            "pose": c.get("pose", ""),
            "pose_label": c.get("pose_label", ""),
            "image": c["image"],
            "quality": c.get("quality", ""),
            "signs": [x for x in c.get("signs", []) if x in sign_ids],
            "sign_names": [sign_name[x] for x in c.get("signs", []) if x in sign_ids],
            "teaching_note": c.get("teaching_note", ""),
            "source_page": c.get("source_page", ""),
            "license": c.get("license", ""),
            "artist": c.get("artist", ""),
            "zones": zones,
        })
    zone_name_pool = {k: list(dict.fromkeys(v)) for k, v in zone_name_pool.items()}
    by_case = {c["id"]: c for c in out_cases}

    # ---- 题目：定位 / 判读 / 征象 ----
    questions = []
    for c in out_cases:
        for z in c["zones"]:
            if len(z["coords"]) != 4:
                continue
            # 定位题
            qid = f"LAB-LOC-{c['id']}-{z['id']}"
            pose_pool = zone_name_pool.get(c.get("pose", ""), [])
            opts = pick_options(z["name"], pose_pool, qid, max(3, min(4, len(pose_pool))))
            questions.append({
                "qid": qid,
                "type": "locate",
                "type_label": "影像定位",
                "case_id": c["id"],
                "zone_id": z["id"],
                "coords": z["coords"],
                "prompt": "图中框选的区域属于哪个解剖分区？",
                "options": opts,
                "answer": z["name"],
                "answer_index": opts.index(z["name"]),
                "explain": f"{z['name']}：{z.get('note') or '按库内分区框定位。'}（框选位置以库内 coords 为准，不代表诊断。）",
                "difficulty": "基础",
                "tags": [c["title"], z["name"]],
                "citations": {
                    "case_id": c["id"],
                    "zone_id": z["id"],
                    "sign_ids": z["sign_ids"],
                    "source_ids": [],
                    "guideline_ids": [],
                },
            })
            # 判读题
            qid = f"LAB-STS-{c['id']}-{z['id']}"
            opts = pick_options(STATUS_LABEL[z["status"]], STATUS_OPTIONS, qid)
            questions.append({
                "qid": qid,
                "type": "status",
                "type_label": "分区判读",
                "case_id": c["id"],
                "zone_id": z["id"],
                "coords": z["coords"],
                "prompt": "该分区在库内逐区标注中的状态是？",
                "options": opts,
                "answer": STATUS_LABEL[z["status"]],
                "answer_index": opts.index(STATUS_LABEL[z["status"]]),
                "explain": f"{z['text']}（依据：{z.get('basis') or '库内逐区标注'}。"
                           "「来源未提及」不等于正常；本工具不作推断。）",
                "difficulty": "进阶" if z["status"] in ("unmentioned", "limited") else "基础",
                "tags": [c["title"], z["name"], STATUS_LABEL[z["status"]]],
                "citations": {
                    "case_id": c["id"],
                    "zone_id": z["id"],
                    "sign_ids": z["sign_ids"],
                    "source_ids": [],
                    "guideline_ids": [],
                },
            })
            # 征象题：只在该区挂载了征象时生成
            if z["sign_ids"]:
                correct_sid = z["sign_ids"][0]
                correct_name = sign_name[correct_sid]
                wrong_pool = [sign_name[x] for x in CHEST_SIGNS if x not in z["sign_ids"] and x in sign_name]
                qid = f"LAB-SGN-{c['id']}-{z['id']}"
                opts = pick_options(correct_name, wrong_pool, qid)
                src_ids = []
                for sid in z["sign_ids"]:
                    src_ids.extend((next((s for s in signs if s["id"] == sid), {}) or {}).get("source_ids", []))
                src_ids = list(dict.fromkeys(src_ids))
                questions.append({
                    "qid": qid,
                    "type": "sign",
                    "type_label": "征象识别",
                    "case_id": c["id"],
                    "zone_id": z["id"],
                    "coords": z["coords"],
                    "prompt": "该分区在库内关联的征象中，下列哪一项属于本区？",
                    "options": opts,
                    "answer": correct_name,
                    "answer_index": opts.index(correct_name),
                    "explain": f"本区关联征象：{'、'.join(sign_name[x] for x in z['sign_ids'])}。"
                               f"{z['text']}（本题只考库内关联，不代表该例一定出现此征象，也不构成诊断。）",
                    "difficulty": "进阶",
                    "tags": [c["title"], z["name"]] + [sign_name[x] for x in z["sign_ids"]],
                    "citations": {
                        "case_id": c["id"],
                        "zone_id": z["id"],
                        "sign_ids": z["sign_ids"],
                        "source_ids": src_ids,
                        "guideline_ids": [],
                    },
                })

    questions.sort(key=lambda q: (q["case_id"], q["zone_id"], q["type"]))
    counts = {
        "cases": len(out_cases),
        "zones": sum(len(c["zones"]) for c in out_cases),
        "questions": len(questions),
        "locate": sum(1 for q in questions if q["type"] == "locate"),
        "status": sum(1 for q in questions if q["type"] == "status"),
        "sign": sum(1 for q in questions if q["type"] == "sign"),
        "signs": len(signs),
        "concepts": len(concepts),
        "guidelines": len(guidelines),
        "sources": len(smap),
    }
    # ---- 文献段落：把词条 / 指南的段落级锚点带进问答与自测 ----
    para_rows = read_jsonl(DATA / "paragraphs.jsonl")

    def para_pack(p: dict) -> dict:
        return {
            "para_id": p.get("para_id", ""),
            "doc_id": p.get("doc_id", ""),
            "title": p.get("title", ""),
            "section": p.get("section", ""),
            "para": p.get("para", 0),
            "char_start": p.get("char_start", 0),
            "char_end": p.get("char_end", 0),
            "text": p.get("text", ""),
            "sha256": p.get("sha256", ""),
            "page": p.get("page"),
            "page_status": p.get("page_status", ""),
            "source_url": p.get("source_url", ""),
            "license_note": p.get("license_note", ""),
        }

    sign_paragraphs: dict[str, list[dict]] = {}
    for p in para_rows:
        if p.get("doc_id") in sign_ids:
            sign_paragraphs.setdefault(p["doc_id"], []).append(para_pack(p))
    for sid, rows in sign_paragraphs.items():
        rows.sort(key=lambda x: ({"appearance": 0, "pitfall": 1, "scenario": 2}.get(x["section"], 9), x["para"]))
        sign_paragraphs[sid] = rows[:4]

    guideline_paragraphs: dict[str, list[dict]] = {}
    gids = {g["id"] for g in guidelines}
    for p in para_rows:
        if p.get("doc_id") in gids:
            guideline_paragraphs.setdefault(p["doc_id"], []).append(para_pack(p))
    for gid, rows in guideline_paragraphs.items():
        rows.sort(key=lambda x: ({"statement": 0, "condition": 1, "action": 2}.get(x["section"], 9), x["para"]))
        guideline_paragraphs[gid] = rows[:4]

    counts["sign_paragraphs"] = sum(len(v) for v in sign_paragraphs.values())
    counts["signs_with_paragraphs"] = len(sign_paragraphs)
    counts["guideline_paragraphs"] = sum(len(v) for v in guideline_paragraphs.values())

    payload = {
        "version": "2026-11-22",
        "generated_at": date.today().isoformat(),
        "scope": "21 例已启用 CR 胸部逐区数据；问答、陪练与自测只在此范围内。",
        "disclaimer": "仅用于医学影像教学与研究，不构成诊断意见，不替代临床决策。",
        "method": "题目由 chest_reading.json 的逐区状态、分区框与征象关联规则生成；"
                  "文献引用到来源级 + 段落级摘要锚点（paragraphs.jsonl 的 para_id / char 区间 / sha256）；"
                  "原文页码仍待补，段落是自撰摘要，不复制受版权保护全文。",
        "counts": counts,
        "sources": list(smap.values()),
        "signs": signs,
        "concepts": concepts,
        "guidelines": guidelines,
        "sign_paragraphs": sign_paragraphs,
        "guideline_paragraphs": guideline_paragraphs,
        "cases": out_cases,
        "questions": questions,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print("wrote", OUT)
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
