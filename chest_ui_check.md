# 胸片阅片工作台 · 端到端验收

> 生成时间：2026-11-20 ｜ 通过 37/37 ｜ 基址：http://127.0.0.1:8811/

| # | 检查 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | 页面加载 | 通过 | 胸片阅片工作台 · 选片 → 分区 → 所见与出处 |
| 2 | CASE-001 加载 / 分区 8 / 影像可读 | 通过 | title=正常后前位胸片 zones=8 img=True |
| 3 | CASE-002 加载 / 分区 3 / 影像可读 | 通过 | title=正常侧位胸片 zones=3 img=True |
| 4 | CASE-003 加载 / 分区 8 / 影像可读 | 通过 | title=胸片解剖标注（欠吸气、轻度旋转） zones=8 img=True |
| 5 | CASE-005 加载 / 分区 8 / 影像可读 | 通过 | title=双肺气腔影伴肺不张（含中心静脉导管） zones=8 img=True |
| 6 | CASE-006 加载 / 分区 8 / 影像可读 | 通过 | title=大叶性肺炎（箭头标注） zones=8 img=True |
| 7 | CASE-007 加载 / 分区 8 / 影像可读 | 通过 | title=下肺野气腔影（正位） zones=8 img=True |
| 8 | CASE-008 加载 / 分区 3 / 影像可读 | 通过 | title=下肺野气腔影（侧位） zones=3 img=True |
| 9 | CASE-015 加载 / 分区 8 / 影像可读 | 通过 | title=右中上肺野气腔影（正位） zones=8 img=True |
| 10 | CASE-016 加载 / 分区 8 / 影像可读 | 通过 | title=双肺弥漫粟粒样结节 zones=8 img=True |
| 11 | CASE-017 加载 / 分区 8 / 影像可读 | 通过 | title=双侧下肺野模糊伴肋膈角变钝 zones=8 img=True |
| 12 | CASE-018 加载 / 分区 3 / 影像可读 | 通过 | title=侧位胸片：后肋膈角变钝（箭头） zones=3 img=True |
| 13 | CASE-033 加载 / 分区 8 / 影像可读 | 通过 | title=胸部正位 X 线（解剖标注版） zones=8 img=True |
| 14 | CASE-034 加载 / 分区 8 / 影像可读 | 通过 | title=胸部正位 X 线 zones=8 img=True |
| 15 | CASE-036 加载 / 分区 8 / 影像可读 | 通过 | title=气胸（胸片，标注版） zones=8 img=True |
| 16 | CASE-041 加载 / 分区 8 / 影像可读 | 通过 | title=胸大肌影（胸片） zones=8 img=True |
| 17 | CASE-047 加载 / 分区 8 / 影像可读 | 通过 | title=胸部后前位 X 线 zones=8 img=True |
| 18 | CASE-153 加载 / 分区 8 / 影像可读 | 通过 | title=胸部 X 线 zones=8 img=True |
| 19 | CASE-162 加载 / 分区 8 / 影像可读 | 通过 | title=胸部 X 线 zones=8 img=True |
| 20 | CASE-202 加载 / 分区 8 / 影像可读 | 通过 | title=大叶性肺炎（胸片，红箭头） zones=8 img=True |
| 21 | CASE-203 加载 / 分区 8 / 影像可读 | 通过 | title=肺结核（胸片，历史影像） zones=8 img=True |
| 22 | CASE-204 加载 / 分区 8 / 影像可读 | 通过 | title=结节病：双肺结节（胸片） zones=8 img=True |
| 23 | CASE-006 右肺中野/下野 abnormal、右肺上野 unmentioned | 通过 | ['zone unmentioned', 'zone abnormal', 'zone abnormal', 'zone unmentioned', 'zone unmentioned', 'zone unmentioned', 'zone unmentioned', 'zone unmentioned'] |
| 24 | CASE-006 右肺中野回答含“异常” | 通过 | kael Häggström commons.wikimedia.org/wiki/File:X-ray_of_lobar_pneumonia.jpg
分区标注 · 右肺中野
异常 · 依据：原图箭头 + 公开说明
征象解释 · 实变 · consolidation
肺实质密度均匀增高，掩盖其内血管走行，常可见空气支气管征。 易错点：与胸腔积液区别在于是否可见空气支气管征；需结合病程与实验室检查 ｜ 参考：Fleischner Society 胸部影像术语表（2018）、Radiopaedia 影像学参考条目pubs.rsna.org/doi/10.1148/radiol.2017151718 |
| 25 | CASE-006 右肺上野回答为“来源未提及” | 通过 | edia 影像学参考条目pubs.rsna.org/doi/10.1148/radiol.2017151718
右肺上野有没有异常？
右肺上野 · 来源未提及

