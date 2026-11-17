"""📐 추세 판단 — 종목별 하락 채널·5일선·실시간 캔들 모양(운영자 11/17). 사이트 맨 위 '추세 판단' 칸(news.json 'chan').

  python tools/chan.py        # 지금 계산 결과(확인용)

- 설정: data/channels.json (종목 묶음·채널 기준 날짜 구간·판단 기준 문장)
- 일봉: 한국 = 한투 일봉(FHKST03010100, 하루 한 번), 미국·일본 = 야후 일봉 + 최근 5일 시간봉(야후 일봉의 마지막 날 누락 보완)
- 실시간 캔들: 한국 = 한투 현재가(시가·고가·저가·현재가, 09:00 이후), 미국·일본 = 야후 시간봉으로 오늘 봉을 다시 만든다(1분 캐시)
- 상태: 채널 안 / 상단 근접(다음 거래일 상단까지 3% 안) / 채널 위·5일선 아래(돌파 미확인) / 돌파 시도(장중 상단 +1%·5일선 위) /
        돌파 확인(종가 상단 +1%·5일선 위) / 하단 이탈
- 캔들: 장대양봉·장대음봉·망치형(아래꼬리)·윗꼬리·도지·양봉·음봉 — 오늘(진행 중) 봉 기준
- 기록: 상태·눈에 띄는 캔들이 바뀌면 state_dir/chan_log.json 에 쌓고 최근 것을 사이트 '기록'에 보여 준다
사실과 숫자만 계산한다. 매수·매도 권유가 아니다. 키·토큰은 출력하지 않는다.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

KST = timezone(timedelta(hours=9))
CONF = ROOT / "data" / "channels.json"
DAILY = keystore.state_dir() / "chan_daily.json"
LIVE = keystore.state_dir() / "chan_live.json"
LOG = keystore.state_dir() / "chan_log.json"
NBARS = 45
UA = {"User-Agent": "Mozilla/5.0"}
INDEX_META: dict[str, dict] = {}
ERRS: list[str] = []                                   # 이번 계산에서 빠진 종목·대체 경로(사이트 데이터 'errs' 로 보임)


def _n(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


# ── 순수 함수(tests/test_chan.py) ──
def candle(o: float, h: float, l: float, c: float, prev: float) -> dict:
    """오늘 봉 모양. 몸통·꼬리 비율과 전일 대비 크기로 이름을 붙인다."""
    rng = h - l
    if rng <= 0 or not o:
        return {"name": "보합", "kind": "flat"}
    body = abs(c - o); upw = h - max(o, c); low = min(o, c) - l
    big = prev and body / prev >= 0.03
    if low >= 2 * body and low >= 0.6 * rng and upw <= 0.2 * rng:     # 꼬리 판정이 먼저(몸통이 작아도 한쪽 꼬리가 길면 망치·윗꼬리)
        name, kind = "망치형 — 아래꼬리(저가 매수 유입)", "hammer"
    elif upw >= 2 * body and upw >= 0.6 * rng and low <= 0.2 * rng:
        name, kind = "윗꼬리 — 위에서 매도", "shoot"
    elif body / rng <= 0.1:
        name, kind = "도지 — 방향 탐색", "doji"
    elif big and body / rng >= 0.6:
        name, kind = ("장대양봉" if c > o else "장대음봉"), ("bigup" if c > o else "bigdn")
    else:
        name, kind = ("양봉" if c > o else "음봉"), ("up" if c > o else "dn")
    return {"name": name, "kind": kind, "body": round(body / rng * 100), "upw": round(upw / rng * 100), "low": round(low / rng * 100),
            "vs_open": round((c / o - 1) * 100, 2)}


def channel(rows: list[list], anchors: dict, contact_rules: dict | None = None,
            *, last_closed: bool = False) -> dict | None:
    """상·하단 각각 3회 접촉과 경미한 겹침을 검증. 진행 중 봉은 선 학습에서 제외."""
    from channel_fit import fit_recent_side
    rules = contact_rules or {}
    tolerance = float(rules.get("tolerance_pct", 0.75))
    spacing = int(rules.get("min_spacing_bars", 3))
    required = max(3, int(rules.get("min_touches", 3)))
    dates = [r[0] for r in rows]
    high = [r[2] for r in rows]
    low = [r[3] for r in rows]
    last = len(rows) - (1 if last_closed else 2)

    def seed(values, window, choose):
        eligible = [i for i in range(last + 1) if window[0] <= dates[i] <= window[1]]
        return choose(eligible, key=lambda i: values[i]) if eligible else None

    h1, l1 = seed(high, anchors["hi1"], max), seed(low, anchors["lo1"], min)
    if h1 is None or l1 is None:
        return None
    kwargs = dict(tolerance_pct=tolerance, min_spacing=spacing, min_touches=required)
    upper = fit_recent_side(high, dates, h1, anchors["hi2"][0], last, True, **kwargs)
    lower = fit_recent_side(low, dates, l1, anchors["lo2"][0], last, False, **kwargs)
    if not upper or not lower:
        return None
    up = lambda i: upper["slope"] * i + upper["intercept"]
    lo = lambda i: lower["slope"] * i + lower["intercept"]
    n = len(rows) - 1
    px = rows[n][4]
    width_valid = all(up(i) > lo(i) > 0 for i in range(max(upper["start"], lower["start"]), n + 2))
    verified = upper["verified"] and lower["verified"] and width_valid
    closes = [r[4] for r in rows]
    return {"hi": upper["touches"], "lo": lower["touches"],
            "upper_start": upper["start"], "lower_start": lower["start"],
            "su": upper["slope"], "sl": lower["slope"],
            "up_now": up(n), "lo_now": lo(n), "up_next": up(n + 1), "lo_next": lo(n + 1),
            "pos": (px - lo(n)) / (up(n) - lo(n)) * 100 if up(n) > lo(n) else None,
            "ma5": sum(closes[-5:]) / min(5, len(closes)), "gap_next": (up(n + 1) / px - 1) * 100,
            "dd": (px / high[h1] - 1) * 100, "peak": high[h1], "peak_day": dates[h1],
            "upper_touch_count": len(upper["touches"]), "lower_touch_count": len(lower["touches"]),
            "upper_verified": upper["verified"], "lower_verified": lower["verified"],
            "channel_valid": verified, "channel_width_valid": width_valid,
            "touch_tolerance_pct": tolerance, "touch_min_spacing": spacing, "touch_required": required,
            "touch_lookback_bars": len(rows),
            "upper_overlap_pct": upper["max_overlap_pct"], "lower_overlap_pct": lower["max_overlap_pct"]}


def state(ch: dict, px: float, live: bool) -> str:
    if ch.get("channel_width_valid") is False:
        return "채널선 교차·재확인"
    if ch.get("channel_valid") is False:
        return "접촉 검증 대기"
    above = px > ch["up_now"] * 1.01
    if above and px > ch["ma5"]:
        return "돌파 시도(장중)" if live else "돌파 확인"
    if above:
        return "채널 위·5일선 아래"
    if px < ch["lo_now"]:
        return "하단 이탈"
    if ch["gap_next"] <= 3:
        return "상단 근접"
    return "채널 안"


# ── 데이터 ──
def _yahoo(sym: str, rng: str, iv: str) -> list[list]:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range={rng}&interval={iv}"
    j = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=12).read())["chart"]["result"][0]
    q = j["indicators"]["quote"][0]; tz = timezone(timedelta(seconds=j["meta"].get("gmtoffset", 0)))
    days: dict[str, list] = {}
    for t, o, h, l, c in zip(j["timestamp"], q["open"], q["high"], q["low"], q["close"]):
        if None in (o, h, l, c):
            continue
        k = datetime.fromtimestamp(t, tz).strftime("%m/%d")
        x = days.get(k)
        days[k] = [k, o, h, l, c] if not x else [k, x[1], max(x[2], h), min(x[3], l), c]
    return list(days.values())


def _kis_daily(code: str) -> list[list]:
    import kis
    now = datetime.now(KST)
    d = kis.get("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code, "FID_INPUT_DATE_1": (now - timedelta(days=130)).strftime("%Y%m%d"),
                 "FID_INPUT_DATE_2": now.strftime("%Y%m%d"), "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"})
    rows = [[r["stck_bsop_date"][4:6] + "/" + r["stck_bsop_date"][6:8], _n(r["stck_oprc"]), _n(r["stck_hgpr"]), _n(r["stck_lwpr"]), _n(r["stck_clpr"])]
            for r in (d.get("output2") or []) if _n(r.get("stck_clpr"))]
    return rows[::-1]


def _kiwoom_daily(code: str) -> list[list]:
    """키움 주식일봉(ka10081) — 한투 일봉이 안 될 때만. 마지막 날 전일 대비(pred_pre)로 전날 종가를 맞춘다
    (11/17 확인: 키움 일봉 11/13 종가 209,000 vs 거래소 206,000 — 다른 기준이 섞여 있어 전날 종가는 pred_pre 로 보정)."""
    import kiwoom
    j, _ = kiwoom.call("ka10081", "/api/dostk/chart", {"stk_cd": code, "base_dt": datetime.now(KST).strftime("%Y%m%d"), "upd_stkpc_tp": "1"})
    raw = (j.get("stk_dt_pole_chart_qry") or [])[:90]
    rows = [[r["dt"][4:6] + "/" + r["dt"][6:8], abs(_n(r["open_pric"])), abs(_n(r["high_pric"])), abs(_n(r["low_pric"])), abs(_n(r["cur_prc"]))]
            for r in raw if _n(r.get("cur_prc"))][::-1]
    if len(rows) >= 2 and raw and _n(raw[0].get("pred_pre")):
        rows[-2][4] = rows[-1][4] - _n(raw[0]["pred_pre"])
    return rows


def _naver_daily(code: str) -> list[list]:
    """네이버 일봉(인증 없음) — 한투·키움이 서버에서 안 될 때(11/17)."""
    import re
    u = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=90&requestType=0"
    raw = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=10).read().decode("euc-kr", "replace")
    out = []
    for m in re.finditer(r'data="(\d{8})\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|', raw):
        d, o, h, l, c = m.groups()
        out.append([d[4:6] + "/" + d[6:8], float(o), float(h), float(l), float(c)])
    return out


def _kis_now(code: str) -> list | None:
    import kis
    q = kis.get("/uapi/domestic-stock/v1/quotations/inquire-price", "FHKST01010100", {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}).get("output") or {}
    o, h, l, c = (_n(q.get(k)) for k in ("stck_oprc", "stck_hgpr", "stck_lwpr", "stck_prpr"))
    if o and c:
        return [datetime.now(KST).strftime("%m/%d"), o, h, l, c]
    try:                                                   # 11/17: 서버에서 한투가 안 되면 네이버 실시간(거래소 시가·고가·저가·현재가)
        u = f"https://polling.finance.naver.com/api/realtime/domestic/stock/{code}"
        x = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=8).read())["datas"][0]
        if str(x.get("localTradedAt", ""))[:10] != datetime.now(KST).strftime("%Y-%m-%d"):
            return None                                    # 오늘 체결이 아직 없음(장 전)
        o, h, l, c = (_n(x.get(k)) for k in ("openPriceRaw", "highPriceRaw", "lowPriceRaw", "closePriceRaw"))
        return [datetime.now(KST).strftime("%m/%d"), o, h, l, c] if o and c else None
    except Exception:  # noqa: BLE001
        return None


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(p: Path, d: dict) -> None:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def bars(cc: str, code: str, now: datetime) -> tuple[list[list], bool]:
    """(일봉 + 오늘 봉, 오늘 봉이 진행 중인가)."""
    if cc == "kr_index":
        from index_chan import bars as index_bars
        rows, live, meta = index_bars(code, now, daily_path=DAILY, live_path=LIVE, yahoo=_yahoo)
        INDEX_META[code] = meta
        return rows, live
    today = now.strftime("%Y-%m-%d")
    dc = _load(DAILY)
    e = dc.get(code) or {}
    if e.get("day") != today or not e.get("rows"):              # 일봉 원본은 하루 한 번
        rows = []
        try:
            rows = _kis_daily(code) if cc == "kr" else _yahoo(code, "6mo", "1d")
        except Exception as x:  # noqa: BLE001
            ERRS.append(f"{code} 일봉 {type(x).__name__}")
        if not rows and cc == "kr":                              # 11/17: 서버에서 한투 일봉 실패 → 키움 일봉(ka10081)으로
            ERRS.append(f"{code} 한투 일봉 없음 → 키움")
            try:
                rows = _kiwoom_daily(code)
            except Exception as x:  # noqa: BLE001
                ERRS.append(f"{code} 키움 일봉 {type(x).__name__}")
        if not rows and cc == "kr":
            try:
                rows = _naver_daily(code)
                ERRS.append(f"{code} 네이버 일봉 사용")
            except Exception as x:  # noqa: BLE001
                ERRS.append(f"{code} 네이버 일봉 {type(x).__name__}")
        if not rows:
            rows = e.get("rows") or []
        if rows:
            dc[code] = {"day": today, "rows": rows[-90:]}
            _save(DAILY, dc)
        e = dc.get(code) or {}
    rows = [list(r) for r in e.get("rows") or []]
    lc = _load(LIVE); le = lc.get(code) or {}
    live = None
    if time.time() - le.get("t", 0) < 55:
        live = le.get("bars")
    else:
        try:
            if cc == "kr":
                hm = now.hour * 100 + now.minute
                live = [_kis_now(code)] if now.weekday() < 5 and hm >= 900 else []
                live = [b for b in live if b]
            else:
                live = _yahoo(code, "5d", "60m")[-1:]            # 오늘(마지막 날)만 — 전날은 일봉 종가 그대로
            lc[code] = {"t": time.time(), "bars": live}
            _save(LIVE, lc)
        except Exception:  # noqa: BLE001
            live = le.get("bars") or []
    for b in live or []:                                   # 같은 날짜는 바꾸고, 새 날짜는 붙인다
        if rows and rows[-1][0] == b[0]:
            rows[-1] = b
        elif not rows or b[0] > rows[-1][0] or (rows[-1][0][:2] == "12" and b[0][:2] == "01"):
            rows.append(b)
    in_session = bool(live) and live[-1][0] == rows[-1][0] and _open_now(cc, now)
    return rows[-NBARS:], in_session


def _open_now(cc: str, now: datetime) -> bool:
    if cc == "kr":
        hm = now.hour * 100 + now.minute
        return now.weekday() < 5 and 900 <= hm < 1530
    if cc == "jp":
        hm = now.hour * 100 + now.minute
        return now.weekday() < 5 and 900 <= hm < 1530
    ny = now.astimezone(timezone(timedelta(hours=-5)))       # 뉴욕(겨울, EST)
    m = ny.hour * 60 + ny.minute
    return ny.weekday() < 5 and 570 <= m < 960


def build(now: datetime | None = None) -> dict:
    now = now or datetime.now(KST)
    ERRS.clear()
    INDEX_META.clear()
    c = json.loads(CONF.read_text(encoding="utf-8"))
    groups, events = [], []
    contact_policy = json.dumps(c.get("contact_rules") or {}, sort_keys=True)
    log = _load(LOG); prev = log.get("last", {}) if log.get("contact_policy") == contact_policy else {}; hist = log.get("events", [])
    signals = [s for s in log.get("signals", []) if now.timestamp() * 1000 - s["ts"] < 20 * 3600_000 and s.get("contact_policy") == contact_policy]   # 오늘(20시간 안) 시그널만
    for g in c["groups"]:
        items = []
        for code, name in g["items"]:
            try:
                rows, live = bars(g["cc"], code, now)
            except Exception as x:  # noqa: BLE001
                ERRS.append(f"{code} 시세 {type(x).__name__}"); continue
            if len(rows) < 20:
                ERRS.append(f"{code} 일봉 {len(rows)}개뿐"); continue
            ch = channel(rows, c["anchors"], c.get("contact_rules"), last_closed=not live)
            if not ch:
                ERRS.append(f"{code} 채널 기준점 없음"); continue
            o, h, l, px = rows[-1][1:5]
            pc = rows[-2][4]
            cd = candle(o, h, l, px, pc)
            st = state(ch, px, live)
            if g["cc"] == "kr_index" and INDEX_META.get(code, {}).get("stale"):
                st = "자료 확인 중"
            was0 = (prev.get(code) or {}).get("state")       # 11/17: 3% 경계에서 오락가락(채널 안↔상단 근접) 막기 — 나갈 때는 3.5%
            if was0 == "상단 근접" and st == "채널 안" and ch["gap_next"] <= 3.5:
                st = "상단 근접"
            it = {"code": code, "name": name, "day": rows[-1][0], "live": live, "px": px, "chg": round((px / pc - 1) * 100, 2),
                  "candle": cd, "state": st, "rows": [[r[0]] + [round(x, 2) for x in r[1:5]] for r in rows],
                  **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in ch.items()}}
            if g["cc"] == "kr_index":
                it.update(INDEX_META.get(code, {}))
            items.append(it)
            key = f"{code}"
            was = prev.get(key) or {}
            stamp = f"{rows[-1][0]}"
            if was.get("state") and was.get("state") != st:
                events.append({"ts": int(now.timestamp() * 1000), "code": code, "text": f"{name}: {was['state']} → {st} ({_fmt(g['cc'], px)}, 상단선 {_fmt(g['cc'], ch['up_now'])}, 5일선 {_fmt(g['cc'], ch['ma5'])})"})
            if live and cd["kind"] in ("bigup", "bigdn", "hammer", "shoot", "doji") and was.get("shape") != f"{stamp}:{cd['kind']}":
                events.append({"ts": int(now.timestamp() * 1000), "code": code, "text": f"{name}: 오늘 캔들 {cd['name']} (시가 대비 {cd['vs_open']:+.2f}%, {_fmt(g['cc'], px)})"})
                was = {**was, "shape": f"{stamp}:{cd['kind']}"}
            # 11/17 운영자: 오늘 봉이 5일선을 위로 넘으면 시그널(어제 종가는 어제까지 5일선 아래였을 때). 하루 한 번
            closes = [r[4] for r in rows]
            ma5_prev = sum(closes[-6:-1]) / 5 if len(closes) >= 6 else None
            it["gap_low"] = round((ch["lo_now"] / px - 1) * 100, 2)             # 하락 추세 지속 시 다음 채널 지지선까지
            it["above_ma5"] = px > ch["ma5"]
            if live and ch["channel_valid"] and ma5_prev and pc <= ma5_prev and px > ch["ma5"] and was.get("ma5sig") != stamp:
                sig = {"ts": int(now.timestamp() * 1000), "day": stamp, "code": code, "name": name, "cc": g["cc"], "contact_policy": contact_policy,
                       "text": f"📐 5일선 돌파 시그널 — {name} {_fmt(g['cc'], px)}가 5일선 {_fmt(g['cc'], ch['ma5'])} 위로 (어제 {_fmt(g['cc'], pc)}는 5일선 아래) · 채널 상단선 {_fmt(g['cc'], ch['up_now'])}까지 {((ch['up_now'] / px - 1) * 100):+.1f}%"}
                signals.append(sig)
                events.append({"ts": sig["ts"], "code": code, "text": sig["text"]})
                was = {**was, "ma5sig": stamp}
            prev[key] = {**was, "state": st}
        if g["cc"] != "kr_index":
            items.sort(key=lambda x: -x["dd"])
        for i, it in enumerate(items):
            it["rank"] = i + 1
        if items:
            groups.append({"cc": g["cc"], "country": g["country"], "sector": g["sector"], "items": items})
    if events:
        hist = (hist + events)[-60:]
    import hashlib
    body = {"contact_policy": contact_policy, "rule": c["rule"], "stance": c.get("stance", ""), "groups": groups, "log": hist[-20:][::-1], "signals": signals[::-1]}
    fp = hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    at = log.get("at") if log.get("fp") == fp and log.get("at") else int(now.timestamp() * 1000)   # 내용이 같으면 시각도 그대로(주말에 매분 올리지 않게)
    _save(LOG, {"contact_policy": contact_policy, "last": prev, "events": hist, "fp": fp, "at": at, "signals": signals})
    return {"at": at, **body, "errs": ERRS[:20]}


def _fmt(cc: str, v: float) -> str:
    if cc == "kr_index":
        return f"{v:,.2f}pt"
    return f"${v:,.2f}" if cc == "us" else (f"{v:,.0f}엔" if cc == "jp" else f"{v:,.0f}원")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    r = build()
    for g in r["groups"]:
        print(f"\n[{g['country']} · {g['sector']}]")
        for it in g["items"]:
            print(f"  {it['rank']}. {it['name']} {it['day']} {it['px']:,.2f} ({it['chg']:+.2f}%) · {it['state']} · 상단 {it['up_now']:,.2f} 5일선 {it['ma5']:,.2f} · 다음 상단까지 {it['gap_next']:+.1f}% · 캔들 {it['candle']['name']}{' (진행 중)' if it['live'] else ''}")
    print("\n기록:", *[e["text"] for e in r["log"][:5]], sep="\n  ")
