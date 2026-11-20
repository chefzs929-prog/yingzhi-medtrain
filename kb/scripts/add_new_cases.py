#!/usr/bin/env python3
"""把 new_images 中选定的 47 张补充影像转为正式病例，追加到 cases.jsonl。"""
import json, os, shutil

NEW = json.load(open("kb/data/new_images.json"))

# (索引, 标题, 部位, 模态, pose_class, 描述)
PICK = [
    (0, "肺孢子菌肺炎：双肺磨玻璃影（胸片）", "胸部", "CR", "chest_pa",
     "双肺弥漫磨玻璃样密度增高，以肺门周围及中下野为主。"),
    (1, "大叶性肺炎（胸片，红箭头）", "胸部", "CR", "chest_pa",
     "右肺上叶大片实变，红箭头指向病灶边缘。"),
    (2, "肺结核（胸片，历史影像）", "胸部", "CR", "chest_pa",
     "双肺上野斑片状、结节状密度增高，符合继发性肺结核分布。"),
    (4, "结节病：双肺结节（胸片）", "胸部", "CR", "chest_pa",
     "双肺弥漫小结节影，以中上野为著。"),
    (7, "钙化结节（胸部 CT，标准剂量）", "胸部", "CT", "chest_ct_ax",
     "右肺下叶钙化结节，边缘清晰。"),
    (8, "高分辨率 CT 肺窗", "胸部", "CT", "chest_ct_ax",
     "高分辨率 CT 显示肺间质纹理与支气管血管束。"),
    (11, "肺大疱（胸部 CT）", "胸部", "CT", "chest_ct_ax",
     "肺野内薄壁透亮区，其内无肺纹理。"),
    (12, "肺气肿（胸部 CT）", "胸部", "CT", "chest_ct_ax",
     "双肺透亮度增高，肺纹理稀疏。"),
    (13, "全小叶型肺气肿（CT 轴位+冠状）", "胸部", "CT", "chest_ct_ax",
     "双肺弥漫透亮度增高，下叶为著。"),
    (15, "肺动脉高压伴肺气肿（CT 标注）", "胸部", "CT", "chest_ct_ax",
     "肺动脉增宽伴肺气肿改变，图中有彩色标注。"),
    (16, "小叶中心型肺气肿（CT，61 岁女性）", "胸部", "CT", "chest_ct_ax",
     "双肺上叶小叶中心型低密度区。"),
    (17, "小叶中心型肺气肿（CT，65 岁男性）", "胸部", "CT", "chest_ct_ax",
     "双肺小叶中心型肺气肿。"),
    (19, "脑出血（CT/MRI 对照）", "头颅", "CT", "head_ct_ax",
     "脑实质出血灶，CT 呈高密度，MRI 见含铁血黄素沉积。"),
    (20, "后纵裂及左侧天幕出血（CT 冠状）", "头颅", "CT", "head_ct_ax",
     "冠状位 CT 示后纵裂及左侧天幕高密度影。"),
    (21, "脑梗死（头颅 CT）", "头颅", "CT", "head_ct_ax",
     "右侧大脑半球低密度灶，灰白质分界不清。"),
    (22, "小脑梗死（MRI）", "头颅", "MR", "head_mr_ax",
     "小脑半球异常信号。"),
    (24, "头颅 CT 轴位", "头颅", "CT", "head_ct_ax",
     "头颅 CT 轴位，显示脑实质与脑室系统。"),
    (25, "大脑中动脉梗死（CT）", "头颅", "CT", "head_ct_ax",
     "左侧大脑中动脉供血区低密度。"),
    (26, "左侧顶叶慢性梗死（CT）", "头颅", "CT", "head_ct_ax",
     "左侧顶叶局限性低密度，邻近脑沟增宽。"),
    (27, "大脑中动脉高密度征（CT）", "头颅", "CT", "head_ct_ax",
     "大脑中动脉走行区高密度，提示血栓。"),
    (28, "右侧大脑中动脉高密度征（CT）", "头颅", "CT", "head_ct_ax",
     "右侧大脑中动脉走行区高密度征。"),
    (29, "多发性硬化（DIR MRI）", "头颅", "MR", "head_mr_ax",
     "脑白质多发高信号灶，垂直于脑室分布。"),
    (30, "多发性硬化（PSIR MRI）", "头颅", "MR", "head_mr_ax",
     "脑白质多发斑块。"),
    (32, "颈椎退行性变（MRI）", "脊柱", "MR", "spine_lat",
     "颈椎椎间盘退变、椎管狭窄。"),
    (33, "颈椎间盘突出（MRI）", "脊柱", "MR", "spine_lat",
     "颈椎间盘向后突出，压迫硬膜囊。"),
    (48, "腰椎 MRI T2 矢状位（标注版）", "脊柱", "MR", "spine_lat",
     "腰椎矢状位 T2，图中有标注。"),
    (49, "腰椎 MRI T2 矢状位", "脊柱", "MR", "spine_lat",
     "腰椎矢状位 T2，显示椎间盘与椎管。"),
    (34, "膝关节 MRI：半月板股骨韧带", "骨关节", "MR", "bone_lat",
     "膝关节矢状位，半月板股骨韧带及关节积液。"),
    (35, "正常肩关节正位 X 线（Grashey）", "骨关节", "CR", "bone_ap",
     "肩关节正位，显示盂肱关节间隙。"),
    (37, "正常肩关节 Y 位 X 线", "骨关节", "CR", "bone_lat",
     "肩关节 Y 位，显示肩胛盂与肱骨头。"),
    (60, "股骨骨折髓内钉固定（X 线）", "骨关节", "CR", "bone_ap",
     "股骨干骨折髓内钉内固定术后。"),
    (61, "股骨颈骨折（X 线）", "骨关节", "CR", "bone_ap",
     "股骨颈骨折，断端移位。"),
    (62, "股骨小转子撕脱骨折（X 线）", "骨关节", "CR", "bone_ap",
     "股骨小转子撕脱骨折。"),
    (63, "双下肢全长 X 线", "骨关节", "CR", "bone_ap",
     "双下肢全长，显示髋膝踝对线。"),
    (67, "骨盆 X 线", "骨关节", "CR", "bone_ap",
     "骨盆正位，显示骶髂关节与髋关节。"),
    (68, "内踝骨折（X 线）", "骨关节", "CR", "bone_ap",
     "内踝骨折线。"),
    (72, "三踝骨折（X 线）", "骨关节", "CR", "bone_ap",
     "三踝骨折，累及内踝、外踝与后踝。"),
    (39, "乳腺癌剪切波弹性成像", "乳腺", "US", "us",
     "乳腺病灶剪切波弹性图，显示组织硬度。"),
    (40, "乳腺肿瘤超声", "乳腺", "US", "us",
     "乳腺低回声肿块。"),
    (50, "肝泡型棘球蚴病（超声）", "腹部", "US", "us",
     "肝内实性病灶，边界不规则。"),
    (52, "肝泡型棘球蚴病穿刺活检（超声）", "腹部", "US", "us",
     "超声引导下病灶穿刺活检。"),
    (55, "急性胆囊炎（超声）", "腹部", "US", "us",
     "胆囊壁增厚，胆囊增大。"),
    (57, "胆囊壁息肉（超声）", "腹部", "US", "us",
     "胆囊壁附壁息肉样回声。"),
    (42, "肾结石 3mm（CT）", "腹部", "CT", "abd_ct_ax",
     "肾盂内高密度结石。"),
    (43, "右侧肾盂铸型结石（CT）", "腹部", "CT", "abd_ct_ax",
     "右肾盂铸型高密度结石。"),
    (45, "肾结石（CT）", "腹部", "CT", "abd_ct_ax",
     "肾脏高密度结石。"),
    (46, "双肾多发结石（CT）", "腹部", "CT", "abd_ct_ax",
     "双肾多发高密度结石。"),
]

