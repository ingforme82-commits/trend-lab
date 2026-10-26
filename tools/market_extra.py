"""해외 지수 · 이번 주 화제 종목 · 오늘 뉴스에 많이 나온 종목 (news.json에 함께 싣는다)

- 해외 지수: 야후 5분봉(장중 갱신, 5분마다만 새로 받음). 대만은 야후 지수가 멈춰 있어 하이퍼리퀴드 EWT(24시간)를 쓴다.
- 화제 종목: data/site.json 의 spotlight(spot.py로 켜고 끔). 하이퍼리퀴드에 없는 종목은 야후로 값을 받는다.
- 많이 나온 종목: 최근 24시간 뉴스 헤드라인에서 종목 이름·티커 언급 수를 센다(사실 집계, 추천 아님).
"""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tools" / "world_cache.json"

WORLD = [  # (심볼, 이름, 지역, 출처)
    ("^N225", "니케이225", "일본", "yf"), ("000001.SS", "상하이종합", "중국", "yf"), ("000300.SS", "CSI300", "중국", "yf"),
    ("^HSI", "항셍", "홍콩", "yf"), ("xyz:EWT", "대만(EWT·24시간)", "대만", "hl"),
    ("^GDAXI", "DAX", "독일", "yf"), ("^FCHI", "CAC40", "프랑스", "yf"), ("^STOXX50E", "유로스톡스50", "유럽", "yf"),
]

# 종목 이름 사전(언급 수 집계용): 표시 이름 → 찾을 말
NAMES = {
    "테슬라": r"테슬라|Tesla|\$TSLA", "엔비디아": r"엔비디아|Nvidia|NVIDIA|\$NVDA", "애플": r"애플|Apple\b|\$AAPL",
    "마이크로소프트": r"마이크로소프트|Microsoft|\$MSFT", "알파벳(구글)": r"알파벳|구글|Alphabet|Google|\$GOOGL?",
    "아마존": r"아마존|Amazon|\$AMZN", "메타": r"메타|Meta\b|\$META", "브로드컴": r"브로드컴|Broadcom|\$AVGO",
    "AMD": r"\bAMD\b", "마이크론": r"마이크론|Micron|\$MU\b", "TSMC": r"TSMC|\$TSM\b", "인텔": r"인텔|Intel\b|\$INTC",
    "팔란티어": r"팔란티어|Palantir|\$PLTR", "코어위브": r"코어위브|CoreWeave|\$CRWV", "오라클": r"오라클|Oracle|\$ORCL",
    "스페이스X": r"스페이스X|SpaceX|\$SPCX", "앤트로픽": r"앤트로픽|앤스로픽|Anthropic|\$ANT\b", "오픈AI": r"오픈AI|OpenAI",
    "삼성전자": r"삼성전자", "SK하이닉스": r"하이닉스|SK hynix|Hynix", "현대차": r"현대차|현대자동차|Hyundai Motor",
    "LG에너지솔루션": r"LG에너지솔루션|LG엔솔", "한화에어로스페이스": r"한화에어로", "두산에너빌리티": r"두산에너빌리티",
    "삼성전기": r"삼성전기", "셀트리온": r"셀트리온", "카카오": r"카카오", "네이버": r"네이버|NAVER",
    "코인베이스": r"코인베이스|Coinbase", "비트코인": r"비트코인|Bitcoin",
    "루멘텀": r"루멘텀|Lumentum|\$LITE", "코히런트": r"코히런트|Coherent|\$COHR", "광통신": r"광통신|광트랜시버|광모듈|CPO", "네비우스": r"네비우스|Nebius|\$NBIS",
}


def _yf(sym: str) -> dict | None:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range=1d&interval=5m"
    try:
        j = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=12).read())
        r = j["chart"]["result"][0]
        m = r["meta"]
        pts = [[t * 1000, round(c, 2)] for t, c in zip(r.get("timestamp") or [], r["indicators"]["quote"][0]["close"]) if c]
        return {"px": m.get("regularMarketPrice"), "prev": m.get("chartPreviousClose"), "at": m["regularMarketTime"] * 1000, "spark": pts}
    except Exception:  # noqa: BLE001
        return None


def _hl_ctx() -> dict:
    try:
        req = urllib.request.Request("https://api.hyperliquid.xyz/info", data=b'{"type":"metaAndAssetCtxs","dex":"xyz"}',
                                     headers={"Content-Type": "application/json"})
        meta, ctx = json.loads(urllib.request.urlopen(req, timeout=12).read())
        return {a["name"]: c for a, c in zip(meta["universe"], ctx)}
    except Exception:  # noqa: BLE001
        return {}


