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
| `kb/data/` | 病例 200（可用 195，5 例停用）/ 分区 981 / 结论 967 / 段落 546 |
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

### 带模型问答（本地）

上传影像与模型问答需要两个进程：

```bash
# 1) 模型服务（配置见 docs/纯文本模型接入指南.md）
yingzhi/serve/start.sh                 # 默认 8800

# 2) 读片工作台 + 数据接口
python3 kb/scripts/serve_region.py --port 4191
# 打开 http://127.0.0.1:4191/clinic
```

`serve_region.py` 把 `/api/ask` 原样转发给 8800，所以前端只需同源访问 4191。
公网静态版没有模型服务，上传按钮会明确提示「请在本地运行后使用」，不会假装能用。

## 读片工作台（分区定位 + 双引用）

`read/clinic.html` 是命题要求的「输入影像 → 区域定位 → 文献溯源」入口：

1. 点工具栏「上传影像」，选一张片；
2. 在「问答」页输入问题；
3. 视觉模型给出候选框 → 前端 `locate` 匹配到已标注分区 → 右侧「证据」显示该分区的空间锚点与文献锚点。

三条硬规则：

- **只认库内影像**：上传图按 md5 与 `kb/images/` 精确比对。截图、转发压缩过的图匹配不上，
  系统会明说「该影像不在标注库内，未做区域定位」，不猜最像的一例。
- **框不准就不落分区**：候选框与任何分区的覆盖率不足 35%，或同时落在两个分区，
  系统返回「未覆盖」或「请缩小范围」，不下结论。
- **定位成功不等于有结论**：分区必须绑定了 claim 才显示证据，否则显示「该分区暂无绑定结论」。

定位算法自检：`python3 kb/scripts/selfcheck_locate.py` → `outputs/medtrain/locate_selfcheck.md`。
当前数字：981 个分区自命中 90.4%，跨区 8.6%，未命中 1.0%（全部是「边缘带」这类窄条分区）。
这是**算法下限**，不是端到端准确率——模型框准不准需真实 key 才能测。

## 数据构成

`kb/data/cases.jsonl` 共 200 条，其中 5 条 `status=inactive`（素材为检查场景照片或大体标本），
**可用 195 例**：

| 来源 | 数量 | 说明 |
| --- | --- | --- |
| 人工核验 | 45 | `human_verified_no_identifier` |
| 历史自动筛查 | 102 | `auto_screened` |
| 扩容新增 | 48 | 新影像，`auto_screened_pending_human`（**待人工核验**） |
| 分区聚焦视角 | 29 | 复用已有影像，`shared_image_of` 指向源病例 |

**195 例不是 195 张独立影像**：`kb/images/` 有 209 个文件，去重后 89 张唯一图像；
29 例为同图不同分区视角，其余为多例共用同一张图。详见
`docs/分片与200例扩容记录.md` 与 `docs/病例元数据体检.md`。

## 工程特性

- **分片加载**：首屏 `kb.js` 约 0.63 MB，按「部位 + 模态」拆 6 片，切病例时按需加载。
- **双引用**：影像分区锚点 + 文献段落锚点；摘录带 64 位 SHA-256 与 span，可回查。
- **诚实性**：证据不足降级/拒答；指南条款一律标「候选，适用性需人工判断」。
- **AI 只做预审**：审核签字责任由人承担，界面与文档均有声明。

## 许可

代码与文档：见仓库；影像：Wikimedia Commons 的 CC0 / CC BY / CC BY-SA / 公有领域，
逐张署名与许可见站点根目录 `ATTRIBUTION.md`（由 `kb/data/cases.jsonl` 自动生成）。
