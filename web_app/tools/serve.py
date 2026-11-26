from __future__ import annotations

import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


handler = partial(NoCacheHandler, directory=str(ROOT))
with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    print(f"DDNet Mini App: {url}", flush=True)
    print("Оставь это окно открытым, чтобы сервер работал. Для остановки нажми Ctrl+C.", flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.", flush=True)
