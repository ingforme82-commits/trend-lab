"""종목 교차 확인(통합) — 운영자 11/17 "NH뿐만 아니라 키움·한투·KB API 모두 확인해서 크로스 체크, 통합으로 보자".

xbroker.py(지수·2종목 고정)를 아무 종목에나 쓰도록 넓힌 것. 조회만 한다. 키·토큰은 출력하지 않는다.
- 한국 종목: 'KRX'(거래소) = 키움 · 한투(J) · NH(KRX) · 네이버 / '통합'(NXT 포함) = 키움(_AL) · NH(UNT) · KB
- 미국 종목: NH(해외 현재가) · 한투(해외 현재가) · 야후
- 일본 종목: 한투(도쿄) · 야후
채택은 xbroker.consensus(허용 오차 안에서 가장 많은 출처가 맞는 값, 동률이면 우선순위). 어긋난 출처는 off.

  python tools/xquote.py 005930 005935 --us NVDA MU --jp 6981
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xbroker import _f, consensus  # noqa: E402

US_EX = {"SOXL": "AMS", "KORU": "AMS", "SOXS": "AMS", "EWY": "AMS", "DRAM": "AMS"}   # 그 밖은 나스닥(NAS)


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001
        return None


# ── 한국 ──
def kr_kiwoom(code: str) -> dict:
    import kiwoom
    out = {}
    x = kiwoom.stock_now(code)
    if x and x.get("px"):
        out["KRX"] = x["px"]
    j, _ = kiwoom.call("ka10001", "/api/dostk/stkinfo", {"stk_cd": code + "_AL"})
    px = kiwoom._num(j.get("cur_prc"))
    if px:
        out["통합"] = abs(px)
    return out


def kr_kis(code: str) -> dict:
    import kis
    o = kis.get("/uapi/domestic-stock/v1/quotations/inquire-price", "FHKST01010100",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}).get("output") or {}
    return {"KRX": _f(o.get("stck_prpr"))} if _f(o.get("stck_prpr")) else {}


def kr_nh(code: str) -> dict:
    import nhfut
    out = {}
    for mk, basis in (("KRX", "KRX"), ("UNT", "통합")):
        o = _safe(lambda: nhfut._first(nhfut._call("/krstock/quote/v1/currentPrice", {"market_cd": mk, "iem_cd": code}), "Output_0")) or {}
        if _f(o.get("stck_prpr")):
            out[basis] = _f(o["stck_prpr"])
        time.sleep(0.3)
    return out


def kr(codes: list[str]) -> dict:
    """{code: {'KRX': {출처: 값, 'adopt': {...}}, '통합': {...}}}"""
    import kbprog
    from krx import quotes
    vals = {c: {"KRX": {}, "통합": {}} for c in codes}
    for c in codes:                                       # 증권사별 호출 한도 때문에 종목은 차례로, 증권사는 나란히
        with ThreadPoolExecutor(max_workers=3) as ex:
            res = dict(zip(("키움", "한투", "NH"), ex.map(lambda f: _safe(f, c) or {}, (kr_kiwoom, kr_kis, kr_nh))))
        for src, r in res.items():
            for basis, px in r.items():
                vals[c][basis][src] = px
    kb = _safe(kbprog.fetch_quotes, codes) or {}
    for c, px in kb.items():
        vals[c]["통합"]["KB"] = px
    nv = _safe(quotes, [c + ".KS" for c in codes]) or {}
    for c in codes:
        q = nv.get(c + ".KS") or {}
        if q.get("px"):
            vals[c]["KRX"]["네이버"] = q["px"]
    out = {}
    for c, b in vals.items():
        out[c] = {}
        for basis, v in b.items():
            if v:
                out[c][basis] = {"src": v, "adopt": consensus({s: (p, None) for s, p in v.items()}, "stk")}
    return out


# ── 미국·일본 ──
def _yahoo(sym: str) -> float | None:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m"
    m = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read())["chart"]["result"][0]["meta"]
    return m.get("regularMarketPrice")


def _kis_os(excd: str, sym: str) -> float | None:
    import kis
    o = kis.get("/uapi/overseas-price/v1/quotations/price", "HHDFS00000300", {"AUTH": "", "EXCD": excd, "SYMB": sym}).get("output") or {}
    return _f(o.get("last")) or None


def _nh_us(sym: str) -> float | None:
    import nhfut
    o = nhfut._first(nhfut._call("/gbstock/quote/v1/current", {"iem_cd": sym}), "Output_0")
    return _f(o.get("trdprc")) or None


def overseas(us: list[str], jp: list[str]) -> dict:
    out = {}
    for s in us:
        v = {k: p for k, p in (("NH", _safe(_nh_us, s)), ("한투", _safe(_kis_os, US_EX.get(s, "NAS"), s)), ("야후", _safe(_yahoo, s))) if p}
        out[s] = {"src": v, "adopt": consensus({k: (p, None) for k, p in v.items()}, "idx", prio=["NH", "한투", "야후"]) if v else None}
    for s in jp:
        v = {k: p for k, p in (("한투", _safe(_kis_os, "TSE", s)), ("야후", _safe(_yahoo, s + ".T"))) if p}
        out[s] = {"src": v, "adopt": consensus({k: (p, None) for k, p in v.items()}, "stk", prio=["한투", "야후"]) if v else None}
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("kr", nargs="*")
    ap.add_argument("--us", nargs="*", default=[])
    ap.add_argument("--jp", nargs="*", default=[])
    a = ap.parse_args()
    r = {"kr": kr(a.kr) if a.kr else {}, "os": overseas(a.us, a.jp)}
    print(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
