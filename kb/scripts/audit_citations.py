#!/usr/bin/env python3
"""引用一致性审计：把“双引用”从口号变成可核对的数据。

检查范围：
  1. claim 的 image_id / region_id 是否存在；
  2. spatial cite 的 bbox 是否合法、是否与 claim 的病例/分区一致；
  3. doc cite 的 doc_id 是否能在 guidelines / signs / concepts / sources 中找到；
  4. doc excerpt 的 sha256 是否与记录一致，hash_ok 是否诚实；
  5. dual_status 是否与 cites 的实际组合一致；
  6. audit.rule_check 是否与本次检查结论一致。

输出：
  outputs/medtrain/data/audit/citation_audit.json
  docs/引用一致性审计_2026-11-23.md
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb/data"
OUT_JSON = ROOT / "outputs/medtrain/data/audit/citation_audit.json"
OUT_MD = ROOT / "docs/引用一致性审计_2026-11-23.md"


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def zone_key(region_id: str, case_id: str) -> str:
    """REG-001-RUL -> RUL；兼容 region_id 直接就是分区 id 的情况。"""
    prefix = f"REG-{case_id.split('-')[-1]}-"
    if region_id.startswith(prefix):
        return region_id[len(prefix):]
    parts = region_id.split("-")
    return parts[-1] if parts else region_id


def main() -> None:
    chest = json.loads((DATA / "chest_reading.json").read_text(encoding="utf8"))
    claims = read_jsonl(DATA / "claims.jsonl")
    signs = read_jsonl(DATA / "signs.jsonl")
    concepts = read_jsonl(DATA / "concepts.jsonl")
    guidelines = read_jsonl(DATA / "guidelines.jsonl")
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf8")).get("sources", [])
    all_cases = read_jsonl(DATA / "cases.jsonl")
    all_regions = read_jsonl(DATA / "regions.jsonl")

    # 全库病例/分区：cases.jsonl + regions.jsonl；chest_reading 只用于标记胸片发布集。
    cases = {c["id"]: c for c in all_cases}
    enabled = {c["id"] for c in chest["cases"] if c.get("enabled")}
    zones = {(r["image_id"], r["id"]): r for r in all_regions}
    # chest_reading 的分区 id 是短名（RUL），regions.jsonl 是 REG-001-RUL；两套都建索引。
    for c in chest["cases"]:
        for z in c.get("zones") or []:
            zones.setdefault((c["id"], z["id"]), z)
            zones.setdefault((c["id"], f"REG-{c['id'].split('-')[-1]}-{z['id']}"), z)
    sign_ids = {s["id"] for s in signs}
    concept_ids = {c["id"] for c in concepts}
    guideline_ids = {g["id"] for g in guidelines}
    source_ids = {s["id"] for s in sources}

    doc_known = {
        "guideline": guideline_ids,
        "sign": sign_ids,
        "concept": concept_ids,
        "source": source_ids,
    }

    results = []
    for claim in claims:
        checks: list[dict] = []

        def add(name: str, ok: bool, detail: str = "") -> None:
            checks.append({"name": name, "ok": bool(ok), "detail": detail})

        case_id = claim.get("image_id", "")
        region_id = claim.get("region_id", "")
        zid = zone_key(region_id, case_id)
        case = cases.get(case_id)
        zone = zones.get((case_id, region_id)) or zones.get((case_id, zid))

        add("病例存在", case is not None, case_id)
        add("分区存在", zone is not None, f"{case_id}/{zid}")

        spatial = [c for c in claim.get("cites", []) if c.get("kind") == "spatial"]
        docs = [c for c in claim.get("cites", []) if c.get("kind") == "doc"]

        add("有 spatial 引用", len(spatial) == 1, f"{len(spatial)} 条")

        for i, cite in enumerate(spatial):
            anchor = cite.get("anchor") or {}
            bbox = anchor.get("bbox") or []
            bbox_ok = (
                len(bbox) == 4
                and all(isinstance(v, (int, float)) for v in bbox)
                and 0 <= bbox[0] < bbox[2] <= 1
                and 0 <= bbox[1] < bbox[3] <= 1
            )
            add(f"spatial[{i}] bbox 合法", bbox_ok, str(bbox))
            add(
                f"spatial[{i}] 与 claim 同病例/分区",
                anchor.get("image_id") == case_id and anchor.get("region_id") == region_id,
                f"{anchor.get('image_id')}/{anchor.get('region_id')}",
            )
            if zone:
                coords = zone.get("coords") or []
                # coords 是 [x, y, w, h]；bbox 是 [x1, y1, x2, y2]。
                add(
                    f"spatial[{i}] bbox 落在分区框内",
                    len(coords) == 4
                    and bbox_ok
                    and coords[0] <= bbox[0] and coords[1] <= bbox[1]
                    and bbox[2] <= coords[0] + coords[2]
                    and bbox[3] <= coords[1] + coords[3],
                    f"zone={coords}",
                )

        for i, cite in enumerate(docs):
            anchor = cite.get("anchor") or {}
            kind = anchor.get("doc_kind", "")
            did = anchor.get("doc_id", "")
            known = doc_known.get(kind, set())
            add(f"doc[{i}] doc_id 可解析", did in known, f"{kind}:{did}")
            excerpt = anchor.get("excerpt", "")
            recorded = anchor.get("excerpt_sha256", "")
            actual = sha256(excerpt) if excerpt else ""
            add(f"doc[{i}] excerpt hash 一致", bool(excerpt) and actual == recorded, did)
            add(
                f"doc[{i}] hash_ok 诚实",
                bool(cite.get("hash_ok")) == (bool(excerpt) and actual == recorded),
                f"recorded={cite.get('hash_ok')}",
            )

        if docs:
            actual_dual = "dual" if spatial and docs and all(c.get("hash_ok") for c in docs) else "broken"
        else:
            actual_dual = "imaging_only" if spatial else "broken"
        add("dual_status 与 cites 一致", claim.get("dual_status") == actual_dual,
            f"recorded={claim.get('dual_status')} actual={actual_dual}")

        expected_rule = "pass" if all(c["ok"] for c in checks) else "fail"
        add(
            "audit.rule_check 与本次检查一致",
            (claim.get("audit") or {}).get("rule_check") == expected_rule,
            f"recorded={(claim.get('audit') or {}).get('rule_check')} actual={expected_rule}",
        )

        results.append(
            {
                "id": claim["id"],
                "case_id": case_id,
                "zone_id": zid,
                "in_publish_set": case_id in enabled,
                "dual_status": claim.get("dual_status"),
                "actual_dual": actual_dual,
                "sign_ids": claim.get("sign_ids") or [],
                "doc_kinds": [(c.get("anchor") or {}).get("doc_kind") for c in docs],
                "passed": all(c["ok"] for c in checks),
                "checks": checks,
            }
        )

    def tier(r: dict) -> str:
        kinds = [k for k in r["doc_kinds"] if k]
        if not kinds:
            return "none"
        if all(k in ("guideline", "source") for k in kinds):
            return "external"
        if all(k in ("sign", "concept") for k in kinds):
            return "internal"
        return "mixed"

    def summary(rows: list[dict]) -> dict:
        return {
            "claims": len(rows),
            "passed": sum(1 for r in rows if r["passed"]),
            "failed": sum(1 for r in rows if not r["passed"]),
            "dual": sum(1 for r in rows if r["dual_status"] == "dual"),
            "dual_external": sum(1 for r in rows if r["dual_status"] == "dual" and tier(r) == "external"),
            "dual_internal": sum(1 for r in rows if r["dual_status"] == "dual" and tier(r) == "internal"),
            "dual_mixed": sum(1 for r in rows if r["dual_status"] == "dual" and tier(r) == "mixed"),
            "imaging_only": sum(1 for r in rows if r["dual_status"] == "imaging_only"),
            "broken": sum(1 for r in rows if r["dual_status"] == "broken"),
            "with_sign": sum(1 for r in rows if r["sign_ids"]),
            "with_sign_dual": sum(1 for r in rows if r["sign_ids"] and r["dual_status"] == "dual"),
            "with_sign_uncovered": sum(1 for r in rows if r["sign_ids"] and r["dual_status"] != "dual"),
            "no_sign": sum(1 for r in rows if not r["sign_ids"]),
        }

    publish = [r for r in results if r["in_publish_set"]]
    all_summary = summary(results)
    pub_summary = summary(publish)

    def pair_set(rows: list[dict], only_dual: bool = False) -> set[tuple[str, str]]:
        out = set()
        for r in rows:
            if only_dual and r["dual_status"] != "dual":
                continue
            for sid in r["sign_ids"]:
                out.add((r["case_id"], sid))
        return out

    all_pairs = pair_set(results)
    all_pairs_dual = pair_set(results, only_dual=True)
    pub_pairs = pair_set(publish)
    pub_pairs_dual = pair_set(publish, only_dual=True)
    pair_stats = {
        "all": {"total": len(all_pairs), "dual": len(all_pairs_dual)},
        "publish": {"total": len(pub_pairs), "dual": len(pub_pairs_dual)},
    }
    med_uncovered = sum(
        1 for r in results
        if r["sign_ids"] and r["dual_status"] != "dual" and r["zone_id"] == "MED"
    )

    by_check = defaultdict(lambda: {"total": 0, "failed": 0})
    for row in results:
        for check in row["checks"]:
            by_check[check["name"]]["total"] += 1
            if not check["ok"]:
                by_check[check["name"]]["failed"] += 1

    failures = [
        {
            "id": r["id"],
            "case_id": r["case_id"],
            "zone_id": r["zone_id"],
            "in_publish_set": r["in_publish_set"],
            "failed": [c for c in r["checks"] if not c["ok"]],
        }
        for r in results
        if not r["passed"]
    ]

    payload = {
        "generated_at": date.today().isoformat(),
        "scope": {
            "all_claims": len(results),
            "publish_cases": len(enabled),
            "publish_claims": len(publish),
            "note": "publish 指 chest_reading.json 中 enabled=true 的 21 例胸片；全库还包含非胸片/未启用病例。",
        },
        "summary": {"all": all_summary, "publish": pub_summary},
        "case_sign_pairs": pair_stats,
        "dual_coverage": {
            "all": round(all_summary["dual"] / max(all_summary["claims"], 1), 4),
            "publish": round(pub_summary["dual"] / max(pub_summary["claims"], 1), 4),
            "note": "分子含指南级与征象条目级两种第二锚点，不等于指南背书。",
        },
        "sign_coverage": {
            "all": round(all_summary["with_sign_dual"] / max(all_summary["with_sign"], 1), 4),
            "publish": round(pub_summary["with_sign_dual"] / max(pub_summary["with_sign"], 1), 4),
            "note": "分母只算有征象的 claims；正常对照/解剖标注不计入。",
        },
        "by_check": dict(sorted(by_check.items())),
        "failures": failures,
        "results": results,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf8")

    def pct(n: int, d: int) -> str:
        return f"{n / d * 100:.1f}%" if d else "—"

    lines = [
        "# 引用一致性审计 · 2026-11-23",
        "",
        "> 脚本：`kb/scripts/audit_citations.py`｜原始结果：`outputs/medtrain/data/audit/citation_audit.json`",
        "> 口径：`publish` = `chest_reading.json` 中 `enabled=true` 的 21 例胸片；`all` = `claims.jsonl` 全库。",
        "",
        "## 一、结论",
        "",
        f"先看分母：全库 **{all_summary['claims']}** 条 claims 中 **{all_summary['no_sign']}** 条没有征象（正常对照、解剖标注、未逐区标注），本身不存在“第二锚点”；真正可谈双引用的是 **{all_summary['with_sign']}** 条有征象 claims。发布集同理：**{pub_summary['claims']}** 条中 **{pub_summary['no_sign']}** 条无征象，**{pub_summary['with_sign']}** 条有征象。",
        "",
        "| 口径 | 全库 | 胸片发布集 |",
        "| --- | ---: | ---: |",
        f"| claims 总数 | {all_summary['claims']} | {pub_summary['claims']} |",
        f"| 无征象（不适用第二锚点） | {all_summary['no_sign']} | {pub_summary['no_sign']} |",
        f"| 有征象（可挂第二锚点） | {all_summary['with_sign']} | {pub_summary['with_sign']} |",
        f"| 指南/文献级双引用（E1+外部条款） | {all_summary['dual_external']} | {pub_summary['dual_external']} |",
        f"| 征象条目级锚点（E1+库内词条） | {all_summary['dual_internal']} | {pub_summary['dual_internal']} |",
        f"| 有征象 claims 的二级锚点覆盖 | {all_summary['with_sign_dual']}/{all_summary['with_sign']}（{pct(all_summary['with_sign_dual'], all_summary['with_sign'])}） | {pub_summary['with_sign_dual']}/{pub_summary['with_sign']}（{pct(pub_summary['with_sign_dual'], pub_summary['with_sign'])}） |",
        f"| 病例-征象对覆盖（去重） | {pair_stats['all']['dual']}/{pair_stats['all']['total']} | {pair_stats['publish']['dual']}/{pair_stats['publish']['total']} |",
        f"| 引用检查通过 | {all_summary['passed']}/{all_summary['claims']} | {pub_summary['passed']}/{pub_summary['claims']} |",
        "",
        "**准确话术**（替换旧说法）：",
        "",
        f"> 有征象的 claims 已基本做到“影像分区锚点 + 第二锚点”：其中 {all_summary['dual_external']} 条挂指南/文献条款，{all_summary['dual_internal']} 条挂库内征象条目定义；正常对照与解剖标注 claims 保持影像单锚点，不硬补。指南级双引用仍是 {all_summary['dual_external']}/{all_summary['claims']}，不能表述为“全库每条都双引用”。",
        "",
        f"**为什么不全补成指南**：指南条款讲的是分类与随访阈值，多数胸片征象（气胸、积液、实变、不张）没有可对齐的条款；硬挂会制造伪引用。征象条目锚点解决“描述有出处”，指南锚点解决“处理有依据”，两者不能混算。当前仍有 {all_summary['with_sign_uncovered']} 条有征象 claims 未挂第二锚点：其中 {med_uncovered} 条是纵隔/心影分区（{pub_summary['with_sign_uncovered']} 条属发布集；病例级文本复制到该分区，挂肺实质征象会跨分区误引），另 1 条是 broken 演示样本。",
        "",
        "## 二、逐项检查失败分布（全库）",
        "",
        "| 检查项 | 总次数 | 失败 |",
        "| --- | ---: | ---: |",
    ]
    for name, stat in sorted(by_check.items(), key=lambda kv: (-kv[1]["failed"], kv[0])):
        lines.append(f"| {name} | {stat['total']} | {stat['failed']} |")

    lines += ["", "## 三、失败明细", ""]
    if failures:
        lines += ["| claim | 病例/分区 | 是否发布集 | 失败项 |", "| --- | --- | --- | --- |"]
        for f in failures:
            detail = "；".join(f"{c['name']}（{c['detail']}）" for c in f["failed"])
            lines.append(
                f"| `{f['id']}` | {f['case_id']}/{f['zone_id']} | {'是' if f['in_publish_set'] else '否'} | {detail} |"
            )
    else:
        lines.append("无。")

    lines += [
        "",
        "## 四、处置建议",
        "",
        "1. **分两档汇报**：对外主指标用“有征象 claims 的二级锚点覆盖”（全库 85/101、发布集 28/35），同时明示指南级只有 9/434；不要用 87/434 冒充“全库双引用”。",
        "2. **保留 broken 演示样本**：`CLM-011-BROKEN` 是故意构造的 hash 不一致样本，用于证明拦截有效；报告中单列，不计入胸片发布集。",
        "3. **纵隔/心影分区暂不补词条锚点**：该分区 15 条 claim 是病例级文本复制，挂肺实质征象会跨分区误引；若要补，应先做分区级文本重写，而不是直接加引用。",
        "4. **指南级仍按条件匹配**：只有 claim 的分类/尺寸/随访语境与条款条件对齐时才挂指南；条件不足时保持词条级或影像单锚点。",
        "5. **问答层单独统计**：学生实验室的 L1 来自 `sign.sources`，不是 claim 的 doc cite；应另做“问答双引用覆盖率”，不要与 claims 级混用。",
        "6. **每次构建跑一次**：把本脚本加入 `medtrain/build.py` 之后的检查步骤，失败即阻断发布。",
        "",
        "## 五、复现",
        "",
        "```bash",
        "python3 kb/scripts/attach_sign_cites.py   # 首次补齐；幂等，可重复跑",
        "python3 kb/scripts/audit_citations.py",
        "```",
        "",
    ]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf8")

    print(json.dumps({"all": all_summary, "publish": pub_summary}, ensure_ascii=False, indent=1))
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
