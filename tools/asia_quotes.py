"""Publish Taiwanese and Japanese index snapshots independently of live news."""
import base64
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from chan import CONF, NBARS, _yahoo, candle, channel, state
from market_extra import _taiex, _yf, taiex_daily, taiex_intraday
from nh_quotes import REPO, gh


def trend(row, bars, config, live, source):
    if len(bars) < 20:
        return
    bars = bars[-NBARS:]
    result = channel(bars, config["anchors"], config.get("contact_rules"), last_closed=not live)
    if result is None:
        return
    day, o, h, l, px = bars[-1]
    prev = bars[-2][4]
    row["trend"] = {
        **result, "code": row["sym"], "name": row["name"], "day": day, "live": live,
        "px": px, "chg": round((px / prev - 1) * 100, 2), "base": prev,
        "candle": candle(o, h, l, px, prev), "state": state(result, px, live),
        "rows": bars, "source": source, "source_at": row["at"],
    }


def add_japan_trend(row, config=None):
    try:
        if config is None:
            config = json.loads(CONF.read_text(encoding="utf-8"))
        bars = _yahoo("^N225", "3mo", "1d")
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return
    tokyo = ZoneInfo("Asia/Tokyo")
    now = datetime.now(tokyo)
    traded = datetime.fromtimestamp(row["at"] / 1000, tokyo)
    if not bars or bars[-1][0] != traded.strftime("%m/%d"):
        return
    day, opening, high, low, _ = bars[-1]
    # The two Yahoo requests can return snapshots from different times.
    # Use the already collected quote for the latest candle and card.
    px = row["px"]
    bars[-1] = [day, opening, max(high, px), min(low, row.get("low", px)), px]
    live = traded.date() == now.date() and traded.hour * 100 + traded.minute < 1530
    trend(row, bars, config, live, "Yahoo 일봉")
    if "trend" in row:
        row["trend"]["chg"] = row["chg"]


def taiwan_row(config=None):
    if config is None:
        config = json.loads(CONF.read_text(encoding="utf-8"))
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    daily = taiex_daily(now, months=4, minimum=NBARS)
    closed = _taiex(daily)
    live = taiex_intraday(now)
    quote = live if live and (not closed or live["at"] > closed["at"]) else closed
    if not quote:
        return None
    row = {**quote, "sym": "TAIEX", "name": "가권지수", "region": "대만"}
    bars = [[at.strftime("%m/%d"), *ohlc] for at, ohlc in daily]
    if quote is live:
        # Draw a live candle only if its official previous close matches the daily series.
        if bars and abs(bars[-1][4] - live["prev"]) < 0.01:
            bars.append([now.strftime("%m/%d"), live["open"], live["high"], live["low"], live["px"]])
            trend(row, bars, config, True, "TWSE 장중 지수")
    else:
        trend(row, bars, config, False, "대만증권거래소 공식 일봉")
    return row


def collect():
    config = json.loads(CONF.read_text(encoding="utf-8"))
    taiwan = taiwan_row(config)
    japan = _yf("^N225")
    rows = [taiwan] if taiwan else []
    if japan and japan["px"] and japan["prev"]:
        px, low = japan["px"], japan.get("low")
        row = {"sym": "^N225", "name": "니케이225", "region": "일본", "px": px,
               "at": japan["at"], "chg": round((px / japan["prev"] - 1) * 100, 2)}
        if low and 0 < low <= px:
            row.update(low=low, rebound=round((px / low - 1) * 100, 2))
        add_japan_trend(row, config)
        rows.append(row)
    return rows


def main():
    rows = collect()
    if not rows:
        raise RuntimeError("Asian index sources unavailable")
    endpoint = f"repos/{REPO}/contents/asia-quotes.json"
    try:
        current = gh([endpoint + "?ref=quotes"])
    except RuntimeError:
        current = {}
    previous = json.loads(base64.b64decode(current["content"])) if current else []
    merged = {row["sym"]: row for row in previous}
    for row in rows:
        old = merged.get(row["sym"], {})
        if row["at"] >= old.get("at", 0):
            merged[row["sym"]] = {**old, **row} if row["at"] == old.get("at") else row
    updated = list(merged.values())
    if updated == previous:
        return
    payload = {"branch": "quotes", "message": "Update Asian index quotes",
               "content": base64.b64encode(json.dumps(updated, ensure_ascii=False).encode()).decode()}
    if current:
        payload["sha"] = current["sha"]
    gh(["--method", "PUT", endpoint], payload)


if __name__ == "__main__":
    main()
