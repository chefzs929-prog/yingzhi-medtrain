#!/usr/bin/env python3
"""生成第四态抽检包与双 AI 预标注队列。

定位：
  - 这不是“人工金标准”，而是两个独立视角的 AI 预标注：
      AI-A 报告视角：只读病例级公开描述，判断来源是否覆盖该分区；
      AI-B 结构化视角：只读 claim 的 sign_ids / zone.status / claim.text。
  - 两者一致只说明规则自洽；冲突条目优先送专家复核。
  - 专家复核入口在 read/qc.html，结论写入 localStorage，可导出 JSON。

输出：
  outputs/medtrain/data/audit/review_queue.json
  docs/第四态抽检_SOP.md
  docs/双AI预标注报告_2026-11-23.md
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb/data"
OUT_JSON = ROOT / "outputs/medtrain/data/audit/review_queue.json"
OUT_SOP = ROOT / "docs/第四态抽检_SOP.md"
OUT_MD = ROOT / "docs/双AI预标注报告_2026-11-23.md"

ZONE_WORDS = {
    "RUL": ["右肺上野", "右上肺", "右上肺野", "右肺尖", "右肺上叶", "右上叶", "right upper", "right apex"],
    "RML": ["右肺中野", "右中肺", "右中肺野", "右肺中叶", "右中叶", "right middle"],
    "RLL": ["右肺下野", "右下肺", "右下肺野", "右肺底", "右肺下叶", "右下叶", "right lower", "right base"],
    "LUL": ["左肺上野", "左上肺", "左上肺野", "左肺尖", "左肺上叶", "左上叶", "left upper", "left apex"],
    "LML": ["左肺中野", "左中肺", "左中肺野", "左肺舌段", "舌段", "left middle", "lingula"],
    "LLL": ["左肺下野", "左下肺", "左下肺野", "左肺底", "左肺下叶", "左下叶", "left lower", "left base"],
    "MED": ["纵隔", "心影", "心脏", "肺门", "纵隔旁", "mediastin", "cardiac silhouette", "heart shadow"],
    "SUB": ["膈下", "膈肌", "膈面", "subdiaphragmatic", "diaphragm"],
    "ANT": ["胸骨后", "前纵隔", "retrosternal", "anterior mediastin"],
    "MID": ["肺门", "中区", "肺门区", "hilum", "hilar"],
}
GENERIC = {
    "bilateral": ["双肺", "两肺", "双侧", "双肺野", "bilateral", "both lungs", "both sides", "diffuse"],
    "upper": ["上肺野", "上肺", "upper zone", "upper lung", "upper lobe"],
    "middle": ["中肺野", "中肺", "middle zone", "middle lung", "middle lobe"],
    "lower": ["下肺野", "下肺", "lower zone", "lower lung", "lower lobe"],
}
ABNORMAL_WORDS = [
    "密度增高", "斑片", "实变", "结节", "粟粒", "肿块", "占位", "空洞", "钙化",
    "积液", "气胸", "增厚", "增大", "模糊", "不张", "网格", "蜂窝", "支扩",
    "气腔影", "渗出", "水肿", "纤维化", "导管", "移位", "透亮", "变钝",
    "opacity", "infiltrat", "consolidat", "nodul", "miliary", "mass", "cavity",
    "calcif", "effusion", "pneumothorax", "thickening", "enlarg", "atelecta",
    "reticul", "honeycomb", "bronchiecta", "edema", "fibros", "catheter",
    "collapse", "blunting", "interstitial",
]
NORMAL_WORDS = ["正常", "未见", "清晰", "无异常", "阴性", "未见明显", "未见明确",
                "normal", "no abnormality", "clear", "unremarkable", "negative"]


def load() -> tuple[dict, list[dict]]:
    chest = json.loads((DATA / "chest_reading.json").read_text(encoding="utf8"))
    claims = [json.loads(l) for l in (DATA / "claims.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]
    return chest, claims


def has_any(text: str, words: list[str]) -> bool:
    t = (text or "").lower()
    return any(w.lower() in t for w in words)


def zone_covered(text: str, zone_id: str) -> tuple[bool, str]:
    """判断病例级描述是否覆盖该分区；返回 (covered, reason)。"""
    for w in ZONE_WORDS.get(zone_id, []):
        if w.lower() in text.lower():
            return True, f"出现分区词“{w}”"
    level = zone_id[1:] if len(zone_id) == 3 else ""
    # 先看层级词：出现“上肺野/下肺野”时，只覆盖对应层级，不让“双肺”扩大到全肺。
    has_level = has_any(text, GENERIC["upper"] + GENERIC["middle"] + GENERIC["lower"])
    if has_level:
        if level == "UL" and has_any(text, GENERIC["upper"]):
            return True, "出现“上肺野”泛化词"
        if level == "ML" and has_any(text, GENERIC["middle"]):
            return True, "出现“中肺野”泛化词"
        if level == "LL" and has_any(text, GENERIC["lower"]):
            return True, "出现“下肺野”泛化词"
        return False, "出现层级泛化词，但不覆盖该分区层级"
    if has_any(text, GENERIC["bilateral"]):
        if zone_id in {"RUL", "RML", "RLL", "LUL", "LML", "LLL"}:
            return True, "出现“双肺/双侧”泛化词，覆盖双侧肺野"
        if zone_id in {"MED", "SUB"}:
            return False, "“双肺/双侧”不覆盖纵隔/膈下"
    return False, "未出现该分区词或可覆盖的泛化词"


def ai_a(desc: str, zone_id: str, status: str) -> dict:
    """AI-A：报告视角。只读病例级公开描述。"""
    text = (desc or "").strip()
    if not text:
        return {"label": "uncertain", "supported": "uncertain", "reason": "病例级描述为空"}
    covered, why = zone_covered(text, zone_id)
    if not covered:
        if has_any(text, NORMAL_WORDS) and not has_any(text, ABNORMAL_WORDS):
            return {
                "label": "mentioned_normal",
                "supported": "supported" if status == "normal" else "not_supported",
                "reason": "病例级正常描述，覆盖全片",
            }
        return {
            "label": "not_mentioned",
            "supported": "supported" if status == "unmentioned" else "not_supported",
            "reason": f"{why}；按第四态规则判为“来源未逐区提及”",
        }
    abnormal = has_any(text, ABNORMAL_WORDS)
    normal = has_any(text, NORMAL_WORDS)
    if abnormal:
        return {
            "label": "mentioned_abnormal",
            "supported": "supported" if status == "abnormal" else "not_supported",
            "reason": f"{why}，且出现异常词",
        }
    if normal:
        return {
            "label": "mentioned_normal",
            "supported": "supported" if status == "normal" else "not_supported",
            "reason": f"{why}，且出现正常词",
        }
    return {
        "label": "mentioned_other",
        "supported": "uncertain",
        "reason": f"{why}，但无法从描述判断异常/正常",
    }


def ai_b(claim: dict, zone: dict) -> dict:
    """AI-B：结构化视角。只读 sign_ids / zone.status / claim.text。"""
    text = (claim.get("text") or "").strip()
    status = zone.get("status")
    signs = claim.get("sign_ids") or []
    if "未逐区" in text or "未提及" in text:
        return {
            "label": "not_mentioned",
            "supported": "supported" if status == "unmentioned" else "not_supported",
            "reason": "claim 文本明确写“未逐区标注/未提及”",
        }
    if not claim:
        # claim 缺失时回退到结构化状态；这属于数据缺口，报告中单列。
        fallback = {
            "abnormal": ("mentioned_abnormal", "supported"),
            "normal": ("mentioned_normal", "supported"),
            "unmentioned": ("not_mentioned", "supported"),
            "limited": ("uncertain", "uncertain"),
        }.get(status, ("uncertain", "uncertain"))
        return {
            "label": fallback[0],
            "supported": fallback[1],
            "reason": f"claim 缺失，回退到分区状态 {status}",
            "fallback": True,
        }
    if signs and status == "abnormal":
        return {
            "label": "mentioned_abnormal",
            "supported": "supported",
            "reason": f"有 {len(signs)} 个征象 id，且分区状态为 abnormal",
        }
    if not signs and status == "normal":
        return {
            "label": "mentioned_normal",
            "supported": "supported",
            "reason": "无征象 id，且分区状态为 normal",
        }
    if signs and status != "abnormal":
        return {
            "label": "mentioned_abnormal",
            "supported": "not_supported",
            "reason": "有征象 id，但分区状态不是 abnormal",
        }
    if not signs and status == "abnormal":
        return {
            "label": "mentioned_other",
            "supported": "not_supported",
            "reason": "分区为 abnormal，但 claim 没有征象 id",
        }
    if status == "limited":
        return {"label": "uncertain", "supported": "uncertain", "reason": "分区状态为 limited"}
    return {
        "label": "uncertain",
        "supported": "uncertain",
        "reason": f"结构化字段不足（status={status}, signs={len(signs)}）",
    }


def kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's kappa，二分类 supported / not_supported / uncertain 三分类。"""
    labels = ["supported", "not_supported", "uncertain"]
    n = len(pairs)
    if not n:
        return 0.0
    po = sum(1 for a, b in pairs if a == b) / n
    pe = 0.0
    for lab in labels:
        pa = sum(1 for a, _ in pairs if a == lab) / n
        pb = sum(1 for _, b in pairs if b == lab) / n
        pe += pa * pb
    return 0.0 if pe == 1 else round((po - pe) / (1 - pe), 4)


