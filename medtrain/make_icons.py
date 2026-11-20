#!/usr/bin/env python3
"""生成 PWA 图标（桌面/主屏快捷入口用）。

用法：
  python3 medtrain/make_icons.py

产物写入 medtrain/app/icons/，由 build.py 一并复制到站点根目录 icons/。
图标是「R」字标：深青底 + 浅青渐变描边 + 白字，和站点主题色一致。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC = Path(__file__).resolve().parent / "app" / "icons"
FONT_CANDIDATES = [
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 0),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
]
BG_TOP = (14, 124, 123)
BG_BOTTOM = (11, 79, 85)
INK = (255, 255, 255)


def font(size):
    for path, index in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=index)
    raise SystemExit("找不到可用的中文字体，请手动安装或改用图标源文件")


def gradient(size):
    img = Image.new("RGB", (size, size), BG_BOTTOM)
    px = img.load()
    for y in range(size):
        t = y / max(size - 1, 1)
        r = round(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = round(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = round(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return img


def draw_icon(size, maskable=False):
    scale = 4  # 先放大绘制再缩小，边缘更干净
    s = size * scale
    img = gradient(s).convert("RGBA")

    if not maskable:
        # 普通图标：圆角矩形，透明四角
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=255)
        img.putalpha(mask)

    d = ImageDraw.Draw(img)
    # 内描边：一圈浅青光环，缩到 32px 仍可辨认
    inset = int(s * (0.10 if maskable else 0.055))
    d.rounded_rectangle(
        (inset, inset, s - inset, s - inset),
        radius=int(s * 0.18),
        outline=(143, 227, 214, 120),
        width=max(2, int(s * 0.012)),
    )

    # 「影」字：maskable 版留足安全区（内容控制在 80% 内）
    text = "R"
    f = font(int(s * (0.46 if maskable else 0.52)))
    box = d.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((s - w) / 2 - box[0], (s - h) / 2 - box[1]), text, font=f, fill=INK)

    return img.resize((size, size), Image.LANCZOS)


def main():
    SRC.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-maskable-512.png", 512, True),
        ("apple-touch-icon-180.png", 180, False),
    ]
    for name, size, maskable in targets:
        icon = draw_icon(size, maskable=maskable)
        if name.startswith("apple-touch"):
            # iOS 会自己加圆角，底色必须不透明
            flat = Image.new("RGB", (size, size), BG_BOTTOM)
            flat.paste(icon, (0, 0), icon)
            flat.save(SRC / name, optimize=True)
        else:
            icon.save(SRC / name, optimize=True)
        print("wrote", (SRC / name).relative_to(SRC.parent.parent.parent), (SRC / name).stat().st_size)


if __name__ == "__main__":
    main()
