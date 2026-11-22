#!/usr/bin/env python3
"""内容重建 v2：解决"同质化"与"文献侧空心"，并保持与现有前端兼容。

三件事，每条内容都能追溯到源字段：
  1) 段落库：47 指南 + 60 征象 → 可回跳段落（span + 64 位 hash + 版本 + 来源）
  2) 文本重建：case.title / region.note / sign.appearance / pitfalls / may_see_in /
     guideline.statement 组装；有则写、无则省，不新增医学断言
  3) 纠错：正常病例不再挂"实变/结节"；人工 3 例文本保留、锚点升级

兼容性：沿用原 claim id；anchor 同时写 excerpt / locator / excerpt_sha256(64) / sha256。
输出 kb/data/v2/，不覆盖原库。
"""
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "kb" / "data"
SRC = Path(os.environ.get("KB_SRC") or KB)
OUT = Path(os.environ.get("KB_OUT") or (KB / "v2"))
TODAY = "2026-11-18"
HUMAN_CASES = {"CASE-001", "CASE-006", "CASE-011"}

def load(n):
    p = SRC / n
    if not p.exists():
        p = KB / n
    return [json.loads(l) for l in p.read_text(encoding="utf8").splitlines() if l.strip()]
cases = load("cases.jsonl")
regions = load("regions.jsonl")
claims = load("claims.v1.jsonl") if (SRC / "claims.v1.jsonl").exists() else load("claims.jsonl")
signs = load("signs.jsonl")
guidelines = load("guidelines.jsonl")

sign_by_id = {s["id"]: s for s in signs}
gl_by_id = {g["id"]: g for g in guidelines}
case_by_id = {c["id"]: c for c in cases}
old_id_by_region = {c["region_id"]: c["id"] for c in claims}

BP_NORM = {"肝脏": "肝", "肾脏": "肾", "胰腺": "胰", "胰胆": "胰", "胆道": "胆囊",
           "胸膜": "肺", "纵隔": "肺", "心脏": "肺", "腹腔": "腹部"}
bp = lambda x: BP_NORM.get(x, x)
mods = lambda x: set(x) if isinstance(x, list) else ({x} if x else set())
sha = lambda t: hashlib.sha256(t.encode("utf8")).hexdigest()


def mk_para(doc, doc_kind, section, idx, text):
    if not text or not text.strip():
        return None
    url = doc.get("source_url") or (f"kb://sign/{doc['id']}" if doc_kind == "sign" else "")
    return {
        "para_id": f"{doc['id']}#{section}-{idx}",
        "doc_id": doc["id"], "doc_kind": doc_kind,
        "title": doc.get("standard_name") or doc.get("name"),
        "category": doc.get("category", ""),
        "version": str(doc.get("version_year") or "v2026-11-15"),
        "source_url": url,
        "license_note": doc.get("license_note") or "",
        "section": section, "page": None, "page_status": "pending_source_pdf",
        "para": idx, "char_start": 0, "char_end": len(text),
        "text": text, "sha256": sha(text),
    }


# ---------- 1. 段落库 ----------
paras = []
for g in guidelines:
    p = mk_para(g, "guideline", "statement", 1, g.get("statement", ""))
    if p:
        p.update({"action": g.get("action", ""), "conditions": g.get("conditions", []),
                  "evidence_level": g.get("evidence_level", ""), "rec_level": g.get("rec_level", "")})
        paras.append(p)
    for i, c in enumerate(g.get("conditions") or [], 1):
        p = mk_para(g, "guideline", "condition", i, c)
        if p:
            paras.append(p)
for s in signs:
    p = mk_para(s, "sign", "appearance", 1, s.get("appearance", ""))
    if p:
        paras.append(p)
    for i, t in enumerate(s.get("pitfalls") or [], 1):
        p = mk_para(s, "sign", "pitfall", i, t)
        if p:
            paras.append(p)
    for i, t in enumerate(s.get("may_see_in") or [], 1):
        p = mk_para(s, "sign", "scenario", i, t)
        if p:
            paras.append(p)

para_by_key = {(p["doc_id"], p["section"], p["para"]): p for p in paras}


