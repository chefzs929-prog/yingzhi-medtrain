#!/usr/bin/env python3
"""把 kb/ 的知识资产编译成影知 App 的离线数据包。

输出：
  outputs/medtrain/data/kb.js      window.__KB__ = {...}（可 file:// 直接打开）
  outputs/medtrain/data/kb.json    同一份数据的 JSON，便于排查
  outputs/medtrain/images/*        压缩后的病例影像

只读取 kb/ 的已核验数据，不新增临床结论。
"""
import argparse
import os
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "kb"
DATA = Path(os.environ.get("KB_DATA") or (KB / "data"))

REGION_MAP = {
    "胸部": "REG-CHEST", "肺": "REG-CHEST", "胸": "REG-CHEST", "胸膜": "REG-CHEST",
    "纵隔": "REG-CHEST", "心": "REG-CHEST",
    "头颅": "REG-HEAD-NECK", "头颈": "REG-HEAD-NECK", "甲状腺": "REG-HEAD-NECK",
    "颈部": "REG-HEAD-NECK", "脑": "REG-HEAD-NECK",
    "乳腺": "REG-BREAST",
    "腹部": "REG-ABDOMEN", "肝": "REG-ABDOMEN", "胆": "REG-ABDOMEN",
    "胰": "REG-ABDOMEN", "肾": "REG-ABDOMEN", "脾": "REG-ABDOMEN",
    "肌骨": "REG-MSK", "脊柱": "REG-MSK", "手": "REG-MSK", "足": "REG-MSK",
    "膝关节": "REG-MSK", "膝": "REG-MSK", "肘": "REG-MSK", "腕": "REG-MSK",
    "肩": "REG-MSK", "骨盆": "REG-MSK", "四肢": "REG-MSK",
    # 脊柱各段原先落到 REG-CHEST，导致颈椎/腰椎病例被归到胸部
    "颈椎": "REG-MSK", "胸椎": "REG-MSK", "腰椎": "REG-MSK", "骶尾": "REG-MSK",
}
REGION_NAME = {
    "REG-CHEST": "胸部", "REG-HEAD-NECK": "头颈部", "REG-BREAST": "乳腺",
    "REG-ABDOMEN": "腹部", "REG-MSK": "肌骨与脊柱",
}


