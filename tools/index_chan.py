"""코스피·코스닥 전용 일봉/현재봉. 주식 조회·주문 경로와 분리한다."""
from __future__ import annotations

import json
import math
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic

INDEXES = {"KOSPI": ("0001", "^KS11"), "KOSDAQ": ("1001", "^KQ11")}
NAVER_INDEX_CODES = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ"}
UA = {"User-Agent": "Mozilla/5.0"}
MAX_LIVE_AGE = 180
LIVE_DIAGNOSTICS: dict[str, str] = {}


def _ohlc(values) -> list[float] | None:
    try:
        o, h, l, c = [float(str(v).replace(",", "")) for v in values]
    except (ValueError, TypeError):
        return None
    if not all(math.isfinite(v) and v > 0 for v in (o, h, l, c)):
        return None
    if l > min(o, c) or h < max(o, c) or h < l:
        return None
    return [o, h, l, c]


def parse_history(data: dict, now: datetime) -> list[list]:
    rows = {}
    for item in data.get("output2") or []:
        day = str(item.get("stck_bsop_date") or "")
        try:
            date = datetime.strptime(day, "%Y%m%d").date()
        except ValueError:
            continue
        values = _ohlc(item.get(k) for k in ("bstp_nmix_oprc", "bstp_nmix_hgpr", "bstp_nmix_lwpr", "bstp_nmix_prpr"))
        if values and date <= now.date():
            rows[day] = [date.strftime("%m/%d"), *values]
    return [rows[k] for k in sorted(rows)]


def parse_quote(item: dict, code: str, now: datetime) -> dict | None:
    if item.get("itemCode") != code:
        return None
    try:
        source = datetime.fromisoformat(item.get("localTradedAt") or "")
        if source.tzinfo is None:
            return None
        source = source.astimezone(now.tzinfo)
    except (TypeError, ValueError):
        return None
    age = (now - source).total_seconds()
    if age < -5 or age > 7 * 86400:
        return None
    values = _ohlc(item.get(k + "Raw") or item.get(k) for k in ("openPrice", "highPrice", "lowPrice", "closePrice"))
    if not values:
        return None
    market_status = str(item.get("marketStatus") or "missing")
    market_open = market_status == "OPEN"
    # 시장 제공 상태를 사용해 수능일 등 시각 변경·휴장 때 정규시간만으로 열림을 추정하지 않는다.
    live = market_open and source.date() == now.date() and 0 <= age <= MAX_LIVE_AGE
    return {"row": [source.strftime("%m/%d"), *values], "source_at": int(source.timestamp() * 1000),
            "source_day": source.date().isoformat(), "source": "네이버 지수", "market_open": market_open,
            "provider_market_status": market_status, "age_seconds": round(age),
            "live": live, "stale": market_open and not live,
            "quality_note": "장중 제공 지수" if live else "제공 지수 지연·실시간 판단 보류" if market_open else "장 종료·마지막 제공 지수"}


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def parse_naver(data: list, now: datetime, *, include_today: bool = False) -> list[list]:
    rows = {}
    for item in data or []:
        day = str(item.get("localDate") or "")
        try:
            date = datetime.strptime(day, "%Y%m%d").date()
        except ValueError:
            continue
        values = _ohlc(item.get(k) for k in ("openPrice", "highPrice", "lowPrice", "closePrice"))
        if values and (date < now.date() or (include_today and date == now.date())):
            rows[day] = [date.strftime("%m/%d"), *values]
    return [rows[k] for k in sorted(rows)]


def _naver_history(code: str, now: datetime, days: int = 150, *, include_today: bool = False) -> list[list]:
    u = (f"https://api.stock.naver.com/chart/domestic/index/{code}/day?startDateTime={(now - timedelta(days=days)).strftime('%Y%m%d')}"
         f"&endDateTime={now.strftime('%Y%m%d')}")
    return parse_naver(json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=8).read()),
                       now, include_today=include_today)


def fill_gaps(rows: list[list], recent: list[list]) -> list[list]:
    """11/20: 야후 지수 일봉에 11/19 가 빠져 전일·5일선이 하루 밀렸다 → 최근 네이버 일봉으로 빠진 날을 채운다(같은 날은 그대로)."""
    have = {r[0] for r in rows}
    first = rows[0][0] if rows else ""
    add = [r for r in recent if r[0] not in have and r[0] >= first[:5]] if rows else list(recent)
    if not add:
        return rows
    def key(r):                                              # 연말·연초 넘어갈 때 순서 유지
        return ("1" if rows and r[0] < rows[0][0] and r[0].startswith("01/") else "0") + r[0]
    return sorted(rows + add, key=key)


