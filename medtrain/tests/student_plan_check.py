#!/usr/bin/env python3
"""学生端错题归因 / 7 天计划 / 能力雷达验收。

前置：在 outputs/medtrain 启动静态服务器（默认 8811）。
运行：python3 medtrain/tests/student_plan_check.py
输出：outputs/medtrain/student_plan_check.md
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/student_plan_check.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))
    print(("  ✓ " if ok else "  ✗ ") + name + (("  " + detail) if detail and not ok else ""))


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        errs: list[str] = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

        page.goto(BASE + "read/classroom.html?role=teacher", wait_until="networkidle")
        page.wait_for_timeout(700)
        page.evaluate("""async () => {
          localStorage.removeItem('radiocheck.classroom.v1');
          const c = window.RCClass.createClass('计划测试班', '李老师');
          const s = window.RCClass.addStudent(c.id, '小周').student;
          const a = window.RCClass.createAssignment({classId:c.id, title:'胸片基础', caseIds:['CASE-001','CASE-002','CASE-036'], due:'2026-12-01', passScore:60}).assignment;
          window.RCClass.setActiveStudent(c.id, s.id);
          window.RCClass.setRole('student');
          const data = await fetch('../data/chest/chest_reading.json', {cache:'no-cache'}).then(r=>r.json());
          const cases = data.cases.filter(x => x.enabled && ['CASE-001','CASE-002','CASE-036'].includes(x.id));
          for (const cc of cases) {
            const ans = window.RCClass.caseAnswer(cc);
            const wrong = {zoneId: cc.zones.find(z=>z.status==='abnormal')?.id || 'none', status:'normal', signs:[]};
            const use = cc.id === 'CASE-001' ? ans : wrong;
            const g = window.RCClass.gradeCase(cc, use);
            window.RCClass.saveAttempt({classId:c.id, assignmentId:a.id, studentId:s.id, caseId:cc.id, answers:use, score:g.score, detail:g.detail});
          }
          location.href = location.pathname + '?role=student';
        }""")
        page.wait_for_timeout(1800)
        check("能力雷达渲染", page.locator(".radar-svg").count() == 1, str(page.locator(".radar-svg").count()))
        check("雷达四维标签", all(t in page.inner_text(".radar-wrap") for t in ["定位", "判读", "征象", "依据"]))
        check("7 天计划渲染", page.locator(".plan-day").count() == 7, str(page.locator(".plan-day").count()))
        check("归因标签渲染", page.locator(".plan-tag").count() >= 3, str(page.locator(".plan-tag").count()))
        check("错题本有条目", page.locator(".error-row").count() >= 1, str(page.locator(".error-row").count()))
        check("计划可跳转重练", page.locator(".plan-item").count() >= 1 and "clinic.html" in page.locator(".plan-item").first.get_attribute("href"))
        check("依据口径写明行为代理", "行为代理" in page.inner_text(".radar-wrap"))
        check("无 console/page error", not errs, "; ".join(errs[:3]))
        page.screenshot(path=str(ROOT / ".deepworks/tmp/student_plan.png"), full_page=False)
        browser.close()

    lines = ["# 学生端错题归因与能力雷达验收 · 2026-11-23", "", "| 检查 | 结果 | 说明 |", "| --- | --- | --- |"]
    for name, ok, detail in rows:
        lines.append(f"| {name} | {'通过' if ok else '失败'} | {detail} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    if not all(ok for _, ok, _ in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
