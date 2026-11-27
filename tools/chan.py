"""📐 추세 판단 — 종목별 하락 채널·5일선·실시간 캔들 모양(운영자 11/17). 사이트 맨 위 '추세 판단' 칸(news.json 'chan').

  python tools/chan.py        # 지금 계산 결과(확인용)

- 설정: data/channels.json (종목 묶음·채널 기준 날짜 구간·판단 기준 문장)
- 일봉: 한국 = 한투 일봉(FHKST03010100, 하루 한 번), 미국·일본 = 야후 일봉 + 최근 5일 시간봉(야후 일봉의 마지막 날 누락 보완)
- 실시간 캔들: 한국 = 한투 현재가(시가·고가·저가·현재가, 09:00 이후), 미국·일본 = 야후 시간봉으로 오늘 봉을 다시 만든다(1분 캐시)
- 상태: 채널 안 / 상단 근접(다음 거래일 상단까지 3% 안) / 채널 위·5일선 아래(돌파 미확인) / 돌파 시도(장중 상단 +1%·5일선 위) /
        돌파 확인(종가 상단 +1%·5일선 위) / 하단 이탈
- 캔들: 장대양봉·장대음봉·망치형(아래꼬리)·윗꼬리·도지·양봉·음봉 — 오늘(진행 중) 봉 기준
- 넥장(NXT, 11/18 운영자 "추세판단 업데이트"): 한국 종목은 08:00~08:50 프리·15:30 이후 애프터 체결가로 '넥장 기준' 위치를 따로 계산한다
        (it['nxt']). 거래소(KRX) 일봉·상태·5일선 시그널은 그대로 두고 섞지 않는다. 출처 = 네이버 NXT 실시간(체결 시각 오늘인 것만).
- 통합/시간외 차트: session_chan.py가 화면용 display를 만든다. 국내 오늘 KRX+NXT 통합 OHLC, 미국 프리+정규+애프터 1분봉을 날짜별 통합하고 확보 이력을 유지. 정규장 상태·주문용 signals는 보존한다.
- 기록: 상태·눈에 띄는 캔들이 바뀌면 state_dir/chan_log.json 에 쌓고 최근 것을 사이트 '기록'에 보여 준다
사실과 숫자만 계산한다. 매수·매도 권유가 아니다. 키·토큰은 출력하지 않는다.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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


def levels(rows: list[list], px: float, k: int = 3) -> dict:
    """수평 저항·지지(news.js chLevels 와 같은 규칙, 운영자 11/19): 최근 80봉에서 좌우 3봉보다 높은 고점(스윙 고점) 중
    현재가 바로 위 = 수평 저항(전고점), 좌우 3봉보다 낮은 저점 중 현재가 바로 아래 = 수평 지지. 마지막 2봉은 스윙 후보에서 뺀다."""
    n = len(rows); start = max(0, n - 80); res = sup = None
    for i in range(start + k, n - 2):
        win = [j for j in range(i - k, min(n - 1, i + k) + 1) if j != i]
        if all(rows[j][2] <= rows[i][2] for j in win) and rows[i][2] > px and (res is None or rows[i][2] < res[1]):
            res = (i, rows[i][2])
        if all(rows[j][3] >= rows[i][3] for j in win) and rows[i][3] < px and (sup is None or rows[i][3] > sup[1]):
            sup = (i, rows[i][3])
    return {"res_h": res[1] if res else None, "res_day": rows[res[0]][0] if res else None,
            "sup_h": sup[1] if sup else None, "sup_day": rows[sup[0]][0] if sup else None}


def res_gap(ch: dict, px: float) -> float:
    """다음 거래일 채널 상단과 수평 저항(전고점) 중 더 높은 쪽까지 거리(%). 운영자 11/19: 상단은 채널 저항·전고점을 같이 본다."""
    g = ch["gap_next"]
    if ch.get("res_h"):
        g = max(g, (ch["res_h"] / px - 1) * 100)
    return g


def channel(rows: list[list], anchors: dict, contact_rules: dict | None = None,
            *, last_closed: bool = False) -> dict | None:
    """기존 하락 구간의 두 기준점으로 선을 고정하고 추가 접촉 횟수만 표시."""
    from channel_fit import anchored_side
    rules = contact_rules or {}
    tolerance = float(rules.get("tolerance_pct", 0.75))
    spacing = int(rules.get("min_spacing_bars", 3))
    required = 2
    dates = [r[0] for r in rows]
    high = [r[2] for r in rows]
    low = [r[3] for r in rows]
    # 마지막 봉은 돌파·이탈을 검사할 대상이므로 마감 여부와 무관하게 선 계산에서 제외한다.
    last = len(rows) - 2

    def seed(values, window, choose):
        eligible = [i for i in range(last + 1) if window[0] <= dates[i] <= window[1]]
        return choose(eligible, key=lambda i: values[i]) if eligible else None

    h1, l1 = seed(high, anchors["hi1"], max), seed(low, anchors["lo1"], min)
    if h1 is None or l1 is None:
        return None
    kwargs = dict(tolerance_pct=tolerance, min_spacing=spacing)
    upper = anchored_side(high, dates, h1, anchors["hi2"][0], last, True, **kwargs)
    lower = anchored_side(low, dates, l1, anchors["lo2"][0], last, False, **kwargs)
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
            "upper_reinforced": len(upper["touches"]) >= 3, "lower_reinforced": len(lower["touches"]) >= 3,
            "line_method": "fixed_two_anchor",
            "channel_valid": verified, "channel_width_valid": width_valid,
            "touch_tolerance_pct": tolerance, "touch_min_spacing": spacing, "touch_required": required,
            "touch_lookback_bars": len(rows),
            "upper_overlap_pct": upper["max_overlap_pct"], "lower_overlap_pct": lower["max_overlap_pct"],
            **levels(rows, px)}


def swing_anchors(rows: list[list], window: int = 30, spacing: int = 3, side: int = 2) -> dict | None:
    """11/28 운영자 "중국·홍콩 추세선 2점씩 잘 연결": 종목 일봉 최근 window 봉에서 채널 기준점 날짜를 고른다(종목별 anchors 용).
    상단: 가장 높은 스윙 고점 뒤에 스윙 고점이 또 있으면 (최고점 → 뒤 고점, 하락·횡보), 없으면 (바로 앞 스윙 고점 → 최고점, 상승).
    하단: 가장 낮은 스윙 저점 기준 같은 방식. 스윙 = 좌우 side 봉보다 높/낮음. 마지막 봉은 판정 대상이라 제외."""
    last = len(rows) - 2
    first = max(side, last - window + 1)
    if last - first < 2 * spacing + 2:
        return None
    dates = [r[0] for r in rows]

    def piv(vals, up):
        out = []
        for i in range(first, last - side + 1):
            nb = vals[i - side:i] + vals[i + 1:i + 1 + side]
            if all(vals[i] >= v for v in nb) if up else all(vals[i] <= v for v in nb):
                if not out or i - out[-1] >= spacing:
                    out.append(i)
                elif (vals[i] > vals[out[-1]]) if up else (vals[i] < vals[out[-1]]):
                    out[-1] = i
        return out

    def pick(vals, up):
        ps = piv(vals, up)
        if len(ps) < 2:
            return None
        ext = (max if up else min)(ps, key=lambda i: vals[i])
        later = [i for i in ps if i - ext >= spacing]
        if later:
            return ext, later[0]
        earlier = [i for i in ps if ext - i >= spacing]
        return (earlier[-1], ext) if earlier else None
    hp, lp = pick([r[2] for r in rows], True), pick([r[3] for r in rows], False)
    if not hp or not lp:
        return None
    return {"hi1": [dates[hp[0]], dates[hp[0]]], "hi2": [dates[hp[1]], dates[last]],
            "lo1": [dates[lp[0]], dates[lp[0]]], "lo2": [dates[lp[1]], dates[last]]}


def best_anchors(rows: list[list], contact_rules: dict | None = None, window: int = 30, spacing: int = 3, side: int = 2) -> dict | None:
    """swing_anchors 보완: 최근 window 봉의 스윙 고점·저점을 첫 점 후보로 놓고, 채널 폭이 유효(교차·음수 없음)하면서
    두 선 기울기(가격 대비)가 가장 비슷한 조합을 고른다 — 한쪽 선만 가팔라 벌어지는 채널을 피함. 선이 짧으면 감점."""
    base = swing_anchors(rows, window, spacing, side)
    last = len(rows) - 2
    first = max(side, last - window + 1)
    dates = [r[0] for r in rows]

    def piv(k, up):
        vals = [r[k] for r in rows]
        def ok(i):
            nb = vals[i - side:i] + vals[i + 1:i + 1 + side]
            return all(vals[i] >= v for v in nb) if up else all(vals[i] <= v for v in nb)
        return [i for i in range(first, last - spacing + 1) if ok(i)]
    px = rows[-1][4]
    best, best_score = base, None
    if base:
        ch = channel(rows, base, contact_rules)
        if ch and ch["channel_width_valid"]:
            best_score = abs(ch["su"] - ch["sl"]) / px * 100
    for h in piv(2, True):
        for l in piv(3, False):
            a = {"hi1": [dates[h], dates[h]], "hi2": [dates[h + spacing], dates[last]],
                 "lo1": [dates[l], dates[l]], "lo2": [dates[l + spacing], dates[last]]}
            ch = channel(rows, a, contact_rules)
            if not ch or not ch["channel_width_valid"] or not ch["lo_now"] > 0:
                continue
            short = max(0, 12 - (last - min(h, l))) * 0.05      # 12봉보다 짧은 선은 감점
            sc = abs(ch["su"] - ch["sl"]) / px * 100 + short
            if best_score is None or sc < best_score - 0.05:
                best, best_score = a, sc
    return best


def breakout_watch(ch: dict, px: float) -> bool:
    """현재 채널 상단에서 3% 이내이고 5일선을 넘어선 종목."""
    return (ch.get("channel_valid") is not False and ch.get("channel_width_valid") is not False
            and px > ch["ma5"] and abs(ch["up_now"] / px - 1) <= 0.03)


def state(ch: dict, px: float, live: bool) -> str:
    if ch.get("channel_width_valid") is False:
        return "채널선 교차·재확인"
    if ch.get("channel_valid") is False:
        return "접촉 검증 대기"
    above = px > ch["up_now"] * 1.01
    over_res = not ch.get("res_h") or px > ch["res_h"]      # 운영자 11/19: 채널 상단 +1%와 수평 저항(전고점)을 둘 다 넘어야 돌파
    if above and px > ch["ma5"] and over_res:
        return "돌파 시도(장중)" if live else "돌파 확인"
    if above and px > ch["ma5"]:
        return "채널 돌파·전고점 아래"
    if above:
        return "채널 위·5일선 아래"
    if px < ch["lo_now"]:
        return "하단 이탈"
    if breakout_watch(ch, px):
        return "돌파 관찰·상단 근접"
    if res_gap(ch, px) <= 3:
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




def _nh_jp_client():
    import nh_quotes
    candidates = [
        Path(os.environ.get("NH_APP_KEY_FILE", "")).expanduser() if os.environ.get("NH_APP_KEY_FILE") else None,
        Path.home() / ".nhplug" / ".env",
        keystore.keys_file(),
    ]
    keyfile = next((p for p in candidates if p and p.is_file()), None)
    if keyfile is None:
        raise FileNotFoundError("NH credentials")
    return nh_quotes, keyfile, nh_quotes.access_token(keyfile)


def _nh_jp_daily(code: str, now: datetime) -> list[list]:
    """NH 해외주식 기간별시세 Output_1의 일본 종목 일봉만 사용한다."""
    nh_quotes, keyfile, token = _nh_jp_client()
    # Period API uses the bare ticker (e.g. AAPL); JPN prefix is only for current quote.
    symbol = code.removesuffix(".T")
    payload = {"Input_0": {
        "iem_cd": symbol,
        "end_dt": now.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d"),
        "count": "90",
        "maxavg": "0",
        "gubun": "3",
        "xtick": "0001",
        "today_cls": "0",
        "market_cls": "1",
    }}
    response = nh_quotes.request("/gbstock/quote/v1/period", payload, token)
    if response.get("rsp_cd") == "IGW40043":
        token = nh_quotes.access_token(keyfile, force=True)
        response = nh_quotes.request("/gbstock/quote/v1/period", payload, token)
    if response.get("rsp_cd") != "00000":
        raise ValueError("NH Japan daily rejected")
    raw = response.get("Output_1")
    if not isinstance(raw, list):
        raise ValueError("NH Japan daily Output_1 missing")
    rows = []
    for bar in raw:
        date = str(bar.get("bsop_date") or bar.get("trade_date") or bar.get("date") or "")
        if len(date) != 8 or not date.isdigit():
            continue
        op = _n(bar.get("open_prc"))
        hi = _n(bar.get("high"))
        lo = _n(bar.get("low"))
        close = _n(bar.get("close_prc"))
        if not all((op > 0, hi > 0, lo > 0, close > 0)) or not lo <= min(op, close) <= max(op, close) <= hi:
            continue
        rows.append([date, op, hi, lo, close])
    rows.sort(key=lambda row: row[0])
    if len(rows) < 20:
        raise ValueError(f"NH Japan daily bars insufficient: {len(rows)}")
    return [[datetime.strptime(r[0], "%Y%m%d").strftime("%m/%d"), *r[1:]] for r in rows[-90:]]

def _nh_jp_bar(code: str, now: datetime, fallback: list[list]) -> list | None:
    """NH 일본 현재가를 오늘 일봉에 반영한다. 날짜/가격이 검증되지 않으면 일봉만 표시한다."""
    try:
        nh_quotes, keyfile, token = _nh_jp_client()
        symbol = "JPN" + code.removesuffix(".T")
        response = nh_quotes.current_quote(symbol, token)
        if response.get("rsp_cd") == "IGW40043":
            token = nh_quotes.access_token(keyfile, force=True)
            response = nh_quotes.current_quote(symbol, token)
        if response.get("rsp_cd") != "00000":
            ERRS.append(f"{code} NH 현재가 응답 {response.get('rsp_cd', '없음')}")
            return None
        q = response.get("Output_0") or {}
        px = _n(q.get("trdprc"))
        base = _n(q.get("normal_trdprc"))
        if px <= 0 or base <= 0:
            ERRS.append(f"{code} NH 현재가 필드 확인")
            return None
        raw_day = str(q.get("bsop_date") or q.get("trade_date") or q.get("trd_date") or q.get("local_date") or "")
        digits = "".join(ch for ch in raw_day if ch.isdigit())
        if len(digits) >= 8:
            day = digits[:4] + "-" + digits[4:6] + "-" + digits[6:8]
        elif _open_now("jp", now):
            day = now.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
        else:
            ERRS.append(f"{code} NH 거래일 미확인")
            return None
        today = now.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
        if day != today:
            ERRS.append(f"{code} NH 시세 날짜 불일치")
            return None
        hhmmss = "".join(ch for ch in str(q.get("quote_time") or q.get("trd_time") or "") if ch.isdigit())[-6:]
        if hhmmss and len(hhmmss) == 6:
            minute = int(hhmmss[:2]) * 60 + int(hhmmss[2:4])
            if minute < 9 * 60 or (minute > 11 * 60 + 30 and minute < 12 * 60 + 30) or minute > 15 * 60 + 30:
                ERRS.append(f"{code} NH 체결 시각 확인")
                return None
        old = next((row for row in fallback if row[0] == now.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%m/%d")), None)
        def field(*keys):
            return next((_n(q.get(key)) for key in keys if _n(q.get(key)) > 0), 0.0)
        op = field("open_prc", "open_price", "oprc") or (old[1] if old else px)
        hi = field("high_prc", "high_price", "hgpr") or (old[2] if old else max(op, px))
        lo = field("low_prc", "low_price", "lwpr") or (old[3] if old else min(op, px))
        return [now.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%m/%d"), op, max(hi, px), min(lo, px), px]
    except Exception as error:  # noqa: BLE001
        ERRS.append(f"{code} NH 일본 현재가 {type(error).__name__}")
        return None

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


def _krx_close(code: str, now: datetime) -> float | None:
    """오늘 KRX 종가 = 네이버 15:30 분봉(종가 단일가). 11/20: 장 마감 뒤 네이버 현재가·일봉의 종가 자리에 넥장(NXT) 애프터 가격이
    들어와(SK하이닉스 KRX 1,113,000 → 1,109,000) 등락률·상태가 틀어지던 문제. 하루 한 번만 받아 LIVE 캐시에 둔다."""
    day = now.strftime("%Y-%m-%d")
    lc = _load(LIVE)
    k = f"krx_close:{code}"
    if (lc.get(k) or {}).get("day") == day:
        return lc[k]["px"]
    try:
        u = (f"https://api.stock.naver.com/chart/domestic/item/{code}/minute?startDateTime={now:%Y%m%d}1530"
             f"&endDateTime={now:%Y%m%d}1530")
        x = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=8).read())
        b = next((r for r in x if str(r.get("localDateTime", "")).startswith(f"{now:%Y%m%d}1530")), None)
        px = _n(b.get("currentPrice")) if b else 0
    except Exception:  # noqa: BLE001
        return None
    if not px:
        return None
    lc[k] = {"day": day, "px": px}
    _save(LIVE, lc)
    return px


def nxt_window(now: datetime) -> bool:
    """넥스트레이드 시간: 평일 08:00~08:50 프리마켓, 15:30 이후 애프터마켓(20:00 마감 뒤엔 마지막 체결을 '마감'으로)."""
    hm = now.hour * 100 + now.minute
    return now.weekday() < 5 and (800 <= hm < 850 or hm >= 1530)


def _nxt_quotes(codes: list[str], now: datetime) -> dict:
    """네이버 NXT 체결. 이전 체결은 시각과 함께 마지막 값으로만 보존한다."""
    if not codes:
        return {}
    lc = _load(LIVE)
    cached = lc.get("_nxt") or {}
    quotes = cached.get("q") or {}
    now_ms = int(now.timestamp() * 1000)
    active = nxt_window(now) and now.hour < 20
    delay = 55 if active else 300
    premarket_day = now.date().isoformat() if active and now.hour == 8 else None
    entering_premarket = premarket_day is not None and cached.get("premarket_day") != premarket_day
    if entering_premarket or time.time() - cached.get("t", 0) >= delay or not set(codes) <= set(cached.get("codes", [])):
        from krx import BASE, _parse

        try:
            u = f"{BASE}/NXT/stock/{','.join(codes)}"
            rows = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=8).read()).get("datas", [])
            quotes = {**quotes}
            for row in rows:
                stamp = str(row.get("localTradedAt") or "")
                code = row.get("itemCode")
                clock = stamp[11:16]
                if code not in codes or not ("08:00" <= clock <= "08:50" or "15:40" <= clock <= "20:00"):
                    continue
                try:
                    traded = datetime.fromisoformat(stamp)
                except ValueError:
                    continue
                if traded.tzinfo is None:
                    traded = traded.replace(tzinfo=now.tzinfo)
                parsed = _parse(row)
                if not parsed or not 0 < traded.timestamp() * 1000 <= now_ms + 60000:
                    continue
                at = int(traded.timestamp() * 1000)
                if at < (quotes.get(code) or {}).get("at", 0):
                    continue
                quotes[code] = {"px": parsed["px"], "chg": parsed.get("chg"), "at": at,
                                "status": row.get("marketStatus", ""), "day": stamp[:10],
                                "session": "프리" if stamp[11:16] < "09:00" else "애프터"}
        except Exception as error:  # noqa: BLE001
            ERRS.append(f"넥장 시세 {type(error).__name__}")
        # NXT 선정 종목이 아닌 종목도 KRX 시간외(16:00~20:00)에서 체결될 수 있다.
        # NXT 응답에 없는 종목만 네이버 국내 통합 현재가로 보완하고, 오늘 시간외 체결이
        # 2분 이내로 확인될 때만 사용한다. 소스가 달라 NXT 시세와 합치지 않는다.
        hm = now.hour * 60 + now.minute
        if now.weekday() < 5 and hm >= 16 * 60:
            today = now.date().isoformat()
            missing = [code for code in codes if not quotes.get(code)
                       or quotes[code].get("day") != today
                       or quotes[code].get("status") != "OPEN"
                       or now_ms - quotes[code].get("at", 0) > 120000]
            if missing:
                # KRX 별도 애프터마켓은 NXT 피드와 분리된다.
                # Naver 당일 기준가로 거래일을 확인한 뒤 KIS 시간외 체결 TR을 조회한다.
                try:
                    from krx import quotes as krx_quotes
                    current = krx_quotes([f"{code}.KS" for code in missing])
                except Exception as error:  # noqa: BLE001
                    current = {}
                    ERRS.append(f"KRX 시간외 거래일 확인 {type(error).__name__}")
                eligible = [code for code in missing
                            if (current.get(f"{code}.KS") or {}).get("day") == today]
                try:
                    import kis
                    for code in eligible:
                        result = kis.get(
                            "/uapi/domestic-stock/v1/quotations/inquire-time-overtimeconclusion",
                            "FHPST02310000",
                            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code, "FID_HOUR_CLS_CODE": "1"},
                        )
                        output = result.get("output1") or {}
                        rows = list(result.get("output2") or [])
                        # KIS output1도 최신 시간외 체결 시각·현재가를 제공한다.
                        if output.get("stck_cntg_hour") and _n(output.get("ovtm_untp_prpr")) > 0:
                            rows.append({"stck_cntg_hour": output["stck_cntg_hour"],
                                         "stck_prpr": output["ovtm_untp_prpr"]})
                        trades = []
                        for row in rows:
                            clock = str(row.get("stck_cntg_hour") or "").zfill(6)
                            if len(clock) != 6 or not clock.isdigit() or int(clock) < 160000:
                                continue
                            at = int(now.replace(hour=int(clock[:2]), minute=int(clock[2:4]),
                                                 second=int(clock[4:6]), microsecond=0).timestamp() * 1000)
                            px = _n(row.get("stck_prpr"))
                            if 0 < px and at <= now_ms:
                                trades.append((at, px))
                        if not trades:
                            continue
                        at, px = max(trades)
                        raw_pct = output.get("ovtm_untp_prdy_ctrt")
                        prev = (current.get(f"{code}.KS") or {}).get("prev")
                        pct = _n(raw_pct) if raw_pct not in (None, "") else ((px / prev - 1) * 100 if prev else 0)
                        old = quotes.get(code) or {}
                        if at > old.get("at", 0):
                            quotes[code] = {"px": px, "chg": round(pct, 2), "at": at,
                                            "status": "OPEN", "day": today, "session": "애프터",
                                            "venue": "KRX", "source": "한국투자증권 KRX 시간외 체결"}
                except Exception as error:  # noqa: BLE001
                    ERRS.append(f"KRX 시간외 한투 {type(error).__name__}")
                remaining = [code for code in eligible if (quotes.get(code) or {}).get("venue") != "KRX"]
                if remaining:
                    try:
                        for code in remaining:
                            q = current.get(f"{code}.KS") or {}
                            at = int(q.get("at") or 0)
                            if (q.get("px", 0) > 0 and at > 0 and 0 <= now_ms - at <= 120000
                                    and datetime.fromtimestamp(at / 1000, now.tzinfo).date().isoformat() == today
                                    and datetime.fromtimestamp(at / 1000, now.tzinfo).hour * 60
                                    + datetime.fromtimestamp(at / 1000, now.tzinfo).minute >= 16 * 60):
                                old = quotes.get(code) or {}
                                if at > old.get("at", 0):
                                    quotes[code] = {"px": q["px"], "chg": q.get("chg"), "at": at,
                                                    "status": "OPEN", "day": today, "session": "애프터",
                                                    "venue": "KRX"}
                    except Exception as error:  # noqa: BLE001
                        ERRS.append(f"KRX 시간외 보완 {type(error).__name__}")
        lc["_nxt"] = {"t": time.time(), "codes": codes, "q": quotes, "premarket_day": premarket_day}
        _save(LIVE, lc)
    return {code: {**quote, "last_only": (not active or quote.get("day") != now.date().isoformat()
                                         or quote.get("status") != "OPEN"
                                         or now_ms - quote["at"] > 120000)}
            for code, quote in quotes.items()
            if code in codes and -60000 <= now_ms - (quote.get("at") or 0) < 7 * 86400_000}


def nxt_view(rows: list[list], ch: dict, px: float, today: str) -> dict:
    """넥장 가격을 오늘 종가 자리에 넣었을 때의 위치. 프리마켓(오늘 봉 없음)은 다음 칸 선, 애프터는 오늘 칸 선."""
    closes = [r[4] for r in rows]
    if rows[-1][0] == today:                               # 애프터마켓: 거래소 오늘 봉이 있음
        up, lo, up_nx = ch["up_now"], ch["lo_now"], ch["up_next"]
        ma5 = (sum(closes[-5:-1]) + px) / 5
    else:                                                  # 프리마켓: 오늘 봉 전
        up, lo, up_nx = ch["up_next"], ch["lo_next"], ch["up_next"] + (ch["up_next"] - ch["up_now"])
        ma5 = (sum(closes[-4:]) + px) / 5
    st = state({**ch, "up_now": up, "lo_now": lo, "ma5": ma5, "gap_next": (up_nx / px - 1) * 100}, px, True)
    return {"state": st.replace("(장중)", "(넥장)"), "ma5": round(ma5, 2), "above_ma5": px > ma5,
            "up": round(up, 2), "lo": round(lo, 2), "gap_up": round((up / px - 1) * 100, 2), "session": "애프터" if rows[-1][0] == today else "프리"}


# ── 11/20 운영자 "통합 종가로 하자 · KRX 종가도 따로 표시해 체크(종가가 지금은 기준가)" ──
# 대조(SK하이닉스 11/18): KRX 정규장 종가 1,144,000(한투·NH·네이버 15:30봉) / 통합 종가 1,164,000(넥장 20:00 마지막 체결 = 네이버 일봉).
# 5일선 = 통합 종가, 등락률 기준가 = KRX 종가. 둘 다 카드에 따로 보인다.
KRX_SEED = ROOT / "data" / "kr_krx_closes.json"
KRX_ARCH = keystore.state_dir() / "kr_krx_closes.json"


def _iso(md: str, now: datetime) -> str:
    y = now.year - (1 if md > now.strftime("%m/%d") else 0)
    return f"{y}-{md[:2]}-{md[3:5]}"


def uni_closes(code: str, now: datetime) -> dict:
    """{MM/DD: 통합 종가} — 네이버 일봉(넥장 20:00 마감 반영), 하루 한 번. 오늘 값은 쓰지 않는다(진행 중)."""
    dc = _load(DAILY); k = f"uni:{code}"; e = dc.get(k) or {}
    today = now.strftime("%Y-%m-%d")
    if e.get("day") != today:
        try:
            e = {"day": today, "c": {r[0]: r[4] for r in _naver_daily(code)}}
            dc[k] = e; _save(DAILY, dc)
        except Exception as x:  # noqa: BLE001
            ERRS.append(f"{code} 통합 종가 {type(x).__name__}")
    return {d: v for d, v in (e.get("c") or {}).items() if d != now.strftime("%m/%d")}


def krx_closes(code: str) -> dict:
    """{YYYY-MM-DD: KRX 종가} — 저장본(NH 일봉) + 서버가 매일 보탠 네이버 기준가."""
    seed = (_load(KRX_SEED).get("closes") or {}).get(code) or {}
    return {**seed, **((_load(KRX_ARCH).get(code)) or {})}


def _krx_prev(codes: list[str], now: datetime) -> dict:
    """{code: [시세 날짜 YYYY-MM-DD, 전일 KRX 종가]} — 네이버 거래소 시세의 '전일 대비'로 거꾸로 구한 기준가. 10분 캐시."""
    lc = _load(LIVE); c = lc.get("_krxprev") or {}
    if time.time() - c.get("t", 0) < 600 and set(codes) <= set(c.get("codes", [])):
        return c.get("q") or {}
    from krx import BASE, _parse
    q = {}
    try:
        u = f"{BASE}/stock/{','.join(codes)}"
        for d in json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=8).read()).get("datas", []):
            r = _parse(d)
            if r and r.get("prev") and r.get("day"):
                q[d["itemCode"]] = [r["day"], round(r["prev"])]
    except Exception as x:  # noqa: BLE001
        ERRS.append(f"KRX 기준가 {type(x).__name__}")
        return c.get("q") or {}
    lc["_krxprev"] = {"t": time.time(), "codes": codes, "q": q}
    _save(LIVE, lc)
    return q


def archive_krx(prev: dict, now: datetime) -> None:
    """기준가(전일 KRX 종가)를 그 전 거래일 날짜로 저장. 전 거래일 = 통합 일봉에서 시세 날짜 바로 앞 날."""
    a = _load(KRX_ARCH); changed = False
    for code, (day, px) in prev.items():
        before = sorted(d for d in (_iso(m, now) for m in uni_closes(code, now)) if d < day)
        if before and (a.get(code) or {}).get(before[-1]) != px:
            a.setdefault(code, {})[before[-1]] = px; changed = True
    if changed:
        _save(KRX_ARCH, a)


def kr_basis(code: str, rows: list[list], now: datetime, nq: dict | None) -> dict:
    """통합·KRX 두 기준의 종가 줄·5일선·기준가. rows 마지막 봉 = 오늘(장중·마감) 또는 전일(장 전)."""
    U, K = uni_closes(code, now), krx_closes(code)
    md = now.strftime("%m/%d")
    last_today = rows[-1][0] == md
    hm = now.hour * 100 + now.minute
    u, k, miss_u, miss_k = [], [], 0, 0
    for i, r in enumerate(rows):
        if i == len(rows) - 1 and last_today:
            kx = r[4]                                          # 장중 현재가 / 15:31 뒤 KRX 종가
            at = datetime.fromtimestamp(nq["at"] / 1000, KST).strftime("%H%M") if nq and nq.get("at") else ""
            u.append(nq["px"] if nq and hm >= 1530 and at >= "1530" else kx); k.append(kx)
            continue
        kv, uv = K.get(_iso(r[0], now)), U.get(r[0])
        if i >= len(rows) - 6:
            miss_u += uv is None; miss_k += kv is None
        k.append(float(kv) if kv else r[4]); u.append(float(uv) if uv else (float(kv) if kv else r[4]))
    done_k = not last_today or hm >= 1531
    done_u = not last_today or hm >= 2000
    closed_rows = rows if done_u else rows[:-1]
    closed = []
    for row in closed_rows[-5:]:
        if last_today and row[0] == md:
            if (nq and nq.get("day") == now.date().isoformat()
                    and nq.get("session") == "애프터" and nq.get("px", 0) > 0):
                closed.append(float(nq["px"]))
            else:
                break
        elif U.get(row[0]):
            closed.append(float(U[row[0]]))
        else:
            break
    uni_sma5_closed = sum(closed) / 5 if len(closed) == 5 else None
    uni_below_sma5 = closed[-1] < uni_sma5_closed if uni_sma5_closed is not None else None
    return {"uni_sma5_closed": uni_sma5_closed, "uni_below_sma5": uni_below_sma5,
            "u": u, "k": k, "ma5": sum(u[-5:]) / 5, "ma5_krx": sum(k[-5:]) / 5,
            "base": k[-2] if last_today and len(k) > 1 else k[-1],
            "krx_close": k[-1] if done_k else k[-2], "krx_close_day": rows[-1 if done_k else -2][0],
            "uni_close": u[-1] if done_u else u[-2], "uni_close_day": rows[-1 if done_u else -2][0],
            "miss_u": miss_u, "miss_k": miss_k}


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
    refresh_split = code == "SNDK" and e.get("schema") != "sndk-split-20261120"
    jp_after_close = cc == "jp" and now.weekday() < 5 and now.hour * 100 + now.minute >= 1531
    refresh_jp = jp_after_close and (e.get("day") != today or not e.get("closed"))
    if refresh_split or refresh_jp or e.get("day") != today or not e.get("rows"):  # 원본 일봉은 하루 한 번
        rows = []
        try:
            if cc == "kr":
                rows = _kis_daily(code)
            elif cc == "jp":
                rows = _nh_jp_daily(code, now)
            else:
                rows = _yahoo(code, "6mo", "1d")
        except Exception as x:  # noqa: BLE001
            ERRS.append(f"{code} 일봉 {type(x).__name__}")
        if not rows and cc == "jp":
            try:
                rows = _yahoo(code, "6mo", "1d")
                if rows:
                    ERRS.append(f"{code} NH 일봉 실패 → Yahoo 일봉 임시 사용")
            except Exception as x:  # noqa: BLE001
                ERRS.append(f"{code} Yahoo 대체 일봉 {type(x).__name__}")
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
        if not rows and refresh_split:
            return [], False
        if not rows and cc != "jp":
            rows = e.get("rows") or []
        if rows:
            dc[code] = {"day": today, "rows": rows[-90:]}
            if code == "SNDK":
                dc[code]["schema"] = "sndk-split-20261120"
            if cc == "jp":
                dc[code]["closed"] = jp_after_close and rows[-1][0] == now.strftime("%m/%d")
            _save(DAILY, dc)
        e = dc.get(code) or {}
    rows = [list(r) for r in e.get("rows") or []]
    lc = _load(LIVE); le = lc.get(code) or {}
    live = None
    if time.time() - le.get("t", 0) < 55 and (code != "SNDK" or le.get("interval") == "1d"):
        live = le.get("bars")
    else:
        try:
            if cc == "kr":
                hm = now.hour * 100 + now.minute
                live = [_kis_now(code)] if now.weekday() < 5 and hm >= 900 else []
                live = [b for b in live if b]
            elif cc == "jp":
                # Closed market: use the latest daily close; do not query the live quote endpoint.
                if _open_now("jp", now):
                    nh_bar = _nh_jp_bar(code, now, rows)
                    live = [nh_bar] if nh_bar else []
                else:
                    live = []
            elif cc == "tw" or code == "SNDK":
                # 분할 조정된 일봉의 시가·고가·저가를 마지막 시간봉으로 덮지 않는다.
                live = _yahoo(code, "5d", "1d")[-1:]
            else:
                live = _yahoo(code, "5d", "60m")[-1:]            # 오늘(마지막 날)만 — 전날은 일봉 종가 그대로
            lc[code] = {"t": time.time(), "bars": live}
            if code == "SNDK":
                lc[code]["interval"] = "1d"
            _save(LIVE, lc)
        except Exception:  # noqa: BLE001
            live = le.get("bars") or [] if code != "SNDK" or le.get("interval") == "1d" else []
    if code == "SNDK" and rows and live and not 0.4 <= live[-1][4] / rows[-1][4] <= 2.5:
        ERRS.append("SNDK 분할 가격 기준 불일치")
        live = []
    if cc == "us" and live:                                # 11/20: CME 선물은 야후가 약 10분 늦다 → NH 실시간 현재가로 오늘 봉 종가
        try:
            from nhfut import cme_live
            q = cme_live(code, ref=live[-1][4])
            if q:
                d, o, h, l, _ = live[-1][:5]
                live = live[:-1] + [[d, o, max(h, q["px"]), min(l, q["px"]), q["px"]]]
        except Exception:  # noqa: BLE001
            pass
    if cc == "jp" and live:
        recent = {r[0]: r for r in live}
        rows = [recent.pop(r[0], r) for r in rows]
        # Backfill missing recent sessions in chronological order, including year rollover.
        rows.extend(recent.values())
        rows.sort(key=lambda r: (r[0] > now.strftime("%m/%d"), r[0]))
    for b in ([] if cc == "jp" else live) or []:                                   # 같은 날짜는 바꾸고, 새 날짜는 붙인다
        if rows and rows[-1][0] == b[0]:
            rows[-1] = b
        elif not rows or b[0] > rows[-1][0] or (rows[-1][0][:2] == "12" and b[0][:2] == "01"):
            rows.append(b)
    if cc == "kr" and rows and now.weekday() < 5 and now.hour * 100 + now.minute >= 1531 and rows[-1][0] == now.strftime("%m/%d"):
        kc = _krx_close(code, now)                         # 장 마감 뒤 종가는 KRX 값만(넥장은 it['nxt']로 따로)
        if kc:
            d, o, h, l, _ = rows[-1][:5]
            rows[-1] = [d, o, max(h, kc), min(l, kc), kc]
    in_session = _is_current_session_bar(cc, live, rows, now, code)
    return rows[-NBARS:], in_session


def cn_limit_pct(code: str) -> float | None:
    """중국 본토 가격제한폭(%): 커촹반 688·촹예반 300/301 = 20, 그 밖 상하이·선전 = 10. 홍콩은 없음(None). ST 종목은 따지지 않음."""
    if code.endswith(".HK"):
        return None
    return 20.0 if code.startswith(("688", "689", "300", "301")) else 10.0


def cn_limit_state(code: str, chg: float | None) -> str | None:
    """등락률이 가격제한폭에 닿았으면(0.05%p 안) '상한가'·'하한가'."""
    lim = cn_limit_pct(code)
    if lim is None or chg is None:
        return None
    return "상한가" if chg >= lim - 0.05 else "하한가" if chg <= -lim + 0.05 else None


def _open_now(cc: str, now: datetime, code: str = "") -> bool:
    if cc == "kr":
        hm = now.hour * 100 + now.minute
        return now.weekday() < 5 and 900 <= hm < 1530
    if cc == "jp":
        hm = now.hour * 100 + now.minute
        return now.weekday() < 5 and (900 <= hm < 1130 or 1230 <= hm < 1530)
    if cc == "tw":
        local = now.astimezone(ZoneInfo("Asia/Taipei"))
        return local.weekday() < 5 and 900 <= local.hour * 100 + local.minute < 1330
    if cc == "cn":                                          # 11/28: 홍콩 09:30~12:00·13:00~16:00, 상하이·선전 09:30~11:30·13:00~15:00(현지)
        local = now.astimezone(ZoneInfo("Asia/Shanghai"))
        hm = local.hour * 100 + local.minute
        if code.endswith(".HK"):
            return local.weekday() < 5 and (930 <= hm < 1200 or 1300 <= hm < 1600)
        return local.weekday() < 5 and (930 <= hm < 1130 or 1300 <= hm < 1500)
    ny = now.astimezone(ZoneInfo("America/New_York"))       # DST 포함
    m = ny.hour * 60 + ny.minute
    return ny.weekday() < 5 and 570 <= m < 960


def _is_current_session_bar(cc: str, live: list[list], rows: list[list], now: datetime, code: str = "") -> bool:
    """장중 표시는 해당 시장의 오늘 날짜 봉이 실제로 있을 때만 허용한다."""
    zones = {"kr": "Asia/Seoul", "jp": "Asia/Tokyo", "tw": "Asia/Taipei", "us": "America/New_York", "cn": "Asia/Shanghai"}
    zone = zones.get(cc)
    if not zone or not live or not rows:
        return False
    day = now.astimezone(ZoneInfo(zone)).strftime("%m/%d")
    return live[-1][0] == rows[-1][0] == day and _open_now(cc, now, code)


def build(now: datetime | None = None) -> dict:
    realtime_clock = now is None
    now = now or datetime.now(KST)
    ERRS.clear()
    INDEX_META.clear()
    c = json.loads(CONF.read_text(encoding="utf-8"))
    from session_chan import collect as collect_sessions, display as display_session, closed_nxt_quote
    session_cache_path = keystore.state_dir() / "chan_sessions.json"
    session_quotes, session_errors = collect_sessions(c["groups"], now, session_cache_path)
    session_archive = (_load(session_cache_path).get("_history") or {})
    groups, events = [], []
    contact_policy = json.dumps(c.get("contact_rules") or {}, sort_keys=True)
    log = _load(LOG); prev = log.get("last", {}) if log.get("contact_policy") == contact_policy else {}; hist = log.get("events", [])
    signals = [s for s in log.get("signals", []) if now.timestamp() * 1000 - s["ts"] < 20 * 3600_000 and s.get("contact_policy") == contact_policy]   # 오늘(20시간 안) 시그널만
    watch_signals = [s for s in log.get("watch_signals", [])
                     if now.timestamp() * 1000 - s["ts"] < 20 * 3600_000 and s.get("contact_policy") == contact_policy]
    resists = [s for s in log.get("resists", []) if now.timestamp() * 1000 - s["ts"] < 20 * 3600_000 and s.get("contact_policy") == contact_policy]   # 5일선 저항(11/18), 주문용 signals 와 따로
    kr_codes = [code for g in c["groups"] if g["cc"] == "kr" for code, _ in g["items"]]
    nxq = _nxt_quotes(kr_codes, now)
    try:                                                        # 11/20: 매일 기준가(전일 KRX 종가)를 모아 KRX 종가 줄을 잇는다
        archive_krx(_krx_prev(kr_codes, now), now)
    except Exception as x:  # noqa: BLE001
        ERRS.append(f"KRX 종가 저장 {type(x).__name__}")
    ipo_cfg = c.get("ipo") or {}
    for g in c["groups"]:
        items = []
        for code, name in g["items"]:
            if code in ipo_cfg:                                 # 11/20 운영자: 상장 초기 종목(ANT)은 채널 대신 공모가·시가·고점 기준 카드
                try:
                    it = ipo_item(code, name, ipo_cfg[code], now)
                    if it:
                        items.append(it)
                    else:
                        ERRS.append(f"{code} 상장 초기 시세 없음")
                except Exception as x:  # noqa: BLE001
                    ERRS.append(f"{code} 상장 초기 시세 {type(x).__name__}")
                continue
            fcc = "hk" if g["cc"] == "cn" and code.endswith(".HK") else g["cc"]   # 금액 표기(홍콩 HK$·본토 위안)
            try:
                observed_at = datetime.now(KST) if realtime_clock and g["cc"] == "kr_index" else now
                rows, live = bars(g["cc"], code, observed_at)
            except Exception as x:  # noqa: BLE001
                ERRS.append(f"{code} 시세 {type(x).__name__}"); continue
            if len(rows) < 20:
                ERRS.append(f"{code} 일봉 {len(rows)}개뿐"); continue
            anc = (c.get("anchors_by_code") or {}).get(code) or c["anchors"]   # 11/28: 종목별 기준점(중국·홍콩)이 있으면 우선
            if g.get("inverse"):                                # 11/21 운영자 "SKDD 하방 지지선 오류": 인버스는 기초자산과 반대로 움직이므로
                anc = {"hi1": anc["lo1"], "hi2": anc["lo2"], "lo1": anc["hi1"], "lo2": anc["hi2"]}   # 기초자산 저점 구간 = 인버스 고점 구간
            index_stale = g["cc"] == "kr_index" and INDEX_META.get(code, {}).get("stale")
            provisional = index_stale and rows[-1][0] == observed_at.strftime("%m/%d")
            ch = channel(rows, anc, c.get("contact_rules"), last_closed=not (live or provisional))
            if not ch:
                ERRS.append(f"{code} 채널 기준점 없음"); continue
            kb = None
            if g["cc"] == "kr":                                   # 11/20 운영자: 5일선 = 통합 종가, 기준가 = KRX 종가
                try:
                    kb = kr_basis(code, rows, now, nxq.get(code))
                    ch["ma5"] = kb["ma5"]
                except Exception as x:  # noqa: BLE001
                    ERRS.append(f"{code} 통합·KRX 종가 {type(x).__name__}")
            o, h, l, px = rows[-1][1:5]
            pc = kb["base"] if kb else rows[-2][4]
            pcu = kb["u"][-2] if kb else pc                       # 시그널 '어제 종가'는 5일선과 같은 통합 기준
            cd = candle(o, h, l, px, pc)
            st = state(ch, px, live)
            if index_stale and st == "돌파 확인":
                st = "돌파 관찰·상단 근접"
            was0 = (prev.get(code) or {}).get("state")       # 11/17: 3% 경계에서 오락가락(채널 안↔상단 근접) 막기 — 나갈 때는 3.5%
            if was0 == "상단 근접" and st == "채널 안" and res_gap(ch, px) <= 3.5:
                st = "상단 근접"
            market_stale = g["cc"] != "kr_index" and _open_now(g["cc"], now, code) and not live
            if g["cc"] == "jp" and not market_stale and jp_daily_stale(rows[-1][0], now):   # 11/28: NH 일봉에 전 거래일 봉이 없으면 지난 값 표시
                market_stale = True
            it = {"code": code, "name": name, "day": rows[-1][0], "live": live, "stale": market_stale, "px": px, "chg": round((px / pc - 1) * 100, 2),
                  "candle": cd, "state": st, "rows": [[r[0]] + [round(x, 2) for x in r[1:5]] for r in rows],
                  **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in ch.items()}}
            if g["cc"] == "jp":
                it["source"] = "NH투자증권"
                it["base_day"] = rows[-2][0]
                if market_stale:
                    it["stale_note"] = f"{it['day']} 기준 지난 값(최근 거래일 봉 없음)"
            if g["cc"] == "tw":
                it["source"] = "Yahoo 일봉 · 지연 가능"
            if g["cc"] == "cn":                                   # 11/28 1b: 중국·홍콩 — Yahoo 일봉 + 당일 60분봉(일봉 당일 값이 비어 옴)
                it["source"] = "Yahoo 일봉·60분봉 · 지연 가능"
                it["limit_pct"] = cn_limit_pct(code)
                lim = cn_limit_state(code, it["chg"])
                if lim:
                    it["limit"] = lim
                    it["name"] = f"{name} · {lim}"
            if g["cc"] == "kr_index":
                index_meta = INDEX_META.get(code, {})
                it.update(index_meta)
                if index_meta.get("stale"):
                    ERRS.append(f"{code} 지수 실시간 원천 미확인 · {index_meta.get('live_diagnostic', '갱신 대기')}")
            if kb:
                it.update(ma5_krx=round(kb["ma5_krx"], 2), krx_close=kb["krx_close"], krx_close_day=kb["krx_close_day"],
                          uni_close=kb["uni_close"], uni_close_day=kb["uni_close_day"],
                          uni_sma5_closed=kb["uni_sma5_closed"], uni_below_sma5=kb["uni_below_sma5"], base=kb["base"],
                          reg_closes=[[r[0], round(v, 2)] for r, v in zip(rows, kb["u"])][:-1],
                          ma5_basis="통합 종가(KRX+넥장 20시) 4일 + 현재가" + (f" · 통합 {kb['miss_u']}일 KRX로 대체" if kb["miss_u"] else ""),
                          krx_missing=kb["miss_k"])
            if g["cc"] == "kr" and code in nxq:
                nq = nxq[code]
                it["nxt"] = nq
            if g["cc"] == "kr" and code in nxq and not nxq[code].get("last_only"):
                it["nxt"] = {**nq, "vs_krx": round((nq["px"] / px - 1) * 100, 2) if rows[-1][0] == now.strftime("%m/%d") else None,
                             **nxt_view([r[:4] + [v] for r, v in zip(rows, kb["u"])] if kb else rows, ch, nq["px"], now.strftime("%m/%d"))}
            if g["cc"] in ("kr", "us"):
                sq = session_quotes.get(code)
                nq = nxq.get(code) if g["cc"] == "kr" else None
                if g["cc"] == "kr" and nq and nq.get("session") == "애프터" and nq.get("day") == _iso(rows[-1][0], now):
                    archived = (session_archive.get(code) or {}).get(nq["day"])
                    closed = closed_nxt_quote(archived, nq, now)
                    if closed and (not sq or not sq.get("provider_open") or sq.get("day") != nq["day"]):
                        sq = closed
                if sq:
                    try:
                        view = display_session(rows, sq, anc, c.get("contact_rules"), now=now,
                                               channel=channel, candle=candle, state=state)
                        if view and kb:                    # 통합 5일선·KRX 기준가로 맞춘다
                            uc = {r[0]: v for r, v in zip(rows, kb["u"])}
                            prior = [uc[r[0]] for r in rows if r[0] != view["day"]][-4:]
                            if len(prior) == 4:
                                view["ma5"] = (sum(prior) + view["px"]) / 5
                                view["above_ma5"] = view["px"] > view["ma5"]
                            view["reg_closes"] = [[d, round(v, 2)] for d, v in uc.items() if d != view["day"]]
                            view["ma5_basis"] = it["ma5_basis"]
                            kbase = {r[0]: v for r, v in zip(rows, kb["k"])}.get(view.get("base_day"))
                            if kbase:
                                view.update(base=kbase, change=round(view["px"] - kbase, 4), chg=round((view["px"] / kbase - 1) * 100, 2))
                        if view:
                            it["display"] = view
                    except (ValueError, TypeError, KeyError, IndexError):
                        session_errors.append(f"{code} 확장차트 계산 확인")
                if "display" not in it:
                    it["session_note"] = "통합·확장세션 OHLC 미확인 — 정규장 차트 표시"
            items.append(it)
            key = f"{code}"
            was = prev.get(key) or {}
            stamp = f"{rows[-1][0]}"
            if not index_stale and was.get("state") and was.get("state") != st:
                events.append({"ts": int(now.timestamp() * 1000), "code": code, "text": f"{name}: {was['state']} → {st} ({_fmt(fcc, px)}, 상단선 {_fmt(fcc, ch['up_now'])}, 5일선 {_fmt(fcc, ch['ma5'])})"})
            if live and cd["kind"] in ("bigup", "bigdn", "hammer", "shoot", "doji") and was.get("shape") != f"{stamp}:{cd['kind']}":
                events.append({"ts": int(now.timestamp() * 1000), "code": code, "text": f"{name}: 오늘 캔들 {cd['name']} (시가 대비 {cd['vs_open']:+.2f}%, {_fmt(fcc, px)})"})
                was = {**was, "shape": f"{stamp}:{cd['kind']}"}
            # 11/17 운영자: 오늘 봉이 5일선을 위로 넘으면 시그널(어제 종가는 어제까지 5일선 아래였을 때). 하루 한 번
            closes = kb["u"] if kb else [r[4] for r in rows]
            ma5_prev = sum(closes[-6:-1]) / 5 if len(closes) >= 6 else None
            it["gap_low"] = round((ch["lo_now"] / px - 1) * 100, 2)             # 하락 추세 지속 시 다음 채널 지지선까지
            it["above_ma5"] = px > ch["ma5"]
            if code != "NVDL" and live and ch["channel_valid"] and ma5_prev and pcu <= ma5_prev and px > ch["ma5"] and was.get("ma5sig") != stamp:
                sig = {"ts": int(now.timestamp() * 1000), "day": stamp, "code": code, "name": name, "cc": g["cc"], "contact_policy": contact_policy,
                       "text": _josa(f"📐 5일선 돌파 시그널 — {name} {_fmt(fcc, px)}가 5일선 {_fmt(fcc, ch['ma5'])} 위로 (어제 {_fmt(fcc, pcu)}는 5일선 아래) · 채널 상단선 {_fmt(fcc, ch['up_now'])}까지 {((ch['up_now'] / px - 1) * 100):+.1f}%")}
                signals.append(sig)
                events.append({"ts": sig["ts"], "code": code, "text": sig["text"]})
                was = {**was, "ma5sig": stamp}
            if live and not it.get("stale") and breakout_watch(it, px) and was.get("watch_day") != stamp:
                gap = (it["up_now"] / px - 1) * 100
                watch_signals.append({"ts": int(now.timestamp() * 1000), "day": stamp, "code": code,
                                      "name": name, "cc": g["cc"], "contact_policy": contact_policy,
                                      "text": f"📐 돌파 관찰 — {name} 5일선 위 · 채널 상단까지 {gap:+.1f}% · 종가·지지 확인 필요"})
                was = {**was, "watch_day": stamp}
            # 11/18 운영자 전략 '5일선 저항 시 매도·돌파 시 매수' — 저항 = 어제 5일선 아래, 오늘 고가가 5일선에 닿은 뒤 현재가가 5일선 0.3% 넘게 아래.
            # 사실만 기록하고 주문용 signals 에는 넣지 않는다(자동 주문 경로와 분리). 하루 한 번
            if live and ch["channel_valid"] and ma5_prev and pcu <= ma5_prev and h >= ch["ma5"] and px < ch["ma5"] * 0.997 and was.get("ma5res") != stamp:
                rs = {"ts": int(now.timestamp() * 1000), "day": stamp, "code": code, "name": name, "cc": g["cc"], "contact_policy": contact_policy, "kind": "resist",
                      "text": f"📐 5일선 저항 — {name} 장중 고가 {_ro(_fmt(fcc, h))} 5일선 {_fmt(fcc, ch['ma5'])} 터치 후 현재 {_fmt(fcc, px)} (5일선 대비 {((px / ch['ma5'] - 1) * 100):+.1f}%)"}
                resists.append(rs)
                events.append({"ts": rs["ts"], "code": code, "text": rs["text"]})
                was = {**was, "ma5res": stamp}
            if not index_stale:
                prev[key] = {**was, "state": st}
        if g["cc"] != "kr_index":
            items.sort(key=lambda x: -x["dd"])
        chan_items = [x for x in items if not x.get("ipo")]
        for i, it in enumerate(items):
            it["rank"] = i + 1
            if not it.get("ipo"):
                it["res_gap"] = round(res_gap(it, it["px"]), 2)
        if items:
            grp = {"cc": g["cc"], "country": g["country"], "sector": g["sector"], "items": items}
            if len(chan_items) > 1 and g["cc"] != "kr_index":
                grp["sector_view"] = sector_view(chan_items)
            groups.append(grp)
    if events:
        hist = (hist + events)[-60:]
    import hashlib
    body = {"build": "chan-krx-overtime-kis-v3-global-sectors", "contact_policy": contact_policy, "rule": c["rule"], "stance": c.get("stance", ""), "global_sectors": c.get("global_sectors", []), "groups": groups, "log": hist[-20:][::-1], "signals": signals[::-1], "watch_signals": watch_signals[::-1], "resists": resists[::-1], "session_errs": session_errors[:20]}
    fp = hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    at = log.get("at") if log.get("fp") == fp and log.get("at") else int(now.timestamp() * 1000)   # 내용이 같으면 시각도 그대로(주말에 매분 올리지 않게)
    _save(LOG, {"contact_policy": contact_policy, "last": prev, "events": hist, "fp": fp, "at": at, "signals": signals, "watch_signals": watch_signals, "resists": resists})
    return {"at": at, **body, "errs": ERRS[:20]}


def jp_daily_stale(last_day: str, now: datetime) -> bool:
    """일본 일봉 마지막 날짜(MM/DD)가 기대하는 최근 거래일보다 앞이면 True. 평일 09:00(도쿄) 전은 전 평일까지 기대.
    공휴일은 따지지 않음(공휴일 다음 날 오전엔 하루 지난 값으로 보일 수 있음)."""
    tk = now.astimezone(ZoneInfo("Asia/Tokyo"))
    d = tk.date()
    if tk.weekday() >= 5 or tk.hour * 100 + tk.minute < 900:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    try:
        last = datetime.strptime(f"{d.year}/{last_day}", "%Y/%m/%d").date()
    except (TypeError, ValueError):
        return True
    if last > d:                                            # 연말 넘김(12/30 봉을 1월에 볼 때)
        last = last.replace(year=last.year - 1)
    return last < d


IPO_STATE = keystore.state_dir() / "chan_ipo.json"


def ipo_daily(code: str) -> list[list]:
    """상장 뒤 일봉 [YYYY-MM-DD, 시가, 고가, 저가, 종가](Yahoo, 거래소 현지 날짜)."""
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(code)}?range=3mo&interval=1d"
    r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=10).read())["chart"]["result"][0]
    q = r["indicators"]["quote"][0]; tz = timezone(timedelta(seconds=r["meta"].get("gmtoffset", 0)))
    return [[datetime.fromtimestamp(t, tz).strftime("%Y-%m-%d"), o, h, l, c]
            for t, o, h, l, c in zip(r.get("timestamp") or [], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]


def ipo_base(code: str, listed: str | None, today: str, daily=None, path: Path | None = None) -> dict:
    """첫 시가·상장 뒤 고점/저점을 상장일부터 계산해 저장(하루 한 번 일봉 갱신, 첫 시가는 한 번 정하면 그대로)."""
    path = path or IPO_STATE
    st = _load(path)
    e = dict(st.get(code) or {})
    if e.get("day") == today and e.get("open1"):
        return e
    rows = [r for r in (daily or ipo_daily)(code) if not listed or r[0] >= listed]
    if rows:
        if not e.get("open1"):
            e.update(open1=round(rows[0][1], 4), open1_day=rows[0][0])
        e["hi"] = round(max([r[2] for r in rows] + ([e["hi"]] if e.get("hi") else [])), 4)
        e["lo"] = round(min([r[3] for r in rows] + ([e["lo"]] if e.get("lo") else [])), 4)
        e["day"] = today
        st[code] = e
        _save(path, st)
    return e


def ipo_prev_close(meta: dict, regular: list[list], ny_tz: ZoneInfo, ipo_px: float) -> float:
    """전일 종가: Yahoo meta previousClose(5일 창 앞 종가 chartPreviousClose 아님) → 직전 거래일 마지막 정규장 봉 → 공모가."""
    for k in ("regularMarketPreviousClose", "previousClose"):
        if meta.get(k):
            return float(meta[k])
    if regular:
        last_day = datetime.fromtimestamp(regular[-1][0] / 1000, ny_tz).date()
        before = [b for b in regular if datetime.fromtimestamp(b[0] / 1000, ny_tz).date() < last_day]
        if before:
            return before[-1][4]
    return ipo_px


def ipo_broker_extended_bars(code: str, ny_tz: ZoneInfo) -> list[list]:
    """한투 해외주식 조회 전용 TR에서 실제 체결이 있는 시간외 5분봉만 사용한다."""
    import kis

    result = kis.get(
        "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice",
        "HHDFS76950200",
        {"AUTH": "", "EXCD": "NAS", "SYMB": code, "NMIN": "5", "PINC": "1",
         "NEXT": "", "NREC": "120", "FILL": "", "KEYB": ""},
    )
    bars = []
    for row in result.get("output2") or []:
        try:
            local = datetime.strptime(str(row["xymd"]) + str(row["xhms"]).zfill(6), "%Y%m%d%H%M%S").replace(tzinfo=ny_tz)
            minute = local.hour * 60 + local.minute
            if local.weekday() >= 5 or float(row["evol"]) <= 0:
                continue
            if 240 <= minute < 570:
                session = "pre"
            elif 960 <= minute < 1200:
                session = "post"
            else:
                continue
            o, h, l, c = (round(float(row[key]), 4) for key in ("open", "high", "low", "last"))
            if 0 < l <= min(o, c) <= max(o, c) <= h < float("inf"):
                timestamp = int(local.timestamp()) // 300 * 300_000
                bars.append([timestamp, o, h, l, c, session, "한국투자증권"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return bars


def ipo_item(code: str, name: str, cfg: dict, now: datetime) -> dict | None:
    """상장 초기 종목 카드(채널을 그릴 일봉이 모자람). 기준선 = 공모가·첫날 시가·상장 뒤 고점/저점, 5분봉(프리마켓·정규장·애프터마켓).
    해석 없이 위치만: 현재가가 공모가·시가 위/아래인지."""
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(code)}?range=5d&interval=5m&includePrePost=true"
    r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read())["chart"]["result"][0]
    m, q = r["meta"], r["indicators"]["quote"][0]
    ny_tz = ZoneInfo("America/New_York")
    bars5 = []
    for t, o, h, l, cl in zip(r.get("timestamp") or [], q["open"], q["high"], q["low"], q["close"]):
        if None not in (o, h, l, cl) and h > 0:
            local = datetime.fromtimestamp(t, ny_tz)
            minute = local.hour * 60 + local.minute
            if local.weekday() >= 5 or not 240 <= minute < 1200:
                continue
            session = "pre" if minute < 570 else "reg" if minute < 960 else "post"
            bars5.append([int(t) * 1000, round(o, 4), round(h, 4), round(l, 4), round(cl, 4), session])
    px = m.get("regularMarketPrice")
    regular = [bar for bar in bars5 if bar[5] == "reg"]
    if not px or not regular:
        return None
    ipo_px = float(cfg["ipo_px"])
    first = next((b for b in regular if b[1] != ipo_px or b[2] != ipo_px), regular[0])   # 상장 전 자리표시 봉(공모가 고정) 건너뜀
    live_bars = [b for b in bars5 if b[0] >= first[0]]
    regular = [bar for bar in regular if bar[0] >= first[0]]
    by_time = {bar[0]: [*bar, "Yahoo Finance"] for bar in live_bars}
    for bar in ipo_broker_extended_bars(code, ny_tz):
        if bar[0] >= first[0]:
            by_time[bar[0]] = bar
    live_bars = [by_time[t] for t in sorted(by_time)]
    hi = max(bar[2] for bar in regular)
    lo = min(bar[3] for bar in regular)
    open1, base = first[1], {}
    try:                                                    # 11/28: 첫 시가·고점/저점은 5일 창이 아니라 상장일부터
        base = ipo_base(code, cfg.get("listed"), now.astimezone(ny_tz).strftime("%Y-%m-%d"))
        if base.get("open1"):
            open1 = base["open1"]
            hi, lo = max(hi, base["hi"]), min(lo, base["lo"])
    except Exception as x:  # noqa: BLE001
        ERRS.append(f"{code} 상장일 일봉 {type(x).__name__}")
    prev = ipo_prev_close(m, regular, ny_tz, ipo_px)
    pos = "공모가 위" if px > ipo_px else "공모가 아래"
    pos += " · 첫 시가 위" if px > open1 else " · 첫 시가 아래"
    age = now.timestamp() - (m.get("regularMarketTime") or 0)
    day = datetime.fromtimestamp(m.get("regularMarketTime") or regular[-1][0] / 1000, ny_tz).strftime("%m/%d")   # 11/28: 화면 휴장·대기 판정용 거래일
    return {"code": code, "name": name, "ipo": True, "day": day, "px": px, "chg": round((px / prev - 1) * 100, 2), "chg_basis": "전일 종가(상장일은 공모가)",
            "prev_close": round(prev, 4), "ipo_px": ipo_px, "open1": open1, "open1_day": base.get("open1_day"), "hi": hi, "lo": lo, "vs_ipo": round((px / ipo_px - 1) * 100, 2),
            "vs_open1": round((px / open1 - 1) * 100, 2), "from_hi": round((px / hi - 1) * 100, 2), "dd": round((px / hi - 1) * 100, 2),
            "listed": cfg.get("listed"), "note": cfg.get("note", ""), "state": pos, "live": age < 600, "bars": live_bars[-160:],
            "source": "Yahoo 5분봉 · 현재가", "source_at": int((m.get("regularMarketTime") or 0) * 1000)}


def sector_view(items: list[dict]) -> dict:
    """운영자 11/19: 대장만 갈 수 없다 — 섹터 돌파는 가장 약한 종목까지 돌파해야 인정.
    가장 약한 종목 = 채널 상단(+1%)·수평 저항 중 높은 쪽까지 거리가 가장 먼 종목."""
    def need(it):                                          # 돌파까지 남은 거리(%)
        lines = [it["up_now"] * 1.01] + ([it["res_h"]] if it.get("res_h") else [])
        return (max(lines) / it["px"] - 1) * 100
    lag = max(items, key=need)
    ok = sum(1 for it in items if it["state"] in ("돌파 확인", "돌파 시도(장중)"))
    if ok == len(items):
        st = "섹터 돌파 확인" if all(it["state"] == "돌파 확인" for it in items) else "섹터 돌파 시도(장중)"
    else:
        st = "섹터 돌파 아님"
    return {"state": st, "broke": ok, "total": len(items), "laggard": lag["name"], "laggard_code": lag["code"],
            "laggard_need": round(need(lag), 2)}


def _fmt(cc: str, v: float) -> str:
    if cc in ("hk", "cn"):
        return f"HK${v:,.2f}" if cc == "hk" else f"{v:,.2f}위안"
    if cc == "tw":
        return f"NT${v:,.2f}"
    if cc == "kr_index":
        return f"{v:,.2f}pt"
    return f"${v:,.2f}" if cc == "us" else (f"{v:,.0f}엔" if cc == "jp" else f"{v:,.0f}원")


def _ro(s: str) -> str:
    """조사 '(으)로': 원·엔은 받침이 있어 '으로'(11/19 '6,710엔로' 오타)."""
    return s + ("으로" if s.endswith(("원", "엔")) else "로")


def _josa(t: str) -> str:
    """'712,000원가'·'716,000원는' → '원이'·'원은'(받침 있는 원·엔 뒤 조사)."""
    import re as _re
    return _re.sub(r"(\d)(원|엔)(가|는|를|로)(?=[\s,·(])", lambda m: m.group(1) + m.group(2) + {"가": "이", "는": "은", "를": "을", "로": "으로"}[m.group(3)], t)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    r = build()
    for g in r["groups"]:
        print(f"\n[{g['country']} · {g['sector']}]")
        for it in g["items"]:
            if "day" not in it:                           # 상장 초기 카드(ANT 등)는 채널 값이 없다(11/20 KeyError)
                print(f"  {it.get('name')} · {it.get('state', '')} {it.get('px', '')}")
                continue
            change = f"{it['chg']:+.2f}%" if it["chg"] is not None else "확인 중"
            print(f"  {it['rank']}. {it['name']} {it['day']} {it['px']:,.2f} ({change}) · {it['state']} · 상단 {it['up_now']:,.2f} 5일선 {it['ma5']:,.2f} · 다음 상단까지 {it['gap_next']:+.1f}% · 캔들 {it['candle']['name']}{' (진행 중)' if it['live'] else ''}")
    print("\n기록:", *[e["text"] for e in r["log"][:5]], sep="\n  ")
