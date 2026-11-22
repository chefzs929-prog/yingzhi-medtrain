#!/usr/bin/env python3
"""学生影像实验室 · 端到端验收。

前置：
  cd outputs/medtrain && python3 -m http.server 8811
运行：
  python3 medtrain/tests/student_lab_check.py
输出：
  outputs/medtrain/student_lab_check.md

覆盖：
  - 学生端 5 个页签；
  - 影像库问答：征象 / 概念 / 指南 / 未命中，区域框 + 双引用；
  - 读片陪练：定位 → 判读 → 征象 → 对照，提示与评分；
  - 自测出题器：范围 / 题型 / 题量 / 限时，答题卡、交卷、错题重做、导出；
  - 互助小组：教师建组 / 演示数据、学生加入 / 发帖 / 回复 / 标记解决；
  - 移动端无横向溢出、无 console / page error、无 4xx。
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/student_lab_check.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")

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
        bad: list[tuple[int, str]] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("response", lambda r: bad.append((r.status, r.url)) if r.status >= 400 else None)
        page.on("dialog", lambda d: d.accept())

        page.goto(BASE + "read/classroom.html", wait_until="networkidle")
        page.evaluate("localStorage.clear()")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(300)

        # 建演示班 + 学生加入
        page.click('[data-act="role"][data-role="teacher"]')
        page.wait_for_timeout(200)
        page.click('[data-act="demo-class"]')
        page.wait_for_timeout(350)
        code = page.inner_text(".code-box b")
        page.click('#roleSwitch [data-role="student"]')
        page.wait_for_timeout(300)
        page.fill("#joinName", "测试同学")
        page.fill("#joinCode", code)
        page.click('[data-act="join-class"]')
        page.wait_for_timeout(400)
        tabs = page.locator("[data-student-tab]").all_inner_texts()
        check("学生端 5 个页签", tabs == ["我的作业", "影像问答", "读片陪练", "自测出题", "互助小组"], str(tabs))

        # ---------- 影像库问答 ----------
        page.click('[data-student-tab="qa"]')
        page.wait_for_timeout(700)
        check("问答页加载", page.locator("#labQ").count() == 1)
        page.fill("#labQ", "气胸")
        page.click("[data-lab-ask]")
        page.wait_for_timeout(350)
        qa = page.inner_text("#labQaResult")
        check("气胸命中 SIGN-008", "SIGN-008" in qa and "气胸" in qa, qa[:240])
        check("气胸给出影像定位 E1", "E1" in qa and "CASE-036" in qa, qa[:320])
        check("气胸给出文献 L1", "L1" in qa and "SIGN-008" in qa and "SRC-" in qa, qa[:500])
        check("双引用链可见", "双引用链" in qa and "CASE-036" in qa, qa[:600])
        check("区域框已绘制", page.locator(".lab-bbox").count() >= 1, str(page.locator(".lab-bbox").count()))
        check("文献外链可点", page.locator(".lab-src a[href^='http']").count() >= 1,
              str(page.locator(".lab-src a[href^='http']").count()))
        check("影像可跳阅片台", page.locator("a[href*='clinic.html?case=CASE-036']").count() >= 1)

        page.fill("#labQ", "肺结核")
        page.click("[data-lab-ask]")
        page.wait_for_timeout(300)
        qa = page.inner_text("#labQaResult")
        check("肺结核命中概念 CON-125", "CON-125" in qa, qa[:240])
        check("肺结核标注关联征象", "关联" in qa and ("SIGN-003" in qa or "SIGN-004" in qa), qa[:500])

        page.fill("#labQ", "实变和胸腔积液怎么区分")
        page.click("[data-lab-ask]")
        page.wait_for_timeout(300)
        qa = page.inner_text("#labQaResult")
        check("对比问法并列两个征象", "对比检索" in qa and "SIGN-002" in qa and "SIGN-007" in qa, qa[:400])
        check("对比问法给鉴别点", "易错点" in qa and "不是诊断路径" in qa, qa[:800])

        page.fill("#labQ", "肺结节随访")
        page.click("[data-lab-ask]")
        page.wait_for_timeout(300)
        qa = page.inner_text("#labQaResult")
        check("肺结节随访命中指南", "GL-" in qa and ("Fleischner" in qa or "Lung-RADS" in qa), qa[:400])
        check("指南显示适用条件", "适用条件" in qa, qa[:600])

        page.fill("#labQ", "阑尾炎")
        page.click("[data-lab-ask]")
        page.wait_for_timeout(300)
        qa = page.inner_text("#labQaResult")
        check("未命中明确拒答", "库内未覆盖" in qa and "诚实拒答" in qa, qa[:300])
        check("未命中不编造 id", "SIGN-" not in qa, qa[:500])

        page.fill("#labQ", "这个气胸需要做胸腔闭式引流吗")
        page.click("[data-lab-ask]")
        page.wait_for_timeout(300)
        qa = page.inner_text("#labQaResult")
        check("越界问题明确拒答", "越界拒答" in qa and "不提供这类内容" in qa, qa[:300])

        page.fill("#labQ", "气胸")
        page.click("[data-lab-ask]")
        page.wait_for_timeout(300)
        qa = page.inner_text("#labQaResult")
        check("命中给段落 L2", "段落 L2" in qa and "SIGN-008#" in qa, qa[:600])
        check("答案固定非诊断声明", "不构成诊断意见" in qa, qa[-300:])

        page.click(".lab-report summary")
        page.wait_for_timeout(200)
        page.fill("#labReport", "右肺上野见气胸，脏层胸膜线可见，余肺野清晰。")
        page.click("[data-lab-report]")
        page.wait_for_timeout(400)
        qa = page.inner_text("#labQaResult")
        check("报告文本映射到影像与段落", "报告文本映射" in qa and "E1" in qa and "段落 L2" in qa, qa[:500])
        page.fill("#labReport", "6 mm 实性结节怎么随访？")
        page.click("[data-lab-report]")
        page.wait_for_timeout(400)
        qa = page.inner_text("#labQaResult")
        check("指南问题给条款与段落", "指南条款" in qa and "段落 L2" in qa, qa[:500])

        # ---------- 读片陪练 ----------
        page.click('[data-student-tab="coach"]')
        page.wait_for_timeout(700)
        check("陪练页加载", page.locator(".lab-zone").count() >= 3, str(page.locator(".lab-zone").count()))
        page.select_option("#labCoachCase", "CASE-007")
        page.wait_for_timeout(300)
        page.click('[data-lab-coach-zone="RLL"]')
        page.wait_for_timeout(150)
        check("陪练第 1 步选中分区", "右肺下野" in page.inner_text(".lab-picked"), page.inner_text(".lab-picked"))
        page.click("[data-lab-coach-hint]")
        page.wait_for_timeout(150)
        check("陪练提示不直接给答案", "提示" in page.inner_text(".lab-hint"), page.inner_text(".lab-hint")[:160])
        page.click("[data-lab-coach-next]")
        page.wait_for_timeout(150)
        page.click('[data-lab-coach-status="abnormal"]')
        page.click("[data-lab-coach-next]")
        page.wait_for_timeout(150)
        page.click('[data-lab-coach-sign="SIGN-002"]')
        page.click("[data-lab-coach-submit]")
        page.wait_for_timeout(350)
        coach = page.inner_text(".lab-step")
        check("陪练评分 100", "100" in coach and "定位 40" in coach, coach[:300])
        check("陪练显示库内对照", "该区库内所见" in coach and "依据" in coach, coach[:700])
        practice = page.evaluate("JSON.parse(localStorage.getItem('radiocheck.studentlab.v1') || '{}').practice || []")
        check("陪练记录写入本机", len(practice) >= 1, str(len(practice)))

        # ---------- 自测出题器 ----------
        page.click('[data-student-tab="quiz"]')
        page.wait_for_timeout(700)
        check("自测配置页加载", page.locator("#labScope").count() == 1)
        page.select_option("#labScope", "sign:SIGN-008")
        page.select_option("#labType", "locate")
        page.select_option("#labCount", "5")
        page.select_option("#labMinutes", "10")
        page.click("[data-lab-quiz-start]")
        page.wait_for_timeout(400)
        check("生成 5 题试卷", page.locator(".lab-sheet-cell").count() == 5,
              str(page.locator(".lab-sheet-cell").count()))
        check("试卷有影像与区域框", page.locator(".lab-stage img").count() == 1 and page.locator(".lab-bbox").count() == 1)
        check("限时计时器可见", page.locator("#labTimer").count() == 1, page.inner_text("#labTimer") if page.locator("#labTimer").count() else "")
        check("选项至少 3 个", page.locator(".lab-option").count() >= 3, str(page.locator(".lab-option").count()))
        page.locator(".lab-option").first.click()
        page.wait_for_timeout(120)
        check("作答写入答题卡", page.locator(".lab-sheet-cell.done").count() == 1,
              str(page.locator(".lab-sheet-cell.done").count()))
        page.click("[data-lab-next]")
        page.wait_for_timeout(150)
        page.click("[data-lab-submit]")
        page.wait_for_timeout(400)
        result = page.inner_text("#studentTabBody")
        check("交卷显示结果", "自测结果" in result and "分" in result, result[:300])
        check("结果逐题给解析", "正确答案" in result and "影像 E1" in result, result[:700])
        check("结果给文献引用", "文献 L" in result or "SIGN-" in result, result[:900])
        check("错题卡有 Agent 追问", page.locator(".lab-qr.bad [data-agent-ask]").count() >= 1,
              str(page.locator(".lab-qr.bad [data-agent-ask]").count()))
        page.click("[data-lab-retry-wrong]")
        page.wait_for_timeout(350)
        check("错题重做生成新卷", page.locator(".lab-sheet-cell").count() >= 1,
              str(page.locator(".lab-sheet-cell").count()))
        page.click("[data-lab-submit]")
        page.wait_for_timeout(350)
        with page.expect_download(timeout=8000) as dl:
            page.click("[data-lab-export]")
        check("成绩单可导出", dl.value.suggested_filename.endswith(".md"), dl.value.suggested_filename)
        page.click("[data-lab-quiz-again]")
        page.wait_for_timeout(300)
        check("再测一次回到配置", page.locator("#labScope").count() == 1)

        # ---------- 互助小组 ----------
        page.click('#roleSwitch [data-role="teacher"]')
        page.wait_for_timeout(300)
        page.click('[data-teacher-tab="group"]')
        page.wait_for_timeout(250)
        check("教师端小组页", "小组与组内论坛" in page.inner_text("#classroomMain"))
        page.click("[data-group-seed]")
        page.wait_for_timeout(400)
        check("演示小组已载入", page.locator(".group-card").count() >= 3,
              str(page.locator(".group-card").count()))
        page.locator("[data-group-open]").first.click()
        page.wait_for_timeout(250)
        check("教师可查看组内帖子", page.locator(".post-row").count() >= 1,
              str(page.locator(".post-row").count()))

        page.click('#roleSwitch [data-role="student"]')
        page.wait_for_timeout(300)
        page.click('[data-student-tab="group"]')
        page.wait_for_timeout(400)
        check("学生端小组页", "班级互助小组" in page.inner_text("#studentTabBody"))
        if page.locator("[data-group-join]").count():
            page.locator("[data-group-join]").first.click()
            page.wait_for_timeout(300)
        page.locator("[data-group-open]").first.click()
        page.wait_for_timeout(300)
        check("学生进入组内论坛", page.locator("#postTitle").count() == 1)
        page.fill("#postTitle", "CASE-007 下肺野密度增高，实变还是积液？")
        page.fill("#postBody", "我看到双侧下肺野密度增高，但肋膈角还能看见；应该先选实变还是积液？")
        page.select_option("#postCase", "CASE-007")
        page.click("[data-post-submit]")
        page.wait_for_timeout(350)
        check("学生发帖成功", "实变还是积液" in page.inner_text(".post-detail"), page.inner_text(".post-detail")[:300])
        check("帖子关联病例卡", page.locator(".post-case").count() == 1)
        page.fill("#replyBody", "我会先看肋膈角是否变钝，再看空气支气管征。")
        page.click("[data-reply-submit]")
        page.wait_for_timeout(300)
        check("组内回复成功", "肋膈角是否变钝" in page.inner_text(".post-detail"), page.inner_text(".post-detail")[:500])
        page.click("[data-post-resolve]")
        page.wait_for_timeout(250)
        check("帖子可标记已解决", "已解决" in page.inner_text(".post-detail"), page.inner_text(".post-detail")[:300])
        posts = page.evaluate("JSON.parse(localStorage.getItem('radiocheck.classroom.v1')).posts")
        check("帖子写入本机", any("实变还是积液" in p["title"] for p in posts), str(len(posts)))

        # 教师端能看到新帖
        page.click('#roleSwitch [data-role="teacher"]')
        page.wait_for_timeout(250)
        page.click('[data-teacher-tab="group"]')
        page.wait_for_timeout(250)
        page.locator("[data-group-open]").first.click()
        page.wait_for_timeout(250)
        check("教师端看到学生新帖", "实变还是积液" in page.inner_text("#classroomMain"),
              page.inner_text("#classroomMain")[:600])

        # ---------- 移动端 ----------
        page.set_viewport_size({"width": 390, "height": 844})
        page.click('#roleSwitch [data-role="student"]')
        page.wait_for_timeout(300)
        for tab, label in [("qa", "问答"), ("coach", "陪练"), ("quiz", "自测"), ("group", "小组")]:
            page.click(f'[data-student-tab="{tab}"]')
            page.wait_for_timeout(450)
            overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(f"移动端 {label} 无横向溢出", overflow <= 1, str(overflow))

        check("无 console / page error", not errors, "；".join(errors[:4]))
        check("无 4xx", not bad, str(bad[:4]))
        browser.close()

    passed = sum(1 for _, ok, _ in rows if ok)
    total = len(rows)
    lines = [
        "# 学生影像实验室 · 端到端验收",
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
        "> 本验收只证明问答、陪练、自测与组内论坛流程可复现；",
        "> 不证明医学结论正确；正式教学前须由医学人员逐条审核。",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"\n{passed}/{total} passed -> {OUT}")
    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
