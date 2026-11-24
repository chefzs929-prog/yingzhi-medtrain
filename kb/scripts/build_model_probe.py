"""用成熟的胸片多标签模型做独立交叉检验（离线预生成）。

模型：torchxrayvision 的 DenseNet121，权重 densenet121-res224-all
（在多个公开胸片数据集上联合训练，18 类常见影像表现）。

注意：
- 这是整图级的多标签概率，不是分区级定位，也不是诊断
- 只用于和人工逐区标注做「是否互相打脸」的对比
- 必须在 .venv 下运行：.venv/bin/python kb/scripts/build_model_probe.py

产物：kb/data/model_probe.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "kb/data/chest_reading.json"
IMG_ROOT = ROOT / "kb"
OUT = ROOT / "kb/data/model_probe.json"

WEIGHTS = "densenet121-res224-all"
TOP_K = 5

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
    img = Image.open(path).convert("L")
    arr = np.asarray(img.resize((224, 224)), dtype=np.float32)
    arr = xrv.datasets.normalize(arr, 255)
    t = torch.from_numpy(arr[None, ...])
    with torch.no_grad():
        out = model(t)[0].numpy()
    labels = list(model.pathologies)
    pairs = sorted(zip(labels, out.tolist()), key=lambda x: x[1], reverse=True)
    return {k: float(v) for k, v in pairs}


def main() -> None:
    payload = json.loads(SRC.read_text(encoding="utf8"))
    cases = [c for c in payload["cases"] if c.get("enabled") is not False]

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

        abnormal_zones = {z["id"] for z in case["zones"] if z["status"] == "abnormal"}
        named = [z for z in case["zones"] if z["id"] != "SUB"]
        all_normal = len(abnormal_zones) == 0

        # 一致性判定：只看高分标签（>=0.5）
        high = [t for t in top if t["score"] >= 0.5]
        agree, verdict, note = False, "silent", ""
        if high:
            hit = False
            for h in high:
                zones = LABEL_ZONES.get(h["label"], set())
                if zones & abnormal_zones:
                    hit = True
                    break
            if hit:
                agree, verdict = True, "consistent"
                note = "模型高分项与人工标注的异常分区指向同一类表现"
            elif all_normal:
                verdict, note = "conflict", "模型给出高分提示，但该例人工标注为全部未见异常"
            else:
                verdict, note = "partial", "模型有高分提示，但未命中人工标注的异常分区"
        else:
            if all_normal:
                agree, verdict = True, "consistent"
                note = "模型无高分提示，与「全部未见异常」一致"
            else:
                verdict, note = "silent", "人工标注存在异常，但模型未给出高分提示（漏检）"

        results.append(
            {
                "case_id": case["id"],
                "title": case.get("title", ""),
                "abnormal_zones": sorted(abnormal_zones),
                "top": top,
                "verdict": verdict,
                "agreement": agree,
                "note": note,
            }
        )
        print(f"  [{i:02d}] {case['id']} {verdict} top={top[0]['label']} {top[0]['score']:.2f}")

    out = {
        "version": "0.1.0",
        "method": f"torchxrayvision DenseNet121 ({WEIGHTS})",
        "disclaimer": (
            "整图级多标签概率，不是分区级定位，也不是诊断结论；"
            "模型在公开胸片数据上训练，对本库病例仅为独立交叉检验，未经医学审核。"
        ),
        "cases": results,
        "summary": {
            "cases": len(results),
            "consistent": sum(1 for r in results if r["verdict"] == "consistent"),
            "conflict": sum(1 for r in results if r["verdict"] == "conflict"),
            "partial": sum(1 for r in results if r["verdict"] == "partial"),
            "silent": sum(1 for r in results if r["verdict"] == "silent"),
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    print("\n写出", OUT)
    print("汇总", out["summary"])


if __name__ == "__main__":
    sys.exit(main())
