#!/usr/bin/env python3
"""无 Swift 壳时的兜底入口：本地起服务并用默认浏览器打开。

用法：
    python3 desktop/start.py
或双击 desktop/start.command
"""
import http.server
import os
import socketserver
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "outputs/medtrain"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".webmanifest": "application/manifest+json",
        ".json": "application/json; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
    }

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def main() -> None:
    if not (SITE / "read/clinic.html").exists():
        raise SystemExit("站点未构建，请先运行 python3 medtrain/build.py")
    os.chdir(SITE)

    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as httpd:
        httpd.daemon_threads = True
        port = httpd.server_address[1]
        url = "http://127.0.0.1:%d/" % port
        print("RadioCheck 已启动：%s" % url)
        print("关闭此窗口或按 Ctrl+C 停止。")
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止。")


if __name__ == "__main__":
    main()
