"""Finnhub(무료, 분당 60회) — 미국 시세 교차 확인 · 실적 예상/실제 · 종목 뉴스(교차 보도 확인용).

키: FINNHUB_API_KEY(keystore). 값은 출력·로그에 남기지 않는다.
- quote(sym)              → {px, chg, prev, hi, lo, at}
- earnings(sym, d1, d2)   → 실적 일정(예상 EPS·매출, 발표 뒤 실제치)
- surprise(row)           → 예상 대비 차이(%)
- news(sym, d1, d2)       → [{at, src, title, url}]
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

BASE = "https://finnhub.io/api/v1/"
UA = {"User-Agent": "trendlab-client"}


def _get(path: str, **params) -> dict | list:
    key = keystore.get("FINNHUB_API_KEY")
    if not key:
        raise RuntimeError("FINNHUB_API_KEY 없음")
    q = urllib.parse.urlencode({**params, "token": key})
    req = urllib.request.Request(f"{BASE}{path}?{q}", headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def parse_quote(d: dict) -> dict | None:
    if not d or not d.get("c"):
        return None
    return {"px": d["c"], "chg": round(d.get("dp") or 0, 2), "prev": d.get("pc"), "hi": d.get("h"), "lo": d.get("l"),
            "at": int(d.get("t") or 0) * 1000}


def quote(sym: str) -> dict | None:
    return parse_quote(_get("quote", symbol=sym))


def earnings(sym: str, d1: str, d2: str) -> list[dict]:
    return (_get("calendar/earnings", symbol=sym, **{"from": d1, "to": d2}) or {}).get("earningsCalendar", [])


def surprise(row: dict) -> dict:
    """예상 대비 실제(%) — 실제치가 없으면 None."""
    def pct(a, e):
        return round((a / e - 1) * 100, 2) if a is not None and e not in (None, 0) else None
    return {"eps": pct(row.get("epsActual"), row.get("epsEstimate")),
            "rev": pct(row.get("revenueActual"), row.get("revenueEstimate"))}


def parse_news(rows: list) -> list[dict]:
    return [{"at": int(r.get("datetime") or 0) * 1000, "src": r.get("source", ""), "title": r.get("headline", ""),
             "url": r.get("url", "")} for r in rows or [] if r.get("headline")]


def news(sym: str, d1: str, d2: str) -> list[dict]:
    return parse_news(_get("company-news", symbol=sym, **{"from": d1, "to": d2}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for s in sys.argv[1:] or ["NVDA"]:
        print(s, quote(s))
        time.sleep(0.2)
