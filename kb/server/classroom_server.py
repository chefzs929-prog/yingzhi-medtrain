#!/usr/bin/env python3
"""RadioCheck 课堂可选同步服务（标准库，无第三方依赖）。

定位：
  - 纯静态课堂默认仍是 localStorage；本服务是“可选同步”，不是账号系统。
  - 单库快照 + 按 id 合并；适合课堂演示/单机内网，不做并发数据库。
  - 设 YZ_SYNC_TOKEN（或 --token）后，读快照与合并都必须带 X-Sync-Token；
    未设口令时等价于旧的本机/内网模式，但只应监听 127.0.0.1。
  - /api/reset 默认关闭，必须显式 --allow-reset 才开放，且同样受口令保护。

运行：
  python3 kb/server/classroom_server.py --port 8820
  YZ_SYNC_TOKEN=课堂口令 python3 kb/server/classroom_server.py --port 8820
  python3 kb/server/classroom_server.py --port 8820 --token 课堂口令 --allow-reset

接口：
  GET  /api/health   （探活，不校验口令）
  GET  /api/snapshot （设口令后需 X-Sync-Token）
  POST /api/merge    {"data": {...课堂数据...}}（设口令后需 X-Sync-Token）
  POST /api/reset    （默认 403；--allow-reset 后开放，需口令）
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import sqlite3
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MAX_BODY = 8 * 1024 * 1024
LOCK = threading.Lock()
DB_PATH = Path("classroom.db")
SYNC_TOKEN = ""
ALLOW_RESET = False
ALLOW_ORIGIN = "*"


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
        "tombstones": [],
    }


TOMBSTONE_TYPES = {"student", "assignment", "group", "post", "attempt"}


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
    if not isinstance(out.get("tombstones"), list):
        out["tombstones"] = []
    else:
        out["tombstones"] = [
            t for t in out["tombstones"]
            if isinstance(t, dict) and t.get("type") in TOMBSTONE_TYPES and t.get("id")
        ]
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


def _merge_tombstones(server: dict, client: dict) -> list[dict]:
    seen: dict[str, dict] = {}
    for t in list(server.get("tombstones") or []) + list(client.get("tombstones") or []):
        if not isinstance(t, dict):
            continue
        typ, oid = t.get("type"), t.get("id")
        if typ not in TOMBSTONE_TYPES or not oid:
            continue
        key = f"{typ}:{oid}"
        if key not in seen:
            seen[key] = {
                "type": typ,
                "id": oid,
                "classId": t.get("classId") or "",
                "name": t.get("name") or "",
                "at": t.get("at") or "",
            }
    return list(seen.values())


def _apply_tombstones(db: dict) -> None:
    """按墓碑剔除对象；删除必须能跨设备传播，否则 pull 会把旧对象加回来。"""
    toms = db.get("tombstones") or []
    if not toms:
        return

    def match_class(c: dict, cid: str) -> bool:
        return not cid or c.get("id") == cid or c.get("code") == cid

    for t in toms:
        typ, oid = t.get("type"), t.get("id") or ""
        cid, name = t.get("classId") or "", t.get("name") or ""
        if typ == "student":
            gone: set[str] = set()
            for c in db["classes"]:
                if not match_class(c, cid):
                    continue
                keep = []
                for s in c["students"]:
                    if (oid and s.get("id") == oid) or (name and s.get("name") == name):
                        gone.add(s.get("id"))
                    else:
                        keep.append(s)
                c["students"] = keep
            db["attempts"] = [
                a for a in db["attempts"]
                if not ((not cid or a.get("classId") == cid) and a.get("studentId") in gone)
            ]
        elif typ == "assignment":
            for c in db["classes"]:
                if match_class(c, cid):
                    c["assignments"] = [a for a in c["assignments"] if a.get("id") != oid]
            db["attempts"] = [a for a in db["attempts"] if a.get("assignmentId") != oid]
        elif typ == "group":
            for c in db["classes"]:
                if not match_class(c, cid):
                    continue
                gone = {
                    g.get("id") for g in c["groups"]
                    if (oid and g.get("id") == oid) or (name and g.get("name") == name)
                }
                c["groups"] = [g for g in c["groups"] if g.get("id") not in gone]
                if gone:
                    db["posts"] = [
                        p for p in db["posts"]
                        if not (p.get("classId") == c.get("id") and p.get("groupId") in gone)
                    ]
        elif typ == "post":
            db["posts"] = [p for p in db["posts"] if p.get("id") != oid]
        elif typ == "attempt":
            db["attempts"] = [a for a in db["attempts"] if a.get("id") != oid]


def merge(server: dict, client: dict) -> dict:
    """按 code / name / id 合并；先应用墓碑删除，再追加新增，删除才能跨设备生效。"""
    s = normalize(server)
    c = normalize(client)

    s["tombstones"] = _merge_tombstones(s, c)
    c["tombstones"] = s["tombstones"]
    _apply_tombstones(s)
    _apply_tombstones(c)

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
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Sync-Token")
        self.send_header("Cache-Control", "no-store")

    def _token_ok(self) -> bool:
        """未配置口令时放行（本机模式）；配置后 header 或 query 必须匹配。"""
        if not SYNC_TOKEN:
            return True
        sent = (self.headers.get("X-Sync-Token") or "").strip()
        if not sent:
            q = parse_qs(urlparse(self.path).query)
            sent = (q.get("token") or [""])[0].strip()
        return hmac.compare_digest(sent, SYNC_TOKEN)

    def _deny(self, error: str = "需要口令") -> None:
        self._json(401, {"ok": False, "error": error, "auth": "required"})

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
        if self.path.startswith("/api/health"):
            self._json(200, {"ok": True, "service": "radiocheck-classroom-sync", "db": str(DB_PATH),
                             "auth": bool(SYNC_TOKEN), "reset": ALLOW_RESET})
            return
        if self.path.startswith("/api/snapshot"):
            if not self._token_ok():
                self._deny()
                return
            with LOCK:
                db = read_db()
            self._json(200, {"ok": True, "data": db})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/merge", "/api/reset"}:
            self._json(404, {"ok": False, "error": "not found"})
            return
        if not self._token_ok():
            self._deny()
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

        if path == "/api/reset":
            if not ALLOW_RESET:
                self._json(403, {"ok": False, "error": "reset disabled; start with --allow-reset"})
                return
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
    global DB_PATH, SYNC_TOKEN, ALLOW_RESET, ALLOW_ORIGIN
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8820)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--db", default=".deepworks/tmp/classroom.db")
    parser.add_argument("--token", default=os.environ.get("YZ_SYNC_TOKEN", ""),
                        help="同步口令；也可用环境变量 YZ_SYNC_TOKEN")
    parser.add_argument("--allow-reset", action="store_true",
                        default=os.environ.get("YZ_ALLOW_RESET", "") == "1",
                        help="开放 /api/reset；也可用 YZ_ALLOW_RESET=1")
    parser.add_argument("--allow-origin", default=os.environ.get("YZ_ALLOW_ORIGIN", "*"),
                        help="CORS 允许的来源；建议设为站点地址，如 http://127.0.0.1:8811")
    args = parser.parse_args()
    DB_PATH = Path(args.db)
    SYNC_TOKEN = (args.token or "").strip()
    ALLOW_RESET = bool(args.allow_reset)
    ALLOW_ORIGIN = (args.allow_origin or "*").strip()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"RadioCheck classroom sync on http://{args.host}:{args.port}  db={DB_PATH}")
    if SYNC_TOKEN:
        print("口令保护：已开启（请求需带 X-Sync-Token 或 ?token=）")
    else:
        print("口令保护：未开启；仅用于本机/内网演示，不要暴露到公网。")
    if ALLOW_RESET:
        print("重置接口：已开放（需口令）；演示结束请关闭服务。")
    else:
        print("重置接口：已关闭（默认）。")
    if ALLOW_ORIGIN == "*":
        print("CORS：允许所有来源；跨域演示可保留，正式使用建议 --allow-origin 指定站点。")
    if args.host not in ("127.0.0.1", "localhost", "::1") and not SYNC_TOKEN:
        print("警告：监听非本机地址且未设口令，同网段任何人都能读写课堂数据。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
