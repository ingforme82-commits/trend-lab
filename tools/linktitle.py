"""링크만 올린 텔레그램 글 → 기사 제목·언론사(og:title·og:site_name). 사이트에는 링크 없이 '제목 · 언론사'만 싣는다.

- 한 번 받은 제목은 tools/linktitle_cache.json 에 저장(다시 받지 않음), 실행마다 새로 받는 건 최대 BUDGET 개
- http(s)만, 5초 제한, 앞 300KB만 읽음
"""

from __future__ import annotations

import html
import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

CACHE = Path(__file__).resolve().parent / "linktitle_cache.json"
BUDGET = 8
URL_ONLY = re.compile(r"^\s*(https?://\S+)\s*$")
OUTLET = {"hankyung.com": "한국경제", "hani.co.kr": "한겨레", "mk.co.kr": "매일경제", "chosun.com": "조선일보", "joongang.co.kr": "중앙일보",
          "donga.com": "동아일보", "yna.co.kr": "연합뉴스", "edaily.co.kr": "이데일리", "sedaily.com": "서울경제", "mt.co.kr": "머니투데이",
          "fnnews.com": "파이낸셜뉴스", "hankookilbo.com": "한국일보", "khan.co.kr": "경향신문", "asiae.co.kr": "아시아경제",
          "newsis.com": "뉴시스", "news1.kr": "뉴스1", "etnews.com": "전자신문", "thelec.kr": "디일렉", "bloomberg.com": "Bloomberg",
          "reuters.com": "Reuters", "wsj.com": "WSJ", "ft.com": "FT", "cnbc.com": "CNBC"}
_state = {"left": BUDGET}


def outlet_of(url: str, site_name: str | None = None) -> str:
    host = urlparse(url).hostname or ""
    for dom, name in OUTLET.items():
        if host == dom or host.endswith("." + dom):
            return name
    return site_name or host.replace("www.", "")


def _load() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def parse_meta(page: str) -> tuple[str | None, str | None]:
    def meta(prop: str) -> str | None:
        m = re.search(rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]*content=["\']([^"\']+)', page, re.I) or \
            re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{prop}["\']', page, re.I)
        return html.unescape(m.group(1)).strip() if m else None
    title = meta("og:title")
    if not title:
        m = re.search(r"<title[^>]*>([^<]{4,200})</title>", page, re.I)
        title = html.unescape(m.group(1)).strip() if m else None
    return title, meta("og:site_name")


def title_for(url: str) -> tuple[str, str] | None:
    """(제목, 언론사) 또는 None(못 받음·예산 소진)."""
    cache = _load()
    if url in cache:
        v = cache[url]
        return (v[0], v[1]) if v else None
    if _state["left"] <= 0 or not url.startswith(("http://", "https://")):
        return None
    _state["left"] -= 1
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko,en"})
        raw = urllib.request.urlopen(req, timeout=5).read(300_000)
        page = raw.decode("utf-8", "replace")
        if "charset=euc-kr" in page[:3000].lower() or "charset=\"euc-kr\"" in page[:3000].lower():
            page = raw.decode("cp949", "replace")
        t, site = parse_meta(page)
        val = [t[:160], outlet_of(url, site)] if t else None
    except Exception:  # noqa: BLE001
        val = None
    cache[url] = val
    try:
        CACHE.write_text(json.dumps(dict(list(cache.items())[-3000:]), ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return (val[0], val[1]) if val else None
