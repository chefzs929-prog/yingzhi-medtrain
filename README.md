# RadioCheck · 胸片阅片

> v7.0（2026-11-20）· 全站收缩版
>
> 对外只保留**一个首页 + 一个胸片阅片工作台**。旧的多角色 SPA、人体 3D、分区图谱、
> 组卷自测、报告对照全部退出对外入口，只保留跳转，避免旧链接 404。

**定位**：医学影像教学与研究演示，**不构成诊断**，不提供治疗建议，不做分期。
正式教学或对外发布前，逐区文本须由医学人员逐条审核签字。

## 现在只有两个页面

| 入口 | 说明 |
| --- | --- |
| `index.html` | 唯一门面：一句话定位、四种状态、能力边界 |
| `read/clinic.html` | 唯一功能页：21 例 CR 胸部逐区阅片 |

旧入口 `app.html`、`read/index.html`、`read/teach.html`、`read/paper.html`、
`read/compare.html`、`dev/*.html` 都已改为跳转到 `read/clinic.html`。

## 主链路

1. 左侧选一例（21 例，可按正常 / 气腔影 / 气胸 / 积液 / 结核 / 结节筛选）；
2. 点影像上的教学分区（PA 8 区、LAT 3 区），或拖框；
3. 右栏给出该区独立所见、状态与依据；
4. 「生成阅片记录」导出系统所见 + 分区所见 + 出处 + 非诊断声明。

纯静态：上传按 SHA-256 精确匹配库内影像，未入库明确拒绝；页面不调用大模型。

## 为什么收缩

- 原来有 7 个入口、3 种角色、4 条链条、120 例跨部位病例，评委找不到主功能。
- 原来的分区结论是病例级一句话复制到所有区；CASE-006 五个区同句，CASE-036 写“健康男性”但图注是气胸。
- 静态版的上传和问答依赖后端，部署到 GitHub Pages 只能看到壳。
- 现在只保证胸片 CR：23 例中 21 例进入队列，CASE-019 多图拼接、CASE-201 双幅对照移出。

## 四种状态

| 状态 | 含义 | 界面 |
| --- | --- | --- |
| `abnormal` | 公开来源/图注明确描述异常 | 琥珀色 |
| `normal` | 公开来源明确为正常，或正常病例的解剖对照 | 青绿色 |
| `unmentioned` | 公开来源没有逐区描述 | 灰色虚线，写“不作推断” |
| `limited` | 投照条件/图像质量导致判读受限 | 蓝色 |

`unmentioned` 绝不渲染成 `normal`。

## 在线入口

- 在线版：<https://chefzs929-prog.github.io/yingzhi-medtrain/>（gh-pages 分支，随构建更新）
- 桌面版：双击桌面上的 `RadioCheck.app`，内置本地静态服务，无需联网。

## 构建与运行

```bash
python3 medtrain/build.py
cd outputs/medtrain
python3 -m http.server 8080
# 打开 http://127.0.0.1:8080/
```

### 桌面应用（macOS）

```bash
bash desktop/build.sh        # 产物：outputs/desktop/RadioCheck.app / .dmg / -macOS.zip
open outputs/desktop/RadioCheck.app
```

`desktop/build.sh` 会先确保站点已构建，再用 Objective-C + WKWebView 编译原生壳，
并把 `outputs/medtrain` 整站打进 `RadioCheck.app/Contents/Resources/site`。
无原生壳时可用 `python3 desktop/start.py`（或双击 `desktop/start.command`）以浏览器打开。

`medtrain/build.py` 会依次生成胸片逐区数据、复制 5 个 clinic 资源、23 张胸片，
并写入首页、跳转页与 README。不再需要 `build_data.py` 或 3D 模型资源。

## 验收

```bash
python3 kb/scripts/selfcheck_chest_reading.py   # 数据规则 183 项
python3 medtrain/tests/chest_check.py           # 工作台端到端 35 项（需先起 8811 端口）
python3 medtrain/tests/site_check.py            # 全站收缩 18 项（同上）
```

- 数据自检：`outputs/medtrain/chest_selfcheck.md`
- 工作台端到端：`outputs/medtrain/chest_ui_check.md`
- 全站收缩：`outputs/medtrain/site_check.md`

覆盖 21 例逐例加载、分区数量、影像可读、局灶病例只有病灶区异常、气胸左右区分、
自然提问、越界拒答、阅片记录、库内上传命中、陌生上传拒绝、拖框命中、无 console error。

## 数据与许可

- 21 例 CR 胸部逐区校正；每例有独立分区状态、文本、依据与 SHA-256。
- 影像仅来自 Wikimedia Commons 的 CC0 / CC BY / CC BY-SA / 公有领域素材。
- 分区框为教学分区，不是病灶分割。
- 逐张署名与许可见 `outputs/medtrain/ATTRIBUTION.md`。

## 明确不做

- 非胸片泛化、DICOM、病灶检测与分割；
- 诊断、分期、治疗或预后判断；
- 静态页调用大模型；证据不足时降级或拒答，不编造引用；
- 多角色、多链条、组卷、报告对照等第二套功能。

## 文档

- [胸片阅片_重规划_2026-11-20.md](docs/胸片阅片_重规划_2026-11-20.md)
- [胸片阅片_验收_2026-11-20.md](docs/胸片阅片_验收_2026-11-20.md)
- [全站收缩_2026-11-20.md](docs/全站收缩_2026-11-20.md)