def load_jsonl(name):
    path = DATA / f"{name}.jsonl"
    if not path.exists():
        path = KB / "data" / f"{name}.jsonl"
    rows = []
    with path.open(encoding="utf8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def norm_modality(value):
    if isinstance(value, list):
        return [str(v).upper() for v in value if v]
    if not value:
        return []
    return [str(value).upper()]


def region_id(body):
    return REGION_MAP.get(str(body or ""), "REG-CHEST")


def short_hash(text):
    return hashlib.sha256((text or "").encode("utf8")).hexdigest()[:8]


def full_hash(text):
    return hashlib.sha256((text or "").encode("utf8")).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "outputs" / "medtrain"))
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--image-max", type=int, default=900)
    ap.add_argument("--image-quality", type=int, default=65)
    args = ap.parse_args()

    out = Path(args.out)
    (out / "data").mkdir(parents=True, exist_ok=True)
    img_out = out / "images"
    img_out.mkdir(parents=True, exist_ok=True)

    signs = load_jsonl("signs")
    guidelines = load_jsonl("guidelines")
    cases = [c for c in load_jsonl("cases") if str(c.get("status", "active")) != "inactive"]
    # 停用病例（非影像素材）不进入前端，也不保留其分区/结论，避免错配数据继续被检索。
    active_ids = {c["id"] for c in cases}
    regions = [r for r in load_jsonl("regions") if r.get("image_id") in active_ids]
    claims = [c for c in load_jsonl("claims") if c.get("image_id") in active_ids]
    groups = load_jsonl("groups")
    standards = load_jsonl("standards")
    links = load_jsonl("sign_links")
    def read_json(name):
        q = DATA / name
        if not q.exists():
            q = KB / "data" / name
        return json.loads(q.read_text(encoding="utf8"))

    taxonomy = read_json("taxonomy.json")
    sources_raw = read_json("sources.json")
    sources = {s["id"]: s for s in sources_raw.get("sources", [])}

    # ---------- 规范化 ----------
    sign_by_id = {}
    for s in signs:
        s["modality"] = norm_modality(s.get("modality"))
        s["region_id"] = region_id(s.get("body_part"))
        s["source_refs"] = [sources.get(x, {"id": x, "title": x}) for x in s.get("sources", [])]
        sign_by_id[s["id"]] = s

    for g in guidelines:
        g["modality"] = norm_modality(g.get("modality"))
        g["region_id"] = region_id(g.get("body_part"))

    for c in cases:
        # 病例库里 "CR" 是字符串，不规范化会被前端 join 成 "C/R"
        c["modality"] = norm_modality(c.get("modality"))
        c["region_id"] = region_id(c.get("body_part"))
        c["image"] = "images/" + Path(c["image"]).name
        c["sign_tags"] = list(c.get("sign_tags") or [])
        c["chapter"] = c.get("chapter") or REGION_NAME.get(c["region_id"], "其他")

    regions_by_case = defaultdict(list)
    for r in regions:
        regions_by_case[r["image_id"]].append(r)

    claims_by_case = defaultdict(list)
    for c in claims:
        for cite in c.get("cites", []):
            anchor = cite.get("anchor", {})
            if cite.get("kind") == "doc":
                excerpt = anchor.get("excerpt", "")
                expected = anchor.get("excerpt_sha256") or ""
                actual = full_hash(excerpt) if len(expected) == 64 else short_hash(excerpt)
                cite["hash_ok"] = bool(expected) and actual == expected
        kinds = {x.get("kind") for x in c.get("cites", [])}
        broken = any(x.get("kind") == "doc" and x.get("hash_ok") is False for x in c.get("cites", []))
        if broken:
            c["cite_status"] = "broken"
        elif {"spatial", "doc"} <= kinds:
            c["cite_status"] = "dual"
        elif kinds:
            c["cite_status"] = "single"
        else:
            c["cite_status"] = "none"
        claims_by_case[c["image_id"]].append(c)

    # ---------- 关联索引 ----------
    sign_cases = defaultdict(list)
    for c in cases:
        for sid in c["sign_tags"]:
            sign_cases[sid].append(c["id"])
    for r in regions:
        for sid in r.get("sign_ids") or []:
            if r["image_id"] not in sign_cases[sid]:
                sign_cases[sid].append(r["image_id"])

    sign_guidelines = defaultdict(list)
    for g in guidelines:
        for s in signs:
            if s["region_id"] == g["region_id"] and set(s["modality"]) & set(g["modality"]):
                sign_guidelines[s["id"]].append(g["id"])

    # 迁移数据：同标签/同部位/跨部位/跨模态
    transfer = {}
    for s in signs:
        tags = set(s.get("tags") or [])
        related = []
        for o in signs:
            if o["id"] == s["id"]:
                continue
            shared = tags & set(o.get("tags") or [])
            if shared:
                related.append((len(shared), o["id"], sorted(shared)))
        related.sort(key=lambda x: (-x[0], x[1]))
        related = related[:8]
        cross_part = []
        for o in signs:
            if o["id"] == s["id"]:
                continue
            if o["region_id"] != s["region_id"] and tags & set(o.get("tags") or []):
                cross_part.append(o["id"])
        cross_part = cross_part[:6]
        transfer[s["id"]] = {
            "related": [{"id": i, "shared": sh} for _, i, sh in related],
            "cross_part": cross_part,
            "cases": sign_cases[s["id"]][:8],
            "guidelines": sign_guidelines[s["id"]][:4],
        }

    # ---------- 演练题 ----------
    # 规则：优先选“有明确文字结论”的分区；否则选与病例标签重合最多的分区；
    # 再否则按部位挑一个解剖分区。题干只使用库内已有文字，不生成新结论。
    heuristics = {
        "REG-CHEST": ["右肺中野", "右肺下野", "图像中部", "图像中央"],
        "REG-HEAD-NECK": ["图像中央", "图像中部", "左侧", "图像前部"],
        "REG-BREAST": ["图像上部", "图像中央", "图像下部", "乳晕后区"],
        "REG-ABDOMEN": ["图像中央", "图像中部", "图像右侧", "图像左侧"],
        "REG-MSK": ["图像中央", "图像上部", "图像下部", "图像中部"],
    }

    def pick_region(case):
        rs = regions_by_case.get(case["id"], [])
        if not rs:
            return None, None
        rich = []
        for r in rs:
            for cl in claims_by_case.get(case["id"], []):
                if cl.get("region_id") != r["id"]:
                    continue
                if "区域解剖范围" in cl["text"]:
                    continue
                if any(x.get("kind") == "doc" and str(x.get("anchor", {}).get("doc_id", "")).startswith("SIGN")
                       for x in cl.get("cites", [])):
                    rich.append((r, cl))
        if rich:
            return rich[0]
        tags = set(case.get("sign_tags") or [])
        best = max(rs, key=lambda r: len(tags & set(r.get("sign_ids") or [])))
        if tags & set(best.get("sign_ids") or []):
            return best, next((cl for cl in claims_by_case.get(case["id"], []) if cl.get("region_id") == best["id"]), None)
        for key in heuristics.get(case["region_id"], []):
            for r in rs:
                if key in r.get("name", ""):
                    return r, next((cl for cl in claims_by_case.get(case["id"], []) if cl.get("region_id") == r["id"]), None)
        r = rs[0]
        return r, next((cl for cl in claims_by_case.get(case["id"], []) if cl.get("region_id") == r["id"]), None)

    def blank_region(text, region_name):
        if not text:
            return ""
        text = text.replace(region_name, "该分区")
        # “该分区区域解剖范围”读起来重复，收一下
        text = text.replace("该分区区域解剖范围", "该分区的解剖范围")
        return text

    drills = []
    rng = random.Random(20261115)

    # 只对“有来源征象标签”的病例，以及明确的正常/解剖对照病例出完整演练题。
    # 其余病例仍可在病例库中浏览，但不自动生成“看图下结论”的题目。
    normal_ids = {
        c["id"] for c in cases
        if not c.get("sign_tags") and (
            "NORMAL" in str(c.get("group_id", ""))
            or any(k in c["title"] for k in ("正常", "解剖", "示意"))
        )
    }
    drill_cases = [c for c in cases if c.get("sign_tags") or c["id"] in normal_ids]

    for case in drill_cases:
        region, claim = pick_region(case)
        if not region or not claim:
            continue
        has_tags = bool(case.get("sign_tags"))
        correct_signs = list(dict.fromkeys(case.get("sign_tags") or []))[:3] if has_tags else []
        primary = sign_by_id.get(correct_signs[0]) if correct_signs else None

        # 描述选项：有标签时用主征象定义；正常对照时用库内原文描述
        desc_pool = [s for s in signs if s["region_id"] == case["region_id"] and s["id"] not in correct_signs]
        rng.shuffle(desc_pool)
        if has_tags and primary:
            desc_options = [{"id": primary["id"], "text": primary["appearance"], "correct": True}]
        else:
            desc_options = [{"id": "NORMAL", "text": "正常解剖对照：未见明确局灶性密度增高、结节或肿块影。", "correct": True}]
        for s in desc_pool[:2]:
            desc_options.append({"id": s["id"], "text": s["appearance"], "correct": False})
        rng.shuffle(desc_options)

        # 征象选项：有标签时用来源标签；正常对照时“未见明确异常”为正确项
        sign_pool = [s for s in signs if s["region_id"] == case["region_id"] and s["id"] not in correct_signs]
        rng.shuffle(sign_pool)
        if has_tags:
            sign_options = [{"id": sid, "name": sign_by_id[sid]["name"], "correct": True} for sid in correct_signs]
            sign_prompt = "该病例的公开描述提示哪些征象？（多选）"
        else:
            sign_options = [{"id": "NORMAL", "name": "未见明确局灶性异常", "correct": True}]
            sign_prompt = "这张正常/解剖对照影像，最应得出的结论是？"
        for s in sign_pool[:2]:
            sign_options.append({"id": s["id"], "name": s["name"], "correct": False})
        rng.shuffle(sign_options)

        # 文献依据：优先用该分区文字结论里的真实文献锚点
        evidence = None
        for cite in claim.get("cites", []):
            if cite.get("kind") != "doc":
                continue
            anchor = cite.get("anchor", {})
            doc_id = str(anchor.get("doc_id", ""))
            if anchor.get("excerpt") and (doc_id in correct_signs or (not has_tags and doc_id.startswith("GL"))):
                evidence = {
                    "kind": "claim",
                    "docId": doc_id,
                    "title": anchor.get("doc_title") or sign_by_id.get(doc_id, {}).get("name", doc_id),
                    "locator": anchor.get("locator", ""),
                    "excerpt": anchor.get("excerpt", ""),
                    "url": anchor.get("url", ""),
                    "hashOk": cite.get("hash_ok", True),
                    "correct": True,
                }
                break
        if not evidence and primary:
            src = (primary.get("source_refs") or [{}])[0]
            evidence = {
                "kind": "sign",
                "docId": primary["id"],
                "title": src.get("title", "征象词条"),
                "locator": f"{primary['id']} / 影像表现",
                "excerpt": primary["appearance"],
                "url": src.get("url", ""),
                "hashOk": True,
                "correct": True,
            }
        if not evidence:
            evidence = {
                "kind": "case", "docId": claim["id"], "title": "病例公开来源",
                "locator": case["title"],
                "excerpt": case.get("teaching_note") or claim["text"],
                "url": case.get("source_page", ""), "hashOk": True, "correct": True,
            }
        ev_pool = [s for s in signs if s["id"] not in correct_signs and s["region_id"] == case["region_id"]]
        rng.shuffle(ev_pool)
        ev_options = [evidence]
        for s in ev_pool[:2]:
            src = (s.get("source_refs") or [{}])[0]
            ev_options.append({
                "kind": "sign",
                "docId": s["id"],
                "title": src.get("title", "征象词条"),
                "locator": f"{s['id']} / 影像表现",
                "excerpt": s["appearance"],
                "url": src.get("url", ""),
                "hashOk": True,
                "correct": False,
            })
        rng.shuffle(ev_options)

        guide = None
        guide_ids = sign_guidelines.get(primary["id"], []) if primary else []
        for cite in claim.get("cites", []):
            if cite.get("kind") == "doc" and str(cite.get("anchor", {}).get("doc_id", "")).startswith("GL"):
                guide_ids = [cite["anchor"]["doc_id"]] + guide_ids
                break
        if guide_ids:
            guide = next((g for g in guidelines if g["id"] == guide_ids[0]), None)

        drills.append({
            "id": "D-" + case["id"],
            # 主征象的易错点，答错时直接展示，把「错在哪」和「为什么」绑在同一题上
            "pitfalls": (primary.get("pitfalls") or []) if primary else [],
            "examType": "case",
            "caseId": case["id"],
            "title": case["title"],
            "mode": "finding" if has_tags else "normal",
            "modality": case["modality"],
            "bodyPart": case["body_part"],
            "regionId": case["region_id"],
            "image": case["image"],
            "level": case.get("level", "global"),
            "region": {
                "id": region["id"], "name": region["name"], "coords": region["coords"],
                "patientSide": region.get("patient_side", ""),
                "note": region.get("note", ""),
            },
            "stem": blank_region(claim["text"], region["name"]),
            "locateMode": "anatomy" if "区域解剖范围" in claim["text"] else "finding",
            "claimId": claim["id"],
            "claimText": claim["text"],
            "regionOptions": [
                {"id": r["id"], "name": r["name"], "coords": r["coords"]}
                for r in regions_by_case.get(case["id"], [])
            ],
            "descOptions": desc_options,
            "signOptions": sign_options,
            "signPrompt": sign_prompt,
            "correctSigns": correct_signs,
            "evOptions": ev_options,
            "guideline": ({
                "id": guide["id"], "standard": guide["standard_name"], "category": guide.get("category", ""),
                "statement": guide["statement"], "conditions": guide.get("conditions", []),
                "action": guide.get("action", ""), "version": guide.get("version_year"),
                "url": guide.get("source_url", ""),
            } if guide else None),
            "teachingNote": case.get("teaching_note", ""),
            "sourcePage": case.get("source_page", ""),
            "license": case.get("license", ""),
            "artist": case.get("artist", ""),
        })

    # ---------- 双线判断预置结果 ----------
    dual_presets = {}
    try:
        sys.path.insert(0, str(KB / "scripts"))
        from kbsearch import KB as KBEngine  # noqa: E402
        from dual import assess  # noqa: E402
        kb = KBEngine()
        queries = [
            "甲状腺结节 TR4 1.6cm", "肺实性结节 7mm", "磨玻璃影",
            "乳腺肿块 BI-RADS 4 伴毛刺", "肾囊肿 Bosniak IIF", "胸腔积液",
        ]
        for q in queries:
            r = assess(kb, q)
            dual_presets[q] = {
                "query": q,
                "signIds": [s["id"] for s in r.get("imaging", {}).get("signs", [])[:4]],
                "guidelineIds": [g["id"] for g in r.get("guidelines", [])[:4]],
                "alignment": r.get("alignment", {}),
                "disclaimer": r.get("disclaimer", ""),
            }
    except Exception as exc:  # 数据包仍可独立使用
        print("dual presets skipped:", exc, file=sys.stderr)

    # ---------- 考点题库 ----------
    # 题型参考国内影像学考试（执业医师 / 规培结业 / 放射职称）的常见考法：
    #   定义辨析（给描述选征象）、检查选择（给征象选模态）、易错辨析（选出属于该征象的易错点）。
    # 题目内容全部来自 kb/data/signs.jsonl 的 appearance / modality / pitfalls 原文，
    # 不生成知识库里没有的结论，也不声称是任何考试的真题。
    GENERIC_PIT = ("层厚", "窗宽", "窗位", "体位", "呼吸", "曝光", "伪影", "扫描", "重建")
    quiz = []
    by_part = defaultdict(list)
    for sg in signs:
        by_part[sg.get("body_part", "")].append(sg)

    def distractors(sign, n):
        """同部位优先，不足再从全库补；始终排除自身。"""
        out = [x for x in by_part.get(sign.get("body_part", ""), []) if x["id"] != sign["id"]]
        if len(out) < n:
            seen = {x["id"] for x in out} | {sign["id"]}
            out += [x for x in signs if x["id"] not in seen]
        return out[:n]

    def src_of(sign):
        refs = sign.get("source_refs") or []
        return refs[0] if refs else {}

    for sg in signs:
        sid, name = sg["id"], sg["name"]
        base = {
            "signId": sid,
            "signName": name,
            "regionId": sg.get("region_id", ""),
            "bodyPart": sg.get("body_part", ""),
            "source": src_of(sg).get("title", ""),
            "sourceUrl": src_of(sg).get("url", ""),
        }

        # 1) 定义辨析：给影像表现原文，选征象
        app = (sg.get("appearance") or "").strip()
        if app:
            ds = distractors(sg, 3)
            if len(ds) == 3:
                opts = [{"text": name, "correct": True}] + [{"text": d["name"], "correct": False} for d in ds]
                rng.shuffle(opts)
                quiz.append({
                    **base, "id": "Q-DEF-" + sid, "type": "define",
                    "typeName": "定义辨析", "multi": False,
                    "prompt": "下列影像表现描述的是哪个征象？",
                    "stem": app,
                    "options": opts,
                    "explain": f"{name}：{app}",
                    "pitfalls": sg.get("pitfalls") or [],
                })

        # 2) 检查选择：给征象，选知识库标注的模态（多选，避免组合选项把正确答案包含进去）
        mods = sg.get("modality") or []
        if mods:
            all_mods = []
            for o in signs:
                for m in (o.get("modality") or []):
                    if m not in all_mods:
                        all_mods.append(m)
            wrong = [m for m in all_mods if m not in mods]
            if len(wrong) >= 2:
                rng.shuffle(wrong)
                opts = [{"text": m, "correct": True} for m in mods[:3]]
                opts += [{"text": m, "correct": False} for m in wrong[:2]]
                rng.shuffle(opts)
                quiz.append({
                    **base, "id": "Q-MOD-" + sid, "type": "modality",
                    "typeName": "检查选择", "multi": True,
                    "prompt": f"「{name}」在知识库中标注的检查模态包括哪些？（多选）",
                    "stem": "",
                    "options": opts,
                    "explain": f"知识库标注 {name} 的模态为 {'/'.join(mods)}。",
                    "pitfalls": sg.get("pitfalls") or [],
                })

        # 3) 易错辨析：选出属于该征象的易错点
        own = [x for x in (sg.get("pitfalls") or []) if x and not any(g in x for g in GENERIC_PIT)]
        if own:
            others = []
            for o in signs:
                if o["id"] == sid or o.get("body_part") == sg.get("body_part"):
                    continue
                for x in (o.get("pitfalls") or []):
                    if x and not any(g in x for g in GENERIC_PIT) and name not in x:
                        others.append(x)
            rng.shuffle(others)
            if len(others) >= 2:
                opts = [{"text": x, "correct": True} for x in own[:2]]
                opts += [{"text": x, "correct": False} for x in others[:3]]
                rng.shuffle(opts)
                quiz.append({
                    **base, "id": "Q-PIT-" + sid, "type": "pitfall",
                    "typeName": "易错辨析", "multi": True,
                    "prompt": f"关于「{name}」，下列哪些属于它记录的易错点？（多选，按知识库标注）",
                    "stem": "",
                    "options": opts,
                    "explain": f"{name}的易错点：" + "；".join(own),
                    "pitfalls": sg.get("pitfalls") or [],
                })

    # ---------- 演示班级 ----------
    names = ["林嘉禾", "周予安", "陈知远", "许清和", "沈亦然", "顾南星", "宋听白", "叶青梧",
             "唐可心", "陆星野", "苏景行", "何见微", "罗予宁", "高云舒", "程一诺", "夏沐言",
             "蒋和光", "杜若川", "邵清越", "施雨眠", "傅思齐", "钟未晚", "袁既明", "崔知夏",
             "范疏桐", "彭观澜", "谢明川", "韩星洲", "曹予安", "石知微", "黎见山", "温言"]
    mock_class = []
    mrng = random.Random(42)
    for i, name in enumerate(names):
        mock_class.append({
            "id": f"STU-{i+1:02d}", "name": name,
            "learn": mrng.randint(45, 100), "transfer": mrng.randint(30, 96),
            "drill": mrng.randint(35, 98), "apply": mrng.randint(20, 92),
            "minutes": mrng.randint(35, 260), "last": mrng.choice(["今天", "昨天", "2 天前", "3 天前"]),
        })

    counts = {
        "signs": len(signs), "guidelines": len(guidelines), "standards": len(standards),
        "cases": len(cases), "regions": len(regions), "claims": len(claims),
        "links": len(links), "groups": len(groups), "drills": len(drills), "quiz": len(quiz),
        "dual": sum(1 for c in claims if c.get("cite_status") == "dual"),
        "broken": sum(1 for c in claims if c.get("cite_status") == "broken"),
    }

    payload = {
        "meta": {
            "name": "影知 · 影像临床思维平台",
            "version": "2.0.0",
            "builtAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "counts": counts,
            "regions": [{"id": k, "name": v} for k, v in REGION_NAME.items()],
            "disclaimer": "本平台仅用于医学影像教学与研究，不构成诊断意见，不替代临床决策。",
        },
        "taxonomy": taxonomy,
        "sources": sources,
        "signs": signs,
        "guidelines": guidelines,
        "standards": standards,
        "cases": cases,
        "regionsByCase": regions_by_case,
        "claimsByCase": claims_by_case,
        "groups": groups,
        "links": links,
        "transfer": transfer,
        "drills": drills,
        "quiz": quiz,
        "dualPresets": dual_presets,
        "mockClass": mock_class,
    }

    # ---------- 分片：cases 保留摘要，regions/claims 按部位拆包 ----------
    PART_OF = {"胸部": "chest", "肺": "chest", "胸": "chest", "胸膜": "chest", "纵隔": "chest",
               "头颅": "head", "甲状腺": "head", "头颈": "head", "脑": "head",
               "腹部": "abdomen", "肝": "abdomen", "胆囊": "abdomen", "胰": "abdomen",
               "肾": "abdomen", "骨盆": "abdomen", "乳腺": "breast"}
    def part_of(c):
        bp = c.get("body_part")
        m = c.get("modality")
        m = "/".join(m) if isinstance(m, list) else str(m or "")
        if bp in ("胸部", "肺", "胸", "胸膜", "纵隔"):
            return "chest_ct" if "CT" in m else "chest_cr"
        return PART_OF.get(bp, "msk")
    for c in cases:
        c["part"] = part_of(c)
    parts = {}
    for c in cases:
        d = parts.setdefault(c["part"], {"regionsByCase": {}, "claimsByCase": {}})
        if c["id"] in regions_by_case:
            d["regionsByCase"][c["id"]] = regions_by_case[c["id"]]
        if c["id"] in claims_by_case:
            d["claimsByCase"][c["id"]] = claims_by_case[c["id"]]
    payload.pop("regionsByCase", None)
    payload.pop("claimsByCase", None)
    payload["parts"] = {k: {"cases": len(v["regionsByCase"])} for k, v in parts.items()}

    js = "window.__KB__ = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (out / "data" / "kb.js").write_text(js, encoding="utf8")
    for old in (out / "data").glob("kb.part.*.js"):
        old.unlink()
    for k, v in parts.items():
        pj = ('window.__KB_PARTS__ = window.__KB_PARTS__ || {};'
              f'window.__KB_PARTS__["{k}"] = ' + json.dumps(v, ensure_ascii=False, separators=(",", ":")) + ";\n")
        (out / "data" / f"kb.part.{k}.js").write_text(pj, encoding="utf8")
    (out / "data" / "kb.json").write_text(json.dumps({**payload, "regionsByCase": regions_by_case,
                                                      "claimsByCase": claims_by_case}, ensure_ascii=False, indent=1), encoding="utf8")

    # 组卷题库：由 kb/scripts/build_quiz_bank.py 生成，静态站直接取用
    qb = KB / "data" / "quiz_bank.json"
    if qb.exists():
        shutil.copy2(qb, out / "data" / "quiz_bank.json")
        print("quiz_bank MB", round(qb.stat().st_size / 1e6, 2))

    # ---------- 影像压缩 ----------
    if not args.no_images:
        for case in cases:
            src = KB / case["image"].replace("images/", "images/", 1)
            if not src.exists():
                src = KB / "images" / Path(case["image"]).name
            if not src.exists():
                continue
            dst = img_out / src.name
            if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
                continue
            ext = src.suffix.lower()
            try:
                if ext == ".png":
                    subprocess.run(["sips", "-Z", str(args.image_max), str(src), "--out", str(dst)],
                                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.run(["sips", "-Z", str(args.image_max), "-s", "format", "jpeg",
                                    "-s", "formatOptions", str(args.image_quality), str(src), "--out", str(dst)],
                                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                shutil.copy2(src, dst)

    print("built", out)
    print(json.dumps(counts, ensure_ascii=False))
    print("kb.js MB", round((out / "data" / "kb.js").stat().st_size / 1e6, 2))


if __name__ == "__main__":
    main()
