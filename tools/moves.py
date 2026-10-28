"""변곡점(평소보다 크게 움직이기 시작한 구간) 감지 + 직전 뉴스 연결.

- 1분봉 24시간: 하이퍼리퀴드(나스닥100·코스피200·WTI·브렌트·금), 야후(미 10년물 금리 ^TNX, 달러인덱스 DXY)
- 5·10·30분 변화가 평소 변화폭(중앙값)의 4배와 자산별 최소 기준을 동시에 넘으면 급변으로 본다.
- WTI·브렌트는 60분 1.5% 또는 180분 2.5% 이상인 방향성 있는 누적 움직임도 찾는다.
- 이어지는 급변 분을 하나의 구간으로 묶고, 그 직전 저점(상승)·고점(하락)을 변곡점으로 잡는다.
- 시작 15분 전부터 급변 구간(최대 30분), 누적 움직임은 구간 끝까지 관련 뉴스 후보를 최대 3건 연결한다.
인과관계를 단정하지 않는다 — 화면에는 '시각이 겹친 뉴스'로만 표시한다.
"""

from __future__ import annotations

import json
import re
import statistics
import urllib.request
from datetime import datetime, timezone

# (코드, 이름, 출처, 심볼, 단위, 10분 최소 기준, 관련 태그)
ASSETS = [
    ("NQ", "나스닥100", "hl", "xyz:XYZ100", "pct", 0.50, ("AI·빅테크", "반도체", "지수", "연준·금리", "사이버보안", "원전")),
    ("SP", "S&P500", "hl", "xyz:SP500", "pct", 0.40, ("AI·빅테크", "반도체", "지수", "연준·금리", "원전", "중동·유가")),
    ("K200", "코스피200", "hl", "xyz:KR200", "pct", 0.60, ("한국", "반도체", "지수", "원전", "방산", "2차전지", "조선")),
    ("WTI", "WTI", "hl", "xyz:CL", "pct", 0.80, ("중동·유가", "러·우")),
    ("BRENT", "브렌트", "hl", "xyz:BRENTOIL", "pct", 0.80, ("중동·유가", "러·우")),
    ("GOLD", "금", "hl", "xyz:GOLD", "pct", 0.45, ("연준·금리", "중동·유가")),
    ("US10Y", "미 10년물 금리", "yf", "^TNX", "bp", 4.0, ("연준·금리",)),
    ("DXY", "달러인덱스", "yf", "DX-Y.NYB", "pct", 0.20, ("연준·금리",)),
]
WIN = 10            # 분
US_A, KR_A = {"NQ", "SP"}, {"K200"}
US_RX = re.compile(r"미국|나스닥|S&P|다우|뉴욕|월가|연준|파월|엔비디아|브로드컴|인텔|AMD|마이크론|테슬라|애플|오클로|뉴스케일|"
                   r"\$[A-Z]{1,5}\b|Nasdaq|Wall Street|\bFed\b|NYSE")
KR_RX = re.compile(r"코스피|코스닥|한국|국내|삼성|하이닉스|한은|원/달러|원화|KOSPI|KOSDAQ|Korea|외국인|기관|국민성장")


KEY_RX = re.compile(r"트럼프|Trump|파월|Powell|OPEC|오펙|사우디|빈 살만|이란|하메네이|네타냐후|푸틴|시진핑|백악관|재무장관|베선트|연준|Fed\b")


def region(it: dict) -> str:
    """뉴스 지역: 'US' / 'KR' / ''(둘 다 또는 판단 불가). 섹터 시세는 섹터 이름으로."""
    t = it.get("text", "")
    if it.get("kind") == "섹터 시세":
        return "US" if "미국" in t[:12] else "KR"
    us, kr = bool(US_RX.search(t)), bool(KR_RX.search(t))
    return "US" if us and not kr else "KR" if kr and not us else ""


