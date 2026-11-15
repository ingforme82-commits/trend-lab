"""키움 REST API — 조회 전용(시세·업종지수). 주문 기능은 만들지 않는다(실주문은 운영자만).

- 키: 사용자 환경변수 KIWOOM_APP_KEY / KIWOOM_SECRET_KEY(실전용). 화면·로그·저장소에 키를 남기지 않는다.
- 토큰: 저장소 밖 %LOCALAPPDATA%\\trendlab\\kiwoom_token.json (약 24시간, 만료 10분 전 새로 받음)
- 키움은 등록한 IP에서만 열린다(최대 10개). 키가 없거나 IP가 등록 안 된 PC에서는 30분 쉬고 빈 값 → 호출하는 쪽은 그냥 건너뛴다.
- 키움 REST API에는 뉴스·시황 API가 없다(2026-11-15 공식 명세 306개 확인). 뉴스는 기존 출처, 지수는 여기서.

  python tools/kiwoom.py          # 연결 점검: 코스피·코스닥 현재가와 1분봉 개수(키는 출력하지 않음)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://api.kiwoom.com"
KST = timezone(timedelta(hours=9))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

TOKDIR = keystore.state_dir()                  # Windows %LOCALAPPDATA%/trendlab · 리눅스 ~/.local/state/trendlab
TOKEN = TOKDIR / "kiwoom_token.json"
DOWN = TOKDIR / "kiwoom_down.json"            # 실패하면 30분 쉼(IP 미등록 PC·서버 장애 때 속보 갱신이 느려지지 않게)
INDS = {"KOSPI": "001", "KOSDAQ": "101", "K200": "201"}   # 업종코드: 코스피 종합·코스닥 종합·코스피200
NAME = {"001": "코스피", "101": "코스닥", "201": "코스피200"}
REST_S = 30 * 60


def _keys() -> tuple[str, str] | None:
    """키: 환경변수 → 비공개 키 파일 → Windows 레지스트리(keystore, PC·Oracle 공통)."""
    return keystore.pair("KIWOOM_APP_KEY", "KIWOOM_SECRET_KEY")


def _down(why: str | None = None) -> str | None:
    """why 를 주면 쉼 기록, 안 주면 쉬는 중인지(이유) 돌려준다."""
    if why:
        try:
            TOKDIR.mkdir(parents=True, exist_ok=True)
            DOWN.write_text(json.dumps({"at": time.time(), "why": why[:120]}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return why
    try:
        d = json.loads(DOWN.read_text(encoding="utf-8"))
        return d["why"] if time.time() - d["at"] < REST_S else None
    except Exception:  # noqa: BLE001
        return None


def _http(path: str, body: dict, headers: dict) -> tuple[dict, dict]:
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json",
                                  "User-Agent": "trendlab/1.0", **headers}, method="POST")   # 기본 Python-urllib 이름은 키움 방화벽이 400(HTML)으로 막음(11/15 Oracle)
    try:
        r = urllib.request.urlopen(req, timeout=8)
        return json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        try:
            return json.loads(raw), {}
        except ValueError:                                 # 원문 앞부분을 남겨 원인(IP 미등록 등)을 볼 수 있게
            txt = " ".join(raw.decode("utf-8", "replace").split())[:120]
            return {"return_code": e.code, "return_msg": f"HTTP {e.code} {txt}".strip()}, {}


def _token() -> str | None:
    try:
        t = json.loads(TOKEN.read_text(encoding="utf-8"))
        if t["exp"] - time.time() > 600:
            return t["v"]
    except Exception:  # noqa: BLE001
        pass
    ks = _keys()
    if not ks:
        _down("키 없음(KIWOOM_APP_KEY)")
        return None
    j, _ = _http("/oauth2/token", {"grant_type": "client_credentials", "appkey": ks[0], "secretkey": ks[1]}, {})
    if j.get("return_code") != 0 or not j.get("token"):
        _down(f"토큰 실패: {j.get('return_msg', '')}")      # IP 미등록이면 여기서 막힌다
        return None
    try:
        exp = datetime.strptime(j["expires_dt"], "%Y%m%d%H%M%S").replace(tzinfo=KST).timestamp()
    except Exception:  # noqa: BLE001
        exp = time.time() + 6 * 3600
    TOKDIR.mkdir(parents=True, exist_ok=True)
    keystore.write_private(TOKEN, json.dumps({"v": j["token"], "exp": exp}))
    return j["token"]


def call(api_id: str, path: str, body: dict, cont: str = "") -> tuple[dict, str]:
    """조회 TR 한 번. 반환 (응답, 다음 페이지 키 또는 ''). 쉬는 중·실패면 ({}, '')."""
    if api_id.startswith("kt"):                           # kt = 주문 계열 — 이 모듈에서는 막는다
        raise PermissionError("키움 주문 API는 쓰지 않는다(조회 전용)")
    if _down():
        return {}, ""
    tok = _token()
    if not tok:
        return {}, ""
    h = {"authorization": "Bearer " + tok, "api-id": api_id}
    if cont:
        h.update({"cont-yn": "Y", "next-key": cont})
    try:
        j, hd = _http(path, body, h)
    except Exception as e:  # noqa: BLE001
        _down(f"{api_id} 접속 실패: {e}")
        return {}, ""
    if j.get("return_code") != 0:
        if "토큰" in str(j.get("return_msg", "")):
            TOKEN.unlink(missing_ok=True)                 # 토큰 만료·폐기 → 다음 호출에 새로
        _down(f"{api_id}: {j.get('return_msg', '')}")
        return {}, ""
    return j, (hd.get("next-key", "") if hd.get("cont-yn") == "Y" else "")


def _num(v) -> float | None:
    """키움 값: '+529053'·'-5290.53' 처럼 앞 부호는 '전일 대비 방향'이라 떼고 읽는다."""
    s = str(v or "").strip().lstrip("+-")
    try:
        return float(s)
    except ValueError:
        return None


def index_now(code: str = "001") -> dict | None:
    """업종현재가(ka20001) → {name, px, chg(%), up, down, flat}."""
    j, _ = call("ka20001", "/api/dostk/sect", {"mrkt_tp": "1" if code.startswith("1") else "0", "inds_cd": code})
    px = _num(j.get("cur_prc"))
    if px is None:
        return None
    rt = str(j.get("flu_rt") or "0")
    return {"name": NAME.get(code, code), "px": px, "chg": float(rt.replace("+", "")) if rt.lstrip("+-").replace(".", "").isdigit() else None,
            "up": int(_num(j.get("rising")) or 0) + int(_num(j.get("upl")) or 0),
            "down": int(_num(j.get("fall")) or 0) + int(_num(j.get("lst")) or 0), "flat": int(_num(j.get("stdns")) or 0)}


def stock_now(code: str) -> dict | None:
    """주식기본정보(ka10001) → {name, px, chg(%)}."""
    j, _ = call("ka10001", "/api/dostk/stkinfo", {"stk_cd": code})
    px = _num(j.get("cur_prc"))
    if not px:
        return None
    rt = str(j.get("flu_rt") or "").replace("+", "")
    try:
        chg = float(rt)
    except ValueError:
        chg = None
    return {"name": j.get("stk_nm", code), "px": px, "chg": chg}


def kr_quotes() -> dict:
    """사이트 '한국 증시' 칸 형식(market_extra.kr_now 와 같음): KOSPI·KOSDAQ·KR200·SMSN·SKHX → {px, prev, chg, at, open}.
    장중이면 at=지금, 장 밖이면 마지막 1분봉 시각(=마지막 거래소 체결). 실패한 항목은 빠진다."""
    out = {}
    live = in_session()
    last = index_minutes("001", hours=24 * 5)
    at = int(time.time() * 1000) if live else (last[-1][0] + 60_000 if last else None)
    for key, code in (("KOSPI", "001"), ("KOSDAQ", "101"), ("KR200", "201")):
        x = index_now(code)
        if x and x.get("chg") is not None:
            out[key] = {"px": x["px"], "prev": round(x["px"] / (1 + x["chg"] / 100), 2), "chg": x["chg"], "at": at, "open": live,
                        "src": "키움"}
    for key, code in (("SMSN", "005930"), ("SKHX", "000660")):
        x = stock_now(code)
        if x and x.get("chg") is not None:
            out[key] = {"px": x["px"], "prev": round(x["px"] / (1 + x["chg"] / 100)), "chg": x["chg"], "at": at, "open": live,
                        "src": "키움"}
    return out


def in_session(now: datetime | None = None) -> bool:
    k = (now or datetime.now(KST)).astimezone(KST)
    m = k.hour * 60 + k.minute
    return k.weekday() < 5 and 8 * 60 + 59 <= m <= 15 * 60 + 40


def index_minutes(code: str = "001", hours: int = 24) -> list[tuple[int, float]]:
    """업종 1분봉(ka20005) → [(ms, 지수)] 오래된 것부터, 최근 hours 시간. 한 번에 900개(약 이틀 반).
    장중에는 50초, 장 밖에는 30분 동안 같은 값을 다시 쓴다(호출 줄이기, 캐시는 저장소 밖)."""
    cache = TOKDIR / f"kiwoom_min_{code}.json"
    try:
        c = json.loads(cache.read_text(encoding="utf-8"))
        if time.time() - c["at"] < (50 if in_session() else REST_S):
            rows = [tuple(r) for r in c["rows"]]
            cut = (time.time() - hours * 3600) * 1000
            return [r for r in rows if r[0] >= cut]
    except Exception:  # noqa: BLE001
        pass
    j, _ = call("ka20005", "/api/dostk/chart", {"inds_cd": code, "tic_scope": "1", "base_dt": datetime.now(KST).strftime("%Y%m%d")})
    rows = []
    for r in j.get("inds_min_pole_qry") or []:
        v = _num(r.get("cur_prc"))
        try:
            t = datetime.strptime(r["cntr_tm"], "%Y%m%d%H%M%S").replace(tzinfo=KST)
        except Exception:  # noqa: BLE001
            continue
        if v:
            rows.append((int(t.timestamp() * 1000) - 60_000, round(v / 100, 2)))   # 봉 끝 시각 → 시작 시각(하이퍼리퀴드와 같게)
    rows.sort()
    if rows:
        try:
            TOKDIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"at": time.time(), "rows": rows}), encoding="utf-8")
        except OSError:
            pass
    cut = (time.time() - hours * 3600) * 1000
    return [r for r in rows if r[0] >= cut]


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    DOWN.unlink(missing_ok=True)                          # 점검할 때는 쉼 기록을 지우고 바로 시도
    print("키:", "있음" if _keys() else "없음(KIWOOM_APP_KEY·KIWOOM_SECRET_KEY)")
    for code in ("001", "101"):
        n = index_now(code)
        if not n:
            print(NAME[code], "조회 실패 —", _down() or "알 수 없음", "(다른 PC면 openapi.kiwoom.com 에서 이 PC IP 등록)")
            return
        rows = index_minutes(code, hours=72)
        last = datetime.fromtimestamp(rows[-1][0] / 1000, KST).strftime("%m/%d %H:%M") if rows else "-"
        print(f"{n['name']} {n['px']:,.2f} ({n['chg']:+.2f}%) 상승 {n['up']}·하락 {n['down']} | 1분봉 {len(rows)}개, 마지막 {last}")


if __name__ == "__main__":
    main()
