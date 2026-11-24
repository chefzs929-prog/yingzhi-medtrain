# RadioCheck · 胸片阅片、病例题与课堂

> v10.3（2026-11-24）· 课堂数据多端同步（可选口令）+ 首页/Agent/对比三项反馈修复 + 隧道演示脚本
>
> 上一版 v10.2：课堂/对比回归修复 + 桌面新窗口打开 + 学生影像实验室
>
> 对外保留**一个首页 + 一个胸片阅片工作台 + 一组执业医师大纲病例题 + 一个对比阅片页 + 一个教师/学生课堂**。
> 学生端在课堂内新增**影像库问答、读片陪练、自测出题器、班级互助小组**。
> 旧的多角色 SPA、人体 3D、分区图谱、报告对照全部退出对外入口，只保留跳转，避免旧链接 404。

**定位**：医学影像教学与研究演示，**不构成诊断**，不提供治疗建议，不做分期。
正式教学或对外发布前，逐区文本与题目解析须由医学人员逐条审核签字。

## 六个页面

| 入口 | 说明 |
| --- | --- |
| `index.html` | 学习入口（移动端卡片布局）：按「课堂（教师 / 学生）」与「阅片学习（阅片 / 对比 / 病例题）」两条主路径分流，并写明能力边界。桌面端由 `read/clinic.html` 作为主工作台 |
| `read/clinic.html` | 阅片工作台：21 例 CR 胸部逐区阅片；支持课堂任务模式 |
| `read/exam.html` | 病例题：执业医师大纲胸部 10 例，主诉 + 查体 + 胸片，5 选 1 |
| `read/compare.html` | 对比阅片：任意两张影像拖到两侧，同高对齐 / 并排 / 叠加擦除 / 同步缩放 |
| `read/classroom.html` | 课堂：教师建班/布置作业/看学情/看小组论坛；学生加入/作答/问答/陪练/自测/互助小组 |
| `read/daily.html` | 今日查房：按日期确定性生成的每日教学卡（主题 + 区域框 + 逐字条款 + 对照 + 自测） |

旧入口 `app.html`、`read/index.html`、`read/teach.html`、`read/paper.html`、`dev/*.html`
都已改为跳转到 `read/clinic.html`。`read/compare.html` 不再是旧“报告—指南对照”，已重建为对比阅片。

## 病例题主链路

1. 左侧大纲列出 10 个胸部考点：正常、肺炎、浸润性肺结核、肺癌、气胸、胸腔积液、
   肋骨骨折、二尖瓣型 / 主动脉型 / 普大型心；
2. 每题先给主诉、现病史、既往史、查体与辅助检查，再看胸片；
3. 5 选 1，提交后给影像所见、阅片要点、易错点、考点与影像出处；
4. 答题卡记录在本机 `localStorage`，可只看错题、重做、清空；
5. 提交后可直接把当前病例送进对比阅片。

题目按公开大纲与公开例题的题型**自编**，不是官方真题原文；不复制受版权保护的题库。
大纲与考试形式来源见 [病例题文档](docs/执业医师胸片病例题_2026-11-22.md)。

## 对比阅片主链路

1. 底部胶片条拖动任意病例到左侧或右侧；也可以点卡片，再点“分配到左侧/右侧”；
2. **并排模式**：拖动中间分隔条改变两侧宽度；
3. **叠加擦除模式**：两张影像叠在同一画布，拖动中间手柄看同一位置的差异；
4. **同高对齐**：两侧按同一显示高度、同一水平中线排布，缩放与平移共用一套视图；双击复位；
5. 8 组预置鉴别卡：肺炎 vs 结核、肺炎 vs 肺癌、结核 vs 肺癌、气胸 vs 正常、
   积液 vs 肺炎、二尖瓣型 vs 主动脉型、主动脉型 vs 普大型、肋骨骨折 vs 正常；
6. 也可自由对比任意两例，页面给出各自诊断、关键征象、易错点与考点；
7. 底部区域高度与右侧鉴别区宽度都可拖拽调整（双击分隔条复位，布局记在本机），鉴别区也可一键「加宽 / 还原」。

