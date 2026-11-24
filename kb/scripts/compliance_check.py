#!/usr/bin/env python3
"""合规门禁：来源、许可、隐私、表述边界、图像一致性。

用法：python3 kb/scripts/compliance_check.py
退出码 0 表示全部通过。
"""
import json
import re
import sys
from pathlib import Path

import sign_links as sign_links_mod

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

ALLOWED_LICENSE = re.compile(r"^(cc0|cc by 2\.0|cc by 3\.0|cc by 4\.0|cc by-sa 2\.0|cc by-sa 3\.0|cc by-sa 4\.0|public domain)$", re.I)
FORBIDDEN_CLAIMS = ["诊断为", "确诊为", "可以确诊", "建议手术", "建议用药", "推荐用药",
                    "必须手术", "无需治疗", "就是癌", "一定是", "确定为"]
PRIVACY_PATTERNS = [r"姓名[:：]", r"身份证", r"住院号", r"门诊号", r"患者姓名", r"\bMRN\b"]


def load(name):
    return [json.loads(l) for l in (DATA / name).read_text(encoding="utf8").splitlines() if l.strip()]


def main():
    signs = load("signs.jsonl")
    standards = load("standards.jsonl")
    cases = load("cases.jsonl")
    guidelines = load("guidelines.jsonl")
    groups = load("groups.jsonl")
    links = load("sign_links.jsonl") if (DATA / "sign_links.jsonl").exists() else []
    sources = {s["id"]: s for s in json.loads((DATA / "sources.json").read_text(encoding="utf8"))["sources"]}

    errors, warnings = [], []
    if not (DATA / "sign_links.jsonl").exists():
        errors.append("缺少 sign_links.jsonl（征象文字与影像区域关联）")

    # 1. 来源完整性
    for s in signs:
        if not s.get("sources"):
            errors.append(f"{s['id']} 缺少来源")
        for sid in s.get("sources", []):
            if sid not in sources:
                errors.append(f"{s['id']} 引用了未登记来源 {sid}")

    # 1b. 指南条款完整性
    std_ids = {s["id"] for s in standards}
    for g in guidelines:
        if g.get("standard_id") not in std_ids:
            errors.append(f"{g['id']} 关联的标准不存在")
        if not g.get("source_url", "").startswith("http"):
            errors.append(f"{g['id']} 缺少来源链接")
        if not isinstance(g.get("version_year"), int):
            errors.append(f"{g['id']} 缺少版本年份")
        if not g.get("conditions"):
            errors.append(f"{g['id']} 缺少适用条件")
        if g.get("status") not in ("active", "deprecated"):
            errors.append(f"{g['id']} 状态不合法")

    # 2. 标准必须有官方入口与许可说明
    for s in standards:
        if not s.get("official_url", "").startswith("http"):
            errors.append(f"{s['id']} 缺少官方链接")
        if not s.get("license_note"):
            errors.append(f"{s['id']} 缺少版权说明")

    # 2b. 影像分组
    gids = {g["id"] for g in groups}
    for g in groups:
        if not g.get("criteria"):
            errors.append(f"{g['id']} 缺少归类依据")
        if not g.get("caution"):
            errors.append(f"{g['id']} 缺少使用提醒")
        for sid in g.get("sign_ids", []):
            if sid not in {s["id"] for s in signs}:
                errors.append(f"{g['id']} 关联征象 {sid} 不存在")
    for c in cases:
        if c.get("group_id") not in gids:
            errors.append(f"{c['id']} 未归入有效影像组")

    # 2c. 两级分类：部位（一级）→ 病症（二级）
    tax_path = ROOT / "data" / "taxonomy.json"
    if not tax_path.exists():
        errors.append("缺少 taxonomy.json（一级部位/二级病症）")
    else:
        tax = json.loads(tax_path.read_text(encoding="utf8"))
        region_ids = {r["id"] for r in tax.get("regions", [])}
        covered = set()
        for r in tax.get("regions", []):
            if not r.get("name"):
                errors.append(f"{r['id']} 缺少部位名称")
            for gid in r.get("groups", []):
                if gid not in gids:
                    errors.append(f"{r['id']} 引用了不存在的影像组 {gid}")
                if gid in covered:
                    errors.append(f"影像组 {gid} 重复归属多个部位")
                covered.add(gid)
        for g in groups:
            if g.get("region_id") not in region_ids:
                errors.append(f"{g['id']} 的 region_id 无效：{g.get('region_id')}")
        missing = gids - covered
        if missing:
            errors.append("以下影像组未纳入两级分类：" + "、".join(sorted(missing)))

    # 3. 图像许可、来源、文件、隐私
    attr = (ROOT / "licenses" / "ATTRIBUTION.md").read_text(encoding="utf8")
    for c in cases:
        if not ALLOWED_LICENSE.match(c.get("license", "")):
            errors.append(f"{c['id']} 许可不在白名单：{c.get('license')}")
        if not c.get("source_page", "").startswith("https://commons.wikimedia.org/"):
            errors.append(f"{c['id']} 来源页不是 Commons 链接")
        if not (ROOT / c.get("image", "")).exists():
            errors.append(f"{c['id']} 图像文件缺失")
        if c.get("image", "").split("/")[-1] not in attr:
            errors.append(f"{c['id']} 未出现在署名文件中")
        pc = c.get("privacy_check")
        if pc not in ("human_verified_no_identifier", "verified_no_identifier"):
            if pc == "auto_screened":
                warnings.append(f"{c['id']} 仅自动筛查无标识，未逐张人工复核")
            else:
                errors.append(f"{c['id']} 未通过隐私核验标记（{pc}）")
        for tag in c.get("sign_tags", []):
            if tag not in {s["id"] for s in signs}:
                errors.append(f"{c['id']} 标签 {tag} 不存在")

    # 3b. 图文关联：文字锚点、图像锚点、侧别与标注来源
    signs_by_id = {s["id"]: s for s in signs}
    cases_by_id = {c["id"]: c for c in cases}
    errors.extend(sign_links_mod.validate(links, signs_by_id, cases_by_id, sources))
    for sign_id in {x["sign_id"] for x in links}:
        rows = [x for x in links if x["sign_id"] == sign_id]
        try:
            sign_links_mod.segments_for(signs_by_id[sign_id]["appearance"], rows)
        except Exception as exc:  # noqa: BLE001 - 合规报告需要保留具体原因
            errors.append(f"{sign_id} 文字分段失败：{exc}")
    if not links:
        warnings.append("尚无征象文字与影像区域关联")

    # 4. 表述边界
    for rows, label in ((signs, "sign"), (standards, "standard"), (cases, "case"),
                        (guidelines, "guideline"), (links, "sign_link")):
        for r in rows:
            blob = json.dumps(r, ensure_ascii=False)
            for w in FORBIDDEN_CLAIMS:
                if w in blob:
                    errors.append(f"{label} {r.get('id')} 含越界表述：{w}")

    # 5. 隐私词
    for rows, label in ((signs, "sign"), (standards, "standard"), (cases, "case"),
                        (guidelines, "guideline"), (links, "sign_link")):
        for r in rows:
            blob = json.dumps(r, ensure_ascii=False)
            for pat in PRIVACY_PATTERNS:
                if re.search(pat, blob):
                    errors.append(f"{label} {r.get('id')} 命中隐私模式 {pat}")

    # 6. 覆盖率提醒
    for s in signs:
        if not s.get("aliases"):
            warnings.append(f"{s['id']} 无别名，可能影响召回")
    no_case_parts = {"前列腺", "卵巢", "骨", "关节", "胸膜", "心脏", "纵隔", "胆囊", "肠道"}
    have = {c.get("body_part") for c in cases}
    for p in sorted(no_case_parts - have):
        warnings.append(f"部位「{p}」暂无公开影像对照")

    report = {
        "signs": len(signs), "standards": len(standards), "cases": len(cases),
        "guidelines": len(guidelines), "groups": len(groups),
        "sign_links": len(links),
        "sources": len(sources), "errors": errors, "warnings": warnings,
        "status": "pass" if not errors else "fail",
    }
    (ROOT / "index" / "compliance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")

    print(f"signs={len(signs)} standards={len(standards)} cases={len(cases)} "
          f"guidelines={len(guidelines)} groups={len(groups)} sign_links={len(links)} "
          f"sources={len(sources)}")
    print(f"errors={len(errors)} warnings={len(warnings)}")
    for e in errors:
        print("  ERROR", e)
    for w in warnings[:8]:
        print("  WARN ", w)
    print("STATUS:", report["status"].upper())
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
