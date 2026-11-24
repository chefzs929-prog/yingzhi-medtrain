"""稳定性检查：同一问句重复问，必须得到逐字相同的答案。

评审反馈原话是「同一问句重复问三次，两个不同答案，一次没有原文」。
根因是问答页每次加载随机选病例，而检索只在当前病例内进行。
本检查锁死这一点：任何一次结果不同即失败。

用法：python3 medtrain/tests/stability_check.py
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SITE = ROOT / "outputs/medtrain"
OUT = ROOT / "outputs/medtrain/stability_check.md"

REPEAT = 5
QUERIES = [
    "右肺中野有什么问题",
    "这张片子有没有结节",
    "这张片子是不是肺癌",
]


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main() -> int:
    if not (SITE / "read/ask.html").exists():
        print("先运行 medtrain/build.py", file=sys.stderr)
        return 2

    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(SITE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}/"
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)

    rows = []
    ok = True
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            for q in QUERIES:
                seen = []
                first = ""
                for i in range(REPEAT):
                    page = browser.new_page(viewport={"width": 1400, "height": 880})
                    page.goto(base + "read/ask.html", wait_until="networkidle")
                    page.fill("#q", q)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(650)
                    text = page.inner_text("#result")
                    page.close()
                    if i == 0:
                        first = text
                    seen.append(text)
                stable = len(set(seen)) == 1
                has_zone = "影像区域" in first
                has_cite = "依据原文" in first
                refused = "不能回答" in first
                # 能答的必须有区域+原文；拒答的必须有理由
                complete = refused or (has_zone and has_cite)
                good = stable and complete
                ok = ok and good
                rows.append(
                    {
                        "query": q,
                        "stable": stable,
                        "distinct": len(set(seen)),
                        "zone": has_zone,
                        "cite": has_cite,
                        "refused": refused,
                        "pass": good,
                    }
                )
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    lines = [
        "# 问答稳定性检查",
        "",
        f"> 同一问句连续问 {REPEAT} 次，要求逐字一致；能答必须同时有「影像区域」与「依据原文」。",
        "",
        "| 问句 | 稳定 | 不同结果数 | 区域 | 原文 | 拒答 | 结论 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            "| {q} | {s} | {d} | {z} | {c} | {r} | {p} |".format(
                q=r["query"],
                s="是" if r["stable"] else "**否**",
                d=r["distinct"],
                z="✓" if r["zone"] else "—",
                c="✓" if r["cite"] else "—",
                r="拒绝" if r["refused"] else "—",
                p="通过" if r["pass"] else "**失败**",
            )
        )
    passed = sum(1 for r in rows if r["pass"])
    lines += ["", f"**{passed}/{len(rows)} 通过。**", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[-6:]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
