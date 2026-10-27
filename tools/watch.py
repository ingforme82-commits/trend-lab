"""👀 운영자 관전 포인트 — data/watch.json 의 종목을 장중 1분마다 수치로 추적한다(live_news.py → news.json watch).

- 운영자 메모(memo)는 운영자가 쓴 그대로 '운영자'로 표시. 자동 화면은 수치·사실만(해석·추천 없음)
- 계산(미국 정규장 기준, 야후):
  · 갭: 오늘 시가(5분봉 첫 봉) vs 전일 종가·전일 고가
  · 5일선: 전일까지 4일 종가 + 오늘 현재가의 평균(시가 때는 전일까지 5일 평균과 비교)
  · 연속 양봉: 종가 > 시가 이면서 종가가 전일보다 높은 날이 며칠째인지(오늘 포함). 3일째면 '적삼병 조건 충족(진행 중/마감)'
  · 가격대(level): 현재가와의 거리, 최근 10거래일 중 그 가격대까지 올랐다가 아래에서 마감한 날
- 07:20 정시 브리핑에 마감 결과가 함께 기록된다.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "watch.json"
KST = timezone(timedelta(hours=9))


def _chart(sym: str, rng: str, iv: str) -> dict:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={iv}"
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=12).read())["chart"]["result"][0]


def _days(r: dict) -> list[dict]:
    q, off = r["indicators"]["quote"][0], r["meta"].get("gmtoffset", 0)
    out = []
    for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]):
        if c and o:
            out.append({"d": datetime.fromtimestamp(t + off, timezone.utc).strftime("%Y-%m-%d"), "o": o, "h": h, "l": l, "c": c})
    return out


# ── 순수 함수(tests/test_watch.py) ──
def analyze(past: list[dict], today: dict | None, level: float | None = None) -> dict:
    """past: 전일까지 일봉(오래된 순), today: {o,h,l,c} 오늘 정규장(없으면 None = 개장 전)."""
    p = past[-1]
    ma5_prev = sum(x["c"] for x in past[-5:]) / min(5, len(past))
    out = {"prev": round(p["c"], 2), "prev_h": round(p["h"], 2), "ma5_prev": round(ma5_prev, 2)}
    # 전일까지 연속 양봉(종가>시가, 종가 상승)
    streak = 0
    for i in range(len(past) - 1, 0, -1):
        if past[i]["c"] > past[i]["o"] and past[i]["c"] > past[i - 1]["c"]:
            streak += 1
        else:
            break
    out["streak_prev"] = streak
    if today:
        px = today["c"]
        ma5 = (sum(x["c"] for x in past[-4:]) + px) / (min(4, len(past)) + 1)
        bull = px > today["o"] and px > p["c"]
        out.update(px=round(px, 2), o=round(today["o"], 2), h=round(today["h"], 2), l=round(today["l"], 2),
                   chg=round((px / p["c"] - 1) * 100, 2), gap=round((today["o"] / p["c"] - 1) * 100, 2),
                   gap_over_high=today["o"] > p["h"], open_over_ma5=today["o"] > ma5_prev,
                   ma5=round(ma5, 2), over_ma5=px > ma5, vs_ma5=round((px / ma5 - 1) * 100, 2),
                   bull=bull, streak=streak + 1 if bull else 0, three=bull and streak >= 2)
    if level:
        ref = out.get("px", p["c"])
        out["level"] = level
        out["to_level"] = round((level / ref - 1) * 100, 2)
        out["level_hits"] = [{"d": x["d"], "h": round(x["h"], 2), "c": round(x["c"], 2)}      # 그 가격대까지 올랐다가 아래에서 마감한 날
                             for x in past[-10:] if x["h"] >= level * 0.995 and x["c"] < level]
        if today:
            out["level_touched"] = today["h"] >= level
    return out


def build(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    try:
        cfg = json.loads(CFG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    kday = now.astimezone(KST)
    items = []
    for w in cfg.get("items", []):
        # 관전일(한국 날짜) 당일 저녁 ~ 다음 날 낮 12시까지만 보여 준다
        start = datetime.fromisoformat(w["date"]).replace(tzinfo=KST)
        if not (start <= kday < start + timedelta(hours=36)):
            continue
        row = {"sym": w["sym"], "name": w.get("name", w["sym"]), "focus": w.get("focus", [])}
        try:
            d = _days(_chart(w["sym"], "1mo", "1d"))
            i5 = _chart(w["sym"], "1d", "5m")
            m = i5["meta"]
            q = i5["indicators"]["quote"][0]
            ts = i5.get("timestamp") or []
            off = m.get("gmtoffset", 0)
            tday = datetime.fromtimestamp((m.get("regularMarketTime") or 0) + off, timezone.utc).strftime("%Y-%m-%d")
            opens = [o for o in q.get("open") or [] if o]
            today = None
            if ts and opens:
                hs = [h for h in q.get("high") or [] if h]
                ls = [x for x in q.get("low") or [] if x]
                today = {"o": opens[0], "h": max(hs), "l": min(ls), "c": m.get("regularMarketPrice")}
            past = [x for x in d if x["d"] < tday] if today else d
            row.update(analyze(past, today, w.get("level")))
            row["day"] = tday
            row["at"] = (m.get("regularMarketTime") or 0) * 1000
            row["open"] = bool(today) and (now.timestamp() - (m.get("regularMarketTime") or 0) < 15 * 60)
        except Exception as e:  # noqa: BLE001
            row["err"] = type(e).__name__
        items.append(row)
    if not items:
        return {}
    return {"date": cfg.get("date", ""), "title": cfg.get("title", ""), "memo": cfg.get("memo", ""),
            "items": items, "at": int(now.timestamp() * 1000)}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(build(), ensure_ascii=False, indent=1))
