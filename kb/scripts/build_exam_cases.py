#!/usr/bin/env python3
"""构建执业医师实践技能·胸部 X 线病例题数据。

输入：
    kb/data/exam_cases_src.json       自编题干、选项、解析、对比对
    kb/images/exam_src/*              已核对授权与来源的影像母本

输出：
    kb/data/exam_cases.json           页面只读这一份
    kb/images/exam/ex-*.jpg           统一压缩后的教学影像
    kb/licenses/EXAM_ATTRIBUTION.md   逐张署名与许可

规则：
  - 每例必须有唯一 id、5 个选项、答案下标合法；
  - 对比对的 left/right 必须指向存在的病例；
  - 影像统一转为 RGB、最长边不超过 1600、JPEG 质量 86；
  - 记录 sha256，便于页面和验收核对同一张图。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "kb/data/exam_cases_src.json"
OUT_DATA = ROOT / "kb/data/exam_cases.json"
IMG_SRC = ROOT / "kb/images/exam_src"
IMG_OUT = ROOT / "kb/images/exam"
ATTRIBUTION = ROOT / "kb/licenses/EXAM_ATTRIBUTION.md"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def render_image(src: Path, dst: Path) -> tuple[int, int]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((1600, 1600), Image.LANCZOS)
        im.save(dst, "JPEG", quality=86, optimize=True, progressive=True)
        return im.size


def main() -> None:
    payload = json.loads(SRC.read_text(encoding="utf8"))
    cases = payload["cases"]
    pairs = payload["pairs"]

    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise SystemExit("病例 id 重复")
    if len(cases) != len(payload["syllabus"]):
        raise SystemExit("大纲条目数与病例数不一致")

    by_id = {c["id"]: c for c in cases}
    for item in payload["syllabus"]:
        if item["case_id"] not in by_id:
            raise SystemExit("大纲条目指向不存在的病例：%s" % item["case_id"])

    for c in cases:
        if len(c["options"]) != 5:
            raise SystemExit("%s 选项数不是 5" % c["id"])
        if not (0 <= int(c["answer"]) < 5):
            raise SystemExit("%s 答案下标越界" % c["id"])
        if c["options"][int(c["answer"])] != c["diagnosis"]:
            # 诊断允许带括号、分期或“陈旧性”等限定；比较前去掉这些修饰。
            import re
            opt = c["options"][int(c["answer"])]
            norm = lambda s: re.sub(r"（[^）]*）|\([^)]*\)|陈旧性|可能", "", s)
            if norm(opt) not in norm(c["diagnosis"]):
                raise SystemExit("%s 正确选项与诊断不一致：%s / %s" % (c["id"], opt, c["diagnosis"]))
        for other in c.get("compare", []):
            if other not in by_id:
                raise SystemExit("%s compare 指向不存在的病例 %s" % (c["id"], other))

    for p in pairs:
        for side in ("left", "right"):
            if p[side] not in by_id:
                raise SystemExit("对比对 %s 的 %s 指向不存在的病例" % (p["id"], side))

    attribution_rows = []
    for c in cases:
        src = ROOT / c["image_src"]
        if not src.exists():
            raise SystemExit("缺少影像母本：%s" % src)
        dst_name = c["id"].lower() + ".jpg"
        dst = IMG_OUT / dst_name
        w, h = render_image(src, dst)
        c["image"] = "images/exam/" + dst_name
        c["image_width"] = w
        c["image_height"] = h
        c["sha256"] = sha256(dst)
        attribution_rows.append(
            "| {id} | {title} | {artist} | {license} | [Commons]({url}) |".format(
                id=c["id"],
                title=c["source"]["title"],
                artist=c["source"]["artist"],
                license=c["source"]["license"],
                url=c["source"]["url"],
            )
        )

    out = {
        "version": payload["version"],
        "title": payload["title"],
        "subtitle": payload["subtitle"],
        "scope": payload["scope"],
        "disclaimer": payload["disclaimer"],
        "question_basis": payload["question_basis"],
        "syllabus": payload["syllabus"],
        "sources": payload["sources"],
        "cases": cases,
        "pairs": pairs,
        "counts": {
            "cases": len(cases),
            "syllabus": len(payload["syllabus"]),
            "pairs": len(pairs),
            "groups": sorted({c["group"] for c in cases}),
        },
    }
    OUT_DATA.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")

    lines = [
        "# 病例题影像署名与许可",
        "",
        "本文件由 `kb/scripts/build_exam_cases.py` 生成。",
        "影像只用于医学影像教学演示；版权归原作者，使用遵循下列许可。",
        "部分影像为公开来源自带教学标注（红箭头/白线/文字），已在题目 `image_note` 中说明。",
        "",
        "| 病例 | 原始文件 | 作者 | 许可 | 来源 |",
        "| --- | --- | --- | --- | --- |",
    ] + attribution_rows + [
        "",
        "## 处理说明",
        "",
        "- `EX-06` 的母本为公开来源的左侧大量胸腔积液胸片，原图带黑色圆圈标注；",
        "  本站用 OpenCV 局部修复去除圆圈，仅保留影像本体，未改变病灶。",
        "- `EX-02` 保留来源原图红箭头；`EX-07` 保留来源原图白线与 Old fractures 文字；",
        "  两处均为公开来源自带教学标注，已在题目 `image_note` 中说明，不代表诊断。",
        "- 其余影像仅做尺寸压缩与 JPEG 转码，未做病灶增强或合成。",
        "",
        "## 题目版权",
        "",
        "题干、选项、解析与对比要点为本站按公开大纲与公开例题的题型自编，",
        "不复制受版权保护的题库原文；如用于正式教学，请由医学人员逐条审核。",
    ]
    ATTRIBUTION.write_text("\n".join(lines) + "\n", encoding="utf8")

    print("cases=%d pairs=%d images=%d" % (len(cases), len(pairs), len(cases)))
    print("wrote", OUT_DATA)
    print("wrote", ATTRIBUTION)


if __name__ == "__main__":
    main()