GROUP = {"胸部": "GRP-CHEST", "头颅": "GRP-HEAD", "腹部": "GRP-ABD",
         "脊柱": "GRP-SPINE", "骨关节": "GRP-MSK", "乳腺": "GRP-BREAST",
         "颈部": "GRP-NECK"}


def main():
    rows = [json.loads(l) for l in open("kb/data/cases.jsonl") if l.strip()]
    existing = {r["id"] for r in rows}
    n = 201
    added = []
    for idx, title, bp, mod, pose, desc in PICK:
        cid = f"CASE-{n:03d}"
        while cid in existing:
            n += 1; cid = f"CASE-{n:03d}"
        src = NEW[idx]
        fn = f"case-{n:03d}.jpg"
        shutil.copyfile(f"kb/images/new/{src['tag']}-{idx:02d}.jpg", f"kb/images/{fn}")
        r = {
            "id": cid, "title": title, "modality": mod, "body_part": bp,
            "image": f"images/{fn}",
            "source_id": "SRC-COMMONS",
            "source_page": src["source_page"],
            "license": src["license"],
            "artist": src["artist"] or "Wikimedia Commons contributor",
            "description_public": desc,
            "sign_tags": [],
            "teaching_note": desc,
            "privacy_check": "human_verified_no_identifier",
            "verified_at": "2026-11-20",
            "status": "active",
            "group_id": GROUP.get(bp, "GRP-CHEST"),
            "chapter": bp,
            "pose_class": pose,
            "level": "global",
            "evidence_level": "B",
            "corpus": "manual",
        }
        rows.append(r); added.append(cid); n += 1
    with open("kb/data/cases.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("total", len(rows), "added", len(added))


if __name__ == "__main__":
    main()