def session_of(code: str, ts: int) -> str:
    """그 시각의 거래 시간대(한국 시각 기준, 미국은 서머타임 자동)."""
    from zoneinfo import ZoneInfo
    k = datetime.fromtimestamp(ts / 1000, ZoneInfo("Asia/Seoul"))
    km = k.hour * 60 + k.minute
    if code == "K200":
        if k.weekday() < 5 and 9 * 60 <= km < 15 * 60 + 30:
            return "정규장"
        if (k.weekday() < 5 and km >= 18 * 60) or (k.weekday() in (1, 2, 3, 4, 5) and km < 5 * 60):
            return "야간선물 시간"
        return "장외(24시간 지수)"
    if code in US_A:
        n = datetime.fromtimestamp(ts / 1000, ZoneInfo("America/New_York"))
        nm = n.hour * 60 + n.minute
        if n.weekday() < 5 and 9 * 60 + 30 <= nm < 16 * 60:
            return "미국 정규장"
        if n.weekday() < 5 and 4 * 60 <= nm < 9 * 60 + 30:
            return "프리마켓"
        if n.weekday() < 5 and 16 * 60 <= nm < 20 * 60:
            return "애프터마켓"
        return "선물 야간(24시간)"
    return "24시간" if code in ("WTI", "BRENT", "GOLD") else ""


def us_open_gap(ts: int) -> int | None:
    """미국 정규장 개장(09:30 ET) 뒤 0~15분이면 그 분, 아니면 None."""
    from zoneinfo import ZoneInfo
    n = datetime.fromtimestamp(ts / 1000, ZoneInfo("America/New_York"))
    d = n.hour * 60 + n.minute - (9 * 60 + 30)
    return d if n.weekday() < 5 and 0 <= d <= 15 else None


def group_moments(moves: list[dict], gap_min: int = 6) -> None:
    """시작 시각이 gap_min 분 안인 변곡점끼리 같은 '순간'(grp)으로 묶는다(제자리 수정)."""
    for m in sorted(moves, key=lambda m: m["start"]):
        m.pop("grp", None)
    cur, anchor = None, None
    for m in sorted(moves, key=lambda m: m["start"]):
        if anchor is None or m["start"] - anchor > gap_min * 60_000:
            cur, anchor = m["id"], m["start"]
        m["grp"] = cur
SIGMA = 4.0
BEFORE, AFTER = 15, 3   # 변곡점 기준 뉴스 찾는 범위(분) — 움직임이 이어지는 동안(최대 AFTER_MAX분)도 본다
AFTER_MAX = 30
# 주요 가격대(이 단위의 배수를 3분 넘게 넘어서 유지하면 '가격대 돌파'로 기록)
LEVEL_STEP = {"WTI": 5, "BRENT": 5, "GOLD": 100, "NQ": 1000, "SP": 100, "K200": 50, "US10Y": 0.1, "DXY": 1}
LEVEL_HOLD = 3          # 분
LEVEL_BUF = 0.1         # % — 기준선을 이만큼 넘어야 돌파로 인정(기준선 근처 오르내림 거르기)
LEVEL_GAP = 60          # 분 — 같은 가격대를 이 시간 안에 다시 넘으면 가장 최근 돌파만 남긴다


