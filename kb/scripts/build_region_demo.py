#!/usr/bin/env python3
"""构建「影像区域定位 + 文献溯源双引用」单文件演示页。

输入：kb/web/region-cite.template.html（含 __IMG_DATA__ 占位符）
      kb/images/ 下 3 张已核验的公开影像
输出：outputs/region-cite-demo.html（单文件、可离线打开）

影像会先等比缩放到 780px 宽并压缩，再以 base64 内嵌；
优先用 Pillow，其次 macOS 自带 sips，两者都不可用时内嵌原图。

用法：python3 kb/scripts/build_region_demo.py
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
TEMPLATE = KB / "web/region-cite.template.html"
OUT = PROJ / "outputs/region-cite-demo.html"

CASES = {
    "CASE-001": "case-001.jpg",
    "CASE-006": "case-006.jpg",
    "CASE-011": "case-011.jpg",
}
MAX_W = 780
QUALITY = 58


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


def main() -> int:
    if not TEMPLATE.exists():
        print(f"缺少模板：{TEMPLATE}", file=sys.stderr)
        return 1

    imgs = {}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for key, name in CASES.items():
            src = KB / "images" / name
            if not src.exists():
                print(f"缺少影像：{src}", file=sys.stderr)
                return 1
            dst = tmp / name
            ok = shrink_with_pillow(src, dst) or shrink_with_sips(src, dst)
            use = dst if ok else src
            imgs[key] = "data:image/jpeg;base64," + base64.b64encode(use.read_bytes()).decode("ascii")

    html = TEMPLATE.read_text(encoding="utf8")
    placeholder = '"__IMG_DATA__"'
    if placeholder not in html:
        print("模板缺少 __IMG_DATA__ 占位符", file=sys.stderr)
        return 1
    html = html.replace(placeholder, json.dumps(imgs, ensure_ascii=False))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf8")
    print(f"written {OUT.relative_to(PROJ)}  ({OUT.stat().st_size/1024:.0f} KB, {len(imgs)} images)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
