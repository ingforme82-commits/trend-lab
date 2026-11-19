"""확장 세션 표시용 캔들. 정규장 주문 판정·기록을 덮어쓰지 않는다.

국내 오늘 OHLC는 네이버 integratedPriceInfo(KRX+NXT), 과거는 기존 일봉.
미국 오늘 OHLC는 Yahoo includePrePost=true 1분봉(미국 동부 날짜·DST). 11/18 운영자 "미국 시간외·한국장 변화 1분마다" → 5분봉에서 1분봉으로.
원천 제공 시각/봉 시작 시각과 조회 시각을 분리한다. 합성상품은 사용하지 않는다.
"""
from __future__ import annotations

import json
import math
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0"}
MAX_AGE = {"kr": 180, "us": 180}


def number(value):
    try:
        n = float(str(value).replace(",", ""))
        return n if math.isfinite(n) and n > 0 else None
    except (TypeError, ValueError):
        return None


def ohlc(values):
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        return None
    values = [number(v) for v in values]
    if any(v is None for v in values):
        return None
    o, h, l, c = values
    return values if l <= min(o, c) <= max(o, c) <= h else None


def parse_kr(data, now):
    """시가·고가·저가 없는 최근가로 가짜 캔들을 만들지 않는다."""
    out = {}
    local = now.astimezone(KST)
    for row in data.get("datas") or []:
        code = row.get("itemCode")
        if not isinstance(code, str) or len(code) != 6:
            continue
        over = row.get("overMarketPriceInfo") or {}
        # provider session wins over hard-coded schedules (e.g. delayed opening).
        use_over = over.get("tradingSessionType") in ("PRE_MARKET", "AFTER_MARKET") and bool(over.get("localTradedAt")) and (over.get("overMarketStatus") == "OPEN" or row.get("marketStatus") != "OPEN")
        current = over if use_over else row
        stamp = current.get("localTradedAt")
        try:
            at = datetime.fromisoformat(stamp)
            if at.tzinfo is None:
                continue
            at = at.astimezone(KST)
        except (TypeError, ValueError):
            continue
        if at.date() != local.date() or at.timestamp() > now.timestamp() + 120:
            continue
        integrated = row.get("integratedPriceInfo") or {}
        close = current.get("overPriceRaw") or current.get("overPrice") if use_over else row.get("closePriceRaw") or row.get("closePrice")
        values = ohlc([integrated.get(k + "Raw") or integrated.get(k) for k in ("openPrice", "highPrice", "lowPrice")] + [close])
        if not values:
            continue
        status = current.get("overMarketStatus") if use_over else row.get("marketStatus")
        session = {"PRE_MARKET": "NXT 프리", "AFTER_MARKET": "NXT 애프터"}.get(current.get("tradingSessionType"), "정규장")
        out[code] = {"day": at.date().isoformat(), "ohlc": values, "source_at": int(at.timestamp() * 1000),
                     "checked_at": int(now.timestamp() * 1000), "source": "네이버 KRX+NXT 통합",
                     "session": session, "provider_open": status == "OPEN",
                     "time_kind": "제공 시각", "max_age_seconds": MAX_AGE["kr"],
                     "history_note": "과거는 정규장 일봉 · 오늘은 KRX+NXT 통합 OHLC",
                     "scope": "KRX+NXT", "country": "kr"}
    return out


