"""📊 장중 수급(한투 Open API, 조회 전용) — 운영자 11/16: 08~09시는 종목별 프로그램으로 외국인 흐름을 가늠하고,
09:20쯤 외국인·09:50쯤 기관 장중 추정(가집계)이 나오면 바로 TRL 수급에 반영한다.

- 프로그램(종목별): FHPPG04650101 program-trade-by-stock, 시장 'UN'(통합 = KRX + 넥스트레이드 08:00 프리마켓 포함)
  → 오늘 누적 순매수 금액(원)·수량·시각. 08:00~15:40 자주 보는 종목은 2분, 나머지는 10분마다(장 밖은 30분).
- 외국인·기관 장중 추정(종목별): HHPTJ04160200 investor-trend-estimate → 가장 최근 차수의 추정 순매수 수량.
  거래소·증권사 가집계는 대략 외국인 09:20~09:30, 기관 09:50~10:00부터 나오고 장중 몇 차례 갱신된다. 09:15~15:40 2분 반마다.
  금액 = 추정 수량 × 현재가(추정치). 장 마감 뒤 확정치는 네이버 investor-trend(flows.py)가 맡는다.
- 사실 집계이며 매수·매도 권유가 아니다. 키·토큰은 출력하지 않는다(kis.py 가 조회 TR 만 허용).
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
CACHE = keystore.state_dir() / "kisflow_cache.json"


def _n(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return 0.0


# ── 순수 함수(tests/test_kisflow.py) ──
def _last(d: dict) -> dict | None:
    rows = (d or {}).get("output") or []
    return rows[0] if rows else None                      # 첫 행이 가장 최근 체결(오늘 누적)


def parse_prog(krx: dict, nxt: dict, today: str) -> dict | None:
    """KRX(J)·넥스트레이드(NX) 응답 → 오늘 누적 {amt = 합계, krx, nxt(08시 프리마켓 포함), q, hm}. 통합(UN) = J + NX 와 같다(11/16 실측)."""
    a, b = _last(krx), _last(nxt)
    if not a and not b:
        return None
    ka = _n((a or {}).get("whol_smtn_ntby_tr_pbmn")) if a else None
    na = _n((b or {}).get("whol_smtn_ntby_tr_pbmn")) if b else None
    hh = max(str((a or {}).get("bsop_hour") or ""), str((b or {}).get("bsop_hour") or ""))
    return {"day": today, "amt": (ka or 0) + (na or 0), "krx": ka, "nxt": na,
            "q": _n((a or {}).get("whol_smtn_ntby_qty")) + _n((b or {}).get("whol_smtn_ntby_qty")),
            "hm": f"{hh[:2]}:{hh[2:4]}" if len(hh) >= 4 else "", "src": "한투"}


ROUND = {"1": "1차", "2": "2차", "3": "3차", "4": "4차", "5": "5차"}


def parse_est(d: dict, today: str) -> dict | None:
    """investor-trend-estimate 응답 → 가장 최근 차수 {frgn_q, org_q, round}. 값이 모두 0인 차수(아직 미집계)는 건너뛴다."""
    rows = d.get("output2") or d.get("output") or []
    if isinstance(rows, dict):
        rows = [rows]
    best = None
    for r in rows:
        f, o = _n(r.get("frgn_fake_ntby_qty")), _n(r.get("orgn_fake_ntby_qty"))
        if not f and not o:
            continue
        gb = str(r.get("bsop_hour_gb") or "")
        if best is None or gb > best["gb"]:
            best = {"gb": gb, "frgn_q": f, "org_q": o, "sum_q": _n(r.get("sum_fake_ntby_qty"))}
    if not best:
        return None
    return {"day": today, "round": ROUND.get(best["gb"], best["gb"]), **best}


def merge(r: dict, kp: dict, ke: dict) -> None:
    """flows·s7 행에 붙인다: prog = 한투 오늘(통합) 값(5일 합계는 KB 값이 있으면 유지), est = 장중 추정 금액(수량 × 현재가)."""
    p = kp.get(r.get("code"))
    if p:
        r["prog"] = {**p, "amt5": (r.get("prog") or {}).get("amt5")}
    e = ke.get(r.get("code"))
    if e and r.get("px"):
        # 0 은 '아직 집계 전'(기관은 09:50쯤부터) — 0억으로 보이지 않게 None
        r["est"] = {"round": e.get("round"), "frgn": e["frgn_q"] * r["px"] if e.get("frgn_q") else None,
                    "org": e["org_q"] * r["px"] if e.get("org_q") else None}


# ── 수집 ──
def _load() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"prog": {}, "est": {}}


def _save(c: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def fetch(codes: list[str], hot: set[str] | None = None, now: datetime | None = None) -> tuple[dict, dict]:
    """종목코드 → (프로그램 {day, amt, q, t}, 장중 추정 {day, round, frgn_q, org_q}). 오늘 값만 돌려준다."""
    from kis import get
    now = now or datetime.now(KST)
    today, t, hm = now.strftime("%Y-%m-%d"), time.time(), now.hour * 100 + now.minute
    wk = now.weekday() < 5
    hot = hot or set()
    c = _load()
    prog_on = wk and 800 <= hm < 1540
    est_on = wk and 915 <= hm < 1540

    def age(kind, x):
        e = c[kind].get(x) or {}
        return t - e.get("t", 0) if e.get("day") == today else 1e9

    need_p = [x for x in codes if age("prog", x) > ((120 if x in hot else 600) if prog_on else 1800)] if (prog_on or wk) else []
    need_e = [x for x in codes if age("est", x) > 150] if est_on else []      # 차수 발표 뒤 늦어도 2~3분 안에 반영

    def one_p(x):
        q = lambda m: get("/uapi/domestic-stock/v1/quotations/program-trade-by-stock", "FHPPG04650101",   # noqa: E731
                          {"FID_COND_MRKT_DIV_CODE": m, "FID_INPUT_ISCD": x})
        def safe(m):
            try:
                return q(m)
            except Exception:  # noqa: BLE001
                return None
        nx = safe("NX")                                   # 넥스트레이드 미상장 종목은 정상 응답(rt_cd 0)에 빈 output
        kx = safe("J") if hm >= 900 else {"rt_cd": "0"}   # 정규장 전에는 넥스트레이드 프리마켓만
        bad = lambda d: not d or d.get("rt_cd") != "0"    # noqa: E731  kis.get 은 실패(한도 초과 등)면 {} 를 돌려준다
        if bad(nx) and bad(kx):
            return x, False
        p = parse_prog({} if bad(kx) else kx, {} if bad(nx) else nx, today)
        old = c["prog"].get(x) or {}
        if p and old.get("day") == today:                 # 11/16 09:54: 한쪽 호출만 실패하면 합계가 틀어짐 → 그쪽은 직전 값 유지
            for side, d in (("krx", kx), ("nxt", nx)):
                if bad(d) and old.get(side) is not None:
                    p[side] = old[side]
            p["amt"] = (p.get("krx") or 0) + (p.get("nxt") or 0)
        return x, p

    def one_e(x):
        try:
            return x, parse_est(get("/uapi/domestic-stock/v1/quotations/investor-trend-estimate", "HHPTJ04160200",
                                    {"MKSC_SHRN_ISCD": x}), today)
        except Exception:  # noqa: BLE001
            return x, False

    with ThreadPoolExecutor(max_workers=3) as ex:                              # 한투 초당 한도 여유(4 → 3)
        for x, v in ex.map(one_p, need_p):
            if v is not False:
                c["prog"][x] = {**(v or {}), "day": today, "t": t, "none": v is None}
        for x, v in ex.map(one_e, need_e):
            if v is not False:
                c["est"][x] = {**(v or {}), "day": today, "t": t, "none": v is None}
    if need_p or need_e:
        _save(c)
    pick = lambda kind: {x: {k: v for k, v in e.items() if k not in ("t", "none")}   # noqa: E731
                         for x, e in c[kind].items() if e.get("day") == today and not e.get("none")}
    return pick("prog"), pick("est")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cs = sys.argv[1:] or ["005930", "000660"]
    p, e = fetch(cs, set(cs))
    for x in cs:
        print(x, "프로그램", p.get(x), "| 추정", e.get(x))
