"""⏱ 시간대별 강세 종목·섹터 — 한국·미국 장중 매시(KST) '이번 시간 상승률' 상위 종목과 업종 (news.json hourly).

  python tools/hourly.py        # 지금 값을 한 번 계산해서 출력(확인용)

- 한국: 네이버 코스피·코스닥 전 종목 시세(장중 3분마다), 업종은 네이버 국내 업종 79개 구성 종목으로 매일 한 번 지도 작성
- 미국: 네이버 해외 나스닥·뉴욕거래소 시가총액 상위 각 300종목(tools/leaders.py 저장본), 업종은 네이버 분류
- 시간대 시작값: 그 시(KST) 첫 수집 가격. 첫 시간대(한국 09시·미국 개장)는 전일 종가부터라 시가 갭 포함
- 이번 시간 상승률 = 지금(또는 다음 시간대 시작) 가격 ÷ 시간대 시작 가격 − 1
- 걸러내기: 한국 오늘 거래대금 30억 원 이상(우선주·ETF 제외), 업종은 걸러진 종목 3개 이상
- 사실 집계이며 매수·매도 권유가 아니다.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leaders import _chg, _get, _n  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "tools" / "hourly_state.json"
KR_CACHE = ROOT / "tools" / "hourly_kr_cache.json"
LCACHE = ROOT / "tools" / "leaders_cache.json"
KST = timezone(timedelta(hours=9))
MIN_VAL_KR = 30e8
N_STOCK, N_SEC = 8, 5


# ── 순수 계산(tests/test_hourly.py) ──
def slot_rank(start: dict[str, float], now: dict[str, dict], sector_of: dict[str, str], min_val: float = 0) -> dict:
    """start: 코드→시간대 시작 가격, now: 코드→{name, px, chg, val} → 이번 시간 상승률 상위 종목·업종."""
    rows = []
    for c, s0 in start.items():
        x = now.get(c)
        if not x or not s0 or not x.get("px") or (x.get("val") or 0) < min_val:
            continue
        rows.append({"code": c, "name": x["name"], "slot": round((x["px"] / s0 - 1) * 100, 2), "chg": x.get("chg"),
                     "val": x.get("val"), "sec": sector_of.get(c, "")})
    by: dict[str, list[dict]] = {}
    for r in rows:
        if r["sec"]:
            by.setdefault(r["sec"], []).append(r)
    secs = [{"name": k, "slot": round(sum(r["slot"] for r in v) / len(v), 2), "n": len(v), "up": sum(1 for r in v if r["slot"] > 0),
             "top": [r["name"] for r in sorted(v, key=lambda r: -r["slot"])[:3]]} for k, v in by.items() if len(v) >= 3]
    return {"stocks": sorted(rows, key=lambda r: -r["slot"])[:N_STOCK], "sectors": sorted(secs, key=lambda g: -g["slot"])[:N_SEC],
            "n": len(rows), "up": sum(1 for r in rows if r["slot"] > 0)}


# ── 수집 ──
def _kr_all() -> dict[str, dict]:
    """코스피·코스닥 전 종목(ETF 제외) 지금 시세. 장중 3분 캐시."""
    try:
        c = json.loads(KR_CACHE.read_text(encoding="utf-8"))
        if time.time() - c.get("t", 0) < 170:
            return c["v"]
    except Exception:  # noqa: BLE001
        pass
    base = "https://m.stock.naver.com/api/stocks/marketValue"
    pages = []
    for mk in ("KOSPI", "KOSDAQ"):
        n = int(_get(f"{base}/{mk}?page=1&pageSize=1").get("totalCount", 0))
        pages += [(mk, p) for p in range(1, -(-n // 100) + 1)]

    def page(x):
        try:
            return _get(f"{base}/{x[0]}?page={x[1]}&pageSize=100").get("stocks", [])
        except Exception:  # noqa: BLE001
            return []
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = [s for ss in ex.map(page, pages) for s in ss]
    v = {}
    for s in res:
        code = s.get("itemCode") or ""
        if s.get("stockEndType") != "stock" or not code.endswith("0"):          # ETF·우선주 제외
            continue
        v[code] = {"name": s.get("stockName"), "px": _n(s.get("closePriceRaw")), "chg": _chg(s), "val": _n(s.get("accumulatedTradingValueRaw")),
                   "status": s.get("marketStatus", "")}
    try:
        KR_CACHE.write_text(json.dumps({"t": time.time(), "v": v}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return v


def _kr_sectors(st: dict) -> dict[str, str]:
    """코드 → 네이버 국내 업종 이름(하루 한 번)."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    if st.get("secmap_day") == today and st.get("secmap"):
        return st["secmap"]
    base = "https://m.stock.naver.com/api/stocks/industry"
    inds = _get(f"{base}?page=1&pageSize=100").get("groups", [])

    def members(g):
        out, p = [], 1
        while True:
            try:
                ss = _get(f"{base}/{g['no']}?page={p}&pageSize=100").get("stocks", [])
            except Exception:  # noqa: BLE001
                break
            out += [s.get("itemCode") for s in ss]
            if len(ss) < 100:
                break
            p += 1
        return g["name"], out
    m = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for name, codes in ex.map(members, inds):
            for c in codes:
                if c:
                    m.setdefault(c, name)
    st["secmap"], st["secmap_day"] = m, today
    return m


