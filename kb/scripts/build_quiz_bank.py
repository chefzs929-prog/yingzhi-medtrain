#!/usr/bin/env python3
"""从标注数据生成可组卷题库。

题库不是"背名词"，每道题都带影像与框选坐标：
学生看到一张胸片上的高亮框，判断它属于哪个分区——这才是读片训练。

题型：
  locate     图上高亮一个分区框 → 选出分区名（干扰项取自同一张图的真实分区）
  sign       图上高亮分区 → 选出该区在库内关联的征象
  laterality 体位规则题（PA 胸片影像左侧对应患者哪侧）
  doc        给定结论文本 → 选出它引用的文献（训练可追溯性）

输出：kb/data/quiz_bank.json
"""
import json
import re
import random
import hashlib
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb" / "data"
OUT = DATA / "quiz_bank.json"


def read_jsonl(name):
    p = DATA / name
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def sha8(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


def box(coords):
    """[x,y,w,h] -> 四舍五入到 3 位，避免 JSON 里一长串浮点。"""
    return [round(float(v), 3) for v in coords]


def pick_options(rnd, right, pool, n=4):
    """right 必进选项，其余从 pool 去重抽取。"""
    others = [x for x in dict.fromkeys(pool) if x and x != right]
    rnd.shuffle(others)
    return [right] + others[: n - 1]


def main():
    cases = {c["id"]: c for c in read_jsonl("cases.jsonl") if c.get("status") == "active"}
    regions_all = read_jsonl("regions.jsonl")
    signs = {s["id"]: s for s in read_jsonl("signs.jsonl")}
    claims_all = read_jsonl("claims.jsonl")

    regions = [r for r in regions_all
               if r.get("image_id") in cases
               and r.get("status") == "active"
               and len(r.get("coords") or []) == 4]

    # 同一张图内的分区名（用作干扰项），以及同部位跨图的分区名（兜底）
    by_image = defaultdict(list)
    by_body = defaultdict(list)
    for r in regions:
        by_image[r["image_id"]].append(r)
        by_body[cases[r["image_id"]]["body_part"]].append(r)

    # 征象池按部位分组
    signs_by_body = defaultdict(list)
    for s in signs.values():
        bp = s.get("body_part") or ""
        signs_by_body[bp].append(s["name"])
        signs_by_body["*"].append(s["name"])

    bank = []

    # ---------- locate：图上框选 → 选分区 ----------
    for r in regions:
        case = cases[r["image_id"]]
        rnd = random.Random(int(sha8(r["id"]), 16))
        same = [x["name"] for x in by_image[r["image_id"]] if x["id"] != r["id"]]
        pool = same if len(same) >= 3 else same + [
            x["name"] for x in by_body[case["body_part"]] if x["id"] != r["id"]]
        if len(set(pool)) < 3:
            continue
        opts = pick_options(rnd, r["name"], pool)
        rnd.shuffle(opts)
        bank.append({
            "qid": "Q-LOC-" + r["id"],
            "type": "locate",
            "case_id": case["id"],
            "image": case["image"],
            "coords": box(r["coords"]),
            "chapter": case.get("chapter", ""),
            "body_part": case["body_part"],
            "modality": case["modality"],
            "pose_class": case.get("pose_class", ""),
            "region_id": r["id"],
            "prompt": "图中框选的区域属于哪个解剖分区？",
            "options": opts,
            "answer": r["name"],
            "explain": "%s：%s（标注位置以库内 coords 为准，不代表诊断）"
                       % (r["name"], r.get("note", "")),
        })

    # ---------- sign：图上框选分区 → 选该区关联征象 ----------
    # 干扰项取"同一章节"的征象，保证在同一个教学单元内可混淆；
    # 不要用全库池，否则胸部题里会蹦出"胰腺钙化"这种一眼排除的选项。
    signs_by_chapter = defaultdict(list)
    for r in regions:
        ch = cases[r["image_id"]].get("chapter", "")
        for sid in r.get("sign_ids") or []:
            if sid in signs:
                signs_by_chapter[ch].append(signs[sid]["name"])

    for r in regions:
        ids = r.get("sign_ids") or []
        names = [signs[i]["name"] for i in ids if i in signs]
        if not names:
            continue
        case = cases[r["image_id"]]
        rnd = random.Random(int(sha8(r["id"] + "-sign"), 16))
        right = rnd.choice(names)
        pool = signs_by_chapter.get(case.get("chapter", "")) or signs_by_body["*"]
        opts = pick_options(rnd, right, pool)
        if len(opts) < 4:
            continue
        rnd.shuffle(opts)
        bank.append({
            "qid": "Q-SGN-" + r["id"],
            "type": "sign",
            "case_id": case["id"],
            "image": case["image"],
            "coords": box(r["coords"]),
            "chapter": case.get("chapter", ""),
            "body_part": case["body_part"],
            "modality": case["modality"],
            "pose_class": case.get("pose_class", ""),
            "region_id": r["id"],
            "prompt": "框选分区「%s」在库内关联的征象中，下列哪一项属于本区？" % r["name"],
            "options": opts,
            "answer": right,
            "explain": "以库内 signs.jsonl 的部位归属为准；本题不代表该例一定出现此征象，也不构成诊断。",
        })

    # ---------- laterality：体位规则 ----------
    # PA/AP 胸片：影像左侧 = 患者右侧。这是最经典的读片易错点。
    # 答案必须从 laterality_rule 字符串解析，不能靠 image_side/patient_side 猜：
    # 显式写 no_laterality_inference 的体位（四肢局部、超声）本来就不做左右推断，不出题。
    seen_rule = set()
    for r in regions:
        case = cases[r["image_id"]]
        rule = (r.get("laterality_rule") or "").strip()
        if not rule or rule in seen_rule:
            continue
        if "no_laterality_inference" in rule:
            continue
        m = re.search(r"image_left\s*=\s*patient_(right|left)", rule)
        if not m:
            continue
        seen_rule.add(rule)
        side = m.group(1)
        pose = case.get("pose_class") or "PA"
        bank.append({
            "qid": "Q-LAT-" + sha8(rule),
            "type": "laterality",
            "case_id": case["id"],
            "image": case["image"],
            "coords": None,
            "chapter": case.get("chapter", ""),
            "body_part": case["body_part"],
            "modality": case["modality"],
            "pose_class": pose,
            "region_id": r["id"],
            "prompt": "%s 体位的%s影像上，画面左侧显示的是患者的哪一侧？" % (pose, case["body_part"]),
            "options": ["患者右侧", "患者左侧"],
            "answer": "患者右侧" if side == "right" else "患者左侧",
            "explain": "规则：%s。阅片时先确认体位，再判断左右，勿按画面方向直读。" % rule,
        })

    # ---------- doc：结论 → 引用文献 ----------
    # 关键：doc_kind 必须对齐。库里 guideline 的 title 是"ACR Lung-RADS"，
    # sign 的 title 是"胸腔积液"这类征象名。混在一个池里出题，等于把答案唯一化。
    docs_by_key = defaultdict(list)
    for c in claims_all:
        if c.get("image_id") not in cases:
            continue
        ch = cases[c["image_id"]].get("chapter", "")
        for ct in c.get("cites") or []:
            if ct.get("kind") == "doc":
                a = ct.get("anchor") or {}
                k, t = a.get("doc_kind"), a.get("doc_title")
                if k and t:
                    docs_by_key[(k, ch)].append(t)
                    docs_by_key[(k, "*")].append(t)
    for k in list(docs_by_key):
        docs_by_key[k] = list(dict.fromkeys(docs_by_key[k]))

    KIND_LABEL = {"guideline": "指南", "sign": "征象词条", "group": "影像组"}
    seen_doc = set()

    for c in claims_all:
        if c.get("image_id") not in cases:
            continue
        doc = None
        for ct in c.get("cites") or []:
            if ct.get("kind") == "doc":
                doc = ct.get("anchor") or {}
                break
        if not doc or not doc.get("doc_title"):
            continue
        case = cases[c["image_id"]]
        ch = case.get("chapter", "")
        kind = doc.get("doc_kind")
        # 同一份文献只出一题：否则 610 道题里几百道答案都是 ACR Lung-RADS，
        # 学生做两道就记住了，测不出溯源能力。
        key = (kind, doc["doc_title"])
        if key in seen_doc:
            continue
        pool = docs_by_key.get((kind, ch)) or []
        if len(set(pool)) < 4:
            pool = docs_by_key.get((kind, "*")) or []
        if len(set(pool)) < 4:
            continue
        seen_doc.add(key)
        rnd = random.Random(int(sha8(c["id"] + "-doc"), 16))
        opts = pick_options(rnd, doc["doc_title"], pool)
        rnd.shuffle(opts)
        text = c["text"]
        if len(text) > 46:
            text = text[:46] + "…"
        label = KIND_LABEL.get(kind, "文献")
        bank.append({
            "qid": "Q-DOC-" + c["id"],
            "type": "doc",
            "case_id": case["id"],
            "image": case["image"],
            "coords": None,
            "chapter": case.get("chapter", ""),
            "body_part": case["body_part"],
            "modality": case["modality"],
            "pose_class": case.get("pose_class", ""),
            "region_id": c.get("region_id"),
            "prompt": "结论「%s」引用的是哪份%s？" % (text, label),
            "options": opts,
            "answer": doc["doc_title"],
            "explain": "%s · %s · %s" % (doc.get("doc_title", ""), doc.get("version", ""),
                                         doc.get("locator", "")),
        })

    # 稳定排序，便于 diff
    bank.sort(key=lambda q: (q["type"], q["qid"]))

    payload = {
        "version": 1,
        "generated_from": {
            "cases": len(cases),
            "regions": len(regions),
            "claims": len(claims_all),
            "signs": len(signs),
        },
        "counts": {},
        "questions": bank,
    }
    for q in bank:
        payload["counts"][q["type"]] = payload["counts"].get(q["type"], 0) + 1

    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("题库已生成：%s" % OUT)
    print("  题目总数 %d" % len(bank))
    for k, v in sorted(payload["counts"].items()):
        print("    %-11s %d" % (k, v))
    print("  文件大小 %.1f KB" % (OUT.stat().st_size / 1024))
    print("  章节分布：")
    ch = defaultdict(int)
    for q in bank:
        ch[q["chapter"] or "未分类"] += 1
    for k, v in sorted(ch.items(), key=lambda x: -x[1]):
        print("    %-8s %d" % (k, v))


if __name__ == "__main__":
    main()
