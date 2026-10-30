"""📊 종목별 프로그램 매매 — KB증권 Open API IVU10450_프로그램(일별, 오늘 행은 장중 누적). 읽기 전용 조회만.

- 키: Windows 사용자 환경변수 KB_APP_KEY / KB_APP_SECRET (없으면 조용히 건너뜀 → 화면은 '준비 중')
- 접속 토큰: 저장소 밖 %LOCALAPPDATA%\\trendlab\\kb_token.json (공개 저장소에 올라가지 않음, 만료 전 재사용)
- 금액: nt_b_amt(천 원) × 1000 = 원. 오늘 순매수 + 최근 5거래일 합계
- 갱신: 장중(09:00~15:40) '자주 보는 종목'은 3분마다, 나머지·장 밖은 30분마다 (tools/kbprog_cache.json, git 제외)
- 사실 집계이며 매수·매도 권유가 아니다. 키·토큰 값은 어디에도 출력하지 않는다.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tools" / "kbprog_cache.json"
TOKDIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "trendlab"
TOKEN = TOKDIR / "kb_token.json"
BASE = "https://developer.kbsec.com:32484"
KST = timezone(timedelta(hours=9))
HDR = {"ipAddr": "127.0.0.1", "macAddr": "00:00:00:00:00:00"}


def _keys() -> tuple[str, str] | None:
    k, s = os.environ.get("KB_APP_KEY", "").strip(), os.environ.get("KB_APP_SECRET", "").strip()
    if not (k and s) and os.name == "nt":                     # 예약 작업 등 새 환경변수를 못 받은 프로세스: 레지스트리(사용자)에서 직접
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                k = k or str(winreg.QueryValueEx(h, "KB_APP_KEY")[0]).strip()
                s = s or str(winreg.QueryValueEx(h, "KB_APP_SECRET")[0]).strip()
        except OSError:
            pass
    return (k, s) if k and s else None


def _post(url: str, body: dict, token: str | None = None) -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        h["Authorization"] = f"bearer {token}"
    req = urllib.request.Request(url, data=json.dumps({"dataHeader": HDR, "dataBody": body}).encode(), headers=h, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def _token() -> str | None:
    try:
        t = json.loads(TOKEN.read_text(encoding="utf-8"))
        if t.get("exp", 0) - time.time() > 600:
            return t["v"]
    except Exception:  # noqa: BLE001
        pass
    ks = _keys()
    if not ks:
        return None
    r = _post(f"{BASE}/oauth2/token", {"grantType": "client_credentials", "appKey": ks[0], "appSecret": ks[1]})
    h, b = r.get("dataHeader") or {}, r.get("dataBody") or {}
    if h.get("resultCode") != "200" or not b.get("access_token"):
        raise RuntimeError("KB 인증 거부(신청 상태·키 확인)")
    TOKDIR.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(json.dumps({"v": b["access_token"], "exp": time.time() + float(b.get("expires_in") or 3600)}), encoding="utf-8")
    return b["access_token"]


def parse(rows: list[dict]) -> dict | None:
    """IVU10450 일별 행(최신순) → 오늘(첫 행) 순매수 금액·수량, 5거래일 합계(원). 순수 함수(tests/test_kbprog.py)."""
    days = []
    for r in rows[:5]:
        try:
            days.append({"day": f"{r['dt'][:4]}-{r['dt'][4:6]}-{r['dt'][6:8]}", "amt": float(r["nt_b_amt"]) * 1000, "q": float(r.get("nt_b_q") or 0)})
        except (KeyError, ValueError, TypeError):
            continue
    if not days:
        return None
    return {"day": days[0]["day"], "amt": days[0]["amt"], "q": days[0]["q"], "amt5": sum(d["amt"] for d in days), "n5": len(days)}


def _one(code: str, token: str) -> dict | None:
    r = _post(f"{BASE}/api/v1/ivu10450", {"is_cd": code, "excg_clsf": "0", "prd_clsf": "2"}, token)
    if (r.get("dataHeader") or {}).get("resultCode") != "200":
        return None
    out = (r.get("dataBody") or {}).get("out") or []
    return parse(out if isinstance(out, list) else [out])


def fetch_quotes(codes: list[str]) -> dict[str, float]:
    """KB IVU10140 국내주식 현재가. 인증정보·원응답은 기록하지 않는다."""
    now = time.time()
    try:
        cache = json.loads((TOKDIR / "kbquote_cache.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cache = {}
    need = [code for code in codes if now - (cache.get(code) or {}).get("t", 0) > 45]
    if need:
        try:
            tok = _token()
        except Exception:  # noqa: BLE001
            tok = None
        if tok:
            def one(code: str):
                try:
                    r = _post(f"{BASE}/api/v1/ivu10140", {"shrt_cd": code, "excg_clsf": "0"}, tok)
                    if (r.get("dataHeader") or {}).get("resultCode") != "200":
                        return code, None
                    px = float(str((r.get("dataBody") or {}).get("now_prc") or "0").replace(",", "").replace("+", ""))
                    return code, px if px > 0 else None
                except Exception:  # noqa: BLE001
                    return code, None
            with ThreadPoolExecutor(max_workers=4) as ex:
                for code, px in ex.map(one, need):
                    if px:
                        cache[code] = {"t": now, "px": px}
            try:
                TOKDIR.mkdir(parents=True, exist_ok=True)
                (TOKDIR / "kbquote_cache.json").write_text(json.dumps(cache), encoding="utf-8")
            except OSError:
                pass
    return {code: float(cache[code]["px"]) for code in codes if cache.get(code) and cache[code].get("px")}


def fetch(codes: list[str], hot: set[str] | None = None) -> dict[str, dict]:
    """종목코드 → {day, amt, q, amt5}. 키가 없거나 실패하면 저장본(있으면)만 돌려준다."""
    try:
        c = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        c = {}
    now = datetime.now(KST)
    hh = now.hour * 100 + now.minute
    live = now.weekday() < 5 and 900 <= hh < 1540
    hot = hot or set()
    need = [x for x in codes if time.time() - (c.get(x) or {}).get("t", 0) > (170 if live and x in hot else 1800)]
    if need:
        try:
            tok = _token()
        except Exception:  # noqa: BLE001
            tok = None
        if tok:
            def one(x):
                try:
                    return x, _one(x, tok)
                except Exception:  # noqa: BLE001
                    return x, None
            with ThreadPoolExecutor(max_workers=4) as ex:
                for x, v in ex.map(one, need[:120]):
                    if v:
                        c[x] = {"t": time.time(), "v": v}
            try:
                CACHE.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
    return {x: c[x]["v"] for x in codes if c.get(x)}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for k, v in fetch(["005930", "000660", "402340"], {"005930"}).items():
        print(k, v["day"], f"오늘 {v['amt'] / 1e8:+,.0f}억", f"5일 {v['amt5'] / 1e8:+,.0f}억")
