"""网络文献检索：PubMed E-utilities。

为什么选 PubMed：
- 无需 API key，黑客松现场不用配账号；
- esearch + esummary 两次请求约 0.7s，实测比 Europe PMC 稳定；
- 返回 PMID / DOI / 期刊 / 年份，引用可被评委当场打开核对。

边界：
- 只做检索，不生成结论；标题原样返回，不改写；
- 网络失败返回 ok=false + reason，由上层显式降级，不静默编造文献；
- 中文术语不送检索（PubMed 对中文召回极差），没有英文术语就明确返回 no_english_term；
- 摘要不在这里抓：esummary 不含摘要，逐条 efetch 会拖慢主链路，留给用户点开 PubMed。
"""

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "kb" / "data"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UA = "yingzhi-hackathon/1.0 (educational)"
DEFAULT_LIMIT = 5
TIMEOUT = float(os.environ.get("YZ_LIT_TIMEOUT", "8"))
CACHE_TTL = 3600

_CACHE = {}

MODALITY = {
    "CT": "computed tomography",
    "MR": "magnetic resonance",
    "MRI": "magnetic resonance",
    "US": "ultrasound",
    "CR": "radiography",
    "XR": "radiography",
    "MG": "mammography",
}

# 库里的 body_part 是中文细粒度，映射成 PubMed 常用的英文限定词。
# 不做这层，consolidation 会命中骨科，nodule 会命中植物学。
PART_TERMS = {
    "肺": ["lung", "pulmonary", "chest"],
    "胸膜": ["pleura", "pleural"],
    "纵隔": ["mediastinum", "mediastinal"],
    "心脏": ["heart", "cardiac"],
    "脑": ["brain", "cerebral"],
    "腹部": ["abdomen", "abdominal"],
    "腹腔": ["abdomen", "abdominal"],
    "肝脏": ["liver", "hepatic"],
    "胰胆": ["pancreas", "biliary"],
    "胆道": ["biliary"],
    "胆囊": ["gallbladder"],
    "胰腺": ["pancreas", "pancreatic"],
    "肾脏": ["kidney", "renal"],
    "肠道": ["bowel", "intestine"],
    "骨": ["bone", "skeletal"],
    "关节": ["joint"],
    "膝关节": ["knee"],
    "乳腺": ["breast", "mammary"],
    "甲状腺": ["thyroid"],
}


def _signs():
    p = DATA / "signs.jsonl"
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf8").splitlines():
        if not line.strip():
            continue
        try:
            s = json.loads(line)
        except Exception:
            continue
        if s.get("id"):
            out[s["id"]] = s
    return out


def _is_ascii_term(t):
    return bool(t) and all(ord(ch) < 128 for ch in t)


def build_query(sign_ids=None, extra=None, modality=None, body_parts=None):
    """拼 PubMed 检索式：(征象短语) AND (检查方式) AND (部位) AND humans[mh]。"""
    signs = _signs()
    terms = []
    parts = list(body_parts or [])
    for sid in sign_ids or []:
        s = signs.get(sid) or {}
        en = (s.get("en") or "").strip()
        if en and en not in terms:
            terms.append(en)
        bp = (s.get("body_part") or "").strip()
        if bp and bp not in parts:
            parts.append(bp)
    for t in extra or []:
        t = (t or "").strip()
        if _is_ascii_term(t) and t not in terms:
            terms.append(t)
    if not terms:
        return None

    clauses = ["(%s)" % " OR ".join('"%s"' % t for t in terms[:3])]
    mod = MODALITY.get((modality or "").upper().strip())
    if mod:
        clauses.append('("%s")' % mod)

    part_words = []
    for bp in parts:
        for w in PART_TERMS.get(bp, []):
            if w not in part_words:
                part_words.append(w)
    if part_words:
        clauses.append("(%s)" % " OR ".join("%s[tiab]" % w for w in part_words[:6]))

    clauses.append("humans[mh]")
    return " AND ".join(clauses)


def _get(path, params):
    url = "%s/%s?%s" % (EUTILS, path, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf8"))


def _norm(pmid, row):
    doi = ""
    for aid in row.get("articleids") or []:
        if aid.get("idtype") == "doi":
            doi = aid.get("value") or ""
            break
    journal = (row.get("fulljournalname") or row.get("source") or "").strip()
    return {
        "id": "PMID:%s" % pmid,
        "kind": "literature",
        "source": "PubMed",
        "pmid": pmid,
        "doi": doi or None,
        "title": (row.get("title") or "").strip().rstrip("."),
        "authors": (row.get("sortfirstauthor") or "").strip(),
        "journal": journal,
        "year": (row.get("pubdate") or "").split(" ")[0],
        "cited_by": 0,
        "open_access": False,
        "abstract": "",
        "url": "https://pubmed.ncbi.nlm.nih.gov/%s/" % pmid,
    }


def search(term, limit=DEFAULT_LIMIT):
    if not term:
        return {"ok": False, "reason": "empty_query", "items": [], "query": None}
    key = "%s|%s" % (term, limit)
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return dict(hit[1], cached=True)

    limit = max(1, min(int(limit), 20))
    try:
        found = _get("esearch.fcgi", {
            "db": "pubmed", "retmode": "json", "retmax": limit,
            "sort": "relevance", "term": term,
        })
        ids = ((found.get("esearchresult") or {}).get("idlist") or [])
        hit_count = int((found.get("esearchresult") or {}).get("count") or 0)
        if not ids:
            out = {"ok": True, "reason": None, "items": [], "query": term,
                   "hit_count": hit_count, "source": "PubMed"}
        else:
            summary = _get("esummary.fcgi", {
                "db": "pubmed", "retmode": "json", "id": ",".join(ids),
            })
            rows = summary.get("result") or {}
            items = [_norm(pmid, rows.get(pmid) or {}) for pmid in ids if rows.get(pmid)]
            out = {"ok": True, "reason": None, "items": items, "query": term,
                   "hit_count": hit_count, "source": "PubMed"}
    except Exception as exc:
        return {"ok": False, "reason": "%s: %s" % (type(exc).__name__, exc),
                "items": [], "query": term, "source": "PubMed"}

    _CACHE[key] = (now, out)
    return out


def search_signs(sign_ids, extra=None, modality=None, body_parts=None, limit=DEFAULT_LIMIT):
    q = build_query(sign_ids, extra, modality, body_parts)
    if not q:
        return {"ok": False, "reason": "no_english_term", "items": [], "query": None,
                "source": "PubMed"}
    return search(q, limit)
