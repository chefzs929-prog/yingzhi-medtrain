"""用成熟的胸片多标签模型做独立交叉检验（离线预生成）。

模型：torchxrayvision 的 DenseNet121，权重 densenet121-res224-all
（在多个公开胸片数据集上联合训练，18 类常见影像表现）。

注意：
- 这是整图级的多标签概率，不是分区级定位，也不是诊断
- 只用于和人工逐区标注做「是否互相打脸」的对比
- 侧位片与解剖标注图不参与主统计：模型训练以 PA/AP 为主，标注图不是诊断影像
- 必须在 .venv 下运行：.venv/bin/python kb/scripts/build_model_probe.py
- 没有 torch 环境时，可用 --recompute 只重算判定与汇总（不重新推理）

产物：kb/data/model_probe.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "kb/data/chest_reading.json"
CASES_META = ROOT / "kb/data/cases.jsonl"
IMG_ROOT = ROOT / "kb"
OUT = ROOT / "kb/data/model_probe.json"

WEIGHTS = "densenet121-res224-all"
TOP_K = 5

# 主判定阈值：0.5 会把大量正常片的弱信号（0.50~0.62）误判成「模型高分提示」。
# 0.6 是常用的弱校准阈值；同时输出 0.5/0.6/0.7/0.8 的敏感性，避免单点结论。
HIGH_THRESHOLD = 0.6
THRESHOLD_GRID = (0.5, 0.6, 0.7, 0.8)

# 不参与主统计的图像：侧位投照、解剖标注图。
EXCLUDE_POSE = {"chest_lat"}
EXCLUDE_TITLE_KEYWORDS = ("解剖标注",)

# 模型标签 -> 中文
LABEL_CN = {
    "Atelectasis": "肺不张",
    "Consolidation": "实变",
    "Infiltration": "浸润",
    "Pneumothorax": "气胸",
    "Edema": "肺水肿",
    "Emphysema": "肺气肿",
    "Fibrosis": "纤维化",
    "Effusion": "胸腔积液",
    "Pneumonia": "肺炎",
    "Pleural_Thickening": "胸膜增厚",
    "Cardiomegaly": "心影增大",
    "Nodule": "结节",
    "Mass": "肿块",
    "Hernia": "疝",
    "Lung Lesion": "肺部病灶",
    "Fracture": "骨折",
    "Lung Opacity": "肺野透亮度异常",
    "Enlarged Cardiomediastinum": "纵隔/心影增大",
}

# 模型标签 -> 可能对应的分区（用于和逐区标注比对）
LABEL_ZONES = {
    "Consolidation": {"RUL", "RML", "RLL", "LUL", "LML", "LLL"},
    "Infiltration": {"RUL", "RML", "RLL", "LUL", "LML", "LLL"},
    "Pneumonia": {"RUL", "RML", "RLL", "LUL", "LML", "LLL"},
    "Lung Opacity": {"RUL", "RML", "RLL", "LUL", "LML", "LLL"},
    "Atelectasis": {"RUL", "RML", "RLL", "LUL", "LML", "LLL"},
    "Nodule": {"RUL", "RML", "RLL", "LUL", "LML", "LLL"},
    "Mass": {"RUL", "RML", "RLL", "LUL", "LML", "LLL"},
    "Effusion": {"RLL", "LLL", "SUB"},
    "Pneumothorax": {"RUL", "RML", "RLL", "LUL", "LML", "LLL"},
    "Cardiomegaly": {"MED"},
    "Enlarged Cardiomediastinum": {"MED"},
    "Edema": {"RML", "RLL", "LML", "LLL"},
    "Fibrosis": {"RUL", "RLL", "LUL", "LLL"},
}


def load_model():
    import torchxrayvision as xrv

    model = xrv.models.DenseNet(weights=WEIGHTS)
    model.eval()
    return model, xrv


def infer(model, xrv, path: Path) -> dict:
    import numpy as np
    import torch
    from PIL import Image

    img = Image.open(path).convert("L")
    arr = np.asarray(img.resize((224, 224)), dtype=np.float32)
    arr = xrv.datasets.normalize(arr, 255)
    t = torch.from_numpy(arr[None, ...])
    with torch.no_grad():
        out = model(t)[0].numpy()
    labels = list(model.pathologies)
    pairs = sorted(zip(labels, out.tolist()), key=lambda x: x[1], reverse=True)
    return {k: float(v) for k, v in pairs}


def load_meta() -> dict[str, dict]:
    meta: dict[str, dict] = {}
    if not CASES_META.exists():
        return meta
    for line in CASES_META.read_text(encoding="utf8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        meta[row.get("id", "")] = {
            "pose_class": row.get("pose_class", ""),
            "title": row.get("title", ""),
        }
    return meta


def eligibility(case: dict) -> tuple[bool, str]:
    if case.get("pose_class") in EXCLUDE_POSE:
        return False, "侧位投照：模型训练以 PA/AP 为主，不纳入主统计"
    title = case.get("title") or ""
    if any(k in title for k in EXCLUDE_TITLE_KEYWORDS):
        return False, "解剖标注图：不是诊断影像，不纳入主统计"
    return True, ""


def judge(top: list[dict], abnormal_zones: set[str], threshold: float) -> tuple[bool, str, str]:
    all_normal = len(abnormal_zones) == 0
    high = [t for t in top if t["score"] >= threshold]
    top1 = top[0] if top else {"label": "", "score": 0.0}
    if high:
        if any(LABEL_ZONES.get(h["label"], set()) & abnormal_zones for h in high):
            return True, "consistent", "模型高分项与人工标注的异常分区指向同一类表现"
        if all_normal:
            return False, "conflict", f"模型最高分 {top1['score']:.3f} ≥ {threshold}，但该例人工标注为全部未见异常"
        return False, "partial", "模型有高分提示，但未命中人工标注的异常分区"
    if all_normal:
        return True, "consistent", f"模型最高分 {top1['score']:.3f} < {threshold}，与「全部未见异常」一致"
    return False, "silent", f"人工标注存在异常，但模型最高分 {top1['score']:.3f} < {threshold}（弱信号/漏检）"


def build_result(case: dict, top: list[dict], threshold: float) -> dict:
    abnormal_zones = {z["id"] for z in case.get("zones", []) if z.get("status") == "abnormal"}
    eligible, reason = eligibility(case)
    agree, verdict, note = judge(top, abnormal_zones, threshold)
    return {
        "case_id": case["id"],
        "title": case.get("title", ""),
        "pose_class": case.get("pose_class", ""),
        "eligible": eligible,
        "exclude_reason": reason,
        "abnormal_zones": sorted(abnormal_zones),
        "top": top,
        "verdict": verdict,
        "agreement": agree,
        "note": note,
    }


def summarize(results: list[dict], threshold: float) -> dict:
    eligible = [r for r in results if r["eligible"]]
    n = len(eligible)
    counts = {k: sum(1 for r in eligible if r["verdict"] == k) for k in ("consistent", "conflict", "partial", "silent")}
    strict = round(counts["consistent"] / n, 4) if n else 0
    weighted = round((counts["consistent"] + 0.5 * counts["partial"]) / n, 4) if n else 0

    grid = {}
    for th in THRESHOLD_GRID:
        rows = []
        for r in eligible:
            zones = set(r["abnormal_zones"])
            agree, verdict, _ = judge(r["top"], zones, th)
            rows.append(verdict)
        c = {k: rows.count(k) for k in ("consistent", "conflict", "partial", "silent")}
        grid[str(th)] = {
            "consistent": c["consistent"],
            "conflict": c["conflict"],
            "partial": c["partial"],
            "silent": c["silent"],
            "strict_rate": round(c["consistent"] / n, 4) if n else 0,
        }

    return {
        "cases": len(results),
        "eligible": n,
        "excluded": len(results) - n,
        "consistent": counts["consistent"],
        "conflict": counts["conflict"],
        "partial": counts["partial"],
        "silent": counts["silent"],
        "threshold": threshold,
        "strict_rate": strict,
        "weighted_rate": weighted,
        "thresholds": grid,
        "note": (
            "严格一致率只统计 eligible 病例（排除侧位投照与解剖标注图）；"
            "阈值敏感性见 thresholds，单点数字不应单独引用。"
        ),
    }


def write_out(results: list[dict], threshold: float, method: str, disclaimer: str) -> None:
    out = {
        "version": "0.2.0",
        "method": method,
        "disclaimer": disclaimer,
        "cases": results,
        "summary": summarize(results, threshold),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    print("\n写出", OUT)
    print("汇总", json.dumps(out["summary"], ensure_ascii=False))


def recompute(threshold: float) -> None:
    """只重算判定与汇总，不重新推理；用于没有 torch 的环境。"""
    if not OUT.exists():
        raise SystemExit("缺少 model_probe.json，无法 --recompute")
    old = json.loads(OUT.read_text(encoding="utf8"))
    meta = load_meta()
    chest = json.loads(SRC.read_text(encoding="utf8"))
    cases = {c["id"]: c for c in chest["cases"] if c.get("enabled") is not False}

    results = []
    for row in old.get("cases", []):
        case = cases.get(row.get("case_id"))
        if not case:
            continue
        case = dict(case)
        case.update(meta.get(row.get("case_id"), {}))
        results.append(build_result(case, row.get("top") or [], threshold))
    write_out(results, threshold, old.get("method", ""), old.get("disclaimer", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true", help="只重算判定，不加载模型")
    parser.add_argument("--threshold", type=float, default=HIGH_THRESHOLD)
    args = parser.parse_args()
    if args.recompute:
        recompute(args.threshold)
        return

    payload = json.loads(SRC.read_text(encoding="utf8"))
    cases = [c for c in payload["cases"] if c.get("enabled") is not False]
    meta = load_meta()

    print("加载模型…")
    model, xrv = load_model()

    results = []
    for i, case in enumerate(cases, 1):
        p = IMG_ROOT / case["image"]
        if not p.exists():
            print("  缺图", case["id"])
            continue
        try:
            probs = infer(model, xrv, p)
        except Exception as exc:  # noqa: BLE001
            print("  推理失败", case["id"], exc)
            continue

        top = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:TOP_K]
        top = [{"label": k, "label_cn": LABEL_CN.get(k, k), "score": round(v, 4)} for k, v in top]
        case = dict(case)
        case.update(meta.get(case["id"], {}))
        result = build_result(case, top, args.threshold)
        results.append(result)
        flag = "" if result["eligible"] else "（不纳入主统计）"
        print(f"  [{i:02d}] {case['id']} {result['verdict']} top={top[0]['label']} {top[0]['score']:.2f} {flag}")

    write_out(
        results,
        args.threshold,
        f"torchxrayvision DenseNet121 ({WEIGHTS})",
        (
            "整图级多标签概率，不是分区级定位，也不是诊断结论；"
            "模型在公开胸片数据上训练，对本库病例仅为独立交叉检验，未经医学审核。"
            "侧位投照与解剖标注图不纳入主统计。"
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
