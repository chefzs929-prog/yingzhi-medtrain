# RadioCheck · 胸片阅片、病例题与课堂（v10.4）

对外保留一个首页、一个阅片工作台、一组执业医师大纲病例题、一个对比阅片页和一个课堂：

| 入口 | 说明 |
| --- | --- |
| `index.html` | 唯一门面：范围、四种状态、病例题 / 对比 / 课堂入口、能力边界 |
| `read/clinic.html` | 阅片工作台：21 例 CR 胸部逐区阅片，支持课堂任务模式 |
| `read/exam.html` | 病例题：大纲胸部 10 例，主诉 + 查体 + 胸片，5 选 1 |
| `read/compare.html` | 对比阅片：任意两张影像拖到两侧，并排 / 叠加擦除 / 同步缩放 |
| `read/classroom.html` | 课堂：教师建班/布置/看学情/看小组论坛；学生加入/作答/问答/陪练/自测/互助小组 |

旧入口 `app.html`、`read/teach.html`、`read/paper.html`、`read/index.html`、
`dev/*.html` 都已改为跳转到 `read/clinic.html`，不再提供旧的多角色 SPA。

## 运行

```bash
# 推荐：后端同时提供知识库 API 与前端
python3 yingzhi/serve/main.py --port 8800
# 打开 http://127.0.0.1:8800/read/clinic.html

# 或纯静态托管（前端自动回退构建期 JSON）
cd outputs/medtrain
python3 -m http.server 8080
# 打开 http://127.0.0.1:8080/
```

知识库与数据资源由后端 `kb/data` 直接提供，前端取数失败时回退静态 JSON。
静态托管需要显式连接后端时，可加 `?api=http://127.0.0.1:8800`。

## 病例题主链路

1. 左侧大纲列出 10 个胸部考点：正常、肺炎、浸润性肺结核、肺癌、气胸、胸腔积液、肋骨骨折、二尖瓣型 / 主动脉型 / 普大型心；
2. 每题先给主诉、现病史、既往史、查体与辅助检查，再看胸片；
3. 5 选 1，提交后给影像所见、阅片要点、易错点、考点与影像出处；
4. 答题卡记录在本机 localStorage，可只看错题、重做、清空；
5. 提交后可直接把当前病例送进对比阅片。

题目按公开大纲与公开例题的题型自编，不是官方真题原文；不复制受版权保护的题库。

## 对比阅片主链路

1. 底部胶片条拖动任意病例到左侧或右侧；也可以点卡片，再点“分配到左侧/右侧”；
2. 并排模式：拖动中间分隔条改变两侧宽度；
3. 叠加擦除模式：两张影像叠在同一画布，拖动中间手柄看同一位置的差异；
4. 同步缩放 / 平移可一起看同一解剖位置；双击复位；
5. 8 组预置鉴别卡：肺炎 vs 结核、肺炎 vs 肺癌、结核 vs 肺癌、气胸 vs 正常、积液 vs 肺炎、二尖瓣型 vs 主动脉型、主动脉型 vs 普大型、肋骨骨折 vs 正常；
6. 也可自由对比任意两例，页面给出各自诊断、关键征象、易错点与考点。

## 阅片主链路

1. 左侧选一例（21 例，可按正常 / 气腔影 / 气胸 / 积液 / 结核 / 结节筛选）；
2. 点影像上的教学分区（PA 8 区、LAT 3 区），或拖框；
3. 右栏给出该区独立所见、状态与依据；
4. 「生成阅片记录」导出系统所见 + 分区所见 + 出处 + 非诊断声明。

## 课堂主链路

1. 教师建班，生成 6 位班级码；
2. 教师从 21 例中选病例、设置截止日期与及格线，发布作业；
3. 学生用班级码 + 姓名加入，打开考核工作台；
4. 提交前隐藏病例标题、分区颜色与出处；学生完成定位 / 判读 / 征象三题；
5. 提交后立即评分并解锁对照；低于 80 分的病例进入错题本；
6. 教师端查看提交率、均分、逐例三段得分率与错题，导出班级报告。

## 学生影像实验室

学生端 5 个页签：我的作业 / 影像问答 / 读片陪练 / 自测出题 / 互助小组。

