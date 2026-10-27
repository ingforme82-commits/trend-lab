"""속보를 사건 단위로 묶고 검증 상태를 붙인다(live_news.py 에서 사용, 순수 함수라 테스트 가능).

- 같은 소식(헤드라인 글자쌍 유사도 0.5 이상, 6시간 안)은 한 사건으로 묶는다.
- 대표 항목은 '최초 보도'(가장 이른 시각). 뒤이은 출처는 also 에 [{src, ts}] 로 남긴다.
- 검증 상태(verify)
    official      : 공식 기관 출처(연준·EIA 등)
    multi         : 서로 다른 출처 2곳 이상
    single        : 한 곳에서만
    unconfirmed   : 익명 소식통·보도 인용·루머 표현(공식 출처가 아니면 출처 수와 관계없이)
  시세 데이터('섹터 시세')와 증권사 시황·분석 글은 검증 대상이 아니라 verify 를 넣지 않는다.
"""

from __future__ import annotations

import re

OFFICIAL = {"미 연준", "미 EIA"}
NOT_NEWS = {"섹터 시세", "증권사 시황", "시황 분석"}
RUMOR = re.compile(r"루머|소문|찌라시|\b설\b|[가-힣]설$|미확인|소식통|관계자에 따르면|관계자들?에 따르면|익명|보도에 따르면|것으로 알려|전해졌|"
                   r"rumou?r|unconfirmed|reportedly|people familiar|sources? (?:say|said)|according to (?:people|sources|a report)|is said to", re.I)
WINDOW_MS = 6 * 3600_000
SIM = 0.5


def bigrams(s: str) -> set[str]:
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s.lower())
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similar(a: set[str], b: set[str]) -> bool:
    return bool(a) and bool(b) and len(a & b) / max(1, len(a | b)) >= SIM


def verify_of(members: list[dict]) -> str:
    srcs = {m["src"] for m in members}                    # 독립 출처 = 채널·언론사(같은 채널 재게시는 1곳)
    if srcs & OFFICIAL or any(m.get("osrc") in OFFICIAL for m in members):
        return "official"
    if any(RUMOR.search(m["text"] + " " + m.get("orig", "")) for m in members):
        return "unconfirmed"
    return "multi" if len(srcs) >= 2 else "single"


def group(items: list[dict]) -> list[dict]:
    """items(순서 무관) → 사건 대표 항목 목록(최신 최초보도 순). 원본 dict 는 바꾸지 않는다."""
    groups: list[dict] = []                     # {"g": bigrams, "m": [items]}
    for it in sorted(items, key=lambda x: x["ts"]):       # 이른 것부터 → 첫 항목이 최초 보도
        if it.get("kind") in NOT_NEWS:
            groups.append({"g": set(), "m": [it]})
            continue
        g = bigrams(it["text"])
        hit = None
        for gr in reversed(groups):
            first = gr["m"][0]
            if it["ts"] - first["ts"] > WINDOW_MS:
                break
            if first.get("kind") not in NOT_NEWS and similar(g, gr["g"]):
                hit = gr
                break
        if hit:
            hit["m"].append(it)
        else:
            groups.append({"g": g, "m": [it]})
    out = []
    for gr in groups:
        first = dict(gr["m"][0])
        if first.get("kind") not in NOT_NEWS:
            seen, also = {first["src"]}, []
            for m in gr["m"][1:]:
                if m["src"] not in seen:
                    seen.add(m["src"])
                    also.append({"src": m["src"], "ts": m["ts"]} | ({"osrc": m["osrc"]} if m.get("osrc") else {}))
            if also:
                first["also"] = also[:6]
            first["nsrc"] = len(seen)
            first["verify"] = verify_of(gr["m"])
            first["hot"] = any(m.get("hot") for m in gr["m"])
            tags = [t for t in dict.fromkeys(t for m in gr["m"] for t in m.get("tags", [])) if t != "기타"]
            first["tags"] = tags[:2] or first.get("tags", [])
        out.append(first)
    return sorted(out, key=lambda x: -x["ts"])
