"""💰 주도주 수급 — 반도체·국내 보안주 상승 상위 종목의 거래대금·수급(data/flows.json 에 종목군).

  python tools/flows.py        # 지금 값을 한 번 계산해서 출력(확인용)

- 시세·거래대금: 네이버 실시간(krx.quotes), 1분마다. 거래대금은 통합(KRX + 넥스트레이드 프리·애프터마켓)
- 외국계 창구 순매수(장중): 다음 금융 trader/histories — 외국계 '증권사 창구' 합계라 외국인 투자자 수급과 다르다. 2분마다
- 외국인·기관·개인 순매수(확정): 네이버 investor-trend(KRX), 장 마감 후 확정된 일별 값. 30분마다(15:40~19:00 은 10분마다)
- 프로그램 매매(종목별): 무료 공개 출처가 없어 비워 둔다 → 증권사 API 연결 후 추가
- 금액은 '순매수 수량 × 그날 종가(장중은 현재가)'로 계산한 추정치. 사실 집계이며 매수·매도 권유가 아니다.
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
CACHE = ROOT / "tools" / "flows_cache.json"
KST = timezone(timedelta(hours=9))
TOP = 6
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _get(url: str, headers: dict | None = None) -> dict | list:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    return json.loads(urllib.request.urlopen(req, timeout=8).read())


def _n(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return 0.0


# ── 순수 함수(tests/test_flows.py) ──
def pick_top(tickers: dict[str, str], q: dict[str, dict], n: int = TOP) -> list[dict]:
    """종목군에서 등락률 상위 n개 ∪ 거래대금 상위 n개(등락률 순). 시세 없는 종목은 뺀다."""
    rows = [{"sym": s, "code": s.split(".")[0], "name": name, "px": q[s]["px"], "chg": q[s]["chg"], "val": q[s].get("val"), "val_krx": q[s].get("val_krx")}
            for s, name in tickers.items() if q.get(s) and q[s].get("px")]
    by_chg = sorted(rows, key=lambda r: -r["chg"])[:n]
    by_val = sorted(rows, key=lambda r: -(r["val"] or 0))[:n]
    keep = {r["sym"] for r in by_chg + by_val}
    return [r for r in sorted(rows, key=lambda r: -r["chg"]) if r["sym"] in keep]


def parse_trend(items: list[dict]) -> dict | None:
    """네이버 investor-trend items → 최근 확정일 순매수 금액(추정)과 5일 합계."""
    days = []
    for it in items[:5]:
        k = it.get("krx") or {}
        px = _n(k.get("closingPrice"))
        if not px:
            continue
        days.append({"day": it.get("localTradedAt", ""), "frgn": _n(k.get("foreignNetVolume")) * px,
                     "org": _n(k.get("organizationNetVolume")) * px, "ind": _n(k.get("individualNetVolume")) * px})
    if not days:
        return None
    d0 = days[0]
    return {"day": d0["day"], "frgn": d0["frgn"], "org": d0["org"], "ind": d0["ind"],
            "frgn5": sum(d["frgn"] for d in days), "org5": sum(d["org"] for d in days), "n5": len(days)}


def parse_trader(data: list[dict], today: str, px: float) -> dict | None:
    """다음 trader/histories → 오늘 외국계 창구 순매수(수량·추정 금액). 오늘 행이 없으면 None."""
    if not data or str(data[0].get("date", ""))[:10] != today:
        return None
    net = _n((data[0].get("foreignTrader") or {}).get("netSales"))
    return {"qty": net, "amt": net * px}


# ── 수집 ──
def _trend(code: str) -> list[dict]:
    u = f"https://stock.naver.com/api/stockSecurity/investor-trend/v2/domestic/{code}/paged?exchangeType=krx&pageSize=5"
    return _get(u).get("items", [])


def _trader(code: str) -> list[dict]:
    u = f"https://finance.daum.net/api/trader/histories?symbolCode=A{code}&page=1&perPage=1"
    return _get(u, {"Referer": "https://finance.daum.net/"}).get("data", [])


def _load() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"trend": {}, "trader": {}}


def build() -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from krx import quotes
    groups = json.loads((ROOT / "data" / "flows.json").read_text(encoding="utf-8"))
    syms = [s for g in groups.values() for s in g["tickers"]]
    q = quotes(syms)
    if not q:
        return {}
    now = datetime.now(KST)
    today, t = now.strftime("%Y-%m-%d"), time.time()
    hhmm = now.hour * 100 + now.minute
    is_open = any(v.get("status") == "OPEN" for v in q.values()) and 900 <= hhmm < 1535
    cache = _load()
    tops = {name: pick_top(g["tickers"], q) for name, g in groups.items()}
    codes = sorted({r["code"] for rows in tops.values() for r in rows})

    # 확정 수급: 30분마다, 장 마감 직후(15:40~19:00)에는 오늘 값이 나올 때까지 10분마다
    trend_age = 600 if 1540 <= hhmm < 1900 else 1800
    need_tr = [c for c in codes if t - (cache["trend"].get(c) or {}).get("t", 0) > trend_age
               and (cache["trend"].get(c) or {}).get("day") != today or c not in cache["trend"]]
    # 외국계 창구: 장중 2분마다, 장 끝난 뒤에는 오늘 값 한 번 더
    need_wd = [c for c in codes if c not in cache["trader"] or (t - cache["trader"][c].get("t", 0) > 120
               and (is_open or cache["trader"][c].get("day") != today or cache["trader"][c].get("t", 0) < _close_ts(now)))]
    with ThreadPoolExecutor(max_workers=6) as ex:
        tr = dict(zip(need_tr, ex.map(lambda c: _safe(_trend, c), need_tr)))
        wd = dict(zip(need_wd, ex.map(lambda c: _safe(_trader, c), need_wd)))
    for c, items in tr.items():
        if items is not None:
            cache["trend"][c] = {"t": t, "items": items, "day": (items[0].get("localTradedAt") if items else "")}
    for c, data in wd.items():
        if data is not None:
            cache["trader"][c] = {"t": t, "data": data, "day": str(data[0].get("date", ""))[:10] if data else ""}
    try:
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass

    out = []
    for name, rows in tops.items():
        for r in rows:
            r["inv"] = parse_trend((cache["trend"].get(r["code"]) or {}).get("items") or [])
            r["win"] = parse_trader((cache["trader"].get(r["code"]) or {}).get("data") or [], today, r["px"])
            r.pop("sym")
        out.append({"name": name, "icon": groups[name].get("icon", ""), "n": len(groups[name]["tickers"]),
                    "up": sum(1 for s in groups[name]["tickers"] if (q.get(s) or {}).get("chg", 0) > 0), "rows": rows})
    return {"at": int(t * 1000), "open": is_open, "groups": out, "prog": None}


def _close_ts(now: datetime) -> float:
    return now.replace(hour=15, minute=35, second=0, microsecond=0).timestamp()


def _safe(fn, code):
    try:
        return fn(code)
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = build()
    for g in d.get("groups", []):
        print(f"\n{g['icon']} {g['name']} (상승 {g['up']}/{g['n']})")
        for r in g["rows"]:
            inv, win = r["inv"] or {}, r["win"] or {}
            e = lambda v: f"{v / 1e8:+,.0f}억" if v is not None else "-"
            print(f"  {r['name']:<10} {r['chg']:+6.2f}%  대금 {e(r['val'])}  외국계창구 {e(win.get('amt'))}"
                  f"  | {inv.get('day', '-')} 외인 {e(inv.get('frgn'))} 기관 {e(inv.get('org'))} · 5일 외인 {e(inv.get('frgn5'))} 기관 {e(inv.get('org5'))}")
