# 病例题影像署名与许可

本文件由 `kb/scripts/build_exam_cases.py` 生成。
影像只用于医学影像教学演示；版权归原作者，使用遵循下列许可。
部分影像为公开来源自带教学标注（红箭头/白线/文字），已在题目 `image_note` 中说明。

| 病例 | 原始文件 | 作者 | 许可 | 来源 |
| --- | --- | --- | --- | --- |
| EX-01 | Normal posteroanterior (PA) chest radiograph | Mikael Häggström | CC0 | [Commons](https://commons.wikimedia.org/wiki/File:Normal_posteroanterior_(PA)_chest_radiograph_(X-ray).jpg) |
| EX-02 | X-ray of lobar pneumonia | Mikael Häggström | CC0 | [Commons](https://commons.wikimedia.org/wiki/File:X-ray_of_lobar_pneumonia.jpg) |
| EX-03 | PulmonaryTBCXR | James Heilman, MD | CC BY-SA 4.0 | [Commons](https://commons.wikimedia.org/wiki/File:PulmonaryTBCXR.png) |
| EX-04 | Lung Cancer on Chest X-Ray | James Heilman, MD | CC BY-SA 4.0 | [Commons](https://commons.wikimedia.org/wiki/File:Lung_Cancer_on_Chest_X-Ray.jpg) |
| EX-05 | Pneumothorax on chest x-ray (right side) | Hellerhoff | CC BY-SA 3.0 | [Commons](https://commons.wikimedia.org/wiki/File:09-01-Pneumothorax.png) |
| EX-06 | A large left sided pleural effusion as seen on an upright chest X-ray | James Heilman, MD | CC BY-SA 3.0 | [Commons](https://commons.wikimedia.org/wiki/File:Effusionhalf.PNG) |
| EX-07 | Chest X-ray of a normal lung with old left 5th and 6th ribs fractures | Cerevisae | CC BY-SA 4.0 | [Commons](https://commons.wikimedia.org/wiki/File:Chest_X-ray_of_a_normal_lung_with_old_left_5th_and_6th_ribs_fractures.jpg) |
| EX-08 | Enfermedad Mitral | SCiardullo | CC BY-SA 3.0 | [Commons](https://commons.wikimedia.org/wiki/File:Enfermedad_Mitral.JPG) |
| EX-09 | Aortale Herzkonfiguration bei Aortenstenose | Hellerhoff | CC BY-SA 4.0 | [Commons](https://commons.wikimedia.org/wiki/File:Aortale_Herzkonfiguration_bei_Aortenstenose_75W_-_CR_pa_-_001.jpg) |
| EX-10 | Rad 1300124 | Nevit Dilmen | CC BY-SA 3.0 | [Commons](https://commons.wikimedia.org/wiki/File:Rad_1300124.JPG) |

## 处理说明

- `EX-06` 的母本为公开来源的左侧大量胸腔积液胸片，原图带黑色圆圈标注；
  本站用 OpenCV 局部修复去除圆圈，仅保留影像本体，未改变病灶。
- `EX-02` 保留来源原图红箭头；`EX-07` 保留来源原图白线与 Old fractures 文字；
  两处均为公开来源自带教学标注，已在题目 `image_note` 中说明，不代表诊断。
- 其余影像仅做尺寸压缩与 JPEG 转码，未做病灶增强或合成。

## 题目版权

题干、选项、解析与对比要点为本站按公开大纲与公开例题的题型自编，
不复制受版权保护的题库原文；如用于正式教学，请由医学人员逐条审核。
