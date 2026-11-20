"""陌生影像的模板分区。

库内病例有逐病例人工标注（regions.jsonl），locate 走的是精确几何。
陌生文献影像没有这些标注，只能用 build_atlas_templates.py 聚合出的
通用模板做推断。

边界：
- 输出 source=atlas_template，不是人工标注，前端不得混用徽标；
- n_cases 少的 atlas 可信度低，必须在 warning 里说出来；
- 模板只回答「这个位置通常属于哪个分区」，不回答「这是什么病变」。
"""

import json
import os
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "kb" / "data"
TEMPLATE_FILE = DATA / "atlas_templates.json"

MAX_AREA = 0.30
MIN_SIDE = 0.03
MIN_COVER = 0.45
CROSS_GAP = 0.08
SECOND_MIN = 0.20
MIN_CASES_OK = 3


def _area(b):
    return max(0.0, b[2]) * max(0.0, b[3])


def _inter(a, b):
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[0] + a[2], b[0] + b[2])
    y2 = min(a[1] + a[3], b[1] + b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _clamp(bbox):
    b = [float(v) for v in bbox]
    b[0] = max(0.0, min(1.0, b[0]))
    b[1] = max(0.0, min(1.0, b[1]))
    b[2] = max(0.0, min(1.0 - b[0], b[2]))
    b[3] = max(0.0, min(1.0 - b[1], b[3]))
    return b


class AtlasTemplates:
    def __init__(self, path=None):
        self.path = Path(path or TEMPLATE_FILE)
        self.data = {"atlases": {}}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf8"))
            except Exception:
                self.data = {"atlases": {}}
        self.atlases = self.data.get("atlases") or {}

    # ---------- 选模板 ----------
    def list_atlases(self):
        out = []
        for aid, a in sorted(self.atlases.items()):
            out.append({
                "id": aid,
                "name": a.get("name"),
                "modality": a.get("modality") or [],
                "body_part": a.get("body_part") or "",
                "view": a.get("view") or "",
                "n_cases": a.get("n_cases") or 0,
                "n_regions": a.get("n_regions") or 0,
                "trust": "ok" if (a.get("n_cases") or 0) >= MIN_CASES_OK else "thin",
            })
        return out

    def match(self, modality=None, body_part=None, view=None):
        """按检查类型/部位/投照位打分选模板。没给条件就返回 None，不猜。"""
        if not (modality or body_part or view):
            return None
        want_mod = (modality or "").upper().strip()
        want_part = (body_part or "").strip()
        want_view = (view or "").upper().strip()

        best = None
        for aid, a in self.atlases.items():
            score = 0.0
            mods = [str(m).upper() for m in (a.get("modality") or [])]
            if want_mod and any(want_mod == m or want_mod in m for m in mods):
                score += 3.0
            if want_part and want_part == (a.get("body_part") or ""):
                score += 2.0
            elif want_part and want_part in (a.get("body_part") or ""):
                score += 1.0
            if want_view and want_view == (a.get("view") or "").upper():
                score += 2.0
            if score <= 0:
                continue
            # 同分时优先病例多的模板，样本越多模板越稳。
            score += min((a.get("n_cases") or 0), 50) / 100.0
            if best is None or score > best[0]:
                best = (score, aid, a)
        if best is None:
            return None
        return {"score": round(best[0], 2), "atlas": best[2]}

    # ---------- 模板定位 ----------
    def locate(self, atlas_id, bbox):
        a = self.atlases.get(atlas_id)
        if not a:
            return {"status": "no_template", "message": "没有这个分区模板", "bbox": _clamp(bbox)}
        b = _clamp(bbox)
        if _area(b) > MAX_AREA:
            return {"status": "too_large", "message": "选区过大，请缩小到单一分区后再定位", "bbox": b}
        if b[2] < MIN_SIDE or b[3] < MIN_SIDE:
            return {"status": "too_small", "message": "选区过小，请扩大后再定位", "bbox": b}

        scored = []
        for r in a.get("regions") or []:
            c = r.get("coords") or []
            if len(c) != 4:
                continue
            inter = _inter(b, c)
            coverage = inter / max(1e-9, _area(b))
            purity = inter / max(1e-9, _area(c))
            scored.append({
                "region": r,
                "coverage": coverage,
                "purity": purity,
                "score": 0.7 * coverage + 0.3 * purity,
            })
        if not scored:
            return {"status": "no_template", "message": "模板没有可用分区", "bbox": b}
        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[0]
        second = scored[1] if len(scored) > 1 else None

        if top["coverage"] < MIN_COVER:
            return {"status": "uncovered", "message": "该位置不在模板分区内，不作推断", "bbox": b}
        if second and (top["score"] - second["score"]) < CROSS_GAP and second["coverage"] > SECOND_MIN:
            return {
                "status": "cross",
                "message": "选区同时落在两个分区，请缩小范围",
                "bbox": b,
                "candidates": [self._card(top, a), self._card(second, a)],
                "gap": round(top["score"] - second["score"], 4),
                "source": "atlas_template",
            }
        return {
            "status": "single",
            "bbox": b,
            "primary": self._card(top, a),
            "secondary": self._card(second, a) if second and second["coverage"] > 0.12 else None,
            "mode": "template",
            "source": "atlas_template",
        }

    def _card(self, s, atlas):
        r = s["region"]
        sd = r.get("sd") or [0, 0, 0, 0]
        mean_sd = sum(sd) / 4.0
        # 不叫 confidence：这是模板离散度换算出的「一致度」，不是模型置信度。
        agreement = round(s["coverage"] * max(0.0, 1 - mean_sd / 0.05), 3)
        card = {
            "region": {
                "id": None,
                "name": r.get("name"),
                "name_en": r.get("name_en") or "",
                "coords": r.get("coords"),
                "level": r.get("level"),
                "parent_region_id": r.get("parent_region_id"),
                "patient_side": r.get("patient_side"),
                "image_side": r.get("image_side"),
                "note": r.get("note") or "",
                "sign_ids": r.get("sign_ids") or [],
                "atlas_id": atlas.get("id"),
            },
            "coverage": round(s["coverage"], 4),
            "purity": round(s["purity"], 4),
            "score": round(s["score"], 4),
            "template_n": r.get("n") or 0,
            "template_sd": sd,
            "agreement": agreement,
            "source": "atlas_template",
        }
        if (atlas.get("n_cases") or 0) < MIN_CASES_OK:
            card["warning"] = "该模板仅由 %d 例标注聚合，样本偏少，结论需人工复核" % (atlas.get("n_cases") or 0)
        return card


_CACHE = {"mtime": None, "obj": None}


def load(path=None):
    p = Path(path or TEMPLATE_FILE)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return AtlasTemplates(p)
    if _CACHE["obj"] is None or _CACHE["mtime"] != mtime:
        _CACHE["obj"] = AtlasTemplates(p)
        _CACHE["mtime"] = mtime
    return _CACHE["obj"]
