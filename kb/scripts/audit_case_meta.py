#!/usr/bin/env python3
"""病例素材/元数据体检。

按「标题 + 公开说明」中的关键词与 modality / body_part 交叉核对，列出：
  1. 非影像素材（检查场景、诊室、器械、大体标本照片）
  2. 模态错配（说明写 MRI/CT/超声，modality 却是 CR/MG）
  3. 部位错配（说明写腰椎/鼻骨，body_part 却是头颅/胸部）

输出：
  docs/病例元数据体检.md   人读清单
  kb/data/meta_audit.json  机器可读结果
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb" / "data"

SCENE_RE = re.compile(
    r"(technologist|mammograph\w* (?:center|room|machine)|women'?s imaging|"
    r"undergoing|waiting room|control room|autopsy|gross (?:specimen|photograph)|"
    r"cross section of a human liver|healthcare system)",
    re.I,
)
MR_RE = re.compile(r"(\bMRI\b|magnetic resonance|T1[- ]weighted|T2[- ]weighted|FLAIR|DWI)", re.I)
CT_RE = re.compile(r"(\bCT\b|computed tomography|PET/CT)", re.I)
US_RE = re.compile(r"(\bultrasound\b|\bUS\b|sonograph|B-mode|SWE)", re.I)
CR_RE = re.compile(r"(radiograph|\bX-?ray\b|chest film|plain film)", re.I)

BODY_HINTS = [
    (re.compile(r"(lumbar|L1|L2|L3|L4|L5|S1)", re.I), "腰椎"),
    (re.compile(r"(cervical spine|C1|C2|C3|C4|C5|C6|C7)", re.I), "颈椎"),
    (re.compile(r"(nose|nasal)", re.I), "鼻骨"),
    (re.compile(r"(knee|meniscus|meniscofemoral|patell)", re.I), "膝关节"),
    (re.compile(r"(brain|intracranial|cerebral|mening|FLAIR)", re.I), "头颅"),
    (re.compile(r"(thyroid)", re.I), "甲状腺"),
    (re.compile(r"(breast|mammograph|mammary)", re.I), "乳腺"),
    (re.compile(r"(chest|pulmonary|lung|pneumo|pleural|thorac)", re.I), "胸部"),
    (re.compile(r"(liver|hepat|abdomen|abdominal|renal|kidney|pancrea)", re.I), "腹部"),
]

MODALITY_ALIASES = {
    "MR": {"MR", "MRI"},
    "CT": {"CT"},
    "US": {"US", "超声"},
    "CR": {"CR", "DR", "X线", "X-ray"},
    "MG": {"MG", "钼靶"},
}


def norm_modalities(value):
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[,/、\s]+", str(value or ""))
    out = set()
    for v in raw:
        v = str(v).strip().upper()
        if v:
            out.add(v)
    return out


def main():
    cases = [json.loads(line) for line in (DATA / "cases.jsonl").read_text(encoding="utf8").splitlines() if line.strip()]
    findings = []
    for c in cases:
        text = f"{c.get('title', '')} {c.get('description_public', '')} {c.get('teaching_note', '')}"
        mods = norm_modalities(c.get("modality"))
        issues = []

        if SCENE_RE.search(text):
            issues.append({"kind": "非影像素材", "detail": SCENE_RE.search(text).group(0)})

        if MR_RE.search(text) and not (mods & MODALITY_ALIASES["MR"]):
            issues.append({"kind": "模态错配", "detail": "说明为 MRI，modality=" + ",".join(sorted(mods))})
        elif CT_RE.search(text) and not (mods & MODALITY_ALIASES["CT"]):
            issues.append({"kind": "模态错配", "detail": "说明为 CT，modality=" + ",".join(sorted(mods))})
        elif US_RE.search(text) and not (mods & MODALITY_ALIASES["US"]):
            issues.append({"kind": "模态错配", "detail": "说明为超声，modality=" + ",".join(sorted(mods))})
        elif CR_RE.search(text) and not (mods & MODALITY_ALIASES["CR"]):
            issues.append({"kind": "模态错配", "detail": "说明为 X 线，modality=" + ",".join(sorted(mods))})

        for rx, body in BODY_HINTS:
            if rx.search(text) and c.get("body_part") not in (body, "肌骨", "骨"):
                # 只报明确冲突的跨大部位错配
                if body == "腰椎" and c.get("body_part") in ("头颅", "颈椎", "胸部"):
                    issues.append({"kind": "部位错配", "detail": f"说明像{body}，body_part={c.get('body_part')}"})
                elif body == "鼻骨" and c.get("body_part") not in ("骨", "肌骨"):
                    issues.append({"kind": "部位错配", "detail": f"说明像{body}，body_part={c.get('body_part')}"})
                elif body == "头颅" and c.get("body_part") in ("胸部", "腰椎", "颈椎", "腹部"):
                    issues.append({"kind": "部位错配", "detail": f"说明像{body}，body_part={c.get('body_part')}"})
                break

        if issues:
            findings.append({"id": c["id"], "title": c.get("title"), "body_part": c.get("body_part"),
                             "modality": sorted(mods), "status": c.get("status", "active"), "issues": issues})

    (DATA / "meta_audit.json").write_text(json.dumps(findings, ensure_ascii=False, indent=1), encoding="utf8")

    lines = ["# 病例素材与元数据体检", "",
             "按标题与公开说明交叉核对，只列可自动判定的冲突；未列出的病例仍需人工看图核验。", "",
             f"共 {len(findings)} / {len(cases)} 例命中。", "",
             "| 病例 | 状态 | 部位 | 模态 | 标题 | 问题 |", "| --- | --- | --- | --- | --- | --- |"]
    for f in findings:
        detail = "；".join(f"{i['kind']}（{i['detail']}）" for i in f["issues"])
        lines.append(f"| {f['id']} | {'已停用' if f.get('status') == 'inactive' else '启用'} | {f['body_part']} | {'/'.join(f['modality'])} | {f['title']} | {detail} |")
    lines += ["", "## 处理建议", "",
              "1. 「非影像素材」：从分区标注库停用，或换成同部位真实影像后再启用。",
              "2. 「模态错配 / 部位错配」：先改 cases.jsonl 的 modality 与 body_part，再按新部位重写分区与结论。",
              "3. 批量修正前逐例看图确认；本表只做筛查，不替代人工核验。"]
    (ROOT / "docs" / "病例元数据体检.md").write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"{len(findings)} findings -> docs/病例元数据体检.md")


if __name__ == "__main__":
    main()
