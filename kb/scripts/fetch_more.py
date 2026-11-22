#!/usr/bin/env python3
"""按征象组抓取公开许可影像候选（Wikimedia Commons）。

严格约束：
- 仅 CC0 / 公有领域 / CC BY / CC BY-SA；
- 描述含姓名、ID、患者编号的直接丢弃；
- 下载后必须逐张人工核验，未核验不得入库；
- 低频请求 + 退避，避免触发限流。
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAND = ROOT / "_candidates2"
CAND.mkdir(exist_ok=True)
UA = "DeepWorksKB/1.0 (hackathon teaching demo; local use)"

QUERIES = [
    ("chest radiograph pneumonia", "GRP-LUNG-CONSOLIDATION", "CR", "肺"),
    ("chest x-ray pleural effusion", "GRP-PLEURAL", "CR", "胸膜"),
    ("chest x-ray pneumothorax", "GRP-PLEURAL", "CR", "胸膜"),
    ("chest CT ground glass opacity", "GRP-LUNG-GGO", "CT", "肺"),
    ("chest CT lung nodule", "GRP-LUNG-NODULE", "CT", "肺"),
    ("chest radiograph tuberculosis", "GRP-LUNG-CONSOLIDATION", "CR", "肺"),
    ("thyroid ultrasound nodule", "GRP-THYROID", "US", "甲状腺"),
    ("thyroid ultrasound", "GRP-THYROID", "US", "甲状腺"),
    ("mammography calcification", "GRP-BREAST", "MG", "乳腺"),
    ("mammography mass", "GRP-BREAST", "MG", "乳腺"),
    ("breast ultrasound lesion", "GRP-BREAST", "US", "乳腺"),
    ("CT head hemorrhage", "GRP-HEAD", "CT", "头颅"),
    ("MRI brain stroke", "GRP-HEAD", "MR", "头颅"),
    ("MRI brain tumor", "GRP-HEAD", "MR", "头颅"),
    ("CT liver lesion", "GRP-ABDOMEN", "CT", "肝"),
    ("CT kidney cyst", "GRP-ABDOMEN", "CT", "肾"),
    ("ultrasound gallbladder stone", "GRP-ABDOMEN", "US", "胆囊"),
    ("MRI knee meniscus", "GRP-MSJ", "MR", "膝"),
    ("MRI lumbar spine disc", "GRP-MSJ", "MR", "脊柱"),
    ("X-ray bone fracture", "GRP-MSJ", "CR", "骨"),
    ("chest radiograph normal", "GRP-NORMAL", "CR", "胸"),
    ("CT head normal", "GRP-NORMAL", "CT", "头颅"),
]

LICENSE_OK = re.compile(r"^(cc0|cc-by-[234]\.0|cc-by-sa-[234]\.0|public domain|pd-.*|pd)$", re.I)
PRIVACY_BAD = re.compile(
    r"(patient\s*name|name\s*:|姓名|患者姓名|\bid\s*[:：]\s*\d|mrn|hospital\s*number|身份证|\bage\s*[:：]\s*\d)",
    re.I,
)
API = "https://commons.wikimedia.org/w/api.php"


def api(params, tries=5):
    params.update({"action": "query", "format": "json"})
    url = API + "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(8 * (i + 1))
    raise last


def search(term, limit=14):
    d = api({"list": "search", "srsearch": term, "srnamespace": "6", "srlimit": str(limit)})
    return [x["title"] for x in d.get("query", {}).get("search", [])]


def info(title):
    d = api({
        "prop": "imageinfo", "titles": title,
        "iiprop": "url|size|mime|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|License|Artist|Credit|ImageDescription",
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
        "mime": ii.get("mime", ""), "width": ii.get("width", 0), "height": ii.get("height", 0),
        "bytes": ii.get("size", 0), "thumb": ii.get("thumburl", ""), "original": ii.get("url", ""),
        "license_short": get("LicenseShortName"), "license_code": get("License"),
        "artist": get("Artist")[:120], "description": get("ImageDescription")[:600],
    }


def main():
    manifest = []
    if (CAND / "manifest.json").exists():
        manifest = json.loads((CAND / "manifest.json").read_text(encoding="utf8"))
    seen = {m["title"] for m in manifest}
    done = {m["query"] for m in manifest}

    for term, group, modality, part in QUERIES:
        if term in done:
            continue
        try:
            titles = search(term)
        except Exception as e:
            print("search fail", term, e, file=sys.stderr)
            time.sleep(20)
            continue
        kept = 0
        for t in titles:
            if kept >= 3 or t in seen:
                continue
            try:
                it = info(t)
            except Exception:
                time.sleep(10)
                continue
            if not it:
                continue
            if it["mime"] not in ("image/jpeg", "image/png"):
                continue
            if it["width"] < 500 or it["bytes"] > 6_000_000:
                continue
            lic = (it["license_short"] or "").lower().replace(" ", "-")
            code = (it["license_code"] or "").lower()
            if not (LICENSE_OK.match(lic) or LICENSE_OK.match(code)):
                continue
            if PRIVACY_BAD.search(it["description"] or ""):
                continue
            seen.add(t)
            it.update({"query": term, "group_id": group, "modality": modality,
                       "body_part": part, "status": "candidate"})
            manifest.append(it)
            kept += 1
            time.sleep(2.0)
        print(f"{term}: {kept}", flush=True)
        time.sleep(4)
        (CAND / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")

    for i, it in enumerate(manifest, 1):
        if it.get("file"):
            continue
        ext = ".jpg" if it["mime"] == "image/jpeg" else ".png"
        out = CAND / f"cand-{i:03d}{ext}"
        ok = False
        for attempt in range(3):
            try:
                req = urllib.request.Request(it["thumb"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=40) as r:
                    out.write_bytes(r.read())
                it["file"] = out.name
                ok = True
                break
            except Exception as e:
                print("dl retry", out.name, str(e)[:50], flush=True)
                time.sleep(20)
        print(("saved " if ok else "fail  ") + out.name, it["title"][:55], flush=True)
        time.sleep(4)
        (CAND / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")

    print("total", len(manifest), "saved", sum(1 for x in manifest if x.get("file")))


if __name__ == "__main__":
    main()
