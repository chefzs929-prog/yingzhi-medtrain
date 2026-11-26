#!/usr/bin/env python3
"""知识库检索核心：纯标准库 BM25 + 同义词扩展 + 元数据过滤 + 相似关联。

设计约束：
- 只返回可回溯的公开来源，不生成诊断性结论；
- 每条结果都带 source 链接与许可说明；
- 检索失败时返回空结果，由上层给出边界话术。
"""
from __future__ import annotations
import json
import math
import re
from collections import Counter
from pathlib import Path

import sign_links

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INDEX = ROOT / "index" / "index.json"


def _built_at() -> str | None:
    p = INDEX.parent / "built_at.txt"
    try:
        return p.read_text(encoding="utf8").strip()
    except OSError:
        return None

STOP = set("的 了 是 在 有 和 与 及 或 等 中 见 可见 表现 影像 图像 检查 显示 出现 情况 部位".split())

PART_HINTS = {
    "肺": "肺", "胸部": "胸", "胸腔": "胸", "胸膜": "胸膜", "纵隔": "纵隔", "心脏": "心脏",
    "乳腺": "乳腺", "甲状腺": "甲状腺", "肝": "肝", "胆": "胆", "胰": "胰", "肾": "肾",
    "脑": "脑", "头颅": "脑", "膝": "膝", "关节": "关节", "腹": "腹", "肠": "肠", "骨": "骨",
}
PART_FAMILY = {
    "肺": ["肺", "胸"], "胸部": ["肺", "胸"], "胸膜": ["胸膜", "胸"],
    "脑": ["脑", "头颅"], "头颅": ["脑", "头颅"],
    "膝": ["膝", "关节"], "关节": ["膝", "关节"],
    "腹": ["腹", "肠", "肝", "胆", "胰", "肾"], "肝": ["肝", "腹"], "胆": ["胆", "腹"],
    "胰": ["胰", "腹"], "肾": ["肾", "腹"], "肠": ["肠", "腹"],
}
MOD_HINTS = {
    "ct": "CT", "mr": "MR", "磁共振": "MR", "核磁": "MR", "超声": "US", "b超": "US",
    "钼靶": "MG", "乳腺x": "MG", "x线": "CR", "x光": "CR", "胸片": "CR", "dr": "CR",
}
CJK = re.compile(r"[\u4e00-\u9fff]+")
LATIN = re.compile(r"[a-z0-9][a-z0-9\-\.]*")


def tokenize(text):
    text = (text or "").lower()
    out = []
    for seg in CJK.findall(text):
        if len(seg) == 1:
            out.append(seg)
        else:
            out.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    out.extend(LATIN.findall(text))
    return [t for t in out if t and t not in STOP]


