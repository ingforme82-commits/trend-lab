"""⚡ 지수 급변 자동 분석 → 주요 이슈(data/headline.json) 맨 위 자동 갱신. 2026-11-12 운영자 요청:
"지수 선물이 예상보다 큰 변화일 때는 관련 이유를 찾아 분석해서 TRL 자동 업데이트 수시로".

live_news.py 가 1분마다 부른다(실행 PC 한 대). 조건이 맞을 때만 쓰고 push 한다.
  python tools/move_issue.py --dry     # 지금 데이터(live news.json)로 무엇을 쓸지 보기만

언제 쓰나(24시간 선물, 전일 정산 대비 = brief.futures)
- 나스닥100 ±1.5% · S&P500 ±1.0% · 코스피200 ±2.0% 중 하나라도 넘거나, 최근 60분 안에 이 지수들의 변곡점(moves)이 생기면.
- 같은 날 다시 쓰는 경우: 크기가 0.5%p 더 커졌거나 방향이 바뀌었거나, 새 변곡점이 생겼거나, 마지막 갱신 뒤 30분이 지났을 때.
무엇을 쓰나(사실·수치·출처만, 인과 단정 없이 '시각이 겹친 요인'으로)
- 지수 숫자 · 최근 변곡점 구간과 같은 구간 다른 자산 · 같은 시각 주요 뉴스(출처) · 그 시각 주도/부진 업종 ·
  금리·달러·유가·금 · 규칙으로 고른 '성격'(AI·반도체 주도 / 금리·달러 부담 / 유가·지정학 / 안전자산 이동).
수동으로 쓴 주요 이슈는 건드리지 않는다(태그 '⚡ 지수 급변(자동)' 하나만 갈아 끼움).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD = ROOT / "data" / "headline.json"
STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "trendlab" / "move_issue_state.json"
KST = timezone(timedelta(hours=9))
TAG = "⚡ 지수 급변(자동)"
LIMIT = {"나스닥100": 1.5, "S&P500": 1.0, "코스피200": 2.0}
ASSET = {"NQ": "나스닥100", "SP": "S&P500", "K200": "코스피200"}
MIN = 60_000
IDX_RX = re.compile(r"나스닥|S&P|다우|증시|월가|뉴욕|코스피|코스닥|반도체|AI|엔비디아|연준|금리|국채|달러|유가|이란|관세|트럼프|"
                    r"Nasdaq|Wall Street|stocks|Fed|Treasury|yield|chip|Nvidia|rally|selloff", re.I)


def pc(v: float | None) -> str:
    return "-" if v is None else f"{v:+.2f}%"


def hm(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, KST).strftime("%H:%M")


def trigger(d: dict, now_ms: int) -> tuple[dict, list[dict]]:
    """(기준 넘은 지수 {이름: 등락}, 최근 60분 지수 변곡점들)"""
    fut = {f["name"]: f for f in (d.get("brief") or {}).get("futures") or []}
    big = {n: fut[n]["chg"] for n, lim in LIMIT.items() if n in fut and fut[n].get("chg") is not None and abs(fut[n]["chg"]) >= lim}
    mv = [m for m in d.get("moves") or [] if m.get("asset") in ASSET and now_ms - m["end"] < 60 * MIN and m.get("kind") != "level"]
    return big, mv


def character(d: dict, big: dict, mv: list[dict]) -> list[str]:
    """규칙으로 고른 성격(사실 조합). 단정하지 않고 '시각이 겹친 요인'으로 쓴다."""
    fut = {f["name"]: f.get("chg") for f in (d.get("brief") or {}).get("futures") or []}
    up = sum(1 for v in big.values() if v > 0) >= max(1, len(big)) / 2 if big else (mv[0]["move"] > 0 if mv else True)
    us = ((d.get("leaders") or {}).get("us") or {}).get("industry") or []
    top = [g["name"] for g in sorted(us, key=lambda g: -(g.get("chg") or 0))[:3]]
    bp = (d.get("us10y") or {}).get("bp")
    dxy, wti, gold = fut.get("달러인덱스"), fut.get("WTI"), fut.get("금")
    out = []
    if up and any("반도체" in t or "하드웨어" in t for t in top):
        out.append("AI·반도체가 상승을 이끔(미국 업종 상위: " + " · ".join(top) + ")")
    if up and (bp or 0) >= 5 and (dxy or 0) >= 0.3:
        out.append(f"금리(+{bp:.0f}bp)·달러({pc(dxy)})가 함께 올랐는데도 주가 상승 — 실적·테마가 금리 부담보다 크게 반영")
    if not up and (bp or 0) >= 5:
        out.append(f"미 10년물 +{bp:.0f}bp — 금리·긴축 부담과 시각이 겹침")
    if not up and (wti or 0) >= 2:
        out.append(f"유가 {pc(wti)} — 유가·지정학 부담과 시각이 겹침")
    if up and (gold or 0) <= -0.5:
        out.append(f"금 {pc(gold)} — 안전자산에서 위험자산으로 이동")
    if not up and (gold or 0) >= 0.5:
        out.append(f"금 {pc(gold)} — 안전자산 선호")
    tr = [t["name"] for t in (d.get("trending") or [])[:3]]
    if tr:
        out.append("가장 많이 나온 이름: " + " · ".join(tr))
    return out


def compose(d: dict, now_ms: int) -> dict | None:
    big, mv = trigger(d, now_ms)
    if not big and not mv:
        return None
    fut = {f["name"]: f for f in (d.get("brief") or {}).get("futures") or []}
    idx = " · ".join(f"{n} {pc(fut[n]['chg'])}" for n in ("나스닥100", "S&P500", "코스피200") if n in fut)
    ch = character(d, big, mv)
    lead = ch[0].split("(")[0] if ch else "지수 급변"
    title = f"{idx} (24시간 선물, {hm(now_ms)}) — {lead}"
    pts = []
    for m in mv[:3]:
        oth = " · ".join(f"{k} {v:+.2f}{'bp' if '금리' in k else '%'}" for k, v in list((m.get("others") or {}).items())[:5])
        pts.append(f"변곡점 {hm(m['start'])}~{hm(m['end'])} {m['name']} {m['move']:+.2f}{'bp' if m.get('unit') == 'bp' else '%'}"
                   + (f" · 같은 구간 {oth}" if oth else ""))
    ids = {t for m in mv for t in (m.get("news") or [])}
    items = d.get("items") or []
    linked = [i for i in items if i["ts"] in ids]
    recent = [i for i in items if now_ms - i["ts"] < 180 * MIN and i.get("lv") in ("상", "중")
              and IDX_RX.search(i.get("text", "") + " " + i.get("orig", "")) and i not in linked]
    tr = [t.get("kw") or t["name"] for t in (d.get("trending") or [])[:4]]
    semis = any("반도체" in t or "하드웨어" in t for t in [g["name"] for g in sorted(
        ((d.get("leaders") or {}).get("us") or {}).get("industry") or [], key=lambda g: -(g.get("chg") or 0))[:3]])

    def rel(i: dict) -> float:
        """움직임과의 관련도: 화제 이름·지수 직접 언급·(반도체 주도면) AI·칩 뉴스를 중요도보다 먼저."""
        t = i.get("text", "") + " " + i.get("orig", "")
        s = (i.get("imp") or 0) / 10
        s += 4 * sum(1 for k in tr if k and re.search(k, t, re.I))
        s += 3 if re.search(r"나스닥|S&P|증시|월가|Wall Street|stocks|rally|급등|급락|surge|tumble", t, re.I) else 0
        s += 3 if semis and re.search(r"AI|반도체|칩|chip|semiconductor|메모리|HBM", t, re.I) else 0
        return s
    news = (linked + sorted(recent, key=lambda i: (-rel(i), -i["ts"])))[:4]
    for i in news:
        pts.append(f"{hm(i['ts'])} {i.get('src', '')}: {i['text'][:90]}")
    us = ((d.get("leaders") or {}).get("us") or {}).get("industry") or []
    if us:
        s = sorted(us, key=lambda g: -(g.get("chg") or 0))
        pts.append("미국 업종 강세: " + " · ".join(f"{g['name']} {pc(g.get('chg'))}" for g in s[:3])
                   + (" / 약세: " if (s[-1].get("chg") or 0) < 0 else " / 덜 오른 업종: ")
                   + " · ".join(f"{g['name']} {pc(g.get('chg'))}" for g in s[-2:]))
    kr = ((d.get("leaders") or {}).get("kr") or {}).get("industry") or []
    if "코스피200" in big and kr:
        pts.append("한국 업종 강세: " + " · ".join(f"{g['name']} {pc(g.get('chg'))}" for g in sorted(kr, key=lambda g: -(g.get("chg") or 0))[:3]))
    oth = [f"미 10년물 {d['us10y']['px']:.3f}%({d['us10y'].get('bp', 0):+.1f}bp)"] if (d.get("us10y") or {}).get("px") else []
    oth += [f"{n} {pc(fut[n]['chg'])}" for n in ("달러인덱스", "WTI", "금", "원/달러") if n in fut]
    if oth:
        pts.append("함께 움직인 자산: " + " · ".join(oth))
    if len(ch) > 1:
        pts.append("시각이 겹친 요인: " + " / ".join(ch[1:]))
    day = datetime.fromtimestamp(now_ms / 1000, KST)
    return {"tag": TAG, "title": title, "when": f"{day:%m/%d} {day:%H시 %M분} 자동 갱신", "until": (day + timedelta(days=1)).strftime("%Y-%m-%d"),
            "points": pts, "source": "트렌드랩 자동 집계(하이퍼리퀴드 24시간 선물·변곡점·네이버 업종) · 뉴스 출처는 각 줄", "_big": big,
            "_moves": [m.get("grp") or m.get("id") for m in mv]}


def due(it: dict, st: dict, now_ms: int) -> bool:
    day = datetime.fromtimestamp(now_ms / 1000, KST).strftime("%Y-%m-%d")
    if st.get("day") != day:
        return True
    mx, prev = max((abs(v) for v in it["_big"].values()), default=0), st.get("max", 0)
    sign = sorted((k, v > 0) for k, v in it["_big"].items())
    return (mx >= prev + 0.5 or sign != [tuple(x) for x in st.get("sign", [])] or bool(set(it["_moves"]) - set(st.get("moves", [])))
            or now_ms - st.get("at", 0) >= 30 * MIN)


def update(d: dict, push: bool = True) -> str:
    """live_news 에서 부른다. 썼으면 한 줄 요약, 아니면 빈 문자열. 실패해도 예외 없음."""
    try:
        now_ms = int(time.time() * 1000)
        it = compose(d, now_ms)
        if not it:
            return ""
        try:
            st = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            st = {}
        if not due(it, st, now_ms):
            return ""
        h = json.loads(HEAD.read_text(encoding="utf-8")) if HEAD.exists() else {"items": []}
        rec = {k: v for k, v in it.items() if not k.startswith("_")}
        h["items"] = [rec] + [x for x in h.get("items", []) if x.get("tag") != TAG]
        h["updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        HEAD.write_text(json.dumps(h, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        if push:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from ops import push as git_push
            git_push(f"주요 이슈 자동: {rec['title'][:60]}", ["data/headline.json"])
            try:                                          # 📲 앱 푸시(등록 기기가 있을 때) — 카톡은 보내지 않음(카톡 예외 3가지에 없음)
                from push_notify import SITE, push as app_push
                app_push("TRL · ⚡ 지수 급변", rec["title"] + ("\n" + rec["points"][0] if rec["points"] else ""), SITE + "#headline",
                         "move-" + datetime.now(KST).strftime("%m%d"))
            except Exception:  # noqa: BLE001
                pass
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"day": datetime.now(KST).strftime("%Y-%m-%d"), "at": now_ms,
                                     "max": max((abs(v) for v in it["_big"].values()), default=0),
                                     "sign": sorted((k, v > 0) for k, v in it["_big"].items()), "moves": it["_moves"]}), encoding="utf-8")
        return rec["title"]
    except Exception as e:  # noqa: BLE001
        return f"(실패 {type(e).__name__}: {e})"


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    import urllib.request
    d = json.loads(urllib.request.urlopen(urllib.request.Request(
        "https://api.github.com/repos/ingforme82-commits/trend-lab/contents/news.json?ref=live",
        headers={"Accept": "application/vnd.github.raw+json", "User-Agent": "trl"}), timeout=30).read())
    it = compose(d, int(time.time() * 1000))
    if not it:
        print("지금은 기준을 넘는 지수 급변 없음")
        return
    print(f"[{it['tag']}] {it['title']}\n" + "\n".join(" - " + p for p in it["points"]) + f"\n출처: {it['source']}")


if __name__ == "__main__":
    main()
