"""한국 증시 실시간 시세(네이버 금융 polling, 지연 없음). 야후는 한국 종목이 약 20분 늦다.

주의: 네이버 등락률(fluctuationsRatio)·전일 대비(compareToPreviousClosePrice)는 부호가 없다.
상승·하락은 compareToPreviousPrice.code 로만 판단한다(1 상한, 2 상승, 3 보합, 4 하한, 5 하락).
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime

BASE = "https://polling.finance.naver.com/api/realtime/domestic"
INDEX = {"^KS11": "KOSPI", "^KQ11": "KOSDAQ", "^KS200": "KPI200"}
DOWN = {"4", "5"}
UP = {"1", "2"}


def _num(v) -> float:
    return float(str(v).replace(",", "")) if v not in (None, "", "-") else 0.0


def _parse(d: dict) -> dict | None:
    px = _num(d.get("closePriceRaw") or d.get("closePrice"))
    diff = abs(_num(d.get("compareToPreviousClosePriceRaw") or d.get("compareToPreviousClosePrice")))
    code = str((d.get("compareToPreviousPrice") or {}).get("code", "3"))
    sign = -1 if code in DOWN else 1 if code in UP else 0
    if not px:
        return None
    prev = px - sign * diff
    t = d.get("localTradedAt") or ""
    try:
        at = int(datetime.fromisoformat(t).timestamp() * 1000)
    except ValueError:
        at = 0
    return {"px": px, "prev": prev, "chg": round((px / prev - 1) * 100, 2) if prev else 0.0, "at": at,
            "day": t[:10], "status": d.get("marketStatus", ""), "cur": "KRW"}


def quotes(syms: list[str]) -> dict[str, dict]:
    """야후 심볼(005930.KS, 035720.KQ, ^KS11 …) → 실시간 시세. 실패한 심볼은 빠진다."""
    stocks = {s.split(".")[0]: s for s in syms if s.endswith((".KS", ".KQ"))}
    idx = {INDEX[s]: s for s in syms if s in INDEX}
    out: dict[str, dict] = {}
    for kind, m in (("stock", stocks), ("index", idx)):
        codes = list(m)
        for i in range(0, len(codes), 20):
            u = f"{BASE}/{kind}/{','.join(codes[i:i + 20])}"
            try:
                r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=8).read())
            except Exception:  # noqa: BLE001
                continue
            for d in r.get("datas", []):
                q = _parse(d)
                if q and d.get("itemCode") in m:
                    out[m[d["itemCode"]]] = q
    return out


def merge(yq: dict[str, dict | None]) -> dict[str, dict | None]:
    """야후 시세(심볼→dict)의 한국 종목·지수를 네이버 실시간 가격·전일 종가로 바꾼다(고점 기록은 야후 것 유지)."""
    kr = quotes([s for s in yq if s.endswith((".KS", ".KQ")) or s in INDEX])
    for sym, q in kr.items():
        base = dict(yq.get(sym) or {})
        base.update(px=q["px"], prev=q["prev"], at=q["at"], day=q["day"], cur="KRW", stale=False, live=q["status"] == "OPEN")
        yq[sym] = base
    return yq


if __name__ == "__main__":
    for k, v in quotes(["^KS11", "^KQ11", "^KS200", "005930.KS", "000660.KS"]).items():
        print(k, v)
