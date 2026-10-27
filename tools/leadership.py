"""📈 Leadership Score · Sector Momentum — 4개 지표 버전(수급 제외). 설계: docs/leadership-design.md

  python tools/leadership.py          # 계산해서 표로 보기 + tools/leadership_dry.json 저장(사이트에는 안 올림)

지표(국내 감시 종목끼리 백분위 0~100 → 가중 평균)
  거래대금 가속도(25) : 오늘 누적 거래대금 ÷ 직전 20거래일 평균 거래대금
  상대강도(20)        : 오늘 등락률 − 소속 지수(코스피/코스닥) 등락률
  5일선 위치(15)      : 현재가 ÷ 5일 이동평균(직전 4일 종가 + 현재가) − 1
  신고가 근접(15)     : 현재가 ÷ 직전 3개월 최고가 − 1 (0 이상이면 돌파)
누락·지연 지표는 빼고 남은 가중치로 다시 나눈다(used 에 기록). 순위일 뿐 매수·매도 권유가 아니다.
"""

from __future__ import annotations

import json
import statistics
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "tools" / "sector_state.json"
HIST = ROOT / "tools" / "leadership_hist.json"
DRY = ROOT / "tools" / "leadership_dry.json"
KST = timezone(timedelta(hours=9))
W = {"tva": 25, "rs": 20, "ma5": 15, "high": 15}
NAMES = {"tva": "거래대금 가속도", "rs": "상대강도", "ma5": "5일선 위치", "high": "신고가 근접"}
STALE_MS = 10 * 60_000


# ── 순수 계산(테스트 대상) ──
def pct_rank(vals: dict[str, float | None]) -> dict[str, float]:
    """값 → 0~100 백분위(동점은 평균 순위). None 은 제외. 1개뿐이면 50."""
    xs = sorted((v, k) for k, v in vals.items() if v is not None)
    if not xs:
        return {}
    if len(xs) == 1:
        return {xs[0][1]: 50.0}
    out, i = {}, 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1][0] == xs[i][0]:
            j += 1
        r = (i + j) / 2 / (len(xs) - 1) * 100
        for k in range(i, j + 1):
            out[xs[k][1]] = round(r, 1)
        i = j + 1
    return out


def indicators(row: dict, hist: dict | None, idx_chg: float | None) -> dict[str, float | None]:
    """종목 하나의 원값. hist: {"closes": [직전 거래일 종가들(오래된→최근)], "vals": [직전 거래대금들], "hi3m": 직전 3개월 고가}"""
    px, chg, val = row.get("px"), row.get("chg"), row.get("val_krx") or row.get("val")   # 과거 일봉(KRX)과 같은 기준
    h = hist or {}
    closes, vals = h.get("closes") or [], h.get("vals") or []
    avg20 = sum(vals[-20:]) / len(vals[-20:]) if len(vals) >= 10 else None
    ma5 = (sum(closes[-4:]) + px) / 5 if px and len(closes) >= 4 else None
    return {
        "tva": val / avg20 if val and avg20 else None,
        "rs": chg - idx_chg if chg is not None and idx_chg is not None else None,
        "ma5": (px / ma5 - 1) * 100 if ma5 else None,
        "high": (px / h["hi3m"] - 1) * 100 if px and h.get("hi3m") else None,
    }


def score(raw: dict[str, dict[str, float | None]]) -> dict[str, dict]:
    """raw: {sym: 지표 원값} → {sym: {"score", "parts": {지표: 백분위}, "used": [쓴 지표]}}"""
    ranks = {k: pct_rank({s: r[k] for s, r in raw.items()}) for k in W}
    out = {}
    for s in raw:
        parts = {k: ranks[k][s] for k in W if s in ranks[k]}
        wsum = sum(W[k] for k in parts)
        out[s] = {"score": round(sum(parts[k] * W[k] for k in parts) / wsum, 1) if wsum else None,
                  "parts": parts, "used": list(parts)}
    return out