def main() -> None:
    chest, claims = load()
    cases = {c["id"]: c for c in chest["cases"]}
    claim_by = {(c["image_id"], c["region_id"]): c for c in claims}
    zones = []
    for c in chest["cases"]:
        for z in c.get("zones") or []:
            zones.append((c, z))

    rng = random.Random(20261123)

    # 1) 第四态抽检：58 条中按病例分层抽 20 条。
    unmentioned = [(c, z) for c, z in zones if z.get("status") == "unmentioned"]
    by_case = defaultdict(list)
    for c, z in unmentioned:
        by_case[c["id"]].append((c, z))
    case_ids = sorted(by_case)
    rng.shuffle(case_ids)
    picked = []
    for cid in case_ids:
        if len(picked) >= 20:
            break
        picked.append(rng.choice(by_case[cid]))
    for c, z in unmentioned:
        if len(picked) >= 20:
            break
        if (c, z) not in picked:
            picked.append((c, z))

    # 2) 双 AI 标注 30 例：abnormal / normal / unmentioned 各 10。
    strata = {"abnormal": [], "normal": [], "unmentioned": []}
    for c, z in zones:
        if z.get("status") in strata:
            strata[z["status"]].append((c, z))
    labeled = []
    for status, pool in strata.items():
        rng.shuffle(pool)
        labeled.extend(pool[:10])

    items = []
    for idx, (c, z) in enumerate(picked, 1):
        claim = claim_by.get((c["id"], f"REG-{c['id'].split('-')[-1]}-{z['id']}"))
        a = ai_a(c.get("description_public", ""), z["id"], z.get("status"))
        b = ai_b(claim or {}, z)
        items.append({
            "id": f"UM-{idx:02d}",
            "kind": "unmentioned",
            "case_id": c["id"],
            "case_title": c["title"],
            "zone_id": z["id"],
            "zone_name": z["name"],
            "status": z.get("status"),
            "claim_id": (claim or {}).get("id", ""),
            "claim_text": (claim or {}).get("text", ""),
            "description": c.get("description_public", ""),
            "ai_a": a,
            "ai_b": b,
            "agree": a["supported"] == b["supported"],
            "expert": {"status": "pending", "label": "", "reviewer": "", "note": "", "at": ""},
        })

    for idx, (c, z) in enumerate(labeled, 1):
        claim = claim_by.get((c["id"], f"REG-{c['id'].split('-')[-1]}-{z['id']}"))
        a = ai_a(c.get("description_public", ""), z["id"], z.get("status"))
        b = ai_b(claim or {}, z)
        items.append({
            "id": f"DL-{idx:02d}",
            "kind": "dual_label",
            "case_id": c["id"],
            "case_title": c["title"],
            "zone_id": z["id"],
            "zone_name": z["name"],
            "status": z.get("status"),
            "claim_id": (claim or {}).get("id", ""),
            "claim_text": (claim or {}).get("text", ""),
            "description": c.get("description_public", ""),
            "ai_a": a,
            "ai_b": b,
            "agree": a["supported"] == b["supported"],
            "expert": {"status": "pending", "label": "", "reviewer": "", "note": "", "at": ""},
        })

    un_items = [i for i in items if i["kind"] == "unmentioned"]
    dl_items = [i for i in items if i["kind"] == "dual_label"]
    dl_pairs = [(i["ai_a"]["supported"], i["ai_b"]["supported"]) for i in dl_items]
    um_pairs = [(i["ai_a"]["supported"], i["ai_b"]["supported"]) for i in un_items]

    claim_missing = sum(1 for i in items if not i["claim_text"])
    status_text_conflict = sum(
        1 for i in items
        if "未逐区" in (i["claim_text"] or "") and i["status"] in {"normal", "abnormal"}
    )
    status_signs_conflict = 0
    for i in items:
        claim = claim_by.get((i["case_id"], f"REG-{i['case_id'].split('-')[-1]}-{i['zone_id']}"))
        signs = (claim or {}).get("sign_ids") or []
        if (i["status"] == "unmentioned" and signs) or (i["status"] == "abnormal" and not signs):
            status_signs_conflict += 1

    def dist(rows: list[dict], key: str) -> dict:
        return dict(Counter(r["ai_a"][key] for r in rows))

    payload = {
        "generated_at": date.today().isoformat(),
        "policy": {
            "role": "AI 预标注，不是人工金标准；专家结论优先于 AI。",
            "ai_a": "报告视角：只读病例级公开描述，判断来源是否覆盖该分区。",
            "ai_b": "结构化视角：只读 claim.sign_ids / zone.status / claim.text。",
            "unmentioned_definition": "“来源未逐区提及”，不是“来源完全没提”；病例级泛化描述若覆盖该区，不算未提及。",
        },
        "summary": {
            "unmentioned_total": len(unmentioned),
            "unmentioned_sample": len(un_items),
            "dual_label_total": len(dl_items),
            "dual_agree": sum(1 for a, b in dl_pairs if a == b),
            "dual_kappa": kappa(dl_pairs),
            "unmentioned_agree": sum(1 for a, b in um_pairs if a == b),
            "unmentioned_kappa": kappa(um_pairs),
            "ai_a_distribution": dist(items, "label"),
            "conflicts": sum(1 for i in items if not i["agree"]),
            "claim_missing": claim_missing,
            "status_text_conflict": status_text_conflict,
            "status_signs_conflict": status_signs_conflict,
        },
        "items": items,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf8")

    # SOP
    sop = [
        "# 第四态抽检 SOP（AI 预标注 + 专家复核）",
        "",
        "> 适用对象：`unmentioned`（来源未逐区提及）分区。",
        "> 关键定义：**“未提及”指来源没有对该分区做逐区描述，不等于“来源完全没提这个病例”，也不等于“正常”。**",
        "",
        "## 一、判定步骤",
        "",
        "1. 打开该病例的来源页与病例级公开描述，确认没有逐区报告。",
        "2. 检查描述中是否出现该分区名（如“右肺上野”）。",
        "3. 检查是否出现可覆盖该区的泛化词：",
        "   - “双肺/两肺/双侧”覆盖双侧肺野，不覆盖纵隔/膈下；",
        "   - “上肺野/中肺野/下肺野”覆盖对应层级的双侧分区；",
        "   - “肺门”覆盖 MID，不覆盖 MED/SUB。",
        "4. 若出现分区词或泛化词，再看是否带异常词/正常词：",
        "   - 异常词：密度增高、结节、实变、积液、气胸、增厚、增大、模糊、不张、网格、蜂窝、支扩、钙化、空洞、斑片、粟粒等；",
        "   - 正常词：正常、未见、清晰、无异常、阴性。",
        "5. 只有“未出现分区词且未被泛化词覆盖”时，才判 `not_mentioned`。",
        "",
        "## 二、专家复核选项",
        "",
        "| 选项 | 含义 | 写入字段 |",
        "| --- | --- | --- |",
        "| 确认 AI 结论 | 同意 AI 的 supported / not_supported | `expert.label=agree` |",
        "| 改为来源已提及（异常） | 来源覆盖该区且有异常描述 | `expert.label=mentioned_abnormal` |",
        "| 改为来源已提及（正常） | 来源覆盖该区且描述正常 | `expert.label=mentioned_normal` |",
        "| 改为未提及 | 来源确实没有逐区描述 | `expert.label=not_mentioned` |",
        "| 存疑/需查原文 | 现有材料不足 | `expert.label=uncertain` |",
        "",
        "## 三、抽检口径",
        "",
        f"- 全库 `unmentioned` 共 **{len(unmentioned)}** 条；本次按病例分层抽 **{len(un_items)}** 条。",
        "- 抽样固定随机种子 `20261123`，可复现。",
        "- AI 一致率高只说明两个视角自洽，不代表真实金标准；冲突条目必须专家复核。",
        "",
        "## 四、复核入口",
        "",
        "- 页面：`outputs/medtrain/read/qc.html`",
        "- 数据：`outputs/medtrain/data/audit/review_queue.json`",
        "- 导出：页面右上角“导出复核结果 JSON”，可直接作为专家复核记录。",
        "",
    ]
    OUT_SOP.write_text("\n".join(sop), encoding="utf8")

    # 报告
    md = [
        "# 双 AI 预标注报告 · 2026-11-23",
        "",
        "> 这不是人工双人标注，而是**双 AI 预标注 + 专家复核入口**。AI 结论只用于筛冲突，不冒充金标准。",
        "",
        "## 一、结论",
        "",
        f"- 双 AI 标注：**{len(dl_items)}** 条（abnormal / normal / unmentioned 各 10）。",
        f"- 一致：**{payload['summary']['dual_agree']}/{len(dl_items)}**；Cohen's kappa = **{payload['summary']['dual_kappa']}**。",
        f"- 第四态抽检：**{len(un_items)}/{len(unmentioned)}**；一致 **{payload['summary']['unmentioned_agree']}/{len(un_items)}**；kappa = **{payload['summary']['unmentioned_kappa']}**。",
        f"- 全部冲突：**{payload['summary']['conflicts']}** 条，已进入专家复核队列。",
        "",
        "## 二、AI-A / AI-B 分布",
        "",
        "| 视角 | 判定分布 |",
        "| --- | --- |",
        f"| AI-A 报告视角 | `{json.dumps(payload['summary']['ai_a_distribution'], ensure_ascii=False)}` |",
        "| AI-B 结构化视角 | 见 `review_queue.json` 每条 `ai_b.label` |",
        "",
        "## 三、数据质量信号（比一致率更重要）",
        "",
        f"- claim 缺失：**{payload['summary']['claim_missing']}** 条（AI-B 回退到分区状态）。",
        f"- 状态与文本冲突：**{payload['summary']['status_text_conflict']}** 条（分区标为 normal/abnormal，但 claim 写“未逐区描述”）。",
        f"- 状态与征象冲突：**{payload['summary']['status_signs_conflict']}** 条（unmentioned 却有征象 id，或 abnormal 却无征象 id）。",
        "",
        "这三类不是 AI 规则问题，而是**数据本身需要专家裁决**的信号；应优先于“提高 kappa”处理。",
        "",
        "## 四、怎么读 kappa",
        "",
        "- kappa 高：两个视角对“来源是否支持当前状态”的判断一致，说明规则自洽、数据内部矛盾少。",
        "- kappa 低：说明报告粒度与结构化标注不一致，优先送专家；这比“刷高一致率”更有价值。",
        "- 无论高低，都不能写成“人工标注一致性”；准确写法是“双 AI 预标注一致性”。",
        "",
        "## 五、冲突样例（前 10 条）",
        "",
        "| id | 病例/分区 | 状态 | AI-A | AI-B | 来源描述 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    conflicts = [i for i in items if not i["agree"]][:10]
    if conflicts:
        for i in conflicts:
            desc = (i["description"] or "").replace("|", "｜")[:60]
            md.append(
                f"| {i['id']} | {i['case_id']}/{i['zone_id']} | {i['status']} | "
                f"{i['ai_a']['supported']} | {i['ai_b']['supported']} | {desc} |"
            )
    else:
        md.append("| — | 无冲突 | — | — | — | — |")

    md += [
        "",
        "## 六、专家复核入口",
        "",
        "1. 打开 `outputs/medtrain/read/qc.html`（或从课堂页头部“质控复核”进入）。",
        "2. 逐条查看来源描述、claim 文本、两个 AI 的判定与理由。",
        "3. 选择专家结论、填写备注；数据保存在本机浏览器。",
        "4. 点“导出复核结果 JSON”，作为专家复核记录归档。",
        "",
        "## 七、边界",
        "",
        "- AI-A 只看病例级描述，无法替代阅读原图；它判断的是“来源文本是否覆盖该区”，不是“影像上是否真的正常”。",
        "- AI-B 只看结构化字段，无法发现“字段与原文语义不符”的问题；这正是需要专家复核的原因。",
        "- 本报告不声称已完成人工双人标注；只声称已完成 AI 预标注并预留专家入口。",
        "",
    ]
    OUT_MD.write_text("\n".join(md), encoding="utf8")

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=1))
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"wrote {OUT_SOP.relative_to(ROOT)}")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
