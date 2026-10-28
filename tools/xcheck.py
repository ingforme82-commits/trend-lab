"""🌐 외신 교차 확인 — 김치터미널(한국어 번역 속보)을 해외 언론 원문 헤드라인과 대조한다. live_news.py 가 1분마다 호출.

1) 속보를 영어로 옮기고(gtx), 고유명사·숫자로 검색어를 만든다
2) 먼저 이미 받은 해외 RSS 원문과, 없으면 구글 뉴스 검색(최근 1일)과 비교 — 핵심 단어 겹침으로 같은 소식인지 판단
3) 같은 소식이면: 언론사 등급(주요 외신 / 공식 보도자료 / 기타 매체), 원문 헤드라인과 그 한국어 번역을 붙인다
4) 수치 대조: %·달러 금액이 양쪽에 모두 있는데 하나도 맞지 않으면 '수치 다름'으로 표시
- 한 번에 최대 5건, 못 찾으면 10분·40분 뒤 다시(최대 3번). 결과는 tools/xcheck_cache.json 에 저장
- 사이트에는 언론사 이름과 헤드라인 텍스트만 싣는다(외부 링크 없음). 판단은 단어·수치 비교뿐(AI 문장 생성 없음)
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tools" / "xcheck_cache.json"
SRCS = {"김치터미널"}
BUDGET = 5
RETRY_MIN = (10, 40)
UA = {"User-Agent": "Mozilla/5.0"}

TIER1 = re.compile(r"Reuters|Bloomberg|Associated Press|AP News|\bAFP\b|Wall Street Journal|WSJ|Financial Times|\bFT\b|CNBC|BBC|"
                   r"New York Times|Al Jazeera|Axios|MarketWatch|Barron|Nikkei|Yonhap|Guardian|Politico|CNN|Fox Business|"
                   r"S&P Global|Argus|Platts|Times of Israel|Washington Post|The Economist|Dow Jones|Kyodo|Xinhua|TASS|Interfax", re.I)
OFFICIAL = re.compile(r"PR Newswire|Business Wire|GlobeNewswire|Federal Reserve|White House|Department of|Treasury|SEC\b|"
                      r"Investor Relations|Newsroom", re.I)
STOP = set("the a an of to in on for and or is are was were be been by with as at from that this it its has have had will would could "
           "should can may said says say after over into new us u.s amid about than more less up down per vs not no but if also "
           "report reports reported results stock stocks shares market markets news according latest live update".split())


# ── 순수 함수(tests/test_xcheck.py) ──
def toks(s: str) -> set[str]:
    return {w.strip(".") for w in re.findall(r"[a-z0-9][a-z0-9.\-]*", s.lower().replace("’", "'")) if w.strip(".") not in STOP and len(w.strip(".")) > 1}


def query_of(en: str) -> str:
    """고유명사(대문자 시작)·숫자 위주로 최대 5단어."""
    out: list[str] = []
    for w in re.findall(r"[A-Z][A-Za-z\-&]+|\d+(?:\.\d+)?%?", en):
        if w.lower() not in STOP and w.lower() not in (x.lower() for x in out):
            out.append(w)
    return " ".join(out[:5])


def similar(a_en: str, b_en: str) -> float:
    """같은 소식 점수(0~1): 겹친 핵심 단어 / 짧은 쪽 단어 수. 겹친 단어가 3개 미만이면 0."""
    a, b = toks(a_en), toks(b_en)
    sh = a & b
    if len(sh) < 3 or not a or not b or len(sh) / len(a | b) < 0.25:   # 지명(이란·호르무즈 등)만 겹치는 다른 기사 거르기
        return 0.0
    return round(len(sh) / min(len(a), len(b)), 2)


def tier_of(src: str) -> str:
    return "official" if OFFICIAL.search(src or "") else "major" if TIER1.search(src or "") else "other"


_MUL_KO = {"조": 1e12, "억": 1e8, "만": 1e4, "천": 1e3}
_MUL_EN = {"trillion": 1e12, "tn": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6, "m": 1e6}


def nums_ko(s: str) -> dict[str, set[float]]:
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    s = re.sub(r"\d{4}년|\d+월\s*\d+일|\d+분기|\d+번째|\d+척|\d+명|\d+시|\d+분(?!기)", " ", s)
    out = {"pct": set(), "usd": set()}
    for v in re.findall(r"(\d+(?:\.\d+)?)\s*%", s):
        out["pct"].add(float(v))
    for v in re.findall(r"\$\s?(\d+(?:\.\d+)?)", s):
        out["usd"].add(float(v))
    for amount in re.findall(r"((?:\d+(?:\.\d+)?\s*[조억만천]\s*)+\d*(?:\.\d+)?)\s*달러", s):
        parts = re.findall(r"(\d+(?:\.\d+)?)\s*([조억만천])", amount)
        tail = re.sub(r"\d+(?:\.\d+)?\s*[조억만천]\s*", "", amount).strip()
        out["usd"].add(sum(float(v) * _MUL_KO[mul] for v, mul in parts) + (float(tail) if tail else 0))
    return out


def nums_en(s: str) -> dict[str, set[float]]:
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    out = {"pct": set(), "usd": set()}
    for v in re.findall(r"(\d+(?:\.\d+)?)\s*(?:%|percent|pct)", s, re.I):
        out["pct"].add(float(v))
    for v, mul in re.findall(r"\$\s?(\d+(?:\.\d+)?)\s*(trillion|billion|million|tn|bn|mn|m)?\b", s, re.I):
        out["usd"].add(float(v) * _MUL_EN.get(mul.lower(), 1) if mul else float(v))
    return out


def num_conflict(ko: str, en: str) -> bool:
    a, b = nums_ko(ko), nums_en(en)
    close = lambda x, y: abs(x - y) <= max(abs(x), abs(y)) * 0.01
    for k in ("pct", "usd"):
        if a[k] and b[k] and not any(close(x, y) for x in a[k] for y in b[k]):
            return True
    return False


def judge(ko: str, en_ko: str, cands: list[dict], ts: int) -> dict | None:
    """cands=[{title, src, ts}] 중 같은 소식(점수 0.45 이상, 보도 시각 ±12시간)을 골라 결과로."""
    best = []
    for c in cands:
        if c.get("ts") and abs(c["ts"] - ts) > 12 * 3600_000:
            continue
        sc = similar(en_ko, c["title"])
        if sc >= 0.45:
            best.append((sc, {"official": 2, "major": 1}.get(tier_of(c["src"]), 0), c))
    if not best:
        return None
    best.sort(key=lambda x: (-x[1], -x[0]))
    top = best[0][2]
    srcs = []
    for _, _, c in best:
        if c["src"] not in srcs:
            srcs.append(c["src"])
    tiers = {tier_of(s) for s in srcs}
    st = "diff" if num_conflict(ko, top["title"]) else "ok" if tiers & {"major", "official"} else "ref"
    return {"st": st, "src": srcs[:3], "en": top["title"][:200], "tier": tier_of(top["src"]), "score": best[0][0]}


# ── 수집 ──
def _gtx(text: str, sl: str, tl: str) -> str:
    u = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode({"client": "gtx", "sl": sl, "tl": tl, "dt": "t", "q": text})
    r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=10).read())
    return "".join(x[0] for x in r[0] if x and x[0]).strip()


def gnews(q: str) -> list[dict]:
    u = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:1d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    x = ET.fromstring(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=10).read())
    out = []
    for i in list(x.iter("item"))[:20]:
        src = i.findtext("source") or ""
        title = (i.findtext("title") or "")
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        try:
            ts = int(parsedate_to_datetime(i.findtext("pubDate")).timestamp() * 1000)
        except Exception:  # noqa: BLE001
            ts = 0
        out.append({"title": title, "src": src, "ts": ts})
    return out


def _check(it: dict, rss_en: list[dict]) -> dict | None:
    en = _gtx(it["text"], "ko", "en")
    res = judge(it["text"], en, rss_en, it["ts"])
    if not res or res["st"] == "ref":
        q = query_of(en)
        if q:
            g = judge(it["text"], en, gnews(q), it["ts"])
            if g and (not res or g["st"] != "ref"):
                res = g
    return res


def run(items: list[dict], rss: list[dict], tr_ko=None) -> int:
    """items 중 대상 출처 속보에 xc 결과를 붙인다(제자리 수정). 새로 확인한 건수를 돌려준다."""
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cache = {}
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    rss_en = [{"title": r["orig"], "src": r.get("src", ""), "ts": r["ts"]} for r in rss if r.get("orig")]
    todo = []
    for it in items:
        if it.get("src") not in SRCS or it.get("kind") in ("증권사 시황", "시황 분석"):
            continue
        key = it["text"][:100]
        c = cache.get(key)
        if c and c.get("res"):
            res = dict(c["res"])
            res["st"] = "diff" if num_conflict(it["text"], res["en"]) else "ok" if res["tier"] in {"major", "official"} else "ref"
            c["res"] = it["xc"] = res
            continue
        if now - it["ts"] > 3 * 3600_000:
            continue
        n = (c or {}).get("n", 0)
        if n > len(RETRY_MIN) or (n and now - c["first"] < RETRY_MIN[n - 1] * 60_000):
            continue
        todo.append((key, it, c))
    todo = todo[:BUDGET]

    def one(x):
        try:
            return _check(x[1], rss_en)
        except Exception:  # noqa: BLE001
            return "err"
    with ThreadPoolExecutor(max_workers=BUDGET) as ex:
        outs = list(ex.map(one, todo))
    for (key, it, c), res in zip(todo, outs):
        c = c or {"first": now, "n": 0}
        if res == "err":
            cache[key] = c                                   # 네트워크 오류는 횟수에 넣지 않음
            continue
        c["n"] += 1
        if res:
            if tr_ko:
                try:
                    res["ko"] = tr_ko(res["en"])
                except Exception:  # noqa: BLE001
                    pass
            c["res"] = res
            it["xc"] = res
        cache[key] = c
    for it in items:                                          # 주요 외신·공식 자료와 일치하면 '복수 출처'로
        if (it.get("xc") or {}).get("st") == "ok" and it.get("verify") == "single":
            it["verify"], it["nsrc"] = "multi", max(2, (it.get("nsrc") or 1) + 1)
    cut = now - 2 * 86400_000
    cache = {k: v for k, v in cache.items() if v.get("first", now) > cut}
    try:
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return len(todo)
