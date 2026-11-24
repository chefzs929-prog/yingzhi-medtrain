#!/usr/bin/env python3
"""RadioCheck 课堂可选同步服务（标准库，无第三方依赖）。

定位：
  - 纯静态课堂默认仍是 localStorage；本服务是“可选同步”，不是账号系统。
  - 单库快照 + 按 id 合并；适合课堂演示/单机内网，不做并发数据库。
  - 无鉴权：只监听 127.0.0.1 或内网，不要暴露到公网。

运行：
  python3 kb/server/classroom_server.py --port 8820
  python3 kb/server/classroom_server.py --port 8820 --db .deepworks/tmp/classroom.db

接口：
  GET  /api/health
  GET  /api/snapshot
  POST /api/merge   {"data": {...课堂数据...}}
  POST /api/reset   （仅演示用）
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 8 * 1024 * 1024
LOCK = threading.Lock()
DB_PATH = Path("classroom.db")


def blank() -> dict:
    return {
        "version": 1,
        "teacher": {"name": "", "createdAt": ""},
        "classes": [],
        "activeRole": "",
        "activeClassId": "",
        "activeStudentId": "",
        "attempts": [],
        "posts": [],
    }


def normalize(db: dict | None) -> dict:
    if not isinstance(db, dict) or db.get("version") != 1:
        return blank()
    out = blank()
    out.update(db)
    for key in ("classes", "attempts", "posts"):
        if not isinstance(out.get(key), list):
            out[key] = []
    if not isinstance(out.get("teacher"), dict):
        out["teacher"] = {"name": "", "createdAt": ""}
    for c in out["classes"]:
        for key in ("students", "assignments", "groups"):
            if not isinstance(c.get(key), list):
                c[key] = []
        for a in c["assignments"]:
            if not isinstance(a.get("caseIds"), list):
                a["caseIds"] = []
            if not isinstance(a.get("passScore"), (int, float)):
                a["passScore"] = 60
        for g in c["groups"]:
            if not isinstance(g.get("memberIds"), list):
                g["memberIds"] = []
    for p in out["posts"]:
        if not isinstance(p.get("replies"), list):
            p["replies"] = []
        if p.get("status") != "resolved":
            p["status"] = "open"
    return out


def merge(server: dict, client: dict) -> dict:
    """按 code / name / id 合并；服务端已有数据不丢，客户端新数据追加。"""
    s = normalize(server)
    c = normalize(client)

    if not s["teacher"].get("name") and c["teacher"].get("name"):
        s["teacher"] = c["teacher"]

    for ic in c["classes"]:
        code = ic.get("code")
        cur = next((x for x in s["classes"] if x.get("code") == code), None)
        if not cur:
            s["classes"].append(ic)
            continue

        for stu in ic.get("students", []):
            if not any(x.get("name") == stu.get("name") for x in cur["students"]):
                cur["students"].append(stu)

        for a in ic.get("assignments", []):
            idx = next((i for i, x in enumerate(cur["assignments"]) if x.get("id") == a.get("id")), None)
            if idx is None:
                cur["assignments"].append(a)
            else:
                # 作业以较新的 updatedAt / createdAt 为准，避免旧设备覆盖新截止日期
                old = cur["assignments"][idx]
                if str(a.get("updatedAt") or a.get("createdAt") or "") >= str(old.get("updatedAt") or old.get("createdAt") or ""):
                    cur["assignments"][idx] = a

        for g in ic.get("groups", []):
            old = next((x for x in cur["groups"] if x.get("name") == g.get("name")), None)
            if not old:
                cur["groups"].append(g)
            else:
                ids = set(old.get("memberIds") or []) | set(g.get("memberIds") or [])
                old["memberIds"] = list(ids)

    for a in c["attempts"]:
        if not any(x.get("id") == a.get("id") for x in s["attempts"]):
            s["attempts"].append(a)

    for p in c["posts"]:
        old = next((x for x in s["posts"] if x.get("id") == p.get("id")), None)
        if not old:
            s["posts"].append(p)
            continue
        for r in p.get("replies", []):
            if not any(x.get("id") == r.get("id") for x in old.get("replies", [])):
                old.setdefault("replies", []).append(r)

    return s


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.commit()


def read_db() -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT data FROM snapshot WHERE id = 1").fetchone()
    if not row:
        return blank()
    try:
        return normalize(json.loads(row[0]))
    except Exception:
        return blank()


def write_db(db: dict) -> None:
    payload = json.dumps(normalize(db), ensure_ascii=False)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO snapshot (id, data, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (payload, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()


class Handler(BaseHTTPRequestHandler):
    server_version = "RadioCheckSync/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print("[sync] " + (fmt % args))

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._json(200, {"ok": True, "service": "radiocheck-classroom-sync", "db": str(DB_PATH)})
            return
        if self.path == "/api/snapshot":
            with LOCK:
                db = read_db()
            self._json(200, {"ok": True, "data": db})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path not in {"/api/merge", "/api/reset"}:
            self._json(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._json(413, {"ok": False, "error": "body too large"})
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf8") or "{}")
        except Exception:
            self._json(400, {"ok": False, "error": "invalid json"})
            return

        if self.path == "/api/reset":
            with LOCK:
                write_db(blank())
            self._json(200, {"ok": True, "data": blank()})
            return

        incoming = body.get("data")
        if not isinstance(incoming, dict):
            self._json(400, {"ok": False, "error": "data must be an object"})
            return
        with LOCK:
            current = read_db()
            merged = merge(current, incoming)
            write_db(merged)
        self._json(200, {"ok": True, "data": merged, "merged": True})


def main() -> None:
    global DB_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8820)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--db", default=".deepworks/tmp/classroom.db")
    args = parser.parse_args()
    DB_PATH = Path(args.db)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"RadioCheck classroom sync on http://{args.host}:{args.port}  db={DB_PATH}")
    print("无鉴权，仅用于本机/内网演示；不要暴露到公网。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
