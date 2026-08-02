"""
ProxyGuard: Lightweight Python HTTP proxy guard for blocking direct access to Cloud Run.
Enforces the X-Orca-Proxy-Secret header sent exclusively by Cloudflare Worker.
"""

import os
import sys
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

PROXY_SECRET = os.environ.get("ORCA_PROXY_SECRET", "orca-cloudflare-secret-987654321")
TARGET_PORT = int(os.environ.get("TARGET_PORT", "8081"))

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class ProxyGuardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress verbose log noise

    def handle_proxy(self):
        secret = self.headers.get("X-Orca-Proxy-Secret")
        if secret != PROXY_SECRET:
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"403 Forbidden: Direct access denied. Please access via https://orca-datawarehouse.dev\n")
            return

        target_url = f"http://127.0.0.1:{TARGET_PORT}{self.path}"
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'transfer-encoding')}
        headers['Host'] = f"127.0.0.1:{TARGET_PORT}"

        body = None
        content_length = self.headers.get('Content-Length')
        if content_length and int(content_length) > 0:
            body = self.rfile.read(int(content_length))

        try:
            req = urllib.request.Request(target_url, data=body, headers=headers, method=self.command)
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ('transfer-encoding', 'content-length'):
                        self.send_header(k, v)
                resp_body = resp.read()
                self.send_header('Content-Length', str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"502 Bad Gateway: Upstream service error.\n")

    do_GET = handle_proxy
    do_POST = handle_proxy
    do_PUT = handle_proxy
    do_DELETE = handle_proxy
    do_HEAD = handle_proxy
    do_OPTIONS = handle_proxy

if __name__ == '__main__':
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadedHTTPServer(('0.0.0.0', port), ProxyGuardHandler)
    print(f"ProxyGuard active on port {port}, forwarding to internal port {TARGET_PORT}")
    server.serve_forever()