def _us_all() -> tuple[dict[str, dict], dict[str, str], bool]:
    try:
        c = json.loads(LCACHE.read_text(encoding="utf-8"))["us"]["v"]
    except Exception:  # noqa: BLE001
        return {}, {}, False
    rows = c.get("all") or []
    return ({r["sym"]: {"name": r["name"], "px": r["px"], "chg": r["chg"], "val": r["val"]} for r in rows},
            {r["sym"]: r.get("ind") or "" for r in rows}, bool(c.get("open")))


def _market(st: dict, key: str, now_px: dict[str, dict], secmap: dict, is_open: bool, day: str, hour: str, min_val: float) -> dict | None:
    m = st.setdefault(key, {})
    if m.get("day") != day:
        m.clear()
        m["day"], m["slots"] = day, {}
    slots = m["slots"]
    if is_open and now_px and hour not in slots:                     # 이번 시간대 시작값
        first = not slots
        slots[hour] = {c: (x["px"] / (1 + x["chg"] / 100) if first and x.get("chg") is not None else x["px"]) for c, x in now_px.items() if x.get("px")}
        m["first"] = m.get("first") or hour
    if not slots:
        return None
    hours = sorted(slots, key=lambda h: (int(h) - (22 if key == "us" else 0)) % 24)   # 미국은 22시부터 다음 날 순서
    out = []
    for i, h in enumerate(hours):
        end = {c: {**now_px[c], "px": slots[hours[i + 1]][c]} for c in slots[h] if i + 1 < len(hours) and c in slots[hours[i + 1]] and c in now_px} if i + 1 < len(hours) else now_px
        r = slot_rank(slots[h], end, secmap, min_val)
        r.update(h=h, live=(i == len(hours) - 1 and is_open), gap=(h == m.get("first")))
        out.append(r)
    return {"day": day, "slots": out[::-1], "open": is_open}


def build() -> dict:
    now = datetime.now(KST)
    hh = now.hour * 100 + now.minute
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {}
    out = {"at": int(time.time() * 1000)}
    # 한국: 평일 09:00~15:30
    kr_open = now.weekday() < 5 and 900 <= hh < 1530
    if kr_open or (st.get("kr") or {}).get("day") == now.strftime("%Y-%m-%d"):
        try:
            px = _kr_all() if kr_open else {}
            if not kr_open:                                            # 장 마감 뒤엔 저장본 가격으로 마지막 시간대 마무리
                try:
                    px = json.loads(KR_CACHE.read_text(encoding="utf-8"))["v"]
                except Exception:  # noqa: BLE001
                    px = {}
            r = _market(st, "kr", px, _kr_sectors(st), kr_open, now.strftime("%Y-%m-%d"), f"{now.hour:02d}", MIN_VAL_KR)
            if r:
                out["kr"] = r
        except Exception:  # noqa: BLE001
            pass
    # 미국: 네이버 장 상태가 OPEN 일 때(서머타임 자동), 거래일은 KST 09시 이전이면 전날
    try:
        px, sec, us_open = _us_all()
        uday = (now - timedelta(hours=9)).strftime("%Y-%m-%d")
        if us_open or (st.get("us") or {}).get("day") == uday:
            r = _market(st, "us", px, sec, us_open, uday, f"{now.hour:02d}", 0)
            if r:
                out["us"] = r
    except Exception:  # noqa: BLE001
        pass
    st.pop("_", None)
    try:
        STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = build()
    for mk in ("kr", "us"):
        for s in (d.get(mk) or {}).get("slots", []):
            print(f"\n[{mk} {s['h']}시{' 진행 중' if s['live'] else ''}{' (전일 종가부터)' if s['gap'] else ''}] 상승 {s['up']}/{s['n']}")
            print("  업종:", " · ".join(f"{g['name']} {g['slot']:+.2f}%({g['up']}/{g['n']})" for g in s["sectors"]))
            print("  종목:", " · ".join(f"{r['name']} {r['slot']:+.2f}%" for r in s["stocks"]))
