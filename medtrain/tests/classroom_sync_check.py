#!/usr/bin/env python3
"""课堂可选同步：API 合并 + 前端离线回退验收。

前置：在 outputs/medtrain 启动静态服务器（默认 8811）。
运行：python3 medtrain/tests/classroom_sync_check.py
输出：outputs/medtrain/classroom_sync_check.md
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/medtrain/classroom_sync_check.md"
BASE = os.environ.get("YZ_BASE", "http://127.0.0.1:8811/")
PORT = 8821
SYNC = f"http://127.0.0.1:{PORT}"
DB = ROOT / ".deepworks/tmp/classroom_sync_test.db"

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))
    print(("  ✓ " if ok else "  ✗ ") + name + (("  " + detail) if detail and not ok else ""))


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        SYNC + path,
        data=json.dumps(payload).encode("utf8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(SYNC + path, timeout=5) as r:
        return json.loads(r.read().decode("utf8"))


def wait_health() -> None:
    for _ in range(50):
        try:
            if get("/api/health").get("ok"):
                return
        except Exception:
            time.sleep(0.1)
    raise SystemExit("sync server did not start")


def wait_health_at(port: int) -> None:
    url = f"http://127.0.0.1:{port}/api/health"
    for _ in range(50):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if json.loads(r.read().decode("utf8")).get("ok"):
                    return
        except Exception:
            time.sleep(0.1)
    raise SystemExit(f"sync server :{port} did not start")


def status(url: str, method: str = "GET", token: str = "", payload: dict | None = None) -> int:
    data = json.dumps(payload).encode("utf8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Sync-Token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> None:
    DB.unlink(missing_ok=True)
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "kb/server/classroom_server.py"), "--port", str(PORT), "--db", str(DB)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_health()

        # 1) API 合并：两个“设备”分别提交，服务端不能丢数据。
        a = {
            "version": 1, "teacher": {"name": "张老师", "createdAt": "2026-11-23"},
            "classes": [{"id": "C1", "code": "ABC123", "name": "试点班", "teacher": "张老师",
                         "students": [{"id": "S1", "name": "甲"}], "assignments": [], "groups": []}],
            "attempts": [], "posts": [],
        }
        b = {
            "version": 1, "teacher": {"name": "张老师", "createdAt": "2026-11-23"},
            "classes": [{"id": "C1", "code": "ABC123", "name": "试点班", "teacher": "张老师",
                         "students": [{"id": "S2", "name": "乙"}], "assignments": [], "groups": []}],
            "attempts": [{"id": "A1", "classId": "C1", "studentId": "S2", "caseId": "CASE-001", "score": 88}],
            "posts": [],
        }
        r1 = post("/api/merge", {"data": a})
        r2 = post("/api/merge", {"data": b})
        snap = get("/api/snapshot")["data"]
        cls = snap["classes"][0]
        check("API 创建班级", r1.get("ok") and cls["code"] == "ABC123")
        check("API 合并学生不丢", {s["name"] for s in cls["students"]} == {"甲", "乙"}, str(cls["students"]))
        check("API 合并答题不丢", len(snap["attempts"]) == 1 and snap["attempts"][0]["id"] == "A1")
        check("API 二次合并返回快照", r2.get("ok") and r2.get("merged") is True)

        # 1b) 删除必须传播：带墓碑的客户端快照合并后，服务端不能保留旧对象。
        deleted = {
            "version": 1, "teacher": {"name": "张老师", "createdAt": "2026-11-23"},
            "classes": [{"id": "C1", "code": "ABC123", "name": "试点班", "teacher": "张老师",
                         "students": [], "assignments": [], "groups": []}],
            "attempts": [], "posts": [],
            "tombstones": [
                {"type": "student", "id": "S1", "classId": "C1", "name": "甲"},
                {"type": "student", "id": "S2", "classId": "C1", "name": "乙"},
                {"type": "attempt", "id": "A1", "classId": "C1"},
            ],
        }
        post("/api/merge", {"data": deleted})
        snap_del = get("/api/snapshot")["data"]
        cls_del = snap_del["classes"][0]
        check("删除学生同步生效", cls_del["students"] == [], str(cls_del["students"]))
        check("删除答题同步生效", snap_del["attempts"] == [], str(snap_del["attempts"]))
        check("墓碑持久化", len(snap_del.get("tombstones") or []) >= 3, str(snap_del.get("tombstones")))

        # 1c) 口令保护：另起一个带口令的实例，验证 401 / 200 / reset 默认关闭。
        tok_port = PORT + 1
        tok_db = DB.with_name("classroom_sync_token.db")
        tok_db.unlink(missing_ok=True)
        tok_proc = subprocess.Popen(
            [sys.executable, str(ROOT / "kb/server/classroom_server.py"),
             "--port", str(tok_port), "--db", str(tok_db), "--token", "s3cret"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            wait_health_at(tok_port)
            tok = f"http://127.0.0.1:{tok_port}"
            check("口令实例探活", status(tok + "/api/health") == 200)
            check("无口令读快照被拒", status(tok + "/api/snapshot") == 401)
            check("错口令被拒", status(tok + "/api/snapshot", token="bad") == 401)
            check("正确口令可读", status(tok + "/api/snapshot", token="s3cret") == 200)
            check("reset 默认关闭", status(tok + "/api/reset", method="POST", token="s3cret", payload={}) == 403)
        finally:
            tok_proc.terminate()
            try:
                tok_proc.wait(timeout=3)
            except Exception:
                tok_proc.kill()

        # 2) 前端：带 sync 参数打开课堂，载入演示班级后应自动推送。
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx1 = browser.new_context(viewport={"width": 1440, "height": 950})
            pg1 = ctx1.new_page()
            errs: list[str] = []
            pg1.on("pageerror", lambda e: errs.append(str(e)))
            pg1.on("console", lambda m: errs.append(m.text) if m.type == "error" and "api/kb/health" not in ((getattr(m, "location", None) or {}).get("url") or "") else None)
            pg1.goto(BASE + f"read/classroom.html?sync={SYNC}", wait_until="networkidle")
            pg1.wait_for_timeout(1200)
            check("前端显示同步状态", "同步" in pg1.inner_text("#syncStatus"), pg1.inner_text("#syncStatus"))
            pg1.evaluate("() => window.RCClass.createClass('前端同步班', '李老师')")
            pg1.wait_for_timeout(2200)
            after = get("/api/snapshot")["data"]
            check("前端写操作触发推送", any(c.get("name") == "前端同步班" for c in after["classes"]),
                  str([c.get("name") for c in after["classes"]]))

            # 2b) 前端删除后推送，服务端不能把学生复活。
            ids = pg1.evaluate("""() => {
              const db = window.RCClass.read();
              const c = db.classes.find(x => x.name === '前端同步班');
              const r = window.RCClass.addStudent(c.id, '待删学生');
              return { classId: c.id, studentId: r.student.id };
            }""")
            pg1.wait_for_timeout(2200)
            pg1.evaluate("(ids) => window.RCClass.removeStudent(ids.classId, ids.studentId)", ids)
            pg1.wait_for_timeout(2200)
            after_del = get("/api/snapshot")["data"]
            c_del = next((c for c in after_del["classes"] if c.get("name") == "前端同步班"), None)
            check("前端删除学生同步生效",
                  c_del is not None and all(s.get("name") != "待删学生" for s in c_del["students"]),
                  str(c_del and c_del["students"]))

            # 3) 第二个“设备”：独立 localStorage，拉取后应看到同一个班级。
            ctx2 = browser.new_context(viewport={"width": 1440, "height": 950})
            pg2 = ctx2.new_page()
            pg2.goto(BASE + f"read/classroom.html?sync={SYNC}", wait_until="networkidle")
            pg2.wait_for_timeout(1500)
            n = pg2.evaluate("window.RCClass ? window.RCClass.read().classes.length : -1")
            check("第二设备拉取到班级", n and n >= 1, str(n))

            # 4) 离线回退：不可达地址不应白屏/报错。
            ctx3 = browser.new_context(viewport={"width": 1440, "height": 950})
            pg3 = ctx3.new_page()
            errs3: list[str] = []
            pg3.on("pageerror", lambda e: errs3.append(str(e)))
            pg3.goto(BASE + "read/classroom.html?sync=http://127.0.0.1:9", wait_until="networkidle")
            pg3.wait_for_timeout(1500)
            check("离线回退显示本机模式", "本机" in pg3.inner_text("#syncStatus"), pg3.inner_text("#syncStatus"))
            check("离线无 page error", not errs3, "; ".join(errs3[:2]))
            check("前端无 console error", not errs, "; ".join(errs[:2]))
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

    lines = ["# 课堂可选同步验收 · 2026-11-23", "", "| 检查 | 结果 | 说明 |", "| --- | --- | --- |"]
    for name, ok, detail in rows:
        lines.append(f"| {name} | {'通过' if ok else '失败'} | {detail} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    if not all(ok for _, ok, _ in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
