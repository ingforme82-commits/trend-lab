"""섹터 시세 감시 — 종목 가격 변화를 '뉴스처럼' 속보 목록에 싣는다 (data/sectors.json 에 섹터·종목)

신호(종목별 현지 거래일 기준, 하루 한 번씩만):
- 하루 +3% / -3% 이상, +5% / -5% 이상
- 3개월 고점 돌파
- 52주 신고가 3% 이내 접근 / 52주 신고가 돌파
5분마다 야후 일봉(3개월)을 받아 확인하고, 새 신호가 생기면 섹터별로 한 줄 속보를 만든다.
화면용 섹터 카드 데이터(종목별 등락·고점 대비 위치)도 함께 만든다. 사실 집계이며 추천이 아니다.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "tools" / "sector_state.json"
ET = timezone(timedelta(hours=-4))       # 미국 동부(서머타임 기간). 날짜 구분용이라 1시간 오차는 무시


def _quote(sym: str) -> dict | None:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range=3mo&interval=1d"
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=12).read())["chart"]["result"][0]
        m, q = r["meta"], r["indicators"]["quote"][0]
        off = m.get("gmtoffset", 0)
        day = lambda t: datetime.fromtimestamp(t + off, timezone.utc).strftime("%Y-%m-%d")   # 거래소 현지 날짜
        mday = day(m.get("regularMarketTime", 0))
        past = [(day(t), c, h) for t, c, h in zip(r["timestamp"], q["close"], q["high"]) if day(t) < mday and c]
        if not past:
            return None
        today = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + off, timezone.utc)
        return {"px": m.get("regularMarketPrice"), "prev": past[-1][1], "hi52": m.get("fiftyTwoWeekHigh"),
                "hi3m": max(h for _, _, h in past if h), "at": m.get("regularMarketTime", 0) * 1000,
                "day": mday, "cur": m.get("currency", "USD"),
                "stale": today.weekday() < 5 and mday < today.strftime("%Y-%m-%d")}   # 거래일인데 아직 전일 값(개장 전·지연)
    except Exception:  # noqa: BLE001
        return None


def run() -> tuple[list[dict], list[dict]]:
    """반환: (속보 항목들, 섹터 카드). 5분마다만 새로 받는다."""
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {"at": 0, "fired": {}, "items": [], "cards": []}
    now = datetime.now(timezone.utc)
    if now.timestamp() - st.get("at", 0) < 290:
        return st["items"], st["cards"]
    try:
        sectors = json.loads((ROOT / "data" / "sectors.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return st["items"], st["cards"]
    # 신호 기록: "거래일:종목:신호" (사흘 지난 기록은 지움)
    cutoff = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    fired = {k: v for k, v in st.get("fired", {}).items() if not k.startswith("_") and k[:10] >= cutoff}
    from concurrent.futures import ThreadPoolExecutor
    syms = [sym for sec in sectors.values() for sym in sec["tickers"]]
    with ThreadPoolExecutor(max_workers=8) as ex:            # 60여 종목을 동시에(약 5초)
        quotes = dict(zip(syms, ex.map(_quote, syms)))
    try:
        from krx import merge
        merge(quotes)                                          # 한국 종목은 네이버 실시간(야후는 20분 지연)
    except Exception:  # noqa: BLE001
        pass
    cards, new_items = [], []
    for sname, sec in sectors.items():
        rows, sig = [], []
        for sym, name in sec["tickers"].items():
            d = quotes.get(sym)
            if not d or not d.get("px") or not d.get("prev"):
                continue
            chg = (d["px"] / d["prev"] - 1) * 100
            to52 = (d["px"] / d["hi52"] - 1) * 100 if d.get("hi52") else None
            to3m = (d["px"] / d["hi3m"] - 1) * 100 if d.get("hi3m") else None
            flags = []
            if chg >= 5: flags.append("+5%")
            elif chg >= 3: flags.append("+3%")
            if chg <= -5: flags.append("-5%")
            elif chg <= -3: flags.append("-3%")
            if d.get("stale"): flags = []                            # 전일 값이면 오늘 신호로 쓰지 않음
            if to52 is not None and to52 >= 0 and not d.get("stale"): flags.append("52주 신고가")
            elif to52 is not None and to52 >= -3 and not d.get("stale"): flags.append("52주 고가 근접")
            if to3m is not None and to3m > 0 and not d.get("stale"): flags.append("3개월 고점 돌파")
            rows.append({"sym": sym, "name": name, "px": round(d["px"], 2), "chg": round(chg, 2), "cur": d.get("cur", "USD"),
                         "to52": None if to52 is None else round(to52, 1), "to3m": None if to3m is None else round(to3m, 1),
                         "flags": flags, "at": d["at"], "stale": bool(d.get("stale"))} | ({"val": d["val"], "val_krx": d.get("val_krx")} if d.get("val") else {}))
            fresh = now.timestamp() * 1000 - d["at"] < 30 * 60_000      # 장중(30분 안에 체결된 값)일 때만 신호
            for f in flags:
                key = f"{d['day']}:{sym}:{f}"
                if fresh and key not in fired:
                    fired[key] = True
                    sig.append((sym, name, f, chg, to3m, to52))
        rows.sort(key=lambda r: -r["chg"])
        avg = sum(r["chg"] for r in rows) / len(rows) if rows else 0
        cards.append({"name": sname, "icon": sec.get("icon", "📊"), "tag": sec.get("tag", sname), "avg": round(avg, 2), "rows": rows})
        if sig:
            ups = [f"{n} {c:+.1f}%" for s, n, f, c, *_ in sig if f in ("+3%", "+5%")]
            dns = [f"{n} {c:+.1f}%" for s, n, f, c, *_ in sig if f in ("-3%", "-5%")]
            his = [f"{n}({f})" for s, n, f, *_ in sig if f in ("52주 신고가", "52주 고가 근접", "3개월 고점 돌파")]
            parts = ([f"{', '.join(ups)} 3% 넘게 상승"] if ups else []) + ([f"{', '.join(dns)} 3% 넘게 하락"] if dns else []) + ([" · ".join(his)] if his else [])
            text = f"{sec.get('icon', '📊')} {sname} 섹터: " + " / ".join(parts) + f" (섹터 평균 {avg:+.1f}%)"
            new_items.append({"ts": int(now.timestamp() * 1000), "src": "섹터 시세 감시", "kind": "섹터 시세", "text": text[:160],
                              "tags": [sec.get("tag", sname)], "hot": False, "sector": sname})
    keep = [it for it in st.get("items", []) if now.timestamp() * 1000 - it["ts"] < 30 * 3600_000]
    st = {"at": now.timestamp(), "fired": fired, "items": (new_items + keep)[:40], "cards": cards}
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return st["items"], st["cards"]


if __name__ == "__main__":
    items, cards = run()
    for c in cards:
        print(c["icon"], c["name"], c["avg"], [(r["name"], r["chg"], r["flags"]) for r in c["rows"]])
    for it in items:
        print(it["text"])
