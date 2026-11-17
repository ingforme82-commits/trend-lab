"""한투(KIS) 웹소켓 실시간 체결 → 저장소 밖 rt.json(1초마다). 조회 전용. 2026-11-16 운영자: "더 빠르고 정확한 방법, 실시간으로".

1분마다 묻는 방식(REST) 대신 체결이 날 때마다 받는다. 표준 라이브러리만 씀(서버에 추가 설치 없음).
- 국내 주식 H0STCNT0, 국내 지수 H0UPCNT0, 미국 주식 HDFSCNT0(지연 없는 무료 범위는 KIS 정책을 따름)
- 넥스트레이드(NXT) 프리·애프터마켓: 국내주식 통합 체결 H0UNCNT0(KRX+NXT, 칸 배치는 H0STCNT0과 같음 — KIS 공식 예제 ccnl_total).
  2026-11-18 운영자 "넥장까지 실시간". 08:00~09:00·15:30~20:00 KST 는 지수가 안 움직이므로 삼성전자·SK하이닉스·SK스퀘어 NXT 체결로 바꿔 받는다.
- 등락률 = 현재가 ÷ (현재가 − 부호 있는 전일 대비) − 1 → 기준(전일 종가)도 함께 저장(ref)
- 끊기면 다시 붙음(5→60초). 연결·수신 결과는 출처 점수판(srcscore 'rt')에 기록
- 키: keystore KIS_APP_KEY/KIS_APP_SECRET(값은 출력하지 않음)

  python tools/rt_kis.py            # 계속 실행(서버 서비스용)
  python tools/rt_kis.py --once 20  # 20초만 받아 보고 끝(점검)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import struct
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

BASE = "https://openapi.koreainvestment.com:9443"
WS_HOST, WS_PORT = "ops.koreainvestment.com", 21000
OUT = keystore.state_dir() / "rt.json"
# 11/16 확인: 이 키는 접속 1개(두 번째는 ALREADY IN USE)·동시 구독 3종목까지(4번째 MAX SUBSCRIBE OVER)
# → 시간대별로 3개씩 바꿔 받는다. KRX 정규장(09:00~15:30 KST) 지수, NXT 프리(08:00~09:00)·애프터(15:30~20:00) 삼성전자·SK하이닉스·SK스퀘어, 그 밖은 SOXL·SKHY·KORU.
MAX_SUBS = 3
SUBS_KR = [("H0UPCNT0", "0001", "KOSPI", "코스피"), ("H0UPCNT0", "2001", "KR200", "코스피200"), ("H0UPCNT0", "1001", "KOSDAQ", "코스닥")]
SUBS_US = [("HDFSCNT0", "DAMSSOXL", "SOXL", "SOXL"), ("HDFSCNT0", "DNASSKHY", "SKHY", "SKHY"), ("HDFSCNT0", "DAMSKORU", "KORU", "KORU")]   # 11/16 운영자: SK하이닉스 ADR(나스닥 코드 확인). DRAM·MU 는 1분 값
SUBS_NXT = [("H0UNCNT0", "005930", "SMSN", "삼성전자"), ("H0UNCNT0", "000660", "SKHX", "SK하이닉스"), ("H0UNCNT0", "402340", "SKSQ", "SK스퀘어")]   # 통합 체결 — 장 밖엔 NXT 체결만 들어옴
SUBS = SUBS_KR + SUBS_NXT + SUBS_US


def subs_now(now: float | None = None) -> list[tuple]:
    from datetime import datetime, timedelta, timezone
    k = datetime.fromtimestamp(now or time.time(), timezone(timedelta(hours=9)))
    m = k.hour * 60 + k.minute
    if k.weekday() < 5 and 9 * 60 <= m < 15 * 60 + 30:      # KRX 정규장
        return SUBS_KR[:MAX_SUBS]
    if k.weekday() < 5 and 8 * 60 <= m < 20 * 60:           # NXT 프리마켓(08:00~08:50)·애프터마켓(15:40~20:00) — 단일가 구간 포함
        return SUBS_NXT[:MAX_SUBS]
    return SUBS_US[:MAX_SUBS]


# 체결 메시지에서 (현재가, 부호, 전일 대비, 시각) 칸 위치
FIELDS = {"H0STCNT0": (2, 3, 4, 1), "H0UNCNT0": (2, 3, 4, 1), "H0UPCNT0": (2, 3, 4, 1), "HDFSCNT0": (11, 12, 13, 7)}


def approval_key() -> str:
    ks = keystore.pair("KIS_APP_KEY", "KIS_APP_SECRET")
    if not ks:
        raise SystemExit("KIS 키 없음(KIS_APP_KEY·KIS_APP_SECRET)")
    body = json.dumps({"grant_type": "client_credentials", "appkey": ks[0], "secretkey": ks[1]}).encode()
    r = urllib.request.urlopen(urllib.request.Request(BASE + "/oauth2/Approval", body, {"Content-Type": "application/json; charset=UTF-8",
                                                                                        "User-Agent": "trendlab/1.0"}), timeout=10)
    return json.loads(r.read())["approval_key"]


class WS:
    """아주 작은 웹소켓(ws://, 텍스트 프레임) 클라이언트."""

    def __init__(self, host: str, port: int, path: str = "/tryitout/H0STCNT0"):
        self.s = socket.create_connection((host, port), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            c = self.s.recv(1)
            if not c:
                raise ConnectionError("핸드셰이크 끊김")
            head += c
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise ConnectionError(head.split(b"\r\n")[0].decode(errors="replace"))
        self.s.settimeout(20)

    def _send(self, op: int, data: bytes) -> None:
        mask = os.urandom(4)
        n = len(data)
        hdr = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536
                                    else bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def send(self, text: str) -> None:
        self._send(0x1, text.encode())

    def _exact(self, n: int) -> bytes:
        b = b""
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise ConnectionError("연결 끊김")
            b += c
        return b

    def recv(self) -> str:
        buf = b""
        while True:
            b1, b2 = self._exact(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exact(8))[0]
            if b2 & 0x80:
                m = self._exact(4)
                data = bytes(x ^ m[i % 4] for i, x in enumerate(self._exact(n)))
            else:
                data = self._exact(n)
            if op == 0x9:                               # ping → pong
                self._send(0xA, data)
                continue
            if op == 0x8:
                raise ConnectionError("서버가 닫음")
            buf += data
            if b1 & 0x80:
                return buf.decode("utf-8", errors="replace")

    def close(self) -> None:
        try:
            self._send(0x8, b"")
            self.s.close()
        except OSError:
            pass


def parse(msg: str, keymap: dict) -> list[dict]:
    """'0|TRID|건수|칸^칸^…' → [{key, px, chg, ref, t}]. 부호 4·5 = 하락."""
    parts = msg.split("|", 3)
    if len(parts) < 4 or parts[0] not in ("0", "1") or parts[1] not in FIELDS:
        return []
    tr, n = parts[1], max(1, int(parts[2] or 1))
    f = parts[3].split("^")
    size = len(f) // n
    rec = f[size * (n - 1):]                             # 여러 건이면 마지막 체결
    ip, isg, idf, it = FIELDS[tr]
    try:
        px, diff = float(rec[ip]), abs(float(rec[idf]))
    except (ValueError, IndexError):
        return []
    sign = rec[isg].strip()
    if sign in ("4", "5"):
        diff = -diff
    elif sign == "3":
        diff = 0.0
    ref = px - diff
    code = rec[0] if tr != "HDFSCNT0" else rec[0]
    key = keymap.get((tr, code)) or keymap.get((tr, rec[1] if len(rec) > 1 else ""))
    if not key or px <= 0 or ref <= 0:
        return []
    out = {"key": key, "px": px, "chg": round((px / ref - 1) * 100, 2), "ref": round(ref, 4), "t": rec[it]}
    if tr == "H0UNCNT0":
        t = rec[it].strip()
        out["mk"] = "KRX+NXT" if t[:4].isdigit() and "0900" <= t[:4] < "1530" else "NXT"   # 체결 시각으로 세션 구분
    return [out]


def subscribe(ws: WS, ak: str, subs: list[tuple]) -> None:
    for tr, k, _, _ in subs:
        ws.send(json.dumps({"header": {"approval_key": ak, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
                            "body": {"input": {"tr_id": tr, "tr_key": k}}}))
        time.sleep(0.2)


def write(state: dict) -> None:
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT.with_suffix(".tmp")
        tmp.write_text(json.dumps({"at": int(time.time() * 1000), "src": "KIS-WS", "q": state}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(OUT)
    except OSError:
        pass


def run(seconds: float | None = None, verbose: bool = False) -> dict:
    import srcscore
    keymap = {}
    for tr, k, key, _ in SUBS:
        keymap[(tr, k)] = key
        if tr == "HDFSCNT0":
            keymap[(tr, k[1:])] = key                    # 응답의 RSYM 이 'DNASNVDA' 또는 'NASNVDA' 일 때
            keymap[(tr, k[4:])] = key                    # SYMB 'NVDA'
    state: dict = {}
    try:
        state = json.loads(OUT.read_text(encoding="utf-8")).get("q") or {}
    except Exception:  # noqa: BLE001
        pass
    end = time.time() + seconds if seconds else None
    wait, acks = 5, []
    while end is None or time.time() < end:
        ws = None
        try:
            ak = approval_key()
            ws = WS(WS_HOST, WS_PORT)
            cur = subs_now()
            subscribe(ws, ak, cur)
            srcscore.record("rt", "KIS-WS", True)
            wait, last_w = 5, time.time()
            write(state)                                    # 체결이 없어도(장 밖) 살아 있음을 알린다 → rt_url 이 사이트에 실림
            while end is None or time.time() < end:
                if subs_now() != cur:                       # 한국장 ↔ 미국 시간 바뀌면 다시 붙어 종목 교체
                    break
                if time.time() - last_w >= 30:
                    write(state)
                    last_w = time.time()
                try:
                    m = ws.recv()
                except socket.timeout:
                    continue
                if m.startswith("{"):
                    j = json.loads(m)
                    h = j.get("header") or {}
                    if h.get("tr_id") == "PINGPONG":
                        ws.send(m)                          # KIS 연결 유지 신호는 그대로 돌려준다
                    else:
                        b = j.get("body") or {}
                        acks.append(f"{h.get('tr_id')} {h.get('tr_key')}: {b.get('msg1', '').strip()}")
                        if verbose:
                            print("  구독", acks[-1])
                    continue
                for r in parse(m, keymap):
                    r["at"] = int(time.time() * 1000)
                    state[r.pop("key")] = r
                    if verbose:
                        print("  체결", json.dumps(r, ensure_ascii=False))
                if time.time() - last_w >= 1:
                    write(state)
                    last_w = time.time()
        except Exception as e:  # noqa: BLE001
            srcscore.record("rt", "KIS-WS", False)
            print(f"  연결 오류: {type(e).__name__}: {str(e)[:120]} → {wait}초 뒤 다시", flush=True)
            if end is not None and time.time() + wait >= end:
                break
            time.sleep(wait)
            wait = min(60, wait * 2)
        finally:
            if ws:
                ws.close()
            write(state)
    return {"acks": acks, "q": state}


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", type=float, help="이 초만큼만 받아 보고 끝")
    a = ap.parse_args()
    r = run(a.once, verbose=bool(a.once))
    if a.once:
        print(f"구독 응답 {len(r['acks'])}건 · 받은 종목 {len(r['q'])}개 → {OUT}")


if __name__ == "__main__":
    main()
