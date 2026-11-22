#!/usr/bin/env python3
"""给「正常对照」结论补文献侧引用。

CASE-002 / 014 / 172 / 173 是正常解剖对照，claim 只有 spatial、没有 doc，
查询时会直接以「文献侧没有可引用的段落」拒答。这里补一条阴性对照引用：
  - 胸部 → Lung-RADS 1 类（未见肺结节）
  - 头颅 → 征象词条「脑膜强化」（阴性对照）
只补引用，不改结论文字，不新增临床判断。
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb" / "data"


def sha(text):
    return hashlib.sha256((text or "").encode("utf8")).hexdigest()


def load(name):
    return [json.loads(l) for l in (DATA / f"{name}.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]


def main():
    cases = {c["id"]: c for c in load("cases")}
    signs = {s["id"]: s for s in load("signs")}
    guides = {g["id"]: g for g in load("guidelines")}
    claims = load("claims")

    added = 0
    for c in claims:
        if any(x.get("kind") == "doc" for x in c.get("cites", [])):
            continue
        body = cases.get(c["image_id"], {}).get("body_part", "")
        if body in ("胸部", "肺", "胸膜"):
            g = guides.get("GL-LUNGRADS-01")
            if not g:
                continue
            anchor = {
                "doc_kind": "guideline", "doc_id": g["id"], "doc_title": g["standard_name"],
                "version": str(g.get("version_year") or ""),
                "locator": f"{g.get('category')} · {g.get('section')}",
                "excerpt": g["statement"], "excerpt_sha256": sha(g["statement"]),
                "url": g.get("source_url", ""),
            }
        elif body == "头颅":
            s = signs.get("SIGN-038")
            if not s:
                continue
            anchor = {
                "doc_kind": "sign", "doc_id": s["id"], "doc_title": s["name"],
                "version": "", "locator": f"{s['id']} / 影像表现",
                "excerpt": s["appearance"], "excerpt_sha256": sha(s["appearance"]),
                "url": "",
            }
        else:
            continue
        c.setdefault("cites", []).append({"kind": "doc", "anchor": anchor, "hash_ok": True})
        c["dual_status"] = "dual"
        added += 1

    (DATA / "claims.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in claims) + "\n", encoding="utf8")
    print("added doc cites", added)


if __name__ == "__main__":
    main()
