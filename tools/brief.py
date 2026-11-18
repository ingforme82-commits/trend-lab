"""📋 시장 브리핑 — 카톡 리포트의 시장 부분을 사이트에도 (실시간 + 매일 12시 저장해 후속 확인)

- make(out): news.json 내용으로 브리핑 요약을 만든다(가장 큰 변곡점·섹터 강약·많이 나온 종목·해외 지수·화제 종목).
- save(brief): data/briefs.json 에 하루 한 번(12시 리포트 때) 저장한다. 최근 60일 보관.
사실·수치 요약만 담는다(해석·추천 없음).
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIEFS = ROOT / "data" / "briefs.json"
KST = timezone(timedelta(hours=9))
HISTORY_FROM = "2026-11-14"

# 24시간 선물·CFD(하이퍼리퀴드): (심볼, 이름, 단위)
FUT = [("xyz:KR200", "코스피200", ""), ("xyz:JP225", "니케이225", ""), ("xyz:SMSN", "삼성전자", "$"), ("xyz:SKHX", "SK하이닉스", "$"),
       ("xyz:XYZ100", "나스닥100", ""), ("xyz:SP500", "S&P500", ""), ("xyz:CL", "WTI", "$"), ("xyz:BRENTOIL", "브렌트", "$"),
       ("xyz:GOLD", "금", "$"), ("xyz:DXY", "달러인덱스", ""), ("xyz:KRW", "원/달러", "원"), ("xyz:JPY", "엔/달러", "엔")]
# 경제지표 발표(수치가 있는 것만)
MACRO = re.compile(r"GDP|CPI|PCE|PPI|소비자물가|생산자물가|고용|실업률|비농업|신규 실업|PMI|소매판매|산업생산|기준금리|금리 결정|무역수지|경상수지|수출|수입|소비자신뢰|ISM|설비투자|민간 소비|건설투자")
MACRO_NUM = re.compile(r"예상|예측|전망치|추정|컨센서스|실제|이전치|발표")
HOT_TAGS = {"중동·유가", "연준·금리", "반도체", "AI·빅테크", "한국", "지수", "러·우"}


def session(now: datetime) -> str:
    """지금 열려 있는 시장(한국 시각 기준, 미국은 서머타임 자동 반영)."""
    from zoneinfo import ZoneInfo
    k = now.astimezone(KST)
    ny = now.astimezone(ZoneInfo("America/New_York"))
    km, nm = k.hour * 60 + k.minute, ny.hour * 60 + ny.minute
    wk, nwk = k.weekday() < 5, ny.weekday() < 5
    if nwk and 9 * 60 + 30 <= nm < 16 * 60:
        return "미국 정규장"
    if wk and 9 * 60 <= km < 15 * 60 + 30:
        return "한국·일본 장중" if km < 15 * 60 else "한국 장 마감 직전"
    if wk and 7 * 60 <= km < 9 * 60:
        return "아시아 개장 전"
    if wk and 15 * 60 + 30 <= km < 17 * 60:
        return "한국 장 마감 후"
    if nwk and 4 * 60 <= nm < 9 * 60 + 30 and km >= 16 * 60:
        return "유럽 장중 · 미국 개장 전"
    if nwk and 16 * 60 <= nm < 20 * 60:
        return "미국 장 마감 후"
    return "주말·휴장" if not wk and not nwk else "야간 선물 시간"


def futures() -> list[dict]:
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from market_extra import _hl_ctx
        c = _hl_ctx()
    except Exception:  # noqa: BLE001
        return []
    cn = cnbc_fx()
    out = []
    for sym, name, u in FUT:
        if name in CNBC_FX.values():                     # 달러: CNBC·야후 24시간 중 더 최근 값(점수판 기록). 하이퍼리퀴드 환율은 거래 멈춤이라 안 씀(11/16)
            best = pick_fx(name, cn.get(name))
            if best:
                out.append({"name": name, **best, "u": u})
            continue
        x = c.get(sym)
        if x and float(x.get("prevDayPx") or 0) and float(x.get("dayNtlVlm") or 0) > 0:   # 거래량 0 = 멈춘 상품은 싣지 않음
            px, prev = float(x["markPx"]), float(x["prevDayPx"])
            out.append({"name": name, "px": px, "chg": round((px / prev - 1) * 100, 2), "u": u, "base": "24시간 전", "ref": prev, "src": "하이퍼리퀴드"})
    return out


CNBC_FX = {".DXY": "달러인덱스", "KRW=": "원/달러", "JPY=": "엔/달러"}


def cnbc_fx() -> dict:
    """CNBC 실시간 환율(24시간 갱신). 실패하면 빈 값 → 하이퍼리퀴드(거래 있는 것만)."""
    u = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=" + urllib.request.quote("|".join(CNBC_FX))
         + "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json")
    out = {}
    try:
        qs = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read())
        for q in qs["FormattedQuoteResult"]["FormattedQuote"]:
            px, prev = float(str(q["last"]).replace(",", "")), float(str(q["previous_day_closing"]).replace(",", ""))
            if px > 0 and prev > 0 and q.get("symbol") in CNBC_FX:
                out[CNBC_FX[q["symbol"]]] = {"px": round(px, 3), "chg": round((px / prev - 1) * 100, 2), "src": "CNBC",
                                             "base": "전일 종가", "ref": round(prev, 3),
                                             "at": int(datetime.fromisoformat(q["last_time"]).timestamp() * 1000)}
    except Exception:  # noqa: BLE001
        pass
    return out


KR_24H = {"코스피200": ("xyz:KR200", "KR200"), "삼성전자": ("xyz:SMSN", "SMSN"), "SK하이닉스": ("xyz:SKHX", "SKHX")}


YAHOO_FX = {"달러인덱스": "DX-Y.NYB", "원/달러": "KRW=X", "엔/달러": "JPY=X"}


def yahoo_fx(name: str) -> dict | None:
    """야후 24시간 환율·달러지수(평일 24시간 갱신). 기준 = 전일 종가(chartPreviousClose)."""
    try:
        u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(YAHOO_FX[name])}?interval=1m&range=1d"
        m = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read())["chart"]["result"][0]["meta"]
        px, prev = float(m["regularMarketPrice"]), float(m.get("chartPreviousClose") or m.get("previousClose") or 0)
        if px > 0 and prev > 0:
            return {"px": round(px, 3), "chg": round((px / prev - 1) * 100, 2), "src": "야후", "base": "전일 종가", "ref": round(prev, 3),
                    "at": int(m.get("regularMarketTime", 0)) * 1000}
    except Exception:  # noqa: BLE001
        pass
    return None


def pick_fx(name: str, cnbc: dict | None) -> dict | None:
    """CNBC 와 야후 중 마지막 체결이 더 최근인 값(같으면 CNBC). 두 값 차이가 0.3% 넘으면 일치 실패로 기록."""
    import srcscore
    g, now = "fx:" + name, time.time()
    cands = {}
    if cnbc:
        cands["CNBC"] = cnbc
    else:
        srcscore.record(g, "CNBC", False)
    y = None if srcscore.skip(g, "야후") else yahoo_fx(name)
    if y:
        cands["야후"] = y
    elif not srcscore.skip(g, "야후"):
        srcscore.record(g, "야후", False)
    if not cands:
        return None
    both = len(cands) == 2 and abs(cands["CNBC"]["px"] / cands["야후"]["px"] - 1) <= 0.003
    for s, v in cands.items():
        srcscore.record(g, s, True, agree=both if len(cands) == 2 else None, age_min=(now - (v.get("at") or 0) / 1000) / 60 if v.get("at") else None)
    return max(cands.values(), key=lambda v: (v.get("at") or 0, v.get("src") == "CNBC"))


def since_close(fut: list[dict], kr: dict) -> None:
    """한국 24시간 시세(하이퍼리퀴드)에 '마지막 거래소 종가 이후 변화'를 붙인다(11/15 운영자 승인 — 주말에 24시간 -0.13%와
    실제 금요일 종가 -1.05%가 섞여 보이던 문제). 한국장 중에는 붙이지 않는다(거래소 실시간이 기준)."""
    import urllib.request
    for f in fut:
        m = KR_24H.get(f["name"])
        k = kr.get(m[1]) if m else None
        if not (m and k and k.get("at")) or k.get("open"):
            continue
        t = int(k["at"])
        try:
            body = json.dumps({"type": "candleSnapshot", "req": {"coin": m[0], "interval": "5m", "startTime": t - 15 * 60_000, "endTime": t + 5 * 60_000}}).encode()
            cs = json.loads(urllib.request.urlopen(urllib.request.Request("https://api.hyperliquid.xyz/info", body,
                                                                          {"Content-Type": "application/json"}), timeout=8).read())
            base = float([c for c in cs if int(c["t"]) <= t][-1]["c"])
        except Exception:  # noqa: BLE001
            continue
        if base > 0:
            f.update(since_close=round((f["px"] / base - 1) * 100, 2), close_at=t, close_chg=k.get("chg"), close_ref=base)


def make(out: dict) -> dict:
    now = datetime.now(timezone.utc).timestamp() * 1000
    items = {it["ts"]: it for it in out.get("items", [])}
    mv = [m for m in out.get("moves", []) if now - m["start"] < 24 * 3600_000]
    top = sorted(mv, key=lambda m: -m.get("ratio", 0))[:3]
    moves = [{"name": m["name"], "asset": m["asset"], "move": m["move"], "unit": m["unit"], "start": m["start"], "end": m["end"],
              "ratio": m["ratio"], "news": [it["text"] for it in (m.get("items") or [items[t] for t in m.get("news", []) if t in items])][:1]}
             for m in top]
    sectors = []
    for c in out.get("sectors", []):
        rows = c.get("rows") or []
        if not rows:
            continue
        sectors.append({"name": c["name"], "icon": c.get("icon", ""), "avg": c["avg"],
                        "best": {"name": rows[0]["name"], "chg": rows[0]["chg"]}, "worst": {"name": rows[-1]["name"], "chg": rows[-1]["chg"]},
                        "flags": sum(1 for r in rows if r.get("flags"))})
    world = out.get("world", [])
    w = {"up": sum(1 for x in world if x["chg"] > 0), "down": sum(1 for x in world if x["chg"] < 0)}
    if world:
        b, k = max(world, key=lambda x: x["chg"]), min(world, key=lambda x: x["chg"])
        w.update(best={"name": b["name"], "chg": b["chg"]}, worst={"name": k["name"], "chg": k["chg"]})
    # 경제지표 발표(최근 12시간) · 주요 속보(최근 3시간)
    news = [it for it in out.get("items", []) if now - it["ts"] < 12 * 3600_000]
    macro, seen = [], set()
    for it in news:
        t = it["text"]
        if it.get("kind") in ("증권사 시황", "시황 분석") or not (MACRO.search(t) and MACRO_NUM.search(t) and re.search(r"\d", t)):
            continue
        ctry = re.search(r"한국|미국|일본|중국|유로존|독일|영국|호주|캐나다", t)
        key = (ctry.group() if ctry else "") + MACRO.search(t).group() + ("전년" if "전년" in t else "전분기" if "전분기" in t else "전월" if "전월" in t else "")
        if key in seen:
            continue
        seen.add(key)
        macro.append({"ts": it["ts"], "text": re.sub(r"\s*\$거시경제\(\$MACRO\)", "", t)[:120], "src": it.get("src", "")})
        if len(macro) >= 6:
            break
    piv = {t for m in out.get("moves", []) for t in m.get("news", [])}
    def score(it):
        return (8 if it["ts"] in piv else 0) + (4 if it.get("hot") else 0) + (3 if it.get("kind") == "섹터 시세" else 0)             + (1 if HOT_TAGS & set(it.get("tags") or []) else 0)             + (4 if re.search(r"(니케이|닛케이|코스피|코스닥|나스닥|S&P|다우|항셍|선물|유가|WTI|브렌트|금값|국채).{0,25}\d+(\.\d+)?\s?%\s?(상승|하락|급등|급락)", it["text"]) else 0)
    cand = [it for it in news if now - it["ts"] < 3 * 3600_000 and it.get("kind") not in ("증권사 시황", "시황 분석")
            and not any(it["ts"] == m["ts"] for m in macro) and not re.search(r"입찰|낙찰|응찰|Bid-to-Cover", it["text"])]
    heads, hs = [], set()
    for it in sorted(cand, key=lambda x: (-score(x), -x["ts"])):
        key = re.sub(r"[^가-힣A-Za-z]", "", it["text"])[:14]
        if key in hs or score(it) < 1:
            continue
        hs.add(key)
        heads.append({"ts": it["ts"], "text": it["text"][:120], "src": it.get("osrc") or it.get("src", ""), "pivot": it["ts"] in piv})
        if len(heads) >= 8:
            break
    heads.sort(key=lambda x: -x["ts"])
    # 📝 텔레 시황 분석(카이에 드 마켓·나쁜양파·증권사 전략 등) — 최근 12시간, 중요도 순 3건
    ana = sorted((it for it in news if it.get("kind") in ("시황 분석", "증권사 시황")), key=lambda x: (-(x.get("imp") or 0), -x["ts"]))[:3]
    analysis = [{"ts": it["ts"], "text": it["text"][:120], "sub": (it.get("sub") or "")[:160], "src": it.get("src", ""), "imp": it.get("imp")} for it in ana]
    fut = futures()
    since_close(fut, out.get("kr") or {})
    try:                                                  # NH 실제 선물(코스피200 주간·야간, CME E-mini) — 맨 앞에(11/15 운영자)
        from nhfut import quotes as nh_fut
        nq = nh_fut()
        fut[:0] = [{"name": v["name"], "px": v["px"], "chg": v["chg"], "u": "", "src": "NH", "real": True,
                    **({"base": v["base"]} if v.get("base") else {}), **({"ref": v["ref"]} if v.get("ref") else {})}
                   for k, v in nq.items() if v.get("chg") is not None]
    except Exception:  # noqa: BLE001
        pass
    tnx = out.get("us10y") or {}
    return {"at": int(now), "session": session(datetime.now(timezone.utc)), "futures": fut, "kr": out.get("kr") or {},
            "us10y": {"px": tnx.get("px"), "bp": tnx.get("bp")} if tnx.get("px") else None,
            "ust": {k: {"px": v["px"], "bp": v["bp"], "prev": v.get("prev"), "src": v.get("src"), "at": v.get("at")} for k, v in (out.get("ust") or {}).items()},
            "official": out.get("official") or {},
            "macro": macro, "heads": heads, "analysis": analysis, "moves": moves, "trending": [{"name": t["name"], "n": t["n"]} for t in out.get("trending", [])[:5]],
            "sectors": sectors, "world": w, "spot": [{"name": s["name"], "chg": s.get("chg")} for s in out.get("spot", [])],
            "ext": out.get("ext") or None}


def save(brief: dict) -> bool:
    """오늘(한국 날짜) 기록이 없으면 저장. 저장했으면 True."""
    day = datetime.now(KST).strftime("%Y-%m-%d")
    try:
        hist = json.loads(BRIEFS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        hist = []
    hist = [h for h in hist if isinstance(h, dict) and isinstance(h.get("day"), str) and h["day"] >= HISTORY_FROM]
    noon = lambda h: h.get("day") == day and h.get("slot", "12:00") == "12:00"
    old = next((h for h in hist if noon(h)), None)
    if old and datetime.fromtimestamp(old["at"] / 1000, KST).hour >= 11:
        return False                                      # 오늘 12시 기록이 이미 있음
    hist = [{"day": day, "slot": "12:00", **brief}] + [h for h in hist if not noon(h)]   # 다른 슬롯 기록은 그대로
    BRIEFS.write_text(json.dumps(hist[:120], ensure_ascii=False, indent=1), encoding="utf-8")
    return True
