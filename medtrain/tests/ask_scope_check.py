#!/usr/bin/env python3
"""提问页范围拒答 · 端到端验收。

前置：在 outputs/medtrain 启动静态或动态服务器（默认 8811）。
运行：python3 medtrain/tests/ask_scope_check.py
输出：outputs/medtrain/ask_scope_check.md

覆盖：
  - 治疗 / 预后 / 操作建议必须拒答，不能落到“本片没有 X”的病例答案；
  - 非胸部部位必须拒答；
  - 定义类问题（怎么找 / 是什么）仍在范围内；
  - 分区问题仍能正常回答；
  - 无 console / page error。
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/ask_scope_check.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")

REFUSE = [
    ("这个气胸需要做胸腔闭式引流吗", "治疗 / 预后 / 操作建议"),
    ("气胸怎么治疗", "治疗 / 预后 / 操作建议"),
    ("需要吃什么药", "治疗 / 预后 / 操作建议"),
    ("要不要手术", "治疗 / 预后 / 操作建议"),
    ("肺癌能活多久", "治疗 / 预后 / 操作建议"),
    ("这个是不是癌", "诊断结论"),
    ("乳腺癌筛查", "非胸部部位"),
]

ANSWER = [
    ("气胸在胸片上怎么找", "气胸"),
    ("气胸和胸腔积液怎么区分", "胸腔积液"),
    ("右肺中野有什么问题", "右肺中野"),
]

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))
    print(("  ✓ " if ok else "  ✗ ") + name + (("  " + detail) if detail and not ok else ""))


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 1200})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(BASE + "read/ask.html", wait_until="networkidle")
        page.wait_for_timeout(700)
        check("提问页加载", page.title().startswith("提问"), page.title())

        for q, label in REFUSE:
            page.fill("#q", q)
            page.click("#ask")
            page.wait_for_timeout(450)
            text = page.inner_text("#result")
            check(f"拒答：{q}",
                  "不能回答" in text and label in text and "本片没有" not in text,
                  text.replace("\n", " ")[:160])

        for q, must in ANSWER:
            page.fill("#q", q)
            page.click("#ask")
            page.wait_for_timeout(450)
            text = page.inner_text("#result")
            check(f"可答：{q}", "可以回答" in text and must in text,
                  text.replace("\n", " ")[:160])

        check("无 console / page error", not errors, "；".join(errors[:3]))
        browser.close()

    passed = sum(1 for _, ok, _ in rows if ok)
    total = len(rows)
    lines = [
        "# 提问页范围拒答 · 端到端验收",
        "",
        f"> 基址：{BASE} ｜ 通过 {passed}/{total}",
        "",
        "| # | 检查 | 结果 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for i, (name, ok, detail) in enumerate(rows, 1):
        lines.append(f"| {i} | {name} | {'通过' if ok else '**未通过**'} | {detail} |")
    lines += [
        "",
        "> 本验收只证明范围拒答在提问页生效；不证明医学诊断准确率。",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"\n{passed}/{total} passed -> {OUT}")
    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
