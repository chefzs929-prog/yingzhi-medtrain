#!/usr/bin/env python3
"""全站收缩验收：一个首页 + 一个胸片工作台。

前置：
  cd outputs/medtrain && python3 -m http.server 8811
运行：
  python3 medtrain/tests/site_check.py
输出：
  outputs/medtrain/site_check.md
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/site_check.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))
    print(("  ✓ " if ok else "  ✗ ") + name + (("  " + detail) if detail and not ok else ""))


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950})

        errors: list[str] = []
        bad: list[tuple[int, str]] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("response", lambda r: bad.append((r.status, r.url)) if r.status >= 400 else None)

        # 首页
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(300)
        check("首页加载", page.title() == "RadioCheck · 胸片阅片", page.title())
        links = set(page.eval_on_selector_all("a[href]", "els=>els.map(e=>e.getAttribute('href'))"))
        expected = {"./", "#method", "read/clinic.html"}
        check("首页只保留必要链接", links == expected, str(links))
        check("首页无旧功能入口", not any(x in " ".join(links) for x in ("app.html", "teach", "paper", "compare")), str(links))

        # 工作台
        page.goto(BASE + "read/clinic.html", wait_until="networkidle")
        page.wait_for_timeout(700)
        nav = page.eval_on_selector_all(
            "nav.switch a", "els=>els.map(e=>[e.textContent.trim(),e.getAttribute('href')])"
        )
        check("工作台导航只有两项", len(nav) == 2, str(nav))
        check("工作台导航为阅片+边界", [n[0] for n in nav] == ["胸片阅片", "方法与边界"], str(nav))
        check("胸片队列 21 例", page.locator("[data-case]").count() == 21, str(page.locator("[data-case]").count()))
        check("影像已加载", page.eval_on_selector("#img", "e=>e.complete && e.naturalWidth>0"))
        check("首页/工作台无 console error", not errors, str(errors[:3]))
        check("首页/工作台无 4xx", not bad, str(bad[:3]))

        # 旧入口全部跳转
        legacy = [
            "app.html", "read/index.html", "read/teach.html",
            "read/paper.html", "read/compare.html", "dev/student.html",
        ]
        for path in legacy:
            page.goto(BASE + path, wait_until="networkidle")
            page.wait_for_timeout(250)
            check("%s 跳转到 clinic" % path, page.url.endswith("/read/clinic.html"), page.url)

        # manifest 只保留一个快捷方式
        manifest = json.loads((ROOT / "outputs/medtrain/manifest.webmanifest").read_text(encoding="utf8"))
        check("manifest start_url 指向 clinic", manifest["start_url"] == "./read/clinic.html", manifest["start_url"])
        check("manifest 只有 1 个快捷方式", len(manifest["shortcuts"]) == 1, str(len(manifest["shortcuts"])))

        # 构建目录只保留被引用的 clinic 资源
        read_dir = ROOT / "outputs/medtrain/read"
        leftovers = [p.name for p in read_dir.iterdir()
                     if p.suffix in (".css", ".js")
                     and p.name not in ("base.css", "clinic.css", "common.js", "locate.js", "clinic.js")]
        check("read/ 无旧页脚本残留", not leftovers, str(leftovers))

        browser.close()

    OUT.write_text(
        "# 全站收缩验收\n\n"
        "| # | 检查 | 结果 |\n| --- | --- | --- |\n"
        + "\n".join("| %d | %s | %s |" % (i + 1, n, "通过" if ok else "失败")
                    for i, (n, ok, _) in enumerate(rows))
        + "\n\n**%d/%d 通过**\n" % (sum(1 for _, ok, _ in rows if ok), len(rows)),
        encoding="utf8",
    )
    print("\n%d/%d passed -> %s" % (sum(1 for _, ok, _ in rows if ok), len(rows), OUT))
    raise SystemExit(0 if all(ok for _, ok, _ in rows) else 1)


if __name__ == "__main__":
    main()
