"""RadioCheck 知识库只读数据层。

职责：
  - 把 kb/data 与构建产物里的知识库数据按需暴露为 JSON API；
  - 提供轻量的关键词检索（不是向量检索，也不做诊断）；
  - 提供影像文件读取与站点静态文件定位。

设计约束：
  - 只读；不写库、不改数据、不做推理。
  - 文件带 mtime/size 缓存，数据更新后无需重启即可读到新版本。
  - 所有路径都限制在 kb/ 与 outputs/medtrain/ 内，拒绝目录穿越。
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KB_DATA = ROOT / "kb" / "data"
KB_IMAGES = ROOT / "kb" / "images"
SITE = ROOT / "outputs" / "medtrain"

_LOCK = threading.Lock()
_CACHE: dict[str, tuple[int, int, object]] = {}

MAX_SEARCH = 30


# ---------------------------------------------------------------- 读文件与缓存

def _load_json(path: Path):
    try:
        st = path.stat()
    except OSError:
        return None
    key = str(path)
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            return hit[2]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    with _LOCK:
        _CACHE[key] = (st.st_mtime_ns, st.st_size, data)
    return data


def _load_jsonl(path: Path):
    try:
        st = path.stat()
    except OSError:
        return []
    key = str(path)
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            return hit[2]
    rows = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    with _LOCK:
        _CACHE[key] = (st.st_mtime_ns, st.st_size, rows)
    return rows


def _norm(text) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or "").lower())


def _dice(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if len(a) < 2 or len(b) < 2:
        return 1.0 if a == b else 0.0
    A = {a[i:i + 2] for i in range(len(a) - 1)}
    B = {b[i:i + 2] for i in range(len(b) - 1)}
    return 2.0 * len(A & B) / (len(A) + len(B))


# ---------------------------------------------------------------- 数据快照

def chest():
    return _load_json(KB_DATA / "chest_reading.json")


def exam():
    return _load_json(KB_DATA / "exam_cases.json")


def lab():
    return _load_json(KB_DATA / "student_lab.json")


def review_queue():
    return _load_json(SITE / "data" / "audit" / "review_queue.json")


def _rows(name: str):
    return _load_jsonl(KB_DATA / name)


def counts() -> dict:
    c = chest() or {}
    e = exam() or {}
    l = lab() or {}
    return {
        "chest_cases": len(c.get("cases") or []),
        "chest_zones": sum(len(x.get("zones") or []) for x in (c.get("cases") or [])),
        "exam_cases": len(e.get("cases") or []),
        "signs": len(_rows("signs.jsonl")),
        "concepts": len(_rows("concepts.jsonl")),
        "guidelines": len(_rows("guidelines.jsonl")),
        "claims": len(_rows("claims.jsonl")),
        "regions": len(_rows("regions.jsonl")),
        "lab_signs": len(l.get("signs") or []),
        "lab_questions": len(l.get("questions") or []),
    }


def meta() -> dict:
    c = chest() or {}
    return {
        "ok": True,
        "source": "kb/data",
        "version": c.get("version") or "unknown",
        "generated_at": c.get("generated_at") or "",
        "counts": counts(),
        "disclaimer": c.get("disclaimer") or "仅用于医学影像教学与研究，不构成诊断意见。",
        "endpoints": [
            "/api/kb/health",
            "/api/kb/chest",
            "/api/kb/exam",
            "/api/kb/lab",
            "/api/kb/search?q=气胸",
            "/api/kb/signs?q=气胸",
            "/api/kb/concepts?q=肺水肿",
            "/api/kb/guidelines?q=结节",
            "/api/kb/claims?image_id=CASE-001",
            "/api/kb/regions?image_id=CASE-001",
            "/api/kb/sign/SIGN-001",
            "/api/kb/case/CASE-001",
            "/api/kb/audit/review",
            "/api/kb/image/<name>",
        ],
    }


# ---------------------------------------------------------------- 检索

def _score(q: str, fields) -> int:
    """fields: [(text, weight), ...]；返回可解释的整数分。"""
    qn = _norm(q)
    if not qn:
        return 0
    best = 0
    for text, weight in fields:
        tn = _norm(text)
        if not tn:
            continue
        if tn == qn:
            score = 100 * weight
        elif qn in tn:
            score = 62 * weight
        elif tn in qn:
            score = 52 * weight
        else:
            d = _dice(qn, tn)
            score = int(34 * weight * d) if d >= 0.34 else 0
        if score > best:
            best = score
    return best


def _snippet(text, limit=96) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s[:limit] + ("…" if len(s) > limit else "")


def search(query: str, limit: int = 12) -> dict:
    q = (query or "").strip()
    limit = max(1, min(int(limit or 12), MAX_SEARCH))
    if not q:
        return {"ok": True, "query": q, "items": [], "count": 0}

    items = []

    def add(kind, rid, title, snippet, score, source_url="", extra=""):
        if score <= 0:
            return
        items.append({
            "kind": kind,
            "id": str(rid or ""),
            "title": str(title or ""),
            "snippet": _snippet(snippet),
            "score": int(score),
            "source_url": str(source_url or ""),
            "extra": str(extra or ""),
        })

    for r in _rows("signs.jsonl"):
        sc = _score(q, [
            (r.get("name"), 1.0), (r.get("en"), 0.8),
            (" ".join(r.get("aliases") or []), 0.9),
            (r.get("appearance"), 0.45),
            (r.get("body_part"), 0.35),
            (" ".join(r.get("may_see_in") or []), 0.35),
            (" ".join(r.get("pitfalls") or []), 0.3),
        ])
        add("sign", r.get("id"), r.get("name"), r.get("appearance"), sc,
            extra=" · ".join([x for x in [r.get("body_part"), "/".join(r.get("modality") or [])] if x]))

    for r in _rows("concepts.jsonl"):
        sc = _score(q, [
            (r.get("name"), 1.0), (r.get("en"), 0.8),
            (" ".join(r.get("aliases") or []), 0.9),
            (r.get("note"), 0.4),
        ])
        add("concept", r.get("id"), r.get("name"), r.get("note"), sc,
            extra="疾病 / 病理概念")

    for r in _rows("guidelines.jsonl"):
        sc = _score(q, [
            (r.get("standard_name"), 0.8), (r.get("category"), 0.7),
            (r.get("statement"), 0.55),
            (" ".join(r.get("conditions") or []), 0.4),
            (" ".join(r.get("keywords") or []), 0.5),
        ])
        add("guideline", r.get("id"),
            " · ".join([x for x in [r.get("standard_name"), r.get("category")] if x]),
            r.get("statement"), sc, r.get("source_url"),
            extra="指南条款")

    for r in _rows("claims.jsonl"):
        sc = _score(q, [
            (r.get("text"), 0.55),
            (" ".join(r.get("sign_ids") or []), 0.25),
        ])
        add("claim", r.get("id"), r.get("id"), r.get("text"), sc,
            extra=" · ".join([x for x in [r.get("image_id"), r.get("region_id")] if x]))

    for r in _rows("cases.jsonl"):
        sc = _score(q, [
            (r.get("title"), 0.9),
            (r.get("description_public"), 0.5),
            (r.get("teaching_note"), 0.4),
            (" ".join(r.get("sign_tags") or []), 0.45),
        ])
        add("case", r.get("id"),
            " · ".join([x for x in [r.get("id"), r.get("title")] if x]),
            r.get("description_public") or r.get("teaching_note"), sc,
            r.get("source_page"), extra=r.get("body_part") or "")

    for r in _rows("regions.jsonl"):
        sc = _score(q, [
            (r.get("name"), 0.7), (r.get("name_en"), 0.5),
            (r.get("note"), 0.3),
        ])
        add("region", r.get("id"), r.get("name"), r.get("note"), sc,
            extra=" · ".join([x for x in [r.get("image_id"), r.get("status")] if x]))

    for r in _rows("paragraphs.jsonl"):
        sc = _score(q, [(r.get("text"), 0.4), (r.get("title"), 0.35)])
        add("paragraph", r.get("para_id"),
            " · ".join([x for x in [r.get("title"), r.get("section")] if x]),
            r.get("text"), sc, r.get("source_url"),
            extra="原文段落")

    # 同一 id 只留最高分
    best = {}
    for it in items:
        key = it["id"] or (it["kind"] + ":" + it["title"])
        if key not in best or it["score"] > best[key]["score"]:
            best[key] = it
    out = sorted(best.values(), key=lambda x: (-x["score"], x["kind"], x["id"]))
    return {"ok": True, "query": q, "count": len(out), "items": out[:limit]}


def list_rows(kind: str, q: str = "", image_id: str = "", limit: int = 200) -> dict:
    """按类型列出知识库条目；q 只做简单包含匹配，不做语义检索。"""
    spec = {
        "signs": ("signs.jsonl", ["name", "en", "appearance", "body_part"]),
        "concepts": ("concepts.jsonl", ["name", "en", "note"]),
        "guidelines": ("guidelines.jsonl", ["standard_name", "category", "statement"]),
        "claims": ("claims.jsonl", ["text"]),
        "regions": ("regions.jsonl", ["name", "name_en", "note"]),
        "paragraphs": ("paragraphs.jsonl", ["title", "section", "text"]),
    }
    if kind not in spec:
        return {"ok": False, "error": "unknown kind", "kind": kind}
    filename, fields = spec[kind]
    rows = _rows(filename)
    if image_id:
        rows = [r for r in rows if str(r.get("image_id")) == image_id]
    qn = _norm(q)
    if qn:
        rows = [r for r in rows
                if any(qn in _norm(r.get(f)) for f in fields)]
    limit = max(1, min(int(limit or 200), 1000))
    return {"ok": True, "kind": kind, "count": len(rows), "items": rows[:limit]}


def sign_detail(sign_id: str) -> dict | None:
    sign = next((r for r in _rows("signs.jsonl") if str(r.get("id")) == sign_id), None)
    if not sign:
        return None
    paras = [r for r in _rows("paragraphs.jsonl") if str(r.get("doc_id")) == sign_id]
    cases = []
    for c in (chest() or {}).get("cases") or []:
        zones = [z for z in (c.get("zones") or []) if sign_id in (z.get("sign_ids") or [])]
        if zones:
            cases.append({"id": c.get("id"), "title": c.get("title"),
                          "zones": [{"id": z.get("id"), "name": z.get("name"),
                                     "status": z.get("status")} for z in zones]})
    return {"ok": True, "sign": sign, "paragraphs": paras, "cases": cases[:12]}


def case_detail(case_id: str) -> dict | None:
    for c in (chest() or {}).get("cases") or []:
        if str(c.get("id")) == case_id:
            return {"ok": True, "case": c, "source": "chest_reading"}
    case = next((r for r in _rows("cases.jsonl") if str(r.get("id")) == case_id), None)
    if not case:
        return None
    regions = [r for r in _rows("regions.jsonl") if str(r.get("image_id")) == case_id]
    claims = [r for r in _rows("claims.jsonl") if str(r.get("image_id")) == case_id]
    return {"ok": True, "case": case, "regions": regions, "claims": claims,
            "source": "cases.jsonl"}


# ---------------------------------------------------------------- 文件定位

def _safe_join(root: Path, rel: str) -> Path | None:
    rel = str(rel or "").lstrip("/")
    if not rel or ".." in Path(rel).parts:
        return None
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def image_file(rel: str) -> Path | None:
    raw = str(rel or "").lstrip("/")
    if raw.startswith("images/"):
        raw = raw[len("images/"):]
    return _safe_join(KB_IMAGES, raw)


def site_file(rel: str) -> Path | None:
    return _safe_join(SITE, rel)


def content_type(path: Path) -> str:
    ctype, _ = mimetypes.guess_type(str(path))
    if not ctype:
        if path.suffix == ".webmanifest":
            ctype = "application/manifest+json"
        elif path.suffix in (".js", ".mjs"):
            ctype = "text/javascript"
        elif path.suffix == ".json":
            ctype = "application/json"
        else:
            ctype = "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("application/json", "application/manifest+json", "text/javascript"):
        ctype += "; charset=utf-8"
    return ctype


def site_root() -> Path:
    return SITE
