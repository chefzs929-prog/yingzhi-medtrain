#!/usr/bin/env python3
"""补采第二批影像：乳腺钼靶、脊柱 MRI、超声、骨关节。"""
import json, os, re, time, urllib.parse, urllib.request

UA = "MedTrainEduBot/1.0 (https://commons.wikimedia.org/wiki/User:MedTrainEdu; medtrain.edu@example.org) python-urllib/3.11"
API = "https://commons.wikimedia.org/w/api.php"
META = "kb/data/new_images.json"

QUERIES = [
    ("mg", "mammogram breast mass MLO filetype:bitmap"),
    ("mg", "mammography microcalcification breast filetype:bitmap"),
    ("mg", "breast cancer mammography CC view filetype:bitmap"),
    ("spine_mr", "MRI spine sagittal T2 filetype:bitmap"),
    ("spine_mr", "MRI lumbar disc herniation sagittal filetype:bitmap"),
    ("us", "ultrasound liver lesion filetype:bitmap"),
    ("us", "ultrasound gallbladder stone filetype:bitmap"),
    ("us", "echocardiography apical four chamber filetype:bitmap"),
    ("msk", "X-ray femur fracture filetype:bitmap"),
    ("msk", "X-ray ankle fracture filetype:bitmap"),
    ("msk", "MRI shoulder rotator cuff filetype:bitmap"),
    ("chest_pa", "chest x-ray cardiomegaly filetype:bitmap"),
    ("chest_pa", "chest radiograph atelectasis filetype:bitmap"),
    ("abd_ct", "CT abdomen liver cirrhosis filetype:bitmap"),
    ("head_mr", "MRI brain stroke diffusion filetype:bitmap"),
    ("head_ct", "CT head subdural hematoma filetype:bitmap"),
]

BAD_LIC = re.compile(r"non[- ]?free|fair use|copyright", re.I)
OK_LIC = re.compile(r"^(CC0|CC BY|CC-BY|Public domain|PD)", re.I)
BAD_TITLE = re.compile(r"diagram|schema|drawing|illustration|logo|icon|chart|graph|white house|poster", re.I)


def api(params):
    q = urllib.parse.urlencode(params)
    for attempt in range(5):
        req = urllib.request.Request(API + "?" + q, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(8 * (attempt + 1)); continue
            raise
    raise RuntimeError("429 persistent")


def clean(h):
    return re.sub(r"<[^>]+>", "", h or "").strip()


def main():
    items = json.load(open(META)) if os.path.exists(META) else []
    seen = {x["page"] for x in items}
    for tag, q in QUERIES:
        try:
            d = api({"action": "query", "generator": "search", "gsrsearch": q,
                     "gsrnamespace": 6, "gsrlimit": 12,
                     "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
                     "iiurlwidth": 1400, "format": "json"})
        except Exception as e:
            print("FAIL", tag, e); continue
        for p in d.get("query", {}).get("pages", {}).values():
            ii = p["imageinfo"][0]; em = ii.get("extmetadata", {})
            lic = clean(em.get("LicenseShortName", {}).get("value", ""))
            title = p["title"].replace("File:", "")
            if p["title"] in seen or BAD_TITLE.search(title): continue
            if not OK_LIC.match(lic) or BAD_LIC.search(lic): continue
            if ii.get("width", 0) < 900: continue
            if ii.get("mime", "") not in ("image/jpeg", "image/png"): continue
            items.append({"tag": tag, "page": p["title"], "title": title, "license": lic,
                          "artist": clean(em.get("Artist", {}).get("value", ""))[:120],
                          "desc": clean(em.get("ImageDescription", {}).get("value", ""))[:400],
                          "url": ii.get("thumburl") or ii["url"], "full": ii["url"],
                          "w": ii.get("thumbwidth", ii["width"]), "h": ii.get("thumbheight", ii["height"]),
                          "source_page": "https://commons.wikimedia.org/wiki/" + p["title"].replace(" ", "_")})
            seen.add(p["title"])
        time.sleep(3.0)
    json.dump(items, open(META, "w"), ensure_ascii=False, indent=1)
    print("total", len(items))


if __name__ == "__main__":
    main()
