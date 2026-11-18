#!/usr/bin/env python3
"""把已人工核验的候选图写入 cases.jsonl，并复制到 images/。"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAND = ROOT / "_candidates2"
IMG = ROOT / "images"

# idx: (case_id, 标题, 组, 征象标签, 教学用途, 脱敏公开描述)
VERIFIED = {
    1: ("CASE-015", "右中上肺野气腔影（正位）", "GRP-LUNG-CONSOLIDATION", ["SIGN-002"],
        "对照气腔影的分布与肺野透亮度变化。", "来源公开说明为肺炎相关正位胸片，可见斑片状密度增高。"),
    16: ("CASE-016", "双肺弥漫粟粒样结节", "GRP-LUNG-NODULE", ["SIGN-003"],
         "观察弥漫性小结节的分布、密度与大小一致性。", "来源公开说明为粟粒性结核胸片，双肺弥漫细小结节。"),
    4: ("CASE-017", "双侧下肺野模糊伴肋膈角变钝", "GRP-PLEURAL", ["SIGN-007"],
        "对照少量积液与下肺野模糊的边界。", "来源公开说明为胸腔积液相关胸片，双侧下肺野密度增高。"),
    5: ("CASE-018", "侧位胸片：后肋膈角变钝（箭头）", "GRP-PLEURAL", ["SIGN-007"],
        "对照侧位片上液体的分布与肋膈角形态。", "来源公开说明为大量胸腔积液侧位片，箭头为原图标注。"),
    7: ("CASE-019", "气胸多图对照（含床旁片）", "GRP-PLEURAL", ["SIGN-008"],
        "对照立位与床旁片上的胸膜线与肺压缩表现。", "来源公开说明为气胸系列影像，含体位标记与体外导线。"),
    10: ("CASE-020", "气胸伴磨玻璃影（胸片与 CT）", "GRP-LUNG-GGO", ["SIGN-001", "SIGN-008"],
         "对照胸片与 CT 上气胸与磨玻璃影的显示差异。", "来源公开说明为气胸与磨玻璃影的胸片及 CT 对照图。"),
    11: ("CASE-021", "双肺囊性改变与支气管血管束增厚", "GRP-LUNG-GGO", ["SIGN-011", "SIGN-012"],
         "对照囊性间质改变与支气管血管束增厚。", "来源公开说明为淋巴细胞性间质性肺炎的 CT 图像。"),
    14: ("CASE-022", "低剂量 CT 钙化结节（圆圈标注）", "GRP-LUNG-NODULE", ["SIGN-003", "SIGN-006"],
         "对照钙化结节的密度、边缘与显示条件。", "来源公开说明为低剂量 CT 上的钙化结节，圆圈为原图标注。"),
    18: ("CASE-023", "甲状腺囊肿与钙化结节（标注）", "GRP-THYROID", ["SIGN-058", "SIGN-006"],
         "对照囊性成分、钙化与后方声影。", "来源公开说明为甲状腺右叶下极囊肿伴钙化结节，标注为原图自带。"),
    19: ("CASE-024", "甲状腺超声：结节与囊性区", "GRP-THYROID", ["SIGN-058", "SIGN-059"],
         "对照实性低回声区与囊性无回声区。", "来源公开说明为甲状腺超声图像。"),
    24: ("CASE-025", "乳腺 MLO 位血管钙化（标注）", "GRP-BREAST", ["SIGN-006"],
         "对照血管钙化与腺体钙化的形态差异。", "来源公开说明为乳腺 MLO 位，标注血管钙化与点状钙化。"),
    25: ("CASE-026", "乳腺 MLO 位等密度肿块伴钙化", "GRP-BREAST", ["SIGN-055", "SIGN-056"],
         "对照等密度肿块的边界与伴发钙化。", "来源公开说明为与腺体等密度的肿块，伴钙化。"),
    27: ("CASE-027", "乳腺 MLO 位高密度肿块", "GRP-BREAST", ["SIGN-004"],
         "对照高密度肿块的形态与边缘。", "来源公开说明为左乳高密度肿块。"),
    30: ("CASE-028", "乳腺超声：低回声肿块伴后方声影", "GRP-BREAST", ["SIGN-058", "SIGN-060"],
         "对照低回声肿块与后方声影。", "来源公开说明为乳腺超声图像。"),
    34: ("CASE-029", "头颅 CT 冠状位：出血（标注）", "GRP-HEAD", ["SIGN-045"],
         "对照脑实质、脑室与出血的密度差异。", "来源公开说明为颅内出血，标注出血部位与脑室，原图已遮挡部分区域。"),
    37: ("CASE-030", "FLAIR：左侧颞顶叶高信号", "GRP-HEAD", ["SIGN-036"],
         "对照梗死区域的水肿信号与范围。", "来源公开说明为脑梗死的 FLAIR 图像。"),
    41: ("CASE-031", "脑 MRI：颅神经与囊性改变（标注）", "GRP-HEAD", ["SIGN-012"],
         "对照颅神经走行与脑干周围囊性改变。", "来源公开说明为脑 MRI，标注颅神经与囊性改变，原图已遮挡部分区域。"),
    43: ("CASE-032", "肝脏多发低密度灶", "GRP-ABDOMEN", ["SIGN-021"],
         "对照肝内多发低密度灶的分布与边界。", "来源公开说明为肝多发转移的 CT 图像。"),
}

REJECTED = {
    13: "翻拍屏幕含检查日期与设备参数，隐私风险",
    33: "图像含检查号、年龄标记与检查日期",
    35: "工作站截图含检查日期与序列信息，且为颈椎非目标部位",
    39: "工作站截图含检查日期与时间",
    40: "图像含姓名缩写、编号与检查日期",
    44: "全身 PET 研究对比图，与腹部组不符",
    26: "放大位图像中设备结构占据大半画面，教学价值低",
    28: "人物检查照片，含可识别人物",
}

m = json.loads((CAND / "manifest.json").read_text(encoding="utf8"))
cases = [json.loads(l) for l in (ROOT / "data" / "cases.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]
existing = {c["id"] for c in cases}

added = 0
for idx, meta in sorted(VERIFIED.items()):
    it = m[idx - 1]
    if not it.get("file"):
        print("missing file", idx)
        continue
    cid, title, group, tags, note, desc = meta
    if cid in existing:
        continue
    src = CAND / it["file"]
    ext = src.suffix
    dst_name = cid.lower().replace("case-", "case-") + ext
    dst = IMG / dst_name
    shutil.copyfile(src, dst)
    cases.append({
        "id": cid, "title": title, "modality": [it["modality"]], "body_part": it["body_part"],
        "image": f"images/{dst_name}", "source_id": "SRC-COMMONS", "source_page": it["page"],
        "license": it["license_short"], "artist": it["artist"],
        "description_public": desc, "sign_tags": tags, "teaching_note": note,
        "privacy_check": "human_verified_no_identifier", "verified_at": "2026-11-15",
        "status": "active", "group_id": group,
    })
    added += 1

(ROOT / "data" / "cases.jsonl").write_text(
    "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf8")

rej = json.loads((ROOT / "data" / "rejected.json").read_text(encoding="utf8"))
for idx, why in REJECTED.items():
    rej.append({"candidate": f"_candidates2/cand-{idx:03d}", "reason": why})
(ROOT / "data" / "rejected.json").write_text(json.dumps(rej, ensure_ascii=False, indent=2), encoding="utf8")

print("added", added, "total cases", len(cases))
