#!/usr/bin/env python3
"""在线相似图像/病例检索接口（预留 + 可调用）。

设计边界
--------
1. 只返回候选元数据与来源链接：不下载图像、不入库、不解析图像内容。
2. 许可白名单前置过滤：仅接受 CC0 / 公有领域 / CC BY / CC BY-SA；
   命中 NC、ND 或未知许可时 `license_ok=False`，只作提示，不进入待核验队列。
3. 隐私模式提示：标题或公开描述中出现日期、编号、疑似姓名缩写时标记
   `flags`，要求人工看图核验后才可入库。
4. 入库不在本模块发生：人工核验通过后走 `scripts/add_cases.py` 既有流程。

Provider 插件
-------------
每个 provider 是一个函数 `fn(query, limit, timeout) -> (status, items, error)`，
在 `PROVIDERS` 注册。新增来源只需追加一个函数，不改变对外接口。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "_candidates" / "online_queue.jsonl"
UA = "DeepWorksKB/1.0 (teaching image index; contact: local demo)"
CACHE_TTL = 300
_CACHE: dict[tuple, tuple[float, dict]] = {}

LICENSE_ALLOW = ("cc0", "public domain", "pd-", "cc by", "cc-by")
LICENSE_DENY = ("nc", "nd", "noncommercial", "no derivative", "fair use", "copyright")

PRIVACY_PATTERNS = [
    (r"\b(19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b", "含日期"),
    (r"\b(?:MRN|HN|ID|No\.?|Case)\s*[:#]?\s*\d{4,}\b", "含编号"),
    (r"(?:病例号|检查号|住院号|患者编号|就诊号)\s*[:：#]?\s*[A-Za-z0-9]{4,}", "含编号"),
    (r"\b\d{8,}\b", "含长数字串"),
    (r"\b[A-Z]\.\s?[A-Z]\.", "疑似姓名缩写"),
]


def enabled() -> bool:
    return os.environ.get("KB_ONLINE_SEARCH", "1").strip() not in ("0", "false", "off")


def license_ok(text: str) -> tuple[bool, str]:
    t = (text or "").lower()
    if not t:
        return False, "未标注许可"
    if any(k in t for k in LICENSE_DENY):
        return False, "许可含 NC/ND 或未授权，排除"
    if any(k in t for k in LICENSE_ALLOW):
        return True, "许可在白名单内"
    return False, "许可不在白名单"


def privacy_flags(*texts: str) -> list[str]:
    blob = " ".join(x for x in texts if x)
    return sorted({label for pat, label in PRIVACY_PATTERNS if re.search(pat, blob)})


def _get(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _item(provider, title, page_url, thumb, license_text, snippet, extra=None):
    ok, why = license_ok(license_text)
    flags = privacy_flags(title, snippet)
    out = {
        "provider": provider, "title": (title or "").strip()[:160],
        "page_url": page_url, "thumb_url": thumb,
        "license": (license_text or "").strip()[:60],
        "license_ok": ok, "license_note": why,
        "snippet": (snippet or "").strip()[:220],
        "flags": flags,
        "ingest": "人工核验许可与隐私后，用 scripts/add_cases.py 入库",
    }
    if extra:
        out.update(extra)
    return out


# ---------------- providers ----------------

def commons(query: str, limit: int, timeout: float):
    """Wikimedia Commons 文件搜索（CC0 / CC BY / CC BY-SA 为主）。"""
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrnamespace": "6", "gsrsearch": query, "gsrlimit": str(limit),
        "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": "480",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        raw = _get(url, timeout)
    except urllib.error.HTTPError as e:
        return ("rate_limited" if e.code == 429 else "error"), [], f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return "unreachable", [], type(e).__name__
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "error", [], "响应非 JSON"
    pages = ((data.get("query") or {}).get("pages") or {})
    items = []
    for p in pages.values():
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
        desc = re.sub(r"<[^>]+>", " ", (meta.get("ImageDescription") or {}).get("value", ""))
        items.append(_item(
            "commons", p.get("title", "").replace("File:", ""),
            info.get("descriptionurl") or ("https://commons.wikimedia.org/wiki/" + p.get("title", "")),
            info.get("thumburl"), lic, desc,
            {"width": info.get("width"), "height": info.get("height")},
        ))
    return ("ok" if items else "empty"), items, ""


def openi(query: str, limit: int, timeout: float):
    """Open-i（NCBI 影像库）：返回影像与其公开说明。"""
    url = "https://openi.nlm.nih.gov/api/search?" + urllib.parse.urlencode(
        {"query": query, "m": "1", "n": str(limit)})
    try:
        raw = _get(url, timeout)
    except urllib.error.HTTPError as e:
        return ("rate_limited" if e.code == 429 else "error"), [], f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return "unreachable", [], type(e).__name__
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "error", [], "响应非 JSON（接口可能已变更）"
    items = []
    for x in (data.get("list") or [])[:limit]:
        items.append(_item(
            "openi", x.get("title") or x.get("imgId", ""),
            "https://openi.nlm.nih.gov/detailedresult?img=" + urllib.parse.quote(str(x.get("imgId", ""))),
            x.get("imgThumb") or x.get("imgLarge"), x.get("license", ""),
            x.get("journal_title", ""),
        ))
    return ("ok" if items else "empty"), items, ""


def pubmed(query: str, limit: int, timeout: float):
    """PubMed 相似病例文献（不是图像，只给文献入口）。"""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    try:
        raw = _get(base + "esearch.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "term": query, "retmax": str(limit), "retmode": "json"}), timeout)
        ids = (json.loads(raw).get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return "empty", [], ""
        raw2 = _get(base + "esummary.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}), timeout)
        res = json.loads(raw2).get("result") or {}
    except urllib.error.HTTPError as e:
        return ("rate_limited" if e.code == 429 else "error"), [], f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return "unreachable", [], type(e).__name__
    items = []
    for pid in ids:
        x = res.get(pid) or {}
        items.append(_item(
            "pubmed", x.get("title", pid), f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
            None, "文献（非图像，许可需逐篇核对）", x.get("fulljournalname", ""),
            {"pmid": pid},
        ))
    return ("ok" if items else "empty"), items, ""


def tcia(query: str, limit: int, timeout: float):
    """TCIA 需 NBIA API 与逐数据集许可核对，未配置时显式返回。"""
    if not os.environ.get("TCIA_API_KEY"):
        return "not_configured", [], "需 TCIA_API_KEY 与数据集许可核对"
    return "not_configured", [], "provider 待接入 NBIA API"


PROVIDERS = {
    "commons": ("Wikimedia Commons", commons),
    "openi": ("Open-i 影像库", openi),
    "pubmed": ("PubMed 病例文献", pubmed),
    "tcia": ("TCIA 影像档案", tcia),
}

POLICY = {
    "read_only": True,
    "downloads": False,
    "auto_ingest": False,
    "license_whitelist": ["CC0", "Public Domain", "CC BY", "CC BY-SA"],
    "license_blocked": ["NC", "ND", "Fair use", "未标注"],
    "privacy_check": "命中日期/编号/姓名缩写时标记，需人工看图核验",
    "ingest_path": "scripts/add_cases.py（人工核验后）",
}


def search(query: str, region: str | None = None, condition: str | None = None,
           provider: str = "all", limit: int = 6, timeout: float = 6.0,
           use_cache: bool = True) -> dict:
    q = (query or "").strip()
    limit = max(1, min(int(limit or 6), 12))
    key = (q.lower(), provider, limit)
    if use_cache and key in _CACHE:
        ts, payload = _CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return {**payload, "cached": True}

    if not enabled():
        return {"enabled": False, "query": {"text": q, "region": region, "condition": condition},
                "providers": [], "items": [], "policy": POLICY, "cached": False,
                "hint": "设置环境变量 KB_ONLINE_SEARCH=1 后重启服务即可启用。"}
    if not q:
        return {"enabled": True, "query": {"text": q}, "providers": [], "items": [],
                "policy": POLICY, "cached": False, "error": "empty_query"}

    targets = list(PROVIDERS) if provider in ("", "all", None) else [provider]
    results, merged = [], []
    for pid in targets:
        if pid not in PROVIDERS:
            results.append({"id": pid, "name": pid, "status": "unknown_provider",
                            "count": 0, "error": "未知 provider", "items": []})
            continue
        name, fn = PROVIDERS[pid]
        try:
            status, items, err = fn(q, limit, timeout)
        except Exception as e:  # noqa: BLE001
            status, items, err = "error", [], type(e).__name__
        results.append({"id": pid, "name": name, "status": status,
                        "count": len(items), "error": err, "items": items})
        merged.extend(items)

    payload = {
        "enabled": True,
        "query": {"text": q, "region": region, "condition": condition},
        "providers": results,
        "items": merged[: limit * 2],
        "policy": POLICY,
        "cached": False,
    }
    _CACHE[key] = (time.time(), payload)
    return payload


def queue_candidate(item: dict) -> dict:
    """把人工确认要核验的候选写入待核验队列（仍不入库）。"""
    if not item or not item.get("page_url"):
        return {"queued": False, "reason": "缺少来源链接"}
    ok, why = license_ok(item.get("license", ""))
    if not ok:
        return {"queued": False, "reason": why}
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "queued_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provider": item.get("provider", ""),
        "title": item.get("title", ""),
        "page_url": item.get("page_url", ""),
        "thumb_url": item.get("thumb_url") or "",
        "license": item.get("license", ""),
        "flags": item.get("flags", []),
        "status": "pending_manual_review",
    }
    with QUEUE.open("a", encoding="utf8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"queued": True, "id": "Q-%d" % int(time.time() * 1000), "path": str(QUEUE.relative_to(ROOT))}


if __name__ == "__main__":
    import sys
    r = search(" ".join(sys.argv[1:]) or "ground-glass opacity", limit=3)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:4000])
