#!/usr/bin/env python3
"""补采脊柱影像（颈椎/腰椎），低速、少量。失败不影响主流程。"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
OUT = KB / "_candidates" / "spine"
MAN = KB / "_candidates" / "spine_manifest.json"
UA = "DeepWorksKB/2.0 (hackathon teaching demo; https://example.org/kb)"
API = "https://commons.wikimedia.org/w/api.php"

SPEC = [
    ("search", "cervical spine x-ray lateral", 5, "颈椎", "cspine_lat", "脊柱"),
    ("search", "lumbar spine x-ray lateral", 5, "腰椎", "lspine_lat", "脊柱"),
]
LIC = re.compile(r"^(cc0|cc-by-[234]\.0|cc-by-sa-[234]\.0|cc-by-[234]|cc-by-sa-[234]|public-domain|public domain|pd|pd-.*)$", re.I)


def api(p, tries=5):
    p.update({"action": "query", "format": "json"})
    u = API + "?" + urllib.parse.urlencode(p)
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers={"User-Agent": UA}), timeout=40))
        except Exception as e:
            print("  retry", i + 1, e, file=sys.stderr)
            time.sleep(15 * (i + 1))
    return {}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = json.loads(MAN.read_text(encoding="utf8")) if MAN.exists() else []
    have = {m["title"] for m in man}
    for kind, term, quota, part, pose, chapter in SPEC:
        d = api({"list": "search", "srsearch": term, "srnamespace": "6", "srlimit": "25"})
        titles = [x["title"] for x in d.get("query", {}).get("search", [])]
        titles = [t for t in titles if t not in have][:12]
        if not titles:
            print("empty", term); continue
        time.sleep(4)
        di = api({"prop": "imageinfo", "titles": "|".join(titles),
                  "iiprop": "url|size|mime|extmetadata",
                  "iiextmetadatafilter": "LicenseShortName|License|Artist|ImageDescription",
                  "iiurlwidth": "800"})
        rows = []
        for p in di.get("query", {}).get("pages", {}).values():
            if "imageinfo" not in p: continue
            ii = p["imageinfo"][0]; em = ii.get("extmetadata", {})
            g = lambda k: re.sub(r"<[^>]+>", " ", str(em.get(k, {}).get("value", ""))).strip()
            rows.append({"title": p["title"], "page": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(p["title"].replace(" ", "_")),
                         "mime": ii.get("mime", ""), "width": ii.get("width", 0), "height": ii.get("height", 0),
                         "bytes": ii.get("size", 0), "thumb": ii.get("thumburl", ""),
                         "license_short": g("LicenseShortName"), "license_code": g("License"),
                         "artist": g("Artist")[:120], "description": g("ImageDescription")[:400]})
        kept = 0
        for it in rows:
            if kept >= quota: break
            if it["mime"] not in ("image/jpeg", "image/png") or it["width"] < 600: continue
            if not (LIC.match((it["license_short"] or "").lower().replace(" ", "-")) or LIC.match((it["license_code"] or "").lower())): continue
            name = f"spine-{len(man)+1:03d}{'.png' if it['mime']=='image/png' else '.jpg'}"
            try:
                with urllib.request.urlopen(urllib.request.Request(it["thumb"], headers={"User-Agent": UA}), timeout=45) as r:
                    (OUT / name).write_bytes(r.read())
            except Exception as e:
                print("  dl fail", e, file=sys.stderr); time.sleep(15); continue
            it.update({"file": name, "category": term, "modality": "CR", "body_part": part,
                       "pose_class": pose, "chapter": chapter, "level": "global", "license_ok": True})
            man.append(it); have.add(it["title"]); kept += 1
            print("  saved", name, it["title"][:55]); time.sleep(3.5)
        print(term, "+", kept); time.sleep(4)
    MAN.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf8")
    print("total", len(man))


if __name__ == "__main__":
    main()
