"""🔥 오늘 주도 섹터(자동) — 한국장 실시간, 강하게 오른 종목이 몰린 업종·테마만 잡는다(news.json auto_issues · 속보).

운영자 11/17: "주도섹터들도 자동으로 실시간 분석. 상한가 여러 개 간 종목군에서 보통 나오니까 적어도 15~20% 많이 있는 섹터.
딱히 없으면 굳이 만들지 않아도 되고, 항상 생각했다가 주도 섹터가 5% 이상 오르는 섹터 전체 나오는 경우."

조건(둘 중 하나, 구성 3종목 이상)
- 15% 이상 오른 종목(상한가 포함)이 2개 이상
- 업종·테마 평균 등락률 +5% 이상
없으면 카드를 만들지 않는다. 처음 잡힌 업종·테마는 속보로 한 번 알린다(하루 한 번).
데이터: 네이버 금융(상승률 상위 코스피·코스닥, 업종 79·테마 약 260 — 종목→업종·테마 묶음은 하루 한 번 받아 둔다).
신규 상장 첫날 등 ±30% 를 넘는 값은 상한가 집계에서 뺀다. 사실·수치만, 매수·매도 권유 없음.

  python tools/hot_sectors.py      # 지금 값 출력(확인용)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
BASE = "https://m.stock.naver.com/api/stocks"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "trendlab"
MAP = DIR / "hot_sectors_map.json"
STATE = DIR / "hot_sectors_state.json"
TAG = "🔥 오늘 주도 섹터(자동)"
HOT, LIMIT, ABN = 15.0, 29.5, 30.5       # 15%↑ · 상한가(가격제한 30%, 호가 단위로 29.5% 이상) · 이상치
MIN_HOT, MIN_AVG, MIN_N = 2, 5.0, 3


def _get(url: str):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10).read())


def _n(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return 0.0


def _chg(s: dict) -> float:
    v = _n(s.get("fluctuationsRatioRaw") or s.get("fluctuationsRatio"))
    code = str((s.get("compareToPreviousPrice") or {}).get("code") or "")
    return -abs(v) if code in ("4", "5") else v


# ── 묶음(업종·테마) 목록과 종목→묶음 지도 ──
def groups() -> list[dict]:
    out = []
    for kind in ("industry", "theme"):
        for p in (1, 2, 3, 4):
            g = _get(f"{BASE}/{kind}?page={p}&pageSize=100").get("groups", [])
            out += [{"kind": kind, "no": x["no"], "name": x["name"], "avg": round(_n(x.get("changeRate")), 2),
                     "n": int(x.get("totalCount") or 0), "up": int(x.get("riseCount") or 0)} for x in g]
            if len(g) < 100:
                break
    return out


def member_map(gs: list[dict], max_age_h: float = 20) -> dict[str, list[str]]:
    """종목코드 → ['industry:12', 'theme:345', ...]. 하루 한 번 받아 저장."""
    try:
        c = json.loads(MAP.read_text(encoding="utf-8"))
        if time.time() - c["at"] < max_age_h * 3600 and c.get("m"):
            return c["m"]
    except Exception:  # noqa: BLE001
        pass

    def mem(g):
        codes = []
        for p in (1, 2, 3):
            try:
                st = _get(f"{BASE}/{g['kind']}/{g['no']}?page={p}&pageSize=100").get("stocks", [])
            except Exception:  # noqa: BLE001
                break
            codes += [s.get("itemCode") for s in st if s.get("itemCode")]
            if len(st) < 100:
                break
        return f"{g['kind']}:{g['no']}", codes
    m: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for key, codes in ex.map(mem, gs):
            for c in codes:
                m.setdefault(c, []).append(key)
    if m:
        DIR.mkdir(parents=True, exist_ok=True)
        MAP.write_text(json.dumps({"at": time.time(), "m": m}, ensure_ascii=False), encoding="utf-8")
    return m


def is_pref(name: str, code: str) -> bool:
    """우선주(삼성전자우·동양2우B 등) — 급등해도 섹터 주도로 세지 않는다."""
    import re
    return bool(re.search(r"\d?우[A-C]?$|\(전환\)$", name or "")) or (len(code) == 6 and code.isdigit() and code[-1] != "0")


def risers(min_chg: float = 10.0) -> list[dict]:
    """코스피·코스닥 상승률 상위(보통주 등 stock 만), min_chg 이상."""
    out = []
    for mk in ("KOSPI", "KOSDAQ"):
        for p in (1, 2, 3):
            st = _get(f"{BASE}/up/{mk}?page={p}&pageSize=100").get("stocks", [])
            rows = [{"code": s["itemCode"], "name": s["stockName"], "chg": _chg(s), "px": _n(s.get("closePriceRaw") or s.get("closePrice")),
                     "val": _n(s.get("accumulatedTradingValueRaw")),
                     "mk": mk} for s in st if s.get("stockEndType") == "stock" and not is_pref(s.get("stockName", ""), s.get("itemCode", ""))]
            out += [r for r in rows if r["chg"] >= min_chg]
            if not st or _chg(st[-1]) < min_chg:
                break
    return out


# ── 판정(테스트 대상) ──
def pick(gs: list[dict], m: dict[str, list[str]], rs: list[dict]) -> list[dict]:
    """조건 맞는 묶음 → [{kind,name,avg,n,up,hot:[...],limit_n,hot_n,val}] 강한 순. 같은 급등 종목 묶음은 이름만 합친다."""
    byk = {f"{g['kind']}:{g['no']}": g for g in gs}
    hot: dict[str, list[dict]] = {}
    rs = list({r["code"]: r for r in rs}.values())
    for r in rs:
        if r["chg"] < HOT or r["chg"] > ABN:
            continue
        for k in dict.fromkeys(m.get(r["code"], [])):
            hot.setdefault(k, []).append(r)
    out = []
    for k, g in byk.items():
        if g["n"] < MIN_N:
            continue
        hs = sorted(hot.get(k, []), key=lambda r: -r["chg"])
        if len(hs) >= MIN_HOT or g["avg"] >= MIN_AVG:
            out.append({**g, "key": k, "hot": hs, "hot_n": len(hs), "limit_n": sum(r["chg"] >= LIMIT for r in hs),
                        "val": sum(r["val"] for r in hs)})
    out.sort(key=lambda x: (-(x["hot_n"] + x["limit_n"]), -x["avg"]))          # 급등 종목 수(상한가는 두 번) → 평균
    merged: list[dict] = []
    for x in out:
        sig = tuple(sorted(r["code"] for r in x["hot"]))
        same = next((y for y in merged if sig and tuple(sorted(r["code"] for r in y["hot"])) == sig), None)
        if same:
            same.setdefault("also", []).append(x["name"])
        else:
            merged.append(x)
    return merged


def _eok(v: float) -> str:
    return f"{v / 1e8:,.0f}억" if v else "-"


def line(x: dict) -> str:
    kind = "업종" if x["kind"] == "industry" else "테마"
    names = x["name"] + (f"(같은 종목: {'·'.join(x['also'][:3])})" if x.get("also") else "")
    lim = [r for r in x["hot"] if r["chg"] >= LIMIT]
    rest = [r for r in x["hot"] if r["chg"] < LIMIT]
    seg = [f"{kind} {names} 평균 {x['avg']:+.2f}% · 상승 {x['up']}/{x['n']}"]
    if lim:
        seg.append("상한가 " + ", ".join(f"{r['name']}" for r in lim[:6]))
    if rest:
        seg.append("15%↑ " + ", ".join(f"{r['name']} {r['chg']:+.1f}%" for r in rest[:6]))
    if x["val"]:
        seg.append(f"급등 종목 거래대금 {_eok(x['val'])}")
    return " · ".join(seg)


def phase(now: datetime) -> str:
    if now.weekday() >= 5:
        return ""
    m = now.hour * 60 + now.minute
    return "장중" if 9 * 60 <= m < 15 * 60 + 31 else "마감" if 15 * 60 + 31 <= m < 15 * 60 + 41 else ""


def update(d: dict | None = None) -> list[dict]:
    """live_news 에서 1분마다. 새로 잡힌 묶음의 속보 항목 [{text}] 을 돌려준다. 실패해도 예외 없음."""
    now = datetime.now(KST)
    ph, day = phase(now), now.strftime("%Y-%m-%d")
    if not ph:
        return []
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {}
    if st.get("day") != day:
        st = {"day": day, "seen": {}}
    try:
        gs = groups()
        res = pick(gs, member_map(gs), risers())
    except Exception as e:  # noqa: BLE001
        print(f"[주도 섹터] 건너뜀 {type(e).__name__}: {e}")
        return []
    new = []
    for x in res:
        if x["key"] not in st["seen"]:
            st["seen"][x["key"]] = now.strftime("%H:%M")
            new.append({"text": f"🔥 주도 섹터 포착 — {line(x)}"})
    st.update(at=int(time.time() * 1000), phase=ph, res=[{**x, "first": st["seen"][x["key"]]} for x in res][:8])
    DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return new


def current() -> dict | None:
    """주요 이슈 카드. 조건 맞는 묶음이 없으면 None(카드 안 만듦)."""
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    res = st.get("res") or []
    if not res or st.get("day") != datetime.now(KST).strftime("%Y-%m-%d"):
        return None
    at = datetime.fromtimestamp(st["at"] / 1000, KST)
    top = res[0]
    title = f"{at:%H:%M} {top['name']} 평균 {top['avg']:+.2f}%" + (f" · 상한가 {top['limit_n']}" if top["limit_n"] else "") \
        + (f" · 15%↑ {top['hot_n']}종목" if top["hot_n"] else "") + (f" 외 {len(res) - 1}곳" if len(res) > 1 else "")
    return {"tag": TAG, "title": title, "when": f"{at:%m/%d %H시 %M분} 자동 갱신 · {'장중 실시간' if st.get('phase') == '장중' else '마감'}",
            "until": at.strftime("%Y-%m-%d"),
            "points": [f"{line(x)} (첫 포착 {x['first']})" for x in res]
            + [f"조건: 15% 이상 오른 종목(상한가 포함) {MIN_HOT}개 이상 또는 평균 +{MIN_AVG:.0f}% 이상(구성 {MIN_N}종목 이상) · 매수·매도 권유 아님"],
            "source": "네이버 금융 상승률 상위·업종·테마(트렌드랩 자동 집계)"}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    gs = groups()
    t = time.time(); m = member_map(gs); print(f"묶음 {len(gs)} · 종목 지도 {len(m)} ({time.time() - t:.0f}초)")
    rs = risers()
    print(f"10%↑ {len(rs)}종목 · 15%↑ {sum(HOT <= r['chg'] <= ABN for r in rs)} · 상한가 {sum(LIMIT <= r['chg'] <= ABN for r in rs)}")
    for x in pick(gs, m, rs):
        print("-", line(x))
