#!/usr/bin/env python3
"""低速补采四肢影像（800px 标准缩略图，避免触发 Wikimedia 限流）。

输出：
    kb/_candidates/limbs_manifest.json
    kb/_candidates/limbs/*.jpg

用法：python3 kb/scripts/fetch_limbs.py
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
CAND = KB / "_candidates"
OUT = CAND / "limbs"
MAN = CAND / "limbs_manifest.json"
UA = "DeepWorksKB/2.0 (hackathon teaching demo; https://example.org/kb)"
API = "https://commons.wikimedia.org/w/api.php"

SPEC = [
    ("X-rays of normal knees", 8, "CR", "膝关节", "knee_ap", "四肢"),
    ("X-rays of normal hands", 8, "CR", "手", "hand_pa", "四肢"),
    ("X-rays of normal feet by dorsoplantar projection", 8, "CR", "足", "foot_ap", "四肢"),
    ("X-rays of normal ankles by anteroposterior view", 6, "CR", "踝", "ankle_ap", "四肢"),
    ("X-rays of normal shoulders", 6, "CR", "肩", "shoulder_ap", "四肢"),
    ("X-rays of normal elbows", 5, "CR", "肘", "elbow_ap", "四肢"),
    ("X-rays of normal wrists", 5, "CR", "腕", "wrist_pa", "四肢"),
]

LICENSE_OK = re.compile(
    r"^(cc0|cc-by-[234]\.0|cc-by-sa-[234]\.0|cc-by-[234]|cc-by-sa-[234]|"
    r"public-domain|public domain|pd|pd-.*)$", re.I
)


def api(params, tries=6):
    params.update({"action": "query", "format": "json"})
    url = API + "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception as e:
            last = e
            wait = 20 * (i + 1)
            print(f"  retry {i+1}/{tries} after {wait}s: {e}", file=sys.stderr)
            time.sleep(wait)
    raise last


def main():
    OUT.mkdir(exist_ok=True)
    manifest = json.loads(MAN.read_text(encoding="utf8")) if MAN.exists() else []
    have = {m["title"] for m in manifest}

    for cat, quota, mod, part, pose, chapter in SPEC:
        try:
            d = api({"list": "categorymembers", "cmtitle": "Category:" + cat,
                     "cmtype": "file", "cmlimit": "50"})
        except Exception as e:
            print(f"[skip] {cat}: {e}", file=sys.stderr)
            continue
        titles = [x["title"] for x in d.get("query", {}).get("categorymembers", [])]
        titles = [t for t in titles if t not in have]
        if not titles:
            print(f"[empty] {cat}")
            time.sleep(4)
            continue

        rows = []
        for i in range(0, len(titles), 30):
            try:
                di = api({"prop": "imageinfo", "titles": "|".join(titles[i:i + 30]),
                          "iiprop": "url|size|mime|extmetadata",
                          "iiextmetadatafilter": "LicenseShortName|License|Artist|ImageDescription",
                          "iiurlwidth": "800"})
            except Exception as e:
                print(f"  info fail: {e}", file=sys.stderr)
                continue
            for p in di.get("query", {}).get("pages", {}).values():
                if "imageinfo" not in p:
                    continue
                ii = p["imageinfo"][0]
                em = ii.get("extmetadata", {})
                g = lambda k: re.sub(r"<[^>]+>", " ", str(em.get(k, {}).get("value", ""))).strip()
                rows.append({
                    "title": p["title"],
                    "page": "https://commons.wikimedia.org/wiki/" +
                            urllib.parse.quote(p["title"].replace(" ", "_")),
                    "mime": ii.get("mime", ""),
                    "width": ii.get("width", 0),
                    "height": ii.get("height", 0),
                    "bytes": ii.get("size", 0),
                    "thumb": ii.get("thumburl", ""),
                    "license_short": g("LicenseShortName"),
                    "license_code": g("License"),
                    "artist": g("Artist")[:120],
                    "description": g("ImageDescription")[:400],
                })
            time.sleep(4)

        kept = 0
        for it in rows:
            if kept >= quota:
                break
            if it["mime"] not in ("image/jpeg", "image/png") or it["width"] < 600:
                continue
            lic = (it["license_short"] or "").lower().replace(" ", "-")
            if not (LICENSE_OK.match(lic) or LICENSE_OK.match((it["license_code"] or "").lower())):
                continue
            idx = len(manifest) + 1
            ext = ".png" if it["mime"] == "image/png" else ".jpg"
            name = f"limb-{idx:03d}{ext}"
            try:
                req = urllib.request.Request(it["thumb"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=45) as r:
                    (OUT / name).write_bytes(r.read())
            except Exception as e:
                print(f"  download fail {name}: {e}", file=sys.stderr)
                time.sleep(15)
                continue
            it.update({"file": name, "category": cat, "modality": mod,
                       "body_part": part, "pose_class": pose, "chapter": chapter,
                       "level": "global", "license_ok": True})
            manifest.append(it)
            have.add(it["title"])
            kept += 1
            print(f"  saved {name} {it['title'][:55]}")
            time.sleep(3.5)
        print(f"{cat}: +{kept} (total {len(manifest)})")
        time.sleep(4)

    MAN.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    print(f"\n合计 {len(manifest)} 张")


if __name__ == "__main__":
    main()
