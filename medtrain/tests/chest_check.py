#!/usr/bin/env python3
"""胸片阅片工作台 · 端到端验收。

前置：
  cd outputs/medtrain && python3 -m http.server 8811
运行：
  python3 medtrain/tests/chest_check.py
输出：
  outputs/medtrain/chest_ui_check.md

覆盖：
  - 21 例胸片逐例加载、分区数量、影像可读、无 console error；
  - 局灶病例只有病灶区异常；
  - 气胸病例右侧异常、左侧未提及；
  - 自然提问、越界拒答；
  - 阅片记录导出；
  - 库内上传 SHA-256 命中、陌生图明确拒绝；
  - 拖框命中分区。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/chest_ui_check.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")
DATA = json.loads((ROOT / "kb/data/chest_reading.json").read_text(encoding="utf8"))
CASES = [c for c in DATA["cases"] if c["enabled"]]

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))
    print(("  ✓ " if ok else "  ✗ ") + name + (("  " + detail) if detail and not ok else ""))


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(BASE + "read/clinic.html", wait_until="networkidle")
        page.wait_for_timeout(600)
        check("页面加载", page.title().startswith("胸片阅片工作台"), page.title())

        for c in CASES:
            cid = c["id"]
            page.click(f'[data-case="{cid}"]')
            page.wait_for_timeout(180)
            title = page.inner_text("#caseTitle")
            zones = page.locator(".zone").count()
            expected = 3 if c["pose"] == "LAT" else 8
            img_ok = page.evaluate(
                "() => { const i = document.querySelector('#img'); return !!(i && i.complete && i.naturalWidth > 0); }"
            )
            panel = page.inner_text("#panelBody").strip()
            check(f"{cid} 加载 / 分区 {expected} / 影像可读",
                  title != "正在载入…" and zones == expected and img_ok and bool(panel),
                  f"title={title} zones={zones} img={img_ok}")

        # 局灶病例
        page.click('[data-case="CASE-006"]')
        page.wait_for_timeout(250)
        classes = [page.locator(".zone").nth(i).get_attribute("class") for i in range(page.locator(".zone").count())]
        check("CASE-006 右肺中野/下野 abnormal、右肺上野 unmentioned",
              sum("abnormal" in x for x in classes) == 2 and "unmentioned" in classes[0],
              str(classes))
        page.click('[data-tab="qa"]')
        page.fill("#qaInput", "右肺中野有没有异常？")
        page.click("#qaSend")
        page.wait_for_timeout(250)
        qa = page.inner_text("#qaLog")
        check("CASE-006 右肺中野回答含“异常”", "右肺中野 · 异常" in qa, qa[-300:])
        page.fill("#qaInput", "右肺上野有没有异常？")
        page.click("#qaSend")
        page.wait_for_timeout(250)
        qa = page.inner_text("#qaLog")
        check("CASE-006 右肺上野回答为“来源未提及”", "右肺上野 · 来源未提及" in qa, qa[-300:])

        # 气胸病例
        page.click('[data-case="CASE-036"]')
        page.wait_for_timeout(250)
        classes = [page.locator(".zone").nth(i).get_attribute("class") for i in range(page.locator(".zone").count())]
        check("CASE-036 右侧三区 abnormal",
              sum("abnormal" in x for x in classes) == 3,
              str(classes))
        check("CASE-036 左侧三区 unmentioned",
              sum("unmentioned" in x for x in classes) >= 3,
              str(classes))
        page.click('[data-tab="qa"]')
        page.fill("#qaInput", "有没有气胸？")
        page.click("#qaSend")
        page.wait_for_timeout(250)
        qa = page.inner_text("#qaLog")
        check("CASE-036 气胸回答定位到右侧", "右侧" in qa and "气胸" in qa, qa[-300:])

        # 越界拒答
        page.fill("#qaInput", "是不是肺癌？要不要手术？")
        page.click("#qaSend")
        page.wait_for_timeout(250)
        qa = page.inner_text("#qaLog")
        check("诊断/治疗越界拒答", "超出本页范围" in qa, qa[-300:])

        # 阅片记录
        page.click("#reportBtn")
        page.wait_for_timeout(250)
        report = page.inner_text("#reportText")
        check("阅片记录可打开", page.locator("#reportMask").is_visible())
        check("阅片记录含病例与声明",
              "CASE-036" in report and "胸片阅片记录（教学用，非诊断）" in report and "不构成诊断意见" in report,
              report[:200])
        page.click("#reportClose")

        # 库内上传
        served = ROOT / "outputs/medtrain/images/case-001.jpg"
        page.set_input_files("#fileInput", str(served))
        page.wait_for_timeout(900)
        check("库内影像 SHA-256 命中 CASE-001", page.inner_text("#caseTitle") == "正常后前位胸片",
              page.inner_text("#caseTitle"))

        # 陌生上传
        foreign = ROOT / "outputs/medtrain/icons/icon-192.png"
        page.set_input_files("#fileInput", str(foreign))
        page.wait_for_timeout(900)
        panel = page.inner_text("#panelBody")
        # 静态站：未连接动态服务；动态站无视觉模型：先确认影像类型。
        # 两种都必须给 8 个通用分区，且不下异常结论。
        check("陌生影像进入通用定位",
              ("未连接视觉定位服务" in panel) or ("未确认影像类型" in panel),
              panel[:240])
        check("陌生影像给 8 个通用分区", page.locator("[data-generic-zone]").count() == 8,
              str(page.locator("[data-generic-zone]").count()))
        page.locator("[data-generic-zone]").first.click()
        page.wait_for_timeout(300)
        generic = page.inner_text(".generic-result")
        check("通用分区不下结论",
              "不含该影像的知识库标注" in generic and "不能据此判断有无异常" in generic,
              generic[:300])

        # 拖框
        page.click('[data-case="CASE-001"]')
        page.wait_for_timeout(300)
        box = page.locator("#frame").bounding_box()
        if box:
            x1 = box["x"] + box["width"] * 0.12
            y1 = box["y"] + box["height"] * 0.12
            x2 = box["x"] + box["width"] * 0.32
            y2 = box["y"] + box["height"] * 0.30
            page.mouse.move(x1, y1)
            page.mouse.down()
            page.mouse.move(x2, y2, steps=5)
            page.mouse.up()
            page.wait_for_timeout(300)
            check("拖框命中右肺上野", "右肺上野" in page.inner_text("#chainHint"),
                  page.inner_text("#chainHint"))
        else:
            check("拖框命中右肺上野", False, "frame 不可见")

        check("无 console / page error", not errors, "；".join(errors[:3]))
        browser.close()

    passed = sum(1 for _, ok, _ in rows if ok)
    total = len(rows)
    lines = [
        "# 胸片阅片工作台 · 端到端验收",
        "",
        f"> 生成时间：2026-11-20 ｜ 通过 {passed}/{total} ｜ 基址：{BASE}",
        "",
        "| # | 检查 | 结果 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for i, (name, ok, detail) in enumerate(rows, 1):
        lines.append(f"| {i} | {name} | {'通过' if ok else '**未通过**'} | {detail} |")
    lines += [
        "",
        "> 本验收只证明静态工作台与数据规则可复现，不证明影像诊断准确率；",
        "> 正式教学前须由医学人员逐条审核。",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"\n{passed}/{total} passed -> {OUT}")


if __name__ == "__main__":
    main()