def load_jsonl(path):
    rows = []
    for line in Path(path).read_text(encoding="utf8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def doc_text(d):
    kind = d.get("_type")
    if kind == "sign":
        parts = [d["name"], d["en"]] + d.get("aliases", [])
        parts += [d.get("body_part", ""), " ".join(d.get("modality", []))]
        parts += [d.get("appearance", ""), " ".join(d.get("may_see_in", []))]
        parts += [" ".join(d.get("tags", []))]
        parts += [" ".join(d.get("pitfalls", []))]
        return " ".join(parts)
    if kind == "standard":
        parts = [d["name"], d["full_name"], d["purpose"]]
        parts += d.get("dimensions", [])
        return " ".join(parts)
    if kind == "case":
        mods = d.get("modality", [])
        if isinstance(mods, str):
            mods = [mods]
        parts = [d["title"], d.get("body_part", ""), " ".join(mods), d.get("description_public", ""), d.get("teaching_note", "")]
        return " ".join(parts)
    if kind == "guideline":
        parts = [d.get("standard_name", ""), d.get("category", ""), d.get("section", ""),
                 d.get("statement", ""), " ".join(d.get("conditions", [])),
                 " ".join(d.get("keywords", [])), d.get("body_part", "")]
        return " ".join(parts)
    return ""


def build():
    signs = load_jsonl(DATA / "signs.jsonl")
    standards = load_jsonl(DATA / "standards.jsonl")
    cases = load_jsonl(DATA / "cases.jsonl")
    guidelines = load_jsonl(DATA / "guidelines.jsonl")
    groups = load_jsonl(DATA / "groups.jsonl")
    for s in signs:
        s["_type"] = "sign"
    for s in standards:
        s["_type"] = "standard"
    for c in cases:
        c["_type"] = "case"
        if isinstance(c.get("modality"), str):
            c["modality"] = [c["modality"]]

    for g in guidelines:
        g["_type"] = "guideline"
        if isinstance(g.get("modality"), str):
            g["modality"] = [g["modality"]]

    docs = signs + standards + cases + guidelines
    df = Counter()
    for d in docs:
        d["_text"] = doc_text(d)
        toks = tokenize(d["_text"])
        # 标题与别名加权：重复写入词元
        if d["_type"] == "sign":
            toks += tokenize(d["name"] + " " + d["en"]) * 2
            toks += tokenize(" ".join(d.get("aliases", [])))
        elif d["_type"] == "standard":
            toks += tokenize(d["name"] + " " + d["full_name"])
        elif d["_type"] == "guideline":
            toks += tokenize(d.get("category", "") + " " + " ".join(d.get("keywords", [])))
        else:
            toks += tokenize(d["title"])
        d["_tokens"] = toks
        d["_len"] = len(toks)
        for t in set(toks):
            df[t] += 1

    # 时间戳单独落盘，避免每次重建都让 index.json 产生无意义 diff
    stamp = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    index = {
        "groups": groups,
        "N": len(docs),
        "avgdl": sum(d["_len"] for d in docs) / max(1, len(docs)),
        "df": dict(df),
        "docs": docs,
    }
    INDEX.parent.mkdir(exist_ok=True)
    INDEX.write_text(json.dumps(index, ensure_ascii=False, sort_keys=True), encoding="utf8")
    (INDEX.parent / "built_at.txt").write_text(stamp, encoding="utf8")
    return index


class KB:
    def __init__(self, index=None):
        self.index = index or json.loads(INDEX.read_text(encoding="utf8"))
        self.docs = self.index["docs"]
        self.df = self.index["df"]
        self.N = self.index["N"]
        self.avgdl = self.index["avgdl"]
        self.sources = {s["id"]: s for s in json.loads((DATA / "sources.json").read_text(encoding="utf8"))["sources"]}
        self.group_defs = load_jsonl(DATA / "groups.jsonl") or self.index.get("groups", [])
        tax_path = DATA / "taxonomy.json"
        self.tax_def = json.loads(tax_path.read_text(encoding="utf8")) if tax_path.exists() else {"regions": []}
        self.region_names = {r["id"]: r["name"] for r in self.tax_def.get("regions", [])}
        self.group_region = {g["id"]: g.get("region_id") for g in self.group_defs}
        self.alias_map = {}
        for d in self.docs:
            if d["_type"] == "sign":
                for a in [d["name"], d["en"]] + d.get("aliases", []):
                    self.alias_map[a.lower()] = d["id"]

        # 征象文字 ↔ 影像区域（v1）：数据不合法时直接失败，不带病上线。
        self.sign_by_id = {d["id"]: d for d in self.docs if d["_type"] == "sign"}
        self.case_by_id = {d["id"]: d for d in self.docs if d["_type"] == "case"}
        self.link_rows = [x for x in sign_links.load() if x.get("status") == "active"]
        errors = sign_links.validate(self.link_rows, self.sign_by_id, self.case_by_id, self.sources)
        if errors:
            raise ValueError("sign_links.jsonl 校验失败：" + "；".join(errors[:6]))
        self.links_by_sign = {}
        self.links_by_image = {}
        for link in self.link_rows:
            self.links_by_sign.setdefault(link["sign_id"], []).append(link)
            self.links_by_image.setdefault(link["image_id"], []).append(link)

    def idf(self, term):
        n = self.df.get(term, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def score(self, d, q_tokens, weights):
        tf = Counter(d["_tokens"])
        dl = d["_len"]
        k1, b = 1.5, 0.75
        s = 0.0
        for t in q_tokens:
            f = tf.get(t, 0)
            if not f:
                continue
            denom = f + k1 * (1 - b + b * dl / self.avgdl)
            s += weights.get(t, 1.0) * self.idf(t) * f * (k1 + 1) / denom
        return s

    def expand(self, q):
        """同义词扩展：查询中出现的别名映射到规范征象，并补充其别名与标签词。"""
        ql = q.lower()
        weights, extra_terms = {}, set()
        for alias, sid in self.alias_map.items():
            if len(alias) >= 2 and alias in ql:
                weights[alias] = 2.0
                doc = next(d for d in self.docs if d["id"] == sid)
                for term in tokenize(doc["name"] + " " + " ".join(doc.get("aliases", []))):
                    extra_terms.add(term)
        for t in tokenize(q):
            weights.setdefault(t, 1.0)
        for t in extra_terms:
            weights.setdefault(t, 0.6)
        return list(weights.keys()), weights

    def search(self, q, modality=None, part=None, limit=6):
        q_tokens, weights = self.expand(q or "")
        if not q_tokens:
            return {"query": q, "signs": [], "standards": [], "cases": [], "related": [], "empty": True}

        ql = (q or "").lower()
        want_parts = {v for k, v in PART_HINTS.items() if k in ql}
        want_mods = {v for k, v in MOD_HINTS.items() if k in ql}

        scored = []
        for d in self.docs:
            if modality and d["_type"] in ("sign", "case", "guideline"):
                if modality.upper() not in [m.upper() for m in d.get("modality", [])]:
                    continue
            if part and part not in (d.get("body_part") or ""):
                continue
            s = self.score(d, q_tokens, weights)
            if s <= 0:
                continue
            bp = d.get("body_part") or ""
            mods = [m.upper() for m in d.get("modality", [])]
            if want_parts and any(w in bp for w in want_parts):
                s *= 1.5
            if want_mods and set(want_mods) & set(mods):
                s *= 1.3
            scored.append((s, d))
        scored.sort(key=lambda x: -x[0])

        def pack(items, kind, n):
            out = []
            for s, d in items:
                if d["_type"] != kind:
                    continue
                out.append(self.present(d, round(s, 2)))
                if len(out) >= n:
                    break
            return out

        signs = pack(scored, "sign", limit)
        guidelines = [x for x in pack(scored, "guideline", 6) if x.get("status", "active") == "active"]
        if signs:
            top_part = signs[0].get("body_part", "")
            guidelines = [x for x in guidelines if self.same_family(x.get("body_part", ""), top_part)]
        guidelines = guidelines[:4]
        top_sign_score = next((s for s, d in scored if d["_type"] == "sign"), 0)
        floor = max(5.0, top_sign_score * 0.2)
        standards = [x for x in pack(scored, "standard", 4) if x["score"] >= floor][:2]
        if signs:
            top_part = signs[0].get("body_part", "")
            standards = [x for x in standards if self.same_family(x.get("body_part", ""), top_part)]
        cases = self.pick_cases(scored, signs, limit=6)
        related = self.related(signs[0]["id"], limit=4) if signs else []
        top = signs[0]["score"] if signs else 0
        return {
            "query": q,
            "signs": signs,
            "standards": standards,
            "cases": cases,
            "guidelines": guidelines,
            "related": related,
            "confidence": "high" if top >= 18 else ("medium" if top >= 10 else "low"),
            "empty": not (signs or standards or cases or guidelines),
            "disclaimer": "结果仅用于教学对照与文献定位，不构成诊断意见，不对个体影像给出结论。",
        }

    @staticmethod
    def same_family(a, b):
        if not a or not b:
            return False
        fa = PART_FAMILY.get(a, [a])
        fb = PART_FAMILY.get(b, [b])
        return bool(set(fa) & set(fb))

    def pick_cases(self, scored, signs, limit=6):
        """病例只在能给出可靠关联时返回：标签命中，或同模态同部位。"""
        top = signs[0] if signs else None
        out = []
        for s, d in scored:
            if d["_type"] != "case":
                continue
            ok = False
            if top:
                if top["id"] in d.get("sign_tags", []):
                    ok = True
                elif self.same_family(d.get("body_part"), top.get("body_part")) and set(d.get("modality", [])) & set(top.get("modality", [])):
                    ok = True
            if ok:
                out.append(self.present(d, round(s, 2)))
            if len(out) >= limit:
                break
        if not out and top:
            # 兜底：同部位同模态的公开对照图
            for d in self.docs:
                if d["_type"] != "case":
                    continue
                if self.same_family(d.get("body_part"), top.get("body_part")) and set(d.get("modality", [])) & set(top.get("modality", [])):
                    out.append(self.present(d, 0))
                if len(out) >= limit:
                    break
        return out

    def present(self, d, score):
        base = {"id": d["id"], "type": d["_type"], "score": score}
        if d["_type"] == "sign":
            linked_rows = self.links_by_sign.get(d["id"], [])
            base.update({
                "name": d["name"], "en": d["en"], "aliases": d.get("aliases", []),
                "modality": d.get("modality", []), "body_part": d.get("body_part", ""),
                "appearance": d.get("appearance", ""), "may_see_in": d.get("may_see_in", []),
                "pitfalls": d.get("pitfalls", []), "tags": d.get("tags", []),
                "sources": [self.src(i) for i in d.get("sources", [])],
                "link_count": len(linked_rows),
                "linked_image_count": len({x["image_id"] for x in linked_rows}),
                "linked_image_ids": sorted({x["image_id"] for x in linked_rows}),
            })
        elif d["_type"] == "standard":
            base.update({
                "name": d["name"], "full_name": d["full_name"], "publisher": d["publisher"],
                "purpose": d["purpose"], "dimensions": d.get("dimensions", []),
                "report_form": d.get("report_form", ""), "url": d["official_url"],
                "body_part": d.get("body_part", ""),
                "license_note": d.get("license_note", ""), "note": d.get("note", ""),
            })
        elif d["_type"] == "guideline":
            base.update({
                "standard_id": d.get("standard_id", ""), "standard_name": d.get("standard_name", ""),
                "category": d.get("category", ""), "section": d.get("section", ""),
                "statement": d.get("statement", ""), "conditions": d.get("conditions", []),
                "action": d.get("action", ""), "rec_level": d.get("rec_level", ""),
                "evidence_level": d.get("evidence_level", ""), "version_year": d.get("version_year"),
                "source_url": d.get("source_url", ""), "license_note": d.get("license_note", ""),
                "status": d.get("status", "active"), "body_part": d.get("body_part", ""),
                "modality": d.get("modality", []), "keywords": d.get("keywords", []),
            })
        else:
            linked_rows = self.links_by_image.get(d["id"], [])
            linked_signs = []
            for link in linked_rows:
                sign = self.sign_by_id.get(link["sign_id"], {})
                item = {"id": link["sign_id"], "name": sign.get("name", ""), "count": 0}
                existing = next((x for x in linked_signs if x["id"] == item["id"]), None)
                if existing:
                    existing["count"] += 1
                else:
                    item["count"] = 1
                    linked_signs.append(item)
            base.update({
                "title": d["title"], "modality": d.get("modality", ""), "body_part": d.get("body_part", ""),
                "image": d.get("image", ""), "source_page": d.get("source_page", ""),
                "license": d.get("license", ""), "artist": d.get("artist", ""),
                "description_public": d.get("description_public", ""),
                "teaching_note": d.get("teaching_note", ""), "sign_tags": d.get("sign_tags", []),
                "group_id": d.get("group_id", ""),
                "privacy_check": d.get("privacy_check", ""),
                "link_count": len(linked_rows),
                "linked_signs": linked_signs,
            })
        return base

    def src(self, sid):
        s = self.sources.get(sid, {})
        return {"id": sid, "title": s.get("title", ""), "publisher": s.get("publisher", ""),
                "url": s.get("url", ""), "license_note": s.get("license_note", ""),
                "access": s.get("access", "")}

    def related(self, sign_id, limit=4):
        me = next((d for d in self.docs if d["id"] == sign_id and d["_type"] == "sign"), None)
        if not me:
            return []
        mt = set(me.get("tags", []))
        out = []
        for d in self.docs:
            if d["_type"] != "sign" or d["id"] == sign_id:
                continue
            overlap = len(mt & set(d.get("tags", [])))
            same_part = 1 if d.get("body_part") == me.get("body_part") else 0
            same_mod = len(set(me.get("modality", [])) & set(d.get("modality", [])))
            s = overlap * 2 + same_part + same_mod * 0.5
            if s > 0:
                out.append((s, d))
        out.sort(key=lambda x: -x[0])
        return [{"id": d["id"], "name": d["name"], "body_part": d.get("body_part", ""),
                 "modality": d.get("modality", []), "score": round(s, 1)} for s, d in out[:limit]]

    def get(self, doc_id):
        d = next((x for x in self.docs if x["id"] == doc_id), None)
        return self.present(d, 0) if d else None

    # ---------------- 征象文字 ↔ 影像区域（v1） ----------------
    def link_present(self, link):
        sign = self.sign_by_id.get(link["sign_id"], {})
        case = self.case_by_id.get(link["image_id"])
        return {
            "id": link["id"],
            "sign_id": link["sign_id"],
            "sign_name": sign.get("name", ""),
            "sign_en": sign.get("en", ""),
            "quote": link.get("quote", ""),
            "caption": link.get("caption", ""),
            "reading": link.get("reading", ""),
            "regions": link.get("regions", []),
            "basis": link.get("basis", ""),
            "evidence": link.get("evidence", {}),
            "annotator": link.get("annotator", ""),
            "annotated_at": link.get("annotated_at", ""),
            "review": link.get("review", ""),
            "status": link.get("status", ""),
            "image": self.present(case, 0) if case else None,
        }

    def sign_index(self):
        """已建立图文关联的征象清单，供界面选择器使用。"""
        items = []
        for sign_id, rows in self.links_by_sign.items():
            sign = self.sign_by_id.get(sign_id, {})
            items.append({
                "id": sign_id,
                "name": sign.get("name", sign_id),
                "en": sign.get("en", ""),
                "modality": sign.get("modality", []),
                "body_part": sign.get("body_part", ""),
                "link_count": len(rows),
                "image_count": len({x["image_id"] for x in rows}),
                "quote_count": len({x["quote"] for x in rows}),
            })
        items.sort(key=lambda x: (-x["link_count"], x["name"]))
        return items

    def sign_detail(self, sign_id):
        """一个征象的完整图文对照：文字分段 + 关联影像 + 标注区域。"""
        sign = self.sign_by_id.get(sign_id)
        if not sign:
            return None
        rows = self.links_by_sign.get(sign_id, [])
        try:
            segments = sign_links.segments_for(sign.get("appearance", ""), rows)
        except ValueError as exc:
            raise ValueError(f"{sign_id} 文字分段失败：{exc}") from exc
        items = [self.link_present(x) for x in rows]
        images = {}
        for item in items:
            image = item.get("image")
            if not image:
                continue
            group = images.setdefault(image["id"], {"image": image, "links": []})
            group["links"].append(item)
        basis = Counter(x.get("basis", "") for x in rows)
        return {
            "sign": self.present(sign, 0),
            "appearance": sign.get("appearance", ""),
            "segments": segments,
            "links": items,
            "images": list(images.values()),
            "stats": {
                "links": len(rows),
                "images": len(images),
                "regions": sum(len(x.get("regions", [])) for x in rows),
                "quotes": len({x["quote"] for x in rows}),
                "basis": dict(basis),
                "missing_image": 0,
                "missing_text": 0,
            },
            "note": "框是人工标注的教学区域，不是模型识别，也不是病灶分割；仅用于文字与影像对照。",
        }

    def sign_links(self, sign_id=None, image_id=None):
        """按征象或影像筛选图文关联；两个参数都可省略。"""
        rows = [
            x for x in self.link_rows
            if (not sign_id or x["sign_id"] == sign_id)
            and (not image_id or x["image_id"] == image_id)
        ]
        items = [self.link_present(x) for x in rows]
        return {
            "items": items,
            "stats": {
                "links": len(items),
                "signs": len({x["sign_id"] for x in rows}),
                "images": len({x["image_id"] for x in rows}),
                "regions": sum(len(x.get("regions", [])) for x in rows),
            },
        }

    def search_guidelines(self, q, modality=None, part=None, limit=6):
        r = self.search(q, modality=modality, part=part, limit=1)
        items = r.get("guidelines", [])[:limit]
        if not items:
            # 无征象命中时，直接按条款文本检索
            q_tokens, weights = self.expand(q or "")
            scored = []
            for d in self.docs:
                if d["_type"] != "guideline" or d.get("status", "active") != "active":
                    continue
                if modality and modality.upper() not in [m.upper() for m in d.get("modality", [])]:
                    continue
                if part and part not in (d.get("body_part") or ""):
                    continue
                sc = self.score(d, q_tokens, weights)
                if sc > 0:
                    scored.append((sc, d))
            scored.sort(key=lambda x: -x[0])
            items = [self.present(d, round(sc, 2)) for sc, d in scored[:limit]]
        return items

    def images(self, modality=None, part=None, sign=None, group=None, region=None):
        out = []
        for d in self.docs:
            if d["_type"] != "case":
                continue
            if modality and modality.upper() not in [m.upper() for m in d.get("modality", [])]:
                continue
            if part and part not in (d.get("body_part") or ""):
                continue
            if sign and sign not in d.get("sign_tags", []):
                continue
            if group and d.get("group_id") != group:
                continue
            if region and self.group_region.get(d.get("group_id")) != region:
                continue
            out.append(self.present(d, 0))
        return out

    def groups(self, region=None):
        """影像组 = 二级分类（病症/征象族），附带所属一级部位。"""
        out = []
        for g in self.group_defs:
            if region and g.get("region_id") != region:
                continue
            items = [x for x in self.images() if x.get("group_id") == g["id"]]
            if not items:
                continue
            out.append({
                "id": g["id"], "name": g["name"], "description": g.get("description", ""),
                "criteria": g.get("criteria", ""), "caution": g.get("caution", ""),
                "sign_ids": g.get("sign_ids", []), "modality": g.get("modality", []),
                "body_part": g.get("body_part", ""), "count": len(items), "items": items,
                "search_query": g.get("search_query", ""),
                "region_id": g.get("region_id", ""),
                "region_name": self.region_names.get(g.get("region_id"), "未归类"),
            })
        out.sort(key=lambda x: (x["region_id"], -x["count"]))
        return out

    def taxonomy(self):
        """一级部位 → 二级病症的两级分类树；无影像的二级分类同样返回，便于显示缺口。"""
        imgs = self.images()
        by_group = {}
        for c in imgs:
            by_group.setdefault(c.get("group_id"), []).append(c)
        gmap = {g["id"]: g for g in self.group_defs}
        regions = []
        for r in sorted(self.tax_def.get("regions", []), key=lambda x: x.get("order", 99)):
            conds = []
            for gid in r.get("groups", []):
                g = gmap.get(gid)
                if not g:
                    continue
                items = by_group.get(gid, [])
                conds.append({
                    "id": gid, "name": g["name"],
                    "body_part": g.get("body_part", ""),
                    "modality": g.get("modality", []),
                    "count": len(items),
                    "has_images": bool(items),
                    "caution": g.get("caution", ""),
                    "search_query": g.get("search_query", ""),
                })
            regions.append({
                "id": r["id"], "name": r["name"], "en": r.get("en", ""),
                "note": r.get("note", ""),
                "count": sum(c["count"] for c in conds),
                "conditions": conds,
            })
        return {
            "version": self.tax_def.get("version", ""),
            "regions": regions,
            "totals": {
                "regions": len(regions),
                "conditions": sum(len(r["conditions"]) for r in regions),
                "conditions_with_images": sum(1 for r in regions for c in r["conditions"] if c["has_images"]),
                "images": len(imgs),
            },
        }

    def stats(self):
        return {
            "documents": self.N,
            "signs": sum(1 for d in self.docs if d["_type"] == "sign"),
            "standards": sum(1 for d in self.docs if d["_type"] == "standard"),
            "cases": sum(1 for d in self.docs if d["_type"] == "case"),
            "guidelines": sum(1 for d in self.docs if d["_type"] == "guideline"),
            "groups": len({d.get("group_id") for d in self.docs if d["_type"] == "case"}),
            "regions": len(self.tax_def.get("regions", [])),
            "conditions": len(self.group_defs),
            "sources": len(self.sources),
            "sign_links": len(self.link_rows),
            "linked_signs": len(self.links_by_sign),
            "linked_images": len(self.links_by_image),
            "linked_regions": sum(len(x.get("regions", [])) for x in self.link_rows),
            "linked_quotes": len({x["quote"] for x in self.link_rows}),
            "built_at": _built_at(),
        }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        idx = build()
        print("built", idx["N"], "docs ->", INDEX)
    else:
        kb = KB()
        q = " ".join(sys.argv[1:]) or "甲状腺低回声结节"
        r = kb.search(q)
        print(json.dumps(r, ensure_ascii=False, indent=2)[:3000])