- **影像库问答**：输入征象或疾病名，先查 signs / concepts / guidelines，再回到 21 例胸片分区框；每条命中给“影像定位 E1（病例 + 分区 + 区域框 + 影像出处）”和“文献溯源 L1 + 段落 L2（para_id / char 区间 / sha256）”两条引用链；越界（诊断/治疗/预后/操作）、低置信、库外未命中一律拒答，不编造 id。
- **报告 / 指南文本映射**：可粘贴一段公开教学报告或指南问题；只做“文本 → 库内征象/分区/段落”的关键词映射，不判断报告对错，不生成诊断。
- **读片陪练**：定位（可多选）→ 判读 → 征象 → 对照四步；提示只给方法，不直接给答案；提交后才显示病例标题、分区颜色、库内所见与 40/30/30 评分。
- **自测出题器**：按范围 / 题型 / 题量 / 限时生成试卷；答题卡、倒计时、逐题解析与影像 / 文献引用；支持错题重做、Markdown 成绩单与最近记录。
- **互助小组**：教师建组，学生加入后在组内论坛发帖、回复、标记解决；帖子可关联 21 例胸片。

题目由库内逐区标注规则生成，不是考试真题；答案只代表库内标注。

上传影像只做文件指纹匹配；未入库影像只给通用分区，不下结论；页面默认不调用大模型。
课堂、问答、陪练、自测与小组记录只存在当前浏览器的 localStorage；支持 JSON 导出 / 导入合并，便于教师离线收集。

## 本地 Agent（可选）

知识库检索默认不调用大模型。需要在“智能问答 / 错题追问”里追加解释时，启动本地服务：

```bash
python3 yingzhi/serve/main.py --port 8800
```

前端会先探测 `GET /api/health`；不可用时明确提示启动命令，不会伪装成已接入。Agent 只解释库内证据，不判分、不诊断、不治疗；引用来自服务端 citation 事件，未验证 id 会标红。

## 快速复现（6 条命令）

```bash
git clone https://github.com/chefzs929-prog/yingzhi-medtrain.git
cd yingzhi-medtrain
python3 -m pip install -r requirements.txt && python3 -m playwright install chromium
python3 medtrain/build.py
cd outputs/medtrain && python3 -m http.server 8811   # 浏览器打开 http://127.0.0.1:8811/
```

只装依赖、只构建、只起静态服务即可看到全部页面；下列验收脚本都以此服务为前提。

## 构建与验收

```bash
python3 medtrain/build.py                      # 首页 + clinic + exam + compare + classroom
python3 kb/scripts/selfcheck_chest_reading.py  # 胸片数据规则 183 项
python3 kb/scripts/selfcheck_exam_cases.py     # 病例题数据规则 238 项
python3 kb/scripts/selfcheck_student_lab.py    # 学生实验室数据规则 20 项
python3 kb/scripts/selfcheck_locate_current.py # 当前 153 分区定位下限 + 扰动测试
python3 medtrain/tests/qa_eval.py              # 问答 30 条最小评测集（需先起 8811 端口）
python3 medtrain/tests/chest_check.py          # 工作台端到端 35 项（需先起 8811 端口）
python3 medtrain/tests/exam_check.py           # 病例题 + 对比阅片端到端 51 项（同上）
python3 medtrain/tests/classroom_check.py      # 课堂端到端 33 项（同上）
python3 medtrain/tests/student_lab_check.py    # 问答 / 陪练 / 自测 / 小组 52 项（同上）
python3 medtrain/tests/site_check.py           # 全站入口 41 项（同上）
python3 medtrain/tests/refusal_eval.py         # 拒答 / 命中 50 条（同上）
python3 kb/scripts/crosscheck.py               # JS 与 Python 引擎 69 条逐条比对
python3 -m unittest discover -s kb/tests       # 知识库单元测试（区域定位 / 引用门禁 / 合规）
```

`medtrain/tests/legacy/` 下两个脚本对应已下线的多版 SPA 与 3D 首页，不再纳入复现清单。

胸片数据自检：`outputs/medtrain/chest_selfcheck.md`
病例题数据自检：`outputs/medtrain/exam_selfcheck.md`
工作台端到端：`outputs/medtrain/chest_ui_check.md`
病例题与对比：`outputs/medtrain/exam_check.md`
课堂端到端：`outputs/medtrain/classroom_check.md`
学生实验室数据：`outputs/medtrain/student_lab_selfcheck.md`
当前定位下限：`outputs/medtrain/locate_current.md`
问答 30 条评测：`outputs/medtrain/qa_eval.md`
问答 / 陪练 / 自测 / 小组：`outputs/medtrain/student_lab_check.md`
全站入口：`outputs/medtrain/site_check.md`

## 边界

- 只做 CR 胸部；非胸片未逐区校正，不作为对外功能。
- 病例题只覆盖公开大纲的胸部 X 线考点；腹部、泌尿系、长骨骨折与颅脑 CT 不在本页。
- 不做病灶检测与分割；分区框是教学分区。
- 不做诊断、分期、治疗或预后判断。
- 对比阅片的“相同点 / 鉴别点”是教学归纳，不是诊断路径。
- 逐区与题目文本由 AI 辅助整理，正式教学前须由医学人员逐条审核签字。
