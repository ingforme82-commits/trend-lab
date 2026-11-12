"""📈 금리·유가 변화 감지 → 이유 정리 → 주요 이슈(data/headline.json) 자동 갱신. 2026-11-13 운영자 요청:
"10년 국채랑 WTI 다시 오르는 이유도 분석해야 할 것 같아. 변화 감지 기능 시스템 만들어줘".

live_news.py 가 1분마다 부른다(move_issue 와 같은 방식, 태그 '📈 금리·유가 변화(자동)' 하나만 갈아 끼움).
  python tools/macro_issue.py --dry     # 지금 live news.json 으로 무엇을 쓸지 보기만

언제 쓰나
- 미 10년물: 전일 대비 ±8bp 이상, 또는 0.1%p 단위 가격대(5.00%·5.10% …)를 새로 넘음, 또는 최근 60분 10년물 변곡점
- WTI: 전일 정산 대비 ±2% 이상, 또는 $5 단위 가격대를 새로 넘음, 또는 최근 60분 WTI·브렌트 변곡점(1시간 ±1% 등)
- 같은 날 다시 쓰는 경우: 10년물 3bp 이상 또는 WTI 1%p 이상 더 움직임, 방향 바뀜, 새 변곡점·가격대, 마지막 갱신 뒤 30분
무엇을 쓰나(사실·수치·출처만, 인과 단정 없이 '시각이 겹친 요인'으로)
- 2년·10년·30년 금리와 곡선 모양(단기물 주도/장기물 주도), 달러·금·나스닥100, WTI·브렌트
- 최근 6시간 뉴스를 요인별로 묶어 건수와 대표 헤드라인: 연준 발언 · 물가·지표 · 국채 입찰·공급 · 유가·지정학 · 해외 금리·달러 · 재정·정치
- 규칙으로 고른 '성격'
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
STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "trendlab" / "macro_issue_state.json"
KST = timezone(timedelta(hours=9))
TAG = "📈 금리·유가 변화(자동)"
MIN = 60_000
BP_LIM, WTI_LIM = 8.0, 2.0

# 요인 묶음: (이름, 정규식) — 금리·유가 쪽 뉴스만
DRIVERS = [
    ("연준 발언", r"연준|Fed\b|FOMC|파월|Powell|해먹|Hammack|굴스비|Goolsbee|월러|Waller|보우먼|Bowman|바\(Barr\)|Barr|로건|Logan|"
                r"금리\s?인상|금리\s?인하|긴축|rate hike|rate cut|hawkish|dovish|매파|비둘기"),
    ("물가·지표", r"CPI|PPI|PCE|물가|인플레이션|inflation|고용|실업|payroll|jobless|소매판매|retail sales|기대인플레|breakeven|임금|wage"),
    ("국채 입찰·공급", r"입찰|낙찰|auction|발행|refunding|국채\s?공급|재무부|Treasury (?:sale|supply)|bid-to-cover|응찰"),
    ("유가·지정학", r"유가|원유|WTI|브렌트|Brent|crude|OPEC|오펙|사우디|아람코|Aramco|후티|Houthi|송유관|pipeline|이란|Iran|이스라엘|Israel|"
                  r"호르무즈|Hormuz|홍해|Red Sea|러시아\s?(?:제재|원유)|재고|inventor|EIA|API\b"),
    ("해외 금리·달러", r"달러인덱스|달러\s?강세|DXY|엔화|엔/달러|일본\s?국채|JGB|BOJ|일본은행|독일\s?국채|Bund|ECB|유럽중앙은행|영란은행|BOE|길트|gilt|IMF"),
    ("재정·정치", r"재정|적자|deficit|셧다운|shutdown|부채\s?한도|debt ceiling|관세|tariff|감세|예산|budget|신용등급|downgrade"),
]
DRX = [(n, re.compile(p, re.I)) for n, p in DRIVERS]
RATE_OIL = re.compile(r"금리|국채|수익률|yield|Treasury|채권|bond|연준|Fed\b|물가|인플레|유가|원유|WTI|브렌트|Brent|crude|OPEC|달러", re.I)


def pc(v: float | None) -> str:
    return "-" if v is None else f"{v:+.2f}%"


def hm(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, KST).strftime("%H:%M")


def snap(d: dict) -> dict:
    fut = {f["name"]: f for f in (d.get("brief") or {}).get("futures") or []}
    ust = d.get("ust") or {}
    g = lambda n, k: (fut.get(n) or {}).get(k)  # noqa: E731
    return {"y10": (d.get("us10y") or {}).get("px"), "bp10": (d.get("us10y") or {}).get("bp"),
            "bp2": (ust.get("2Y") or {}).get("bp"), "y2": (ust.get("2Y") or {}).get("px"),
            "bp30": (ust.get("30Y") or {}).get("bp"), "y30": (ust.get("30Y") or {}).get("px"),
            "wti": g("WTI", "px"), "wti_chg": g("WTI", "chg"), "brent": g("브렌트", "px"), "brent_chg": g("브렌트", "chg"),
            "dxy": g("달러인덱스", "chg"), "gold": g("금", "chg"), "nq": g("나스닥100", "chg"), "krw": g("원/달러", "chg")}


def trigger(d: dict, s: dict, now_ms: int, st: dict) -> tuple[list[str], list[dict]]:
    why = []
    if s["bp10"] is not None and abs(s["bp10"]) >= BP_LIM:
        why.append(f"10년물 {s['bp10']:+.1f}bp")
    if s["wti_chg"] is not None and abs(s["wti_chg"]) >= WTI_LIM:
        why.append(f"WTI {pc(s['wti_chg'])}")
    lv10 = int((s["y10"] or 0) * 10) / 10 if s["y10"] else None          # 5.10% 같은 0.1%p 단위
    lvw = int((s["wti"] or 0) // 5 * 5) if s["wti"] else None             # $85 같은 $5 단위
    if lv10 is not None and st.get("lv10") is not None and lv10 != st["lv10"]:
        why.append(f"10년물 {max(lv10, st['lv10']):.2f}% {'상향 돌파' if lv10 > st['lv10'] else '하향 이탈'}")
    if lvw is not None and st.get("lvw") is not None and lvw != st["lvw"]:
        why.append(f"WTI ${max(lvw, st['lvw'])} {'상향 돌파' if lvw > st['lvw'] else '하향 이탈'}")
    mv = [m for m in d.get("moves") or [] if m.get("asset") in ("US10Y", "WTI", "BRENT") and now_ms - m["end"] < 60 * MIN]
    return why, mv


def drivers(items: list[dict], now_ms: int) -> list[tuple[str, list[dict]]]:
    pool = [i for i in items if now_ms - i["ts"] < 360 * MIN and i.get("kind") not in ("시간외 시세", "섹터 시세")]
    out = []
    for name, rx in DRX:
        hit = [i for i in pool if rx.search(i.get("text", "") + " " + i.get("orig", ""))]
        if hit:
            hit.sort(key=lambda i: (-(i.get("imp") or 0), -i["ts"]))
            seen, uniq = set(), []
            for i in hit:
                k = re.sub(r"[^0-9A-Za-z가-힣]", "", i["text"])[:16]
                if k not in seen:
                    seen.add(k)
                    uniq.append(i)
            out.append((name, uniq))
    out.sort(key=lambda x: -len(x[1]))
    return out


def character(s: dict, drv: list[tuple[str, list]]) -> list[str]:
    names = {n: len(v) for n, v in drv}
    out = []
    b2, b10, b30 = s["bp2"], s["bp10"], s["bp30"]
    if None not in (b2, b10) and max(abs(b2), abs(b10)) >= 3:
        if b10 > 0 and b2 > 0:
            out.append(f"단기물 주도 상승(2년 {b2:+.1f}bp ≥ 10년 {b10:+.1f}bp) — 연준 인상·긴축 기대 쪽과 시각이 겹침"
                       if b2 >= b10 else
                       f"장기물 주도 상승(10년 {b10:+.1f}bp > 2년 {b2:+.1f}bp{f', 30년 {b30:+.1f}bp' if b30 is not None else ''}) — 물가·공급·기간 프리미엄 쪽과 시각이 겹침")
        elif b10 < 0 and b2 < 0:
            out.append(f"금리 하락(2년 {b2:+.1f}bp · 10년 {b10:+.1f}bp)")
    if (s["wti_chg"] or 0) >= 1 and (b10 or 0) >= 3:
        out.append(f"유가 {pc(s['wti_chg'])}와 금리 동반 상승 — 유가 → 물가 기대 경로와 시각이 겹침")
    if (s["wti_chg"] or 0) >= 1 and names.get("유가·지정학"):
        out.append(f"유가 상승과 같은 시각 유가·지정학 뉴스 {names['유가·지정학']}건 — 공급 차질 우려")
    if (s["dxy"] or 0) >= 0.2 and (b10 or 0) > 0:
        out.append(f"달러인덱스 {pc(s['dxy'])} 동반 강세")
    if (s["nq"] or 0) <= -0.5 and (b10 or 0) >= 5:
        out.append(f"나스닥100 {pc(s['nq'])} — 금리 부담과 시각이 겹침")
    if (s["gold"] or 0) <= -1 and (b10 or 0) >= 5:
        out.append(f"금 {pc(s['gold'])} — 실질금리·달러 상승과 시각이 겹침")
    return out


def compose(d: dict, now_ms: int, st: dict) -> dict | None:
    s = snap(d)
    why, mv = trigger(d, s, now_ms, st)
    if not why and not mv:
        return None
    drv = drivers(d.get("items") or [], now_ms)
    ch = character(s, drv)
    head = []
    if s["y10"]:
        head.append(f"미 10년물 {s['y10']:.3f}%({(s['bp10'] or 0):+.1f}bp)")
    if s["wti"]:
        head.append(f"WTI ${s['wti']:.2f}({pc(s['wti_chg'])})")
    lead = ch[0].split(" — ")[0].split("(")[0] if ch else (why[0] if why else "금리·유가 변곡점")
    title = " · ".join(head) + f" ({hm(now_ms)}) — {lead}"
    pts = []
    if why:
        pts.append("감지: " + " · ".join(why))
    curve = [f"{n} {y:.3f}%({b:+.1f}bp)" for n, y, b in (("2년", s["y2"], s["bp2"]), ("10년", s["y10"], s["bp10"]), ("30년", s["y30"], s["bp30"]))
             if y is not None and b is not None]
    if curve:
        pts.append("미 국채: " + " · ".join(curve))
    oth = [f"{n} {pc(v)}" for n, v in (("브렌트", s["brent_chg"]), ("달러인덱스", s["dxy"]), ("금", s["gold"]), ("나스닥100", s["nq"]), ("원/달러", s["krw"]))
           if v is not None]
    if oth:
        pts.append("함께 움직인 자산: " + " · ".join(oth))
    for m in mv[:2]:
        unit = "bp" if m.get("unit") == "bp" else "%"
        pts.append(f"변곡점 {hm(m['start'])}~{hm(m['end'])} {m['name']} {m['move']:+.2f}{unit}")
    for name, its in drv[:4]:
        top = its[:2]
        pts.append(f"[{name} · 6시간 {len(its)}건] " + " / ".join(f"{hm(i['ts'])} {i['text'][:70]}({i.get('src', '')})" for i in top))
    if len(ch) > 1 or (ch and why):
        pts.append("시각이 겹친 요인: " + " / ".join(ch))
    day = datetime.fromtimestamp(now_ms / 1000, KST)
    return {"tag": TAG, "title": title, "when": f"{day:%m/%d} {day:%H시 %M분} 자동 갱신",
            "until": (day + timedelta(days=1)).strftime("%Y-%m-%d"), "points": pts,
            "source": "트렌드랩 자동 집계(CNBC 금리·하이퍼리퀴드 24시간 유가·변곡점) · 뉴스 출처는 각 줄 · 인과 단정 아님",
            "_s": s, "_moves": [m.get("grp") or m.get("id") for m in mv],
            "_lv10": int((s["y10"] or 0) * 10) / 10 if s["y10"] else None, "_lvw": int((s["wti"] or 0) // 5 * 5) if s["wti"] else None}


def due(it: dict, st: dict, now_ms: int) -> bool:
    day = datetime.fromtimestamp(now_ms / 1000, KST).strftime("%Y-%m-%d")
    if st.get("day") != day or not st.get("wrote"):
        return True
    s = it["_s"]
    b, w = s["bp10"] or 0, s["wti_chg"] or 0
    return (abs(b - st.get("bp10", 0)) >= 3 or abs(w - st.get("wti", 0)) >= 1
            or (b > 0) != (st.get("bp10", 0) > 0) or bool(set(it["_moves"]) - set(st.get("moves", [])))
            or it["_lv10"] != st.get("lv10") or it["_lvw"] != st.get("lvw") or now_ms - st.get("at", 0) >= 30 * MIN)


def _save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def update(d: dict, push: bool = True) -> str:
    """live_news 에서 부른다. 썼으면 제목, 아니면 빈 문자열. 실패해도 예외 없음."""
    try:
        now_ms = int(time.time() * 1000)
        try:
            st = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            st = {}
        it = compose(d, now_ms, st)
        if not it:
            s = snap(d)                                    # 가격대 기준은 계속 따라가게 저장
            st.update(lv10=int((s["y10"] or 0) * 10) / 10 if s["y10"] else st.get("lv10"),
                      lvw=int((s["wti"] or 0) // 5 * 5) if s["wti"] else st.get("lvw"))
            _save(st)
            return ""
        if not due(it, st, now_ms):
            return ""
        h = json.loads(HEAD.read_text(encoding="utf-8")) if HEAD.exists() else {"items": []}
        rec = {k: v for k, v in it.items() if not k.startswith("_")}
        items = h.get("items", [])
        pos = next((i for i, x in enumerate(items) if x.get("tag") == TAG), None)
        if pos is None:
            h["items"] = [rec] + items
        else:
            items[pos] = rec
            h["items"] = items
        h["updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        HEAD.write_text(json.dumps(h, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        if push:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from ops import push as git_push
            git_push(f"주요 이슈 자동: {rec['title'][:60]}", ["data/headline.json"])
            try:                                          # 📲 앱 푸시만(카톡은 예외 목록에 없어 보내지 않음)
                from push_notify import SITE, push as app_push
                app_push("TRL · 📈 금리·유가 변화", rec["title"], SITE + "#headline", "macro-" + datetime.now(KST).strftime("%m%d"))
            except Exception:  # noqa: BLE001
                pass
        s = it["_s"]
        _save({"day": datetime.now(KST).strftime("%Y-%m-%d"), "at": now_ms, "wrote": True, "bp10": s["bp10"] or 0,
               "wti": s["wti_chg"] or 0, "moves": it["_moves"], "lv10": it["_lv10"], "lvw": it["_lvw"]})
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
    it = compose(d, int(time.time() * 1000), {})
    if not it:
        print("지금은 기준을 넘는 금리·유가 변화 없음")
        return
    print(f"[{it['tag']}] {it['title']}\n" + "\n".join(" - " + p for p in it["points"]) + f"\n출처: {it['source']}")


if __name__ == "__main__":
    main()
