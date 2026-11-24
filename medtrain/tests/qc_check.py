#!/usr/bin/env python3
"""质控复核页端到端验收。

前置：在 outputs/medtrain 启动静态服务器（默认 8811）。
运行：python3 medtrain/tests/qc_check.py
输出：outputs/medtrain/qc_check.md
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/qc_check.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")
QUEUE = json.loads((ROOT / "outputs/medtrain/data/audit/review_queue.json").read_text(encoding="utf8"))

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))
    print(("  ✓ " if ok else "  ✗ ") + name + (("  " + detail) if detail and not ok else ""))


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page = context.new_page()
        errors: list[str] = []
        bad: list[tuple[int, str]] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("response", lambda r: bad.append((r.status, r.url)) if r.status >= 400 else None)

        page.goto(BASE + "read/qc.html", wait_until="networkidle")
        page.wait_for_selector("#qcList .qc-card", timeout=8000)
        cards = page.locator("#qcList .qc-card")
        check("复核队列渲染", cards.count() == len(QUEUE["items"]), f"{cards.count()} / {len(QUEUE['items'])}")
        check("统计卡渲染", page.locator(".qc-stat").count() >= 4, str(page.locator(".qc-stat").count()))
        check("冲突筛选可用", page.locator('[data-filter="conflict"]').count() == 1)
        check("双 AI 视角均显示", page.locator(".qc-ai-box").count() >= 2, str(page.locator(".qc-ai-box").count()))

        first = QUEUE["items"][0]
        iid = first["id"]
        page.select_option(f'[data-qc-label="{iid}"]', "not_mentioned")
        page.fill(f'[data-qc-note="{iid}"]', "端到端测试备注")
        page.fill("#reviewer", "自动测试")
        page.click(f'[data-qc-save="{iid}"]')
        page.wait_for_timeout(300)
        saved = page.evaluate("localStorage.getItem('radiocheck.qc.v1')")
        check("专家复核写入 localStorage", bool(saved) and iid in (saved or ""), (saved or "")[:80])

        page.reload(wait_until="networkidle")
        page.wait_for_selector(f'[data-item="{iid}"]')
        check("刷新后复核状态保留", "已复核" in page.inner_text(f'[data-item="{iid}"]'))
        check("复核人保留", page.input_value("#reviewer") == "自动测试", page.input_value("#reviewer"))

        with page.expect_download(timeout=5000) as dl:
            page.click("#exportQc")
        download = dl.value
        check("导出 JSON 文件名正确", "质控复核" in download.suggested_filename, download.suggested_filename)
        path = download.path()
        exported = json.loads(Path(path).read_text(encoding="utf8"))
        check("导出包含专家字段", any(i["expert"]["status"] == "reviewed" for i in exported["items"]))
        check("导出包含 AI 预标注策略", bool(exported.get("policy")))

        page.locator('[data-filter="conflict"]').click()
        page.wait_for_timeout(200)
        conflict_cards = page.locator("#qcList .qc-card")
        check("冲突筛选只显示冲突", conflict_cards.count() == sum(1 for i in QUEUE["items"] if not i["agree"]),
              f"{conflict_cards.count()}")

        page.screenshot(path=str(ROOT / ".deepworks/tmp/qc.png"), full_page=False)
        check("无 console/page error", not errors, "; ".join(errors[:3]))
        check("无 4xx/5xx 资源", not bad, str(bad[:3]))

        browser.close()

    lines = ["# 质控复核页验收 · 2026-11-23", "", "| 检查 | 结果 | 说明 |", "| --- | --- | --- |"]
    for name, ok, detail in rows:
        lines.append(f"| {name} | {'通过' if ok else '失败'} | {detail} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    if not all(ok for _, ok, _ in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
