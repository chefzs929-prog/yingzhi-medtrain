#!/usr/bin/env python3
"""病例题 + 对比阅片 · 端到端验收。

前置：
  cd outputs/medtrain && python3 -m http.server 8811
运行：
  python3 medtrain/tests/exam_check.py
输出：
  outputs/medtrain/exam_check.md

覆盖：
  - 病例题 10 例大纲、10 格答题卡、5 个选项、影像可读；
  - 选对 / 选错、提交反馈、正确答案、影像所见、出处与对比入口；
  - 答题记录写入 localStorage，刷新后保留；
  - “只看错题”、重做、清空记录；
  - 对比阅片默认配对、同高对齐、同步缩放、胶片条拖拽、并排 / 叠加擦除、隐藏诊断、交换、分隔条；
  - 无 console / page error 与 4xx。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/exam_check.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")
DATA = json.loads((ROOT / "kb/data/exam_cases.json").read_text(encoding="utf8"))
CASES = DATA["cases"]

rows: list[tuple[str, bool, str]] = []


GEOM_JS = """() => {
  const out = {};
  ['left', 'right'].forEach((s) => {
    const img = document.querySelector(s === 'left' ? '#leftImg' : '#rightImg');
    const cv = document.querySelector(s === 'left' ? '#paneLeft .pane-canvas' : '#paneRight .pane-canvas');
    const a = img.getBoundingClientRect();
    const c = cv.getBoundingClientRect();
    out[s] = {
      w: a.width, h: a.height, cy: a.top + a.height / 2,
      ch: c.height, inside: a.top >= c.top - 1 && a.bottom <= c.bottom + 1,
    };
  });
  return out;
}"""



def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))
    print(("  ✓ " if ok else "  ✗ ") + name + (("  " + detail) if detail and not ok else ""))


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()
        errors: list[str] = []
        bad: list[tuple[int, str]] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("response", lambda r: bad.append((r.status, r.url)) if r.status >= 400 else None)

        # ---------- 病例题 ----------
        page.goto(BASE + "read/exam.html", wait_until="networkidle")
        page.evaluate("localStorage.clear()")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(500)

        check("病例题页加载", page.title().startswith("病例题"), page.title())
        check("大纲 10 条", page.locator(".syl-item").count() == 10, str(page.locator(".syl-item").count()))
        check("答题卡 10 格", page.locator(".sheet-cell").count() == 10, str(page.locator(".sheet-cell").count()))
        check("选项 5 个", page.locator(".opt").count() == 5, str(page.locator(".opt").count()))
        check("首例为正常胸片", page.inner_text("#caseNo").startswith("EX-01"), page.inner_text("#caseNo"))
        check("影像已加载", page.eval_on_selector("#img", "e=>e.complete && e.naturalWidth>0"))
        check("影像载入提示已隐藏", not page.locator("#imgEmpty").is_visible())

        # 选对
        page.click('.opt[data-i="0"]')
        check("选择后提交按钮可用", not page.locator("#submitBtn").is_disabled())
        page.click("#submitBtn")
        page.wait_for_timeout(400)
        check("提交后反馈可见", page.locator("#feedback").is_visible())
        check("回答正确横幅", "回答正确" in page.inner_text("#feedback"))
        check("答题卡标记正确", page.locator(".sheet-cell.right").count() == 1,
              str(page.locator(".sheet-cell.right").count()))
        check("反馈含影像所见", "影像所见" in page.inner_text("#feedback"))
        check("反馈含原始页面链接", page.locator("#feedback a[href*='commons.wikimedia.org']").count() >= 1)
        check("反馈含对比入口", page.locator("#feedback .fb-compare a").count() >= 1)

        # 下一题选错
        page.click("#nextBtn")
        page.wait_for_timeout(300)
        check("下一题为肺炎", page.inner_text("#caseNo").startswith("EX-02"), page.inner_text("#caseNo"))
        page.click('.opt[data-i="0"]')  # 正常胸片（错误）
        page.click("#submitBtn")
        page.wait_for_timeout(400)
        fb = page.inner_text("#feedback")
        check("回答错误横幅", "回答错误" in fb)
        check("给出正确答案 B", "正确答案：B" in fb, fb[:200])
        check("答题卡标记错误", page.locator(".sheet-cell.wrong").count() == 1,
              str(page.locator(".sheet-cell.wrong").count()))

        # 只看错题
        page.click("#wrongOnly")
        page.wait_for_timeout(300)
        check("只看错题：非错题变暗", page.locator(".sheet-cell.dim").count() == 9,
              str(page.locator(".sheet-cell.dim").count()))
        check("只看错题按钮文案", "显示全部" in page.inner_text("#wrongOnly"), page.inner_text("#wrongOnly"))
        page.click("#wrongOnly")
        page.wait_for_timeout(200)

        # 刷新保留
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(500)
        check("刷新后保留 1 对 1 错", page.locator(".sheet-cell.right").count() == 1 and
              page.locator(".sheet-cell.wrong").count() == 1,
              f"right={page.locator('.sheet-cell.right').count()} wrong={page.locator('.sheet-cell.wrong').count()}")

        # 清空
        page.on("dialog", lambda d: d.accept())
        page.click("#resetBtn")
        page.wait_for_timeout(400)
        check("清空记录", page.locator(".sheet-cell.right").count() == 0 and
              page.locator(".sheet-cell.wrong").count() == 0)

        # 每例都能加载
        for c in CASES:
            page.click(f'.syl-item[data-case="{c["id"]}"]')
            page.wait_for_timeout(120)
            ok = (page.inner_text("#caseNo").startswith(c["id"]) and
                  page.eval_on_selector("#img", "e=>e.complete && e.naturalWidth>0") and
                  page.locator(".opt").count() == 5)
            check(f"{c['id']} 加载 / 选项 5 / 影像可读", ok,
                  f"title={page.inner_text('#caseNo')}")

        check("病例题无 console / page error", not errors, "；".join(errors[:3]))
        check("病例题无 4xx", not bad, str(bad[:3]))

        # ---------- 对比阅片 ----------
        page.goto(BASE + "read/compare.html", wait_until="networkidle")
        page.wait_for_timeout(500)
        check("对比页加载", page.title().startswith("对比阅片"), page.title())
        check("胶片条 10 例", page.locator(".film-card").count() == 10,
              str(page.locator(".film-card").count()))
        check("预置 8 组", page.locator(".pair-chip").count() == 8,
              str(page.locator(".pair-chip").count()))
        check("默认配对为肺炎 vs 结核",
              page.inner_text("#leftId") == "EX-02" and page.inner_text("#rightId") == "EX-03",
              page.inner_text("#leftId") + " / " + page.inner_text("#rightId"))
        check("两侧影像可读",
              page.eval_on_selector("#leftImg", "e=>e.complete && e.naturalWidth>0") and
              page.eval_on_selector("#rightImg", "e=>e.complete && e.naturalWidth>0"))

        # 同高对齐：两侧显示高度一致、中心落在同一水平线、都不被裁切
        g = page.evaluate(GEOM_JS)
        check("两侧影像同高对齐", abs(g["left"]["h"] - g["right"]["h"]) <= 1.5,
              f"{g['left']['h']:.1f} vs {g['right']['h']:.1f}")
        check("两侧影像同中线", abs(g["left"]["cy"] - g["right"]["cy"]) <= 1.5,
              f"{g['left']['cy']:.1f} vs {g['right']['cy']:.1f}")
        check("对齐后两侧均不裁切", g["left"]["inside"] and g["right"]["inside"], json.dumps(g, ensure_ascii=False))

        # 拖拽
        page.locator('.film-card[data-case="EX-05"]').drag_to(page.locator('.pane-canvas[data-side="right"]'))
        page.wait_for_timeout(400)
        check("拖拽后右侧为气胸", page.inner_text("#rightId") == "EX-05", page.inner_text("#rightId"))
        check("自由对比标题出现", "气胸" in page.inner_text("#diffTitle"), page.inner_text("#diffTitle"))

        # 叠加擦除
        page.click('[data-mode="overlay"]')
        page.wait_for_timeout(250)
        check("切换到叠加擦除", page.get_attribute("#stage", "data-mode") == "overlay")
        check("叠加模式两侧影像仍可见",
              page.locator("#leftImg").is_visible() and page.locator("#rightImg").is_visible())

        # 隐藏诊断
        page.click("#revealBtn")
        page.wait_for_timeout(250)
        check("隐藏诊断后不显示病名", "病例 EX-" in page.inner_text("#leftTopic"), page.inner_text("#leftTopic"))
        check("隐藏诊断提示可见", "诊断已隐藏" in page.inner_text("#leftDiag"))
        page.click("#revealBtn")
        page.wait_for_timeout(200)

        # 交换
        before_l = page.inner_text("#leftId")
        before_r = page.inner_text("#rightId")
        page.click("#swapBtn")
        page.wait_for_timeout(250)
        check("交换左右", page.inner_text("#leftId") == before_r and page.inner_text("#rightId") == before_l,
              f"{before_l}/{before_r} -> {page.inner_text('#leftId')}/{page.inner_text('#rightId')}")

        # 分隔条
        box = page.locator("#split").bounding_box()
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 + 160, box["y"] + box["height"] / 2, steps=5)
            page.mouse.up()
            page.wait_for_timeout(200)
            pct = int(page.inner_text("#splitPct").replace("%", ""))
            check("分隔条可拖动", pct > 50, page.inner_text("#splitPct"))
        else:
            check("分隔条可拖动", False, "split 不可见")

        # 宽幅 / 竖幅混排：用户反馈的错位场景（EX-07 1.33 : EX-01 0.87）
        page.goto(BASE + "read/compare.html?left=EX-07&right=EX-01", wait_until="networkidle")
        page.wait_for_timeout(700)
        g = page.evaluate(GEOM_JS)
        check("宽窄幅混排仍同高", abs(g["left"]["h"] - g["right"]["h"]) <= 1.5,
              f"{g['left']['h']:.1f} vs {g['right']['h']:.1f}")
        check("宽窄幅混排同中线", abs(g["left"]["cy"] - g["right"]["cy"]) <= 1.5,
              f"{g['left']['cy']:.1f} vs {g['right']['cy']:.1f}")
        check("宽幅影像不被上下裁切", g["left"]["inside"] and g["right"]["inside"],
              json.dumps(g, ensure_ascii=False))

        # 缩放同步：在左侧滚轮放大，两侧 transform 必须一致
        lb = page.locator('#paneLeft .pane-canvas').bounding_box()
        if lb:
            page.mouse.move(lb["x"] + lb["width"] / 2, lb["y"] + lb["height"] / 2)
            page.mouse.wheel(0, -240)
            page.wait_for_timeout(250)
            tl = page.eval_on_selector("#leftImg", "e=>e.style.transform")
            tr = page.eval_on_selector("#rightImg", "e=>e.style.transform")
            check("缩放两侧同步", tl == tr and "scale(1)" not in tl, f"{tl} / {tr}")
            check("放大后仍同中线", abs(
                page.eval_on_selector("#leftImg", "e=>e.getBoundingClientRect().top + e.getBoundingClientRect().height/2") -
                page.eval_on_selector("#rightImg", "e=>e.getBoundingClientRect().top + e.getBoundingClientRect().height/2")
            ) <= 1.5)
            page.click("#fitBtn")
            page.wait_for_timeout(200)
            g2 = page.evaluate(GEOM_JS)
            check("复位视图后回到同高", abs(g2["left"]["h"] - g2["right"]["h"]) <= 1.5)
        else:
            check("缩放两侧同步", False, "画布不可见")

        # 取消对齐后允许各自铺满
        page.click("#alignBtn")
        page.wait_for_timeout(250)
        check("可取消对齐", page.get_attribute("#stage", "data-align") == "off")
        page.click("#alignBtn")
        page.wait_for_timeout(250)
        check("可恢复对齐", page.get_attribute("#stage", "data-align") == "on")

        # 预置对比卡
        page.click('.pair-chip[data-pair="P-06"]')
        page.wait_for_timeout(300)
        check("预置二尖瓣 vs 主动脉型", page.inner_text("#diffTitle").startswith("二尖瓣型心 vs 主动脉型心"),
              page.inner_text("#diffTitle"))
        check("鉴别表有行", page.locator(".diff-row").count() >= 5, str(page.locator(".diff-row").count()))

        check("对比页无 console / page error", not errors, "；".join(errors[:3]))
        check("对比页无 4xx", not bad, str(bad[:3]))

        browser.close()

    passed = sum(1 for _, ok, _ in rows if ok)
    total = len(rows)
    lines = [
        "# 病例题 + 对比阅片 · 端到端验收",
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
        "> 本验收只证明静态页面、题目数据与对比交互可复现，不证明影像诊断准确率；",
        "> 题目按公开大纲与公开例题题型自编，正式教学前须由医学人员逐条审核。",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"\n{passed}/{total} passed -> {OUT}")
    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
