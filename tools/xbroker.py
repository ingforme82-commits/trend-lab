"""증권사 교차 확인 — 같은 숫자를 키움·한투·NH·KB(+네이버)에서 받아 다수가 일치하는 값을 채택한다. 2026-11-15 운영자 요청.

기준을 섞지 않는다(11/15 확인: 삼성전자 거래소 종가 209,000 vs NXT 포함 통합 208,500 — 둘 다 맞는 값, 기준이 다름).
- 'KRX'(거래소 정규장): 코스피·코스닥·코스피200 지수, 삼성전자·SK하이닉스 — 키움 · 한투(J) · NH(KRX) · 네이버 · NH 선물의 기초자산(코스피200)
- '통합'(NXT 포함): 삼성전자·SK하이닉스 — 키움(_AL) · NH(UNT) · KB
채택: 허용 오차 안에서 가장 많은 출처가 맞는 값(동률이면 우선순위 키움 > 한투 > NH > KB > 네이버). 어긋난 출처는 'off'.
결과는 저장소 밖에 캐시(장중 60초, 장 밖 30분). 조회만 한다.

  python tools/xbroker.py     # 지금 교차 확인 표
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "trendlab" / "xbroker.json"
PRIO = ["키움", "한투", "NH", "KB", "네이버"]
ITEMS = {  # key: (이름, 종류, 키움 코드, 한투 코드, 네이버 심볼)
    "KOSPI": ("코스피", "idx", "001", "0001", "^KS11"),
    "KOSDAQ": ("코스닥", "idx", "101", "1001", "^KQ11"),
    "KR200": ("코스피200", "idx", "201", "", "^KS200"),        # 한투 업종코드 2001 은 서버 오류(11/15) → 한투 제외
    "SMSN": ("삼성전자", "stk", "005930", "005930", "005930.KS"),
    "SKHX": ("SK하이닉스", "stk", "000660", "000660", "000660.KS"),
}


def _f(v):
    try:
        return float(str(v).replace(",", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def _kiwoom() -> dict:
    import kiwoom
    out = {}
    for k, (_, kind, kc, _, _) in ITEMS.items():
        x = kiwoom.index_now(kc) if kind == "idx" else kiwoom.stock_now(kc)
        if x:
            out[("KRX", k)] = (x["px"], x.get("chg"))
        if kind == "stk":
            j, _ = kiwoom.call("ka10001", "/api/dostk/stkinfo", {"stk_cd": kc + "_AL"})
            px = kiwoom._num(j.get("cur_prc"))
            if px:
                out[("통합", k)] = (px, _f(j.get("flu_rt")))
    return out


def _kis() -> dict:
    import kis
    out = {}
    for k, (_, kind, _, hc, _) in ITEMS.items():
        if kind == "idx":
            x = kis.index_now(hc) if hc else None
            if x:
                out[("KRX", k)] = (x["px"], x["chg"])
        else:
            o = kis.get("/uapi/domestic-stock/v1/quotations/inquire-price", "FHKST01010100",
                        {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": hc}).get("output") or {}
            if _f(o.get("stck_prpr")):
                out[("KRX", k)] = (_f(o["stck_prpr"]), _f(o.get("prdy_ctrt")))
    return out


def _nh() -> dict:
    import nhfut
    out = {}
    for k, (_, kind, kc, _, _) in ITEMS.items():
        if kind != "stk":
            continue
        for mk, basis in (("KRX", "KRX"), ("UNT", "통합")):
            try:
                o = nhfut._first(nhfut._call("/krstock/quote/v1/currentPrice", {"market_cd": mk, "iem_cd": kc}), "Output_0")
            except Exception:  # noqa: BLE001
                continue
            px, rt = _f(o.get("stck_prpr")), _f(o.get("prdy_ctrt"))
            if px:
                if rt is not None and str(o.get("prdy_vrss_sign")) in ("4", "5") and rt > 0:
                    rt = -rt
                out[(basis, k)] = (px, rt)
    try:                                                  # 코스피200 지수 = 선물의 기초자산 현재가
        o = nhfut._first(nhfut._call("/krfuture/quote/v1/day", {"iem_cd": nhfut.k200_code()}), "Output_1")
        if _f(o.get("unas_prpr")):
            out[("KRX", "KR200")] = (_f(o["unas_prpr"]), None)
    except Exception:  # noqa: BLE001
        pass
    return out


def _kb() -> dict:
    import kbprog
    q = kbprog.fetch_quotes([ITEMS["SMSN"][2], ITEMS["SKHX"][2]])
    return {("통합", k): (q[ITEMS[k][2]], None) for k in ("SMSN", "SKHX") if q.get(ITEMS[k][2])}


def _naver() -> dict:
    from krx import quotes
    q = quotes([v[4] for v in ITEMS.values()])
    return {("KRX", k): (q[v[4]]["px"], q[v[4]].get("chg")) for k, v in ITEMS.items() if v[4] in q and q[v[4]].get("px")}


FETCH = {"키움": _kiwoom, "한투": _kis, "NH": _nh, "KB": _kb, "네이버": _naver}


def consensus(vals: dict[str, tuple], kind: str) -> dict:
    """vals {출처: (값, 등락%)} → {px, chg, agree:[..], off:[..]}. 지수는 0.02 이하, 주가는 같은 값만 일치."""
    tol = 0.02 if kind == "idx" else 0.5
    best = []
    for s in sorted(vals, key=lambda x: PRIO.index(x)):
        grp = [t for t in vals if abs(vals[t][0] - vals[s][0]) <= tol]
        if len(grp) > len(best):
            best = grp
    lead = sorted(best, key=lambda x: PRIO.index(x))[0]
    chg = next((vals[s][1] for s in sorted(best, key=lambda x: PRIO.index(x)) if vals[s][1] is not None), None)
    return {"px": vals[lead][0], "chg": chg, "agree": sorted(best, key=lambda x: PRIO.index(x)),
            "off": {s: vals[s][0] for s in vals if s not in best}}


def check(force: bool = False) -> dict:
    """{'KRX': {item: {...}}, '통합': {...}, 'fail': [출처], 'at': ms}"""
    try:
        import kiwoom
        live = kiwoom.in_session()
    except Exception:  # noqa: BLE001
        live = False
    try:
        c = json.loads(CACHE.read_text(encoding="utf-8"))
        if not force and time.time() - c["at"] / 1000 < (60 if live else 1800):
            return c
    except Exception:  # noqa: BLE001
        pass
    got, fail = {}, []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {s: ex.submit(f) for s, f in FETCH.items()}
        for s, fu in futs.items():
            try:
                r = fu.result(timeout=40)
            except Exception:  # noqa: BLE001
                r = {}
            if not r:
                fail.append(s)
            for key, v in r.items():
                got.setdefault(key, {})[s] = v
    out: dict = {"KRX": {}, "통합": {}, "fail": fail, "at": int(time.time() * 1000)}
    for (basis, k), vals in got.items():
        out[basis][k] = {"name": ITEMS[k][0], **consensus(vals, ITEMS[k][1]), "srcs": {s: v[0] for s, v in vals.items()}}
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    r = check(force=True)
    for basis in ("KRX", "통합"):
        print(f"[{basis} 기준]")
        for k, v in r[basis].items():
            off = " · 어긋남 " + ", ".join(f"{s} {p:,.2f}" for s, p in v["off"].items()) if v["off"] else ""
            print(f"  {v['name']:<8} 채택 {v['px']:,.2f} ({v['chg']:+.2f}%) · 일치 {len(v['agree'])}/{len(v['srcs'])} {'·'.join(v['agree'])}{off}"
                  if v["chg"] is not None else f"  {v['name']} 채택 {v['px']:,.2f} · 일치 {'·'.join(v['agree'])}{off}")
    if r["fail"]:
        print("응답 없음:", ", ".join(r["fail"]))


if __name__ == "__main__":
    main()
