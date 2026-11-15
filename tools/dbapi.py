"""DB증권 Open API(REST) — 조회 전용(국내 지수·주가, 미국 주가). 주문·계좌는 쓰지 않는다. 2026-11-16 운영자 요청.

- 키: DB_APP_KEY / DB_APP_SECRET (keystore). 출력·저장소에 남기지 않는다.
- 주소: https://openapi.dbsec.co.kr:8443 · 토큰 POST /oauth2/token (form: grant_type·appkey·appsecretkey·scope=oob — LS 와 같은 방식)
- 시세: POST + JSON {"In": {"InputCondMrktDivCode": 시장, "InputIscd1": 코드}} → {"Out": {Prpr·PrdyVrss·PrdyCtrt …}}
  · 국내 /api/v1/quote/kr-stock/inquiry/price  시장 UJ 주식(통합)·E ETF·U 업종/지수
  · 미국 /api/v1/quote/overseas-stock/inquiry/price  시장 FY NYSE·FN 나스닥·FA AMEX
  (공개 래퍼 pydbsec 소스 기준 — 키 발급 뒤 실제 응답으로 필드명 다시 확인)

  python tools/dbapi.py      # 연결 점검(키는 출력하지 않음)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://openapi.dbsec.co.kr:8443"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

TOKEN = keystore.state_dir() / "db_token.json"
DOWN = keystore.state_dir() / "db_down.json"
REST_S = 10 * 60
KR, US = "/api/v1/quote/kr-stock/inquiry/price", "/api/v1/quote/overseas-stock/inquiry/price"
ALLOW = (KR, US)                                           # 조회만(주문 /trading/… 은 막는다)
UA = {"User-Agent": "trendlab/1.0", "Accept": "application/json"}


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
        if t["exp"] - time.time() > 3600:
            return t["v"]
    except Exception:  # noqa: BLE001
        pass
    ks = keystore.pair("DB_APP_KEY", "DB_APP_SECRET")
    if not ks:
        _down("키 없음(DB_APP_KEY)")
        return None
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "appkey": ks[0], "appsecretkey": ks[1], "scope": "oob"}).encode()
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
    keystore.write_private(TOKEN, json.dumps({"v": j["access_token"], "exp": time.time() + int(j.get("expires_in") or 86400)}))
    return j["access_token"]


def call(path: str, market: str, code: str) -> dict:
    if path not in ALLOW:
        raise PermissionError("DB 모듈은 시세 조회만 쓴다")
    if _down():
        return {}
    tok = _token()
    if not tok:
        return {}
    req = urllib.request.Request(BASE + path, json.dumps({"In": {"InputCondMrktDivCode": market, "InputIscd1": code}}).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + tok, "cont_yn": "N", **UA}, method="POST")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=8).read()).get("Out") or {}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
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


def _q(o: dict) -> dict | None:
    px = _num(o.get("Prpr", o.get("NowPrc")))
    if not px:
        return None
    diff = _num(o.get("PrdyVrss", o.get("Cmpprevddprc")))
    rt = _num(o.get("PrdyCtrt", o.get("Cmpprevddrat")))
    if diff is not None and rt is not None and (diff < 0) != (rt < 0) and diff and rt:
        rt = abs(rt) * (1 if diff > 0 else -1)
    return {"px": px, "chg": rt, "ref": round(px - diff, 4) if diff is not None else None, "src": "DB"}


def stock_now(code: str, market: str = "UJ") -> dict | None:
    return _q(call(KR, market, code))


def index_now(code: str = "0001") -> dict | None:
    return _q(call(KR, "U", code))


def us_now(sym: str, market: str = "FA") -> dict | None:
    return _q(call(US, market, sym))


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    DOWN.unlink(missing_ok=True)
    print("삼성전자", stock_now("005930") or _down() or "응답 없음")
    print("SOXS", us_now("SOXS") or _down() or "응답 없음")


if __name__ == "__main__":
    main()
