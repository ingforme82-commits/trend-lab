"""📊 오늘 시황(자동) — 한국장 장중 30분마다·마감 뒤 한 번, 주요 이슈 맨 위 메인 카드(news.json auto_issues, 1분).
2026-11-15 운영자 승인: 손으로 올리던 '📊 오늘 시황'이 11/13 장중 잠정에서 멈춰 첫 화면 메인 카드가 비던 문제.

- 숫자: 키움 업종지수(코스피·코스닥 현재가·상승/하락 종목·1분봉 고가·저가 시각) + S7·수급(외국인·기관·프로그램) + 주도 업종·테마
  + 오늘 코스피·코스닥 변곡점과 '시각이 겹친 뉴스'. 사실·수치·출처만, 매수·매도 권유 없음.
- 운영자가 손으로 올린 '📊 오늘 시황'(data/headline.json)이 오늘 날짜로 있으면 그 카드가 메인 — 자동 카드는 메인 표시를 뺀다.
- 기한: 다음 거래일까지(주말엔 금요일 마감 카드가 남는다).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
HEAD = ROOT / "data" / "headline.json"
STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "trendlab" / "market_card_state.json"
KST = timezone(timedelta(hours=9))
TAG = "📊 오늘 시황(자동)"
MANUAL_TAG = "📊 오늘 시황"
EVERY_MS = 30 * 60_000


def pc(v) -> str:
    return "-" if v is None else f"{v:+.2f}%"


def num(v, d: int = 2) -> str:
    return f"{v:,.{d}f}"


def eok(v) -> str:
    return "-" if v is None else f"{v:+,.0f}억"


def hm(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, KST).strftime("%H:%M")


def next_trading_day(d: datetime) -> str:
    n = d + timedelta(days=1)
    while n.weekday() >= 5:
        n += timedelta(days=1)
    return n.strftime("%Y-%m-%d")


def phase(now: datetime) -> str:
    """'장중' / '마감' / ''(만들지 않음). 평일 09:00~15:30 장중, 15:35 이후 마감 한 번."""
    if now.weekday() >= 5:
        return ""
    m = now.hour * 60 + now.minute
    return "장중" if 9 * 60 + 1 <= m < 15 * 60 + 35 else "마감" if m >= 15 * 60 + 35 else ""


def intraday(rows: list[tuple[int, float]], day: str) -> dict | None:
    r = [x for x in rows if datetime.fromtimestamp(x[0] / 1000, KST).strftime("%Y-%m-%d") == day]
    if len(r) < 2:
        return None
    hi, lo = max(r, key=lambda x: x[1]), min(r, key=lambda x: x[1])
    return {"open": r[0][1], "hi": hi[1], "hi_t": hi[0], "lo": lo[1], "lo_t": lo[0], "last": r[-1][1]}


def manual_today(day: str, path: Path | None = None) -> bool:
    try:
        h = json.loads((path or HEAD).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    return any(x.get("tag") == MANUAL_TAG and x.get("until", "") >= day and day.replace("-", "/")[5:] in (x.get("when") or "")
               for x in h.get("items", []))


def compose(d: dict, now_ms: int, idx: dict | None = None, mins: dict | None = None) -> dict | None:
    """idx: {'001': index_now, '101': ...}, mins: {'001': [(ms, v)], ...} — 테스트에서 넣을 수 있게."""
    now = datetime.fromtimestamp(now_ms / 1000, KST)
    ph = phase(now)
    if not ph:
        return None
    day = now.strftime("%Y-%m-%d")
    if idx is None or mins is None:
        from kiwoom import index_minutes, index_now
        idx = {c: index_now(c) for c in ("001", "101")}
        mins = {c: index_minutes(c, hours=12) for c in ("001", "101")}
    ks, kq = idx.get("001"), idx.get("101")
    if not ks:                                            # 키움이 안 되는 PC: S7(네이버) 수치로 대신
        k = (d.get("s7") or {}).get("kospi") or {}
        if not k.get("px"):
            return None
        ks = {"px": k["px"], "chg": k.get("chg"), "up": k.get("up"), "down": k.get("dn")}
    s7all = d.get("s7") or {}
    k = s7all.get("kospi") or {} if s7all.get("day") == day else {}
    ik, iq = intraday(mins.get("001") or [], day), intraday(mins.get("101") or [], day)

    lead = []
    if ik and ks.get("px"):
        from_hi = (ks["px"] / ik["hi"] - 1) * 100
        from_lo = (ks["px"] / ik["lo"] - 1) * 100
        if from_hi <= -1.0:
            lead.append(f"장중 고점 대비 {from_hi:.1f}%")
        elif from_lo >= 1.0:
            lead.append(f"장중 저점 대비 +{from_lo:.1f}%")
    if k.get("frgn") is not None:
        lead.append(f"외국인 {eok(k['frgn'])}")
    title = (f"{'마감' if ph == '마감' else hm(now_ms) + ' 장중'} — 코스피 {num(ks['px'])}({pc(ks.get('chg'))})"
             + (f" · 코스닥 {num(kq['px'])}({pc(kq.get('chg'))})" if kq else "") + (" · " + " · ".join(lead) if lead else ""))

    pts = []
    for name, x, it in (("코스피", ks, ik), ("코스닥", kq, iq)):
        if not x:
            continue
        line = f"{name} {num(x['px'])} ({pc(x.get('chg'))})"
        if it:
            line += f" · 시가 {num(it['open'])} · 고가 {num(it['hi'])}({hm(it['hi_t'])}) · 저가 {num(it['lo'])}({hm(it['lo_t'])})"
        if x.get("up") is not None and x.get("down") is not None:
            line += f" · 상승 {int(x['up'])} / 하락 {int(x['down'])}"
        pts.append(line)
    if k:
        flow = [f"외국인 {eok(k.get('frgn'))}", f"기관 {eok(k.get('org'))}", f"개인 {eok(k.get('ind'))}"]
        if k.get("prog") is not None:
            flow.append(f"프로그램 {eok(k['prog'])}(차익 {eok(k.get('arb'))} · 비차익 {eok(k.get('nonarb'))})")
        pts.append("코스피 수급: " + " · ".join(flow))
    s = s7all.get("s7") or {}
    if s and s7all.get("day") == day:
        pts.append(f"S7(시가총액 상위 7) 지수 기여 {s.get('pts', 0):+.1f}p(지수 변화의 {s.get('share')}%) · S7 제외 코스피 {pc(s.get('ex_chg'))}")
    items = {i["ts"]: i for i in d.get("items") or []}
    for m in [m for m in d.get("moves") or [] if m.get("asset") in ("KOSPI", "KOSDAQ")
              and datetime.fromtimestamp(m["start"] / 1000, KST).strftime("%Y-%m-%d") == day][:3]:
        n = next((items[t] for t in m.get("news") or [] if t in items), None)
        pts.append(f"변곡점 {hm(m['start'])}~{hm(m['end'])} {m['name']} {m['move']:+.2f}%"
                   + (f" — 시각이 겹친 뉴스: {n.get('src', '')} '{n['text'][:60]}'" if n else ""))
    kr = (d.get("leaders") or {}).get("kr") or {}
    for key, lab in (("industry", "주도 업종"), ("theme", "주도 테마")):
        g = sorted(kr.get(key) or [], key=lambda x: -(x.get("chg") or 0))[:3]
        if g:
            pts.append(f"{lab}: " + " · ".join(f"{x['name']} {pc(x.get('chg'))}" for x in g))
    pts.append(f"{'마감 기준' if ph == '마감' else '장중 잠정 — 30분마다 갱신'} · 매수·매도 권유 아님")
    return {"tag": TAG, "title": title, "main": not manual_today(day),
            "when": f"{now:%m/%d} {now:%H시 %M분} 자동 갱신" + (" · 마감" if ph == "마감" else " · 장중 잠정"),
            "until": next_trading_day(now), "points": pts,
            "source": "키움 업종지수·1분봉 · 네이버 수급·S7 · 트렌드랩 변곡점(뉴스는 시각이 겹친 것, 인과 단정 아님)", "_phase": ph}


def due(ph: str, st: dict, now_ms: int, day: str) -> bool:
    if st.get("day") != day:
        return True
    if ph == "마감":
        return st.get("phase") != "마감"
    return now_ms - st.get("at", 0) >= EVERY_MS


def update(d: dict) -> str:
    """live_news 에서 부른다. 썼으면 제목, 아니면 ''. 실패해도 예외 없음."""
    try:
        now_ms = int(time.time() * 1000)
        now = datetime.fromtimestamp(now_ms / 1000, KST)
        ph, day = phase(now), now.strftime("%Y-%m-%d")
        try:
            st = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            st = {}
        if not ph or not due(ph, st, now_ms, day):
            return ""
        it = compose(d, now_ms)
        if not it:
            return ""
        rec = {k: v for k, v in it.items() if not k.startswith("_")}
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"day": day, "at": now_ms, "phase": it["_phase"], "rec": rec}, ensure_ascii=False), encoding="utf-8")
        return rec["title"]
    except Exception as e:  # noqa: BLE001
        return f"(실패 {type(e).__name__}: {e})"


def current() -> dict | None:
    try:
        rec = json.loads(STATE.read_text(encoding="utf-8")).get("rec")
    except Exception:  # noqa: BLE001
        return None
    if not rec or rec.get("until", "") < datetime.now(KST).strftime("%Y-%m-%d"):
        return None
    if rec.get("main") and manual_today(datetime.now(KST).strftime("%Y-%m-%d")):
        rec = {**rec, "main": False}                       # 운영자가 그 뒤에 손으로 올렸으면 그쪽이 메인
    return rec
