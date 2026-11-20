"""RadioCheck 首页 3D 模型接入自检：模型就绪 → 点击胸部 → 面板出现影像 → 灯箱打开。"""
import os
import sys
from playwright.sync_api import sync_playwright

EXE = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium_headless_shell-1243/"
    "chrome-headless-shell-mac-arm64/chrome-headless-shell"
)
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8790/"
OUT = ".deepworks/tmp"
fails = []
logs = []

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=["--enable-unsafe-swiftshader", "--disable-gpu"])
    pg = b.new_page(viewport={"width": 1440, "height": 1000})
    pg.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
    pg.on("console", lambda m: logs.append(f"[{m.type}] {m.text}") if m.type in ("error",) else None)

    pg.goto(URL, wait_until="load", timeout=60000)
    pg.wait_for_function("window.__BM_HANDLE__ && window.__BM_HANDLE__.status().ready === true", timeout=90000)
    pg.wait_for_timeout(800)

    st = pg.evaluate("window.__BM_HANDLE__.status()")
    print("status:", st)
    if st.get("mode") != "adapter":
        fails.append("未进入 adapter 模式")

    mode_label = pg.text_content("#bmStatus")
    print("status chip:", mode_label)
    if "3D" not in (mode_label or ""):
        fails.append("状态标签未显示 3D")

    # 定位 canvas 并点击胸部（垂直约 29% 处）
    box = pg.locator(".bm3d-canvas").bounding_box()
    print("canvas box:", box)
    if not box:
        fails.append("找不到 canvas")
    else:
        pg.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.285)
        pg.wait_for_timeout(900)

    panel = pg.text_content("#bmPanel")
    print("panel head:", (panel or "")[:80].replace("\n", " "))
    shots = pg.locator(".bp-shot").count()
    print("shots:", shots)
    if shots == 0:
        fails.append("面板未出现影像缩略图")

    pg.locator("#body").scroll_into_view_if_needed()
    pg.wait_for_timeout(400)
    pg.screenshot(path=os.path.join(OUT, "mt-selected.png"))

    if shots:
        pg.locator(".bp-shot").first.click()
        pg.wait_for_timeout(700)
        lb_open = pg.locator(".bp-lightbox").is_visible()
        print("lightbox visible:", lb_open)
        if not lb_open:
            fails.append("灯箱未打开")
        pg.screenshot(path=os.path.join(OUT, "mt-lightbox.png"))
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)

    # 高亮接口
    pg.evaluate("window.__BM_HANDLE__.highlight('REG-ABDOMEN')")
    pg.wait_for_timeout(500)
    pg.evaluate("window.__BM_HANDLE__.reset()")
    pg.wait_for_timeout(300)

    b.close()

print("--- errors ---")
for line in logs[-10:]:
    print(line)

if fails:
    print("FAIL:", fails)
    sys.exit(1)
print("PASS")