def sector_momentum(sectors: dict[str, list[dict]]) -> list[dict]:
    """sectors: {섹터: [{"score","chg","above5","val","avgval"}]} → 모멘텀 내림차순.
    = 0.4·종목 점수 중앙값 + 0.3·확산도(상승 비율·5일선 위 비율 평균) + 0.3·거래대금 점유율 변화(섹터끼리 백분위)"""
    tot_v = sum(m["val"] or 0 for ms in sectors.values() for m in ms)
    tot_a = sum(m["avgval"] or 0 for ms in sectors.values() for m in ms)
    shift = {}
    for n, ms in sectors.items():
        v, a = sum(m["val"] or 0 for m in ms), sum(m["avgval"] or 0 for m in ms)
        shift[n] = (v / tot_v) / (a / tot_a) if tot_v and tot_a and a else None
    shift_r = pct_rank(shift)
    out = []
    for n, ms in sectors.items():
        sc = [m["score"] for m in ms if m["score"] is not None]
        if not sc:
            continue
        up = sum(1 for m in ms if (m["chg"] or 0) > 0) / len(ms) * 100
        ab = [m["above5"] for m in ms if m["above5"] is not None]
        breadth = (up + (sum(ab) / len(ab) * 100 if ab else up)) / 2
        med = statistics.median(sc)
        parts = [(0.4, med), (0.3, breadth)] + ([(0.3, shift_r[n])] if n in shift_r else [])
        mom = sum(w * v for w, v in parts) / sum(w for w, _ in parts)
        out.append({"name": n, "momentum": round(mom, 1), "median": round(med, 1), "breadth": round(breadth, 1),
                    "up": round(up, 1), "share_shift": None if shift[n] is None else round(shift[n], 2), "n": len(ms)})
    return sorted(out, key=lambda x: -x["momentum"])


# ── 데이터 ──
def _daily(sym: str) -> dict | None:
    """직전 거래일까지의 일봉(오늘 제외): 종가·거래대금(종가×거래량)·3개월 고가."""
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range=6mo&interval=1d"
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=12).read())["chart"]["result"][0]
    except Exception:  # noqa: BLE001
        return None
    q, off = r["indicators"]["quote"][0], r["meta"].get("gmtoffset", 32400)
    today = datetime.now(KST).strftime("%Y-%m-%d")
    rows = [(datetime.fromtimestamp(t + off, timezone.utc).strftime("%Y-%m-%d"), c, v, h)
            for t, c, v, h in zip(r["timestamp"], q["close"], q["volume"], q["high"]) if c and v is not None]
    rows = [x for x in rows if x[0] < today]
    if len(rows) < 10:
        return None
    cut = (datetime.now(KST) - timedelta(days=92)).strftime("%Y-%m-%d")
    return {"last": rows[-1][0], "closes": [x[1] for x in rows[-20:]], "vals": [x[1] * x[2] for x in rows[-20:]],
            "hi3m": max(x[3] for x in rows if x[0] >= cut and x[3])}


