"""한국투자증권(KIS) Open API — 조회 전용(뉴스 제목·업종지수). 주문·계좌 API는 쓰지 않는다(실주문은 운영자만).

- 키: 사용자 환경변수 KIS_APP_KEY / KIS_APP_SECRET. 화면·로그·저장소에 키를 남기지 않는다.
- 토큰: 저장소 밖 %LOCALAPPDATA%\\trendlab\\kis_token.json (24시간). 한투는 토큰 발급 횟수 제한·알림이 있어 만료 1시간 전까지 재사용.
- 실패(키 없음·서버 오류)면 10분 쉬고 빈 값 → 부르는 쪽은 건너뛴다.
- 뉴스(종합 시황/공시 제목, FHKST01011800): 한 번에 최근 40건, 언론사(dorg)·관련 종목코드 포함(2026-11-15 확인).

  python tools/kis.py      # 연결 점검: 코스피 지수 + 최근 뉴스 제목 5건(키는 출력하지 않음)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://openapi.koreainvestment.com:9443"
KST = timezone(timedelta(hours=9))
TOKDIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "trendlab"
TOKEN = TOKDIR / "kis_token.json"
DOWN = TOKDIR / "kis_down.json"
REST_S = 10 * 60
QUOTE_TR = ("FH",)                                         # 시세·뉴스 조회 TR(FH…)만 허용. 주문·계좌(TT…·VT…·CT…)는 막는다


def _keys() -> tuple[str, str] | None:
    k, s = os.environ.get("KIS_APP_KEY", "").strip(), os.environ.get("KIS_APP_SECRET", "").strip()
    if not (k and s) and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                k = k or str(winreg.QueryValueEx(h, "KIS_APP_KEY")[0]).strip()
                s = s or str(winreg.QueryValueEx(h, "KIS_APP_SECRET")[0]).strip()
        except OSError:
            pass
    return (k, s) if k and s else None


def _down(why: str | None = None) -> str | None:
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


def _token() -> str | None:
    try:
        t = json.loads(TOKEN.read_text(encoding="utf-8"))
        if t["exp"] - time.time() > 3600:
            return t["v"]
    except Exception:  # noqa: BLE001
        pass
    ks = _keys()
    if not ks:
        _down("키 없음(KIS_APP_KEY)")
        return None
    body = json.dumps({"grant_type": "client_credentials", "appkey": ks[0], "appsecret": ks[1]}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE + "/oauth2/tokenP", body, {"Content-Type": "application/json; charset=UTF-8"}),
                                   timeout=10)
        j = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        _down(f"토큰 실패: {type(e).__name__}")
        return None
    if not j.get("access_token"):
        _down(f"토큰 실패: {j.get('error_description', '')}")
        return None
    TOKDIR.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(json.dumps({"v": j["access_token"], "exp": time.time() + int(j.get("expires_in") or 86400)}), encoding="utf-8")
    return j["access_token"]


def get(path: str, tr_id: str, params: dict) -> dict:
    """조회 GET 한 번. 쉬는 중·실패면 {}."""
    if not tr_id.startswith(QUOTE_TR):
        raise PermissionError("한투 주문·계좌 API는 쓰지 않는다(조회 전용)")
    if _down():
        return {}
    tok = _token()
    ks = _keys()
    if not (tok and ks):
        return {}
    hd = {"content-type": "application/json; charset=utf-8", "authorization": "Bearer " + tok, "appkey": ks[0], "appsecret": ks[1],
          "tr_id": tr_id, "custtype": "P"}
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE + path + "?" + urllib.parse.urlencode(params), headers=hd), timeout=8)
        j = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            TOKEN.unlink(missing_ok=True)
        _down(f"{tr_id} HTTP {e.code}")
        return {}
    except Exception as e:  # noqa: BLE001
        _down(f"{tr_id} 접속 실패: {type(e).__name__}")
        return {}
    if j.get("rt_cd") != "0":
        _down(f"{tr_id}: {j.get('msg1', '')}")
        return {}
    return j


def news_titles() -> list[dict]:
    """최근 뉴스 제목 40건 → [{ts(ms), src(언론사), text, codes[]}] 최신순. 1분 캐시(저장소 밖)."""
    cache = TOKDIR / "kis_news.json"
    try:
        c = json.loads(cache.read_text(encoding="utf-8"))
        if time.time() - c["at"] < 55:
            return c["items"]
    except Exception:  # noqa: BLE001
        pass
    j = get("/uapi/domestic-stock/v1/quotations/news-title", "FHKST01011800",
            {"FID_NEWS_OFER_ENTP_CODE": "", "FID_COND_MRKT_CLS_CODE": "", "FID_INPUT_ISCD": "", "FID_TITL_CNTT": "",
             "FID_INPUT_DATE_1": datetime.now(KST).strftime("%Y%m%d"), "FID_INPUT_HOUR_1": "", "FID_RANK_SORT_CLS_CODE": "",
             "FID_INPUT_SRNO": ""})          # 날짜를 비우면 '마지막 영업일' 기사만 온다(주말에 금요일 기사만 오던 문제, 11/15)
    out = []
    for x in j.get("output") or []:
        try:
            t = datetime.strptime(x["data_dt"] + x["data_tm"], "%Y%m%d%H%M%S").replace(tzinfo=KST)
        except Exception:  # noqa: BLE001
            continue
        title = " ".join(str(x.get("hts_pbnt_titl_cntt") or "").split())
        if title:
            out.append({"ts": int(t.timestamp() * 1000), "src": (x.get("dorg") or "").strip() or "한투 뉴스", "text": title,
                        "codes": [x[f"iscd{i}"] for i in range(1, 11) if (x.get(f"iscd{i}") or "").strip()]})
    if out:
        try:
            TOKDIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"at": time.time(), "items": out}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return out


def index_now(code: str = "0001") -> dict | None:
    """업종지수 현재가(FHPUP02100000). 0001 코스피 · 1001 코스닥 · 2001 코스피200."""
    j = get("/uapi/domestic-stock/v1/quotations/inquire-index-price", "FHPUP02100000", {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": code})
    o = j.get("output") or {}
    try:
        return {"px": float(o["bstp_nmix_prpr"]), "chg": float(o["bstp_nmix_prdy_ctrt"])}
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    DOWN.unlink(missing_ok=True)
    print("키:", "있음" if _keys() else "없음(KIS_APP_KEY·KIS_APP_SECRET)")
    i = index_now()
    print("코스피:", f"{i['px']:,.2f} ({i['chg']:+.2f}%)" if i else f"실패 — {_down() or '알 수 없음'}")
    for n in news_titles()[:5]:
        print(f"  {datetime.fromtimestamp(n['ts'] / 1000, KST):%m/%d %H:%M} {n['src']} | {n['text'][:60]}")


if __name__ == "__main__":
    main()
