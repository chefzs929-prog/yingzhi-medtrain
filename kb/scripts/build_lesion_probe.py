"""胸片逐区辅助分析（经典图像处理，不依赖深度学习）。

做的事：
1. 对侧对比：右肺上/中/下野 与 左肺上/中/下野 的密度差
2. 局部异质性：分区内标准差相对全图的比例
3. 合成一个 0-1 的「可疑度」分数，只作辅助提示

不做什么：
- 不做病灶检测与分割
- 不替代人工逐区标注
- 不声称是模型置信度

产物同时用于生成「争议档案」：算法提示与人工标注不一致的病例。

用法：
    python3 kb/scripts/build_lesion_probe.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "kb/data/chest_reading.json"
IMG_ROOT = ROOT / "kb"
OUT = ROOT / "kb/data/lesion_probe.json"
SITE_OUT = ROOT / "outputs/medtrain/data/chest/lesion_probe.json"

PAIRS = [("RUL", "LUL"), ("RML", "LML"), ("RLL", "LLL")]
PAIRED = {a for a, b in PAIRS} | {b for a, b in PAIRS}

METHOD = "symmetry_heterogeneity_v0.1"
DISCLAIMER = (
    "经典图像处理启发式（对侧密度差 + 分区异质性），"
    "不是深度学习模型，不是概率，未经医学审核；仅用于教学演示中的辅助提示。"
)


def load_gray(path: Path, max_side: int = 512) -> np.ndarray:
    im = Image.open(path).convert("L")
    w, h = im.size
    scale = max_side / max(w, h)
    if scale < 1:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    arr = np.asarray(im, dtype=np.float32)
    # 轻度平滑，压掉胶片颗粒与文字标注带来的高频噪声
    k = np.array([1, 2, 1], dtype=np.float32) / 4.0
    arr = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, arr)
    arr = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, arr)
    return arr


def zone_patch(arr: np.ndarray, coords) -> np.ndarray | None:
    """coords = [left, top, width, height]，比例单位。"""
    H, W = arr.shape
    l, t, w, h = coords
    x0, x1 = int(l * W), int((l + w) * W)
    y0, y1 = int(t * H), int((t + h) * H)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    # 内缩 15%，避开分区边界上的肋骨与纵隔轮廓
    dx = max(1, int((x1 - x0) * 0.15))
    dy = max(1, int((y1 - y0) * 0.15))
    return arr[y0 + dy : y1 - dy, x0 + dx : x1 - dx]


def analyze_case(case: dict) -> dict | None:
    img_path = IMG_ROOT / case["image"]
    if not img_path.exists():
        return None
    try:
        arr = load_gray(img_path)
    except Exception as exc:  # noqa: BLE001
        print("  读取失败", case["id"], exc)
        return None

    g_std = float(arr.std()) + 1e-6
    stats = {}
    for z in case["zones"]:
        patch = zone_patch(arr, z["coords"])
        if patch is None:
            continue
        stats[z["id"]] = {
            "mean": float(patch.mean()),
            "std": float(patch.std()),
            "hetero": float(patch.std() / g_std),
        }

    asym = {}
    for a, b in PAIRS:
        if a in stats and b in stats:
            ma, mb = stats[a]["mean"], stats[b]["mean"]
            diff = abs(ma - mb) / (ma + mb + 1e-6)
            asym[a] = asym[b] = diff

    zones = []
    for z in case["zones"]:
        zid = z["id"]
        if zid not in stats:
            continue
        s = stats[zid]
        a = asym.get(zid, 0.0)
        # 归一化：对侧差典型 0~0.30，异质性典型 0~2.0
        a_n = min(1.0, a / 0.30)
        h_n = min(1.0, s["hetero"] / 2.0)
        if zid in PAIRED:
            score = 0.68 * a_n + 0.32 * h_n
        else:
            score = 0.25 * a_n + 0.75 * h_n
        zones.append(
            {
                "id": zid,
                "name": z["name"],
                "status": z["status"],
                "score": round(float(score), 4),
                "asym": round(float(a), 4),
                "hetero": round(float(s["hetero"]), 4),
            }
        )

    zones.sort(key=lambda x: x["score"], reverse=True)
    for i, z in enumerate(zones, 1):
        z["rank"] = i

    # 争议：算法排序靠前但标注为「未见异常」，或标注异常但算法排序靠后
    disagreements = []
    for z in zones:
        if z["rank"] <= 3 and z["status"] == "normal" and z["score"] >= 0.42:
            disagreements.append(
                {
                    "type": "algorithm_flags_normal",
                    "zone": z["id"],
                    "zone_name": z["name"],
                    "score": z["score"],
                    "label": "算法提示可疑，但人工标注为未见异常",
                    "handling": "不采纳算法结论，保留人工标注；记录为待复核",
                }
            )
        if z["status"] == "abnormal" and z["score"] <= 0.18:
            disagreements.append(
                {
                    "type": "label_abnormal_low_score",
                    "zone": z["id"],
                    "zone_name": z["name"],
                    "score": z["score"],
                    "label": "人工标注异常，但算法未提示",
                    "handling": "以人工标注为准；说明经典算法对低对比病变不敏感",
                }
            )

    return {
        "case_id": case["id"],
        "title": case.get("title", ""),
        "zones": zones,
        "disagreements": disagreements,
    }


def main() -> None:
    payload = json.loads(SRC.read_text(encoding="utf8"))
    cases = []
    for case in payload["cases"]:
        if case.get("enabled") is False:
            continue
        r = analyze_case(case)
        if r:
            cases.append(r)
            print(" ", r["case_id"], "zones", len(r["zones"]), "dis", len(r["disagreements"]))

    out = {
        "version": "0.1.0",
        "method": METHOD,
        "disclaimer": DISCLAIMER,
        "generated_from": "kb/data/chest_reading.json",
        "cases": cases,
        "summary": {
            "cases": len(cases),
            "disagreements": sum(len(c["disagreements"]) for c in cases),
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    SITE_OUT.parent.mkdir(parents=True, exist_ok=True)
    SITE_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    print("wrote", OUT)
    print("wrote", SITE_OUT)
    print("cases=%d disagreements=%d" % (out["summary"]["cases"], out["summary"]["disagreements"]))


if __name__ == "__main__":
    main()
