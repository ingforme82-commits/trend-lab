"""📊 키움 장중 투자자 집계(조회 전용) — 운영자 11/17 "키움 장중 투자자 집계도 붙여줘".

한투 장중 추정(kisflow.py)과 나란히 두 번째 증권사 값으로 쓴다(교차 확인).
- ka10059 종목별투자자기관별(/api/dostk/stkinfo) — 오늘 날짜 행 = 장중 잠정(장 마감 뒤 확정치로 바뀜).
  금액 단위 백만 원(11/16 삼성전자 외국인 -621,003 = 약 -6,210억, 거래대금 3,225,951 = 약 3.2조와 맞음).
- 09:15~15:40 자주 보는 종목만 5분마다(나머지는 30분). 값이 0 이면 아직 집계 전으로 본다.
- 사실 집계이며 매수·매도 권유가 아니다. 키·토큰은 출력하지 않는다(kiwoom.py).
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

KST = timezone(timedelta(hours=9))
CACHE = keystore.state_dir() / "kwflow_cache.json"
UNIT = 1_000_000                                   # 응답 금액 단위(백만 원)


def _n(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return 0.0


def parse(rows: list[dict], ymd: str) -> dict | None:
    """ka10059 행들 → 오늘(ymd) {frgn, org, ind}(원). 오늘 행이 없거나 외국인·기관이 모두 0 이면 None."""
    r = next((x for x in rows or [] if str(x.get("dt")) == ymd), None)
    if not r:
        return None
    f, o, i = _n(r.get("frgnr_invsr")), _n(r.get("orgn")), _n(r.get("ind_invsr"))
    if not f and not o:
        return None
    return {"frgn": f * UNIT or None, "org": o * UNIT or None, "ind": i * UNIT, "src": "키움"}


def _load() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def fetch(codes: list[str], hot: set[str] | None = None, now: datetime | None = None) -> dict:
    """종목코드 → 오늘 키움 장중 집계 {frgn, org, ind, hm}. 장 밖·실패면 저장본 중 오늘 값만."""
    from kiwoom import call
    now = now or datetime.now(KST)
    ymd, hm, t = now.strftime("%Y%m%d"), now.hour * 100 + now.minute, time.time()
    hot = hot or set()
    c = _load()
    on = now.weekday() < 5 and 915 <= hm < 1540
    need = [x for x in codes if on and (c.get(x, {}).get("day") != ymd or t - c[x].get("t", 0) > (300 if x in hot else 1800))]

    def one(x):
        try:
            j, _ = call("ka10059", "/api/dostk/stkinfo", {"dt": ymd, "stk_cd": x, "amt_qty_tp": "1", "trde_tp": "0", "unit_tp": "1000"})
            if str(j.get("return_code")) != "0":
                return x, False
            return x, parse(j.get("stk_invsr_orgn") or [], ymd)
        except Exception:  # noqa: BLE001
            return x, False

    if need:
        with ThreadPoolExecutor(max_workers=3) as ex:
            for x, v in ex.map(one, need):
                if v is not False:
                    c[x] = {**(v or {}), "day": ymd, "t": t, "hm": now.strftime("%H:%M"), "none": v is None}
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return {x: {k: v for k, v in e.items() if k not in ("t", "none", "day")} for x, e in c.items()
            if e.get("day") == ymd and not e.get("none")}


def merge(r: dict, kw: dict) -> None:
    """flows·s7 행에 키움 값을 est_kw 로 붙인다(한투 est 와 나란히)."""
    v = kw.get(r.get("code"))
    if v:
        r["est_kw"] = {"frgn": v.get("frgn"), "org": v.get("org"), "hm": v.get("hm")}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cs = sys.argv[1:] or ["005930", "000660"]
    print(fetch(cs, set(cs)))
