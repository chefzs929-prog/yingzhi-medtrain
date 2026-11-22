#!/usr/bin/env python3
"""把站点收缩为「一个首页 + 一个胸片阅片工作台」。

用法：
    python3 medtrain/build.py

产物：
    outputs/medtrain/index.html          唯一门面（无 JS，纯静态）
    outputs/medtrain/read/clinic.html    唯一功能页
    outputs/medtrain/data/chest/...      胸片逐区数据
    outputs/medtrain/images/case-*.jpg   胸片影像
    outputs/medtrain/app.html            旧入口 -> 跳转到 clinic
    outputs/medtrain/dev/*.html          旧角色/设备入口 -> 跳转
    outputs/medtrain/read/index|teach|paper|compare.html -> 跳转

不再构建：三角色 SPA、人体 3D 模型、分区图谱、组卷、报告对照。
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(__file__).resolve().parent / "app"
OUT = ROOT / "outputs" / "medtrain"

REDIRECT = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>已收缩至胸片阅片 · RadioCheck</title>
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


def write_redirect(path: Path, target: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(REDIRECT.replace("__TARGET__", target), encoding="utf8")


def write_shell() -> None:
    """首页 + PWA 清单 + 图标；不再复制 SPA 脚本、模型与全库数据。"""
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC / "landing-min.html", OUT / "index.html")
    shutil.copy2(SRC / "manifest.webmanifest", OUT / "manifest.webmanifest")
    attribution = ROOT / "kb/licenses/ATTRIBUTION.md"
    if attribution.exists():
        shutil.copy2(attribution, OUT / "ATTRIBUTION.md")
    icons = SRC / "icons"
    if icons.exists():
        shutil.copytree(icons, OUT / "icons", dirs_exist_ok=True)


def write_redirects() -> None:
    """旧入口全部收敛到胸片阅片，保留链接不 404。"""
    write_redirect(OUT / "app.html", "read/clinic.html")

    for stale in OUT.glob("*.html"):
        if stale.name not in ("index.html", "app.html"):
            write_redirect(stale, "read/clinic.html")

    dev = OUT / "dev"
    if dev.exists():
        for page in dev.glob("*.html"):
            write_redirect(page, "../read/clinic.html")


def write_readme() -> None:
    text = """# RadioCheck · 胸片阅片（收缩版）

对外只有一个首页和一个功能页：

| 入口 | 说明 |
| --- | --- |
| `index.html` | 唯一门面：范围、四种状态、能力边界 |
| `read/clinic.html` | 唯一功能页：21 例 CR 胸部逐区阅片 |

旧入口 `app.html`、`read/teach.html`、`read/paper.html`、`read/compare.html`、
`read/index.html`、`dev/*.html` 都已改为跳转到 `read/clinic.html`，不再提供第二套功能。

## 运行

```bash
cd outputs/medtrain
python3 -m http.server 8080
# 打开 http://127.0.0.1:8080/
```

## 主链路

1. 左侧选一例（21 例，可按正常 / 气腔影 / 气胸 / 积液 / 结核 / 结节筛选）；
2. 点影像上的教学分区（PA 8 区、LAT 3 区），或拖框；
3. 右栏给出该区独立所见、状态与依据；
4. 「生成阅片记录」导出系统所见 + 分区所见 + 出处 + 非诊断声明。

纯静态：上传按 SHA-256 精确匹配库内影像，未入库明确拒绝；页面不调用大模型。

## 构建与验收

```bash
python3 medtrain/build.py                      # 首页 + clinic + 胸片数据/影像
python3 kb/scripts/selfcheck_chest_reading.py  # 数据规则 183 项
python3 medtrain/tests/chest_check.py          # 工作台端到端 35 项（需先起 8811 端口）
python3 medtrain/tests/site_check.py           # 全站收缩 18 项（同上）
```

数据自检：`outputs/medtrain/chest_selfcheck.md`
工作台端到端：`outputs/medtrain/chest_ui_check.md`
全站收缩：`outputs/medtrain/site_check.md`

## 边界

- 只做 CR 胸部；非胸片未逐区校正，不作为对外功能。
- 不做病灶检测与分割；分区框是教学分区。
- 不做诊断、分期、治疗或预后判断。
- 逐区文本由 AI 辅助整理，正式教学前须由医学人员逐条审核签字。
"""
    (OUT / "README.md").write_text(text, encoding="utf8")


def build_reading() -> None:
    for script in ("kb/scripts/build_chest_reading.py",
                   "kb/scripts/build_teach_pages.py"):
        subprocess.run([sys.executable, str(ROOT / script)], check=True, cwd=str(ROOT))


# 只清理 outputs/medtrain 的旧构建产物，不动 kb/ 与 medtrain/app 源码。
LEGACY_ROOT_FILES = [
    "apply-doctor.js", "apply-student.js", "apply-teacher.js", "apply.js",
    "ask.css", "ask.js", "body-3d.js", "body-model.js", "core.js", "drill.js",
    "home.js", "init.js", "landing.css", "landing.js", "learn.js",
    "pwa.css", "pwa.js", "sse.js", "styles.css", "sw.js", "transfer.js",
]
LEGACY_DIRS = ["models", "vendor"]
LEGACY_READ_ASSETS = [
    "agent.css", "agent.js", "app.css", "compare.css", "compare.js",
    "paper.css", "paper.js", "static.js", "teach.css", "teach.js",
]


def clean_legacy() -> None:
    """把构建目录收缩到实际被引用的资源；旧入口保留跳转页。"""
    for name in LEGACY_ROOT_FILES:
        path = OUT / name
        if path.is_file():
            path.unlink()

    for name in LEGACY_DIRS:
        path = OUT / name
        if path.is_dir():
            shutil.rmtree(path)

    for name in LEGACY_READ_ASSETS:
        path = OUT / "read" / name
        if path.is_file():
            path.unlink()

    data = OUT / "data"
    if data.is_dir():
        for child in data.iterdir():
            if child.name == "chest":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    chest = data / "chest" / "chest_reading.json"
    keep = set()
    if chest.exists():
        import json
        payload = json.loads(chest.read_text(encoding="utf8"))
        keep = {Path(case["image"]).name for case in payload["cases"]}

    images = OUT / "images"
    if images.is_dir():
        for child in images.iterdir():
            if child.is_file() and child.name not in keep:
                child.unlink()


def main() -> None:
    write_shell()
    build_reading()
    clean_legacy()
    write_redirects()
    write_readme()
    print("built", OUT)
    for p in sorted(OUT.glob("*.html")):
        print(" ", p.name)


if __name__ == "__main__":
    main()
