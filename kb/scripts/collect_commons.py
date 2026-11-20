#!/usr/bin/env python3
"""从 Wikimedia Commons 采集有明确许可的医学影像，供补充病例使用。
仅下载：位图、宽度>=900、许可为 CC/PD、非示意图。
输出：kb/images/new/*.jpg + kb/data/new_images.json
"""
import json, os, re, sys, time, urllib.parse, urllib.request

UA = "MedTrainEduBot/1.0 (https://commons.wikimedia.org/wiki/User:MedTrainEdu; medtrain.edu@example.org) python-urllib/3.11"
API = "https://commons.wikimedia.org/w/api.php"
OUT = "kb/images/new"
META = "kb/data/new_images.json"

QUERIES = [
    ("chest_pa", "chest radiograph pneumonia filetype:bitmap"),
    ("chest_pa", "chest x-ray tuberculosis filetype:bitmap"),
    ("chest_pa", "chest radiograph pleural effusion filetype:bitmap"),
    ("chest_pa", "chest x-ray lung nodule filetype:bitmap"),
    ("chest_ct", "computed tomography chest lung filetype:bitmap"),
    ("chest_ct", "CT pulmonary emphysema filetype:bitmap"),
    ("head_ct", "CT head hemorrhage filetype:bitmap"),
    ("head_ct", "CT brain infarct filetype:bitmap"),
    ("head_mr", "MRI brain glioma filetype:bitmap"),
    ("head_mr", "MRI brain multiple sclerosis filetype:bitmap"),
    ("spine_mr", "MRI lumbar spine disc herniation filetype:bitmap"),
    ("spine_mr", "MRI cervical spine filetype:bitmap"),
    ("msk", "MRI knee meniscus filetype:bitmap"),
    ("msk", "radiograph wrist fracture filetype:bitmap"),
    ("msk", "radiograph shoulder dislocation filetype:bitmap"),
    ("msk", "radiograph foot fracture filetype:bitmap"),
    ("us", "ultrasound thyroid nodule filetype:bitmap"),
    ("us", "ultrasound breast lesion filetype:bitmap"),
    ("mg", "mammography breast cancer filetype:bitmap"),
    ("abd_ct", "CT liver metastasis filetype:bitmap"),
    ("abd_ct", "CT kidney stone filetype:bitmap"),
]

BAD_LIC = re.compile(r"non[- ]?free|fair use|copyright", re.I)
OK_LIC = re.compile(r"^(CC0|CC BY|CC-BY|Public domain|PD)", re.I)
BAD_TITLE = re.compile(r"diagram|schema|drawing|illustration|logo|icon|chart|graph", re.I)


def api(params):
    q = urllib.parse.urlencode(params)
    for attempt in range(4):
        req = urllib.request.Request(API + "?" + q, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(6 * (attempt + 1)); continue
            raise
    raise RuntimeError("429 persistent")


def clean(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def main():
    os.makedirs(OUT, exist_ok=True)
    seen = set()
    if os.path.exists(META):
        for x in json.load(open(META)):
            seen.add(x["page"])
    items = json.load(open(META)) if os.path.exists(META) else []
    for tag, q in QUERIES:
        try:
            d = api({
                "action": "query", "generator": "search", "gsrsearch": q,
                "gsrnamespace": 6, "gsrlimit": 12,
                "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
                "iiurlwidth": 1400, "format": "json",
            })
        except Exception as e:
            print("API FAIL", tag, e); continue
        pages = d.get("query", {}).get("pages", {})
        for p in pages.values():
            ii = p["imageinfo"][0]
            em = ii.get("extmetadata", {})
            lic = clean(em.get("LicenseShortName", {}).get("value", ""))
            title = p["title"].replace("File:", "")
            if p["title"] in seen: continue
            if BAD_TITLE.search(title): continue
            if not OK_LIC.match(lic) or BAD_LIC.search(lic): continue
            if ii.get("width", 0) < 900: continue
            if ii.get("mime", "") not in ("image/jpeg", "image/png"): continue
            items.append({
                "tag": tag, "page": p["title"], "title": title,
                "license": lic,
                "artist": clean(em.get("Artist", {}).get("value", ""))[:120],
                "desc": clean(em.get("ImageDescription", {}).get("value", ""))[:400],
                "url": ii.get("thumburl") or ii["url"],
                "full": ii["url"], "w": ii.get("thumbwidth", ii["width"]),
                "h": ii.get("thumbheight", ii["height"]),
                "source_page": "https://commons.wikimedia.org/wiki/" + p["title"].replace(" ", "_"),
            })
            seen.add(p["title"])
        time.sleep(3.0)
    # 去重（同一文件多次命中）
    uniq, keys = [], set()
    for x in items:
        if x["page"] in keys: continue
        keys.add(x["page"]); uniq.append(x)
    json.dump(uniq, open(META, "w"), ensure_ascii=False, indent=1)
    print("candidates", len(uniq))


if __name__ == "__main__":
    main()