def level_cross(code: str, name: str, unit: str, rows: list[tuple[int, float]], hold: int = LEVEL_HOLD) -> list[dict]:
    """주요 가격대(LEVEL_STEP 배수) 돌파: 기준선을 넘은 뒤 hold분 동안 다시 돌아오지 않으면 기록."""
    step = LEVEL_STEP.get(code)
    if not step or len(rows) < hold + 2:
        return []
    out, i = [], 1
    while i < len(rows) - hold:
        a, b = rows[i - 1][1], rows[i][1]
        lo, hi = min(a, b), max(a, b)
        k = int(hi // step) * step if hi % step else hi
        if lo < k <= hi and k > 0:                       # a→b 사이에 기준선 k 가 있다
            up = b >= k > a
            win = [c for _, c in rows[i:i + hold + 1]]
            buf = k * LEVEL_BUF / 100 if unit != "bp" else 0.01
            beyond = max(win) >= k + buf if up else min(win) <= k - buf
            if all((c >= k) == up for c in win) and beyond:
                lv = round(k, 4)
                out = [o for o in out if not (o["level"] == lv and rows[i][0] - o["start"] < LEVEL_GAP * 60_000)]   # 같은 가격대를 다시 넘으면 최근 것만
                out.append({"asset": code, "name": name, "unit": unit, "kind": "level", "level": lv, "start": rows[i][0],
                            "end": rows[i + hold][0], "from": a, "to": rows[i + hold][1],
                            "move": round(_chg(a, rows[i + hold][1], unit), 2), "ratio": 0.0})
                i += hold
        i += 1
    return out


def _post(body: dict):
    req = urllib.request.Request("https://api.hyperliquid.xyz/info", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def fetch(asset) -> list[tuple[int, float]]:
    code, _, src, sym, *_ = asset
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    try:
        if src == "hl":
            d = _post({"type": "candleSnapshot", "req": {"coin": sym, "interval": "1m", "startTime": now - 24 * 3600_000, "endTime": now}})
            return [(int(c["t"]), float(c["c"])) for c in d]
        u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range=2d&interval=1m"
        j = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read())
        r = j["chart"]["result"][0]
        rows = [(t * 1000, c) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]
        return [x for x in rows if x[0] >= now - 24 * 3600_000]
    except Exception:  # noqa: BLE001
        return []


def _chg(a: float, b: float, unit: str) -> float:
    return (b - a) * 100 if unit == "bp" else (b / a - 1) * 100


def _returns(rows, win: int) -> list[float]:
    out = []
    for i in range(len(rows)):
        j = i - win
        # 1분봉이 비어 있는 구간(장 마감 등)은 시간으로 맞춘다
        while j > 0 and rows[i][0] - rows[j][0] > win * 60_000 * 1.5:
            j += 1
        out.append(rows[j] if 0 <= j < i else None)
    return out


def detect(asset, rows: list[tuple[int, float]]) -> list[dict]:
    """10분(갑자기 튐)과 30분(계단식으로 밀어 올림) 두 기준으로 급변 분을 찾는다."""
    code, name, _, _, unit, floor, _ = asset
    if len(rows) < 60:
        return []
    flags: dict[int, tuple[bool, int, float]] = {}       # i → (상승?, 기준창, 평소폭)
    for win, mult in ((5, 0.6), (WIN, 1.0), (30, 1.6)):   # 5분(짧고 급한 움직임)·10분·30분
        base = _returns(rows, win)
        rets = [_chg(b[1], rows[i][1], unit) if b else 0.0 for i, b in enumerate(base)]
        absr = [abs(x) for x in rets if x]
        if not absr:
            continue
        mad = statistics.median(absr) or 1e-9
        thr = max(SIGMA * mad, floor * mult)
        for i, r in enumerate(rets):
            if abs(r) >= thr and i not in flags:
                flags[i] = (r > 0, win, mad)
    flagged = sorted(flags)
    eps, cur = [], []
    for i in flagged:
        if cur and (rows[i][0] - rows[cur[-1]][0] > 8 * 60_000 or flags[i][0] != flags[cur[0]][0]):
            eps.append(cur)                               # 8분 넘게 쉬거나 방향이 바뀌면 다른 구간
            cur = []
        cur.append(i)
    if cur:
        eps.append(cur)
    out = []
    for ep in eps:
        f, l = ep[0], ep[-1]
        up, win, mad = flags[f]
        lo = max(0, f - win)
        seg = rows[lo:f + 1]
        s_i = lo + (min(range(len(seg)), key=lambda k: seg[k][1]) if up else max(range(len(seg)), key=lambda k: seg[k][1]))
        seg2 = rows[f:l + 1]
        e_i = f + (max(range(len(seg2)), key=lambda k: seg2[k][1]) if up else min(range(len(seg2)), key=lambda k: seg2[k][1]))
        mv = _chg(rows[s_i][1], rows[e_i][1], unit)
        if abs(mv) < floor:
            continue
        out.append({"asset": code, "name": name, "unit": unit, "start": rows[s_i][0], "end": rows[e_i][0],
                    "from": rows[s_i][1], "to": rows[e_i][1], "move": round(mv, 2), "ratio": round(abs(mv) / mad, 1)})
    return out


# 유가 누적 움직임은 평소폭 배수 대신 절대 변화율과 방향성을 확인한다.
OIL_TREND_WINDOWS = ((60, 1.5), (180, 2.5))


def merge_moves(events: list[dict]) -> list[dict]:
    """같은 방향의 겹친 신호를 통합하고 시작·끝 가격에 맞게 변화율을 계산한다."""
    out = []
    for m in sorted(events, key=lambda x: (x["start"], x["end"])):
        p = out[-1] if out else None
        if p and (m["move"] > 0) == (p["move"] > 0) and m["start"] <= p["end"] + 2 * 60_000:
            last = p if p["end"] >= m["end"] else m
            out[-1] = {**p, "end": last["end"], "to": last["to"],
                       "move": round(_chg(p["from"], last["to"], m["unit"]), 2),
                       "ratio": max(p["ratio"], m["ratio"])}
            if p.get("kind") == "cumulative" or m.get("kind") == "cumulative":
                out[-1]["kind"] = "cumulative"
        else:
            out.append(dict(m))
    return out


def cumulative_moves(asset, rows: list[tuple[int, float]]) -> list[dict]:
    """유가 1·3시간 누적 등락. 데이터 공백과 방향성 없는 왕복 등락은 제외한다."""
    code, name, _, _, unit, _, _ = asset
    if code not in ("WTI", "BRENT"):
        return []
    out = []
    for i in range(1, len(rows)):
        for minutes, threshold in OIL_TREND_WINDOWS:
            j = i - minutes
            if j < 0:
                continue
            segment = rows[j:i + 1]
            elapsed = (segment[-1][0] - segment[0][0]) / 60_000
            if not minutes - 1 <= elapsed <= minutes + 1:
                continue
            if any(b[0] - a[0] > 2 * 60_000 or b[0] <= a[0] or a[1] <= 0 or b[1] <= 0
                   for a, b in zip(segment, segment[1:])):
                continue
            change = _chg(segment[0][1], segment[-1][1], unit)
            path = sum(abs(b[1] - a[1]) for a, b in zip(segment, segment[1:]))
            efficiency = abs(segment[-1][1] - segment[0][1]) / path if path else 0
            if abs(change) + 1e-9 < threshold or efficiency < 0.6:
                continue
            event = {"asset": code, "name": name, "unit": unit, "kind": "cumulative",
                     "start": segment[0][0], "end": segment[-1][0],
                     "from": segment[0][1], "to": segment[-1][1],
                     "move": round(change, 2), "ratio": 0.0}
            if out and event["start"] <= out[-1]["end"]:
                previous = out[-1]
                if (change > 0) == (previous["move"] > 0) and event["end"] - previous["start"] <= 180 * 60_000:
                    out[-1] = {**previous, "end": event["end"], "to": event["to"],
                               "move": round(_chg(previous["from"], event["to"], unit), 2)}
                continue
            out.append(event)
    return out


def _move_between(rows, t0, t1, unit):
    a = next((c for t, c in reversed(rows) if t <= t0), None)
    b = next((c for t, c in reversed(rows) if t <= t1), None)
    return round(_chg(a, b, unit), 2) if a and b else None


def analyze(items: list[dict]) -> tuple[list[dict], dict]:
    """변곡점 목록을 만들고, 직전 뉴스 후보에 pivot 표시를 단다. 반환: (moves, 5분 간격 시계열(금리·달러))"""
    data = {a[0]: fetch(a) for a in ASSETS}
    moves = []
    for a in ASSETS:
        rows = data[a[0]]
        moves += merge_moves(detect(a, rows) + cumulative_moves(a, rows))
        moves += level_cross(a[0], a[1], a[4], data[a[0]])   # 주요 가격대 돌파(예: WTI $100)
    moves.sort(key=lambda m: -m["start"])
    for k, m in enumerate(moves):
        m["id"] = f'{m["asset"]}-{"L" if m.get("kind") == "level" else "C" if m.get("kind") == "cumulative" else ""}{m["start"] // 60000}'
        m["session"] = session_of(m["asset"], m["start"])
        if m["asset"] not in US_A and us_open_gap(m["start"]) is not None:
            m["session"] += " · 미국 개장 직후"
        a = next(x for x in ASSETS if x[0] == m["asset"])
        rel = a[6]
        # 같은 구간 다른 자산의 변화(시장 전체가 움직였는지 보기)
        m["others"] = {x[1]: v for x in ASSETS if x[0] != m["asset"]
                       for v in [_move_between(data[x[0]], m["start"], m["end"], x[4])] if v is not None}
        cands = []
        after = ((m["end"] - m["start"]) / 60000 if m.get("kind") == "cumulative"
                 else max(AFTER, min(AFTER_MAX, (m["end"] - m["start"]) / 60000 + 3)))   # 움직이는 동안 나온 뉴스도
        for it in items:
            dt = (it["ts"] - m["start"]) / 60000
            if it.get("kind") in ("시황 분석", "증권사 시황", "관전 포인트", "섹터 시세"):   # 긴 분석 글·가격에서 만든 자동 집계는 뺀다
                continue
            rg = region(it)
            if (m["asset"] in KR_A and rg != "KR") or (m["asset"] in US_A and rg == "KR"):
                continue                                  # 코스피200은 한국 관련어가 확인된 뉴스만, 미국 지수엔 한국 뉴스 제외
            match = sum(t in rel for t in it.get("tags", []))
            if -BEFORE <= dt <= after and match:          # 그 자산과 관련된 분야의 뉴스만 후보
                score = 3 * match + (1 if it.get("hot") else 0) + (1 - abs(dt) / max(30, after)) + (1 if KEY_RX.search(it["text"]) else 0)
                if it.get("kind") in ("증권사 시황", "시황 분석"):
                    score -= 2                          # 긴 분석 글보다 속보가 직접 원인일 가능성이 높다
                cands.append((score, it))
        cands.sort(key=lambda x: -x[0])
        picked, seen_txt = [], set()
        for sc, it in cands:
            if sc > 0.5 and it["text"] not in seen_txt:
                picked.append(it)
                seen_txt.add(it["text"])
            if len(picked) >= 3:
                break
        m["news"] = [it["ts"] for it in picked]
        m["items"] = [{**{k: it[k] for k in ("ts", "text", "src", "lang", "osrc") if k in it},
                       "lag": round((it["ts"] - m["start"]) / 60000)} for it in picked]   # lag: 움직임 시작 대비 분(음수 = 뉴스가 먼저)
        for it in picked:
            it["pivot"] = True
            unit = "bp" if m["unit"] == "bp" else "%"
            tag = f'{m["name"]} {"+" if m["move"] > 0 else ""}{m["move"]}{unit}'
            it.setdefault("pv", [])
            if tag not in it["pv"]:
                it["pv"].append(tag)
    group_moments(moves)
    # 화면용: 금리·달러 5분 간격 시계열(하이퍼리퀴드에 없는 것)
    series = {}
    for code in ("US10Y", "DXY"):
        rows = data[code]
        series[code] = [[t, round(c, 4)] for t, c in rows if (t // 60000) % 5 == 0]
    return moves[:40], series
