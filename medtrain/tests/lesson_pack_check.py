#!/usr/bin/env python3
"""教师备课包导出验收。

前置：在 outputs/medtrain 启动静态服务器（默认 8811）。
运行：python3 medtrain/tests/lesson_pack_check.py
输出：outputs/medtrain/lesson_pack_check.md
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/lesson_pack_check.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))
    print(("  ✓ " if ok else "  ✗ ") + name + (("  " + detail) if detail and not ok else ""))


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 950}, accept_downloads=True)
        page = ctx.new_page()
        errs: list[str] = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

        page.goto(BASE + "read/classroom.html?role=teacher", wait_until="networkidle")
        page.wait_for_timeout(700)
        page.evaluate("""() => {
          localStorage.removeItem('radiocheck.classroom.v1');
          const c = window.RCClass.createClass('备课测试班', '王老师');
          window.RCClass.createAssignment({
            classId: c.id, title: '胸片基础：定位与征象',
            caseIds: ['CASE-001','CASE-002','CASE-036'], due: '2026-12-01', passScore: 60,
            note: '先定位，再判读，最后选征象'
          });
          location.reload();
        }""")
        page.wait_for_timeout(1200)
        page.wait_for_selector('[data-act="export-lesson"]', timeout=8000)
        check("教师端出现备课包按钮", page.locator('[data-act="export-lesson"]').count() >= 1)

        with page.expect_download(timeout=8000) as dl:
            page.locator('[data-act="export-lesson"]').first.click()
        download = dl.value
        path = download.path()
        text = Path(path).read_text(encoding="utf8")
        check("文件名含备课包", "备课包" in download.suggested_filename, download.suggested_filename)
        check("包含标题", "胸片基础：定位与征象" in text)
        check("包含病例", "CASE-001" in text and "CASE-036" in text)
        check("包含分区表", "| 分区 | 状态 | 来源文本 | 依据 |" in text)
        check("包含证据锚点", "E1：" in text and ("L1：" in text))
        check("包含题目与答案", "### 题目与答案" in text and "定位：" in text)
        check("包含讲评提示", "### 讲评提示" in text)
        check("包含未提及提醒", "来源未逐区提及" in text)
        check("无 console/page error", not errs, "; ".join(errs[:3]))
        browser.close()

    lines = ["# 教师备课包验收 · 2026-11-23", "", "| 检查 | 结果 | 说明 |", "| --- | --- | --- |"]
    for name, ok, detail in rows:
        lines.append(f"| {name} | {'通过' if ok else '失败'} | {detail} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    if not all(ok for _, ok, _ in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