def _history(code: str, now: datetime, yahoo) -> tuple[list[list], str]:
    try:
        import kis
        data = kis.get("/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice", "FHKUP03500100",
                       {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": INDEXES[code][0],
                        "FID_INPUT_DATE_1": (now - timedelta(days=150)).strftime("%Y%m%d"),
                        "FID_INPUT_DATE_2": now.strftime("%Y%m%d"), "FID_PERIOD_DIV_CODE": "D"})
        rows = parse_history(data, now)
        if len(rows) >= 20:
            return rows, "한국투자증권 지수 일봉"
    except Exception:  # noqa: BLE001
        pass
    try:                                                     # 11/20: 서버에서 한투가 막히면 네이버 지수 일봉(KRX 공식 종가)
        rows = _naver_history(code, now)
        if len(rows) >= 20:
            return rows, "네이버 지수 일봉"
    except Exception:  # noqa: BLE001
        pass
    rows = yahoo(INDEXES[code][1], "6mo", "1d")
    rows = [r for r in rows if len(r) == 5 and _ohlc(r[1:])]
    if len(rows) < 20:
        raise ValueError("Insufficient index history")
    try:
        rows = fill_gaps(rows, _naver_history(code, now, 20))
    except Exception:  # noqa: BLE001
        pass
    return rows, "야후 지수 일봉(빠진 날 네이버로 보충)"


def _quote(code: str, now: datetime) -> dict | None:
    started = monotonic()
    naver_code = NAVER_INDEX_CODES.get(code)
    if not naver_code:
        return None
    request = urllib.request.Request(f"https://polling.finance.naver.com/api/realtime/domestic/index/{naver_code}", headers=UA)
    data = json.loads(urllib.request.urlopen(request, timeout=8).read())
    now += timedelta(seconds=monotonic() - started)
    return next((q for item in data.get("datas", []) if (q := parse_quote(item, code, now))), None)



def _kis_quote(code: str, now: datetime) -> dict | None:
    from kis import get

    started = monotonic()
    data = get(
        "/uapi/domestic-stock/v1/quotations/inquire-time-indexchartprice",
        "FHKUP03500200",
        {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_ETC_CLS_CODE": "0",
            "FID_INPUT_ISCD": INDEXES[code][0],
            "FID_INPUT_HOUR_1": "60",
            "FID_PW_DATA_INCU_YN": "N",
        },
    )
    now += timedelta(seconds=monotonic() - started)
    header = data.get("output1") or {}
    if isinstance(header, list):
        header = header[0] if header else {}
    if not isinstance(header, dict):
        return None

    minutes = []
    for row in data.get("output2") or []:
        try:
            stamp = datetime.strptime(
                row["stck_bsop_date"] + row["stck_cntg_hour"], "%Y%m%d%H%M%S"
            ).replace(tzinfo=now.tzinfo)
        except (KeyError, TypeError, ValueError):
            continue
        if stamp.date() == now.date() and 0 <= (now - stamp).total_seconds() <= MAX_LIVE_AGE:
            minutes.append((stamp, row))
    if not minutes:
        return None

    stamp, minute = max(minutes, key=lambda pair: pair[0])
    values = _ohlc([
        header.get("bstp_nmix_oprc"), header.get("bstp_nmix_hgpr"),
        header.get("bstp_nmix_lwpr"), minute.get("bstp_nmix_prpr"),
    ])
    if not values:
        return None
    return {
        "row": [stamp.strftime("%m/%d"), *values],
        "source_at": int(stamp.timestamp() * 1000),
        "source": "한투 지수 1분봉",
        "market_open": True,
    }


def _current_quote(code: str, now: datetime) -> dict | None:
    started = monotonic()
    diagnostics = []
    try:
        quote = _quote(code, now)
    except Exception as exc:  # noqa: BLE001
        quote = None
        diagnostics.append(f"Naver {type(exc).__name__}")
    minutes = now.hour * 60 + now.minute
    if now.weekday() >= 5 or not 540 <= minutes < 930:
        LIVE_DIAGNOSTICS[code] = "정규장 외"
        return quote
    if quote and quote.get("live"):
        LIVE_DIAGNOSTICS[code] = "Naver 현재 지수"
        return quote
    diagnostics.append("Naver 현재 시세 없음" if quote is None else f"Naver marketStatus={quote.get('provider_market_status', 'missing')} age={quote.get('age_seconds', '?')}s")
    try:
        kis_quote = _kis_quote(code, now + timedelta(seconds=monotonic() - started))
        if kis_quote:
            LIVE_DIAGNOSTICS[code] = "한투 1분 지수"
            return kis_quote
        diagnostics.append("한투 신선한 1분봉 없음")
    except Exception as exc:  # noqa: BLE001
        diagnostics.append(f"한투 {type(exc).__name__}")
    LIVE_DIAGNOSTICS[code] = " · ".join(diagnostics)
    return quote


