#!/usr/bin/env python3
"""把 medtrain/app 打包成多版本分发目录。

用法：
  python3 medtrain/build_data.py     # 先生成 data/kb.js 与 images/
  python3 medtrain/build.py          # 再生成 app.html、版本入口与启动页
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(__file__).resolve().parent / "app"
OUT = ROOT / "outputs" / "medtrain"

APP_FILES = [
    "sse.js", "core.js", "home.js", "learn.js", "transfer.js", "drill.js",
    "apply-student.js", "apply-teacher.js", "apply-doctor.js", "apply.js", "ask.js", "init.js",
    "styles.css", "ask.css",
    # 产品首页（index.html）专用
    "body-model.js", "body-3d.js", "landing.js", "landing.css",
]

VERSIONS = [
    ("通用自适应版", "desktop+mobile", "app.html", "一套布局自动适配，评审现场从桌面拖到手机宽度即可演示。", "通用"),
    ("学生端 · 桌面", "student+desktop", "student.html", "学习路径、四步演练、实习任务与学习报告。", "学生"),
    ("学生端 · 移动", "student+mobile", "student-mobile.html", "单列卡片、底部导航、触控点选分区。", "学生"),
    ("教师端 · 桌面", "teacher+desktop", "teacher.html", "班级概览、作业编排、错题分析、课堂投屏。", "教师"),
    ("教师端 · 移动", "teacher+mobile", "teacher-mobile.html", "随时看班、布置任务、讲评清单。", "教师"),
    ("医生端 · 桌面", "doctor+desktop", "doctor.html", "病例工作台、双引用核验、引用审计、交班摘要。", "医生"),
    ("医生端 · 移动", "doctor+mobile", "doctor-mobile.html", "床旁/读片室快速查证与出处核对。", "医生"),
]


def stamp_assets(html):
    """给本地 js/css 引用加内容哈希。

    浏览器会缓存 sse.js/learn.js，改动后用户不硬刷新就还是旧逻辑；
    曾导致「流事件已返回但界面一直转圈」的假故障。内容变了 URL 就变。
    """
    import hashlib
    import re

    def repl(m):
        attr, name = m.group(1), m.group(2)
        if "://" in name or name.startswith("data:"):
            return m.group(0)
        path = OUT / name.split("?")[0]
        if not path.exists():
            return m.group(0)
        h = hashlib.md5(path.read_bytes()).hexdigest()[:10]
        return '%s="%s?v=%s"' % (attr, name, h)

    return re.sub(r'(src|href)="([^"]+\.(?:js|css))"', repl, html)


def copy_app():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in APP_FILES:
        shutil.copy2(SRC / name, OUT / name)
    # app.html = 唯一对外应用入口；index.html = 产品首页（由 write_homepage 生成）
    shutil.copy2(SRC / "index.html", OUT / "app.html")
    (OUT / "app.html").write_text(
        stamp_assets((OUT / "app.html").read_text(encoding="utf8")), encoding="utf8")
    # 首页 3D 人体模型：three.js 运行时 + BodyParts3D 网格
    for sub in ("vendor", "models"):
        src = SRC / sub
        if src.exists():
            shutil.copytree(src, OUT / sub, dirs_exist_ok=True)


def write_entries():
    """固定角色/设备的入口只留给开发者，统一放到 dev/ 子目录。"""
    dev = OUT / "dev"
    dev.mkdir(parents=True, exist_ok=True)
    # 对外只保留 app.html 与 index.html；清掉历史构建留在根目录的固定入口
    for stale in OUT.glob("*.html"):
        if stale.name not in ("app.html", "index.html"):
            stale.unlink()
    for label, key, filename, desc, group in VERSIONS:
        if filename == "app.html":
            continue
        role, device = key.split("+")
        role_q = "" if role == "desktop" else f"role={role}&"
        target = f"../app.html?{role_q}device={device}"
        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{label} · 影知（开发者入口）</title>
<style>html,body{{height:100%;margin:0;background:#0b1c24;color:#dff3ef;font-family:-apple-system,"PingFang SC",sans-serif;display:grid;place-items:center}}
.box{{text-align:center}}.mark{{width:54px;height:54px;border-radius:16px;background:#0e7c7b;display:grid;place-items:center;font-size:24px;margin:0 auto 12px}}
a{{color:#8fe3d6}}</style></head>
<body><div class="box"><div class="mark">影</div><p>正在进入 {label}…</p><p><a href="{target}">如果没有自动跳转，点这里</a></p></div>
<script>location.replace("{target}");</script></body></html>"""
        (dev / filename).write_text(html, encoding="utf8")
    for label, href, filename in [
        ("桌面端", "../app.html?device=desktop", "desktop.html"),
        ("移动端", "../app.html?device=mobile", "mobile.html"),
    ]:
        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{label} · 影知（开发者入口）</title>
