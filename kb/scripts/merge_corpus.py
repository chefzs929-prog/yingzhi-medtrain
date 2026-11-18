#!/usr/bin/env python3
"""把三处候选清单合并成 120 例语料的影像底座。

来源：
  kb/_candidates/corpus_manifest.json   本次采集（部分因 429 未下载）
  kb/_candidates2/manifest.json         上一轮已核验候选（50 张图）
  kb/_candidates/manifest.json          首轮候选（19 张图）

规则：
1. 只保留有本地文件、且标题/描述含医学线索的条目；
2. 与 cases.jsonl 已引用的 source_page 去重；
3. 按部位均衡选 88 张，统一重命名为 case-033..120；
4. 输出 kb/_candidates/corpus_final.json，供 build_corpus_120.py 使用。

重新合并：python3 kb/scripts/merge_corpus.py
"""
import json
import re
import shutil
import urllib.parse
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
CAND = KB / "_candidates"
CAND2 = KB / "_candidates2"
IMG = KB / "images"
OUT = CAND / "corpus_final.json"
START = 33
TOTAL = 88

MED = re.compile(
    r"(x-ray|radiograph|roentgen|röntgen|chest|thorax|lung|pneumon|knee|patell|"
    r"hand|finger|metacarp|foot|feet|toe|tarsal|ankle|malleol|shoulder|glenoid|"
    r"humer|elbow|wrist|carpal|cervical|spine|vertebra|lumbar|pelvi|hip|femur|"
    r"tibia|fibula|skull|head|ct\b|computed tomography|mri|magnetic resonance|"
    r"mammogra|breast|ultrasound|sonograph|thyroid|abdomen|abdominal|brain|bone|"
    r"fraktur|fracture| tuberculosis|pneumonia)", re.I
)
BAD = re.compile(
    r"(self portrait|portrait of|palace|album|1911 test|illustrated|derivative of|"
    r"logo|icon|drawing|diagram|scheme|chart|graph\b)", re.I
)

# 部位推断：(正则, body_part, pose_class, chapter, level)
RULES = [
    (r"(ct|computed tomography).*(lung|chest|thorax|pulmonary)", "胸部", "chest_ct_ax", "胸部", "local"),
    (r"(mammogra|breast|mlo|dmmg)", "乳腺", "breast_mlo", "乳腺", "local"),
    (r"(thyroid|sonograph|ultrasound)", "甲状腺", "us_local", "超声", "local"),
    (r"(\bmri\b|magnetic resonance|flair|dwi|t1 axial|t2 axial)", "头颅", "head_mr_ax", "头颅", "local"),
    (r"(\bct\b|computed tomography)", "腹部", "abd_ct_ax", "腹部", "local"),
    (r"(knee|patell)", "膝关节", "knee_ap", "四肢", "global"),
    (r"(hand|finger|metacarp|thumb)", "手", "hand_pa", "四肢", "global"),
    (r"(foot|feet|toe|tarsal|metatars)", "足", "foot_ap", "四肢", "global"),
    (r"(ankle|malleol)", "踝", "ankle_ap", "四肢", "global"),
    (r"(shoulder|glenoid|humer)", "肩", "shoulder_ap", "四肢", "global"),
    (r"(elbow|olecranon)", "肘", "elbow_ap", "四肢", "global"),
    (r"(wrist|carpal)", "腕", "wrist_pa", "四肢", "global"),
    (r"(cervical)", "颈椎", "cspine_lat", "脊柱", "global"),
    (r"(lumbar|spine|vertebra)", "腰椎", "lspine_lat", "脊柱", "global"),
    (r"(pelvi|hip|femur)", "骨盆", "pelvis_ap", "四肢", "global"),
    (r"(skull|head)", "头颅", "skull_lat", "头颅", "global"),
    (r"(chest|thorax|lung|pneumon|radiograph|x-ray|röntgen|roentgen)", "胸部", "chest_pa", "胸部", "global"),
]

# 各部位目标数量，合计 88
QUOTA = {
    "胸部": 20, "膝关节": 6, "手": 6, "足": 6, "踝": 4, "肩": 4, "肘": 4,
    "腕": 4, "颈椎": 5, "腰椎": 5, "骨盆": 3, "头颅": 6, "腹部": 5,
    "乳腺": 3, "甲状腺": 3,
}
# 补足阶段的上限，避免局部模态（CT/MR/乳腺/超声）挤占四肢与脊柱
CAP = {p: q + (2 if p in ("腹部", "乳腺", "甲状腺", "头颅") else 3) for p, q in QUOTA.items()}


def title_of(page):
    if not page:
        return ""
    tail = page.split("/wiki/")[-1]
    return "File:" + urllib.parse.unquote(tail).replace("_", " ")