def parse_us(result, now):
    """검증된 동일 미국 거래일의 04~20시 1분봉을 시간순으로 합친다."""
    ts = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    data = []
    for i, stamp in enumerate(ts):
        try:
            stamp = float(stamp)
            if not math.isfinite(stamp) or stamp > now.timestamp() + 120:
                continue
            dt = datetime.fromtimestamp(stamp, NY)
            if dt.weekday() >= 5 or not (240 <= dt.hour * 60 + dt.minute < 1200):
                continue
            values = ohlc([quote[k][i] for k in ("open", "high", "low", "close")])
            if values:
                data.append((stamp, dt, values))
        except (KeyError, IndexError, TypeError, ValueError, OverflowError, OSError):
            continue
    if not data:
        return None
    data.sort(key=lambda r: r[0])
    day = data[-1][1].date()
    today = [r for r in data if r[1].date() == day]
    first, last = today[0], today[-1]
    history = []
    for trading_day in sorted({r[1].date() for r in data}):
        group = [r for r in data if r[1].date() == trading_day]
        history.append({"day": trading_day.isoformat(), "ohlc": [group[0][2][0], max(r[2][1] for r in group),
                       min(r[2][2] for r in group), group[-1][2][3]]})
    values = [first[2][0], max(r[2][1] for r in today), min(r[2][2] for r in today), last[2][3]]
    periods = (result.get("meta") or {}).get("currentTradingPeriod") or {}
    active = None
    for key, name in (("pre", "프리마켓"), ("regular", "정규장"), ("post", "애프터마켓")):
        p = periods.get(key) or {}
        if p.get("start", 0) <= now.timestamp() < p.get("end", 0):
            active = name
    minute = last[1].hour * 60 + last[1].minute
    last_session = "프리마켓" if minute < 570 else "정규장" if minute < 960 else "애프터마켓"
    for key, name in (("pre", "프리마켓"), ("regular", "정규장"), ("post", "애프터마켓")):
        p = periods.get(key) or {}
        if p.get("start", 0) <= last[0] < p.get("end", 0):
            last_session = name
    # In a new session, an earlier-session last bar is not a live quote.
    is_open = active == last_session and day == now.astimezone(NY).date()
    return {"day": day.isoformat(), "ohlc": values, "source_at": int(last[0] * 1000),
            "checked_at": int(now.timestamp() * 1000), "source": "Yahoo 확장세션 1분봉",
            "session": last_session, "provider_open": is_open, "time_kind": "1분봉 시작",
            "max_age_seconds": MAX_AGE["us"], "history_note": "과거는 정규장 일봉 · 오늘은 프리+정규+애프터",
            "scope": "미국 확장세션", "country": "us", "active_session": active, "history": history}


def _request(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read(5_000_000))


def apply_cme_live(quotes, errors, live=None):
    """11/20: 야후 CME 선물(NQ=F·ES=F) 1분봉은 약 10분 늦어 '자료 확인 중'이 됐다 → NH 실시간 현재가로 오늘 봉 종가·고가·저가와 제공 시각을 바꾼다.
    NH가 없으면 야후 값 그대로(지연 표시 유지)."""
    if live is None:
        try:
            from nhfut import cme_live as live
        except Exception:  # noqa: BLE001
            return
    for code, quote in quotes.items():
        try:
            o, h, l, c = quote["ohlc"]
            q = live(code, ref=c)
        except Exception:  # noqa: BLE001
            q = None
        if not q:
            if code in ("NQ=F", "ES=F"):
                errors.append(f"{code} NH 실시간 없음 — 야후(약 10분 지연)")
            continue
        quote["ohlc"] = [o, max(h, q["px"]), min(l, q["px"]), q["px"]]
        quote["source_at"] = q["at"]
        quote["source"] = f"{q['src']}({q.get('code') or ''}) · 봉은 Yahoo 1분봉"
        quote["time_kind"] = "증권사 조회 시각"


