#!/usr/bin/env python3
"""把站点收缩为「一个首页 + 一个胸片阅片工作台」。

输出：
    outputs/medtrain/read/clinic.html    唯一功能页
    outputs/medtrain/read/*.css|js       只复制 clinic 需要的 5 个资源
    outputs/medtrain/data/chest/...      胸片逐区数据
    outputs/medtrain/images/case-*.jpg   胸片数据引用到的影像
    outputs/medtrain/read/index|teach|paper|compare.html -> 跳转到 clinic

旧的图谱 / 组卷 / 报告对照页面不再构建，只保留跳转，避免旧链接 404。
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "kb/app"
OUT = ROOT / "outputs/medtrain/read"
SITE = OUT.parent

# clinic.html 只依赖这 5 个资源；agent/app/teach/paper/compare 不再打包
ASSETS = ["base.css", "clinic.css", "common.js", "locate.js", "clinic.js"]

LEGACY_PAGES = ["index.html", "teach.html", "paper.html", "compare.html"]

REDIRECT = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · RadioCheck</title>
<meta http-equiv="refresh" content="0;url=__TARGET__">
<link rel="canonical" href="__TARGET__">
<style>
html,body{height:100%;margin:0;background:#f4fbfa;color:#10232e;
  font:14px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  display:grid;place-items:center}
.box{text-align:center;padding:24px}
.m{width:44px;height:44px;border-radius:13px;margin:0 auto 12px;display:grid;place-items:center;
  background:linear-gradient(140deg,#0b4f55,#0e7c7b);color:#fff;font-size:20px;font-weight:700}
p{margin:4px 0;color:#5b7480}
a{color:#0b4f55;font-weight:600}
</style>
</head>
<body>
<div class="box">
  <div class="m">R</div>
  <p><b>站点已收缩，只保留胸片阅片。</b></p>
  <p><a href="__TARGET__">正在进入胸片阅片…</a></p>
</div>
<script>location.replace("__TARGET__");</script>
</body>
</html>
"""


def write_redirect(path: Path, target: str, title: str = "已收缩至胸片阅片") -> None:
    path.write_text(
        REDIRECT.replace("__TARGET__", target).replace("__TITLE__", title),
        encoding="utf8",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    for name in ASSETS:
        src = SRC / name
        if not src.exists():
            raise SystemExit("missing clinic asset: %s" % src)
        shutil.copy2(src, OUT / name)

    shutil.copy2(SRC / "clinic.html", OUT / "clinic.html")

    # 旧四页与 read 入口全部收敛到 clinic
    for page in LEGACY_PAGES:
        write_redirect(OUT / page, "clinic.html")

    # 胸片逐区数据：页面只读这一份
    chest = ROOT / "kb/data/chest_reading.json"
    if not chest.exists():
        raise SystemExit("missing kb/data/chest_reading.json; run build_chest_reading.py first")
    dst = SITE / "data/chest/chest_reading.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(chest, dst)
    data = json.loads(chest.read_text(encoding="utf8"))

    # 只复制数据实际引用的胸片，不搬 120 例全库影像
    copied = 0
    for case in data["cases"]:
        rel = case["image"]  # images/case-xxx.jpg
        src = ROOT / "kb" / rel
        if not src.exists():
            print("missing image:", src)
            continue
        target = SITE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied += 1

    print("clinic.html + %d assets, %d images, %d cases" % (len(ASSETS), copied, len(data["cases"])))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
