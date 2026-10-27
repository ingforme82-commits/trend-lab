"""🌙 저녁 점검(넥스트레이드 마감 후 ~ 미국 개장 전): 24시간 선물·유가 시황 자료. brief_slot.py 2005 / 2215 에서 사용.

- 선물(하이퍼리퀴드 24시간): S&P500·나스닥100·코스피200·삼성전자·SK하이닉스·니케이 — 미국 정규장 종가 대비, 한국장 마감(15:30) 이후, 넥장 마감(20:00) 이후, 최근 1시간
- 유가·금·달러: WTI·브렌트·금·달러인덱스·원/달러 — 24시간, 15:30 이후, 최근 1시간, 15:30 이후 고가·저가
- 넥스트레이드 애프터마켓 종가(삼성전자·SK하이닉스 + 수급 칸 거래대금 상위)
- 유가·중동 속보(최근 12시간), 오늘 밤 일정(체크포인트 ~ 다음 날 07:00)
수치·출처만 담는다(해석·추천 없음, AI 문장 생성 없음).
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
HL = "https://api.hyperliquid.xyz/info"
IDX = [("xyz:SP500", "S&P500", "", "SP500"), ("xyz:XYZ100", "나스닥100", "", "XYZ100"), ("xyz:KR200", "코스피200", "", None),
       ("xyz:SMSN", "삼성전자", "$", None), ("xyz:SKHX", "SK하이닉스", "$", None), ("xyz:JP225", "니케이225", "", None)]
OIL = [("xyz:CL", "WTI", "$"), ("xyz:BRENTOIL", "브렌트", "$"), ("xyz:GOLD", "금", "$"), ("xyz:DXY", "달러인덱스", ""), ("xyz:KRW", "원/달러", "원")]
NXT_BASE = {"005930": "삼성전자", "000660": "SK하이닉스"}


def _post(body: dict):
    req = urllib.request.Request(HL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def candles(coin: str, start_ms: int, end_ms: int) -> list[dict]:
    try:
        return _post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "5m", "startTime": start_ms, "endTime": end_ms}})
    except Exception:  # noqa: BLE001
        return []


# ── 순수 함수(tests/test_evening.py) ──
def price_at(cs: list[dict], ts: int) -> float | None:
    """ts 시각의 가격 = ts 직전에 끝난 5분봉의 종가(없으면 None)."""
    done = [c for c in cs if c["T"] < ts]
    return float(done[-1]["c"]) if done else None


def pct(a: float | None, b: float | None) -> float | None:
    return round((a / b - 1) * 100, 2) if a and b else None


def metrics(cs: list[dict], px: float, marks: dict[str, int], since: int) -> dict:
    """현재가 px 의 각 기준 시각 대비 등락률 + since 이후 고가·저가."""
    out = {k: pct(px, price_at(cs, t)) for k, t in marks.items()}
    rng = [c for c in cs if c["t"] >= since]
    if rng:
        out["hi"] = max(float(c["h"]) for c in rng)
        out["lo"] = min(float(c["l"]) for c in rng)
    return out


def tonight(cps: list[dict], now: datetime) -> list[dict]:
    """체크포인트 중 지금 ~ 다음 날 07:00 일정(오늘 '종일' 일정 포함)."""
    end = (now + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0) if now.hour >= 7 else now.replace(hour=7, minute=0)
    out = []
    for c in cps:
        if c.get("time"):
            try:
                t = datetime.strptime(f"{c['date']} {c['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)
            except ValueError:
                continue
            if now <= t < end:
                out.append({"time": f"{t.month}/{t.day} {c['time']}" if t.date() != now.date() else c["time"], "title": c["title"], "t": t.timestamp()})
        elif c.get("date") == now.strftime("%Y-%m-%d"):
            out.append({"time": "종일", "title": c["title"], "t": 0})
    return [{"time": x["time"], "title": x["title"]} for x in sorted(out, key=lambda x: x["t"])][:8]


def oil_heads(items: list[dict], now_ms: int) -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from newsgroup import bigrams, similar
    out, seen, grams = [], set(), []
    for it in sorted(items, key=lambda x: -x["ts"]):
        if now_ms - it["ts"] > 12 * 3600_000 or "중동·유가" not in (it.get("tags") or []) or it.get("kind") in ("증권사 시황", "시황 분석"):
            continue
        key = "".join(ch for ch in it["text"] if ch.isalnum())[:14]
        g = bigrams(it["text"])
        who = it["text"].split(":")[0][:12] if ":" in it["text"][:14] else None
        if key in seen or any(similar(g, x) for x in grams)                 or (who and any(o["text"].startswith(who + ":") and o["ts"] - it["ts"] < 15 * 60_000 for o in out)):   # 같은 사건·같은 발언자 15분 안은 최신 한 건만
            continue
        seen.add(key)
        grams.append(g)
        out.append({"ts": it["ts"], "text": it["text"][:120], "src": it.get("osrc") or it.get("src", ""), "verify": it.get("verify", "")})
        if len(out) >= 6:
            break
    return out


def us_open_kst(now: datetime) -> str:
    from zoneinfo import ZoneInfo
    ny = now.astimezone(ZoneInfo("America/New_York"))
    o = ny.replace(hour=9, minute=30, second=0, microsecond=0).astimezone(KST)
    return f"{o.hour:02d}:{o.minute:02d}"


# ── 수집 ──
def nxt(codes: dict[str, str]) -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from krx import BASE, _parse
    out = []
    try:
        get = lambda kind: {d["itemCode"]: d for d in json.loads(urllib.request.urlopen(urllib.request.Request(
            f"{BASE}/{kind}/{','.join(codes)}", headers={"User-Agent": "Mozilla/5.0"}), timeout=8).read()).get("datas", [])}
        krx, nx = get("stock"), get("NXT/stock")
    except Exception:  # noqa: BLE001
        return []
    for code, name in codes.items():
        a, b = krx.get(code), nx.get(code)
        if not a or not b:
            continue
        k, n = _parse(a), _parse(b)
        if not k or not n:
            continue
        kc = float(str(a.get("closePriceRaw") or 0) or 0) or k["px"]
        out.append({"name": name, "px": n["px"], "chg": n["chg"], "vs_krx": pct(n["px"], kc), "status": b.get("marketStatus", ""),
                    "val": n.get("val_krx")})
    return out


def make(d: dict, now: datetime | None = None) -> dict:
    now = (now or datetime.now(KST)).astimezone(KST)
    now_ms = int(now.timestamp() * 1000)
    krc = int(now.replace(hour=15, minute=30, second=0, microsecond=0).timestamp() * 1000)
    nxc = int(now.replace(hour=20, minute=0, second=0, microsecond=0).timestamp() * 1000)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from market_extra import _hl_ctx
    ctx = _hl_ctx()
    reg = d.get("reg") or {}
    start = krc - 30 * 60_000

    def base(coin, name, u):
        x = ctx.get(coin) or {}
        px, prev = float(x.get("markPx") or 0), float(x.get("prevDayPx") or 0)
        if not px:
            return None
        marks = {"kr": krc, "h1": now_ms - 3600_000} | ({"nx": nxc} if now_ms >= nxc + 5 * 60_000 else {})
        return {"name": name, "u": u, "px": px, "d24": pct(px, prev), **metrics(candles(coin, start, now_ms), px, marks, krc)}

    fut = []
    for coin, name, u, rk in IDX:
        r = base(coin, name, u)
        if r:
            if rk and (reg.get(rk) or {}).get("px"):
                r["reg"] = pct(r["px"], reg[rk]["px"])          # 미국 정규장 종가 대비(현물 지수 vs 24시간 선물이라 기초 차이 포함)
            fut.append(r)
    oil = [r for r in (base(c, n, u) for c, n, u in OIL) if r]
    codes = dict(NXT_BASE)
    for g in (d.get("flows") or {}).get("groups", []):
        for r in sorted(g["rows"], key=lambda x: -(x.get("val") or 0))[:3]:
            codes.setdefault(r["code"], r["name"])
    tn = []
    try:
        tn = tonight(json.loads((ROOT / "data" / "checkpoints.json").read_text(encoding="utf-8")), now)
    except Exception:  # noqa: BLE001
        pass
    return {"at": now_ms, "us_open": us_open_kst(now), "fut": fut, "oil": oil, "nxt": nxt(codes),
            "oil_heads": oil_heads(d.get("items") or [], now_ms), "tonight": tn}


def check(e: dict) -> list[str]:
    bad = []
    if sum(1 for r in e.get("fut", []) if r.get("kr") is not None) < 4:
        bad.append("선물 15:30 기준 가격 누락(4종목 미만)")
    if sum(1 for r in e.get("oil", []) if r["name"] in ("WTI", "브렌트") and r.get("kr") is not None) < 2:
        bad.append("유가 시세 누락")
    return bad


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import subprocess
    raw = subprocess.run(["gh", "api", "repos/ingforme82-commits/trend-lab/contents/news.json?ref=live", "-H", "Accept: application/vnd.github.raw"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    e = make(json.loads(raw))
    print(json.dumps(e, ensure_ascii=False, indent=1)[:4000])
    print("check:", check(e))