def collect(groups, now, cache_path: Path):
    """새 확장 경로가 실패해도 정규장 차트·주문 판정은 계속된다."""
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    tasks = []
    kr = [code for g in groups if g["cc"] == "kr" for code, _ in g["items"]]
    if kr:
        tasks.append(("kr", "https://polling.finance.naver.com/api/realtime/domestic/stock/" + ",".join(kr)))
    for g in groups:
        if g["cc"] == "us":
            for code, _ in g["items"]:
                symbol = urllib.request.quote(code, safe="")
                tasks.append((code, f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=7d&interval=1m&includePrePost=true"))
    def one(task):
        key, url = task
        cached = cache.get(key) or {}
        if 0 <= time.time() - cached.get("t", 0) < 55:
            return key, cached.get("raw"), None, cached["t"]
        try:
            return key, _request(url), None, time.time()
        except Exception as exc:  # no URLs/keys or server error body
            return key, None, type(exc).__name__, time.time()
    quotes, errors = {}, []
    archive = cache.get("_history") or {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(one, tasks))
    for key, raw, error, fetched_at in responses:
        if error:
            errors.append(f"{key} 확장세션 {error}")
            continue
        try:
            if key == "kr":
                parsed = parse_kr(raw, now)
                for item in parsed.values():
                    item["checked_at"] = int(fetched_at * 1000)
                quotes.update(parsed)
            else:
                quote = parse_us(raw["chart"]["result"][0], now)
                if quote:
                    quote["checked_at"] = int(fetched_at * 1000)
                    quotes[key] = quote
            cache[key] = {"t": fetched_at, "raw": raw}
        except (KeyError, TypeError, IndexError, ValueError):
            errors.append(f"{key} 확장세션 형식 확인")
    apply_cme_live(quotes, errors)
    for code, quote in quotes.items():
        saved = archive.get(code) or {}
        for entry in quote.get("history") or []:
            if ohlc(entry.get("ohlc")) and entry["day"] <= quote["day"]:
                saved[entry["day"]] = entry["ohlc"]
        saved[quote["day"]] = quote["ohlc"]
        saved = dict(sorted(saved.items())[-90:])
        archive[code] = saved
        quote["history"] = [{"day": day, "ohlc": value} for day, value in sorted(saved.items())]
    cache["_history"] = archive
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(cache_path)
    except OSError:
        pass
    return quotes, errors


def display(rows, quote, anchors, rules, *, now, channel, candle, state):
    """정규장 데이터는 보존하고 화면용 projection만 반환. signals 대상 아님."""
    from copy import deepcopy
    values = ohlc(quote.get("ohlc") or [])
    if not values or len(rows) < 6:
        return None
    target = datetime.fromisoformat(quote["day"]).date()
    md = target.strftime("%m/%d")
    zone = KST if quote["country"] == "kr" else NY
    local_day = now.astimezone(zone).date()
    recent = datetime.strptime(f"{local_day.year}/{rows[-1][0]}", "%Y/%m/%d").date()
    if recent > local_day + timedelta(days=30):
        recent = recent.replace(year=recent.year - 1)
    if target < recent or target > local_day:
        return None
    merged = deepcopy(rows)
    # 확보한 통합/확장 봉은 과거 날짜도 유지한다. 미수집 구간을 가짜 통합봉으로 만들지 않는다.
    history = {entry["day"]: ohlc(entry.get("ohlc")) for entry in quote.get("history") or []
               if isinstance(entry, dict) and isinstance(entry.get("day"), str)}
    for row in merged:
        year = local_day.year - (1 if row[0] > local_day.strftime("%m/%d") else 0)
        day_key = f"{year}/{row[0]}".replace("/", "-")
        if history.get(day_key) and day_key < quote["day"]:
            row[1:5] = history[day_key]
    bar = [md] + values
    if merged[-1][0] == md:
        merged[-1] = bar
    else:
        merged.append(bar)
    merged = merged[-45:]
    ch = channel(merged, anchors, rules)
    if not ch:
        return None
    age = (now.timestamp() * 1000 - quote["source_at"]) / 1000
    fresh = -120 <= age <= quote["max_age_seconds"]
    live = quote["provider_open"] and fresh
    stale = bool(quote["provider_open"] and not fresh)
    phase_mismatch = quote.get("active_session") and quote["active_session"] != quote["session"]
    stale = stale or bool(phase_mismatch)
    # 등락률 기준은 통합 과거봉이 아니라 원본 정규장 종가다.
    same_day = rows[-1][0] == md
    pre = "프리" in quote["session"]
    regular_session = quote["session"] == "정규장"
    base_row = rows[-2] if same_day and (pre or regular_session) else rows[-1]
    px, prev = values[3], base_row[4]
    if not number(prev):
        return None
    st = state(ch, px, True)  # never confirm a regular-close breakout from extended prices
    if quote["session"] != "정규장" or not live:
        st = st.replace("(장중)", "(세션 참고)")
    return {**ch, "rows": merged, "integrated_history_days": len([v for v in history.values() if v]), "day": md, "px": px, "chg": round((px / prev - 1) * 100, 2),
            "ma5": ch["ma5"], "above_ma5": px > ch["ma5"],
            "base": prev, "base_day": base_row[0], "change": round(px - prev, 4),
            "change_basis": "전일 정규장 종가" if regular_session else "정규장 종가",
            "gap_low": round((ch["lo_now"] / px - 1) * 100, 2),
            "candle": candle(*values, prev), "state": "자료 확인 중" if stale else st,
            "live": live, "stale": stale, "session": quote["session"], "source": quote["source"],
            "source_at": quote["source_at"], "checked_at": quote["checked_at"],
            "time_kind": quote["time_kind"], "history_note": quote["history_note"],
            "scope": quote["scope"], "reference_only": True, "signal_eligible": False,
            "quality_note": "지연·세션 확인 필요" if stale else "진행 중" if live else "마감·마지막 제공값"}