两侧默认按**同高对齐**显示（同一显示高度、同一水平中线），缩放与平移共用一套视图，
可以对照同一高度的结构；页面**不做患者体位级的像素配准**，病灶大小仍以测量为准。

## 阅片主链路

1. 左侧选一例（21 例，可按正常 / 气腔影 / 气胸 / 积液 / 结核 / 结节筛选）；
2. 点影像上的教学分区（PA 8 区、LAT 3 区），或拖框；
3. 右栏给出该区独立所见、状态与依据；
4. 「生成阅片记录」导出系统所见 + 分区所见 + 出处 + 非诊断声明。

上传影像只做文件指纹匹配；未入库影像只给通用分区，不下结论。页面默认不调用大模型。

## 课堂主链路

1. **教师建班**：生成 6 位班级码，添加学生；
2. **布置作业**：从 21 例里选病例，设置截止日期、及格线、讲评提示；
3. **学生加入**：班级码 + 姓名，无需注册；
4. **考核模式**：病例标题、分区颜色、来源暂时隐藏；学生逐例完成三题——
   异常分区定位（40 分，可多选，按选全 / 漏选 / 错选计分）、分区状态判读（30 分）、征象多选（30 分）；
5. **提交解锁**：立即评分，解锁分区所见、系统阅片与出处对照；
6. **结果回流**：教师端看到提交率、均分、及格率、逐例定位/判读/征象得分率与错题；
7. **错题重练**：低于 80 分的病例进入学生错题本，可重做并保留历史。

**数据边界**：默认只存在当前浏览器的 `localStorage`；需要跨设备时，可启用同步服务（无账号，可选口令；服务端按 `code`/`name`/`id` 合并，不整体覆盖）：

```bash
# 方式一：独立同步服务（SQLite，适合纯课堂）
python3 kb/server/classroom_server.py --port 8820

# 方式二：主服务内置（站点与 /api 同源，适合隧道演示）
python3 yingzhi/serve/main.py --port 8800 --site outputs/medtrain
# 课堂数据落在 data/classroom.json（已在 .gitignore）
```

课堂页点「同步设置」，或带参数打开：

```
read/classroom.html?sync=http://127.0.0.1:8820
read/classroom.html?sync=http://127.0.0.1:8800&syncToken=<口令>
```

服务端设 `YZ_SYNC_TOKEN`（或 `--token`）后，读快照与合并都必须带口令（设置里写成 `地址#口令`）；两种启动方式（独立 `classroom_server.py` 与主服务 `main.py`）都支持。`/api/reset` 默认关闭，只有显式 `--allow-reset` 才开放，且同样需要口令。服务不可达时自动回退「本机模式」，不阻塞课堂。

删除会以墓碑（tombstone）同步：教师移除学生、删除作业/小组/帖子后，其他设备拉取时不会把它加回来。

评分只对照库内逐区标注，不评价临床诊断。

**质控复核**：课堂页头部“质控复核”进入 AI 预标注 + 专家复核台；AI 只用于筛冲突，专家结论优先。

## 今日查房主链路

`read/daily.html` 每天给一条教学卡片：一个主题、一张片、一个区域框、一条逐字条款，外加一个易混淆对照与一道自测题。

- **按日期确定性生成**：算法只依赖 `kb/data/daily_src.json` 和浏览器本地日期，同一天在任何设备打开都是同一条；
- **不需要定时任务**：没有后台进程、不需要服务器开机、不会因为没人访问而停止；
- **前后端同源**：`kb/scripts/daily_brief.py` 与 `kb/app/daily-core.js` 是同一套规则，60 天逐日比对一致；
- **可回溯**：日期选择器可看过去或未来的任意一天该讲什么；
- **选材有依据**：只取条款与分区描述逐字对应（`relevance_score >= 2`）的条目，避免「讲 Kerley 线、引心胸比」这类错配。

## 学生影像实验室主链路

学生端 5 个页签：**我的作业 / 影像问答 / 读片陪练 / 自测出题 / 互助小组**。

### 1. 影像库问答（区域定位 + 文献溯源双引用）

