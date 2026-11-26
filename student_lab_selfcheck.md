# 学生影像实验室 · 数据自检

> 生成时间：2026-11-22 ｜ 通过 20/20

| # | 检查 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | 版本字段 | 通过 | 2026-11-22 |
| 2 | 范围声明为 21 例 CR 胸部 | 通过 | 21 例已启用 CR 胸部逐区数据；问答、陪练与自测只在此范围内。 |
| 3 | 病例 21 例 | 通过 | 21 |
| 4 | 计数 cases 一致 | 通过 | {'cases': 21, 'zones': 153, 'questions': 234, 'locate': 95, 'status': 95, 'sign': 44, 'signs': 20, 'concepts': 58, 'guidelines': 12, 'sources': 11, 'sign_paragraphs': 80, 'signs_with_paragraphs': 20, 'guideline_paragraphs': 42} |
| 5 | 计数 questions 一致 | 通过 | {'cases': 21, 'zones': 153, 'questions': 234, 'locate': 95, 'status': 95, 'sign': 44, 'signs': 20, 'concepts': 58, 'guidelines': 12, 'sources': 11, 'sign_paragraphs': 80, 'signs_with_paragraphs': 20, 'guideline_paragraphs': 42} |
| 6 | 计数 zones 一致 | 通过 | {'cases': 21, 'zones': 153, 'questions': 234, 'locate': 95, 'status': 95, 'sign': 44, 'signs': 20, 'concepts': 58, 'guidelines': 12, 'sources': 11, 'sign_paragraphs': 80, 'signs_with_paragraphs': 20, 'guideline_paragraphs': 42} |
| 7 | 定位题 95（未提及分区不出题） | 通过 | {'cases': 21, 'zones': 153, 'questions': 234, 'locate': 95, 'status': 95, 'sign': 44, 'signs': 20, 'concepts': 58, 'guidelines': 12, 'sources': 11, 'sign_paragraphs': 80, 'signs_with_paragraphs': 20, 'guideline_paragraphs': 42} |
| 8 | 判读题 95（未提及分区不出题） | 通过 | {'cases': 21, 'zones': 153, 'questions': 234, 'locate': 95, 'status': 95, 'sign': 44, 'signs': 20, 'concepts': 58, 'guidelines': 12, 'sources': 11, 'sign_paragraphs': 80, 'signs_with_paragraphs': 20, 'guideline_paragraphs': 42} |
| 9 | 征象题 44 | 通过 | {'cases': 21, 'zones': 153, 'questions': 234, 'locate': 95, 'status': 95, 'sign': 44, 'signs': 20, 'concepts': 58, 'guidelines': 12, 'sources': 11, 'sign_paragraphs': 80, 'signs_with_paragraphs': 20, 'guideline_paragraphs': 42} |
| 10 | 征象 20 条 | 通过 | 20 |
| 11 | 来源唯一 | 通过 | 11 |
| 12 | 概念至少 30 条 | 通过 | 58 |
| 13 | 指南至少 10 条 | 通过 | 12 |
| 14 | 病例字段 / 分区坐标 / 状态 / 征象引用 | 通过 |  |
| 15 | 征象字段与来源引用 | 通过 |  |
| 16 | 概念到征象引用 | 通过 |  |
| 17 | 题目答案 / 索引 / 选项 / 坐标 / 引用 | 通过 |  |
| 18 | 每个病例都有定位题和判读题 | 通过 |  |
| 19 | 至少 14 例有征象题 | 通过 | 14 |
| 20 | 首题可读 | 通过 | {"qid": "LAB-LOC-CASE-001-LLL", "type": "locate", "type_label": "影像定位", "case_id": "CASE-001", "zone_id": "LLL", "coords": [0.64, 0.57, 0.3, 0.25], "prompt": "图中框选的区域属于哪个解剖分区？", "options": ["纵隔与心影", " |

> 本自检只证明数据结构和引用可复现；不证明医学结论正确。
> 正式教学前须由医学人员逐条审核。
