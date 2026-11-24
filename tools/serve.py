# -*- coding: utf-8 -*-
"""Локальная проверка: python tools/serve.py  ->  http://localhost:8000/p15-postirochnaya/

* раздаёт файлы репозитория;
* /api — те же замечания, что в облаке, но в папке .local-notes/ (код мастера: test);
* PUT …/preview.jpg — сохраняет картинку для превью в мессенджерах
  (откройте страницу с ?savepreview, «Ещё» → «Снимок»).
"""
import http.server
import json
import os
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
import index as notes  # noqa: E402

STORE = notes.FileStore(os.path.join(ROOT, '.local-notes'))
ADMIN = os.environ.get('LOCAL_ADMIN', 'test')


class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.glb': 'model/gltf-binary', '.json': 'application/json'}

    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _api(self, method):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n).decode('utf-8') if n else ''
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {}
        code, res = notes.handle(method, q.get('project', ''), body, STORE, ADMIN, 'http://localhost:8000/')
        self._json(code, res)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == '/api':
            return self._api('GET')
        if p == '/viewer/config.js':
            with open(os.path.join(ROOT, 'viewer', 'config.js'), encoding='utf-8') as f:
                js = f.read().replace("api: ''", "api: '/api'")
            b = js.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        return super().do_GET()

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path == '/api':
            return self._api('POST')
        self.send_error(404)

    def do_PUT(self):
        p = urllib.parse.unquote(urllib.parse.urlparse(self.path).path).strip('/')
        parts = p.split('/')
        if len(parts) == 2 and parts[1] == 'preview.jpg' and os.path.isfile(os.path.join(ROOT, parts[0], 'model.json')):
            n = int(self.headers.get('Content-Length') or 0)
            with open(os.path.join(ROOT, parts[0], 'preview.jpg'), 'wb') as f:
                f.write(self.rfile.read(n))
            return self._json(200, {'ok': True})
        self.send_error(403)


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print('http://localhost:%d/  (код мастера для проверки: #admin=%s)' % (port, ADMIN))
    http.server.ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
