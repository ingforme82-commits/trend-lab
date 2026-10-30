"""🏛️ S7 — 코스피 지수 영향이 큰 삼성·SK 주도 7종목 (news.json s7, 1분마다)

  python tools/s7.py        # 지금 값을 한 번 계산해서 출력(확인용)

- 종목: 삼성전자 · 삼성전자우 · SK하이닉스 · SK스퀘어 · 삼성전기 · 삼성생명 · 삼성물산 (운영자 지정 2026-10-28)
- 지수 기여도(포인트) = 코스피 전일 종가 × 종목 비중(전일 시가총액 ÷ 코스피 보통주 전일 시가총액 합계) × 종목 등락률
  · 코스피는 보통주로만 계산하므로 삼성전자우는 기여도 0(등락만 표시)
  · 코스피 보통주 전일 시가총액 합계는 네이버 시가총액 순위 전체를 하루 한 번 더해서 구한다(근사치, 지수 조정 계수는 반영 안 함)
- S7 제외 코스피 = 코스피 등락 포인트 − S7 기여 포인트, 나머지 비중으로 나눈 등락률
- 시세·거래대금(통합): 네이버 실시간 · 투자자별·프로그램 매매(코스피 전체, 억 원): 네이버 지수 화면
- 종목별 외국인·기관(확정)·외국계 창구(장중)는 tools/flows.py 와 같은 출처
- 사실 집계이며 매수·매도 권유가 아니다.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tools" / "s7_cache.json"
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
S7 = {"005930": "삼성전자", "000660": "SK하이닉스", "005935": "삼성전자우", "402340": "SK스퀘어",
      "009150": "삼성전기", "032830": "삼성생명", "028260": "삼성물산"}
UP, DOWN = {"1", "2"}, {"4", "5"}


def _get(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def _n(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return 0.0


def _sign(d: dict) -> int:
    c = str((d.get("compareToPreviousPrice") or {}).get("code", "3"))
    return -1 if c in DOWN else 1 if c in UP else 0


def is_common(code: str) -> bool:
    """보통주 코드는 끝자리가 0 (우선주 5·7·9·K 등)."""
    return code.isdigit() and code.endswith("0")


# ── 순수 계산(tests/test_s7.py) ──
def prev_mcap(mcap: float, px: float, diff: float, sign: int) -> float:
    # Naver provides a signed difference and a separate direction code; use the magnitude only once.
    prev = px - sign * abs(diff)
    return mcap * prev / px if px and prev > 0 else mcap


def calc(rows: list[dict], kospi_prev: float, kospi_pts: float, total_prev: float) -> dict:
    """rows: code·chg·pmcap(전일 시총) → 각 행에 w(비중 %)·pts(기여 포인트) 채우고 S7 합계·S7 제외 코스피."""
    s_pts = s_w = 0.0
    for r in rows:
        if is_common(r["code"]) and total_prev and r.get("pmcap"):
            w = r["pmcap"] / total_prev
            r["w"] = round(w * 100, 2)
            r["pts"] = round(kospi_prev * w * r["chg"] / 100, 2)
            s_pts += r["pts"]; s_w += w
        else:
            r["w"], r["pts"] = None, 0.0
    ex_pts = kospi_pts - s_pts
    ex_chg = ex_pts / (kospi_prev * (1 - s_w)) * 100 if kospi_prev and s_w < 1 else None
    return {"pts": round(s_pts, 2), "w": round(s_w * 100, 2),
            "share": round(s_pts / kospi_pts * 100) if kospi_pts and abs(kospi_pts) >= 0.5 else None,
            "ex_pts": round(ex_pts, 2), "ex_chg": round(ex_chg, 2) if ex_chg is not None else None}


# ── 수집 ──
def _load() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _total_prev() -> float:
    """코스피 보통주 전일 시가총액 합계(원). 네이버 시가총액 순위 전체 페이지."""
    first = _get("https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=100")
    pages = -(-int(first.get("totalCount", 0)) // 100)

    def page(p):
        try:
            return first if p == 1 else _get(f"https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page={p}&pageSize=100")
        except Exception:  # noqa: BLE001
            return None
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(page, range(1, pages + 1)))
    if any(r is None for r in res):
        raise RuntimeError("시가총액 페이지 일부 실패")
    tot = 0.0
    for r in res:
        for s in r.get("stocks", []):
            if s.get("stockEndType") == "stock" and is_common(s.get("itemCode", "")):
                tot += prev_mcap(_n(s.get("marketValueRaw")), _n(s.get("closePriceRaw")),
                                 abs(_n(s.get("compareToPreviousClosePriceRaw"))), _sign(s))
    return tot


def build() -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from flows import _trader, _trend, parse_trader, parse_trend
    now = datetime.now(KST)
    today, t, hhmm = now.strftime("%Y-%m-%d"), time.time(), now.hour * 100 + now.minute
    base = "https://polling.finance.naver.com/api/realtime/domestic"
    sd = _get(f"{base}/stock/{','.join(S7)}").get("datas", [])
    kd = (_get(f"{base}/index/KOSPI").get("datas") or [{}])[0]
    kpx, kdiff = _n(kd.get("closePriceRaw")), abs(_n(kd.get("compareToPreviousClosePriceRaw")))
    if not kpx or not sd:
        return {}
    ksign = _sign(kd)
    kprev, kpts = kpx - ksign * kdiff, ksign * kdiff
    kday = str(kd.get("localTradedAt", ""))[:10]
    is_open = kd.get("marketStatus") == "OPEN"

    cache = _load()
    if cache.get("tot_day") != kday or not cache.get("tot"):
        try:
            cache["tot"], cache["tot_day"] = _total_prev(), kday
        except Exception:  # noqa: BLE001
            pass
    try:
        from kbprog import fetch_quotes
        kb_quotes = fetch_quotes(list(S7))
    except Exception:  # noqa: BLE001
        kb_quotes = {}
    rows = []
    for d in sd:
        code = d.get("itemCode")
        px, diff, sg = kb_quotes.get(code, _n(d.get("closePriceRaw"))), abs(_n(d.get("compareToPreviousClosePriceRaw"))), _sign(d)
        if code not in S7 or not px:
            continue
        prev = px - sg * diff
        tot_val = _n((d.get("integratedPriceInfo") or {}).get("accumulatedTradingValueRaw"))
        val = _n(d.get("accumulatedTradingValueRaw"))
        rows.append({"code": code, "name": S7[code], "px": px, "chg": round((px / prev - 1) * 100, 2) if prev else 0.0,
                     "val": max(tot_val, val) or None, "val_krx": val or None,
                     "pmcap": prev_mcap(_n(d.get("marketValueFullRaw")), px, diff, sg)})
    s = calc(rows, kprev, kpts, cache.get("tot") or 0)

    # 투자자별·프로그램(코스피 전체, 억 원): 2분마다
    if t - (cache.get("integ") or {}).get("t", 0) > 110:
        try:
            g = _get("https://m.stock.naver.com/api/index/KOSPI/integration")
            dt, pt = g.get("dealTrendInfo") or {}, g.get("programTrendInfo") or {}
            cache["integ"] = {"t": t, "day": dt.get("bizdate", ""), "ind": _n(dt.get("personalValue")), "frgn": _n(dt.get("foreignValue")),
                              "org": _n(dt.get("institutionalValue")), "arb": _n(pt.get("indexDifferenceReal")),
                              "nonarb": _n(pt.get("indexBiDifferenceReal")), "prog": _n(pt.get("indexTotalReal")),
                              "up": _n((g.get("upDownStockInfo") or {}).get("riseCount")) + _n((g.get("upDownStockInfo") or {}).get("upperCount")),
                              "dn": _n((g.get("upDownStockInfo") or {}).get("fallCount")) + _n((g.get("upDownStockInfo") or {}).get("lowerCount"))}
        except Exception:  # noqa: BLE001
            pass

    # 종목별 수급(확정 30분, 장 마감 직후 10분 / 외국계 창구 장중 2분)
    tr_c, wd_c = cache.setdefault("trend", {}), cache.setdefault("trader", {})
    trend_age = 600 if 1540 <= hhmm < 1900 else 1800
    need_tr = [c for c in S7 if c not in tr_c or (t - tr_c[c].get("t", 0) > trend_age and tr_c[c].get("day") != today)]
    need_wd = [c for c in S7 if c not in wd_c or (t - wd_c[c].get("t", 0) > 120 and (is_open or wd_c[c].get("day") != today))]

    def safe(fn, c):
        try:
            return fn(c)
        except Exception:  # noqa: BLE001
            return None
    with ThreadPoolExecutor(max_workers=6) as ex:
        tr = dict(zip(need_tr, ex.map(lambda c: safe(_trend, c), need_tr)))
        wd = dict(zip(need_wd, ex.map(lambda c: safe(_trader, c), need_wd)))
    for c, items in tr.items():
        if items is not None:
            tr_c[c] = {"t": t, "items": items, "day": (items[0].get("localTradedAt") if items else "")}
    for c, data in wd.items():
        if data is not None:
            wd_c[c] = {"t": t, "data": data, "day": str(data[0].get("date", ""))[:10] if data else ""}
    try:
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    try:
        from kbprog import fetch as kb_prog
        prog = kb_prog(list(S7), set(S7))
    except Exception:  # noqa: BLE001
        prog = {}
    for r in rows:
        r["prog"] = prog.get(r["code"])
        r["inv"] = parse_trend((tr_c.get(r["code"]) or {}).get("items") or [])
        r["win"] = parse_trader((wd_c.get(r["code"]) or {}).get("data") or [], today, r["px"])
        r.pop("pmcap", None)
    order = list(S7)
    rows.sort(key=lambda r: order.index(r["code"]))
    ig = cache.get("integ") or {}
    return {"at": int(t * 1000), "open": is_open, "day": kday,
            "quote_source": "KB Open API IVU10140" if kb_quotes else "Naver realtime fallback",
            "kospi": {"px": kpx, "prev": kprev, "pts": round(kpts, 2), "chg": round(kpts / kprev * 100, 2) if kprev else 0.0,
                      **{k: ig.get(k) for k in ("ind", "frgn", "org", "arb", "nonarb", "prog", "up", "dn")}, "flow_day": ig.get("day")},
            "s7": s, "rows": rows, "approx": not cache.get("tot")}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = build()
    k, s = d["kospi"], d["s7"]
    print(f"코스피 {k['px']:,.2f} ({k['chg']:+.2f}%, {k['pts']:+.2f}p)  S7 기여 {s['pts']:+.2f}p (비중 {s['w']}%, 상승분의 {s['share']}%)  "
          f"S7 제외 {s['ex_pts']:+.2f}p {s['ex_chg']}%")
    print(f"투자자(억) 개인 {k['ind']} 외국인 {k['frgn']} 기관 {k['org']} · 프로그램 차익 {k['arb']} 비차익 {k['nonarb']} 합계 {k['prog']}")
    for r in d["rows"]:
        inv, win = r["inv"] or {}, r["win"] or {}
        e = lambda v: f"{v / 1e8:+,.0f}억" if v is not None else "-"
        print(f"  {r['name']:<7} {r['chg']:+6.2f}%  기여 {r['pts']:+7.2f}p  비중 {r['w']}%  대금 {e(r['val'])}  창구 {e(win.get('amt'))}  외인 {e(inv.get('frgn'))} 기관 {e(inv.get('org'))}")
