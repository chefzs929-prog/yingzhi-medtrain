# 公开可用的人体全身模型与 X 光解剖结构图资源清单

> 面向本项目（影像征象 / 指南双线知识库 + 演示页）的素材选型。
> 核验时间：2026-11-15。标注「已核验」的条目均实际访问过页面或接口，并读取了许可声明原文。

## 0. 结论速览

| 档位 | 资源 | 为什么 |
| --- | --- | --- |
| **首选（可商用、可再分发）** | BodyParts3D 4.0 | 全身成年男性、器官级 3D、OBJ 格式、CC BY 4.0、体量可控（62–136 MB） |
| **首选（X 光标注图）** | Wikimedia Commons「正常解剖 X 线」分类 | 逐图 CC0 / CC BY / CC BY-SA，可署名后直接入库 |
| **可用但有限制** | Z-Anatomy | 可编辑、更精细，但是 CC BY-SA 4.0，衍生作品必须同许可 |
| **可用但体量大** | Visible Human Project | 公有领域、真实尸体切片 + CT + MRI，但 15–40 GB |
| **仅可引用、不可再分发** | Radiopaedia、e-Anatomy、BioDigital、Complete Anatomy | NC 或闭源，只能放链接 |

一句话：**要做可再分发的全身 3D，用 BodyParts3D；要补 X 光解剖标注图，用 Commons 的 normal anatomy 分类；要真实断层参考，用 Visible Human。**

---

## 1. 三维全身解剖模型

### 1.1 BodyParts3D 4.0 —— 首选

| 项 | 内容 |
| --- | --- |
| 内容 | 成年男性全身三维模型，按 FMA（Foundational Model of Anatomy）组织，可单独取器官 |
| 格式 | OBJ 网格（多边形简化率 99%），含 IS-A 与 PART-OF 两套器官树 |
| 体积 | PART-OF 树 62 MB / IS-A 树 136 MB；另有器官名与包含关系表（KB 级文本） |
| 许可 | **CC BY 4.0**（已核验，许可页更新于 2025-02-27） |
| 商用 | 允许，需署名 |
| 入口 | https://dbarchive.biosciencedbc.jp/en/bodyparts3d/desc.html |
| 下载 | https://dbarchive.biosciencedbc.jp/data/bodyparts3d/LATEST/partof_BP3D_4.0_obj_99.zip |
| 备注 | 旧站 `lifesciencedb.jp/bp3d` 已不稳定，直接走 dbarchive 更可靠 |

适合 three.js / model-viewer 直接加载，也适合做「点击器官 → 关联征象条目」的交互演示。
器官树文本（`partof_parts_list_e.txt`）可直接映射到知识库的部位字段。

### 1.2 Z-Anatomy

| 项 | 内容 |
| --- | --- |
| 内容 | 基于 BodyParts3D 人工修模的完整解剖模型，含肌肉、血管、神经、筋膜等分层 |
| 格式 | Blender 源工程 / Unity 应用；GitHub 仓库约 800 MB |
| 许可 | **CC BY-SA 4.0**（已核验仓库 LICENSE 原文） |
| 商用 | 允许，但衍生作品必须同样以 BY-SA 分发（有传染性） |
| 入口 | https://www.z-anatomy.com/ ・ https://github.com/LluisV/Z-Anatomy |
| 备注 | 官方 release 只有 Windows 安装包（v0.9.9.7.5，2022）；macOS 建议直接用 .blend 源文件 |

比 BodyParts3D 精细得多，适合做高质量渲染截图；但 **BY-SA 会传染**，若演示页要闭源分发，只用它出图并单独署名，不要把它当作模型资产打包。

### 1.3 Visible Human Project（NLM）

| 项 | 内容 |
| --- | --- |
| 内容 | 一男一女两具遗体：冷冻切片、CT、MRI，轴位 1 mm 间隔 |
| 规模 | 男性 1,871 层 / 约 15 GB；女性 5,189 层 / 约 40 GB |
| 许可 | **公有领域，2019 年起不再需要许可**（已核验官方页面原文） |
| 商用 | 允许，无署名义务（仍建议标注来源） |
| 入口 | https://www.nlm.nih.gov/research/visible/visible_human.html |
| 数据 | https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Male-Images/index.html |
| 备注 | 是「断层 + 重建」的黄金标准，不是现成 mesh；需要自己分割重建 |

若演示要做「X 光片 ↔ 断层 ↔ 3D」三者联动，这是唯一有真实解剖对应的公开数据源。

### 1.4 NIH 3D