<style>html,body{{height:100%;margin:0;background:#0b1c24;color:#dff3ef;font-family:-apple-system,"PingFang SC",sans-serif;display:grid;place-items:center}}
.box{{text-align:center}}.mark{{width:54px;height:54px;border-radius:16px;background:#0e7c7b;display:grid;place-items:center;font-size:24px;margin:0 auto 12px}}
a{{color:#8fe3d6}}</style></head>
<body><div class="box"><div class="mark">影</div><p>正在进入 {label}…</p><p><a href="{href}">如果没有自动跳转，点这里</a></p></div>
<script>location.replace("{href}");</script></body></html>"""
        (dev / filename).write_text(html, encoding="utf8")


def write_homepage():
    """index.html = 产品首页（对外唯一门面）。

    首页职责：定位、人体部位入口、四链条、三端入口、能力边界。
    人体模型通过 body-model.js 挂载，3D 适配器未接入时用 SVG 占位并如实标注。
    """
    data = json.loads((OUT / "data" / "kb.json").read_text(encoding="utf8"))
    c = data["meta"]["counts"]

    chains = [
        ("01", "基础知识问答", "征象是什么、怎么看、容易错在哪；每条解释都能回到出处。"),
        ("02", "临床知识迁移", "换模态、换部位、换病种，同一征象的判断会不会跟着变。"),
        ("03", "真实病例演练", "定位、描述、征象、依据四步，按步计分，结果可回放。"),
        ("04", "真实场景应用", "实习任务、班级讲评、病例工作台与交班摘要。"),
    ]
    chain_html = "".join(
        f'<div class="chain"><span class="no">{no}</span><b>{title}</b><p>{desc}</p></div>'
        for no, title, desc in chains
    )

    roles = [
        ("s", "学生", "医学生 / 规培生", "从术语到病例，按四链条建立可追溯的影像思维。",
         "app.html?role=student", "以学生身份进入"),
        ("t", "教师", "课程教师 / 带教老师", "用同一套病例与错题数据备课、布置、讲评。",
         "app.html?role=teacher", "以教师身份进入"),
        ("d", "医生", "影像科医生 / 临床带教", "把可追溯的影像证据带进读片、交班与带教。",
         "app.html?role=doctor", "以医生身份进入"),
    ]
    role_html = "".join(
        f'<div class="role-card {k}"><b>{name}端</b>'
        f'<p style="margin:0;font-size:11.5px;color:var(--faint)">{full}</p>'
        f'<p>{desc}</p><a class="btn" href="{href}">{cta}</a></div>'
        for k, name, full, desc, href, cta in roles
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b4f55">
<title>影知 · 影像临床思维平台</title>
<meta name="description" content="输入影像与报告/指南文档，回答同时引用影像区域与文献段落；证据不足时诚实拒答，并固定声明非诊断用途。">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%230b4f55'/%3E%3Ctext x='32' y='44' font-size='36' text-anchor='middle' fill='white' font-family='sans-serif'%3E影%3C/text%3E%3C/svg%3E">
<link rel="stylesheet" href="landing.css">
<script type="importmap">{{"imports":{{"three":"./vendor/three.module.js"}}}}</script>
</head>
<body>

<header class="ld-top">
  <div class="ld-brand">
    <div class="ld-mark">影</div>
    <div><b>影知</b><span>YINGZHI · 影像临床思维平台</span></div>
  </div>
  <nav class="ld-nav">
    <a href="#core">核心问答</a>
    <a href="#body">按部位进入</a>
    <a href="#chains">四链条</a>
    <a href="#boundary">能力边界</a>
  </nav>
  <div class="ld-cta">
    <a class="btn primary" href="app.html#/ask">进入问答</a>
  </div>
</header>

<div class="wrap">

  <section class="hero">
    <div class="eyebrow">赛道 B · 医学影像知识问答 · 核心功能</div>
    <h1>影像给区域，文献给段落；<br>不确定就明说。</h1>
    <p>输入一张影像与一段报告/指南文字，回答必须同时引用「图上哪一块」与「哪份文献哪一段」。
       缺影像侧或文献侧就降级，越出教学范围就拒答，所有输出固定声明非诊断用途。</p>
    <div class="flow">
      <span>① 影像区域引用</span><span>② 文献段落引用</span>
      <span>③ 不确定就拒答</span><span>④ 非诊断用途</span>
    </div>
    <div class="acts">
      <a class="btn primary lg" href="app.html#/ask">进入多模态问答</a>
      <a class="btn lg" href="#core">看一次回答怎么组成</a>
      <a class="btn lg" href="app.html">进入系统</a>
    </div>
  </section>

  <div class="sec-h" id="core">
    <h2>核心功能：一次问答的四个硬约束</h2>
    <p>不是「答得像」，而是「答得出处」：每条结论都要能回到影像上的一块区域和文献里的一段原文。</p>
  </div>
  <div class="core-grid">
    <div class="core-copy">
      <div class="core-item"><span>01</span><b>影像区域引用</b><p>分区 id、bbox、atlas 与标注人一起返回；点引用可在影像上定位，左右侧规则显式写出。</p></div>
      <div class="core-item"><span>02</span><b>文献段落引用</b><p>指南条款原文、版本、条款定位与官方入口；摘录带 hash 可回查，词条释义与指南条款分开标注。</p></div>
      <div class="core-item"><span>03</span><b>不确定就拒答</b><p>缺分区、缺条款、缺尺寸、征象并列、左右冲突、越界诊断，都会给出具体原因，不拼凑答案。</p></div>
      <div class="core-item"><span>04</span><b>非诊断用途</b><p>固定声明常驻；只做影像表现与文献条款的对照，不输出诊断、治疗或预后判断。</p></div>
    </div>
    <div class="core-demo">
      <div class="cd-h"><span>示例回答</span><span class="cd-badge">可答 · 双引用齐全</span></div>
      <div class="cd-q">问：右肺中野有没有结节？</div>
      <p class="cd-a">在「正常后前位胸片」的「右肺中野」内，库内结论原文为：右肺中野透亮度均匀，未见明确局灶性密度增高、结节或空洞影。</p>
      <div class="cd-cite spatial"><b>影像引用</b><span>REG-001-RML · 右肺中野</span><em>bbox [0.12, 0.35, 0.36, 0.23] · ATLAS-CHEST-PA-6</em></div>
      <div class="cd-cite doc"><b>文献引用</b><span>ACR Lung-RADS 2019 · 类别 1</span><em>“未见肺结节或仅见良性表现者，按年度低剂量 CT 继续筛查。”</em></div>
      <div class="cd-gate"><span class="ok">可答</span><span class="warn">降级</span><span class="bad">拒答</span><em>三种状态由覆盖检查算出</em></div>
    </div>
  </div>

  <div class="sec-h" id="body">
    <h2>从人体部位进入</h2>
    <p>点选部位查看该分区在知识库中的真实词条与病例。模型层已抽象为可替换接口，
       3D 适配器接入后无需改动本页其余部分。</p>
  </div>
  <div class="body-grid">
    <div class="body-card">
      <div class="body-card-h">
        <b>人体部位</b>
        <span class="bm-status" id="bmStatus">模型加载中…</span>
      </div>
      <div id="bmHost"></div>
    </div>
    <div class="body-panel" id="bmPanel"></div>
  </div>
  <div class="stat-strip" id="statRow"></div>

  <div class="sec-h" id="chains">
    <h2>四链条</h2>
    <p>同一组能力，在三种角色下换任务说法与完成口径，不复制业务逻辑。</p>
  </div>
  <div class="chain-grid">{chain_html}</div>

  <div class="sec-h" id="roles">
    <h2>三端入口</h2>
    <p>一个应用入口，角色在界面内切换；桌面与移动共用一套代码。</p>
  </div>
  <div class="role-grid">{role_html}</div>

  <div class="sec-h" id="boundary">
    <h2>能力边界</h2>
  </div>
  <div class="note-box">
    <b>能当场证明：</b>问答由本地规则引擎在已核验的知识库上生成；影像引用带分区 id、bbox、atlas 与标注人，
    文献引用带条款原文、版本、条款定位与官方入口；缺任一侧即拒答或降级；8 项诚实性自检可在页面内当场重跑。<br>
    <b>还没做到：</b>不做病灶检测与分割；不做语义向量检索（当前为词条/别名/关键词匹配）；
    不接大模型自由生成（避免编造引用）；不做诊断、治疗或预后判断。<br>
    <b>用途声明：</b>仅用于医学影像教学与研究，不构成诊断意见，不替代临床决策。
    病例影像仅使用 CC0 / CC BY / CC BY-SA / 公有领域公开影像，分区框为人工标注解剖区，不是病灶分割。
  </div>

  <details class="dev">
    <summary>开发者入口（固定角色 / 设备，评审对照用）</summary>
    <div class="dev-list">
      <a href="dev/student.html">学生 · 桌面</a>
      <a href="dev/student-mobile.html">学生 · 移动</a>
      <a href="dev/teacher.html">教师 · 桌面</a>
      <a href="dev/teacher-mobile.html">教师 · 移动</a>
      <a href="dev/doctor.html">医生 · 桌面</a>
      <a href="dev/doctor-mobile.html">医生 · 移动</a>
      <a href="dev/desktop.html">仅桌面</a>
      <a href="dev/mobile.html">仅移动</a>
    </div>
  </details>

  <div class="foot">
    <span>知识底座：征象 {c['signs']} · 指南条款 {c['guidelines']} · 公开病例 {c['cases']} · 解剖分区 {c['regions']}</span>
    <span>核心问答在本地规则引擎上运行 · 每条回答可回查影像区域与文献段落</span>
  </div>
</div>

<script src="data/kb.js"></script>
<script src="body-model.js"></script>
<script src="body-3d.js"></script>
<script src="landing.js"></script>
</body>
</html>"""
    (OUT / "index.html").write_text(stamp_assets(html), encoding="utf8")


def write_readme():
    text = """# 影知 · 影像临床思维平台（演示包）

**核心功能：多模态知识库问答。** 输入影像与报告/指南文档，回答同时引用影像区域与文献段落；
证据不足时降级或拒答，并固定声明非诊断用途。

一套知识底座 + 一套交互引擎。对外是「产品首页 + 应用主入口」两个页面，
角色（学生/教师/医生）与设备（桌面/移动）都在应用内切换，不复制业务逻辑。

## 运行

```bash
# 在 outputs/medtrain 目录下
python3 -m http.server 8080
# 打开 http://127.0.0.1:8080/
```

首页的人体模型是 BodyParts3D 三维网格，通过 ES module 与 fetch 载入，**必须用本地服务器打开**。
若用 `file://` 直接双击，浏览器会拦截模块加载，3D 自动回落为可点击的 SVG 部位图（功能不中断）。

## 入口

对外只有两个页面：

| 入口 | 说明 |
| --- | --- |
| `index.html` | 产品首页：核心问答、人体部位入口、四链条、能力边界 |
| `app.html` | 应用主入口，默认进入「问 · 多模态问答」 |
| `app.html#/ask` | 直接进入核心问答工作台 |

固定角色/设备的入口只给开发者对照用，放在 `dev/`：`dev/student.html`、`dev/student-mobile.html`、
`dev/teacher.html`、`dev/teacher-mobile.html`、`dev/doctor.html`、`dev/doctor-mobile.html`、
`dev/desktop.html`、`dev/mobile.html`。

## 核心功能：多模态问答

三栏工作台：左侧输入影像 + 报告/指南，中间影像与人工分区，右侧回答与双引用。

| 状态 | 触发条件 | 界面表现 |
| --- | --- | --- |
| 可答 | 影像区域 + 指南条款都命中 | 绿色；影像引用卡 + 文献引用卡 |
| 部分可答 | 文献侧降级为词条释义、条款并列、缺尺寸、左右冲突 | 琥珀色；逐条列出降级原因 |
| 拒答 | 缺分区、缺结论、缺文献、输入未命中词条、诊断/治疗越界、上传影像未标注 | 红色；给出具体原因与可改问法 |

页面内「诚实性自检」用 8 个固定输入验证：该答的答、该拒的拒，可当场重跑。

## 四链条

| 链条 | 学生 | 教师 | 医生 |
| --- | --- | --- | --- |
| 01 基础知识问答 | 学词条、收藏、看易错点 | 按部位/模态/条款备课 | 读片前速查 |
| 02 临床知识迁移 | 迁移卡、对照近邻 | 设计迁移任务 | 跨场景鉴别 |
| 03 真实病例演练 | 四步计分、错题本 | 组卷、预览、投屏 | 四步读片、回工作台 |
| 04 真实场景应用 | 实习任务、学习报告 | 班级、作业、讲评 | 工作台、审计、交班 |

医生端病例工作台的分区框只标编号（①②③…），分区名与结论条数在图例里；
右上角「隐藏分区」可一键去掉框只看影像，图例仍可按名称选分区。

### 题库

| 题库 | 数量 | 说明 |
| --- | --- | --- |
| 病例演练 | 29 例 | 定位—描述—征象—依据四步，按步计分 |
| 考点练习 | 179 题 | 定义辨析 60 / 检查选择 60 / 易错辨析 59，覆盖全部 60 个征象 |

题型参考影像学考试常见考法，题目内容全部来自知识库原文，判分按知识库标注，不是考试真题。
每题挂载该征象的易错点，答后展示；错题在题库首页聚合为「高频易错点」。
详见 [题库设计与易错点](../docs/题库设计与易错点.md)。

## 验收

```bash
# 终端 1
cd outputs/medtrain && python3 -m http.server 8800
# 终端 2
python3 medtrain/tests/ui_check.py
```

覆盖产品首页与人体部位交互、9 个入口、三角色四链条、医生演练、核验记录、工作台分区标注、
教师跳转、移动端角色切换、考点练习与易错点、「未提问时无假回执」，以及核心问答的双引用、
拒答、降级、hash 校验拦截、人工图文锚点与 8 项诚实性自检；共 118 项检查。

```bash
YZ_BASE=http://127.0.0.1:8080/ python3 medtrain/tests/ui_check.py
```

## 重新构建

```bash
python3 medtrain/build_data.py   # 读取 kb/，生成 data/kb.js 与压缩影像
python3 medtrain/build.py        # 复制前端，生成版本入口与启动页
```

## 数据

- 征象 60 / 指南条款 47 / 公开病例 120 / 解剖分区 596 / 双引用结论 582 / 可练题目 29。
- 病例影像仅使用 CC0 / CC BY / CC BY-SA / 公有领域公开影像；分区框为人工标注解剖区，不是病灶分割。
- 仅用于医学影像教学与研究，不构成诊断意见，不替代临床决策。
"""
    (OUT / "README.md").write_text(text, encoding="utf8")


def build_reading():
    """阅片工作台：导出静态 JSON + 打包 kb/app 到 read/（纯静态可托管）。"""
    for script in ("kb/scripts/export_teach_static.py", "kb/scripts/build_teach_pages.py"):
        subprocess.run([sys.executable, str(ROOT / script)], check=True, cwd=str(ROOT))


def main():
    copy_app()
    write_entries()
    write_homepage()
    write_readme()
    build_reading()
    print("built", OUT)
    for p in sorted(OUT.glob("*.html")):
        print(" ", p.name)


if __name__ == "__main__":
    main()
