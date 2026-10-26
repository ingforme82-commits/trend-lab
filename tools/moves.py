"""변곡점(평소보다 크게 움직이기 시작한 구간) 감지 + 직전 뉴스 연결.

- 1분봉 24시간: 하이퍼리퀴드(나스닥100·코스피200·WTI·브렌트·금), 야후(미 10년물 금리 ^TNX, 달러인덱스 DXY)
- 10분 변화가 '평소 10분 변화폭(중앙값 기준)의 3배'와 '자산별 최소 기준'을 동시에 넘으면 급변 분으로 본다.
- 이어지는 급변 분을 하나의 구간으로 묶고, 그 직전 저점(상승)·고점(하락)을 변곡점으로 잡는다.
- 변곡점 15분 전 ~ 3분 뒤에 나온 뉴스 중 관련성이 높은 것(최대 3건)을 '직전 뉴스 후보'로 붙인다.
인과관계를 단정하지 않는다 — 화면에는 '시각이 겹친 뉴스'로만 표시한다.
"""

from __future__ import annotations

import json
import statistics
import urllib.request
from datetime import datetime, timezone

# (코드, 이름, 출처, 심볼, 단위, 10분 최소 기준, 관련 태그)
ASSETS = [
    ("NQ", "나스닥100", "hl", "xyz:XYZ100", "pct", 0.50, ("AI·빅테크", "반도체", "지수", "연준·금리")),
    ("K200", "코스피200", "hl", "xyz:KR200", "pct", 0.60, ("한국", "반도체", "지수")),
    ("WTI", "WTI", "hl", "xyz:CL", "pct", 0.80, ("중동·유가", "러·우")),
    ("BRENT", "브렌트", "hl", "xyz:BRENTOIL", "pct", 0.80, ("중동·유가", "러·우")),
    ("GOLD", "금", "hl", "xyz:GOLD", "pct", 0.45, ("연준·금리", "중동·유가")),
    ("US10Y", "미 10년물 금리", "yf", "^TNX", "bp", 4.0, ("연준·금리",)),
    ("DXY", "달러인덱스", "yf", "DX-Y.NYB", "pct", 0.20, ("연준·금리",)),
]
WIN = 10            # 분
SIGMA = 4.0
BEFORE, AFTER = 15, 3   # 변곡점 기준 뉴스 찾는 범위(분)


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
    for win, mult in ((WIN, 1.0), (30, 1.6)):
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


def _move_between(rows, t0, t1, unit):
    a = next((c for t, c in reversed(rows) if t <= t0), None)
    b = next((c for t, c in reversed(rows) if t <= t1), None)
    return round(_chg(a, b, unit), 2) if a and b else None


def analyze(items: list[dict]) -> tuple[list[dict], dict]:
    """변곡점 목록을 만들고, 직전 뉴스 후보에 pivot 표시를 단다. 반환: (moves, 5분 간격 시계열(금리·달러))"""
    data = {a[0]: fetch(a) for a in ASSETS}
    moves = []
    for a in ASSETS:
        eps = sorted(detect(a, data[a[0]]), key=lambda m: m["start"])
        merged: list[dict] = []
        for m in eps:                                     # 같은 방향으로 겹치는 구간은 하나로(큰 쪽 기준)
            p = merged[-1] if merged else None
            if p and (m["move"] > 0) == (p["move"] > 0) and m["start"] <= p["end"] + 2 * 60_000:
                big = m if abs(m["move"]) > abs(p["move"]) else p
                merged[-1] = {**big, "start": min(p["start"], m["start"]), "end": max(p["end"], m["end"])}
            else:
                merged.append(m)
        moves += merged
    moves.sort(key=lambda m: -m["start"])
    for k, m in enumerate(moves):
        m["id"] = f'{m["asset"]}-{m["start"] // 60000}'
        a = next(x for x in ASSETS if x[0] == m["asset"])
        rel = a[6]
        # 같은 구간 다른 자산의 변화(시장 전체가 움직였는지 보기)
        m["others"] = {x[1]: v for x in ASSETS if x[0] != m["asset"]
                       for v in [_move_between(data[x[0]], m["start"], m["end"], x[4])] if v is not None}
        cands = []
        for it in items:
            dt = (it["ts"] - m["start"]) / 60000
            match = sum(t in rel for t in it.get("tags", []))
            if -BEFORE <= dt <= AFTER and match:          # 그 자산과 관련된 분야의 뉴스만 후보
                score = 3 * match + (1 if it.get("hot") else 0) + (1 - abs(dt) / 20)
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
        m["items"] = [{k: it[k] for k in ("ts", "text", "src", "lang", "osrc") if k in it} for it in picked]   # 화면 표시용(같은 시각 다른 기사 구분)
        for it in picked:
            it["pivot"] = True
            unit = "bp" if m["unit"] == "bp" else "%"
            tag = f'{m["name"]} {"+" if m["move"] > 0 else ""}{m["move"]}{unit}'
            it.setdefault("pv", [])
            if tag not in it["pv"]:
                it["pv"].append(tag)
    # 화면용: 금리·달러 5분 간격 시계열(하이퍼리퀴드에 없는 것)
    series = {}
    for code in ("US10Y", "DXY"):
        rows = data[code]
        series[code] = [[t, round(c, 4)] for t, c in rows if (t // 60000) % 5 == 0]
    return moves[:40], series