def history(syms: list[str]) -> dict[str, dict]:
    """하루 한 번만 받는다(오늘 날짜로 저장)."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    try:
        c = json.loads(HIST.read_text(encoding="utf-8"))
        if c.get("day") == today and all(s in c["data"] for s in syms):
            return c["data"]
    except Exception:  # noqa: BLE001
        pass
    with ThreadPoolExecutor(max_workers=8) as ex:
        data = {s: d for s, d in zip(syms, ex.map(_daily, syms)) if d}
    HIST.write_text(json.dumps({"day": today, "data": data}, ensure_ascii=False), encoding="utf-8")
    return data


def build(cards: list[dict], idx: dict[str, dict], hist: dict[str, dict], now_ms: int) -> dict:
    """cards: sector_watch 섹터 카드, idx: {"^KS11": {chg, at, status}, "^KQ11": ...}"""
    rows, sec_of = {}, {}
    for c in cards:
        for r in c.get("rows", []):
            if r.get("cur") == "KRW":
                rows[r["sym"]] = r
                sec_of.setdefault(r["sym"], c["name"])
    raw, notes = {}, {}
    for s, r in rows.items():
        late = r.get("stale") or (r.get("at") and now_ms - r["at"] > STALE_MS and (idx.get("^KS11") or {}).get("status") == "OPEN")
        ix = idx.get("^KQ11" if s.endswith(".KQ") else "^KS11") or {}
        ind = indicators(r, hist.get(s), ix.get("chg"))
        if late:                                   # 지연·전일 값이면 오늘 값에 기대는 지표는 뺀다
            ind = {k: (None if k in ("tva", "rs") else v) for k, v in ind.items()}
            notes[s] = "지연"
        raw[s] = ind
    sc = score(raw)
    stocks = []
    for s, r in rows.items():
        h = hist.get(s) or {}
        avg20 = sum(h["vals"]) / len(h["vals"]) if h.get("vals") else None
        stocks.append({"sym": s, "name": r["name"], "sector": sec_of[s], "chg": r.get("chg"), "val": r.get("val_krx") or r.get("val"),
                       "score": sc[s]["score"], "parts": sc[s]["parts"], "used": sc[s]["used"],
                       "raw": {k: (None if v is None else round(v, 2)) for k, v in raw[s].items()},
                       "note": notes.get(s, "" if len(sc[s]["used"]) == 4 else f"{4 - len(sc[s]['used'])}개 지표 누락"),
                       "avgval": avg20})
    stocks.sort(key=lambda x: -(x["score"] or -1))
    by_sec: dict[str, list[dict]] = {}
    for x in stocks:
        by_sec.setdefault(x["sector"], []).append({"score": x["score"], "chg": x["chg"], "val": x["val"], "avgval": x["avgval"],
                                                   "above5": None if x["raw"]["ma5"] is None else x["raw"]["ma5"] > 0})
    return {"at": now_ms, "weights": W, "stocks": stocks, "sectors": sector_momentum(by_sec),
            "idx": {k: {"chg": v.get("chg"), "at": v.get("at")} for k, v in idx.items()},
            "hist_day": max((h.get("last", "") for h in hist.values()), default="")}


def public(cards: list[dict]) -> dict:
    """사이트용: 섹터 모멘텀만(종목별 점수·순위는 넣지 않는다 — 종목 추천처럼 보이지 않게)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from krx import quotes
    syms = [r["sym"] for c in cards for r in c.get("rows", []) if r.get("cur") == "KRW"]
    if not syms:
        return {}
    idx = quotes(["^KS11", "^KQ11"])
    res = build(cards, idx, history(syms), int(datetime.now(timezone.utc).timestamp() * 1000))
    late = sum(1 for x in res["stocks"] if x["note"] == "지연")
    return {"at": res["at"], "sectors": res["sectors"], "open": (idx.get("^KS11") or {}).get("status") == "OPEN",
            "late": late, "n": len(res["stocks"]), "hist_day": res["hist_day"]}


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from krx import quotes
    cards = json.loads(STATE.read_text(encoding="utf-8"))["cards"]
    syms = [r["sym"] for c in cards for r in c.get("rows", []) if r.get("cur") == "KRW"]
    idx = quotes(["^KS11", "^KQ11"])
    res = build(cards, idx, history(syms), int(datetime.now(timezone.utc).timestamp() * 1000))
    DRY.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    t = datetime.fromtimestamp(res["at"] / 1000, KST)
    print(f"[{t:%m/%d %H:%M} KST · 코스피 {idx.get('^KS11', {}).get('chg')}% · 코스닥 {idx.get('^KQ11', {}).get('chg')}% · 일봉 기준 {res['hist_day']}]")
    print("\n섹터 모멘텀")
    for s in res["sectors"]:
        print(f"  {s['name']:<8} {s['momentum']:5.1f}  (종목 중앙값 {s['median']}, 확산도 {s['breadth']}, 상승 {s['up']}%, 거래대금 점유율 변화 ×{s['share_shift']})")
    print("\n종목 상위 10 / 하위 5   점수 | 거래대금 가속도·상대강도·5일선·신고가 (원값)")
    for x in res["stocks"][:10] + [None] + res["stocks"][-5:]:
        if x is None:
            print("  …")
            continue
        r = x["raw"]
        print(f"  {x['name']:<10} {x['score']!s:>5} | ×{r['tva']} · {r['rs']:+}%p · {r['ma5']:+}% · {r['high']:+}%  {x['note']}"
              if None not in r.values() else f"  {x['name']:<10} {x['score']!s:>5} | {r} {x['note']}")


if __name__ == "__main__":
    main()
