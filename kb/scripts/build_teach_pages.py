#!/usr/bin/env python3
"""把 kb/app 的阅片工作台打包成静态页面，输出到 outputs/medtrain/read/。

改动只有路径与脚本注入，不改页面逻辑：
    /teach.css -> teach.css        /teach -> teach.html
    /clinic.css -> clinic.css      /clinic -> clinic.html
    在业务脚本前注入 static.js（/api 映射）与 locate.js（框选本地计算）
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "kb/app"
OUT = ROOT / "outputs/medtrain/read"

ASSETS = ["teach.css", "clinic.css", "paper.css", "compare.css", "app.css",
          "teach.js", "clinic.js", "paper.js", "compare.js", "static.js", "locate.js"]
PAGES = {
    "teach.html": ("teach.css", "teach.js"),
    "clinic.html": ("clinic.css", "clinic.js"),
    "paper.html": ("paper.css", "paper.js"),
    "compare.html": ("compare.css", "compare.js"),
}


def rewrite(html, css, js):
    html = html.replace('href="/%s"' % css, 'href="%s"' % css)
    html = html.replace('src="/%s"' % js, 'src="%s"' % js)
    html = html.replace('href="/teach"', 'href="teach.html"')
    html = html.replace('href="/clinic"', 'href="clinic.html"')
    html = html.replace('href="/paper"', 'href="paper.html"')
    html = html.replace('href="/compare"', 'href="compare.html"')
    # static.js / locate.js 必须先于业务脚本执行
    html = html.replace(
        '<script src="%s"></script>' % js,
        '<script src="static.js"></script>\n<script src="locate.js"></script>\n<script src="%s"></script>' % js,
    )
    return html


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        src = SRC / name
        if src.exists():
            shutil.copy2(src, OUT / name)
        else:
            print("missing asset:", name, file=sys.stderr)

    for page, (css, js) in PAGES.items():
        html = (SRC / page).read_text(encoding="utf8")
        (OUT / page).write_text(rewrite(html, css, js), encoding="utf8")

    # 对照页只需要 47 条指南，不必让它去拉 5MB 的 kb.json
    gl = ROOT / "kb/data/guidelines.jsonl"
    if gl.exists():
        rows = [json.loads(x) for x in gl.read_text(encoding="utf8").splitlines() if x.strip()]
        dst = OUT.parent / "data/guidelines.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps({"guidelines": rows}, ensure_ascii=False,
                                  separators=(",", ":")), encoding="utf8")
        print("guidelines.json %.0f KB" % (dst.stat().st_size / 1024))

    # 入口页：read/ 被直接访问时跳到教学页
    (OUT / "index.html").write_text(
        '<!DOCTYPE html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=teach.html">'
        '<title>分区读片</title><a href="teach.html">进入分区读片</a>',
        encoding="utf8",
    )
    print("wrote", OUT)


if __name__ == "__main__":
    main()