def world_and_spot() -> tuple[list[dict], list[dict]]:
    """5분마다만 새로 받고 그 사이에는 저장본을 쓴다."""
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
        if datetime.now(timezone.utc).timestamp() - cache["at"] < 290:
            return cache["world"], cache["spot"]
    except Exception:  # noqa: BLE001
        cache = None
    hl = _hl_ctx()
    world = []
    for sym, name, region, src in WORLD:
        if src == "hl":
            c = hl.get(sym)
            if c:
                px, prev = float(c["markPx"]), float(c["prevDayPx"])
                world.append({"sym": sym, "name": name, "region": region, "px": px, "chg": round((px / prev - 1) * 100, 2),
                              "at": int(datetime.now(timezone.utc).timestamp() * 1000), "live": True})
            continue
        d = _yf(sym)
        if d and d["px"] and d["prev"]:
            world.append({"sym": sym, "name": name, "region": region, "px": d["px"], "chg": round((d["px"] / d["prev"] - 1) * 100, 2),
                          "at": d["at"], "spark": d["spark"][::2]})
    # 화제 종목
    spot = []
    try:
        cfg = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8")).get("spotlight", [])
    except Exception:  # noqa: BLE001
        cfg = []
    for s in cfg:
        if not s.get("on"):
            continue
        row = {k: s.get(k) for k in ("id", "name", "market", "reason", "since", "kw", "hl", "yf")}
        if s.get("members"):                              # 종목군: 구성 종목별 오늘 등락·3개월 고점 대비
            from concurrent.futures import ThreadPoolExecutor
            from sector_watch import _quote
            syms = list(s["members"])
            with ThreadPoolExecutor(max_workers=8) as ex:
                qs = dict(zip(syms, ex.map(_quote, syms)))
            mem = []
            for sym, nm in s["members"].items():
                qd = qs.get(sym)
                if qd and qd.get("px") and qd.get("prev"):
                    mem.append({"sym": sym, "name": nm, "cur": qd.get("cur", "USD"), "px": round(qd["px"], 2), "chg": round((qd["px"] / qd["prev"] - 1) * 100, 2),
                                "to3m": round((qd["px"] / qd["hi3m"] - 1) * 100, 1) if qd.get("hi3m") else None})
            row["members"] = mem
            if mem:
                row["chg"] = round(sum(m["chg"] for m in mem) / len(mem), 2)       # 종목군 평균
                row["avg"] = True
        if s.get("members"):
            pass
        elif s.get("hl") and hl.get(s["hl"]):
            c = hl[s["hl"]]
            px, prev = float(c["markPx"]), float(c["prevDayPx"])
            row.update(px=px, chg=round((px / prev - 1) * 100, 2), live=True)
        elif s.get("yf"):
            d = _yf(s["yf"])
            if d and d["px"] and d["prev"]:
                row.update(px=d["px"], chg=round((d["px"] / d["prev"] - 1) * 100, 2), at=d["at"])
        spot.append(row)
    if world or not cache:
        CACHE.write_text(json.dumps({"at": datetime.now(timezone.utc).timestamp(), "world": world, "spot": spot}, ensure_ascii=False), encoding="utf-8")
        return world, spot
    return cache["world"], cache["spot"]


def trending(items: list[dict], hours: int = 24) -> list[dict]:
    """최근 뉴스 헤드라인에서 종목 언급 수(같은 소식 중복은 이미 걸러진 목록 기준)."""
    now = datetime.now(timezone.utc).timestamp() * 1000
    recent = [it for it in items if now - it["ts"] < hours * 3600_000]
    out = []
    for name, pat in NAMES.items():
        rx = re.compile(pat)
        hits = [it for it in recent if rx.search(it["text"] + " " + it.get("orig", "") + " " + it.get("sub", ""))]
        if len(hits) >= 2:
            out.append({"name": name, "n": len(hits), "kw": pat, "last": max(h["ts"] for h in hits)})
    out.sort(key=lambda x: (-x["n"], -x["last"]))
    return out[:10]


def dow() -> dict:
    """다우존스: 지수(^DJI, 미국 정규장)와 미니 다우 선물(YM=F, 거의 24시간). 1분마다."""
    out = {}
    for key, sym in (("idx", "^DJI"), ("fut", "YM=F")):
        u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range=1d&interval=1m"
        try:
            m = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read())["chart"]["result"][0]["meta"]
            px, prev = m.get("regularMarketPrice"), m.get("previousClose") or m.get("chartPreviousClose")
            if px and prev:
                out[key] = {"px": px, "chg": round((px / prev - 1) * 100, 2), "at": m.get("regularMarketTime", 0) * 1000}
        except Exception:  # noqa: BLE001
            pass
    return out


def us10y() -> dict:
    """미 10년물 국채 금리(^TNX, %). 전일 대비 변화는 bp. 미국 채권시장 시간에 갱신."""
    u = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?range=1d&interval=1m"
    try:
        m = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read())["chart"]["result"][0]["meta"]
        px, prev = m.get("regularMarketPrice"), m.get("previousClose") or m.get("chartPreviousClose")
        if px and prev:
            return {"px": round(px, 3), "bp": round((px - prev) * 100, 1), "prev": round(prev, 3), "at": m.get("regularMarketTime", 0) * 1000}
    except Exception:  # noqa: BLE001
        pass
    return {}
