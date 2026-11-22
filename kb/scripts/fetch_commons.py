#!/usr/bin/env python3
"""从 Wikimedia Commons 抓取公开许可的医学影像候选。

合规约束：
1. 只接受 CC0 / 公有领域 / CC BY / CC BY-SA（排除 NC、ND、GFDL）；
2. 描述中出现姓名、ID、患者编号等隐私线索的直接丢弃；
3. 只下载缩略图（宽 900），原图链接保留在元数据中；
4. 下载后仍需人工逐张核验，未核验的不得进入正式库。
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAND = ROOT / "_candidates"
CAND.mkdir(exist_ok=True)

UA = "DeepWorksKB/1.0 (hackathon teaching demo; contact: local)"
API = "https://commons.wikimedia.org/w/api.php"

QUERIES = [
    ("chest radiograph normal", "CR", "胸部"),
    ("chest x-ray pneumonia", "CR", "胸部"),
    ("CT scan thorax", "CT", "胸部"),
    ("CT abdomen", "CT", "腹部"),
    ("MRI brain", "MR", "头颅"),
    ("MRI knee", "MR", "膝关节"),
    ("ultrasound thyroid", "US", "甲状腺"),
    ("ultrasound abdomen", "US", "腹部"),
    ("mammography breast", "MG", "乳腺"),
    ("CT head", "CT", "头颅"),
]

LICENSE_OK = re.compile(
    r"^(cc0|cc-by-[234]\.0|cc-by-sa-[234]\.0|public domain|pd-.*|pd)$", re.I
)
PRIVACY_BAD = re.compile(
    r"(patient\s*name|name\s*:|姓名|患者姓名|id\s*[:：]\s*\d|mrn|hospital\s*number|身份证)",
    re.I,
)


def api(params):
    params.update({"action": "query", "format": "json"})
    url = API + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise last


def search(term, limit=20):
    d = api({
        "list": "search",
        "srsearch": term,
        "srnamespace": "6",
        "srlimit": str(limit),
    })
    return [x["title"] for x in d.get("query", {}).get("search", [])]


def info(title):
    d = api({
        "prop": "imageinfo",
        "titles": title,
        "iiprop": "url|size|mime|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|License|Artist|Credit|ImageDescription|UsageTerms",
        "iiurlwidth": "900",
    })
    pages = d.get("query", {}).get("pages", {})
    if not pages:
        return None
    p = list(pages.values())[0]
    if "imageinfo" not in p:
        return None
    ii = p["imageinfo"][0]
    em = ii.get("extmetadata", {})
    get = lambda k: re.sub(r"<[^>]+>", "", str(em.get(k, {}).get("value", ""))).strip()
    return {
        "title": title,
        "page": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
        "mime": ii.get("mime", ""),
        "width": ii.get("width", 0),
        "height": ii.get("height", 0),
        "bytes": ii.get("size", 0),
        "thumb": ii.get("thumburl", ""),
        "original": ii.get("url", ""),
        "license_short": get("LicenseShortName"),
        "license_code": get("License"),
        "artist": get("Artist")[:120],
        "credit": get("Credit")[:160],
        "description": get("ImageDescription")[:600],
    }


def main():
    manifest = []
    seen = set()
    done = set()
    if (CAND / "manifest.json").exists():
        manifest = json.loads((CAND / "manifest.json").read_text(encoding="utf8"))
        seen = {m["title"] for m in manifest}
        done = {m["query"] for m in manifest}
    start_index = len(manifest)
    for term, modality, part in QUERIES:
        if term in done:
            continue
        time.sleep(2.0)
        try:
            titles = search(term)
        except Exception as e:
            print("search fail", term, e, file=sys.stderr)
            continue
        kept = 0
        for t in titles:
            if kept >= 4 or t in seen:
                continue
            try:
                it = info(t)
            except Exception:
                continue
            if not it:
                continue
            if it["mime"] not in ("image/jpeg", "image/png"):
                continue
            if it["width"] < 600 or it["bytes"] > 6_000_000:
                continue
            lic = (it["license_short"] or "").lower().replace(" ", "-")
            code = (it["license_code"] or "").lower()
            if not (LICENSE_OK.match(lic) or LICENSE_OK.match(code)):
                continue
            if PRIVACY_BAD.search(it["description"] or ""):
                continue
            seen.add(t)
            it.update({"query": term, "modality": modality, "body_part": part,
                       "status": "candidate"})
            manifest.append(it)
            kept += 1
            time.sleep(1.2)
        print(f"{term}: {kept} candidates")

    (CAND / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print("total candidates:", len(manifest))

    for i, it in enumerate(manifest, 1):
        if it.get("file"):
            continue
        ext = ".jpg" if it["mime"] == "image/jpeg" else ".png"
        out = CAND / f"cand-{i:03d}{ext}"
        try:
            req = urllib.request.Request(it["thumb"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                out.write_bytes(r.read())
            it["file"] = out.name
            print("saved", out.name, it["title"][:60])
        except Exception as e:
            print("download fail", out.name, e)
            it["file"] = ""
        time.sleep(0.2)

    (CAND / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8"
    )


if __name__ == "__main__":
    main()
