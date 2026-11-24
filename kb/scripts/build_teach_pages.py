#!/usr/bin/env python3
"""构建对外保留的页面：阅片工作台、病例题、对比阅片、课堂、学生影像实验室。

输出：
    outputs/medtrain/read/clinic.html    阅片工作台
    outputs/medtrain/read/exam.html      大纲病例题
    outputs/medtrain/read/compare.html   对比阅片
    outputs/medtrain/read/classroom.html 教师 / 学生课堂
    outputs/medtrain/data/chest/...      胸片逐区数据
    outputs/medtrain/data/exam/...       病例题与对比对数据
    outputs/medtrain/data/lab/...        学生问答 / 陪练 / 自测索引与规则题
    outputs/medtrain/images/case-*.jpg   胸片数据引用到的影像
    outputs/medtrain/images/exam/*.jpg   病例题影像

旧的图谱 / 组卷 / 报告对照页面不再构建，只保留跳转，避免旧链接 404。
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "kb/app"
OUT = ROOT / "outputs/medtrain/read"
SITE = OUT.parent

# 四个页面只依赖这些资源；agent/app/teach/paper 不再打包
ASSETS = [
    "base.css", "clinic.css", "common.js", "kb-api.js", "locate.js", "clinic.js",
    "exam.css", "exam.js", "compare.css", "compare.js",
    "classroom-core.js", "classroom.css", "student-lab.js", "classroom.js",
    "agent-lite.js", "classroom-sync.js", "qc.css", "qc.js",
]

LEGACY_PAGES = ["index.html", "teach.html", "paper.html"]

REDIRECT = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · RadioCheck</title>
<meta http-equiv="refresh" content="0;url=__TARGET__">
<link rel="canonical" href="__TARGET__">
<style>
html,body{height:100%;margin:0;background:#f4fbfa;color:#10232e;
  font:14px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  display:grid;place-items:center}
.box{text-align:center;padding:24px}
.m{width:44px;height:44px;border-radius:13px;margin:0 auto 12px;display:grid;place-items:center;
  background:linear-gradient(140deg,#0b4f55,#0e7c7b);color:#fff;font-size:20px;font-weight:700}
p{margin:4px 0;color:#5b7480}
a{color:#0b4f55;font-weight:600}
</style>
</head>
<body>
<div class="box">
  <div class="m">R</div>
  <p><b>站点已收缩，只保留胸片阅片。</b></p>
  <p><a href="__TARGET__">正在进入胸片阅片…</a></p>
</div>
<script>location.replace("__TARGET__");</script>
</body>
</html>
"""


def write_redirect(path: Path, target: str, title: str = "已收缩至胸片阅片") -> None:
    path.write_text(
        REDIRECT.replace("__TARGET__", target).replace("__TITLE__", title),
        encoding="utf8",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    for name in ASSETS:
        src = SRC / name
        if not src.exists():
            raise SystemExit("missing clinic asset: %s" % src)
        shutil.copy2(src, OUT / name)

    shutil.copy2(SRC / "clinic.html", OUT / "clinic.html")
    shutil.copy2(SRC / "exam.html", OUT / "exam.html")
    shutil.copy2(SRC / "compare.html", OUT / "compare.html")
    shutil.copy2(SRC / "classroom.html", OUT / "classroom.html")
    shutil.copy2(SRC / "qc.html", OUT / "qc.html")
    shutil.copy2(SRC / "blind.html", OUT / "blind.html")
    shutil.copy2(SRC / "dual.html", OUT / "dual.html")
    shutil.copy2(SRC / "drill.html", OUT / "drill.html")
    shutil.copy2(SRC / "path.html", OUT / "path.html")
    shutil.copy2(SRC / "evidence.html", OUT / "evidence.html")

    # 旧四页与 read 入口全部收敛到 clinic
    for page in LEGACY_PAGES:
        write_redirect(OUT / page, "clinic.html")

    # 胸片逐区数据：页面只读这一份
    chest = ROOT / "kb/data/chest_reading.json"
    if not chest.exists():
        raise SystemExit("missing kb/data/chest_reading.json; run build_chest_reading.py first")
    dst = SITE / "data/chest/chest_reading.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(chest, dst)
    data = json.loads(chest.read_text(encoding="utf8"))

    # 预生成的交叉检验数据（传统算法 + 深度模型），缺失不阻断构建
    for extra in ("lesion_probe.json", "model_probe.json", "dual_source.json", "drill_bank.json"):
        p = ROOT / "kb/data" / extra
        if p.exists():
            shutil.copy2(p, dst.parent / extra)

    # 只复制数据实际引用的胸片，不搬 120 例全库影像
    copied = 0
    for case in data["cases"]:
        rel = case["image"]  # images/case-xxx.jpg
        src = ROOT / "kb" / rel
        if not src.exists():
            print("missing image:", src)
            continue
        target = SITE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied += 1

    # 病例题：数据 + 影像
    exam = ROOT / "kb/data/exam_cases.json"
    if not exam.exists():
        raise SystemExit("missing kb/data/exam_cases.json; run build_exam_cases.py first")
    exam_dst = SITE / "data/exam/exam_cases.json"
    exam_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exam, exam_dst)
    exam_data = json.loads(exam.read_text(encoding="utf8"))
    exam_copied = 0
    for case in exam_data["cases"]:
        rel = case["image"]
        src = ROOT / "kb" / rel
        if not src.exists():
            print("missing exam image:", src)
            continue
        target = SITE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        exam_copied += 1

    # 学生影像实验室：问答索引 + 规则题
    lab = ROOT / "kb/data/student_lab.json"
    if not lab.exists():
        raise SystemExit("missing kb/data/student_lab.json; run build_student_lab.py first")
    lab_dst = SITE / "data/lab/student_lab.json"
    lab_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(lab, lab_dst)

    # 质控复核队列：AI 预标注 + 专家复核入口
    review = SITE / "data/audit/review_queue.json"
    if not review.exists():
        print("missing outputs/medtrain/data/audit/review_queue.json; run kb/scripts/build_review_queue.py")

    attribution = ROOT / "kb/licenses/EXAM_ATTRIBUTION.md"
    if attribution.exists():
        shutil.copy2(attribution, SITE / "EXAM_ATTRIBUTION.md")

    print("clinic + exam + compare + classroom + student lab, %d assets, %d chest images, %d exam images, %d cases"
          % (len(ASSETS), copied, exam_copied, len(data["cases"])))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
