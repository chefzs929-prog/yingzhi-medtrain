#!/usr/bin/env python3
"""课堂 · 教师端 / 学生端 · 端到端验收。

前置：
  cd outputs/medtrain && python3 -m http.server 8811
运行：
  python3 medtrain/tests/classroom_check.py
输出：
  outputs/medtrain/classroom_check.md

覆盖：
  - 教师建班、添加学生、按病例布置作业；
  - 学生用班级码加入，打开作业；
  - 考核模式：病例标题隐藏、分区不着色、对照标签页锁定；
  - 三题作答、评分、提交后解锁；
  - 错误作答进入错题本，教师端学情分析可见；
  - 班级报告导出；
  - 无 console / page error。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/classroom_check.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")
DATA = json.loads((ROOT / "kb/data/chest_reading.json").read_text(encoding="utf8"))
CASES = {c["id"]: c for c in DATA["cases"] if c["enabled"]}

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))
    print(("  ✓ " if ok else "  ✗ ") + name + (("  " + detail) if detail and not ok else ""))


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(BASE + "read/classroom.html", wait_until="networkidle")
        page.evaluate("localStorage.clear()")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(300)
        check("课堂入口加载", page.title().startswith("课堂"), page.title())
        check("角色入口可见", page.locator("[data-act='role']").count() >= 2,
              str(page.locator("[data-act='role']").count()))

        # 教师建班
        page.click('[data-act="role"][data-role="teacher"]')
        page.wait_for_timeout(200)
        page.click('[data-act="create-class"]')
        page.wait_for_timeout(300)
        code_el = page.locator(".code-box b")
        check("教师建班并生成班级码", code_el.count() == 1 and code_el.inner_text().startswith("RC-"),
              code_el.inner_text() if code_el.count() else "无班级码")
        class_code = code_el.inner_text() if code_el.count() else ""

        page.fill("#newStudentName", "张同学")
        page.click('[data-act="add-student"]')
        page.wait_for_timeout(250)
        check("添加学生", "张同学" in page.inner_text("#classroomMain"))

        # 布置作业
        page.click('[data-teacher-tab="assign"]')
        page.wait_for_timeout(250)
        page.fill("#assignTitle", "胸片基础：定位与征象")
        page.click('[data-preset="demo"]')
        page.wait_for_timeout(150)
        check("推荐 6 例", page.locator("#pickCount").inner_text() == "已选 6 例",
              page.locator("#pickCount").inner_text())
        page.click('[data-act="create-assignment"]')
        page.wait_for_timeout(400)
        check("发布作业并进入学情", "逐例分析" in page.inner_text("#classroomMain") or
              "还没有学生提交" in page.inner_text("#classroomMain"),
              page.inner_text("#classroomMain")[:200])

        db = page.evaluate("JSON.parse(localStorage.getItem('radiocheck.classroom.v1'))")
        cls = db["classes"][0]
        assignment = cls["assignments"][0]
        student = cls["students"][0]
        check("作业写入 6 例", len(assignment["caseIds"]) == 6, str(assignment["caseIds"]))

        # 学生加入
        page.click('#roleSwitch [data-role="student"]')
        page.wait_for_timeout(250)
        page.fill("#joinName", "新同学")
        page.fill("#joinCode", class_code)
        page.click('[data-act="join-class"]')
        page.wait_for_timeout(350)
        check("学生用班级码加入", "学生端 · 我的作业" in page.inner_text("#classroomMain"),
              page.inner_text("#classroomMain")[:160])
        db2 = page.evaluate("JSON.parse(localStorage.getItem('radiocheck.classroom.v1'))")
        joined = [s for s in db2["classes"][0]["students"] if s["name"] == "新同学"]
        check("新学生写入班级名单", len(joined) == 1, str([s["name"] for s in db2["classes"][0]["students"]]))
        check("学生看到作业", assignment["title"] in page.inner_text("#classroomMain"))
        href = page.locator("a.btn.primary").first.get_attribute("href")
        check("作业链接带 task 与 student", "task=" in href and "student=" in href, href or "")

        # 考核模式
        page.goto(BASE + "read/" + href, wait_until="networkidle")
        page.wait_for_timeout(700)
        check("课堂任务横幅", "课堂任务" in page.inner_text("#taskBanner"), page.inner_text("#taskBanner")[:120])
        check("病例标题隐藏", "考核病例 1" in page.inner_text("#caseTitle"), page.inner_text("#caseTitle"))
        check("分区全部不着色", page.locator(".zone").count() == page.locator(".zone.quiz").count(),
              f"zones={page.locator('.zone').count()} quiz={page.locator('.zone.quiz').count()}")
        hidden = page.eval_on_selector_all("#tabs button", "els=>els.map(e=>[e.textContent,e.hidden])")
        check("对照标签页锁定", all(h for t, h in hidden if t != "课堂任务"), str(hidden))
        check("来源行隐藏", "提交后显示来源" in page.inner_text("#srcLine"), page.inner_text("#srcLine"))

        # 第一例 CASE-001：全对
        page.click('[data-quiz-zone="none"]')
        page.click('[data-quiz-status="normal"]')
        page.click('[data-quiz-sign="none"]')
        page.wait_for_timeout(120)
        check("三题作答后可提交", not page.locator("#quizSubmit").is_disabled())
        page.click("#quizSubmit")
        page.wait_for_timeout(500)
        result = page.inner_text("#panelBody")
        check("第一例 100 分", "100/100" in result, result[:240])
        check("提交后揭示标题", page.inner_text("#caseTitle") == CASES["CASE-001"]["title"],
              page.inner_text("#caseTitle"))
        check("提交后分区着色恢复", page.locator(".zone.quiz").count() == 0,
              str(page.locator(".zone.quiz").count()))
        unlocked = page.eval_on_selector_all("#tabs button", "els=>els.map(e=>e.hidden)")
        check("提交后对照标签页解锁", not any(unlocked), str(unlocked))

        # 第二例 CASE-006：先验证分区可多选，再故意答错
        page.click("[data-quiz-next]")
        page.wait_for_timeout(500)
        check("进入第二例", "考核病例 2" in page.inner_text("#caseTitle"), page.inner_text("#caseTitle"))
        page.click('.zone[data-zone="RML"]')
        page.click('.zone[data-zone="RLL"]')
        page.wait_for_timeout(200)
        check("分区题可多选", page.locator(".zone.on").count() == 2, str(page.locator(".zone.on").count()))
        check("多选分区提示", "2 个分区" in page.inner_text("#bboxMeta"), page.inner_text("#bboxMeta"))
        page.click('[data-quiz-zone="none"]')
        page.click('[data-quiz-status="normal"]')
        page.click('[data-quiz-sign="none"]')
        page.click("#quizSubmit")
        page.wait_for_timeout(500)
        wrong = page.inner_text("#panelBody")
        check("第二例错误作答得低分", "100/100" not in wrong and "/100" in wrong, wrong[:240])
        check("错误作答显示正确答案", "正确答案" in wrong, wrong[:240])

        # 回学生端看进度与错题
        page.goto(BASE + "read/classroom.html?role=student", wait_until="networkidle")
        page.wait_for_timeout(500)
        student_text = page.inner_text("#classroomMain")
        check("学生完成 2/6", "2/6" in student_text, student_text[:400])
        check("错题本出现 CASE-006", "CASE-006" in student_text, student_text[:600])
        check("错题本给出重练入口", page.locator("a.btn", has_text="重练").count() >= 1)

        # 教师学情
        page.click('#roleSwitch [data-role="teacher"]')
        page.wait_for_timeout(300)
        page.click('[data-teacher-tab="analysis"]')
        page.wait_for_timeout(400)
        teacher = page.inner_text("#classroomMain")
        check("教师学情有提交率", "提交率" in teacher and "2/6" in teacher, teacher[:400])
        check("教师逐例分析可见", "逐例分析" in teacher and "CASE-006" in teacher, teacher[:800])
        check("教师错题讲评可见", "错题与讲评" in teacher and "状态判断错误" in teacher, teacher[:900])
        check("教师名单包含新加入学生", "新同学" in teacher, teacher[:500])

        # 导出报告
        with page.expect_download(timeout=8000) as dl:
            page.click('[data-act="export-report"]')
        download = dl.value
        check("班级报告可导出", download.suggested_filename.endswith(".md"),
              download.suggested_filename)

        # 课堂数据 JSON 导出 / 导入
        with page.expect_download(timeout=8000) as dl2:
            page.click("#exportClassroom")
        json_dl = dl2.value
        check("课堂数据可导出 JSON", json_dl.suggested_filename.endswith(".json"),
              json_dl.suggested_filename)
        export_path = ROOT / ".deepworks/tmp/classroom_export_test.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        json_dl.save_as(str(export_path))
        check("课堂数据 JSON 非空", export_path.exists() and export_path.stat().st_size > 100,
              str(export_path.stat().st_size if export_path.exists() else 0))
        page.set_input_files("#importClassroom", str(export_path))
        page.wait_for_timeout(1400)
        restored = page.inner_text("#classroomMain")
        check("课堂数据可导入恢复", "2026 春季影像规培班" in restored or "演示" in restored,
              restored[:300])

        # 窄屏顶栏：导入/导出不能被挤出可视区
        page.set_viewport_size({"width": 1024, "height": 900})
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(500)
        boxes = [
            page.locator("#exportClassroom").bounding_box(),
            page.locator("#importClassroomBtn").bounding_box(),
        ]
        check("窄屏导入导出按钮在可视区",
              all(b and b["x"] >= 0 and b["x"] + b["width"] <= 1024 for b in boxes),
              str(boxes))

        check("无 console / page error", not errors, "；".join(errors[:3]))
        browser.close()

    passed = sum(1 for _, ok, _ in rows if ok)
    total = len(rows)
    lines = [
        "# 课堂 · 教师端 / 学生端 · 端到端验收",
        "",
        f"> 生成时间：2026-11-22 ｜ 通过 {passed}/{total} ｜ 基址：{BASE}",
        "",
        "| # | 检查 | 结果 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for i, (name, ok, detail) in enumerate(rows, 1):
        lines.append(f"| {i} | {name} | {'通过' if ok else '**未通过**'} | {detail} |")
    lines += [
        "",
        "> 本验收只证明课堂流程、评分规则与本地数据回流可复现；",
        "> 不证明影像诊断准确率；正式教学前须由医学人员逐条审核。",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"\n{passed}/{total} passed -> {OUT}")
    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
