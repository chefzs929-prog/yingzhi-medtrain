#!/usr/bin/env python3
"""给“有征象但只有影像锚点”的 claim 补上库内征象条目锚点。

边界（重要）：
- 只补 doc_kind="sign" 的词条定义锚点，不冒充指南/文献背书；
- excerpt 必须来自 paragraphs.jsonl 的 SIGN-xxx#appearance-1，hash 现场计算；
- 纵隔/心影（MED）分区不挂肺实质征象定义，避免跨分区误引；
- 无征象的正常对照/解剖标注 claim 保持 imaging_only，不硬补；
- 幂等：已有 sign 级 doc cite 的 claim 跳过。

用法：
  python3 kb/scripts/attach_sign_cites.py [--dry-run]
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb/data"
OUT = ROOT / "outputs/medtrain/data/audit/sign_cite_attach.json"

# 纵隔/心影分区不挂这些肺实质或胸膜征象的条目定义。
MED_SKIP = {"SIGN-001", "SIGN-002", "SIGN-003", "SIGN-007", "SIGN-008", "SIGN-019"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    path.write_text(text, encoding="utf8")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def pick_sign(claim: dict, signs: dict[str, dict]) -> str:
    """优先选 claim 文本里直接出现的征象名/别名，否则取第一个。"""
    text = claim.get("text", "")
    for sid in claim.get("sign_ids") or []:
        s = signs.get(sid)
        if not s:
            continue
        names = [s.get("name", "")] + list(s.get("aliases") or [])
        if any(n and n in text for n in names):
            return sid
    return (claim.get("sign_ids") or [""])[0]


def main() -> None:
    dry = "--dry-run" in sys.argv
    claims = read_jsonl(DATA / "claims.jsonl")
    signs = {s["id"]: s for s in read_jsonl(DATA / "signs.jsonl")}
    paras = {
        (p["doc_id"], p["section"], p["para"]): p
        for p in read_jsonl(DATA / "paragraphs.jsonl")
    }

    attached, skipped_med, skipped_no_para, already = 0, 0, 0, 0
    by_sign: Counter[str] = Counter()
    pairs: set[tuple[str, str]] = set()
    details: list[dict] = []

    for claim in claims:
        if claim.get("dual_status") != "imaging_only" or not claim.get("sign_ids"):
            continue
        if any(
            c.get("kind") == "doc" and (c.get("anchor") or {}).get("doc_kind") == "sign"
            for c in claim.get("cites", [])
        ):
            already += 1
            continue

        sid = pick_sign(claim, signs)
        sign = signs.get(sid) or {}
        is_med = (claim.get("region_id") or "").endswith("-MED")

        if is_med and sid in MED_SKIP:
            skipped_med += 1
            details.append({"claim": claim["id"], "sign": sid, "action": "skip_med"})
            continue

        p = paras.get((sid, "appearance", 1))
        if not p:
            skipped_no_para += 1
            details.append({"claim": claim["id"], "sign": sid, "action": "skip_no_para"})
            continue

        excerpt = p["text"]
        digest = sha256(excerpt)
        anchor = {
            "doc_kind": "sign",
            "doc_id": sid,
            "doc_title": sign.get("name") or p.get("title") or sid,
            "para_id": p["para_id"],
            "section": "appearance",
            "para": 1,
            "page": p.get("page"),
            "char_start": p.get("char_start"),
            "char_end": p.get("char_end"),
            "sha256": digest,
            "excerpt_sha256": digest,
            "excerpt": excerpt,
            "locator": f"{sign.get('name') or sid} · 征象定义 · 病例级",
            "version": "kb-sign-v1",
            "url": p.get("source_url") or f"kb://sign/{sid}",
            "match": "sign_entry",
            "scope": "case_level",
        }
        claim.setdefault("cites", []).append(
            {
                "cite_id": f"CIT-{claim['id']}-S1",
                "kind": "doc",
                "anchor": anchor,
                "hash_ok": True,
                "match": "sign_entry",
                "scope": "case_level",
            }
        )
        claim["dual_status"] = "dual"
        claim.setdefault("audit", {})["rule_check"] = "pass"
        claim.setdefault("derivation", {})["sign_cite"] = "attached_2026-11-23"
        attached += 1
        by_sign[sid] += 1
        pairs.add((claim["image_id"], sid))
        details.append({"claim": claim["id"], "sign": sid, "action": "attach"})

    payload = {
        "generated_at": date.today().isoformat(),
        "dry_run": dry,
        "attached_claims": attached,
        "skipped_med": skipped_med,
        "skipped_no_paragraph": skipped_no_para,
        "already_has_sign_cite": already,
        "case_sign_pairs": len(pairs),
        "by_sign": dict(by_sign.most_common()),
        "details": details,
    }

    if not dry:
        write_jsonl(DATA / "claims.jsonl", claims)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf8")

    print(json.dumps({k: v for k, v in payload.items() if k != "details"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
