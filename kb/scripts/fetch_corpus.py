#!/usr/bin/env python3
"""采集 120 例语料所需的公开影像：在既有 32 张基础上补齐 88 张。

合规约束（与 fetch_commons.py 一致）：
1. 只接受 CC0 / 公有领域 / CC BY / CC BY-SA；NC、ND、GFDL 一律丢弃；
2. 只下载 1000px 缩略图，原图链接与许可原文留在清单里；
3. 标题/描述含姓名、病历号等线索的标记 privacy_flag，交人工复核；
4. 未核验的候选只写入 _candidates，不直接进 cases.jsonl。

输出：
    kb/_candidates/corpus_manifest.json
    kb/images/case-033.jpg ... case-120.jpg

重新采集：python3 kb/scripts/fetch_corpus.py
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
IMG = ROOT / "images"
MAN = CAND / "corpus_manifest.json"
UA = "DeepWorksKB/2.0 (hackathon teaching demo; contact: local)"
API = "https://commons.wikimedia.org/w/api.php"

TARGET = 88
START_CASE = 33

# (kind, 目标, 配额, modality, body_part, pose_class, 教学章节)
# kind=cat 走分类成员；kind=search 走关键词兜底
SPEC = [
    ("cat", "X-rays of normal chest", 18, "CR", "胸部", "chest_pa", "胸部"),
    ("cat", "X-rays of normal knees", 10, "CR", "膝关节", "knee_ap", "四肢"),
    ("cat", "X-rays of normal hands", 10, "CR", "手", "hand_pa", "四肢"),
    ("cat", "X-rays of normal feet by dorsoplantar projection", 10, "CR", "足", "foot_ap", "四肢"),
    ("cat", "X-rays of normal ankles by anteroposterior view", 8, "CR", "踝", "ankle_ap", "四肢"),
    ("cat", "X-rays of normal shoulders", 6, "CR", "肩", "shoulder_ap", "四肢"),
    ("cat", "X-rays of normal elbows", 6, "CR", "肘", "elbow_ap", "四肢"),
    ("cat", "X-rays of normal wrists", 6, "CR", "腕", "wrist_pa", "四肢"),
    ("cat", "X-rays of normal thumbs", 4, "CR", "手", "hand_pa", "四肢"),
    ("cat", "X-rays of normal pelvises in children and adolescents", 4, "CR", "骨盆", "pelvis_ap", "四肢"),
    ("search", "cervical spine radiograph normal", 5, "CR", "颈椎", "cspine_lat", "脊柱"),
    ("search", "lumbar spine radiograph normal", 5, "CR", "腰椎", "lspine_lat", "脊柱"),
    ("search", "CT abdomen axial", 5, "CT", "腹部", "abd_ct_ax", "腹部"),
    ("search", "MRI brain axial", 5, "MR", "头颅", "head_mr_ax", "头颅"),
    ("search", "mammography MLO", 4, "MG", "乳腺", "breast_mlo", "乳腺"),
    ("search", "thyroid ultrasound", 4, "US", "甲状腺", "us_local", "超声"),
]

LICENSE_OK = re.compile(
    r"^(cc0|cc-by-[234]\.0|cc-by-sa-[234]\.0|cc-by-[234]|cc-by-sa-[234]|"
    r"public-domain|public domain|pd|pd-.*|pd-us)$", re.I
)
PRIVACY_BAD = re.compile(
    r"(patient\s*name|name\s*:|姓名|患者姓名|id\s*[:：]\s*\d|mrn|"
    r"hospital\s*number|身份证|出生日期)", re.I
)
LATERAL = re.compile(r"\b(lateral|side|oblique)\b|侧位|斜位", re.I)


def api(params, tries=5):
    params.update({"action": "query", "format": "json"})
    url = API + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(2.5 * (attempt + 1))
    raise last


def clean(s):
    return re.sub(r"<[^>]+>", " ", str(s or "")).replace("&amp;", "&").strip()


def members(kind, target):
    if kind == "cat":
        d = api({
            "list": "categorymembers",
            "cmtitle": "Category:" + target,
            "cmtype": "file",
            "cmlimit": "50",
        })
        return [x["title"] for x in d.get("query", {}).get("categorymembers", [])]
    d = api({
        "list": "search",
        "srsearch": target,
        "srnamespace": "6",
        "srlimit": "30",
    })
    return [x["title"] for x in d.get("query", {}).get("search", [])]


def infos(titles):
    out = []
    for i in range(0, len(titles), 40):
        d = api({
            "prop": "imageinfo",
            "titles": "|".join(titles[i:i + 40]),
            "iiprop": "url|size|mime|extmetadata",
            "iiextmetadatafilter": "LicenseShortName|License|Artist|ImageDescription",
            "iiurlwidth": "1000",
        })
        for p in d.get("query", {}).get("pages", {}).values():
            if "imageinfo" not in p:
                continue
            ii = p["imageinfo"][0]
            em = ii.get("extmetadata", {})
            get = lambda k: clean(em.get(k, {}).get("value", ""))
            out.append({
                "title": p["title"],
                "page": "https://commons.wikimedia.org/wiki/" +
                        urllib.parse.quote(p["title"].replace(" ", "_")),
                "mime": ii.get("mime", ""),
                "width": ii.get("width", 0),
                "height": ii.get("height", 0),
                "bytes": ii.get("size", 0),
                "thumb": ii.get("thumburl", ""),
                "original": ii.get("url", ""),
                "license_short": get("LicenseShortName"),
                "license_code": get("License"),
                "artist": get("Artist")[:120],
                "description": get("ImageDescription")[:500],
            })
        time.sleep(1.5)
    return out


def main():
    manifest = json.loads(MAN.read_text(encoding="utf8")) if MAN.exists() else []
    have = {m["title"] for m in manifest}
    need = TARGET - len(manifest)
    print(f"已有 {len(manifest)} 张，还需 {need} 张")

    for kind, target, quota, mod, part, pose, chapter in SPEC:
        if need <= 0:
            break
        try:
            titles = members(kind, target)
        except Exception as e:
            print(f"[skip] {target}: {e}", file=sys.stderr)
            continue
        titles = [t for t in titles if t not in have]
        if not titles:
            print(f"[empty] {target}")
            continue
        try:
            rows = infos(titles)
        except Exception as e:
            print(f"[info-fail] {target}: {e}", file=sys.stderr)
            continue

        kept = 0
        for it in rows:
            if kept >= min(quota, need):
                break
            if it["mime"] not in ("image/jpeg", "image/png"):
                continue
            if it["width"] < 700 or it["bytes"] > 8_000_000:
                continue
            lic = (it["license_short"] or "").lower().replace(" ", "-")
            code = (it["license_code"] or "").lower()
            if not (LICENSE_OK.match(lic) or LICENSE_OK.match(code)):
                continue
            privacy = bool(PRIVACY_BAD.search(it["description"] or it["title"]))
            p = pose
            if pose.startswith("chest") and LATERAL.search(it["title"] + " " + it["description"]):
                p = "chest_lat"
            it.update({
                "category": target, "modality": mod, "body_part": part,
                "pose_class": p, "chapter": chapter,
                "privacy_flag": privacy,
                "license_ok": True,
            })
            have.add(it["title"])
            manifest.append(it)
            kept += 1
            need -= 1
        print(f"{target}: +{kept}  (total {len(manifest)})")
        time.sleep(2.0)

    # 下载
    for pos, it in enumerate(manifest):
        idx = START_CASE + pos
        if it.get("file"):
            continue
        ext = ".png" if it["mime"] == "image/png" else ".jpg"
        name = f"case-{idx:03d}{ext}"
        out = IMG / name
        try:
            req = urllib.request.Request(it["thumb"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                out.write_bytes(r.read())
            it["file"] = name
            print(f"saved {name}  {it['title'][:58]}")
        except Exception as e:
            print(f"download fail {name}: {e}", file=sys.stderr)
            it["file"] = ""
        time.sleep(0.4)

    MAN.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    ok = [m for m in manifest if m.get("file")]
    print(f"\n清单 {len(manifest)} 条，已下载 {len(ok)} 张")
    print("case 编号:", START_CASE, "-", START_CASE + len(manifest) - 1)


if __name__ == "__main__":
    main()
