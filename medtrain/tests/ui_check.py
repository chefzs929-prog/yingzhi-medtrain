#!/usr/bin/env python3
"""影知多版本软件 · 逐版验收。

用法：
  cd outputs/medtrain
  python3 -m http.server 8800
  python3 ../../medtrain/tests/ui_check.py

也可以直接运行本脚本：若 8800 未启动，会自动在 outputs/medtrain 下起一个临时服务。
依赖：playwright（Python）。浏览器优先使用环境变量 PLAYWRIGHT_CHROMIUM_EXECUTABLE，
否则尝试 playwright 自带 chromium，最后回退到系统 Chrome for Testing。
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "medtrain"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8800/")
FAILS: list[str] = []
CHECKS = 0


def check(ok: bool, label: str, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if ok:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label} {detail}")
        FAILS.append(label + (" " + detail if detail else ""))


def wait_server(timeout: float = 8.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(BASE + "index.html", timeout=1) as r:
                return r.status == 200
        except Exception:
            time.sleep(0.2)
    return False


def ensure_server():
    if wait_server(1.0):
        return None
    print("· 8800 未启动，正在启动临时服务…")
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8800"],
        cwd=str(OUT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not wait_server(8.0):
        proc.terminate()
        raise SystemExit("无法启动本地服务，请手动运行：cd outputs/medtrain && python3 -m http.server 8800")
    return proc


def browser_executable():
    env = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if env and Path(env).exists():
        return env
    patterns = [
        str(Path.home() / "Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
        str(Path.home() / "Library/Caches/ms-playwright/chromium-*/chrome-linux/chrome"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def new_page(browser, width=1440, height=1000, mobile=False):
    ctx = browser.new_context(
        viewport={"width": width, "height": height},
        is_mobile=mobile,
        has_touch=mobile,
        device_scale_factor=2 if mobile else 1,
    )
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    return ctx, page, errors


def goto(page, path: str, wait=450):
    page.goto(BASE + path, wait_until="load")
    page.wait_for_timeout(wait)


def to_home(page):
    """应用默认落在多模态问答；旧用例验证首页与四链条时先回到首页。"""
    if page.locator(".ask").count():
        page.click('[data-act="nav"][data-view="home"]')
        page.wait_for_timeout(260)


def main() -> int:
    from playwright.sync_api import sync_playwright

    proc = ensure_server()
    exe = browser_executable()
    print(f"· 浏览器：{exe or 'playwright 默认'}")
    try:
        with sync_playwright() as p:
            kwargs = {"executable_path": exe} if exe else {}
            browser = p.chromium.launch(**kwargs)

            # 1. 产品首页
            print("\n[1] 产品首页")
            ctx, page, errs = new_page(browser, 1440, 1000)
            goto(page, "index.html")
            check(page.title().startswith("影知"), "标题正确")
            status_txt = page.inner_text("#bmStatus")
            n_svg = page.locator(".bm-region").count()
            if n_svg:
                check(n_svg == 5, "5 个人体部位（SVG 占位）", str(n_svg))
                check("SVG 占位" in status_txt, "模型状态如实标注（非 3D）", status_txt)
                page.locator('.bm-region[data-region="REG-CHEST"] .bm-hot path').click()
            else:
                # 3D 适配器已接入：模型本身无 DOM 热点，改用右栏部位入口验证联动
                check("3D 适配器" in status_txt, "3D 适配器状态如实标注", status_txt)
                check(page.locator("[data-pick-region]").count() == 5, "5 个部位入口", str(page.locator("[data-pick-region]").count()))
                page.locator('[data-pick-region="REG-CHEST"]').click()
            check(page.locator(".chain").count() == 4, "四链条卡片", str(page.locator(".chain").count()))
            check(page.locator(".role-card").count() == 3, "三端入口", str(page.locator(".role-card").count()))
            check(page.locator("#statRow b").count() == 6, "统计条 6 项", str(page.locator("#statRow b").count()))
            page.wait_for_timeout(200)
            panel = page.inner_text("#bmPanel")
            check("REG-CHEST" in panel and "42" in panel, "点部位联动右侧面板", panel[:60].replace("\n", " "))
            check(page.locator('a[href="app.html"]').count() >= 1, "进入系统入口存在")
            check(not errs, "首页无控制台错误", str(errs[:2]))
            ctx.close()

            # 2. 入口加载（对外 2 个 + 开发者 8 个）
            print("\n[2] 入口加载")
            entries = [
                ("应用主入口", "app.html"),
                ("学生桌面", "dev/student.html"),
                ("学生移动", "dev/student-mobile.html"),
                ("教师桌面", "dev/teacher.html"),
                ("教师移动", "dev/teacher-mobile.html"),
                ("医生桌面", "dev/doctor.html"),
                ("医生移动", "dev/doctor-mobile.html"),
            ]
            for label, path in entries:
                mobile = "mobile" in path
                ctx, page, errs = new_page(browser, 390 if mobile else 1440, 844 if mobile else 1000, mobile)
                goto(page, path)
                to_home(page)
                check(page.locator(".main").count() == 1, f"{label} 主内容渲染")
                check(page.locator(".chain").count() == 4, f"{label} 四链条卡片", str(page.locator(".chain").count()))
                check(not errs, f"{label} 无控制台错误", str(errs[:2]))
                ctx.close()

            # 3. 三角色四链条可达
            print("\n[3] 三角色 × 四链条可达")
            for role in ("student", "teacher", "doctor"):
                ctx, page, errs = new_page(browser)
                goto(page, f"app.html?role={role}&device=desktop")
                to_home(page)
                for i in range(4):
                    page.locator(".chain").nth(i).click()
                    page.wait_for_timeout(260)
                    h1 = page.locator(".page-head h1").inner_text()
                    check(not h1.startswith("把一条"), f"{role} 链条 {i + 1} 可进入", h1)
                    check(page.locator(".main").count() == 1, f"{role} 链条 {i + 1} 主内容存在")
                    page.locator(".brand").click()
                    page.wait_for_timeout(260)
                check(not errs, f"{role} 四链条无错误", str(errs[:2]))
                ctx.close()

            # 4. 医生端：读片演练 → 结果 → 运行回执
            print("\n[4] 医生端读片演练")
            ctx, page, errs = new_page(browser)
            goto(page, "app.html?role=doctor&device=desktop")
            to_home(page)
            page.locator(".chain").nth(2).click()
            page.wait_for_timeout(300)
            check(page.locator(".page-head h1").inner_text() == "练 · 读片演练", "医生端进入读片演练")
            page.locator(".case-card").first.click()
            page.wait_for_timeout(300)
            check(page.locator(".drill-panel").count() == 1, "演练面板加载")
            page.locator(".region-pills button").first.click()
            page.wait_for_timeout(180)
            page.locator("[data-act='drill-next']").click()
            page.wait_for_timeout(180)
            page.locator(".opt").first.click()
            page.wait_for_timeout(150)
            if page.locator("[data-act='drill-confirm']").count():
                page.locator("[data-act='drill-confirm']").click()
                page.wait_for_timeout(150)
            page.locator("[data-act='drill-next']").click()
            page.wait_for_timeout(180)
            page.locator(".opt").first.click()
            page.wait_for_timeout(150)
            if page.locator("[data-act='drill-confirm']").count():
                page.locator("[data-act='drill-confirm']").click()
                page.wait_for_timeout(150)
            page.locator("[data-act='drill-next']").click()
            page.wait_for_timeout(180)
            page.locator(".opt").first.click()
            page.wait_for_timeout(150)
            if page.locator("[data-act='drill-confirm']").count():
                page.locator("[data-act='drill-confirm']").click()
                page.wait_for_timeout(150)
            if page.locator("[data-act='drill-finish']").count():
                page.locator("[data-act='drill-finish']").click()
                page.wait_for_timeout(260)
            check(page.locator(".score-ring").count() == 1, "演练结果生成")
            check(page.locator(".trace").count() >= 1, "判分运行回执存在")
            check(not errs, "演练无控制台错误", str(errs[:2]))
            ctx.close()

            # 5. 医生端：核验记录
            print("\n[5] 医生端核验记录")
            ctx, page, errs = new_page(browser)
            goto(page, "app.html?role=doctor&device=desktop")
            page.locator("[data-act='nav'][data-view='apply']").first.click()
            page.wait_for_timeout(350)
            page.locator(".claim").first.click()
            page.wait_for_timeout(250)
            check(page.locator("[data-act='verify-claim']").count() == 1, "核验按钮存在")
            check(page.locator(".trace").count() >= 1, "核验运行回执存在")
            page.locator("[data-act='verify-claim']").click()
            page.wait_for_timeout(300)
            chip = page.locator(".page-actions .chip").first.inner_text()
            check("已核验 1 条" in chip, "核验计数更新", chip)

            # 分区标注：图上只留编号，名称进图例，并可一键隐藏
            check(page.locator("[data-act='regions']").count() == 1, "分区开关存在")
            labels = page.eval_on_selector_all(".stage .bbox span", "els => els.map(e => e.textContent.trim())")
            check(bool(labels) and all(x.isdigit() for x in labels), "图上分区只标编号", str(labels[:4]))
            nbox = page.locator(".stage .bbox").count()
            nleg = page.locator(".wb-leg").count()
            check(nleg == nbox and nleg > 0, "图例条数 = 分区数", f"{nleg} vs {nbox}")
            page.locator(".wb-leg").nth(1).click()
            page.wait_for_timeout(250)
            check("当前分区" in page.inner_text(".stage-note"), "点图例可选中分区", page.inner_text(".stage-note")[:26])
            page.locator("[data-act='regions']").click()
            page.wait_for_timeout(250)
            check(page.locator(".stage .bbox").count() == 0, "一键隐藏分区框")
            check("显示分区" in page.inner_text("[data-act='regions']"), "开关文案随状态切换")
            page.locator("[data-act='regions']").click()
            page.wait_for_timeout(250)
            check(page.locator(".stage .bbox").count() == nbox, "再点恢复分区框")
            check(page.locator(".evr-rail.off").count() == 1, "工作台默认收起重复证据栏")

            check(not errs, "核验无控制台错误", str(errs[:2]))
            ctx.close()

            # 6. 教师端：演练 → 组卷
            print("\n[6] 教师端演练 → 组卷")
            ctx, page, errs = new_page(browser)
            goto(page, "app.html?role=teacher&device=desktop")
            page.locator(".rail .nav button").filter(has_text="练").first.click()
            page.wait_for_timeout(300)
            check(page.locator(".page-head h1").inner_text() == "练 · 组卷与课堂演练", "教师端进入组卷演练")
            page.locator("[data-act='teacher-go']").first.click()
            page.wait_for_timeout(300)
            check(page.locator(".page-head h1").inner_text() == "教 · 班级管理", "跳转班级管理")
            check(page.locator(".tabs .on").inner_text() == "作业编排", "默认落在作业编排")
            check(not errs, "教师端无控制台错误", str(errs[:2]))
            ctx.close()

            # 7. 移动端角色切换与布局
            print("\n[7] 移动端适配")
            ctx, page, errs = new_page(browser, 390, 844, True)
            goto(page, "app.html?role=doctor&device=auto")
            check(page.locator(".identity").is_visible(), "移动端身份按钮可见")
            check(page.locator(".tabbar").is_visible(), "底部导航可见")
            check(page.evaluate("document.documentElement.scrollWidth") <= 390, "390px 无横向溢出")
            page.locator(".identity").click()
            page.wait_for_timeout(250)
            check(page.locator("#idMenu").is_visible(), "身份菜单可展开")
            page.locator('[data-act="role"][data-role="student"]').click()
            page.wait_for_timeout(400)
            check("把一条知识" in page.locator(".hero h1").inner_text(), "切换学生端成功")
            check("学生端" in page.locator(".identity").inner_text(), "身份按钮同步")
            check(not errs, "移动端无控制台错误", str(errs[:2]))
            ctx.close()

            # 8. 运行回执与双引用
            print("\n[8] 运行回执与双引用")
            ctx, page, errs = new_page(browser)
            goto(page, "app.html?role=student&device=desktop")
            to_home(page)
            page.locator(".chain").first.click()
            page.wait_for_timeout(350)
            check(page.locator(".agent-zone").count() == 1, "问答区渲染")
            # 未发起问答时不允许出现任何回执：旧版这里渲染的是写死的假回执，
            # 真实回执只能由 /api/ask 事件写入。真实链路由 yingzhi/tools/probe.py 与
            # .deepworks/tmp/check_sse.py 验证，本脚本保持不依赖后端。
            check(page.locator(".trace").count() == 0, "未提问时无假回执", str(page.locator(".trace").count()))
            page.locator("[data-act='nav'][data-view='apply']").first.click()
            page.wait_for_timeout(300)
            check(page.locator(".page-head h1").inner_text() == "用 · 实习任务", "学生端 04 链条")
            check(not errs, "问答无控制台错误", str(errs[:2]))
            ctx.close()

            # 9. 考点练习（题库 + 易错点）
            print("\n[9] 考点练习与易错点")
            ctx, page, errs = new_page(browser)
            goto(page, "app.html?role=student#/drill")
            check(page.locator(".drill-tab").count() == 2, "病例/考点双题库切换", str(page.locator(".drill-tab").count()))
            page.click('[data-act="drill-tab"][data-tab="quiz"]')
            page.wait_for_timeout(300)
            cards = page.locator(".quiz-card").count()
            check(cards >= 150, "考点题量 >= 150", str(cards))
            check(page.locator('[data-act="quiz-filter"]').count() == 4, "题型筛选 4 项")
            page.locator(".quiz-card").first.click()
            page.wait_for_timeout(300)
            check(page.locator(".quiz-opt").count() >= 3, "选项渲染")
            n = page.locator(".quiz-opt").count()
            for i in range(n):
                page.locator(".quiz-opt").nth(i).click()
            page.click('[data-act="quiz-submit"]')
            page.wait_for_timeout(300)
            check(page.locator(".feedback").count() == 1, "提交后有判分反馈")
            check(page.locator(".quiz-pit").count() == 1, "答后展示本题易错点")
            page.click('[data-act="quiz-exit"]')
            page.wait_for_timeout(300)
            check(page.locator(".quiz-pit").count() == 1, "错题聚合出高频易错点")
            check(not errs, "考点练习无控制台错误", str(errs[:2]))
            ctx.close()

            # 10. 核心功能：多模态问答 + 双引用 + 诚实拒答
            print("\n[10] 多模态问答（核心功能）")
            ctx, page, errs = new_page(browser)
            goto(page, "app.html")
            check(page.locator(".ask").count() == 1, "默认进入多模态问答")
            check(page.locator(".ask-grid > section").count() == 3, "输入/影像/回答三栏")
            check(page.locator('[data-ask="preset"]').count() >= 6, "预置场景 >= 6")
            check("非诊断" in page.inner_text(".ask-disclaim"), "固定非诊断声明")

            page.click('[data-ask="preset"][data-key="normal"]')
            page.wait_for_timeout(320)
            check("可答" in page.inner_text(".ans-status"), "双引用齐全时可答")
            check(page.locator(".cite-card.spatial").count() == 1, "影像引用卡")
            check(page.locator(".cite-card.doc").count() == 1, "文献引用卡")
            spatial = page.inner_text(".cite-card.spatial")
            check("REG-" in spatial and "bbox" in spatial, "影像引用含分区与 bbox", spatial[:60].replace("\n", " "))
            doc = page.inner_text(".cite-card.doc")
            check("指南条款" in doc and "ACR" in doc, "文献引用含指南条款", doc[:60].replace("\n", " "))

            page.click('[data-ask="preset"][data-key="trads"]')
            page.wait_for_timeout(320)
            check("可答" in page.inner_text(".ans-status"), "TR4 条款可答")
            check("CLM-007" in page.inner_text(".ans-notes"), "hash 校验失败的结论被拦截并说明", page.inner_text(".ans-notes")[:80].replace("\n", " "))

            page.click('[data-ask="preset"][data-key="scope"]')
            page.wait_for_timeout(320)
            check("拒答" in page.inner_text(".ans-status"), "诊断/治疗请求被拒答")
            check("越出教学对照范围" in page.inner_text(".ans-status"), "拒答原因明确")

            page.click('[data-ask="preset"][data-key="upload"]')
            page.wait_for_timeout(320)
            check("拒答" in page.inner_text(".ans-status"), "未标注影像被拒答")
            check("缺少可定位的分区" in page.inner_text(".ans-status"), "拒答指向影像侧缺失")

            page.click('[data-ask="preset"][data-key="ggo"]')
            page.wait_for_timeout(320)
            check("部分可答" in page.inner_text(".ans-status"), "缺尺寸时降级为部分可答")
            check(page.locator(".ans-alt").count() == 1, "条款并列展示")
            check("SL-005" in page.inner_text(".cite-card.spatial"), "磨玻璃影使用人工图文锚点")
            check("并列" in page.inner_text(".ans-text"), "并列条款写入回答正文")

            page.click(".ask-test summary")
            page.wait_for_timeout(160)
            page.click('[data-ask="selftest"]')
            page.wait_for_timeout(420)
            check("8 / 8 通过" in page.inner_text(".st-head"), "诚实性自检 8/8", page.inner_text(".st-head").replace("\n", " "))
            check(not errs, "问答页无控制台错误", str(errs[:2]))
            ctx.close()

            browser.close()
    finally:
        if proc:
            proc.terminate()

    print(f"\n合计 {CHECKS} 项检查，失败 {len(FAILS)} 项。")
    if FAILS:
        for f in FAILS:
            print("  -", f)
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
