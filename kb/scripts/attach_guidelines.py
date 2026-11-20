#!/usr/bin/env python3
"""为部位匹配的病例补文献对照（doc cite），其余保持 imaging_only。"""
import json, collections

PARAS = {}
for line in open("kb/data/paragraphs.jsonl"):
    x = json.loads(line)
    PARAS.setdefault(x["doc_id"], []).append(x)

GUIDES = {json.loads(l)["id"]: json.loads(l) for l in open("kb/data/guidelines.jsonl")}

# body_part -> (doc_id, para_id, locator)
MAP = {
    "颈部": ("GL-TIRADS-03", "GL-TIRADS-03#statement-1", "TR4 · 穿刺阈值"),
    "乳腺": ("GL-BIRADS-04", "GL-BIRADS-04#statement-1", "BI-RADS 4 · 组织学评估"),
    "腹部": ("GL-LIRADS-02", "GL-LIRADS-02#statement-1", "LR-3 · 随访间隔"),
}

CHEST_NORMAL = ("GL-LUNGRADS-01", "GL-LUNGRADS-01#statement-1", "类别 1 · 年度筛查")
CHEST_NODULE = ("GL-LUNGRADS-03", "GL-LUNGRADS-03#statement-1", "实性结节 6—8 mm")


def doc_cite(doc_id, para_id, locator):
    para = next(p for p in PARAS[doc_id] if p["para_id"] == para_id)
    g = GUIDES.get(doc_id, {})
    return {
        "kind": "doc",
        "anchor": {
            "doc_kind": "guideline", "doc_id": doc_id,
            "doc_title": para.get("title") or g.get("title") or doc_id,
            "version": para.get("version") or g.get("version") or "",
            "locator": locator,
            "excerpt": para["text"],
            "excerpt_sha256": para["sha256"],
            "url": para.get("source_url") or g.get("source_url") or "",
        },
        "hash_ok": True,
    }


def main():
    cases = {json.loads(l)["id"]: json.loads(l) for l in open("kb/data/cases.jsonl") if l.strip()}
    claims = [json.loads(l) for l in open("kb/data/claims.jsonl") if l.strip()]
    by_case = collections.defaultdict(list)
    for c in claims:
        by_case[c["image_id"]].append(c)
    n = 0
    for cid, cs in by_case.items():
        case = cases[cid]
        bp = case["body_part"]
        title = case["title"]
        target = None
        if bp in MAP:
            target = MAP[bp]
        elif bp == "胸部" and ("结节" in title or "钙化" in title):
            target = CHEST_NODULE
        elif bp == "胸部" and ("正常" in title):
            target = CHEST_NORMAL
        if not target:
            continue
        doc_id, para_id, loc = target
        # 只挂在该例第一条结论上，避免同一段落重复铺满
        c = cs[0]
        c["cites"] = [x for x in c["cites"] if x.get("kind") != "doc"]
        c["cites"].append(doc_cite(doc_id, para_id, loc))
        c["dual_status"] = "dual"
        c["guideline_ids"] = [doc_id]
        n += 1
    with open("kb/data/claims.jsonl", "w") as f:
        for c in claims:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print("dual claims", n, "of", len(claims))


if __name__ == "__main__":
    main()
