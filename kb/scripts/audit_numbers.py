#!/usr/bin/env python3
"""数字口径审计：把“到底多少例/多少条/多少双引用”固定成一张表。

背景：
  仓库里同时存在“全库知识底座”“胸片教学发布集”“学生实验室发布子集”三套口径，
  旧文档还留有 596/615 分区、580/599 双引用等历史数字。评审一旦交叉核对就会打架。

输出：
  docs/数字口径表.md
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb/data"
OUT = ROOT / "docs/数字口径表.md"


def jsonl(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf8").splitlines() if l.strip()]


def main() -> None:
    cases = jsonl("cases.jsonl")
    regions = jsonl("regions.jsonl")
    claims = jsonl("claims.jsonl")
    signs = jsonl("signs.jsonl")
    concepts = jsonl("concepts.jsonl")
    guidelines = jsonl("guidelines.jsonl")
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf8")).get("sources", [])
    chest = json.loads((DATA / "chest_reading.json").read_text(encoding="utf8"))
    lab = json.loads((DATA / "student_lab.json").read_text(encoding="utf8"))
    quiz = json.loads((DATA / "quiz_bank.json").read_text(encoding="utf8"))
    exam = json.loads((DATA / "exam_cases.json").read_text(encoding="utf8"))

    chest_cases = chest["cases"]
    chest_enabled = [c for c in chest_cases if c.get("enabled")]
    chest_zones = sum(len(c.get("zones") or []) for c in chest_cases)
    chest_claims = [c for c in claims if c["image_id"] in {x["id"] for x in chest_enabled}]
    dual_all = sum(1 for c in claims if c.get("dual_status") == "dual")
    dual_chest = sum(1 for c in chest_claims if c.get("dual_status") == "dual")
    broken = sum(1 for c in claims if c.get("dual_status") == "broken")

    def tier(c):
        kinds = [(x.get("anchor") or {}).get("doc_kind") for x in c.get("cites", []) if x.get("kind") == "doc"]
        kinds = [k for k in kinds if k]
        if not kinds:
            return "none"
        if all(k in ("guideline", "source") for k in kinds):
            return "external"
        if all(k in ("sign", "concept") for k in kinds):
            return "internal"
        return "mixed"

    def stats(rows):
        ws = [c for c in rows if c.get("sign_ids")]
        return {
            "dual": sum(1 for c in rows if c.get("dual_status") == "dual"),
            "ext": sum(1 for c in rows if c.get("dual_status") == "dual" and tier(c) == "external"),
            "int": sum(1 for c in rows if c.get("dual_status") == "dual" and tier(c) == "internal"),
            "ws": len(ws),
            "wsd": sum(1 for c in ws if c.get("dual_status") == "dual"),
        }

    sa, sb = stats(claims), stats(chest_claims)

    rows = [
        ("A. 全库知识底座", "病例", len(cases), "`kb/data/cases.jsonl`", "内部数据审计、Agent 召回压力测试", "不要对外说“教学病例 120 例”"),
        ("A. 全库知识底座", "分区", len(regions), "`kb/data/regions.jsonl`", "同上", "旧文档 596/615 已废弃"),
        ("A. 全库知识底座", "claims 结论", len(claims), "`kb/data/claims.jsonl`", "引用审计、双引用统计", "旧文档 580/599/582 已废弃"),
        ("A. 全库知识底座", "有征象 claims", sa["ws"], "`claims.sign_ids` 非空", "双引用的真实分母", "无征象 claims 不适用第二锚点"),
        ("A. 全库知识底座", "指南/文献级双引用", sa["ext"], "`dual_status=dual` 且 doc_kind∈{guideline,source}", "外部背书", "全库仅 9 条，不要夸大"),
        ("A. 全库知识底座", "征象条目级锚点", sa["int"], "`dual_status=dual` 且 doc_kind∈{sign,concept}", "描述有出处", "不等于指南背书"),
        ("A. 全库知识底座", "有征象 claims 二级锚点覆盖", f'{sa["wsd"]}/{sa["ws"]}', "有征象且 dual", "对外主指标", "不要写成 87/434"),
        ("A. 全库知识底座", "broken 演示样本", broken, "`CLM-011-BROKEN`", "证明拦截有效", "不计入胸片发布集"),
        ("A. 全库知识底座", "征象", len(signs), "`kb/data/signs.jsonl`", "检索层规模", "学生实验室只发布 20 条"),
        ("A. 全库知识底座", "概念", len(concepts), "`kb/data/concepts.jsonl`", "检索层规模", "学生实验室只发布 58 条"),
        ("A. 全库知识底座", "指南条款", len(guidelines), "`kb/data/guidelines.jsonl`", "指南命中", "学生实验室只发布 12 条"),
        ("A. 全库知识底座", "来源登记", len(sources), "`kb/data/sources.json`", "来源可查", "—"),
        ("B. 胸片教学发布集", "病例（全部）", len(chest_cases), "`chest_reading.json`", "构建产物", "—"),
        ("B. 胸片教学发布集", "病例（启用）", len(chest_enabled), "`chest_reading.json enabled=true`", "对外演示、课堂、问答", "对外统一说 21 例"),
        ("B. 胸片教学发布集", "分区", chest_zones, "`chest_reading.json zones`", "153 分区、第四态 58", "—"),
        ("B. 胸片教学发布集", "claims", len(chest_claims), "`claims.jsonl` 与 21 例交集", "发布集引用审计", "—"),
        ("B. 胸片教学发布集", "有征象 claims", sb["ws"], "`claims.sign_ids` 非空", "双引用的真实分母", "64 条无征象不适用"),
        ("B. 胸片教学发布集", "指南/文献级双引用", sb["ext"], "`dual_status=dual` 且 doc_kind∈{guideline,source}", "指南级 4/99，必须如实说", "不要写“99 条都双引用”"),
        ("B. 胸片教学发布集", "征象条目级锚点", sb["int"], "`dual_status=dual` 且 doc_kind∈{sign,concept}", "描述有出处", "不等于指南背书"),
        ("B. 胸片教学发布集", "有征象 claims 二级锚点覆盖", f'{sb["wsd"]}/{sb["ws"]}', "有征象且 dual", "对外主指标", "不要用 30/99 冒充全量"),
        ("C. 学生实验室发布", "病例", len(lab.get("cases", [])), "`student_lab.json`", "问答/陪练/自测/小组", "与课堂 21 例同源"),
        ("C. 学生实验室发布", "征象", len(lab.get("signs", [])), "`student_lab.json`", "问答命中范围", "全库是 60 条"),
        ("C. 学生实验室发布", "概念", len(lab.get("concepts", [])), "`student_lab.json`", "概念反查", "全库是 136 条"),
        ("C. 学生实验室发布", "指南条款", len(lab.get("guidelines", [])), "`student_lab.json`", "指南命中", "全库是 47 条"),
        ("C. 学生实验室发布", "规则题", len(lab.get("questions", [])), "`student_lab.json`", "自测/课堂题池", "定位 153/判读 153/征象 44"),
        ("D. 题库", "规则题（全量）", len(quiz.get("questions", [])), "`kb/data/quiz_bank.json`", "内部题库", "不要与学生实验室 350 题混用"),
        ("E. 病例题", "病例", len(exam.get("cases", [])), "`kb/data/exam_cases.json`", "病例题页面", "与课堂 21 例不是同一批"),
        ("E. 病例题", "对比对", len(exam.get("pairs", [])), "`kb/data/exam_cases.json`", "对比阅片", "—"),
    ]

    # 扫描旧文档中的历史数字，提示替换。
    pat = re.compile(r"(596|615|580|599|582)\s*(个)?\s*(分区|双引用|结论)")
    legacy = []
    for path in list((ROOT / "docs").glob("*.md")) + list((ROOT / "outputs").glob("*.md")) + [ROOT / "README.md"]:
        if path == OUT:
            continue
        try:
            text = path.read_text(encoding="utf8")
        except Exception:
            continue
        head = "\n".join(text.splitlines()[:6])
        if "历史文档（数字已废弃）" in head:
            continue
        for m in pat.finditer(text):
            line = text[:m.start()].count("\n") + 1
            line_text = text.splitlines()[line - 1] if line - 1 < len(text.splitlines()) else ""
            # 已经明确标注“已废弃/历史口径/旧文档”的行是说明，不是仍在使用的旧数字。
            if any(w in line_text for w in ("已废弃", "历史口径", "旧文档", "不要再说")):
                continue
            legacy.append((str(path.relative_to(ROOT)), line, m.group(0)))

    lines = [
        "# 数字口径表 · 2026-11-23",
        "",
        "> 脚本：`kb/scripts/audit_numbers.py`。所有对外材料只引用本表 A/B/C 三套口径之一，并写明是哪一套。",
        "",
        "## 一、一句话口径",
        "",
        f"- **对外演示**：21 例胸片、153 个教学分区、99 条 claims（35 条有征象，28 条已挂第二锚点；其中指南级 4 条）、350 道规则题、20 条征象、58 个概念、12 条指南。",
        f"- **内部知识底座**：{len(cases)} 例、{len(regions)} 个分区、{len(claims)} 条 claims（{sa['ws']} 条有征象，{sa['wsd']} 条已挂第二锚点；其中指南级 {sa['ext']} 条）、{len(signs)} 条征象、{len(concepts)} 个概念、{len(guidelines)} 条指南。",
        f"- **不要再说**：“每条答案都同时带 E1+L1”“580/599 条双引用结论”“596/615 个分区”。",
        "",
        "## 二、三套口径",
        "",
        "| 口径 | 维度 | 数字 | 来源 | 可用场景 | 不要用于 |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for scope, dim, n, src, use, avoid in rows:
        lines.append(f"| {scope} | {dim} | {n} | {src} | {use} | {avoid} |")

    lines += [
        "",
        "## 三、必须改写的三句话",
        "",
        "| 旧说法 | 问题 | 新说法 |",
        "| --- | --- | --- |",
        "| “每条答案都同时带 E1+L1” | 指南级 dual 只有 4/99 | “有征象 claims 已有 28/35 挂第二锚点；其中指南级 4 条，其余为征象条目定义，不能混称指南背书” |",
        "| “580/599 条双引用结论” | 与当前 434 claims 不符 | “434 条 claims，其中 101 条有征象、85 条已挂第二锚点；指南级 9 条” |",
        "| “596/615 个分区” | 与当前 440 个分区不符 | “全库 440 个分区；胸片发布集 153 个教学分区” |",
        "",
        "## 四、历史数字扫描",
        "",
    ]
    if legacy:
        lines += ["| 文件 | 行 | 命中 |", "| --- | ---: | --- |"]
        for f, line, hit in legacy:
            lines.append(f"| `{f}` | {line} | `{hit}` |")
        lines += ["", "> 以上为历史口径，保留作为演进记录；对外材料不要再引用。"]
    else:
        lines.append("未发现 596/615/580/599/582 等历史数字。")

    lines += [
        "",
        "## 五、复现",
        "",
        "```bash",
        "python3 kb/scripts/audit_numbers.py",
        "```",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"legacy hits: {len(legacy)}")


if __name__ == "__main__":
    main()
