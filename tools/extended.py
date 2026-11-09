"""🌙 미국 시간외(프리마켓·애프터마켓) 시세 — 정규장 값과 따로 둔다(2026-10-28 코덱스 점검 반영).

- 출처: NH투자증권 해외주식 현재가 API 먼저(운영자 11/9 지시), 실패하면 야후 1분봉(includePrePost=true)의 마지막 유효 체결. 호가·즉시 체결 보장 값이 아니다.
- 기준가: 직전 정규장 종가(meta.regularMarketPrice). chartPreviousClose 는 하루 더 앞 종가일 수 있어 쓰지 않는다.
- 세션 구분: meta.currentTradingPeriod 의 pre·regular·post 시간(미국 동부, 서머타임·휴장 반영은 야후 값을 따름)
- 지금 시간외 세션이 아니거나 마지막 체결이 15분보다 오래되면 stale=True. checked_at은 조회 시각, at은 원천 체결 시각이다.
- 하이퍼리퀴드 24시간 가격과 섞지 않는다(다른 상품).
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

STALE_S = 15 * 60


def session_of(t: int, reg_time: int, per: dict) -> str:
    """마지막 체결 시각 t(초) → 'pre' / 'reg' / 'post' (순수 함수, tests/test_extended.py)."""
    def inside(k):
        p = per.get(k) or {}
        return p.get("start", 0) <= t < p.get("end", 0)
    if inside("pre"):
        return "pre"
    if inside("regular"):
        return "reg"
    if inside("post"):
        return "post"
    return "post" if t > reg_time else "reg"              # 지난 거래일 애프터마켓 / 정규장 체결


def build_one(meta: dict, ts: list, closes: list, now: float) -> dict | None:
    base = meta.get("regularMarketPrice")
    idx = [i for i, c in enumerate(closes or []) if c]
    if not base or not idx:
        return None
    i = idx[-1]
    t, px = int(ts[i]), float(closes[i])
    per = meta.get("currentTradingPeriod") or {}
    sess = session_of(t, int(meta.get("regularMarketTime") or 0), per)
    if sess == "reg":
        return None
    p = per.get("pre" if sess == "pre" else "post") or {}
    live = p.get("start", 0) <= now < p.get("end", 0)
    return {"sess": sess, "px": round(px, 4), "base": round(float(base), 4), "change": round(px - base, 4), "chg": round((px / base - 1) * 100, 2),
            "at": t * 1000, "checked_at": int(now * 1000), "live": live, "stale": (not live) or now - t > STALE_S}


NH_SESS = {"0": "pre", "2": "post", "3": "day"}   # 1=정규장(야후·정규장 자료로) · 3=주간거래(한국 낮 시간)
_nh_lock = threading.Lock()
_nh_down_until = 0.0
_nh_gap = threading.Lock()
_nh_last = 0.0


# 모의매매(같은 앱 키)가 주문을 내는 시간대 — 이때만 NH 시세를 쉬고 야후로 (KST HHMM 구간)
TRADER_BUSY = ((900, 920), (1058, 1106), (1428, 1436), (1505, 1522))


def nh_gap(now: float) -> float | None:
    """NH 호출 간격(초). None 이면 지금은 NH를 쓰지 않는다.
    평일 한국장(08:50~15:40)에는 간격을 1초로 늘리고 모의매매 주문 시간대는 건너뛴다 — 호출 한도(IGW42902)를 나눠 쓰므로."""
    t = datetime.fromtimestamp(now, ZoneInfo("Asia/Seoul"))
    hm = t.hour * 100 + t.minute
    if t.weekday() < 5 and 850 <= hm <= 1540:
        return None if any(a <= hm <= b for a, b in TRADER_BUSY) else 1.0
    return 0.35


def _nh_token():
    """NH 시세용 토큰(키 파일 ~/.nhplug/.env, 토큰은 ~/.cache 에만 저장 — nh_quotes.py 와 같은 캐시)."""
    import nh_quotes
    with _nh_lock:
        return nh_quotes.access_token(Path(os.environ.get("NH_APP_KEY_FILE") or Path.home() / ".nhplug" / ".env"))


def nh_quote(sym: str, now: float, gap: float = 0.35) -> dict | None:
    """NH투자증권 해외주식 현재가(프리·애프터 세션 체결가, 기준가=직전 정규장 종가). 운영자 11/9 지시."""
    import nh_quotes
    global _nh_last
    tok = _nh_token()
    with _nh_gap:                                  # 초당 호출 건수 제한(IGW42902) — 호출 사이 NH_GAP 초
        time.sleep(max(0.0, _nh_last + gap - time.time()))
        _nh_last = time.time()
    r = nh_quotes.request("/gbstock/quote/v1/current", {"Input_0": {"iem_cd": sym}}, tok)
    o = r.get("Output_0") or {}
    if r.get("rsp_cd") != "00000":
        raise ValueError("NH quote rejected")
    sess = NH_SESS.get(str(o.get("marketperiod_cls")))
    px, base = float(o.get("trdprc") or 0), float(o.get("normal_trdprc") or 0)
    if not sess or px <= 0 or base <= 0:
        return None
    try:
        t = datetime.strptime(f"{o['trade_date']}{o['quote_time']}", "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("America/New_York")).timestamp()
    except Exception:  # noqa: BLE001
        t = now
    if not (now - 12 * 3600 < t <= now + 120):     # 시각 형식이 다르면 조회 시각으로
        t = now
    # NH 가 알려 주는 구분이 '지금 열린 세션'이므로 live. 마지막 체결이 오래됐으면(거래 적은 종목) stale 로 표시만 한다.
    live = True
    return {"sess": sess, "px": round(px, 4), "base": round(base, 4), "change": round(px - base, 4), "chg": round((px / base - 1) * 100, 2),
            "at": int(t * 1000), "checked_at": int(now * 1000), "live": live, "stale": now - t > STALE_S, "src": "NH"}


def quote(sym: str) -> dict | None:
    """NH 먼저, 실패하면 야후. 호출 한도 초과(429)는 그 종목만 야후로, 그 밖의 NH 오류는 10분 동안 야후만 쓴다."""
    global _nh_down_until
    now = time.time()
    gap = nh_gap(now)
    if now >= _nh_down_until and gap is not None:
        try:
            q = nh_quote(sym, now, gap)
            if q:
                return q
        except urllib.error.HTTPError as e:
            if e.code != 429:
                _nh_down_until = now + 600
        except Exception:  # noqa: BLE001
            _nh_down_until = now + 600
    q = yahoo_quote(sym)
    if q:
        q["src"] = "야후"
    return q


def yahoo_quote(sym: str) -> dict | None:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?interval=1m&range=1d&includePrePost=true"
    r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read())["chart"]["result"][0]
    return build_one(r["meta"], r.get("timestamp") or [], r["indicators"]["quote"][0].get("close") or [], time.time())


if __name__ == "__main__":
    for s in ("SOXL", "KORU", "EWY"):
        print(s, quote(s))