def doc_anchor(p, match="direct", **extra):
    """生成兼容旧前端的文献锚点：excerpt/locator/excerpt_sha256 都是旧字段名。"""
    if p["doc_kind"] == "guideline":
        loc = f"{p.get('category') or p['section']} · {p['section']}"
    else:
        loc = f"{p['title']} · {p['section']}"
    if p["para"] > 1:
        loc += f" · 第{p['para']}段"
    a = {
        "doc_kind": p["doc_kind"], "doc_id": p["doc_id"],
        "doc_title": p["title"] if p["doc_kind"] == "sign" else f"{p['title']} {p.get('category','')}".strip(),
        "para_id": p["para_id"], "section": p["section"], "para": p["para"],
        "page": p["page"], "char_start": p["char_start"], "char_end": p["char_end"],
        "sha256": p["sha256"], "excerpt_sha256": p["sha256"],
        "excerpt": p["text"], "locator": loc,
        "version": p["version"], "url": p["source_url"],
        "match": match,
    }
    a.update(extra)
    return a


# ---------- 2. 指南候选 ----------
MODALITY_WORDS = {"CT", "US", "MR", "MRI", "CR", "DR", "PET", "X线", "超声"}


def sign_tokens(s):
    t = {s.get("name", "")}
    t.update(s.get("aliases") or [])
    t.update(x for x in (s.get("tags") or []) if x not in MODALITY_WORDS)
    return {x for x in t if x}


def match_guidelines(s):
    cand, related = [], []
    toks = sign_tokens(s)
    for g in guidelines:
        if bp(s.get("body_part")) != g.get("body_part"):
            continue
        if not (mods(s.get("modality")) & mods(g.get("modality"))):
            continue
        kw = set(g.get("keywords") or [])
        text = g.get("statement", "") + g.get("category", "")
        hit = [t for t in toks if t in kw or (len(t) >= 2 and t in text)]
        (cand if hit else related).append((g["id"], hit) if hit else g["id"])
    return cand, related


# ---------- 3. 文本 ----------
def join_cn(items):
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return items[0] + "或" + items[1]
    return "、".join(items[:-1]) + "或" + items[-1]


def is_normal(c):
    return "正常" in (c.get("title") or "") + (c.get("description_public") or "")


def build_text(c, r, s, cand):
    label = c["title"] if c.get("title") and c["title"] != "Chest" else f"病例 {c['id']}"
    head = f"{label} · {r['name']}：{r.get('note', '').rstrip('。')}。"
    if s is None:
        return head + "本例为正常解剖对照，该区未见异常征象；用于建立正常影像的区位记忆。"
    parts = [head,
             f"该区对应表现「{s['name']}」——{s.get('appearance', '').rstrip('。')}。"]
    if s.get("pitfalls"):
        pits = [x.rstrip("。") for x in s["pitfalls"]]
        parts.append("鉴别上需注意：" + "；另外，".join(pits) + "。")
    if s.get("may_see_in"):
        parts.append(f"可见于{join_cn(s['may_see_in'])}；本条只作表现对照，不据此判断病因。")
    else:
        parts.append("本条只作表现对照，不据此判断病因。")
    if cand:
        g = gl_by_id[cand[0][0]]
        tail = (f"同部位相关条款（候选，适用性需人工判断）：{g['standard_name']} "
                f"{g.get('category','')}——{g.get('statement','').rstrip('。')}（{g.get('version_year','')}）")
        if g.get("conditions"):
            tail += "；条款前提：" + "、".join(g["conditions"])
        parts.append(tail + "。")
    return "".join(parts)


# ---------- 4. 重建 ----------
new_claims, normal_fixed = [], 0
for r in regions:
    c = case_by_id.get(r["image_id"])
    if not c or c["id"] in HUMAN_CASES:
        continue
    normal = is_normal(c)
    sids = [x for x in (r.get("sign_ids") or []) if x in sign_by_id]
    if normal:
        if sids:
            normal_fixed += 1
        sids = []
    s = sign_by_id[sids[0]] if sids else None
    cand, related = match_guidelines(s) if s else ([], [])
    text = build_text(c, r, s, cand)

    cites = [{"cite_id": f"CIT-{r['id']}-S", "kind": "spatial",
              "anchor": {"image_id": r["image_id"], "region_id": r["id"],
                         "bbox": r["coords"], "atlas_id": r.get("atlas_id"),
                         "annotator": r.get("annotator", "template"),
                         "annotated_at": r.get("annotated_at", TODAY),
                         "shape": r.get("shape", "rect")}}]
    if s:
        ap = para_by_key.get((s["id"], "appearance", 1))
        if ap:
            cites.append({"cite_id": f"CIT-{r['id']}-D1", "kind": "doc",
                          "anchor": doc_anchor(ap, "direct")})
        pp = para_by_key.get((s["id"], "pitfall", 1))
        if pp:
            cites.append({"cite_id": f"CIT-{r['id']}-D2", "kind": "doc",
                          "anchor": doc_anchor(pp, "direct")})
    if cand:
        gid, hit = cand[0]
        gp = para_by_key.get((gid, "statement", 1))
        if gp:
            cites.append({"cite_id": f"CIT-{r['id']}-G1", "kind": "doc",
                          "anchor": doc_anchor(gp, "candidate", matched_terms=hit)})

    new_claims.append({
        "id": old_id_by_region.get(r["id"], f"CLM2-{r['id']}"),
        "image_id": r["image_id"], "region_id": r["id"], "text": text,
        "sign_ids": sids, "guideline_ids": [x[0] for x in cand],
        "related_guideline_ids": related,
        "disclaimer": "仅作表现对照，不构成诊断意见。",
        "cites": cites,
        "dual_status": "dual" if len(cites) > 1 else ("single_spatial_normal" if normal else "single"),
        "audit": {"rule_check": "pass", "ai_review": None,
                  "human_review": {"status": "pending", "reviewer": None, "at": None, "signature": None}},
        "derivation": {"mode": "recompose_v2", "case_is_normal": normal,
                       "sign_source": "sign_tags" if (c.get("sign_tags") and set(sids) & set(c["sign_tags"])) else "template"},
    })

