"""한국은행 ECOS(무료) — 원/달러 매매기준율 · 국고채 3년 · 기준금리 · 코스피/코스닥 종가(하루 늦게 들어옴).

키: ECOS_API_KEY(keystore). 공식 확정치 교차 확인용(실시간 아님).
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

# 이름: (통계표, 주기, 항목)
SERIES = {
    "usdkrw": ("731Y001", "D", "0000001"),     # 원/달러 매매기준율
    "ktb3y": ("817Y002", "D", "010200000"),    # 국고채 3년(%)
    "base": ("722Y001", "M", "0101000"),       # 한국은행 기준금리(%)
    "kospi": ("802Y001", "D", "0001000"),      # 코스피 종가
    "kosdaq": ("802Y001", "D", "0089000"),     # 코스닥 종가
}


def parse(js: dict) -> list[tuple[str, float]]:
    rows = (js.get("StatisticSearch") or {}).get("row") or []
    out = []
    for r in rows:
        try:
            out.append((r["TIME"], float(r["DATA_VALUE"])))
        except (KeyError, ValueError):
            continue
    return out


def series(name: str, days: int = 14) -> list[tuple[str, float]]:
    key = keystore.get("ECOS_API_KEY")
    if not key:
        raise RuntimeError("ECOS_API_KEY 없음")
    code, cyc, item = SERIES[name]
    now = datetime.now()
    if cyc == "M":
        s, e = (now - timedelta(days=150)).strftime("%Y%m"), now.strftime("%Y%m")
    else:
        s, e = (now - timedelta(days=days)).strftime("%Y%m%d"), now.strftime("%Y%m%d")
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100/{code}/{cyc}/{s}/{e}/{item}"
    return parse(json.loads(urllib.request.urlopen(url, timeout=15).read()))


def latest(name: str) -> dict | None:
    rows = series(name)
    if not rows:
        return None
    d, v = rows[-1]
    prev = rows[-2][1] if len(rows) > 1 else None
    return {"date": d, "v": v, "chg": round(v - prev, 3) if prev is not None else None}


def build() -> dict:
    out = {}
    for n in SERIES:
        try:
            r = latest(n)
            if r:
                out[n] = r
        except Exception:  # noqa: BLE001
            pass
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(build(), ensure_ascii=False, indent=1))
