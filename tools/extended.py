"""🌙 미국 시간외(프리마켓·애프터마켓) 시세 — 정규장 값과 따로 둔다(2026-10-28 코덱스 점검 반영).

- 출처: 야후 1분봉(includePrePost=true)의 마지막 유효 체결. 호가·즉시 체결 보장 값이 아니다.
- 기준가: 직전 정규장 종가(meta.regularMarketPrice). chartPreviousClose 는 하루 더 앞 종가일 수 있어 쓰지 않는다.
- 세션 구분: meta.currentTradingPeriod 의 pre·regular·post 시간(미국 동부, 서머타임·휴장 반영은 야후 값을 따름)
- 지금 시간외 세션이 아니거나 마지막 체결이 15분보다 오래되면 stale=True → 화면에 '마지막 체결'로 표시(현재 시각을 붙이지 않음)
- 하이퍼리퀴드 24시간 가격과 섞지 않는다(다른 상품).
"""

from __future__ import annotations

import json
import time
import urllib.request

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
    return {"sess": sess, "px": round(px, 2), "base": round(float(base), 2), "chg": round((px / base - 1) * 100, 2),
            "at": t * 1000, "live": live, "stale": (not live) or now - t > STALE_S}


def quote(sym: str) -> dict | None:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?interval=1m&range=1d&includePrePost=true"
    r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read())["chart"]["result"][0]
    return build_one(r["meta"], r.get("timestamp") or [], r["indicators"]["quote"][0].get("close") or [], time.time())


if __name__ == "__main__":
    for s in ("SOXL", "KORU", "EWY"):
        print(s, quote(s))
