#!/usr/bin/env python3
"""修正区域结论的“接地”错误，并给区域框加影像有效性审计。

背景（2026-11-20 用户实测）：
  1) CASE-238「腺体实质」的分区框落在图像全黑区（97% 像素接近纯黑），
     库内却给出「未见明显异常」——把“没看到”当成了“正常”。
  2) CASE-013 等病例的分区文本是「未见明显异常」，同一条结论却挂着
     ACR BI-RADS 4「可疑恶性，考虑组织学评估」的条款，两者直接矛盾。

本脚本只做两件事，不新增任何临床结论：
  A. 像素审计：分区框内 p95 亮度 < 45 或 >90% 像素接近纯黑 → 该分区标记
     status="invalid_image_area"，删除其结论，前端据此拒答。
  B. 文本接地：非正常病例的分区文本若写成「未见明显异常」，改为
     「本分区未逐区标注 + 病例级公开描述」，清空分区级征象与指南条款，
     不再把病例级结论冒充成分区结论。

用法：
  python3 kb/scripts/fix_region_grounding.py            # 就地修复
  python3 kb/scripts/fix_region_grounding.py --check    # 只报告，不写文件
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb" / "data"
IMAGES = ROOT / "kb" / "images"

NEGATIVE_MARKERS = ("未见明显异常", "未见异常", "无异常", "作为正常对照")
MALIGNANT_MARKERS = ("可疑恶性", "恶性", "BI-RADS 4", "BI-RADS 5", "组织学评估",
                     "穿刺", "活检", "TR4", "TR5", "LR-4", "LR-5")

DARK_P95 = 45.0
DARK_FRAC = 0.90


def load(name):
    path = DATA / f"{name}.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf8").splitlines() if x.strip()]


def save(name, rows):
    (DATA / f"{name}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf8")


def is_normal_case(case):
    title = case.get("title", "")
    return "正常" in title or "对照" in title


def pixel_stats(image_path, bbox):
    """返回 bbox 内的亮度分位数与近黑像素占比；缺图或缺 Pillow 时返回 None。"""
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None
    if not image_path.exists():
        return None
    with Image.open(image_path) as im:
        gray = im.convert("L")
        w, h = gray.size
        x0, y0, x1, y1 = bbox
        px0, py0 = int(round(x0 * w)), int(round(y0 * h))
        px1, py1 = int(round(x1 * w)), int(round(y1 * h))
        px0, py0 = max(0, min(px0, w - 2)), max(0, min(py0, h - 2))
        px1, py1 = max(px0 + 2, min(px1, w)), max(py0 + 2, min(py1, h))
        crop = gray.crop((px0, py0, px1, py1))
    hist = crop.histogram()
    total = sum(hist) or 1
    mean = sum(i * n for i, n in enumerate(hist)) / total
    acc, p95 = 0, 255
    for i, n in enumerate(hist):
        acc += n
        if acc / total >= 0.95:
            p95 = i
            break
    dark_frac = sum(hist[:20]) / total
    return {"mean": round(mean, 1), "p95": p95, "dark_frac": round(dark_frac, 2)}


def text_is_negative(text):
    return any(m in text for m in NEGATIVE_MARKERS)


def region_name_of(claim, regions):
    for r in regions:
        if r["id"] == claim.get("region_id"):
            return r["name"]
    return "该分区"


def doc_is_malignant(cite):
    anchor = cite.get("anchor") or {}
    blob = " ".join(str(anchor.get(k, "")) for k in ("doc_title", "locator", "excerpt"))
    return any(m in blob for m in MALIGNANT_MARKERS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只报告，不写文件")
    args = ap.parse_args()

    cases = {c["id"]: c for c in load("cases")}
    regions = load("regions")
    claims = load("claims")

    invalid_regions = {}
    for r in regions:
        case = cases.get(r.get("image_id"))
        if not case:
            continue
        stats = pixel_stats(IMAGES / Path(case["image"]).name, r.get("coords") or [])
        if not stats:
            continue
        if stats["p95"] < DARK_P95 or stats["dark_frac"] > DARK_FRAC:
            invalid_regions[r["id"]] = stats
            r["status"] = "invalid_image_area"
            r["pixel_stats"] = stats
        elif r.get("status") == "invalid_image_area":
            # 换图或重标后恢复
            r["status"] = "active"
            r.pop("pixel_stats", None)

    dropped_claims = [c for c in claims if c["region_id"] in invalid_regions]
    claims = [c for c in claims if c["region_id"] not in invalid_regions]

    rewritten, stripped_docs, dropped_signs = 0, 0, 0
    for c in claims:
        case = cases.get(c["image_id"])
        if not case or is_normal_case(case):
            # 正常病例的「未见明显异常」是正确表述，只需拦掉恶性条款
            if text_is_negative(c["text"]):
                docs = [x for x in c.get("cites", []) if x.get("kind") == "doc"]
                if any(doc_is_malignant(x) for x in docs):
                    c["cites"] = [x for x in c["cites"]
                                  if not (x.get("kind") == "doc" and doc_is_malignant(x))]
                    c["guideline_ids"] = []
                    c["dual_status"] = "imaging_only"
                    stripped_docs += 1
            continue

        if not text_is_negative(c["text"]):
            continue

        desc = (case.get("description_public") or "").strip()
        c["text"] = (f"{case['title']} · {region_name_of(c, regions)}：本分区未逐区标注（该病例非正常对照），"
                     "不单独给出阴性或阳性结论。")
        c["case_description"] = desc
        c["scope"] = "case"
        c["sign_ids"] = []
        c["guideline_ids"] = []
        c["related_guideline_ids"] = []
        before = len(c.get("cites", []))
        c["cites"] = [x for x in c.get("cites", []) if x.get("kind") != "doc"]
        stripped_docs += before - len(c["cites"])
        c["dual_status"] = "imaging_only"
        c.setdefault("derivation", {})["region_scope"] = "case_level"
        c["derivation"]["grounding_fix"] = "no_negative_default"
        rewritten += 1
        dropped_signs += 1

    report = {
        "generated_at": "2026-11-20",
        "invalid_regions": {k: v for k, v in invalid_regions.items()},
        "claims_dropped_for_black_region": len(dropped_claims),
        "claims_rewritten_case_level": rewritten,
        "doc_cites_removed": stripped_docs,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.check:
        print("· --check：未写入文件")
        return
    save("regions", regions)
    save("claims", claims)
    (DATA / "grounding_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print("· 已写入 regions.jsonl / claims.jsonl / grounding_audit.json")


if __name__ == "__main__":
    main()
