"""LS증권 OPEN API(REST) — 조회 전용(국내 지수·주가). 주문·계좌 TR은 쓰지 않는다(실주문은 운영자만). 2026-11-15 운영자 요청.

- 키: LS_APP_KEY / LS_APP_SECRET (keystore: 환경변수 → ~/.config/trendlab/keys.env → Windows 레지스트리). 출력·저장소에 남기지 않는다.
- 주소: https://openapi.ls-sec.co.kr:8080 · 토큰 POST /oauth2/token (form: grant_type·appkey·appsecretkey·scope=oob, 24시간)
- TR 호출: 모든 TR 이 POST, 기능은 헤더 tr_cd 로 고른다. 바디는 {"<TR>InBlock": {...}}, 응답은 "<TR>OutBlock".
  · t1102 주식 현재가  /stock/market-data   shcode
  · t1511 업종 현재가  /indtp/market-data   upcode (001 코스피 · 301 코스닥 · 101 코스피200)
- 허용 TR 은 ALLOW 에 적힌 시세 조회뿐. 실패(키 없음·접속 실패)면 10분 쉬고 빈 값 → 부르는 쪽은 건너뛴다.
- 출력 필드명은 키 발급 뒤 실제 응답으로 다시 확인할 것(문서 기준 추정: price·sign·change·diff / pricejisu·change·diffjisu·jniljisu).

  python tools/lsapi.py      # 연결 점검: 코스피·삼성전자(키는 출력하지 않음)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://openapi.ls-sec.co.kr:8080"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

TOKDIR = keystore.state_dir()
TOKEN = TOKDIR / "ls_token.json"
DOWN = TOKDIR / "ls_down.json"
REST_S = 10 * 60
ALLOW = {"t1102": "/stock/market-data", "t1511": "/indtp/market-data"}   # 시세 조회만. 주문(CSPAT…)·계좌(CSPAQ…)는 막는다
UPCODE = {"KOSPI": "001", "KOSDAQ": "301", "KR200": "101"}
UA = {"User-Agent": "trendlab/1.0", "Accept": "application/json"}


def _keys() -> tuple[str, str] | None:
    return keystore.pair("LS_APP_KEY", "LS_APP_SECRET")


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
    ks = _keys()
    if not ks:
        _down("키 없음(LS_APP_KEY)")
        return None
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "appkey": ks[0], "appsecretkey": ks[1], "scope": "oob"}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE + "/oauth2/token", body,
                                   {"Content-Type": "application/x-www-form-urlencoded", **UA}), timeout=10)
        j = json.loads(r.read())
    except urllib.error.HTTPError as e:
        txt = " ".join(e.read().decode("utf-8", "replace").split())[:100]
        _down(f"토큰 실패: HTTP {e.code} {txt}")
        return None
    except Exception as e:  # noqa: BLE001
        _down(f"토큰 실패: {type(e).__name__}")
        return None
    if not j.get("access_token"):
        _down(f"토큰 실패: {j.get('error_description') or j.get('rsp_msg', '')}")
        return None
    keystore.write_private(TOKEN, json.dumps({"v": j["access_token"], "exp": time.time() + int(j.get("expires_in") or 86400)}))
    return j["access_token"]


def call(tr: str, inblock: dict) -> dict:
    """시세 TR 하나 호출 → OutBlock(dict). 실패면 {}."""
    if tr not in ALLOW:
        raise PermissionError("LS 모듈은 시세 조회 TR 만 쓴다")
    if _down():
        return {}
    tok = _token()
    if not tok:
        return {}
    req = urllib.request.Request(BASE + ALLOW[tr], json.dumps({f"{tr}InBlock": inblock}).encode(), {
        "Content-Type": "application/json; charset=UTF-8", "authorization": f"Bearer {tok}",
        "tr_cd": tr, "tr_cont": "N", "tr_cont_key": "", **UA}, method="POST")
    try:
        j = json.loads(urllib.request.urlopen(req, timeout=8).read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            TOKEN.unlink(missing_ok=True)
        return {}                                          # 요청 하나 실패는 쉬지 않는다(한투와 같은 원칙)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        _down(f"접속 실패: {type(e).__name__}")
        return {}
    except ValueError:
        return {}
    return j.get(f"{tr}OutBlock") or {}


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _signed(chg, sign) -> float | None:
    """LS 부호 코드: 1 상한·2 상승·3 보합·4 하한·5 하락 → 4·5 는 음수."""
    x = _num(chg)
    if x is None:
        return None
    return -abs(x) if str(sign).strip() in ("4", "5") else abs(x) if str(sign).strip() in ("1", "2") else x


def index_now(name: str = "KOSPI") -> dict | None:
    o = call("t1511", {"upcode": UPCODE.get(name, name)})
    px = _num(o.get("pricejisu"))
    if not px:
        return None
    rt = _signed(o.get("diffjisu"), o.get("sign"))
    prev = _num(o.get("jniljisu"))
    return {"px": px, "chg": rt, "prev": prev, "src": "LS"}


def stock_now(code: str) -> dict | None:
    o = call("t1102", {"shcode": code})
    px = _num(o.get("price"))
    if not px:
        return None
    return {"px": px, "chg": _signed(o.get("diff"), o.get("sign")), "name": o.get("hname", ""), "src": "LS"}


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    DOWN.unlink(missing_ok=True)
    x = index_now("KOSPI")
    print("코스피", x or _down() or "응답 없음")
    s = stock_now("005930")
    print("삼성전자", s or _down() or "응답 없음")


if __name__ == "__main__":
    main()
