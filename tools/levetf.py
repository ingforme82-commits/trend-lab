"""🔬 SOXL · KORU 점검 — 레버리지 3배 ETF를 기초지수·구성 종목과 함께 수치로 본다(news.json lev, 2분마다).

- 가격·갭·5일선·20일선·연속 양봉(적삼병 조건): watch.analyze 와 같은 계산(야후 정규장, 시가는 5분봉 첫 봉)
- 20일 고가·저가 대비 위치, 거래량(오늘 누적 ÷ 직전 20일 평균, 장중엔 누적이라 작게 나옴)
- 기초: SOXL ↔ 필라델피아 반도체지수(^SOX), KORU ↔ EWY(MSCI 한국 ETF). 기초 등락 ×3 과 실제 등락 차이
- 24시간 시세(하이퍼리퀴드 xyz:SOXL·xyz:KORU): 정규장 마감 후 움직임
- 🌙 시간외(프리·애프터마켓) 체결: tools/extended.py — 정규장 값과 따로 표시(EWY 는 KORU 행에)
- SOXL 구성 대형주(사이트 '미국 반도체' 섹터 13종목) 상승·하락 상위
수치·사실만(해석·추천 없음).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tools" / "levetf_cache.json"
ETF = [("SOXL", "SOXL", "미국 반도체 3배", "^SOX", "필라델피아 반도체지수"), ("KORU", "KORU", "한국 3배", "EWY", "EWY(MSCI 한국)")]


def extra_stats(past: list[dict], today: dict | None, vol_today: float | None, vols: list[float]) -> dict:
    """20일선·20일 고저·거래량 비율(순수 함수, tests/test_levetf.py)."""
    px = (today or {}).get("c") or past[-1]["c"]
    p20 = past[-19:] if today else past[-20:]
    ma20 = (sum(x["c"] for x in p20) + (px if today else 0)) / (len(p20) + (1 if today else 0))
    hi = max([x["h"] for x in past[-20:]] + ([today["h"]] if today else []))
    lo = min([x["l"] for x in past[-20:]] + ([today["l"]] if today else []))
    avgv = sum(vols[-20:]) / len(vols[-20:]) if vols else None
    return {"ma20": round(ma20, 2), "over_ma20": px > ma20, "vs_ma20": round((px / ma20 - 1) * 100, 2),
            "hi20": round(hi, 2), "lo20": round(lo, 2), "from_hi20": round((px / hi - 1) * 100, 2), "from_lo20": round((px / lo - 1) * 100, 2),
            "vol_ratio": round(vol_today / avgv, 2) if vol_today and avgv else None}


def _one(sym: str) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from watch import _chart, analyze
    d = _chart(sym, "3mo", "1d")
    q, m = d["indicators"]["quote"][0], d["meta"]
    off = m.get("gmtoffset", 0)
    day = lambda t: datetime.fromtimestamp(t + off, timezone.utc).strftime("%Y-%m-%d")
    sday = day(m.get("regularMarketTime") or 0)
    bars = [{"d": day(t), "o": o, "h": h, "l": l, "c": c, "v": v} for t, o, h, l, c, v in
            zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"]) if c and o]
    past = [b for b in bars if b["d"] < sday]
    i5 = _chart(sym, "1d", "5m")
    q5 = i5["indicators"]["quote"][0]
    opens = [o for o in q5.get("open") or [] if o]
    today = None
    if opens and day(i5["meta"].get("regularMarketTime") or 0) == sday:
        today = {"o": opens[0], "h": max(h for h in q5["high"] if h), "l": min(x for x in q5["low"] if x), "c": m.get("regularMarketPrice")}
    out = analyze(past, today)
    out.update(extra_stats(past, today, m.get("regularMarketVolume") if today else None, [b["v"] or 0 for b in past]))
    out["day"] = sday
    out["at"] = (m.get("regularMarketTime") or 0) * 1000
    out["open"] = bool(today) and datetime.now(timezone.utc).timestamp() - (m.get("regularMarketTime") or 0) < 15 * 60
    return out


def build() -> dict:
    now = datetime.now(timezone.utc).timestamp()
    try:
        c = json.loads(CACHE.read_text(encoding="utf-8"))
        if now - c["t"] < 110:
            return c["v"]
    except Exception:  # noqa: BLE001
        pass
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from market_extra import _hl_ctx
    hl = _hl_ctx()
    items = []
    for sym, code, name, base, bname in ETF:
        row = {"sym": sym, "name": name, "base": bname}
        try:
            row.update(_one(sym))
            b = _one(base)
            row["base_chg"] = b.get("chg")
            row["base_over_ma5"] = b.get("over_ma5")
            if row.get("chg") is not None and b.get("chg") is not None:
                row["x3"] = round(b["chg"] * 3, 2)
                row["x3_gap"] = round(row["chg"] - b["chg"] * 3, 2)
        except Exception as e:  # noqa: BLE001
            row["err"] = type(e).__name__
        from extended import quote as ext_quote
        for k, s in (("ext", sym), ("base_ext", "EWY" if sym == "KORU" else None)):
            if s:
                try:
                    row[k] = ext_quote(s)
                except Exception:  # noqa: BLE001
                    row[k] = None
        x = hl.get(f"xyz:{code}")
        if x and row.get("px"):
            p24 = float(x["markPx"])
            row["h24"] = {"px": round(p24, 2), "vs_reg": round((p24 / row["px"] - 1) * 100, 2)}
        if sym == "KORU":
            k = hl.get("xyz:KR200")
            if k and float(k.get("prevDayPx") or 0):
                row["kr200"] = round((float(k["markPx"]) / float(k["prevDayPx"]) - 1) * 100, 2)
        items.append(row)
    try:                                                     # SOXL 구성 대형주 상승·하락 상위(섹터 모멘텀과 같은 데이터)
        us = json.loads((ROOT / "tools" / "leadership_us.json").read_text(encoding="utf-8"))["rows"]
        rs = sorted(({"name": r["name"], "chg": r["chg"]} for r in us), key=lambda r: -r["chg"])
        items[0]["members"] = {"up": rs[:3], "down": rs[-3:][::-1], "n": len(rs), "n_up": sum(1 for r in rs if r["chg"] > 0)}
    except Exception:  # noqa: BLE001
        pass
    v = {"at": int(now * 1000), "items": items}
    try:
        CACHE.write_text(json.dumps({"t": now, "v": v}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return v


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    CACHE.unlink(missing_ok=True)
    print(json.dumps(build(), ensure_ascii=False, indent=1))
