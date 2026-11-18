# 征象文字 ↔ 影像区域关联（v1）

> 每条同时包含文字锚点与图像锚点；框为人工教学标注，不是模型识别或病灶分割。

## 实变（consolidation）

### SL-001 · 大叶性肺炎（箭头标注）

文字锚点：肺实质密度均匀增高，掩盖其内血管走行
图像：大叶性肺炎（箭头标注）（CASE-006）
标注区域：右肺中下野（bbox=[0.09, 0.37, 0.34, 0.37]，pa_chest: image_left = patient_right）
图注：红色箭头所指的右肺中下野片状致密影，覆盖该区血管纹理。
对照说明：该区密度均匀增高、血管边缘不易分辨，与“掩盖其内血管走行”对应；空气支气管征需结合原始图像与来源说明判断。
标注依据：source_label
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File:X-ray_of_lobar_pneumonia.jpg
本地文件：images/case-006.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

### SL-002 · 右中上肺野气腔影（正位）

文字锚点：肺实质密度均匀增高，掩盖其内血管走行
图像：右中上肺野气腔影（正位）（CASE-015）
标注区域：右肺中上野（bbox=[0.12, 0.1, 0.29, 0.36]，pa_chest: image_left = patient_right）
图注：右肺中上野斑片状密度增高，肺野透亮度下降。
对照说明：斑片状密度增高覆盖该区血管纹理，可作为“密度均匀增高”的对照；不据此判断病因。
标注依据：source_description
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File%3AChest_radiograph_in_influensa_and_H_influenzae%2C_posteroanterior.jpg
本地文件：images/case-015.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

### SL-003 · 双肺气腔影伴肺不张（含中心静脉导管）

文字锚点：肺实质密度均匀增高，掩盖其内血管走行
图像：双肺气腔影伴肺不张（含中心静脉导管）（CASE-005）
标注区域：右肺中上野（AP 坐位）（bbox=[0.15, 0.17, 0.35, 0.43]，ap_chest: image_left = patient_right）
图注：原图标注 air-space opacities 指向右肺中上野片状致密影。
对照说明：来源标注为气腔影；图中致密区覆盖血管纹理，与实变的文字表述方向一致，但单张床旁片不足以确认空气支气管征。
标注依据：source_label
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File:Chest_X-ray_showing_neurofibromatosis_with_bilateral_pneumonia.jpg
本地文件：images/case-005.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

## 肺不张（atelectasis）

### SL-004 · 双肺气腔影伴肺不张（含中心静脉导管）

文字锚点：肺组织含气量减少、体积缩小、密度增高
图像：双肺气腔影伴肺不张（含中心静脉导管）（CASE-005）
标注区域：右肺下野（AP 坐位）（bbox=[0.1, 0.46, 0.31, 0.34]，ap_chest: image_left = patient_right）
图注：原图标注 atelectasis 指向右肺下野，伴密度增高与体积缩小。
对照说明：该区密度增高并见体积缩小线索，与肺不张的文字表述对应；“体积缩小”需结合叶间裂与纵隔位置综合观察。
标注依据：source_label
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File:Chest_X-ray_showing_neurofibromatosis_with_bilateral_pneumonia.jpg
本地文件：images/case-005.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

## 磨玻璃影（ground-glass opacity）

### SL-005 · 气胸伴磨玻璃影（胸片与 CT）

文字锚点：肺野密度轻度增高，但其内血管与支气管边缘仍可辨认
图像：气胸伴磨玻璃影（胸片与 CT）（CASE-020）
标注区域：左肺（bbox=[0.76, 0.29, 0.21, 0.38]，axial_ct: image_left = patient_right）
图注：右半侧 CT 图像中，含气肺组织内可见密度轻度增高区，血管边缘仍可分辨。
对照说明：该区密度增高但未完全掩盖血管，与磨玻璃影的文字表述方向一致；图为胸片与 CT 对照，框只覆盖 CT 一侧。
标注依据：source_description
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File%3AX-ray_and_CT_of_ground_glass_opacities_and_pneumothorax_in_pneumocystis_pneumonia.jpg
本地文件：images/case-020.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

## 气胸（pneumothorax）

### SL-006 · 气胸伴磨玻璃影（胸片与 CT）

文字锚点：可见脏层胸膜线，其外肺纹理消失
图像：气胸伴磨玻璃影（胸片与 CT）（CASE-020）
标注区域：右侧胸腔（bbox=[0.57, 0.13, 0.2, 0.63]，axial_ct: image_left = patient_right）
图注：CT 图像左侧大片无肺纹理透亮区，内侧可见被压缩肺组织的边缘。
对照说明：透亮区内肺纹理消失，受压肺组织边缘可作脏层胸膜线的对照；张力性气胸需结合纵隔移位，本图不作判断。
标注依据：source_description
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File%3AX-ray_and_CT_of_ground_glass_opacities_and_pneumothorax_in_pneumocystis_pneumonia.jpg
本地文件：images/case-020.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