1. 输入征象或疾病名（如气胸、实变、肺结核、肺水肿、肺结节随访）；
2. 先检索 `signs` / `concepts` / `guidelines`，再回到 21 例胸片的分区框；
3. 每条命中尽量给两条引用链，**没有可回溯原文时会明确标注，不静默省略、也不补造出处**：
   - **影像定位 E1**：病例 id + 分区名 + 状态 + 影像缩略图上的黄色区域框 + 影像许可；
   - **文献溯源 L1**：征象词条 id + 定义 + `sources` 里的来源标题与链接；命中指南时另给条款与适用条件；
   - 目前 314 条可答分区问中有 40 条（CASE-003/033/034/041/047 × 8 区）只有库内分区标注、没有指南原文，页面会显示“本条无原文锚点”；
4. 概念命中时区分“直接挂载”和“关联征象”，关联不当作原文依据；
5. “A 和 B 怎么区分”会并列两个库内征象，各给最多 2 个影像位置与鉴别点；
6. 未命中对应词条时直接用标准影像学知识作答，不编造 id，也不在正文里解释检索过程；
7. 影像卡可直接跳到 `clinic.html?case=CASE-xxx` 复核原图与分区。

### 2. 读片陪练

按“定位 → 判读 → 征象 → 对照”四步：

- 第 1 步点影像分区（可多选），或选“未见明确异常”；
- 第 2 步选四种状态；强调“来源未提及”不等于正常；
- 第 3 步多选库内挂载征象；
- 第 4 步才显示病例标题、分区颜色、库内所见、依据与 40/30/30 评分；
- “提示”只给方法（扫描顺序、四种状态区别、征象定义），不直接给答案；
- 陪练记录只在本机 `radiocheck.studentlab.v1`，不进入班级成绩。

### 3. 自测出题器

- 范围：全部 21 例 / 有异常标注 / 正常对照 / 按征象；
- 题型：混合、影像定位、分区判读、征象识别；
- 题量：5 / 10 / 15 / 20；限时：不限 / 10 / 20 / 30 分钟；
- 试卷含影像、区域框、答题卡、倒计时；
- 交卷后逐题给正确答案、解析、影像 E1 与文献 L 引用；
- 支持只重做错题、导出 Markdown 成绩单、保留最近 20 次记录。

题目由 `chest_reading.json` 的逐区状态、分区框与征象关联规则生成，**不是考试真题**；答案只代表库内标注。

### 4. 班级互助小组

- 教师端“互助小组”页可创建小组、查看帖子、标记解决、删除；
- 学生端可加入小组、在组内论坛发帖、回复、按最新/待解决/我的参与/已解决筛选；
- 帖子可关联 21 例胸片、具体分区与征象；详情页标签可跳阅片台并自动选中该分区；
- 默认只在本机 `radiocheck.classroom.v1`；可选同步服务见“课堂主链路”；
- 教师端可“载入演示小组与帖子”用于现场演示。

## 四种状态

| 状态 | 含义 | 界面 |
| --- | --- | --- |
| `abnormal` | 公开来源/图注明确描述异常 | 琥珀色 |
| `normal` | 公开来源明确为正常，或正常病例的解剖对照 | 青绿色 |
| `unmentioned` | 公开来源没有逐区描述 | 灰色虚线，写“不作推断” |
| `limited` | 投照条件/图像质量导致判读受限 | 蓝色 |

`unmentioned` 绝不渲染成 `normal`。

## 课堂评分规则

| 题目 | 分值 | 规则 |
| --- | --- | --- |
| 定位 | 40 | 选中该病例任一异常分区即正确；无异常病例选“未见明确异常分区” |
| 判读 | 30 | 按学生所选分区的真实状态判分 |
| 征象 | 30 | 按命中数减错选计分；正常病例选“未见明确征象”得满分 |

总分 100，默认 60 分及格；教师布置作业时可调整及格线。

## 在线入口

- 在线版：<https://chefzs929-prog.github.io/yingzhi-medtrain/>（gh-pages 分支，随构建更新）
- 桌面版：双击桌面上的 `RadioCheck.app`，内置本地静态服务，无需联网。

### 演示（Agent 在本机）

```bash
./scripts/demo_tunnel.sh
```

本机起「站点 + `/api` 同源」服务，再建立 Cloudflare 隧道；终端会打印可直接发给评审的 HTTPS 地址
（同时复制到剪贴板）。Agent 始终只在这台 Mac 上运行，关闭终端或合盖即断开。

