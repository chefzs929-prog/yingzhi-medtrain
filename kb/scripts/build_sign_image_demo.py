#!/usr/bin/env python3
"""构建「征象文字 ↔ 影像位置」v1 离线单文件演示页。

输入：kb/web/sign-image.template.html、kb/web/sign-image-demo.js、kb/web/styles.css
      kb/data/sign_links.jsonl 及其关联的公开影像
输出：outputs/sign-image-demo.html（单文件、可离线打开）

影像会先等比缩放到 780px 宽并压缩，再以 base64 内嵌；
优先用 Pillow，其次 macOS 自带 sips，两者都不可用时内嵌原图。

用法：python3 kb/scripts/build_sign_image_demo.py
"""
import base64
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
PROJ = KB.parent
sys.path.insert(0, str(KB / "scripts"))

import kbsearch  # noqa: E402

TEMPLATE = KB / "web/sign-image.template.html"
DEMO_JS = KB / "web/sign-image-demo.js"
CSS = KB / "web/styles.css"
OUT = PROJ / "outputs/sign-image-demo.html"
MAX_W = 780
QUALITY = 60


def shrink_with_pillow(src: Path, dst: Path) -> bool:
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return False
    im = Image.open(src).convert("RGB")
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    im.save(dst, "JPEG", quality=QUALITY, optimize=True)
    return True


def shrink_with_sips(src: Path, dst: Path) -> bool:
    if not shutil.which("sips"):
        return False
    r = subprocess.run(
        ["sips", "-Z", str(MAX_W), "-s", "format", "jpeg",
         "-s", "formatOptions", str(QUALITY), str(src), "--out", str(dst)],
        capture_output=True,
    )
    return r.returncode == 0 and dst.exists()


def build_data(kb: kbsearch.KB):
    signs, links_map, images_map = [], {}, {}
    for item in kb.sign_index():
        detail = kb.sign_detail(item["id"])
        link_ids = []
        for i, link in enumerate(detail["links"]):
            image = link.get("image") or {}
            rec = {
                "id": link["id"],
                "n": i + 1,
                "sign_id": link["sign_id"],
                "sign_name": link["sign_name"],
                "quote": link["quote"],
                "caption": link["caption"],
                "reading": link["reading"],
                "regions": link["regions"],
                "basis": link["basis"],
                "review": link["review"],
                "annotated_at": link["annotated_at"],
                "image": {
                    k: image.get(k)
                    for k in ("id", "title", "modality", "body_part", "license", "artist", "source_page", "image")
                },
            }
            links_map[rec["id"]] = rec
            link_ids.append(rec["id"])
            group = images_map.setdefault(
                image["id"],
                {
                    "id": image["id"],
                    "title": image.get("title", ""),
                    "modality": image.get("modality", []),
                    "body_part": image.get("body_part", ""),
                    "license": image.get("license", ""),
                    "artist": image.get("artist", ""),
                    "source_page": image.get("source_page", ""),
                    "image": image.get("image", ""),
                    "links": [],
                },
            )
            group["links"].append(rec["id"])
        signs.append({
            "id": item["id"],
            "name": item["name"],
            "en": item["en"],
            "modality": item["modality"],
            "body_part": item["body_part"],
            "appearance": detail["appearance"],
            "segments": detail["segments"],
            "links": link_ids,
            "image_ids": list(dict.fromkeys(x["image"]["id"] for x in detail["links"])),
            "stats": detail["stats"],
        })
    gate = {
        "quotes": len({x["quote"] for x in kb.link_rows}),
        "links": len(kb.link_rows),
        "images": len(images_map),
        "regions": sum(len(x.get("regions", [])) for x in kb.link_rows),
    }
    return {
        "signs": signs,
        "links": links_map,
        "images": images_map,
        "gate": gate,
        "note": "框是人工标注的教学区域，不是模型识别，也不是病灶分割；仅用于文字与影像对照。",
    }


def main() -> int:
    for path in (TEMPLATE, DEMO_JS, CSS):
        if not path.exists():
            print(f"缺少文件：{path}", file=sys.stderr)
            return 1

    kb = kbsearch.KB()
    data = build_data(kb)
    if not data["signs"]:
        print("没有可导出的图文关联", file=sys.stderr)
        return 1

    imgs = {}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for image_id, group in data["images"].items():
            src = KB / group["image"]
            if not src.exists():
                print(f"缺少影像：{src}", file=sys.stderr)
                return 1
            dst = tmp / f"{image_id}{src.suffix}"
            ok = shrink_with_pillow(src, dst) or shrink_with_sips(src, dst)
            use = dst if ok else src
            imgs[image_id] = "data:image/jpeg;base64," + base64.b64encode(use.read_bytes()).decode("ascii")

    html = TEMPLATE.read_text(encoding="utf8")
    for placeholder, value in (
        ("__CSS__", CSS.read_text(encoding="utf8")),
        ("__KB_DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")),
        ("__KB_IMG__", json.dumps(imgs, ensure_ascii=False)),
        ("__JS__", DEMO_JS.read_text(encoding="utf8")),
    ):
        if placeholder not in html:
            print(f"模板缺少占位符：{placeholder}", file=sys.stderr)
            return 1
        html = html.replace(placeholder, value)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf8")
    print(
        f"written {OUT.relative_to(PROJ)}  "
        f"({OUT.stat().st_size / 1024:.0f} KB, {len(data['signs'])} signs, "
        f"{len(data['links'])} links, {len(imgs)} images)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
