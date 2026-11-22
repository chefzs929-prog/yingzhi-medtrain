"""分割适配器：bbox → mask。

当前只做能力探测，不内置模型权重，也不伪造 mask。
装了 `torch` + `sam2`（或 `segment_anything`）后，把权重路径配到
`YZ_SEG_CHECKPOINT`，`available()` 才会返回 True。

为什么先留接口：
- 分割模型动辄数百 MB，不能塞进纯标准库服务；
- 没有权重时返回 unavailable，比返回一个假轮廓诚实。
"""

import os

_CHECKPOINT = os.environ.get("YZ_SEG_CHECKPOINT", "").strip()


def _probe():
    mods = {}
    for name in ("torch", "sam2", "segment_anything"):
        try:
            __import__(name)
            mods[name] = True
        except Exception:
            mods[name] = False
    return mods


def status():
    mods = _probe()
    backend = None
    if mods.get("torch") and mods.get("sam2"):
        backend = "sam2"
    elif mods.get("torch") and mods.get("segment_anything"):
        backend = "sam1"
    return {
        "available": bool(backend and _CHECKPOINT),
        "backend": backend,
        "checkpoint": bool(_CHECKPOINT),
        "modules": mods,
        "reason": None if (backend and _CHECKPOINT) else (
            "missing_checkpoint" if backend else "missing_dependency"),
        "install": "pip install torch sam2 && export YZ_SEG_CHECKPOINT=/path/to/medsam2.pt",
    }


def segment(image, bbox):
    """返回 mask（RLE 或 PNG data URL）。未就绪时抛错，不返回假结果。"""
    st = status()
    if not st["available"]:
        raise RuntimeError("segment unavailable: %s" % st["reason"])
    # 真正的推理放在这里：加载 checkpoint → predictor.predict(bbox) → mask。
    # 当前不写占位实现，避免把随机 mask 当成结果。
    raise RuntimeError("segment backend wired but inference not implemented")