- 地址每次启动都会变化，演示前跑一次即可
- 首次打开约需等待 20–90 秒（域名注册）
- 单次回答首字约 15–25 秒，页面会先显示检索过程，属正常
- 最省事是直接用隧道地址（站点与 `/api` 同源，无需配置）
- 若坚持用线上静态版：在「连接设置」里填隧道地址，保存后全站生效

后续若要 7×24 在线，见 [docs/未来规划.md](docs/未来规划.md)。

## 离线与免安装分发

站点是纯静态的，数据在浏览器本地计算，**不需要后端、不需要定时任务**。

### macOS

```bash
./desktop/build_app.sh      # 生成 ~/Desktop/影知.app
```

双击即用：自动找空闲端口（8901 起）起本地静态服务并打开浏览器，关窗口即停。

### Windows

```bash
./desktop/build_win.sh      # 生成 outputs/影知-Windows.zip
```

解压后双击 `启动影知.bat`（或 `START.bat`）。压缩包自带 Python 3.11 便携运行时，
目标机器**不需要安装 Python**，也不需要管理员权限；服务器只绑定 `127.0.0.1`，不联网、不上传。

### 为什么可以「永久」

- 内容由 `daily_src.json` + 本地日期在客户端算出，同一天在任何设备结果一致；
- 没有依赖时间的后台进程，不会因为没人访问、服务器到期或电脑关机而失效；
- 静态托管（GitHub Pages）免费且不限时，仓库 fork 或克隆后重新构建即可完整复原。

## 构建与运行

```bash
python3 medtrain/build.py
cd outputs/medtrain
python3 -m http.server 8080
# 打开 http://127.0.0.1:8080/
```

`medtrain/build.py` 会依次生成胸片逐区数据、病例题数据、学生影像实验室数据（`kb/data/student_lab.json`），
复制 clinic / exam / compare / classroom 资源，23 张胸片与 10 张病例题影像，并写入首页、跳转页与 README。

### 动态知识库服务（推荐）

知识库与数据资源默认从后端读取，后端直接读 `kb/data`，按文件修改时间缓存；前端取数失败时自动回退构建期静态 JSON，断网/静态托管仍可演示。

```bash
# 一个端口同时提供知识库 API 与前端页面
python3 yingzhi/serve/main.py --port 8800
# 打开 http://127.0.0.1:8800/read/clinic.html
```

主要接口：

| 接口 | 说明 |
| --- | --- |
| `GET /api/kb/health` | 数据版本与规模 |
| `GET /api/kb/chest` | 胸片逐区数据 |
| `GET /api/kb/exam` | 病例题与对比对 |
| `GET /api/kb/lab` | 学生实验室索引与规则题 |
| `GET /api/kb/search?q=气胸` | 跨征象 / 疾病 / 指南 / 病例 / 分区的关键词检索 |
| `GET /api/kb/signs?q=气胸` | 征象列表与关键词筛选 |
| `GET /api/kb/concepts?q=肺水肿` | 疾病 / 概念列表 |
| `GET /api/kb/guidelines?q=结节` | 指南条款列表 |
| `GET /api/kb/claims?image_id=CASE-001` | 按病例取 claims |
| `GET /api/kb/regions?image_id=CASE-001` | 按病例取分区 |
| `GET /api/kb/sign/SIGN-001` | 征象详情、原文段落与相关病例 |
| `GET /api/kb/case/CASE-001` | 病例详情、分区与 claims |
| `GET /api/kb/image/<name>` | 影像文件 |

如果前端仍用静态服务器（例如 `python3 -m http.server 8811`），可显式指定后端：
`http://127.0.0.1:8811/read/clinic.html?api=http://127.0.0.1:8800`。

原始知识库（signs / concepts / guidelines / claims / regions / paragraphs）直接读 `kb/data`，修改后即时生效；
胸片、病例题、学生实验室等构建产物需要重新运行 `python3 medtrain/build.py`。

### 桌面应用（macOS）

```bash
bash desktop/build.sh        # 产物：outputs/desktop/RadioCheck.app / .dmg / -macOS.zip
open outputs/desktop/RadioCheck.app
```

