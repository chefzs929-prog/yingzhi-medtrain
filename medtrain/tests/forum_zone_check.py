#!/usr/bin/env python3
"""互助小组帖子关联分区/征象 + 阅片台跳转验收。

前置：在 outputs/medtrain 启动静态服务器（默认 8811）。
运行：python3 medtrain/tests/forum_zone_check.py
输出：outputs/medtrain/forum_zone_check.md
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/forum_zone_check.md"
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
        page.evaluate("""() => {
          localStorage.removeItem('radiocheck.classroom.v1');
          const c = window.RCClass.createClass('论坛测试班', '陈老师');
          const s = window.RCClass.addStudent(c.id, '小林').student;
          const g = window.RCClass.createGroup(c.id, {name:'胸片读片组', topic:'每周一组病例', studentId:s.id}).group;
          window.RCClass.createPost({
            classId:c.id, groupId:g.id, studentId:s.id,
            title:'CASE-006 右肺中野密度增高，实变还是积液？',
            body:'我先看空气支气管征，再看肋膈角；请帮我确认分区。',
            caseId:'CASE-006', zoneId:'RML', zoneName:'右肺中野',
            signId:'SIGN-002', signName:'实变'
          });
          window.RCClass.setActiveStudent(c.id, s.id);
          window.RCClass.setRole('student');
          location.href = location.pathname + '?role=student';
        }""")
        page.wait_for_timeout(1500)
        page.click('[data-student-tab="group"]')
        page.wait_for_timeout(400)
        page.click('[data-group-open]')
        page.wait_for_timeout(400)
        check("帖子列表渲染", page.locator('[data-post-open]').count() >= 1)
        page.locator('[data-post-open]').first.click()
        page.wait_for_timeout(300)
        post_text = page.inner_text(".post-detail")
        check("帖子显示分区标签", "右肺中野" in post_text)
        check("帖子显示征象标签", "实变" in post_text)
        href = page.locator(".post-case").get_attribute("href")
        check("帖子链接带 zone 参数", "zone=RML" in (href or ""), href or "")
        check("帖子链接带 case 参数", "case=CASE-006" in (href or ""), href or "")

        # 表单动态填充
        page.click("[data-post-back]")
        page.wait_for_timeout(300)
        before = page.locator("#postZone option").count()
        page.select_option("#postCase", "CASE-006")
        page.wait_for_timeout(300)
        after = page.locator("#postZone option").count()
        check("选病例后分区下拉填充", after > before and after >= 2, f"{before} -> {after}")

        # 阅片台按 zone 打开并选中
        clinic = ctx.new_page()
        clinic_errs: list[str] = []
        clinic.on("pageerror", lambda e: clinic_errs.append(str(e)))
        clinic.goto(BASE + "read/" + (href or ""), wait_until="networkidle")
        clinic.wait_for_timeout(1200)
        selected = clinic.evaluate("document.querySelector('.zone.on')?.dataset.zone || ''")
        check("阅片台选中关联分区", selected == "RML", selected)
        check("阅片台无 page error", not clinic_errs, "; ".join(clinic_errs[:2]))
        check("课堂无 console/page error", not errs, "; ".join(errs[:3]))
        browser.close()

    lines = ["# 论坛关联分区/征象验收 · 2026-11-23", "", "| 检查 | 结果 | 说明 |", "| --- | --- | --- |"]
    for name, ok, detail in rows:
        lines.append(f"| {name} | {'通过' if ok else '失败'} | {detail} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    if not all(ok for _, ok, _ in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
