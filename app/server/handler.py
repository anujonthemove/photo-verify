import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote


class PhotoVerifyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Suppress default request log spam

    # ── Response helpers ──────────────────────────────────────────────────────

    def _json(self, data: dict, code: int = 200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type',   'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control',  'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def _image(self, data: bytes, mime: str = 'image/jpeg'):
        self.send_response(200)
        self.send_header('Content-Type',   mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control',  'max-age=300')
        self.end_headers()
        self.wfile.write(data)

    def _404(self):
        self.send_response(404)
        self.end_headers()

    def _read_body(self) -> dict:
        n = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(n)) if n else {}

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        from app.server import routes_get
        u  = urlparse(self.path)
        qs = parse_qs(u.query)
        routes_get.dispatch(self, u, qs)

    def do_POST(self):
        from app.server import routes_post
        u    = urlparse(self.path)
        body = self._read_body()
        routes_post.dispatch(self, u, body)