`desktop/build.sh` 会先确保站点已构建，再用 Objective-C + WKWebView 编译原生壳，
并把 `outputs/medtrain` 整站打进 `RadioCheck.app/Contents/Resources/site`。
无原生壳时可用 `python3 desktop/start.py`（或双击 `desktop/start.command`）以浏览器打开。

## 验收

```bash
python3 kb/scripts/selfcheck_chest_reading.py   # 胸片数据规则 183 项
python3 kb/scripts/selfcheck_exam_cases.py      # 病例题数据规则 238 项
python3 kb/scripts/selfcheck_student_lab.py     # 学生实验室数据规则 20 项
python3 medtrain/tests/chest_check.py           # 工作台端到端 37 项（需先起 8811 端口）
python3 medtrain/tests/exam_check.py            # 病例题 + 对比阅片端到端 62 项（同上）
python3 medtrain/tests/classroom_check.py       # 课堂端到端 39 项（同上）
python3 medtrain/tests/student_lab_check.py     # 问答 / 陪练 / 自测 / 小组 58 项（同上）
python3 medtrain/tests/ask_scope_check.py       # 提问页范围拒答 12 项（治疗/预后/非胸部）
python3 medtrain/tests/site_check.py            # 全站入口 41 项（同上）

# 平台链路：语义检索 + 本地五步工作流（不需要浏览器）
python3 -m unittest kb.tests.test_scope        # 范围拒答 8 项（与提问页/技能共用口径）
python3 yingzhi/serve/test_semantic.py          # 语义检索 10 项（别名/词序/口语改写）
python3 yingzhi/serve/test_workflow.py          # 工作流 11 项（五步齐全、当前病例置顶、引用自证）
python3 yingzhi/serve/test_chest_scope.py       # 胸片专项门控 8 项（拒绝 MG/MR/US/CT 与非胸部部位）

# 一条命令跑完全部验收（单测 + 构建 + 拒答集 + 全站 41 项）
bash scripts/verify_all.sh
bash scripts/verify_all.sh                      # 一键跑全部；YZ_SKIP_BROWSER=1 只跑纯 Python

# 第一优先：证据与质控
python3 kb/scripts/audit_citations.py           # 引用一致性审计 -> docs/引用一致性审计_2026-11-23.md
python3 kb/scripts/build_review_queue.py        # 第四态抽检 + 双 AI 预标注 -> docs/双AI预标注报告_2026-11-23.md
python3 kb/scripts/audit_numbers.py             # 数字口径表 -> docs/数字口径表.md
python3 medtrain/tests/qc_check.py              # 质控复核页 13 项（需 8811）
python3 medtrain/tests/refusal_eval.py          # 拒答/命中 50 条（需 8811）

# 第二优先：教学闭环
python3 medtrain/tests/classroom_sync_check.py  # 同步 API + 双设备 + 离线回退（需 8811）
python3 medtrain/tests/lesson_pack_check.py     # 教师备课包（需 8811）
python3 medtrain/tests/student_plan_check.py    # 错题归因 / 7 天计划 / 雷达图（需 8811）
python3 medtrain/tests/forum_zone_check.py      # 帖子关联分区/征象 + 跳转（需 8811）
```

- 胸片数据自检：`outputs/medtrain/chest_selfcheck.md`
- 病例题数据自检：`outputs/medtrain/exam_selfcheck.md`
- 工作台端到端：`outputs/medtrain/chest_ui_check.md`
- 病例题与对比：`outputs/medtrain/exam_check.md`
- 课堂端到端：`outputs/medtrain/classroom_check.md`
- 学生实验室数据：`outputs/medtrain/student_lab_selfcheck.md`
- 问答 / 陪练 / 自测 / 小组：`outputs/medtrain/student_lab_check.md`
- 全站入口：`outputs/medtrain/site_check.md`
- 语义检索 / 工作流：`GET /api/health` 的 `honesty.semantic_search` 与 `honesty.real_workflow`；
  单次运行的完整五步在 `yingzhi/run/{run_id}/workflow.json`。
  带 `case_id + zone_id` 时，工作流会把**当前病例的逐区原文置顶**（`claim` 纳入证据、其他病例的 claim/case 不进入证据区），
  Agent 的 E1 必须引用当前病例，不再出现“问 CASE-006、引 CASE-202”。
