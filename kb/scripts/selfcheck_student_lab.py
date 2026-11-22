#!/usr/bin/env python3
"""学生影像实验室数据自检。

检查：
    - 21 例 / 分区 / 题目计数与声明一致；
    - 每题答案在选项内，answer_index 正确，题型与答案类型匹配；
    - 病例、分区、征象、来源引用都能解析；
    - 每个病例至少有一道定位题和一道判读题；
    - 问答索引（征象 / 概念 / 指南 / 来源）引用完整。

输出：
    outputs/medtrain/student_lab_selfcheck.md
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb/data/student_lab.json"
OUT = ROOT / "outputs/medtrain/student_lab_selfcheck.md"
STATUS = {"abnormal": "异常", "normal": "未见异常", "unmentioned": "来源未提及", "limited": "判读受限"}

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))
    print(("  ✓ " if ok else "  ✗ ") + name + (("  " + detail) if detail and not ok else ""))


def main() -> None:
    if not DATA.exists():
        raise SystemExit("missing kb/data/student_lab.json; run build_student_lab.py")
    d = json.loads(DATA.read_text(encoding="utf8"))
    cases = d["cases"]
    by_case = {c["id"]: c for c in cases}
    signs = {s["id"]: s for s in d["signs"]}
    sources = {s["id"]: s for s in d["sources"]}
    concepts = {c["id"]: c for c in d["concepts"]}
    questions = d["questions"]
    counts = d["counts"]

    check("版本字段", bool(d.get("version")), str(d.get("version")))
    check("范围声明为 21 例 CR 胸部", "21" in d.get("scope", "") and "CR" in d.get("scope", ""), d.get("scope", ""))
    check("病例 21 例", len(cases) == 21, str(len(cases)))
    check("计数 cases 一致", counts["cases"] == len(cases), str(counts))
    check("计数 questions 一致", counts["questions"] == len(questions), str(counts))
    check("计数 zones 一致", counts["zones"] == sum(len(c["zones"]) for c in cases), str(counts))
    check("定位题 153", counts["locate"] == 153, str(counts))
    check("判读题 153", counts["status"] == 153, str(counts))
    check("征象题 44", counts["sign"] == 44, str(counts))
    check("征象 20 条", len(signs) == 20, str(len(signs)))
    check("来源唯一", len(sources) == len(d["sources"]), str(len(sources)))
    check("概念至少 30 条", len(concepts) >= 30, str(len(concepts)))
    check("指南至少 10 条", len(d["guidelines"]) >= 10, str(len(d["guidelines"])))

    bad_cases = []
    for c in cases:
        if not c.get("image") or not c.get("source_page") or not c.get("license"):
            bad_cases.append(c["id"] + ":meta")
        if not c.get("zones"):
            bad_cases.append(c["id"] + ":nozones")
        for z in c["zones"]:
            co = z.get("coords") or []
            if len(co) != 4 or any(not isinstance(v, (int, float)) for v in co):
                bad_cases.append(c["id"] + "/" + z["id"] + ":coords")
                continue
            x, y, w, h = co
            if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1 and x + w <= 1.001 and y + h <= 1.001):
                bad_cases.append(c["id"] + "/" + z["id"] + ":range")
            if z.get("status") not in STATUS:
                bad_cases.append(c["id"] + "/" + z["id"] + ":status")
            for sid in z.get("sign_ids", []):
                if sid not in signs:
                    bad_cases.append(c["id"] + "/" + z["id"] + ":sign=" + sid)
    check("病例字段 / 分区坐标 / 状态 / 征象引用", not bad_cases, "；".join(bad_cases[:8]))

    bad_signs = []
    for s in signs.values():
        if not s.get("appearance"):
            bad_signs.append(s["id"] + ":appearance")
        if not s.get("source_ids"):
            bad_signs.append(s["id"] + ":nosource")
        for sid in s.get("source_ids", []):
            if sid not in sources:
                bad_signs.append(s["id"] + ":source=" + sid)
    check("征象字段与来源引用", not bad_signs, "；".join(bad_signs[:8]))

    bad_concepts = []
    for c in concepts.values():
        for sid in (c.get("sign_ids") or []) + (c.get("related_sign_ids") or []):
            if sid not in signs:
                bad_concepts.append(c["id"] + ":" + sid)
    check("概念到征象引用", not bad_concepts, "；".join(bad_concepts[:8]))

    bad_q = []
    per_case = {cid: {"locate": 0, "status": 0, "sign": 0} for cid in by_case}
    for q in questions:
        qid = q.get("qid", "?")
        if q.get("type") not in ("locate", "status", "sign"):
            bad_q.append(qid + ":type")
            continue
        c = by_case.get(q.get("case_id"))
        if not c:
            bad_q.append(qid + ":case")
            continue
        z = next((x for x in c["zones"] if x["id"] == q.get("zone_id")), None)
        if not z:
            bad_q.append(qid + ":zone")
            continue
        if len(q.get("options") or []) not in (3, 4):
            bad_q.append(qid + ":options")
        if q.get("answer") not in (q.get("options") or []):
            bad_q.append(qid + ":answer")
        if q.get("answer_index") != (q.get("options") or []).index(q.get("answer")):
            bad_q.append(qid + ":index")
        if q.get("coords") != z.get("coords"):
            bad_q.append(qid + ":coords")
        if not q.get("explain"):
            bad_q.append(qid + ":explain")
        cit = q.get("citations") or {}
        if cit.get("case_id") != c["id"] or cit.get("zone_id") != z["id"]:
            bad_q.append(qid + ":citation")
        if q["type"] == "locate" and q.get("answer") != z["name"]:
            bad_q.append(qid + ":locate-answer")
        if q["type"] == "status" and q.get("answer") != STATUS[z["status"]]:
            bad_q.append(qid + ":status-answer")
        if q["type"] == "sign":
            if not z.get("sign_ids"):
                bad_q.append(qid + ":no-sign")
            else:
                first = signs.get(z["sign_ids"][0])
                if not first or q.get("answer") != first["name"]:
                    bad_q.append(qid + ":sign-answer")
            for sid in cit.get("sign_ids", []):
                if sid not in signs:
                    bad_q.append(qid + ":cite-sign=" + sid)
        per_case[c["id"]][q["type"]] += 1
    check("题目答案 / 索引 / 选项 / 坐标 / 引用", not bad_q, "；".join(bad_q[:10]))
    missing_case_q = [cid for cid, v in per_case.items() if not v["locate"] or not v["status"]]
    check("每个病例都有定位题和判读题", not missing_case_q, "；".join(missing_case_q[:8]))
    check("至少 14 例有征象题", sum(1 for v in per_case.values() if v["sign"]) >= 14,
          str(sum(1 for v in per_case.values() if v["sign"])))

    # 抽一道题做人工可读校验
    q0 = questions[0]
    check("首题可读", q0["case_id"] in by_case and q0["answer"] in q0["options"],
          json.dumps(q0, ensure_ascii=False)[:200])

    passed = sum(1 for _, ok, _ in rows if ok)
    total = len(rows)
    lines = [
        "# 学生影像实验室 · 数据自检",
        "",
        f"> 生成时间：2026-11-22 ｜ 通过 {passed}/{total}",
        "",
        "| # | 检查 | 结果 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for i, (name, ok, detail) in enumerate(rows, 1):
        lines.append(f"| {i} | {name} | {'通过' if ok else '**未通过**'} | {detail} |")
    lines += [
        "",
        "> 本自检只证明数据结构和引用可复现；不证明医学结论正确。",
        "> 正式教学前须由医学人员逐条审核。",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"\n{passed}/{total} passed -> {OUT}")
    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
