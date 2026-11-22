#!/usr/bin/env python3
"""重建 cases.jsonl：保留 73 例，按影像内容修正标题/部位/模态。
原始文件已备份到 .deepworks/tmp/backup。
"""
import json

KEEP = {
    # id: (title, body_part, modality, pose_class)
    "CASE-001": ("正常后前位胸片", "胸部", "CR", "chest_pa"),
    "CASE-002": ("正常侧位胸片", "胸部", "CR", "chest_lat"),
    "CASE-003": ("胸片解剖标注（欠吸气、轻度旋转）", "胸部", "CR", "chest_pa"),
    "CASE-005": ("双肺气腔影伴肺不张（含中心静脉导管）", "胸部", "CR", "chest_pa"),
    "CASE-006": ("大叶性肺炎（箭头标注）", "胸部", "CR", "chest_pa"),
    "CASE-007": ("下肺野气腔影（正位）", "胸部", "CR", "chest_pa"),
    "CASE-008": ("下肺野气腔影（侧位）", "胸部", "CR", "chest_lat"),
    "CASE-009": ("胸腹交界层面 CT（软组织窗）", "胸部", "CT", "chest_ct_ax"),
    "CASE-010": ("胸部 CT 定位像与轴位对照", "胸部", "CT", "chest_ct_ax"),
    "CASE-011": ("甲状腺结节超声", "颈部", "US", "us"),
    "CASE-013": ("乳腺 MLO 位血管钙化", "乳腺", "MG", "breast_mlo"),
    "CASE-014": ("正常头颅 CT 三视图", "头颅", "CT", "head_ct_ax"),
    "CASE-015": ("右中上肺野气腔影（正位）", "胸部", "CR", "chest_pa"),
    "CASE-016": ("双肺弥漫粟粒样结节", "胸部", "CR", "chest_pa"),
    "CASE-017": ("双侧下肺野模糊伴肋膈角变钝", "胸部", "CR", "chest_pa"),
    "CASE-018": ("侧位胸片：后肋膈角变钝（箭头）", "胸部", "CR", "chest_lat"),
    "CASE-019": ("气胸多图对照（含床旁片）", "胸部", "CR", "chest_pa"),
    "CASE-020": ("气胸伴磨玻璃影（胸片与 CT）", "胸部", "CT", "chest_ct_ax"),
    "CASE-021": ("双肺囊性改变与支气管血管束增厚", "胸部", "CT", "chest_ct_ax"),
    "CASE-022": ("低剂量 CT 钙化结节（圆圈标注）", "胸部", "CT", "chest_ct_ax"),
    "CASE-024": ("甲状腺超声：结节与囊性区", "颈部", "US", "us"),
    "CASE-026": ("乳腺 MLO 位等密度肿块伴钙化", "乳腺", "MG", "breast_mlo"),
    "CASE-027": ("乳腺 MLO 位高密度肿块", "乳腺", "MG", "breast_mlo"),
    "CASE-028": ("乳腺超声：低回声肿块伴后方声影", "乳腺", "US", "us"),
    "CASE-029": ("头颅 CT 冠状位：出血（标注）", "头颅", "CT", "head_ct_ax"),
    "CASE-030": ("FLAIR：左侧颞顶叶高信号", "头颅", "MR", "head_mr_ax"),
    "CASE-031": ("脑 MRI：颅神经与囊性改变（标注）", "头颅", "MR", "head_mr_ax"),
    "CASE-032": ("肝脏多发低密度灶", "腹部", "CT", "abd_ct_ax"),
    "CASE-033": ("胸部正位 X 线（解剖标注版）", "胸部", "CR", "chest_pa"),
    "CASE-034": ("胸部正位 X 线", "胸部", "CR", "chest_pa"),
    "CASE-036": ("气胸（胸片，标注版）", "胸部", "CR", "chest_pa"),
    "CASE-041": ("胸大肌影（胸片）", "胸部", "CR", "chest_pa"),
    "CASE-047": ("胸部后前位 X 线", "胸部", "CR", "chest_pa"),
    "CASE-050": ("右肺下叶结节：CT 晕征", "胸部", "CT", "chest_ct_ax"),
    "CASE-051": ("孤立性肺结节（CT，箭头）", "胸部", "CT", "chest_ct_ax"),
    "CASE-060": ("正常手侧位 X 线", "骨关节", "CR", "bone_lat"),
    "CASE-061": ("正常手正位 X 线", "骨关节", "CR", "bone_ap"),
    "CASE-062": ("足部籽骨 X 线", "骨关节", "CR", "bone_ap"),
    "CASE-064": ("足部副骨与籽骨（标注版）", "骨关节", "CR", "bone_ap"),
    "CASE-065": ("拇外翻：Sgarlato 角测量", "骨关节", "CR", "bone_ap"),
    "CASE-066": ("距舟覆盖角测量", "骨关节", "CR", "bone_ap"),
    "CASE-070": ("正常膝关节正位 X 线", "骨关节", "CR", "bone_ap"),
    "CASE-071": ("正常膝关节侧位 X 线", "骨关节", "CR", "bone_lat"),
    "CASE-073": ("腕关节 X 线", "骨关节", "CR", "bone_ap"),
    "CASE-074": ("正常腕关节正位 X 线", "骨关节", "CR", "bone_ap"),
    "CASE-075": ("正常腕关节 X 线", "骨关节", "CR", "bone_ap"),
    "CASE-076": ("颈椎侧位 X 线", "脊柱", "CR", "spine_lat"),
    "CASE-077": ("下颈椎侧位 X 线", "脊柱", "CR", "spine_lat"),
    "CASE-078": ("颈椎 X 线", "脊柱", "CR", "spine_lat"),
    "CASE-079": ("腰椎退行性变（侧位 X 线）", "脊柱", "CR", "spine_lat"),
    "CASE-080": ("腰椎侧位 X 线", "脊柱", "CR", "spine_lat"),
    "CASE-081": ("膝关节正位 X 线：股骨收肌结节", "骨关节", "CR", "bone_ap"),
    "CASE-082": ("头颅 CT 四层面：慢性梗死", "头颅", "CT", "head_ct_ax"),
    "CASE-085": ("头颅 MRI：占位性病变", "头颅", "MR", "head_mr_ax"),
    "CASE-087": ("膝关节 MRI：半月板股骨韧带", "骨关节", "MR", "bone_lat"),
    "CASE-088": ("头颅 CT：脑梗死", "头颅", "CT", "head_ct_ax"),
    "CASE-092": ("胸部 CT：肺内结节（圆圈标注）", "胸部", "CT", "chest_ct_ax"),
    "CASE-097": ("甲状腺超声", "颈部", "US", "us"),
    "CASE-098": ("胸部 CT：钙化结节", "胸部", "CT", "chest_ct_ax"),
    "CASE-100": ("甲状腺超声", "颈部", "US", "us"),
    "CASE-101": ("腰椎 MRI T2 矢状位", "脊柱", "MR", "spine_lat"),
    "CASE-102": ("PET/CT：肺癌示踪剂对照", "胸部", "PET", "pet"),
    "CASE-104": ("甲状腺超声", "颈部", "US", "us"),
    "CASE-105": ("腰椎 MRI T2 矢状位（10/12）", "脊柱", "MR", "spine_lat"),
    "CASE-106": ("鼻骨骨折（侧位 X 线）", "骨关节", "CR", "bone_lat"),
    "CASE-107": ("腰椎骨折（X 线）", "脊柱", "CR", "spine_lat"),
    "CASE-110": ("腰椎骨折（X 线，女性）", "脊柱", "CR", "spine_lat"),
    "CASE-112": ("胆囊结石超声", "腹部", "US", "us"),
    "CASE-118": ("乳腺剪切波弹性成像", "乳腺", "US", "us"),
    "CASE-120": ("乳腺肿瘤超声", "乳腺", "US", "us"),
    "CASE-153": ("胸部 X 线", "胸部", "CR", "chest_pa"),
    "CASE-158": ("胸部 CT", "胸部", "CT", "chest_ct_ax"),
    "CASE-162": ("胸部 X 线", "胸部", "CR", "chest_pa"),
}

GROUP = {
    "胸部": "GRP-CHEST", "头颅": "GRP-HEAD", "腹部": "GRP-ABD",
    "脊柱": "GRP-SPINE", "骨关节": "GRP-MSK", "乳腺": "GRP-BREAST",
    "颈部": "GRP-NECK",
}


def main():
    old = {}
    for line in open("kb/data/cases.jsonl"):
        if line.strip():
            r = json.loads(line)
            old[r["id"]] = r
    out = []
    for cid, (title, bp, mod, pose) in KEEP.items():
        r = dict(old[cid])
        r["title"] = title
        r["body_part"] = bp
        r["modality"] = mod
        r["pose_class"] = pose
        r["group_id"] = GROUP.get(bp, "GRP-CHEST")
        r["chapter"] = bp
        r["status"] = "active"
        r["corpus"] = "manual"
        r.pop("shared_image_of", None)
        r["image"] = r["image"].replace("images/", "images/")
        out.append(r)
    with open("kb/data/cases.jsonl", "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("cases written", len(out))


if __name__ == "__main__":
    main()
