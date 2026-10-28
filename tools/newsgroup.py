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


# ── 발언·발표 연속 묶기(2026-10-29): 한 기자회견·발표에서 줄줄이 나오는 '발언자: 내용' 속보를 한 줄로 ──
# 문장이 서로 달라 위 group()으로는 안 묶이는 경우(예: 맥클럼 총재 기자회견 30여 줄, 영국 예산 발언 40여 줄)
SERIES_WINDOW_MS = 2 * 3600_000
ALIAS = [
    (r"맥클럼|매클럼|맥컬럼|BoC|캐나다\s*(?:중앙\s*)?은행|로저스\s*(?:선임|수석)?\s*부총재", "캐나다은행(BoC)"),
    (r"파월|연준\s*의장|\bFOMC\b|\bFed\b|연방준비제도", "연준(Fed)"),
    (r"라가르드|\bECB\b|유럽중앙은행", "유럽중앙은행(ECB)"),
    (r"우에다|\bBOJ\b|\bBoJ\b|일본은행", "일본은행(BOJ)"),
    (r"베일리|\bBOE\b|\bBoE\b|영란은행", "영란은행(BOE)"),
    (r"불록|\bRBA\b|호주\s*중앙은행", "호주중앙은행(RBA)"),
    (r"브레먼|\bRBNZ\b|뉴질랜드\s*중앙은행", "뉴질랜드중앙은행(RBNZ)"),
    (r"헤일리|힐리|리브스|영국\s*(?:재무장관|재무부|예산)|\bOBR\b|예산책임청", "영국 재무장관·예산"),
    (r"트럼프", "트럼프"),
    (r"베선트|미\s*재무장관", "미 재무장관"),
    (r"세계은행", "세계은행"),
    (r"\bOPEC\b|오펙", "OPEC"),
]
_ALIAS = [(re.compile(p, re.I), k) for p, k in ALIAS]
_GENERIC = {"속보", "단독", "특징주", "시황", "뉴스", "마감", "개장", "오전", "오후", "업데이트", "종합", "분석"}


def speaker_key(it: dict) -> str | None:
    """'발언자: 내용' / '발언자, 내용' 앞부분(30자 안)에서 발언자·기관 열쇠를 찾는다. 못 찾으면 None(묶지 않음)."""
    t = re.sub(r"^\s*(\[[^\]]{1,14}\]|[^\w\s]+)\s*", "", it.get("text", ""))
    if it.get("kind") == "섹터 시세":
        m = re.match(r"^\W*([^:：]{2,20})[:：]", it.get("text", ""))
        return "섹터:" + re.sub(r"\W", "", m.group(1)) if m else None
    m = re.match(r"^([^:：,，\"“]{2,30})([:：,，])", t)
    if not m:
        return None
    pre, sep = m.group(1), m.group(2)
    for rx, k in _ALIAS:                                   # 알려진 발언자·기관: '이름: …' 과 '이름, …' 모두
        if rx.search(pre):
            return k
    if sep not in ":：":                                   # 그 밖에는 '발언자: 내용' 꼴만 — '삼성전자, …' 같은 헤드라인은 묶지 않음
        return None
    w = re.sub(r"[^0-9A-Za-z가-힣]", "", pre)              # 앞부분 전체가 같아야 같은 발언자(예: '영국 국채관리청(DMO)')
    return w if len(w) >= 3 and w not in _GENERIC and not w.isdigit() and not re.fullmatch(r"(미국|영국|중국|일본|한국|유럽|이란|러시아|독일|프랑스)", w) else None


def series(items: list[dict]) -> list[dict]:
    """같은 발언자·기관(speaker_key)의 속보가 2시간 안에 이어지면 한 줄로: 중요도(imp) 가장 높은 것(같으면 최신)이 대표,
    나머지는 series=[{ts,text}](최신순 12개), series_n=총 건수, series_key=묶음 이름. 시세 감시·자동 집계 외 일반 속보와 섹터 시세만."""
    by: dict[str, list[list[dict]]] = {}
    out_other = []
    for it in sorted(items, key=lambda x: -x["ts"]):
        k = None if it.get("kind") in ("증권사 시황", "시황 분석", "관전 포인트", "주도 섹터") else speaker_key(it)
        if not k:
            out_other.append(it)
            continue
        runs = by.setdefault(k, [])
        if runs and runs[-1][-1]["ts"] - it["ts"] <= SERIES_WINDOW_MS:
            runs[-1].append(it)
        else:
            runs.append([it])
    out = out_other
    for k, runs in by.items():
        for run in runs:
            if len(run) == 1:
                out.append(run[0])
                continue
            rep = max(run, key=lambda x: (x.get("imp") or 0, x["ts"]))
            rest = sorted((x for x in run if x is not rep), key=lambda x: -x["ts"])
            r = dict(rep, series_key=k.replace("섹터:", ""), series_n=len(run),
                     series=[{"ts": x["ts"], "text": x["text"][:140]} for x in rest[:12]])
            r["hot"] = any(x.get("hot") for x in run)
            out.append(r)
    return sorted(out, key=lambda x: -x["ts"])


def dup_report(items: list[dict], now_ms: int, hours: float = 1.0, min_n: int = 3) -> list[tuple[str, int]]:
    """묶은 뒤에도 최근 hours 시간 안에 같은 앞머리('○○: …' / '○○, …')가 min_n 건 넘게 남은 것 — 묶음 목록(ALIAS) 보강 후보."""
    cnt: dict[str, int] = {}
    for it in items:
        if now_ms - it["ts"] > hours * 3600_000 or it.get("series_n") or it.get("kind") in ("섹터 시세", "관전 포인트", "주도 섹터"):
            continue
        m = re.match(r"^\W*([^:：,，\"“]{2,20})[:：,，]", it.get("text", ""))
        if m:
            k = re.sub(r"[^0-9A-Za-z가-힣]", "", m.group(1).split()[0])
            if len(k) >= 2:
                cnt[k] = cnt.get(k, 0) + 1
    return sorted(((k, n) for k, n in cnt.items() if n >= min_n), key=lambda x: -x[1])
