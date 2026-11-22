#!/usr/bin/env python3
"""知识库演示服务：零依赖 HTTP + JSON API。

启动：python3 kb/scripts/serve.py --port 4180
"""
import argparse
import json
import mimetypes
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT / "scripts"))
from kbsearch import KB  # noqa: E402
from dual import assess  # noqa: E402
import online_search  # noqa: E402

KB_INSTANCE = KB()


def send_json(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def send_file(handler, path, cache=False):
    if not path.exists() or not path.is_file():
        send_json(handler, {"error": "not_found"}, 404)
        return
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "public, max-age=3600" if cache else "no-store")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server_version = "DeepWorksKB/1.0"

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        one = lambda k: (qs.get(k) or [None])[0]

        try:
            if u.path == "/api/search":
                q = one("q") or ""
                r = KB_INSTANCE.search(q, modality=one("modality"), part=one("part"))
                r["stats"] = KB_INSTANCE.stats()
                send_json(self, r)
            elif u.path == "/api/dual":
                q = one("q") or ""
                send_json(self, assess(KB_INSTANCE, q, modality=one("modality"), part=one("part")))
            elif u.path == "/api/taxonomy":
                send_json(self, KB_INSTANCE.taxonomy())
            elif u.path == "/api/sign-index":
                send_json(self, {"items": KB_INSTANCE.sign_index()})
            elif u.path == "/api/sign-links":
                send_json(self, KB_INSTANCE.sign_links(sign_id=one("sign"), image_id=one("image")))
            elif u.path.startswith("/api/sign/"):
                doc = KB_INSTANCE.sign_detail(urllib.parse.unquote(u.path.rsplit("/", 1)[-1]))
                send_json(self, doc or {"error": "not_found"}, 200 if doc else 404)
            elif u.path == "/api/groups":
                send_json(self, {"items": KB_INSTANCE.groups(region=one("region"))})
            elif u.path == "/api/images":
                send_json(self, {"items": KB_INSTANCE.images(
                    modality=one("modality"), part=one("part"), sign=one("sign"),
                    group=one("group"), region=one("region"))})
            elif u.path == "/api/similar":
                send_json(self, online_search.search(
                    one("q") or "", region=one("region"), condition=one("condition"),
                    provider=one("provider") or "all",
                    limit=int(one("limit") or 6), timeout=float(one("timeout") or 6)))
            elif u.path == "/api/stats":
                send_json(self, KB_INSTANCE.stats())
            elif u.path.startswith("/api/doc/"):
                doc = KB_INSTANCE.get(urllib.parse.unquote(u.path.rsplit("/", 1)[-1]))
                send_json(self, doc or {"error": "not_found"}, 200 if doc else 404)
            elif u.path.startswith("/api/related/"):
                send_json(self, {"items": KB_INSTANCE.related(urllib.parse.unquote(u.path.rsplit("/", 1)[-1]))})
            elif u.path.startswith("/images/"):
                name = urllib.parse.unquote(u.path.split("/", 2)[-1])
                target = (ROOT / "images" / name).resolve()
                if ROOT / "images" not in target.parents:
                    send_json(self, {"error": "forbidden"}, 403)
                    return
                send_file(self, target, cache=True)
            elif u.path in ("/", "/index.html"):
                send_file(self, WEB / "index.html")
            else:
                name = urllib.parse.unquote(u.path.lstrip("/"))
                target = (WEB / name).resolve()
                if WEB not in target.parents:
                    send_json(self, {"error": "forbidden"}, 403)
                    return
                send_file(self, target)
        except BrokenPipeError:
            pass
        except Exception as e:
            send_json(self, {"error": "server_error", "detail": str(e)[:200]}, 500)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except Exception:
            send_json(self, {"error": "bad_json"}, 400)
            return
        if u.path == "/api/similar/queue":
            send_json(self, online_search.queue_candidate(body))
        else:
            send_json(self, {"error": "not_found"}, 404)

    def log_message(self, fmt, *args):
        if args and str(args[1]).startswith("4"):
            sys.stderr.write("HTTP %s %s\n" % (args[0], args[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4180)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"KB demo: http://{a.host}:{a.port}")
    print("stats:", json.dumps(KB_INSTANCE.stats(), ensure_ascii=False))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
