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
import keystore  # noqa: E402

CACHE = keystore.state_dir() / "xbroker.json"
PRIO = ["키움", "한투", "NH", "KB", "LS", "토스", "DB", "네이버"]
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
                sg = str(o.get("prdy_vrss_sign") or "").strip()
                if sg not in ("1", "2", "3", "4", "5"):
                    rt = None                             # NH 현재가는 부호 칸이 비어 올 때가 있다 → 방향 모름(11/15 통합 +1.67% 오표시)
                elif rt is not None and sg in ("4", "5") and rt > 0:
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


def _ls() -> dict:
    import lsapi
    out = {}
    for k, (_, kind, kc, _, _) in ITEMS.items():
        x = lsapi.index_now(k) if kind == "idx" else lsapi.stock_now(kc)
        if x:
            out[("KRX", k)] = (x["px"], x.get("chg"))
    return out


def _toss() -> dict:
    import tossapi
    out = {}
    ind = tossapi.indicators()
    for k in ("KOSPI", "KOSDAQ"):
        if ind.get(k, {}).get("px"):
            out[("KRX", k)] = (ind[k]["px"], None)
    q = tossapi.quotes([ITEMS[k][2] for k in ("SMSN", "SKHX")])
    for k in ("SMSN", "SKHX"):
        x = q.get(ITEMS[k][2])
        if x:
            out[("KRX", k)] = (x["px"], x.get("chg"))      # 토스 REST 국내 = KRX(공식 설명). 다르면 점수판이 '어긋남'으로 센다
    return out


def _db() -> dict:
    import dbapi
    out = {}
    for k, code in (("KOSPI", "0001"), ("KOSDAQ", "1001"), ("KR200", "2001")):
        x = dbapi.index_now(code)
        if x:
            out[("KRX", k)] = (x["px"], x.get("chg"))
    for k in ("SMSN", "SKHX"):
        x = dbapi.stock_now(ITEMS[k][2])                  # UJ = 주식(통합, NXT 포함)
        if x:
            out[("통합", k)] = (x["px"], x.get("chg"))
    return out


FETCH = {"키움": _kiwoom, "한투": _kis, "NH": _nh, "KB": _kb, "LS": _ls, "토스": _toss, "DB": _db, "네이버": _naver}
KEYS = {"키움": "KIWOOM_APP_KEY", "한투": "KIS_APP_KEY", "NH": "NHPLUG_APP_KEY", "KB": "KB_APP_KEY", "LS": "LS_APP_KEY",
        "토스": "TOSS_CLIENT_ID", "DB": "DB_APP_KEY"}   # 키 없는 곳은 부르지 않는다(Oracle 의 KB 등)


def consensus(vals: dict[str, tuple], kind: str, prio: list[str] | None = None) -> dict:
    """vals {출처: (값, 등락%)} → {px, chg, agree:[..], off:[..]}. 지수는 0.02 이하, 주가는 같은 값만 일치.
    prio: 동률·대표값 순서(기본 PRIO, check 는 출처 점수판 순서를 넘긴다)."""
    PRIO = prio or globals()["PRIO"]  # noqa: N806
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
    import srcscore                                       # 11/16 출처 점수판: 응답 시간·일치율로 순서를 계속 고침
    got, fail, secs, rested = {}, [], {}, []

    def timed(s, f):
        t0 = time.time()
        r = f()
        secs[s] = time.time() - t0
        return r
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {}
        for s, f in FETCH.items():
            if s in KEYS and not keystore.has(KEYS[s]):
                continue
            if srcscore.skip("kr", s):
                rested.append(s)                          # 연속 실패 → 잠시 쉼(그 뒤 한 번 다시)
                continue
            futs[s] = ex.submit(timed, s, f)
        for s, fu in futs.items():
            try:
                r = fu.result(timeout=40)
            except Exception:  # noqa: BLE001
                r = {}
            if not r:
                fail.append(s)
                srcscore.record("kr", s, False)
            for key, v in r.items():
                got.setdefault(key, {})[s] = v
    prio = srcscore.rank("kr", PRIO)
    out: dict = {"KRX": {}, "통합": {}, "fail": fail, "rested": rested, "prio": prio, "at": int(time.time() * 1000)}
    agree: dict[str, list[bool]] = {}
    for (basis, k), vals in got.items():
        out[basis][k] = {"name": ITEMS[k][0], **consensus(vals, ITEMS[k][1], prio), "srcs": {s: v[0] for s, v in vals.items()}}
        if len(vals) >= 3:                                # 셋 이상일 때만 '맞다/틀리다'를 센다
            for s in vals:
                agree.setdefault(s, []).append(s in out[basis][k]["agree"])
    for s in futs:
        if s not in fail:
            a = agree.get(s)
            srcscore.record("kr", s, True, secs=secs.get(s), agree=(sum(a) / len(a) >= 0.5) if a else None)
    for k, u in out["통합"].items():                       # 통합 등락률을 모르면 KRX 전일 종가 기준으로 계산
        x = out["KRX"].get(k)
        if u.get("chg") is None and x and x.get("chg") is not None:
            prev = x["px"] / (1 + x["chg"] / 100)
            u["chg"] = round((u["px"] / prev - 1) * 100, 2)
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
    if r.get("rested"):
        print("쉬는 중(연속 실패):", ", ".join(r["rested"]))
    print("우선순위(점수판):", " > ".join(r.get("prio") or PRIO))


if __name__ == "__main__":
    main()
