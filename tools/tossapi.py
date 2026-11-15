"""토스증권 Open API — 조회 전용(국내·미국 현재가, 코스피·코스닥, 한국 국채 금리). 주문·계좌는 쓰지 않는다. 2026-11-16 운영자 요청.

- 키: TOSS_CLIENT_ID / TOSS_CLIENT_SECRET (keystore). 출력·저장소에 남기지 않는다. 허용 IP 에 Oracle 서버 IP 등록 필요.
- 주소: https://openapi.tossinvest.com · 토큰 POST /oauth2/token (form: grant_type·client_id·client_secret, 24시간, 재발급 시 이전 토큰 무효)
- 현재가 GET /api/v1/prices?symbols=005930,AAPL (최대 200) — lastPrice 만 준다 → 등락률은 일봉(/candles 1d) 전일 종가로 계산
- 지표 GET /api/v1/market-indicators/prices?symbols=KOSPI,KOSDAQ,KR_BOND_3Y,KR_BOND_10Y
- 웹소켓(wss://openapi-ws.tossinvest.com/ws/v1): 연결 2개·연결당 100종목 — 실시간 경로는 rt_kis 다음 단계
- 공식 스펙: https://openapi.tossinvest.com/openapi-docs/latest/openapi.json

  python tools/tossapi.py      # 연결 점검(키는 출력하지 않음)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://openapi.tossinvest.com"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

TOKEN = keystore.state_dir() / "toss_token.json"
DOWN = keystore.state_dir() / "toss_down.json"
REST_S = 10 * 60
ALLOW = ("/api/v1/prices", "/api/v1/candles", "/api/v1/market-indicators/prices", "/api/v1/exchange-rate")   # 조회만
UA = {"User-Agent": "trendlab/1.0", "Accept": "application/json"}
INDICATORS = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ", "KR3Y": "KR_BOND_3Y", "KR10Y": "KR_BOND_10Y"}


def _down(why: str | None = None) -> str | None:
    if why:
        try:
            DOWN.write_text(json.dumps({"at": time.time(), "why": why[:120]}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return why
    try:
        d = json.loads(DOWN.read_text(encoding="utf-8"))
        return d["why"] if time.time() - d["at"] < REST_S else None
    except Exception:  # noqa: BLE001
        return None


def _token() -> str | None:
    try:
        t = json.loads(TOKEN.read_text(encoding="utf-8"))
        if t["exp"] - time.time() > 600:
            return t["v"]
    except Exception:  # noqa: BLE001
        pass
    ks = keystore.pair("TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET")
    if not ks:
        _down("키 없음(TOSS_CLIENT_ID)")
        return None
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": ks[0], "client_secret": ks[1]}).encode()
    try:
        j = json.loads(urllib.request.urlopen(urllib.request.Request(BASE + "/oauth2/token", body,
                                              {"Content-Type": "application/x-www-form-urlencoded", **UA}), timeout=10).read())
    except urllib.error.HTTPError as e:
        _down(f"토큰 실패: HTTP {e.code} {' '.join(e.read().decode('utf-8', 'replace').split())[:100]}")
        return None
    except Exception as e:  # noqa: BLE001
        _down(f"토큰 실패: {type(e).__name__}")
        return None
    if not j.get("access_token"):
        _down("토큰 실패: 응답에 토큰 없음")
        return None
    keystore.write_private(TOKEN, json.dumps({"v": j["access_token"], "exp": time.time() + int(j.get("expires_in") or 3600)}))
    return j["access_token"]


def get(path: str, params: dict) -> dict:
    if path not in ALLOW:
        raise PermissionError("토스 모듈은 시세 조회만 쓴다")
    if _down():
        return {}
    tok = _token()
    if not tok:
        return {}
    req = urllib.request.Request(BASE + path + "?" + urllib.parse.urlencode(params), headers={"Authorization": "Bearer " + tok, **UA})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=8).read())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            TOKEN.unlink(missing_ok=True)
        return {}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        _down(f"접속 실패: {type(e).__name__}")
        return {}
    except ValueError:
        return {}


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


_PREV: dict = {}


def prev_close(symbol: str) -> float | None:
    """일봉 최신순 → 오늘 봉이 있으면 그 전 봉 종가, 없으면 최신 봉 종가. 하루 한 번만 묻는다(메모리 캐시)."""
    day = time.strftime("%Y%m%d")
    if (symbol, day) in _PREV:
        return _PREV[(symbol, day)]
    c = (get("/api/v1/candles", {"symbol": symbol, "interval": "1d", "count": 2}).get("result") or {})
    rows = c.get("candles") if isinstance(c, dict) else None
    if not rows:
        return None
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone(timedelta(hours=9 if symbol[:1].isdigit() else -5))).date().isoformat()
    first = rows[0]
    v = _num(rows[1].get("closePrice")) if str(first.get("timestamp", "")).startswith(today) and len(rows) > 1 else _num(first.get("closePrice"))
    _PREV[(symbol, day)] = v
    return v


def quotes(symbols: list[str]) -> dict:
    """{심볼: {px, chg, ref, at, src}} — 국내 6자리·미국 티커 함께."""
    r = get("/api/v1/prices", {"symbols": ",".join(symbols)}).get("result") or []
    out = {}
    for x in r:
        px = _num(x.get("lastPrice"))
        if not px:
            continue
        ref = prev_close(x["symbol"])
        out[x["symbol"]] = {"px": px, "ref": ref, "chg": round((px / ref - 1) * 100, 2) if ref else None,
                            "at": x.get("timestamp"), "src": "토스"}
    return out


def indicators() -> dict:
    r = get("/api/v1/market-indicators/prices", {"symbols": ",".join(INDICATORS.values())}).get("result") or []
    rev = {v: k for k, v in INDICATORS.items()}
    return {rev.get(x["symbol"], x["symbol"]): {"px": _num(x.get("lastPrice")), "at": x.get("timestamp"), "src": "토스"}
            for x in r if _num(x.get("lastPrice"))}


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    DOWN.unlink(missing_ok=True)
    print("지표", indicators() or _down() or "응답 없음")
    print("주가", quotes(["005930", "SOXL", "SOXS"]) or _down() or "응답 없음")


if __name__ == "__main__":
    main()