def bars(code: str, now: datetime, *, daily_path: Path, live_path: Path, yahoo) -> tuple[list[list], bool, dict]:
    if code not in INDEXES:
        raise ValueError("Unknown index")
    started = monotonic()
    today = now.date().isoformat()
    daily = _read(daily_path)
    entry = daily.get(code) or {}
    warning = ""
    if entry.get("day") != today or not entry.get("rows") or entry.get("source") == "야후 지수 일봉":   # 11/20: 빠진 날 있던 옛 캐시는 다시
        try:
            rows, source = _history(code, now, yahoo)
            if rows:
                entry = {"day": today, "rows": rows[-90:], "source": source}
                daily[code] = entry
                _save(daily_path, daily)
        except Exception:  # noqa: BLE001
            warning = "일봉 갱신 실패·기존 자료"
    rows = [list(r) for r in entry.get("rows") or []]
    meta = {"instrument_type": "index", "unit": "pt", "daily_source": entry.get("source", "미확인"),
            "source": entry.get("source", "미확인"), "source_at": None, "stale": True,
            "checked_at": int(now.timestamp() * 1000), "quality_note": warning or "현재봉 제공 시각 미확인·일봉 기준"}
    live_cache = _read(live_path)
    cached = live_cache.get(code) or {}
    quote = cached.get("quote")
    observed_at = now + timedelta(seconds=monotonic() - started)
    if not (quote and 0 <= now.timestamp() - cached.get("t", 0) < 55):
        try:
            quote = _current_quote(code, observed_at)
            live_cache[code] = {"t": (now + timedelta(seconds=monotonic() - started)).timestamp(), "quote": quote}
            _save(live_path, live_cache)
        except Exception:  # noqa: BLE001
            quote = None  # 실패한 현재 조회를 이전 봉으로 대체해 실시간이라고 표시하지 않는다.
    now += timedelta(seconds=monotonic() - started)
    meta["checked_at"] = int(now.timestamp() * 1000)
    active = False
    if quote:
        source = datetime.fromtimestamp(quote["source_at"] / 1000, now.tzinfo)
        age = (now - source).total_seconds()
        row = quote["row"]
        # 캐시된 OPEN 상태도 현재 기준으로 재검증한다.
        active = bool(quote["market_open"] and source.date() == now.date() and 0 <= age <= MAX_LIVE_AGE)
        if not rows or rows[-1][0] == row[0]:
            rows = rows[:-1] + [row] if rows else [row]
        elif row[0] > rows[-1][0] or (rows[-1][0].startswith("12/") and row[0].startswith("01/")):
            rows.append(row)
        else:
            active = False
        meta.update(source=quote["source"], source_at=quote["source_at"],
                    stale=bool(quote["market_open"] and not active),
                    quality_note="장중 제공 지수" if active else "제공 지수 지연·실시간 판단 보류" if quote["market_open"] else "장 종료·마지막 제공 지수")
    today_label = now.strftime("%m/%d")
    if not quote or quote["row"][0] != today_label:
        if now.weekday() < 5 and 540 <= now.hour * 60 + now.minute < 930:
            meta["stale"] = True
        try:
            recent = _naver_history(code, now, 0, include_today=True)
        except (OSError, ValueError, TypeError):
            recent = []
        if recent and recent[-1][0] == today_label:
            if rows and rows[-1][0] == today_label:
                rows[-1] = recent[-1]
            else:
                rows.append(recent[-1])
            meta.update(source="네이버 지수 일봉", source_at=None, stale=True,
                        quality_note="당일 일봉·제공 시각 미확인")
    if warning:
        meta["quality_note"] += " · " + warning
    if not active and meta.get("stale"):
        meta["live_diagnostic"] = LIVE_DIAGNOSTICS.get(code, "현재 지수 원천 확인 중")
    return rows[-45:], active, meta
