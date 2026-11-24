# 影像征象与指南双线知识库（KB）

面向影像教学与相似征象关联的本地知识库：**描述性解释 + 指南条款对照 + 公开影像**，
不做自动判读，不输出临床结论。

> **内容来源声明**：开发者不具备医学专业资质，**分区并未进行人工标注**。分区范围按公开解剖分区规范与文献描述确定，逐区文本由文献资料 + AI 辅助整理并做一致性核查；截至当前版本，**尚未经影像科医师逐例复核**。文中出现的「人工锚点 / 人工标注」仅指早期 v1 少量示例，不代表整体库已人工标注或已通过专家复核。专家复核影像已列入未来优化方向。

## 能力

| 能力 | 实现 |
| --- | --- |
| 征象检索 | 60 条中文征象词条，BM25 + 2-gram 分词 + 同义词扩展 |
| 指南条款库 | 47 条条款，含适用条件、条款方向、版本与官方入口 |
| 双线判断 | 影像线与指南线分别召回，输出对齐结论与缺失条件 |
| 相似征象关联 | 按标签、部位、模态共现排序 |
| 两级分类 | 一级按解剖部位（5 个），二级按病症/征象族（12 个），影像组只归属一个部位 |
| 相似病例/影像关联 | 32 张公开许可影像，按两级分类归并，同类内并排对照 |
| 在线相似检索 | 预留 provider 接口：Commons / Open-i / PubMed / TCIA，只读、只返回链接 |
| 公开标准对照 | 10 个分类系统的维度摘要与官方入口 |
| 图像对照 | 按「部位 → 病症」逐级浏览；本地图像仅并排预览，不上传不分析 |
| 征象图文关联 | 12 条人工锚点，把征象文字片段与影像区域双向绑定；点文字高亮框，点框回到文字 |
| 合规门禁 | 来源、许可白名单、隐私词、越界表述、署名覆盖、条款完整性 |
| 区域定位工作台 v1.1 | 独立服务 + 三面板工作台：32 例队列、2 套 atlas、21 个分区、7 条双引用结论；框选→分区→带锚点结论 |
| 规模化语料 v2.0 | **120 例 / 596 分区 / 582 条结论 / 19 套体位模板**；模板化生成，保留 3 例人工标注 |
| 双场景界面 v2.0 | **教学版** `/teach`：章节树 + 讲解卡 + 自测；**临床版** `/clinic`：队列表格 + 框选定位 + 证据/审计 |

## 双线判断的四种结果

| 结果 | 含义 | 界面表现 |
| --- | --- | --- |
| `aligned` | 影像线覆盖条款全部适用条件 | 绿色：列出已覆盖条件与条款方向 |
| `partial` | 缺关键条件（分类等级、尺寸等） | 琥珀色：列出待补充条件，不推断 |
| `insufficient` | 任一线未命中，或条款仅字面相近 | 红色：明确说明无法对照 |
| `divergent` | 同分类下条款方向不一致 | 并列展示，不作裁决 |

> 判断的是「库内证据是否对齐」，不是病情。条款方向只作原文摘录，不转述为建议。

## 目录

```
kb/
├── data/            signs / standards / guidelines / cases / groups / taxonomy / sources / sign_links
├── images/          公开影像（120 张有引用；另有少量采集残留未引用）
├── licenses/        ATTRIBUTION.md 署名与排除记录
├── index/           检索索引与合规报告（构建产物）
├── scripts/         kbsearch / dual / sign_links / online_search / serve / compliance_check / build_* / export_* / fetch_* / merge_corpus
├── tests/           69 项检索、双线、分类、图文关联、区域定位、在线接口与合规测试
└── web/             单页演示界面（征象检索 / 图文对照 / 双线判断 / 图像对照 / 区域定位模板）
```

## 命令

```bash
cd kb
python3 scripts/kbsearch.py build                 # 建索引
python3 scripts/sign_links.py                     # 校验征象图文关联
python3 scripts/kbsearch.py 磨玻璃影               # 命令行检索
python3 scripts/serve.py --port 4180              # 演示服务
python3 scripts/compliance_check.py               # 合规门禁
python3 -m unittest discover -s tests -t . -v     # 测试
python3 scripts/export_kb.py                      # 导出 DeepWorks 导入包
python3 scripts/export_demo.py                    # 生成离线单文件演示页
python3 scripts/build_sign_image_demo.py          # 生成离线图文对照页
python3 scripts/serve_region.py --port 4191       # v2.0 服务：/ 场景选择，/teach 教学，/clinic 临床
python3 scripts/fetch_corpus.py                   # 采集公开影像（1000px，许可过滤）
python3 scripts/merge_corpus.py                   # 合并候选、去重、均衡选 88 张
python3 scripts/build_corpus_120.py               # 生成 120 例分区与双引用（可重入）
python3 -m unittest tests.test_region_api -v      # 工作台后端测试（25 项）
python3 scripts/build_region_demo.py              # 构建 v1.0 单文件演示页
jsc tests/test_region_demo.js                     # v1.0 演示页自检（17 项）
python3 scripts/online_search.py "thyroid nodule" # 试调用在线相似检索
```