公开来源未逐区描述该分区；本工具不作正常或异常的推断。

该区在原始图注中没有逐区描述，因此不能判为正常或异常；请回到整张片子自行观察。

依据与出处
病例来源 · CASE-006 · 大叶性肺炎（箭头标注）
CC0 · Mikael Häggström commons.wikimedia.org/wiki/File:X-ray_of_lobar_pneumonia.jpg
分区标注 · 右肺上野
来源未提及 · 依据：公开来源说明 |
| 26 | CASE-036 右侧三区 abnormal | 通过 | ['zone abnormal', 'zone abnormal', 'zone abnormal', 'zone unmentioned', 'zone unmentioned', 'zone unmentioned', 'zone unmentioned', 'zone unmentioned'] |
| 27 | CASE-036 左侧三区 unmentioned | 通过 | ['zone abnormal', 'zone abnormal', 'zone abnormal', 'zone unmentioned', 'zone unmentioned', 'zone unmentioned', 'zone unmentioned', 'zone unmentioned'] |
| 28 | CASE-036 气胸回答定位到右侧 | 通过 | 0 · Doctoroftcm commons.wikimedia.org/wiki/File%3AChest_X-ray_2346.jpg
分区标注 · 右肺上野
异常 · 依据：原图标注
分区标注 · 右肺中野
异常 · 依据：原图标注
分区标注 · 右肺下野
异常 · 依据：原图标注
征象解释 · 气胸 · pneumothorax
胸膜腔内出现气体，可见脏层胸膜线，其外肺纹理消失。 易错点：张力性气胸需结合纵隔移位判断，属急症范畴；仰卧位少量气胸易漏诊 ｜ 参考：Radiopaedia 影像学参考条目、StatPearls（NCBI Bookshelf）radiopaedia.org/ |
| 29 | 诊断/治疗越界拒答 | 通过 | 中野
异常 · 依据：原图标注
分区标注 · 右肺下野
异常 · 依据：原图标注
征象解释 · 气胸 · pneumothorax
胸膜腔内出现气体，可见脏层胸膜线，其外肺纹理消失。 易错点：张力性气胸需结合纵隔移位判断，属急症范畴；仰卧位少量气胸易漏诊 ｜ 参考：Radiopaedia 影像学参考条目、StatPearls（NCBI Bookshelf）radiopaedia.org/
是不是肺癌？要不要手术？
超出本页范围

本页只做胸片影像表现、分区定位与出处对照，不提供诊断、分期、治疗或预后判断。

可以换成具体分区或征象来问，例如“右肺上野有没有异常”“有没有气胸”“这张片怎么读”。 |
| 30 | 阅片记录可打开 | 通过 |  |
| 31 | 阅片记录含病例与声明 | 通过 | 胸片阅片记录（教学用，非诊断）
======================================
病例：CASE-036 · 气胸（胸片，标注版）
体位：正位（PA） · 质量：正位片（原图气胸标注）
来源：https://commons.wikimedia.org/wiki/File%3AChest_X-ray_2346.jpg
许可：CC0 · 作者：Doctoroftcm

一、 |
| 32 | 库内影像 SHA-256 命中 CASE-001 | 通过 | 正常后前位胸片 |
| 33 | 陌生影像进入通用定位 | 通过 | 上传影像 · 胸片专项

文件：icon-192.png · 12 KB
文件指纹：已计算
图片只在当前浏览器内存中显示，不上传服务器、不落盘。请勿上传真实患者影像。

未连接视觉定位服务

未连接动态服务（静态预览没有 /api）；可先用下方手动分区做解剖定位。

右肺上野
右肺中野
右肺下野
左肺上野
左肺中野
左肺下野
纵隔与心影
膈下

手动分区只帮助定位解剖位置；没有知识库逐区文本时，本工具不对异常 / 正常作判断。

病例出处
CASE-001 · 正常后前位胸片 |
| 34 | 陌生影像给 8 个通用分区 | 通过 | 8 |
| 35 | 通用分区不下结论 | 通过 | 通用解剖分区 · 右肺上野

这是按胸片比例给出的通用分区，
不含该影像的知识库标注
；不能据此判断有无异常，也不生成征象结论。

可对照左侧 21 例知识库影像的同一分区，或换用知识库原图做逐区对照。需要进一步解释时，可用右侧的智能问答；未入库影像不会给出异常判断。 |
| 36 | 拖框命中右肺上野 | 通过 | 已选：右肺上野 |
| 37 | 无 console / page error | 通过 |  |

> 本验收只证明静态工作台与数据规则可复现，不证明影像诊断准确率；
> 正式教学前须由医学人员逐条审核。
