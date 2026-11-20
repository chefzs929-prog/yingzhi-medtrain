#!/usr/bin/env python3
"""给知识库补一条「引用完整性校验失败」的演示结论。

背景：120 例重建后，claims 全部通过校验，`引用校验拦截` 这条产品能力在演示里
没有可触发的样本。本脚本在 CASE-011（甲状腺 TR4）的腺体实质分区追加一条
hash 对不上的结论，前端会把它排除在回答之外，并在 notes 里写明拦截了哪一条。

幂等：重复运行只会覆盖同 id 的样本，不会重复追加。
用法：
  python3 kb/scripts/add_integrity_demo.py
"""
import json
from pathlib import Path

CLAIMS = Path("kb/data/claims.jsonl")
CASE_ID = "CASE-011"
REGION_ID = "REG-011-PAR"
DEMO_ID = "CLM-011-BROKEN"


def main():
    rows = [json.loads(l) for l in CLAIMS.read_text(encoding="utf-8").splitlines() if l.strip()]
    base = next((r for r in rows if r["id"] == "CLM-011-PAR"), None)
    if not base:
        raise SystemExit("缺少 CLM-011-PAR，先运行 rebuild_regions_claims.py")

    doc_cite = next((c for c in base.get("cites", []) if c.get("kind") == "doc"), None)
    anchor = dict((doc_cite or {}).get("anchor") or {})
    anchor.update({
        "doc_kind": anchor.get("doc_kind", "guideline"),
        "doc_id": anchor.get("doc_id", "GL-TIRADS-03"),
        "doc_title": anchor.get("doc_title", "ACR TI-RADS 2017"),
        "locator": anchor.get("locator", "TR4 结节处理"),
        "excerpt": "（演示样本）TR4 结节 ≥1.5 cm 建议细针穿刺。",
        "url": anchor.get("url", ""),
        "excerpt_sha256": "0" * 64,
        "hash_ok": False,
    })

    demo = {
        "id": DEMO_ID,
        "image_id": CASE_ID,
        "region_id": REGION_ID,
        "text": "甲状腺结节超声 · 腺体实质：演示样本——文献摘录与原文 hash 不一致，应在合并前被拦截。",
        "sign_ids": ["SIGN-058"],
        "guideline_ids": [],
        "related_guideline_ids": [],
        "disclaimer": "影像描述，不构成诊断意见；结论需结合临床与病理。",
        "cites": [
            {
                "cite_id": "CIT-REG-011-PAR-D-DEMO",
                "kind": "doc",
                "anchor": anchor,
                "hash_ok": False,
            },
            {
                "cite_id": "CIT-REG-011-PAR-S",
                "kind": "spatial",
                "anchor": {
                    "image_id": CASE_ID, "region_id": REGION_ID,
                    "bbox": [0.02, 0.02, 0.98, 0.3], "atlas_id": "ATLAS-US",
                    "annotator": "human", "annotated_at": "2026-11-20", "shape": "rect",
                },
            },
        ],
        "dual_status": "broken",
        "cite_status": "broken",
        "audit": {
            "rule_check": "fail",
            "ai_review": None,
            "human_review": {"status": "pending", "reviewer": None, "at": None, "signature": None},
        },
        "derivation": {"mode": "integrity_demo", "case_is_normal": False, "sign_source": "title_rule"},
    }

    out = [r for r in rows if r["id"] != DEMO_ID] + [demo]
    CLAIMS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    print("claims", len(out), "added", DEMO_ID)


if __name__ == "__main__":
    main()
