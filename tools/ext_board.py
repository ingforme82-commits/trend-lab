"""🌙 미국 시간외 시세판(프리마켓·애프터마켓) + 큰 움직임 속보(2026-11-02 운영자 요청).

- 값: tools/extended.py quote()(NH 해외주식 현재가 먼저, 실패 시 야후 1분봉 마지막 체결, 정규장 종가 대비). 지수는 시간외 거래가 없어 ETF(SPY·QQQ)로 본다.
- 대상: 주요 ETF·대형주(BOARD) + 🔥 화제 종목(spot)의 미국 종목.
- 1분마다만 새로 받는다(tools/ext_board_cache.json).
- 시간외 체결이 정규장 종가 대비 ±5%·±10%를 처음 넘으면 그 시각으로 속보 1건(같은 종목·같은 세션·같은 단계는 한 번만, tools/ext_board_state.json).
- 사실·수치만. 하이퍼리퀴드 24시간 가격과 섞지 않는다.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CACHE = TOOLS / "ext_board_cache.json"
STATE = TOOLS / "ext_board_state.json"
KST = timezone(timedelta(hours=9))
TTL = 50
STEPS = (5.0, 10.0)
SESS = {"pre": "프리마켓", "post": "애프터마켓", "day": "주간거래"}

BOARD = [("SPY", "S&P500 ETF"), ("QQQ", "나스닥100 ETF"), ("SOXX", "반도체 ETF"), ("SOXL", "반도체 3배"), ("EWY", "한국 ETF"), ("KORU", "한국 3배"),
         ("NVDA", "엔비디아"), ("AAPL", "애플"), ("MSFT", "마이크로소프트"), ("GOOGL", "알파벳"), ("AMZN", "아마존"), ("META", "메타"),
         ("TSLA", "테슬라"), ("AVGO", "브로드컴"), ("AMD", "AMD"), ("MU", "마이크론"), ("INTC", "인텔"), ("TSM", "TSMC")]


def events(rows: list[dict], state: dict, now: float) -> list[dict]:
    """rows 중 live 시간외 등락이 STEPS 를 처음 넘은 것 → state 에 기록(순수에 가깝게: state 를 고쳐 쓴다). 새로 생긴 키 목록을 돌려준다."""
    # 11/12: 시간외 한 번 튄 체결(MSFT -15% 등 잘못된 값)로 속보가 나간 일 → 다음 갱신(≥50초 뒤)에도 같은 방향으로 넘어 있어야 확정
    pend = state.setdefault("_pending", {})
    new = []
    for r in rows:
        if not r.get("live") or r.get("stale"):
            continue
        day = datetime.fromtimestamp(r["at"] / 1000, KST).strftime("%Y-%m-%d")
        for s in STEPS:
            k = f"{r['sym']}-{r['sess']}-{day}-{int(s)}"
            if abs(r["chg"]) < s or k in state:
                if abs(r["chg"]) < s:
                    pend.pop(k, None)
                continue
            p = pend.get(k)
            if p and now - p["seen"] >= TTL and (p["chg"] > 0) == (r["chg"] > 0):
                state[k] = {"ts": p["ts"], "sym": r["sym"], "name": r["name"], "sess": r["sess"], "px": r["px"], "base": r["base"], "chg": r["chg"], "step": s}
                pend.pop(k, None)
                new.append(k)
            elif not p or (p["chg"] > 0) != (r["chg"] > 0):
                pend[k] = {"seen": now, "ts": r["at"], "chg": r["chg"]}
    for k in [k for k, v in pend.items() if now - v["seen"] > 600]:
        pend.pop(k)
    for k in [k for k, v in state.items() if k != "_pending" and now * 1000 - v["ts"] > 36 * 3600_000]:
        state.pop(k)
    return new


def items_of(state: dict) -> list[dict]:
    """state → 속보 목록용 항목(같은 종목·세션은 가장 높은 단계 하나만)."""
    best = {}
    for k, v in state.items():
        if k == "_pending":
            continue
        key = (v["sym"], v["sess"], datetime.fromtimestamp(v["ts"] / 1000, KST).date())
        if key not in best or v["step"] > best[key]["step"]:
            best[key] = v
    out = []
    for v in best.values():
        up = v["chg"] > 0
        out.append({"ts": v["ts"], "got": v["ts"], "src": "트렌드랩 자동 집계", "kind": "시간외 시세", "hot": v["step"] >= 10,
                    "tags": ["시간외"], "text": f"🌙 {SESS.get(v['sess'], '시간외')} {v['name']}({v['sym']}) {'+' if up else ''}{v['chg']:.2f}% "
                    f"${v['px']:,.2f} — 정규장 종가 ${v['base']:,.2f} 대비 {int(v['step'])}% {'넘게 상승' if up else '넘게 하락'}"})
    return out


def build(spot: list[dict] | None = None) -> dict:
    now = time.time()
    try:
        c = json.loads(CACHE.read_text(encoding="utf-8"))
        if now - c["at"] < TTL:
            return c["data"]
    except Exception:  # noqa: BLE001
        pass
    from extended import quote
    syms = list(BOARD)
    have = {s for s, _ in syms}
    for s in spot or []:
        y = s.get("yf")
        if s.get("market") == "미국" and y and y not in have:
            syms.append((y, s.get("name") or y)); have.add(y)

    def one(p):
        try:
            q = quote(p[0])
            return {"sym": p[0], "name": p[1], **q} if q else None
        except Exception:  # noqa: BLE001
            return None
    with ThreadPoolExecutor(6) as ex:
        rows = [r for r in ex.map(one, syms) if r]
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    events(rows, state, now)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    live = [r for r in rows if r.get("live")]
    sess = live[0]["sess"] if live else (rows[0]["sess"] if rows else None)
    data = {"at": int(now * 1000), "sess": sess, "live": bool(live), "rows": rows, "items": items_of(state)}
    CACHE.write_text(json.dumps({"at": now, "data": data}, ensure_ascii=False), encoding="utf-8")
    return data


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = build()
    print(d["sess"], d["live"])
    for r in d["rows"]:
        print(f"{r['sym']:6} {r['name']:10} {r['sess']} ${r['px']} {r['chg']:+.2f}% live={r['live']} stale={r['stale']}")
    for i in d["items"]:
        print(i["text"])