## 胸腔积液（pleural effusion）

### SL-007 · 双侧下肺野模糊伴肋膈角变钝

文字锚点：立位胸片表现为肋膈角变钝或下肺野均匀致密影
图像：双侧下肺野模糊伴肋膈角变钝（CASE-017）
标注区域：右侧肋膈角（bbox=[0.05, 0.61, 0.29, 0.31]，pa_chest: image_left = patient_right）；左侧肋膈角（bbox=[0.65, 0.57, 0.31, 0.34]，pa_chest: image_left = patient_right）
图注：双侧下肺野密度增高，肋膈角变钝。
对照说明：双侧肋膈角变钝、下肺野密度增高，与立位胸片的积液表述对应；少量积液与胸膜增厚需结合其他体位或超声。
标注依据：source_description
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File%3AMedical_X-Ray_imaging_AGL02_nevit.jpg
本地文件：images/case-017.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

### SL-008 · 侧位胸片：后肋膈角变钝（箭头）

文字锚点：立位胸片表现为肋膈角变钝或下肺野均匀致密影
图像：侧位胸片：后肋膈角变钝（箭头）（CASE-018）
标注区域：后肋膈角（侧位）（bbox=[0.52, 0.34, 0.31, 0.25]，lateral_chest: no left-right distinction）
图注：侧位片后肋膈角变钝，红色箭头为原图标注。
对照说明：侧位片不能区分左右，只能定位前后；后肋膈角变钝与积液表述对应。
标注依据：source_label
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File%3ALargePleuralEffusionLatPlain.png
本地文件：images/case-018.png

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

## 低回声结节（hypoechoic nodule）

### SL-009 · 甲状腺结节超声

文字锚点：超声上回声低于周围腺体组织的结节
图像：甲状腺结节超声（CASE-011）
标注区域：甲状腺结节（图像中央）（bbox=[0.17, 0.2, 0.7, 0.57]，us_local: no whole-body reference）
图注：结节回声低于周围腺体组织，边界可见；图中设备参数为原图自带。
对照说明：该模态没有全身定位参考，分区只表示图像内相对位置；回声高低需与邻近正常腺体比较。
标注依据：source_description
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File:Thyroid_ultrasound_110322134324_1347140.jpg
本地文件：images/case-011.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

## 钙化（calcification）

### SL-010 · 乳腺 MLO 位血管钙化

文字锚点：密度接近骨皮质的斑点、条状或环状影
图像：乳腺 MLO 位血管钙化（CASE-013）
标注区域：血管走行区（条状钙化）（bbox=[0.2, 0.25, 0.32, 0.3]，mg_mlo: laterality requires image marker）；腺体区（点状钙化）（bbox=[0.21, 0.58, 0.08, 0.09]，mg_mlo: laterality requires image marker）
图注：原图标注 vascular calcification 为条状血管壁钙化；下方另见点状钙化。
对照说明：条状与点状高密度影接近骨皮质密度，与钙化的文字表述对应；乳腺钙化的形态意义需结合部位与分布，不能跨部位套用。
标注依据：source_label
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File:Mammography_MLO_view_showing_vascular_calculation_of_the_breast.jpg
本地文件：images/case-013.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

## 蜂窝影（honeycombing）

### SL-011 · 双肺囊性改变与支气管血管束增厚

文字锚点：成簇的厚壁囊状透亮影
图像：双肺囊性改变与支气管血管束增厚（CASE-021）
标注区域：右肺胸膜下（轴位）（bbox=[0.06, 0.04, 0.16, 0.2]，axial_ct: image_left = patient_right）
图注：轴位图左上（胸膜下）成簇囊状透亮影，空心箭头为原图标注。
对照说明：成簇、厚壁、胸膜下分布，与蜂窝影的文字表述对应；单层厚层图像易误判，需薄层确认。
标注依据：source_label
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File%3ACT_of_lymphocytic_interstitial_pneumonia.jpg
本地文件：images/case-021.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。

## 网状影（reticular pattern）

### SL-012 · 双肺囊性改变与支气管血管束增厚

文字锚点：肺内细线状影交织成网
图像：双肺囊性改变与支气管血管束增厚（CASE-021）
标注区域：左肺（轴位）（bbox=[0.28, 0.45, 0.18, 0.3]，axial_ct: image_left = patient_right）
图注：轴位图右侧肺野细线状影增多并交织，实心箭头指向支气管血管束增厚区。
对照说明：细线状影交织成网，与网状影的文字表述对应；需与正常肺纹理增多区分，并结合分布判断。
标注依据：source_label
标注：human · 2026-11-15 · single_review

来源页：https://commons.wikimedia.org/wiki/File%3ACT_of_lymphocytic_interstitial_pneumonia.jpg
本地文件：images/case-021.jpg

边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。
