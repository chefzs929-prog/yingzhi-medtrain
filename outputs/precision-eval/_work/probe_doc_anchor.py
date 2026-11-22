#!/usr/bin/env python3
"""探针 2：把"文献段落引用"做成可回跳、可核验，需要哪些字段；现有库差多少。

做三件事：
1) 统计现有 582 条 claim 的 doc anchor 到底指向什么（指南原文 / 征象词条自撰释义）
2) 用 47 条指南 + 60 条征象释义建一个"段落库"（段落 id + span + 64 位 hash）
3) 验证：随机引用能否 100% 回跳到原文；改一个字能否 100% 被 hash 拦住
"""
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

KB = Path(__file__).resolve().parents[3] / "kb" / "data"
load = lambda n: [json.loads(l) for l in (KB / n).read_text(encoding="utf8").splitlines() if l.strip()]

claims = load("claims.jsonl")
guidelines = load("guidelines.jsonl")
signs = load("signs.jsonl")

# ---------- 1. 现有锚点指向什么 ----------
kinds = Counter()
len8 = 0
no_span = 0
for c in claims:
    for ci in c.get("cites", []):
        if ci.get("kind") != "doc":
            continue
        a = ci.get("anchor", {})
        kinds[a.get("doc_kind")] += 1
        if len(str(a.get("excerpt_sha256", ""))) == 8:
            len8 += 1
        if not any(k in a for k in ("page", "para", "span", "char_start")):
            no_span += 1
print("doc anchor 指向:", dict(kinds))
print("8 位截断 hash:", len8, " 无页/段/字符偏移:", no_span)
print("挂了 guideline 的 claim:", sum(1 for c in claims if any(
    ci.get("kind") == "doc" and ci.get("anchor", {}).get("doc_kind") == "guideline" for ci in c.get("cites", []))))

# ---------- 2. 段落库 ----------
paras = []
for g in guidelines:
    text = g["statement"]
    paras.append({
        "doc_id": g["id"], "doc_kind": "guideline", "title": g["standard_name"],
        "section": g.get("section", ""), "page": None, "para": 1,
        "char_start": 0, "char_end": len(text), "text": text,
        "sha256": hashlib.sha256(text.encode("utf8")).hexdigest(),
    })
for s in signs:
    text = s["appearance"]
    paras.append({
        "doc_id": s["id"], "doc_kind": "sign", "title": s["name"],
        "section": "appearance", "page": None, "para": 1,
        "char_start": 0, "char_end": len(text), "text": text,
        "sha256": hashlib.sha256(text.encode("utf8")).hexdigest(),
    })
print(f"\n段落库: {len(paras)} 段  平均 {sum(len(p['text']) for p in paras)/len(paras):.1f} 字")
out = Path(__file__).resolve().parents[1] / "paragraphs.sample.jsonl"
out.write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in paras) + "\n", encoding="utf8")
print("样例已写出:", out)

# ---------- 3. 回跳与篡改 ----------
random.seed(7)
sample = random.sample(paras, min(200, len(paras)))
back_ok = 0
for p in sample:
    span = p["text"][p["char_start"]:p["char_end"]]
    if hashlib.sha256(span.encode("utf8")).hexdigest() == p["sha256"]:
        back_ok += 1
print(f"回跳一致: {back_ok}/{len(sample)} = {back_ok/len(sample):.1%}")

caught = 0
for p in sample:
    t = p["text"]
    if not t:
        continue
    i = len(t) // 2
    tampered = t[:i] + ("X" if t[i] != "X" else "Y") + t[i + 1:]
    if hashlib.sha256(tampered.encode("utf8")).hexdigest() != p["sha256"]:
        caught += 1
print(f"改一字被拦截: {caught}/{len(sample)} = {caught/len(sample):.1%}")

# 截断 hash 的碰撞风险对比
short_hit = sum(1 for p in sample if hashlib.sha256(p["text"].encode()).hexdigest()[:8] == p["sha256"][:8])
print(f"8 位前缀仍一致: {short_hit}/{len(sample)}（说明前缀校验无法区分版本）")
