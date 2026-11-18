# 影知 · 影像临床思维平台

面向医学影像教学的多模态知识库问答演示系统。输入影像与报告/指南文档，回答同时引用
**影像分区**与**文献段落**；证据不足时降级或拒答，并固定声明非诊断用途。

> **定位**：教学与研究演示，**不构成诊断**、不提供治疗建议、不做分期。
> 正式教学或对外发布前，须由医学人员逐条审核签字。

## 线上站点

GitHub Pages：`https://chefzs929-prog.github.io/yingzhi-medtrain/`

站点由 `gh-pages` 分支托管，内容等于 `outputs/medtrain/` 的构建产物。

## 目录

| 路径 | 说明 |
| --- | --- |
| `medtrain/app/` | 前端源码（问、学、迁、练、用五条链路） |
| `medtrain/build.py` | 打包 `app/` → `outputs/medtrain/`，给静态资源加内容哈希 |
| `medtrain/build_data.py` | 知识库 JSONL → `data/kb.js` + 6 个 `kb.part.*.js` 分片 |
| `kb/data/` | 病例 200 / 分区 981 / 结论 967 / 段落 546 |
| `kb/images/` | 影像文件（Wikimedia Commons，许可见 `ATTRIBUTION.md`） |
| `kb/scripts/` | 内容重建、扩容、分区服务与自检脚本 |
| `docs/` | 评估与实现记录（分区、扩容、AI 预审、内容重建 v2、分片） |
| `outputs/precision-eval/` | 探针脚本与抽样产物 |

## 本地运行

```bash
python3 medtrain/build_data.py      # 生成 data/kb.js 与分片
python3 medtrain/build.py           # 生成 app.html / index.html
python3 -m http.server 8080 --directory outputs/medtrain
# 打开 http://127.0.0.1:8080/
```

首页 3D 人体模型通过 ES module 与 fetch 载入，必须用本地服务器；`file://` 直开时自动回落为 SVG 部位图。

## 数据构成（200 例）

| 来源 | 数量 | 说明 |
| --- | --- | --- |
| 人工核验 | 32 | `human_verified_no_identifier` |
| 历史自动筛查 | 88 | `auto_screened` |
| 扩容新增 | 51 | 新影像，`auto_screened_pending_human`（**待人工核验**） |
| 分区聚焦视角 | 29 | 复用已有影像，`shared_image_of` 指向源病例 |

**200 例不是 200 张独立影像**：51 张为新图，29 例为同图不同分区视角。详见
`docs/分片与200例扩容记录.md`。

## 工程特性

- **分片加载**：首屏 `kb.js` 约 0.63 MB，按「部位 + 模态」拆 6 片，切病例时按需加载。
- **双引用**：影像分区锚点 + 文献段落锚点；摘录带 64 位 SHA-256 与 span，可回查。
- **诚实性**：证据不足降级/拒答；指南条款一律标「候选，适用性需人工判断」。
- **AI 只做预审**：审核签字责任由人承担，界面与文档均有声明。

## 许可

代码与文档：见仓库；影像：Wikimedia Commons 的 CC0 / CC BY / CC BY-SA / 公有领域，
逐张署名与许可见站点根目录 `ATTRIBUTION.md`（由 `kb/data/cases.jsonl` 自动生成）。
