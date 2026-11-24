# 拒答分类学

系统"不能答"不是因为不会，而是因为**这一类问题的证据不在库里**。把类型讲清楚，比笼统说"建议咨询医生"有用。

分两级：`hard`（完全不能答）与 `soft`（不给结论，但可以给相关依据）。

---

## hard · 完全不能答

| 类型 | 典型问法 | 为什么不能答 |
|---|---|---|
| `out_of_scope_diagnosis` | 是不是肺癌 | 分区标注不含病理与恶性依据，需病理、增强 CT、多学科 |
| `out_of_scope_staging` | 早期还是晚期 | 分期依赖 TNM、影像分期与病理 |
| `out_of_scope_etiology` | 细菌还是病毒 | 需痰培养、核酸、抗原等实验室证据 |
| `out_of_scope_treatment` | 吃什么药 / 要不要手术 | 需病原学、药敏、肝肾功能、过敏史 |
| `out_of_scope_management` | 需要住院吗 | 需症状、生命体征、实验室与社会因素 |
| `out_of_scope_prognosis` | 预后怎么样 / 能活多久 | 需纵向随访与分期，单张片不足 |
| `out_of_scope_report` | 帮我写报告并签字 | 医疗文书须由资质医师签发 |
| `out_of_scope_topic` | 有没有骨折 | 分区标注不含骨骼系统判读 |
| `out_of_scope_modality` | 这张 CT 上… | 本项目只覆盖胸部 X 线 |
| `out_of_scope_privacy` | 病人叫什么 | 公开数据集已脱敏，不检索身份信息 |
| `out_of_scope_guidance` | 该挂哪个科 | 不做就诊路径建议 |
| `out_of_scope_task` | 写代码 / 翻译 | 不是影像教学任务 |
| `out_of_scope_guarantee` | 能保证 100% 准确吗 | 不提供准确性承诺 |

## soft · 不给结论，但可以给依据

| 类型 | 典型问法 | 能给什么 |
|---|---|---|
| `out_of_scope_differential` | 肺炎还是肺结核 | 可以分别给两种病变的描述与出处，不下"二者之一"的结论 |
| `out_of_scope_diagnosis`（良恶性） | 结节是良性还是恶性 | 可以给部位、大小、边缘形态的来源描述 |
| `out_of_scope_longitudinal` | 跟上次比变大了吗 | 库里每例只有单张片，没有时间轴 |
| `out_of_scope_measure` | 病灶多少毫米 | 分区级标注，无标尺校准；胸片有投照放大率 |
| `out_of_scope_quantify` | 积液多少毫升 | 可提示存在与大致范围，不做容量估算 |
| `out_of_scope_quality` | 拍得合格吗 / 剂量多少 | 有"判读受限"标记可用，但不评估摄片合格性 |
| `out_of_scope_normal` | 这张片子是正常的吗 | 逐区标注，有的区"未提及"，未提及 ≠ 正常 |
| `out_of_scope_certainty` | 这个阴影一定是病变吗 | 可能是重叠结构、体位或伪影，不做确定性断言 |

---

## 一条铁律

**未提及 ≠ 正常。**

公开来源没有逐区描述某区，只能说"来源未描述"。把它当正常，是本系统最容易犯、也最需要防的错误——练习题库里有 14 道题专考这一点。
