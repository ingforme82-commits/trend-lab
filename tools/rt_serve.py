"""실시간 값(rt.json)을 사이트로 바로 내보내는 작은 웹 서버 + Cloudflare 무료 터널. 2026-11-16 운영자 승인(③).

GitHub 를 거치면 몇 분 늦는다 → Oracle 서버 → (Cloudflare 터널 https) → 사이트가 2초마다 직접 받는다.
- 공개 시세 GET /rt, 게시 검증을 통과한 공개 뉴스·채널·5일선 GET /news, 익명 집계 POST /presence만 받는다. 키·계좌·주문 정보는 내보내지 않는다.
- 터널 주소(https://….trycloudflare.com)는 rt_url.txt 에 적고, live_news 가 news.json 'rt_url' 로 싣는다(주소가 바뀌어도 사이트가 따라감).
- 비용 0: Cloudflare 무료 빠른 터널(계정·도메인 불필요). 고정 주소가 필요하면 도메인(연 1~2만 원) — 운영자 확인 뒤.

  python3 tools/rt_serve.py            # 웹 서버(127.0.0.1:8787) + 터널(cloudflared 있으면)
  python3 tools/rt_serve.py --no-tunnel
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402
import visitor_stats  # noqa: E402
import fast_feed  # noqa: E402

RT = keystore.state_dir() / "rt.json"
URL_FILE = keystore.state_dir() / "rt_url.txt"
PORT = 8787
VISITORS = keystore.state_dir() / 'visitors.sqlite3'


class H(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        if self.path != '/presence':
            self.send_error(404)
            return
        origin = self.headers.get('Origin')
        if origin != visitor_stats.ORIGIN:
            self.send_error(403)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 256:
                self.send_error(413)
                return
            self.connection.settimeout(5)
            payload = json.loads(self.rfile.read(size))
            if not visitor_stats.valid(payload):
                self.send_error(400)
                return
            visitor_stats.heartbeat(VISITORS, payload)
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        except Exception:
            self.send_error(503)
            return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Vary', 'Origin')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if self.path.split('?')[0] == '/news':
            try:
                body, etag = fast_feed.read_public()
            except Exception:
                self.send_response(503)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                return
            not_modified = self.headers.get('If-None-Match') == etag
            query_match = parse_qs(urlsplit(self.path).query).get('tag', [''])[0] == etag
            self.send_response(204 if query_match else 304 if not_modified else 200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Expose-Headers', 'ETag')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('ETag', etag)
            self.end_headers()
            if not not_modified and not query_match:
                self.wfile.write(body)
            return
        if self.path.split("?")[0] != "/rt":
            self.send_response(404)
            self.end_headers()
            return
        try:
            body = RT.read_bytes()
        except OSError:
            body = b'{"q":{}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # 접속 기록은 남기지 않는다
        pass


def tunnel() -> None:
    """cloudflared 빠른 터널을 띄우고 주소를 rt_url.txt 에 적는다. 끊기면 다시."""
    while True:
        try:
            p = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except FileNotFoundError:
            print("cloudflared 없음 → 터널 없이 웹 서버만(설치: scripts/oracle_rt_setup.sh)", flush=True)
            return
        for line in p.stdout:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m:
                URL_FILE.write_text(m.group(0), encoding="utf-8")
                print("터널 주소:", m.group(0), flush=True)
        p.wait()
        URL_FILE.unlink(missing_ok=True)
        time.sleep(10)


def url() -> str | None:
    """live_news 용: 지금 터널 주소(10분 넘게 rt.json 이 안 바뀌면 None — 죽은 값은 내보내지 않음)."""
    try:
        if time.time() - RT.stat().st_mtime > 600:
            return None
        u = URL_FILE.read_text(encoding="utf-8").strip()
        return u if u.startswith("https://") else None
    except OSError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tunnel", action="store_true")
    a = ap.parse_args()
    if not a.no_tunnel:
        threading.Thread(target=tunnel, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