- 12,000+ 生物医学 3D 资产，含解剖、器械、分子模型。
- **许可逐条不同**（多为 CC BY，也有 CC0），下载前必须看条目页的 license 字段。
- 入口：https://3d.nih.gov/discover
- 适合补充单器官或器械模型，不适合当作「一套完整全身模型」。

### 1.5 Open Anatomy Project（SPL / Brigham）

- 图谱级 3D 解剖集，偏神经与头颈。
- 入口：https://www.openanatomy.org/
- 许可按数据集标注（以站内为准），使用前逐项确认。

### 1.6 Gray's Anatomy 1918 图版（2D，公有领域）

- Commons 分类：https://commons.wikimedia.org/wiki/Category:Gray%27s_Anatomy_plates
- 1929 年前出版，已进入公有领域，可自由商用。
- 价值：经典解剖线稿，适合做「X 光片 ↔ 解剖示意图」并排对照的右侧图。

---

## 2. X 光下的解剖结构图

### 2.1 分类导航（Commons，许可最干净）

| 分类 | 用途 |
| --- | --- |
| [X-rays of normal anatomy](https://commons.wikimedia.org/wiki/Category:X-rays_of_normal_anatomy) | 总入口，按部位/年龄下钻 |
| [X-rays of normal chest](https://commons.wikimedia.org/wiki/Category:X-rays_of_normal_chest) | 正常胸片与胸部结构标注 |
| [X-rays of normal knees](https://commons.wikimedia.org/wiki/Category:X-rays_of_normal_knees) | 膝关节正侧位，含 `- Annotation` 标注版 |
| X-rays of normal shoulders / hands / wrists / ankles / feet | 其余肌骨部位 |
| X-rays of normal anatomy at 0–20 years | 儿童各年龄段正常片 |

### 2.2 胸部解剖标注图（逐图已核验许可）

| 文件 | 内容 | 许可 | 作者 |
| --- | --- | --- | --- |
| Mediastinal structures on chest X-ray, annotated.jpg | 纵隔结构叠加标注 | CC BY-SA 3.0 | Mikael Häggström |
| Aortopulmonary window.jpg | 主肺动脉窗定位 | CC BY-SA 3.0 | Mikael Häggström |
| Supraclavicular fossa on chest X-ray.jpg | 锁骨上窝 | CC BY-SA 3.0 | Mikael Häggström |
| Costodiaphragmatic recess.jpg | 肋膈隐窝 | CC BY-SA 3.0 | Mikael Häggström |
| Chest labeled.png | 胸片解剖标注 | CC BY-SA 3.0 | Chikumaya |
| Normal posteroanterior (PA) chest radiograph (X-ray).jpg | 正常后前位 | CC0 | Mikael Häggström |
| Normal lateral chest radiograph (X-ray).jpg | 正常侧位 | CC0 | Mikael Häggström |

这组图的共同点是**标注直接画在片上**，正好对应知识库「正常解剖对照」组想要的形态：一张片子讲清结构位置，而不是纯示意图。

### 2.3 肌骨与脊柱（补 `GRP-MSJ` 的空缺）

`kb/data/groups.jsonl` 里 `GRP-MSJ`（肌骨与脊柱）当前 0 张图。可直接取：

- `File:X-ray of a normal knee by anteroposterior projection.jpg`（正常膝正位）
- `Category:X-rays of normal knees` 下带 `- Annotation` 后缀的文件（解剖标注版）
- 同类：`X-rays of normal shoulders` / `hands` / `wrists` / `ankles` / `feet`

注意：部分文件名含年龄性别（如 `59M`），这是文件命名而非图像内容；入库时仍按现有规则检查图上是否叠加了姓名、日期、ID。

### 2.4 OpenStax《Anatomy and Physiology 2e》

- CC BY 4.0，整本可下载，含大量解剖图与部分 X 光/影像图。
- 入口：https://openstax.org/books/anatomy-and-physiology-2e/pages/1-introduction
- 适合做「教科书级解剖示意 + 影像对照」，但图注是英文，需要自己写中文标签。

### 2.5 Radiopaedia（仅可链接，不可再分发）

- 全球最大的放射学病例库，解剖与征象文章质量高，X 光解剖条目齐全。
- 许可默认 **CC BY-NC-SA**，商用需单独授权；站点有反爬挑战。
- 结论：**演示页里放跳转链接，不下载图片入库。**

---

## 3. 临床全身影像数据集（若要训练或评测）

| 数据集 | 内容 | 许可 | 状态 |
| --- | --- | --- | --- |
| TotalSegmentator | 1,204 例 CT，104 个解剖结构分割 | CC BY 4.0（DOI 10.5281/zenodo.6802614） | 已核验 |
| AMOS22 | 腹部多器官 CT/MRI 分割基准 | CC BY 4.0（DOI 10.5281/zenodo.7155725） | 已核验 |
| Visible Human | 全身断层 + CT + MRI | 公有领域 | 已核验 |
| XCAT phantom | 可配置全身数字体模 | 免费但需申请 | 未直接核验 |
| IT'IS Virtual Population | 高精度全身电磁/热学体模 | 需签许可协议 | 未直接核验 |

前三个可以直接用于「全身结构定位」的功能验证；后两个属于「需申请」，不要在未确认前写进方案。

---

## 4. 许可红线速查

| 许可 | 可商用 | 必须署名 | 衍生作品同许可 | 典型来源 |
| --- | --- | --- | --- | --- |
| CC0 / 公有领域 | 是 | 否 | 否 | VHP、Gray's 1918、部分 Commons 图 |
| CC BY | 是 | 是 | 否 | BodyParts3D、OpenStax、TotalSegmentator |
| CC BY-SA | 是 | 是 | **是** | Z-Anatomy、多数 Commons 标注图 |
| CC BY-NC-SA | **否** | 是 | 是 | Radiopaedia |
| 闭源商业 | 否 | — | — | e-Anatomy、BioDigital、Complete Anatomy |

三条实操规则：

1. **BY-SA 有传染性**。演示页若打包了 BY-SA 模型，整个页面就得按 BY-SA 开放。只想用图不想开源，就只截静态图并单独署名。
2. **署名要写「改了没有」**。CC BY 4.0 要求标明是否修改，缩略图裁剪也算修改。
3. **VHP 是遗体捐献**，公有领域不等于可以配「真实患者病例」的叙事，措辞上仍按教学素材处理。

---

## 5. 落到本项目的建议

1. **补 `GRP-MSJ`**：从 Commons 正常膝/肩/腕/踝分类取 6–8 张，优先带 `- Annotation` 的版本，走现有 `licenses/ATTRIBUTION.md` 流程。
2. **扩 `GRP-NORMAL-CHEST`**：现有 5 张偏「正常片」，可再加主肺动脉窗、肋膈隐窝、锁骨上窝 3 张结构标注图，形成「一个结构一张片」的对照序列。
3. **演示页 3D 交互**：用 BodyParts3D 的 `partof_BP3D_4.0_obj_99.zip`（62 MB），按器官树拆分加载，点击器官跳转到对应征象条目。体积可控，许可也最宽松。
4. **不要做的事**：不要把 Radiopaedia 的图下载入库；不要把 Z-Anatomy 的 .blend 打进闭源分发包；不要用 e-Anatomy 的截图当自有素材。

### 署名模板（可直接抄进 ATTRIBUTION.md）

```text
BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International
https://dbarchive.biosciencedbc.jp/en/bodyparts3d/desc.html

Z-Anatomy — Lluís Vinent Juanico, CC BY-SA 4.0
https://github.com/LluisV/Z-Anatomy

Visible Human Project — U.S. National Library of Medicine, public domain
https://www.nlm.nih.gov/research/visible/visible_human.html

Mediastinal structures on chest X-ray, annotated — Mikael Häggström, CC BY-SA 3.0
https://commons.wikimedia.org/wiki/File:Mediastinal_structures_on_chest_X-ray,_annotated.jpg
```

---

## 6. 核验记录

| 检查项 | 结果 |
| --- | --- |
| BodyParts3D 许可页 | CC BY 4.0，2025-02-27 更新 |
| BodyParts3D OBJ 下载 | HTTP 200，可访问 |
| Z-Anatomy LICENSE | CC BY-SA 4.0 全文 |
| Z-Anatomy release | 仅 Windows exe/msi，v0.9.9.7.5 |
| VHP 官方页 | 「2019 年起不再需要许可」，公有领域 |
| VHP 数据入口 | HTTP 200 |
| Commons normal anatomy 分类 | 存在，含 30+ 子分类 |
| Commons 胸部标注图 3 张 | 均 CC BY-SA 3.0，作者已记录 |
| TotalSegmentator / AMOS22 | Zenodo API 返回 cc-by-4.0 |
| Radiopaedia | 反爬挑战拦截，许可按官方 licence 页记载为 NC |
| Open Anatomy / NIH 3D / OpenStax | HTTP 200，许可需逐条确认 |