## 两级分类

一级为解剖部位，二级为病症/征象族；每个影像组只归属一个部位，不重复计数。
定义在 `data/taxonomy.json`，影像组在 `data/groups.jsonl`（含 `region_id` 与 `search_query`）。

| 一级（部位） | 二级（病症分类） | 张数 |
| --- | --- | --- |
| 胸部（18） | 肺部实变与气腔影 | 5 |
| | 磨玻璃影与间质改变 | 2 |
| | 肺结节与肿块 | 2 |
| | 胸腔积液与气胸 | 3 |
| | 胸部 CT 窗位与层面 | 2 |
| | 正常胸部与解剖 | 4 |
| 头颈部（7） | 头颅出血、梗死与占位 | 3 |
| | 甲状腺结节 | 3 |
| | 正常头颅 | 1 |
| 乳腺（6） | 乳腺钙化与肿块 | 6 |
| 腹部（1） | 腹部实质脏器 | 1 |
| 肌骨与脊柱（0） | 肌骨与脊柱 | 0（待补） |

归类依据写在每个影像组的 `criteria`：只按来源公开描述与图中标注归并，同类不代表同一疾病。

## 征象图文关联（v1）

把征象词条里的一句文字，锚定到公开影像上的一块区域；两边同时存在才进入页面。

```bash
python3 scripts/sign_links.py                     # 数据校验：文字锚点、bbox、侧别、来源
python3 scripts/build_sign_image_demo.py          # 生成 outputs/sign-image-demo.html
python3 scripts/serve.py --port 4180              # 在线界面 →「图文对照」
```

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/sign-index` | GET | 已关联征象清单与关联数 |
| `/api/sign/<id>` | GET | 单个征象的文字分段、关联影像、标注区域 |
| `/api/sign-links?sign=&image=` | GET | 按征象或影像筛选关联 |

数据在 `data/sign_links.jsonl`，字段与校验规则见 `docs/征象图文关联设计.md`。
v1 为 12 条关联、9 个征象、9 张影像、14 个区域，全部人工标注、单次复核；
框是教学标注区域，不是模型识别或病灶分割。

## 在线相似图像/病例接口（预留）

`scripts/online_search.py` 提供只读候选检索，界面与外部脚本共用同一入口：

```bash
python3 scripts/online_search.py "thyroid nodule"   # 命令行试调用
```

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/taxonomy` | GET | 一级部位 → 二级病症树，含每类张数与检索词 |
| `/api/groups?region=` | GET | 影像组（二级分类）与组内影像 |
| `/api/similar?q=&provider=&limit=` | GET | 在线候选，只返回链接与元数据 |
| `/api/similar/queue` | POST | 人工确认的候选写入 `_candidates/online_queue.jsonl` |

Provider 在 `PROVIDERS` 注册，新增来源只加一个函数、不改对外接口：

| id | 来源 | 说明 |
| --- | --- | --- |
| `commons` | Wikimedia Commons | 影像 + 许可元数据，主力来源 |
| `openi` | Open-i 影像库 | 影像与公开说明 |
| `pubmed` | PubMed | 相似病例文献，非图像 |
| `tcia` | TCIA | 需 `TCIA_API_KEY`，未配置时显式返回 |

约束：

1. **只读**：不下载图像、不入库、不解析图像内容。
2. **许可前置**：仅 CC0 / 公有领域 / CC BY / CC BY-SA；NC、ND、未知许可标记为不可用。
3. **隐私标记**：标题或描述命中日期、编号、姓名缩写时提示人工核验。
4. **入库路径不变**：人工核验后走 `scripts/add_cases.py`。
5. **开关**：`KB_ONLINE_SEARCH=0` 关闭接口。

## 设计要点

1. **三库分离**：征象、指南、影像分开建库，避免条款与病例互相挤占召回位。
2. **条款级而非文档级**：指南按条款切片，保留适用条件、版本与方向，才能做双线对齐。
3. **对齐可解释**：每个判断都输出已覆盖条件、缺失条件与对应条款 id，不做黑箱打分。
4. **缺失即提示**：条件不足时明确说缺什么，不猜测、不补全。
5. **来源级引用**：不复制标准全文，只给维度摘要与入口链接；每条记录可回溯。
6. **隐私最小化**：不使用真实患者数据；公开影像逐张核验，排除人物照片与含年龄、日期的图像。
7. **分类可扩展**：新增影像只需给出 `region_id` 与 `search_query`，两级树与在线检索自动生效。

## 数据边界

- 征象条目与条款摘要为教学用途，措辞已保守化，不能替代教材与标准原文。
- 条款阈值与处理路径以官方当前版本为准；本库不对个体影像作出判断。
- 影像标签来自来源页公开描述，未经放射科医师逐例复核，仅作对照参考。
- 未覆盖的征象会明确返回「暂无依据」，不生成猜测内容。
- 图文关联的框为人工教学标注，未做双人 IoU 复核；超声与乳腺按 `local` 只给图像内相对位置。

## 许可

代码：随作品提交。数据：征象、标准与条款摘要为自写内容；影像按 `licenses/ATTRIBUTION.md` 的原许可使用。
