"""🏁 오늘의 주도 섹터(자동) — 한국 업종·테마, 미국 업종을 네이버 금융에서 찾아 순위를 매긴다(news.json leaders).

  python tools/leaders.py        # 지금 값을 한 번 계산해서 출력(확인용)

한국(네이버 국내 업종 79개 · 테마 약 260개)
- 등락률 상위 후보(구성 3종목 이상)만 구성 종목을 받아 거래대금·시가총액·상승 비율을 더한다
미국(네이버 해외 · 나스닥·뉴욕거래소 시가총액 상위 각 300종목)
- 종목의 업종 분류(industryGroupKor)로 묶어 시가총액 가중 등락률·거래대금(달러)·상승 비율을 낸다
주도 점수(0~100) = 등락률 순위 50 + 거래대금 순위 30 + 상승 종목 비율 20 (후보끼리 비교한 백분위)
- 순위일 뿐 매수·매도 권유가 아니다. 화면에서 등락률·거래대금·시가총액·상승 비율로 다시 정렬할 수 있다
갱신: 한국 08~20시·미국 17~09시(프리·정규·애프터) 3분마다, 그 밖에는 30분마다
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
CACHE = ROOT / "tools" / "leaders_cache.json"
STATE = ROOT / "tools" / "leaders_state.json"
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
DOWN = {"4", "5"}
N_IND, N_THEME, N_SHOW, N_MEM = 12, 16, 8, 15


def _get(url: str):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10).read())


def _n(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return 0.0


def _chg(s: dict) -> float:
    v = abs(_n(s.get("fluctuationsRatioRaw") or s.get("fluctuationsRatio")))
    return -v if str((s.get("compareToPreviousPrice") or {}).get("code")) in DOWN else v


# ── 순수 계산(tests/test_leaders.py) ──
def pct_rank(vals: list[float]) -> list[float]:
    """값마다 후보 안에서의 백분위(0~100, 같은 값은 같은 점수)."""
    n = len(vals)
    if n <= 1:
        return [100.0] * n
    order = sorted(vals)
    return [round(sum(1 for x in order if x < v) / (n - 1) * 100, 1) for v in vals]


def score(groups: list[dict]) -> list[dict]:
    """groups: chg·val·up·n → score 채우고 점수순 정렬."""
    if not groups:
        return []
    rc, rv = pct_rank([g["chg"] for g in groups]), pct_rank([g.get("val") or 0 for g in groups])
    for g, a, b in zip(groups, rc, rv):
        g["breadth"] = round(g["up"] / g["n"] * 100, 1) if g["n"] else 0.0
        g["score"] = round(a * 0.5 + b * 0.3 + g["breadth"] * 0.2, 1)
    return sorted(groups, key=lambda g: -g["score"])


def us_groups(stocks: list[dict]) -> list[dict]:
    """미국 종목 → 업종별(3종목 이상) 시가총액 가중 등락률·거래대금·상승 비율."""
    by: dict[str, list[dict]] = {}
    for s in stocks:
        if s.get("ind"):
            by.setdefault(s["ind"], []).append(s)
    out = []
    for name, rows in by.items():
        if len(rows) < 3:
            continue
        mc = sum(r["mcap"] for r in rows) or 1
        out.append({"name": name, "chg": round(sum(r["chg"] * r["mcap"] for r in rows) / mc, 2), "n": len(rows),
                    "up": sum(1 for r in rows if r["chg"] > 0), "val": sum(r["val"] for r in rows), "mcap": mc,
                    "rows": sorted(rows, key=lambda r: -r["val"])[:N_MEM]})
    return out


# ── 수집 ──
def _kr_rows(stocks: list[dict]) -> list[dict]:
    return [{"code": s.get("itemCode"), "name": s.get("stockName"), "px": _n(s.get("closePriceRaw")), "chg": _chg(s),
             "val": _n(s.get("accumulatedTradingValueRaw")), "mcap": _n(s.get("marketValueRaw"))}
            for s in stocks if s.get("stockEndType") == "stock"]


def kr() -> dict:
    base = "https://m.stock.naver.com/api/stocks"
    ind = _get(f"{base}/industry?page=1&pageSize=100").get("groups", [])
    th = []
    for p in (1, 2, 3):
        g = _get(f"{base}/theme?page={p}&pageSize=100").get("groups", [])
        th += g
        if len(g) < 100:
            break

    def cands(gs, k):
        gs = [g for g in gs if int(g.get("totalCount") or 0) >= 3]
        return sorted(gs, key=lambda g: -_n(g.get("changeRate")))[:k]

    def members(kind_g):
        kind, g = kind_g
        try:
            st = _get(f"{base}/{kind}/{g['no']}?page=1&pageSize=100").get("stocks", [])
        except Exception:  # noqa: BLE001
            st = []
        rows = _kr_rows(st)
        return {"kind": kind, "no": g["no"], "name": g["name"], "chg": round(_n(g.get("changeRate")), 2),
                "n": int(g.get("totalCount") or 0), "up": int(g.get("riseCount") or 0), "down": int(g.get("fallCount") or 0),
                "val": sum(r["val"] for r in rows), "mcap": sum(r["mcap"] for r in rows),
                "rows": sorted(rows, key=lambda r: -r["val"])[:N_MEM]}
    todo = [("industry", g) for g in cands(ind, N_IND)] + [("theme", g) for g in cands(th, N_THEME)]
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(members, todo))
    status = ""
    try:
        status = _get(f"{base}/industry/{ind[0]['no']}?page=1&pageSize=1").get("marketStatus", "") if ind else ""
    except Exception:  # noqa: BLE001
        pass
    return {"industry": score([r for r in res if r["kind"] == "industry"])[:N_SHOW],
            "theme": score([r for r in res if r["kind"] == "theme"])[:N_SHOW], "open": status == "OPEN"}


def us() -> dict:
    pages = [(ex, p) for ex in ("NASDAQ", "NYSE") for p in (1, 2, 3)]

    def page(x):
        try:
            return _get(f"https://api.stock.naver.com/stock/exchange/{x[0]}/marketValue?page={x[1]}&pageSize=100").get("stocks", [])
        except Exception:  # noqa: BLE001
            return []
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = [s for ss in ex.map(page, pages) for s in ss]
    stocks, seen, status = [], set(), ""
    for s in res:
        sym = s.get("symbolCode")
        if s.get("stockEndType") != "stock" or sym in seen:
            continue
        seen.add(sym)
        status = status or s.get("marketStatus", "")
        stocks.append({"sym": sym, "name": s.get("stockName"), "ind": (s.get("industryCodeType") or {}).get("industryGroupKor"),
                       "px": _n(s.get("closePriceRaw")), "chg": _chg(s), "val": _n(s.get("accumulatedTradingValueRaw")),
                       "mcap": _n(s.get("marketValueRaw"))})
    return {"industry": score(us_groups(stocks))[:N_SHOW], "open": status == "OPEN",
            "map": {s["sym"]: {"mcap": s["mcap"], "val": s["val"]} for s in stocks}}


def _fresh(c: dict, k: str, hh: int) -> bool:
    live = (800 <= hh < 2000) if k == "kr" else (hh >= 1700 or hh < 900)
    return bool(c.get(k)) and time.time() - c[k].get("t", 0) < (170 if live else 1800)


def build() -> dict:
    now = datetime.now(KST)
    hh = now.hour * 100 + now.minute
    try:
        c = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        c = {}
    for k, fn in (("kr", kr), ("us", us)):
        if not _fresh(c, k, hh):
            try:
                c[k] = {"t": time.time(), "v": fn()}
            except Exception:  # noqa: BLE001
                pass
    try:
        CACHE.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    out = {"at": int(time.time() * 1000)}
    for k in ("kr", "us"):
        if c.get(k):
            out[k] = {**c[k]["v"], "at": int(c[k]["t"] * 1000)}
    return out


def changes(d: dict, now: datetime | None = None) -> list[dict]:
    """1위가 바뀌거나 새 섹터가 3위 안에 들면 속보 한 줄(같은 날 같은 섹터는 한 번). 장중에만."""
    now = now or datetime.now(KST)
    day = now.strftime("%Y-%m-%d")
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {}
    if st.get("day") != day:
        st = {"day": day}
    out = []
    for key, label, flag in (("kr.industry", "업종", "🇰🇷"), ("kr.theme", "테마", "🇰🇷"), ("us.industry", "업종", "🇺🇸")):
        m, k2 = key.split(".")
        blk = d.get(m) or {}
        gs = blk.get(k2) or []
        if not blk.get("open") or not gs:
            continue
        top3 = [g["name"] for g in gs[:3]]
        prev = st.get(key) or {}
        seen = set(prev.get("seen", []))
        if prev and top3[0] != prev.get("top1"):
            g = gs[0]
            out.append({"text": f"🏁 {flag} 주도 {label} 1위 → {g['name']} {g['chg']:+.2f}% (상승 {g['up']}/{g['n']}, 점수 {g['score']})", "mkt": m})
        for i, nm in enumerate(top3[1:], 2):
            if prev and nm not in seen:
                g = gs[i - 1]
                out.append({"text": f"🏁 {flag} 주도 {label} {i}위로 새로 진입: {nm} {g['chg']:+.2f}% (상승 {g['up']}/{g['n']})", "mkt": m})
        st[key] = {"top1": top3[0], "seen": sorted(seen | set(top3))}
    try:
        STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    CACHE.unlink(missing_ok=True)
    d = build()
    e = lambda v, u: f"{v / 1e12:,.1f}조" if u == "원" and v >= 1e12 else f"{v / 1e8:,.0f}억" if u == "원" else f"${v / 1e9:,.2f}B"
    for m, u in (("kr", "원"), ("us", "$")):
        for k in ("industry", "theme"):
            gs = (d.get(m) or {}).get(k)
            if not gs:
                continue
            print(f"\n[{m} {k}] open={d[m]['open']}")
            for g in gs:
                tops = ", ".join(f"{r['name']} {r['chg']:+.1f}%" for r in g["rows"][:3])
                print(f"  {g['score']:5.1f} {g['name'][:22]:<22} {g['chg']:+6.2f}%  상승 {g['up']}/{g['n']}  대금 {e(g['val'], u)}  | {tops}")