- 提问页范围拒答：`outputs/medtrain/ask_scope_check.md`（治疗/预后/操作/非胸部一律拒答）
- 引用审计：`docs/引用一致性审计_2026-11-23.md`
- 双 AI 预标注：`docs/双AI预标注报告_2026-11-23.md`
- 第四态 SOP：`docs/第四态抽检_SOP.md`
- 数字口径：`docs/数字口径表.md`
- 质控复核：`outputs/medtrain/qc_check.md`
- 拒答评测：`outputs/medtrain/refusal_eval.md`
- 课堂同步：`outputs/medtrain/classroom_sync_check.md`
- 备课包：`outputs/medtrain/lesson_pack_check.md`
- 错题计划与雷达图：`outputs/medtrain/student_plan_check.md`
- 论坛分区/征象：`outputs/medtrain/forum_zone_check.md`

## 数据与许可

> **口径**：对外演示 21 例 / 153 个教学分区 / 99 条 claims（35 条有征象，28 条已挂第二锚点，其中指南级 4 条）；全库知识底座 120 例 / 440 个分区 / 434 条 claims（101 条有征象，85 条已挂第二锚点，其中指南级 9 条）；学生实验室发布 20 条征象 / 58 个概念 / 12 条指南 / 350 道规则题。无征象的正常对照/解剖标注不纳入双引用分母。旧文档中的 596/615 分区、580/599 双引用为历史口径，已废弃。详见 [数字口径表](docs/数字口径表.md)。

- 21 例 CR 胸部逐区校正；每例有独立分区状态、文本、依据与 SHA-256。
- 病例题 10 例，覆盖公开大纲的胸部 X 线考点；8 组对比对。
- 学生实验室：21 例、153 个分区、350 道规则题（定位 153 / 判读 153 / 征象 44）、20 条征象、58 个胸部相关概念、12 条肺结节指南条款。
- 影像仅来自 Wikimedia Commons 的 CC0 / CC BY / CC BY-SA / 公有领域素材。
- 逐张署名与许可见 `outputs/medtrain/ATTRIBUTION.md` 与 `outputs/medtrain/EXAM_ATTRIBUTION.md`。
- 分区框为教学分区，不是病灶分割。

## 明确不做

- **非胸片影像**（胸部 CT、乳腺 MG、腰椎 MRI、头颅 CT、超声等）：后端 `chest_gate()` 直接返回 `unsupported_modality`，不套用胸片模板，见 [反思与未来拓展方向](docs/反思与未来拓展方向.md)；
- 非胸片泛化、DICOM、病灶检测与分割；
- 腹部、泌尿系、长骨骨折与颅脑 CT 的病例题（本版只做胸部 X 线）；
- 诊断、分期、治疗或预后判断；
- 知识库检索页直接调用大模型；智能问答由 Agent 服务提供（本地 `127.0.0.1:8800` 或页面「连接设置」里填写的 HTTPS 地址），证据不足时降级或拒答，不编造引用；
- 账号体系、服务端班级同步、复杂题库与旧的多角色 SPA。

## 文档

- [赛前基础说明.md](docs/赛前基础说明.md) —— 从零搭建：真实时间线、最短跑通命令、技术选型取舍、目录地图、当前边界
- [反思与未来拓展方向.md](docs/反思与未来拓展方向.md) —— 已发生的错配与根因、为什么只做胸片、分阶段拓展与上线硬门槛
- [执业医师胸片病例题_2026-11-22.md](docs/执业医师胸片病例题_2026-11-22.md)
- [胸片阅片_重规划_2026-11-20.md](docs/胸片阅片_重规划_2026-11-20.md)
- [胸片阅片_验收_2026-11-20.md](docs/胸片阅片_验收_2026-11-20.md)
- [全站收缩_2026-11-20.md](docs/全站收缩_2026-11-20.md)
- [课堂系统_教师与学生_2026-11-22.md](docs/课堂系统_教师与学生_2026-11-22.md)
- [学生影像实验室与互助小组_2026-11-22.md](docs/学生影像实验室与互助小组_2026-11-22.md)