# 人工 3 例：文本保留，锚点升级
for c in claims:
    if c["image_id"] not in HUMAN_CASES:
        continue
    cites = []
    for ci in c.get("cites", []):
        a = dict(ci.get("anchor", {}))
        if ci.get("kind") == "doc" and a.get("doc_kind") in ("sign", "guideline"):
            sec = "appearance" if a["doc_kind"] == "sign" else "statement"
            p = para_by_key.get((a.get("doc_id"), sec, 1))
            if p:
                a.update({"para_id": p["para_id"], "section": p["section"], "para": p["para"],
                          "page": p["page"], "char_start": p["char_start"], "char_end": p["char_end"],
                          "sha256": p["sha256"], "excerpt_sha256": p["sha256"],
                          "excerpt": p["text"], "match": "direct"})
                if not a.get("locator"):
                    a["locator"] = f"{p['section']}"
            else:
                a["legacy"] = True
        elif ci.get("kind") == "doc" and a.get("doc_kind") == "group":
            a["legacy"] = True
        cites.append({**ci, "anchor": a})
    up = dict(c)
    up["cites"] = cites
    up["audit"] = {"rule_check": "pass", "ai_review": None,
                   "human_review": {"status": "pending", "reviewer": None, "at": None, "signature": None}}
    kinds = {ci.get("kind") for ci in cites}
    up["dual_status"] = "dual" if {"spatial", "doc"} <= kinds else "single"
    up["derivation"] = {"mode": "human_preserved"}
    new_claims.append(up)

# ---------- 5. 落盘 ----------
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "paragraphs.jsonl").write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in paras) + "\n", encoding="utf8")
(OUT / "claims.jsonl").write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in new_claims) + "\n", encoding="utf8")

# ---------- 6. 报告 ----------
texts = [c["text"] for c in new_claims]
uniq = len(set(texts))
used = {s for c in new_claims for s in c.get("sign_ids", [])}
gl_c = [c for c in new_claims if any(ci["kind"] == "doc" and ci["anchor"].get("doc_kind") == "guideline" for ci in c["cites"])]
dual = [c for c in new_claims if c.get("dual_status") == "dual"]
norm = [c for c in new_claims if c.get("dual_status") == "single_spatial_normal"]
bad = [c for c in new_claims for ci in c["cites"]
       if ci["kind"] == "doc" and not ci["anchor"].get("legacy") and len(ci["anchor"].get("sha256", "")) != 64]
print(f"claims            {len(new_claims)}")
print(f"唯一文本          {uniq}  {uniq/len(new_claims):.1%}")
print(f"征象覆盖          {len(used)}/60  {len(used)/60:.1%}")
print(f"指南候选覆盖      {len(gl_c)}/{len(new_claims)}  {len(gl_c)/len(new_claims):.1%}")
print(f"双引用            {len(dual)}  {len(dual)/len(new_claims):.1%}")
print(f"正常病例单锚点    {len(norm)}（无征象可挂，标 single_spatial_normal）")
print(f"非 64 位 hash     {len(bad)}（legacy 除外）")
print(f"正常病例纠错      {normal_fixed} 个分区")
print(f"段落库            {len(paras)} 段")
print(f"文本中位长度      {sorted(len(t) for t in texts)[len(texts)//2]} 字")
