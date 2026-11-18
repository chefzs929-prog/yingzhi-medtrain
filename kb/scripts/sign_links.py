#!/usr/bin/env python3
"""征象文字 ↔ 影像区域关联（v1）的数据校验与文字分段。

设计约束：
- 每条关联必须同时有“文字锚点”（征象 appearance 中的原文片段）和“图像锚点”（图像 + 归一化框）；
- 框是人工标注的教学区域，不是模型检测或病灶分割；
- 侧别由 laterality_rule 显式声明，禁止从图像方位默推患者侧别；
- 校验失败时直接报错，不静默降级。

命令行：python3 kb/scripts/sign_links.py
"""
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

LATERALITY_RULES = {
    # 镜像规则：图像左侧 = 患者右侧
    "pa_chest": {"mode": "mirror", "atlas": "global"},
    "ap_chest": {"mode": "mirror", "atlas": "global"},
    "axial_ct": {"mode": "mirror", "atlas": "global"},
    "axial_mr": {"mode": "mirror", "atlas": "global"},
    # 无左右之分
    "lateral_chest": {"mode": "none", "atlas": "global"},
    # 局部视野：只给图像内相对位置
    "us_local": {"mode": "none", "atlas": "local"},
    "mg_mlo": {"mode": "none", "atlas": "local"},
}
BASIS = {"source_label", "source_description", "teaching_estimate"}
REVIEW = {"single_review", "double_review"}
STATUS = {"active", "deprecated"}
SIDE = {"left", "right"}
ID_RE = re.compile(r"^SL-\d{3}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load(path=None):
    path = Path(path or DATA / "sign_links.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]


def rule_key(rule):
    return str(rule or "").split(":", 1)[0].strip()


def validate_laterality(region, link_id, index):
    """返回错误列表；侧别错误按零容忍处理。"""
    errors = []
    rule = region.get("laterality_rule", "")
    key = rule_key(rule)
    spec = LATERALITY_RULES.get(key)
    label = f"{link_id} regions[{index}]"
    if not spec:
        return [f"{label} 使用了未登记的侧别规则：{rule!r}"]
    image_side = region.get("image_side")
    patient_side = region.get("patient_side")
    atlas = region.get("atlas_level")
    if atlas != spec["atlas"]:
        errors.append(f"{label} atlas_level 应为 {spec['atlas']}，实际 {atlas!r}")
    if spec["mode"] == "mirror":
        if image_side not in SIDE:
            errors.append(f"{label} image_side 必须为 left/right")
        if patient_side not in SIDE:
            errors.append(f"{label} patient_side 必须为 left/right")
        if image_side in SIDE and patient_side in SIDE and image_side == patient_side:
            errors.append(f"{label} 镜像规则下 image_side 与 patient_side 不能相同")
    elif spec["mode"] == "none":
        if image_side is not None or patient_side is not None:
            errors.append(f"{label} 该规则不应声明左右侧别")
    return errors


def validate(links, signs_by_id, cases_by_id, sources=None):
    """校验全部图文关联，返回错误列表（空列表表示通过）。"""
    errors = []
    seen = set()
    for link in links:
        lid = link.get("id", "")
        if not ID_RE.match(lid):
            errors.append(f"{lid or '(空 id)'} id 必须形如 SL-001")
        if lid in seen:
            errors.append(f"{lid} id 重复")
        seen.add(lid)

        sign = signs_by_id.get(link.get("sign_id"))
        case = cases_by_id.get(link.get("image_id"))
        if not sign:
            errors.append(f"{lid} 关联的征象不存在：{link.get('sign_id')}")
        if not case:
            errors.append(f"{lid} 关联的影像不存在：{link.get('image_id')}")
        if sign and case and link.get("sign_id") not in case.get("sign_tags", []):
            errors.append(f"{lid} 影像 {case.get('id')} 的 sign_tags 未包含 {link.get('sign_id')}")

        quote = link.get("quote", "")
        if not quote:
            errors.append(f"{lid} 缺少文字锚点 quote")
        elif sign and quote not in sign.get("appearance", ""):
            errors.append(f"{lid} quote 不是 {link.get('sign_id')} appearance 的原文片段")

        regions = link.get("regions") or []
        if not regions:
            errors.append(f"{lid} 缺少图像锚点 regions")
        for i, region in enumerate(regions):
            label = f"{lid} regions[{i}]"
            bbox = region.get("bbox")
            if not (isinstance(bbox, list) and len(bbox) == 4):
                errors.append(f"{label} bbox 必须是 [x, y, w, h]")
                continue
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox):
                errors.append(f"{label} bbox 必须全部为数值")
                continue
            x, y, w, h = bbox
            if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
                errors.append(f"{label} bbox 越界或宽高非正")
            if x + w > 1.000001 or y + h > 1.000001:
                errors.append(f"{label} bbox 超出图像边界")
            if w < 0.02 or h < 0.02:
                errors.append(f"{label} bbox 太小，无法作为教学区域")
            if not region.get("label"):
                errors.append(f"{label} 缺少区域名称 label")
            errors.extend(validate_laterality(region, lid, i))

        if link.get("basis") not in BASIS:
            errors.append(f"{lid} basis 不合法：{link.get('basis')!r}")
        if link.get("review") not in REVIEW:
            errors.append(f"{lid} review 不合法：{link.get('review')!r}")
        if link.get("status") not in STATUS:
            errors.append(f"{lid} status 不合法：{link.get('status')!r}")
        if link.get("annotator") != "human":
            errors.append(f"{lid} annotator 必须为 human")
        if not DATE_RE.match(str(link.get("annotated_at", ""))):
            errors.append(f"{lid} annotated_at 必须为 YYYY-MM-DD")
        else:
            try:
                date.fromisoformat(link["annotated_at"])
            except ValueError:
                errors.append(f"{lid} annotated_at 不是有效日期")
        evidence = link.get("evidence") or {}
        if sources is not None and evidence.get("source_id") not in sources:
            errors.append(f"{lid} evidence.source_id 未登记：{evidence.get('source_id')!r}")
        if not str(evidence.get("source_page", "")).startswith("https://"):
            errors.append(f"{lid} evidence.source_page 必须是 https 链接")
        if not link.get("caption"):
            errors.append(f"{lid} 缺少 caption")
        if not link.get("reading"):
            errors.append(f"{lid} 缺少 reading")
    return errors


def segments_for(appearance, links):
    """把 appearance 切成普通片段与带 link_ids 的锚点片段。

    多条 link 可以共享同一段原文；不同锚点不允许重叠。
    """
    spans = []
    for link in links:
        quote = link.get("quote", "")
        start = appearance.find(quote)
        if start < 0:
            raise ValueError(f"{link.get('id')} quote 不在 appearance 中：{quote!r}")
        spans.append((start, start + len(quote), link["id"]))
    spans.sort()

    for (s1, e1, l1), (s2, e2, l2) in zip(spans, spans[1:]):
        if s2 < e1 and not (s1 == s2 and e1 == e2):
            raise ValueError(f"文字锚点重叠：{l1} 与 {l2}")

    out = []
    pos = 0
    for start, end, link_id in spans:
        if start > pos:
            out.append({"start": pos, "end": start, "text": appearance[pos:start], "link_ids": []})
        if out and out[-1]["start"] == start and out[-1]["end"] == end:
            if link_id not in out[-1]["link_ids"]:
                out[-1]["link_ids"].append(link_id)
        else:
            out.append({"start": start, "end": end, "text": appearance[start:end], "link_ids": [link_id]})
        pos = end
    if pos < len(appearance):
        out.append({"start": pos, "end": len(appearance), "text": appearance[pos:], "link_ids": []})
    return out


def main():
    signs = {s["id"]: s for s in load(DATA / "signs.jsonl")}
    cases = {c["id"]: c for c in load(DATA / "cases.jsonl")}
    sources = {s["id"]: s for s in json.loads((DATA / "sources.json").read_text(encoding="utf8"))["sources"]}
    links = load()
    errors = validate(links, signs, cases, sources)
    for link in links:
        try:
            segments_for(signs[link["sign_id"]]["appearance"], [link])
        except Exception as exc:  # noqa: BLE001 - CLI 需要直接展示分段错误
            errors.append(f"{link.get('id')} 分段失败：{exc}")
    print(f"sign_links={len(links)} signs={len({x['sign_id'] for x in links})} "
          f"images={len({x['image_id'] for x in links})} errors={len(errors)}")
    for err in errors:
        print("  ERROR", err)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
