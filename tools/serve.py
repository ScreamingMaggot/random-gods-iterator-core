"""本地开发服务：静态托管项目根目录，禁缓存以便改代码即刷新；支持 Range 以便音频拖动。

用法：python tools/serve.py [端口]，默认 8712。
打开  http://127.0.0.1:8712/web/
"""
from __future__ import annotations

import http.server
import mimetypes
import os
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def _path(self):
        rel = urllib.parse.unquote(self.path.split("?", 1)[0].lstrip("/"))
        p = (ROOT / rel).resolve()
        if not str(p).startswith(str(ROOT)):
            return None
        if p.is_dir():
            p = p / "index.html"
        return p if p.is_file() else None

    def do_GET(self):
        self._serve(with_body=True)

    def do_HEAD(self):
        self._serve(with_body=False)

    def _serve(self, with_body):
        p = self._path()
        if p is None or not p.is_file():
            body = b"not found"
            self.send_response(404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if with_body:
                self.wfile.write(body)
            return
        size = p.stat().st_size
        ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        code = 200
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a or 0)
            if b:
                end = min(int(b), size - 1)
            code = 206
        if start > end or start >= size:
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.end_headers()
            return
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if not with_body:
            return
        with open(p, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8712
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("[serve] http://127.0.0.1:%d/web/  (root=%s)" % (port, ROOT))
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