def infer(text):
    for pat, part, pose, chapter, level in RULES:
        if re.search(pat, text, re.I):
            return part, pose, chapter, level
    return "胸部", "chest_pa", "胸部", "global"


def load(path, base):
    p = Path(path)
    if not p.exists():
        return []
    rows = json.loads(p.read_text(encoding="utf8"))
    out = []
    for r in rows:
        f = r.get("file") or ""
        if not f:
            continue
        src = base / f
        if not src.exists():
            continue
        out.append({**r, "_src": str(src)})
    return out


def main():
    used_pages = set()
    for line in (KB / "data" / "cases.jsonl").read_text(encoding="utf8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        t = title_of(c.get("source_page", ""))
        if t:
            used_pages.add(t)

    pool = []
    for rows in (load(CAND / "corpus_manifest.json", IMG),
                 load(CAND2 / "manifest.json", CAND2),
                 load(CAND / "manifest.json", CAND),
                 load(CAND / "limbs_manifest.json", CAND / "limbs"),
                 load(CAND / "spine_manifest.json", CAND / "spine")):
        pool.extend(rows)

    seen_title, seen_src, clean = set(), set(), []
    for r in pool:
        title = r.get("title") or ""
        if not title or title in seen_title or title in used_pages:
            continue
        text = title + " " + (r.get("description") or "")
        if BAD.search(text) or not MED.search(text):
            continue
        if r["_src"] in seen_src:
            continue
        if (r.get("width") or 0) < 500:
            continue
        seen_title.add(title)
        seen_src.add(r["_src"])
        part, pose, chapter, level = infer(text)
        # 侧位/斜位投照不能套正位解剖模板：胸部走侧位模板，四肢走图像内分区
        if re.search(r"(by\s+lateral\s+projection|lateral\s+(chest|radiograph|x-ray|view|projection)|oblique\s+projection|侧位|斜位)", text, re.I):
            if part == "胸部":
                pose = "chest_lat"
            elif part in ("膝关节", "手", "足", "踝", "肩", "肘", "腕", "骨盆"):
                pose, level = "limb_local", "local"
        clean.append({**r, "body_part": part, "pose_class": pose,
                      "chapter": chapter, "level": level})

    # 按部位配额选取，不足的部位由其它部位补足
    by_part = {}
    for r in clean:
        by_part.setdefault(r["body_part"], []).append(r)

    chosen = []
    for part, q in QUOTA.items():
        chosen.extend(by_part.get(part, [])[:q])
    if len(chosen) < TOTAL:
        idx = {p: QUOTA.get(p, 0) for p in by_part}
        while len(chosen) < TOTAL:
            progressed = False
            for p, rows in by_part.items():
                i = idx.get(p, 0)
                if i < len(rows) and i < CAP.get(p, 0) and len(chosen) < TOTAL:
                    chosen.append(rows[i])
                    idx[p] = i + 1
                    progressed = True
            if not progressed:
                break
    if len(chosen) < TOTAL:
        idx2 = {p: len(by_part.get(p, [])) for p in by_part}
        cursor = {p: sum(1 for r in chosen if r["body_part"] == p) for p in by_part}
        while len(chosen) < TOTAL:
            progressed = False
            for p, rows in by_part.items():
                i = cursor.get(p, 0)
                if i < len(rows) and len(chosen) < TOTAL:
                    chosen.append(rows[i])
                    cursor[p] = i + 1
                    progressed = True
            if not progressed:
                break
    chosen = chosen[:TOTAL]

    # 重命名
    final = []
    for i, r in enumerate(chosen):
        cid = f"CASE-{START + i:03d}"
        ext = ".png" if (r.get("mime") == "image/png") else ".jpg"
        dst = IMG / f"case-{START + i:03d}{ext}"
        if Path(r["_src"]).resolve() != dst.resolve():
            shutil.copyfile(r["_src"], dst)
        final.append({
            "case_id": cid,
            "file": dst.name,
            "title": (r.get("title") or "").replace("File:", "").rsplit(".", 1)[0],
            "source_page": r.get("page") or "",
            "license": r.get("license_short") or "",
            "license_code": r.get("license_code") or "",
            "artist": r.get("artist") or "",
            "width": r.get("width") or 0,
            "height": r.get("height") or 0,
            "description": (r.get("description") or "")[:300],
            "body_part": r["body_part"],
            "pose_class": r["pose_class"],
            "chapter": r["chapter"],
            "level": r["level"],
            "privacy_flag": bool(r.get("privacy_flag")),
        })

    OUT.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf8")
    from collections import Counter
    print(f"候选池 {len(clean)} 条，选中 {len(final)} 张")
    print(Counter(x["body_part"] for x in final))
    print(Counter(x["level"] for x in final))
    print(f"输出 {OUT.relative_to(KB)}")


if __name__ == "__main__":
    main()
