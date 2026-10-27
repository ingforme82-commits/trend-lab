"""🏛 공식 발표 데이터(무료·키 없음) — 미 재무부 국채 종가 · EIA 주간 석유 재고 · BLS 물가·고용. news.json official.

- 재무부: home.treasury.gov 일별 수익률 곡선 CSV(공식 종가, 장 마감 후 갱신) — 3개월·2년·10년·30년, 10년−2년, 10년−3개월
- EIA: ir.eia.gov/wpsr/table1.csv (주간 석유 현황 보고서 표1, 백만 배럴) — 상업용 원유·SPR·휘발유·정제유, 전주 대비
- BLS: publicAPI v1(키 없이 하루 25회) — CPI·근원 CPI·PPI(전년 대비), 비농업 고용(전월 대비 증감), 실업률
- 캐시: 재무부·EIA 3시간, BLS 12시간(tools/official_cache.json). 수치·기준일만(해석 없음)
FRED 는 이 PC에서 접속이 끊겨 재무부 원자료로 대신한다. FRED·EIA API 키는 무료지만 운영자가 직접 발급해야 한다.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "official_cache.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TTL = {"ust": 3 * 3600, "eia": 3 * 3600, "bls": 12 * 3600}
BLS = {"CUUR0000SA0": "CPI", "CUUR0000SA0L1E": "근원 CPI", "WPUFD4": "PPI(최종 수요)", "CES0000000001": "비농업 고용", "LNS14000000": "실업률"}
EIA_ROWS = {"Commercial (Excluding SPR)": "상업용 원유", "Strategic Petroleum Reserve (SPR)": "전략비축유(SPR)",
            "Total Motor Gasoline": "휘발유", "Distillate Fuel Oil": "정제유(디젤 등)"}


def _get(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 20) -> str:
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


# ── 순수 파싱(tests/test_official.py) ──
def parse_treasury(text: str) -> dict | None:
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) < 2:
        return None
    a, b = rows[0], rows[1]                                   # 최신이 맨 위
    f = lambda r, k: float(r[k]) if r.get(k) not in (None, "", "N/A") else None
    cur = {k: f(a, c) for k, c in (("3M", "3 Mo"), ("2Y", "2 Yr"), ("10Y", "10 Yr"), ("30Y", "30 Yr"))}
    prev = {k: f(b, c) for k, c in (("3M", "3 Mo"), ("2Y", "2 Yr"), ("10Y", "10 Yr"), ("30Y", "30 Yr"))}
    out = {"date": datetime.strptime(a["Date"], "%m/%d/%Y").strftime("%Y-%m-%d"),
           "rates": {k: {"v": v, "bp": round((v - prev[k]) * 100) if v is not None and prev[k] is not None else None} for k, v in cur.items()}}
    if cur["10Y"] is not None and cur["2Y"] is not None:
        out["s10_2"] = round((cur["10Y"] - cur["2Y"]) * 100)
    if cur["10Y"] is not None and cur["3M"] is not None:
        out["s10_3m"] = round((cur["10Y"] - cur["3M"]) * 100)
    return out


def parse_eia(text: str) -> dict | None:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 4:
        return None
    week = datetime.strptime(rows[0][1], "%m/%d/%y").strftime("%Y-%m-%d")
    items = []
    for r in rows[1:]:
        if r and r[0] in EIA_ROWS:
            items.append({"name": EIA_ROWS[r[0]], "v": float(r[1]), "chg": float(r[3]), "yoy": float(r[7]) if len(r) > 7 and r[7] else None})
    return {"week": week, "items": items} if items else None


def parse_bls(js: dict) -> list[dict]:
    out = []
    for s in (js.get("Results") or {}).get("series", []):
        sid, d = s["seriesID"], [x for x in s.get("data", []) if x.get("period", "").startswith("M") and x["period"] != "M13"]
        if not d:
            continue
        cur = d[0]
        name = BLS.get(sid, sid)
        row = {"name": name, "period": f"{cur['year']}-{cur['period'][1:]}"}
        val = float(cur["value"])
        if sid in ("CES0000000001",):                            # 고용: 전월 대비 증감(천 명)
            row["v"] = round(val - float(d[1]["value"])) if len(d) > 1 else None
            row["unit"] = "천 명(전월 대비)"
        elif sid == "LNS14000000":
            row["v"], row["unit"] = val, "%"
        else:                                                     # 물가: 전년 같은 달 대비 %
            ya = next((x for x in d if x["year"] == str(int(cur["year"]) - 1) and x["period"] == cur["period"]), None)
            row["v"] = round((val / float(ya["value"]) - 1) * 100, 1) if ya else None
            row["unit"] = "% (전년 대비)"
        out.append(row)
    return out


# ── 수집(캐시) ──
def _load() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def build() -> dict:
    c, now = _load(), time.time()
    yr = datetime.now().year

    def fresh(k):
        return c.get(k) and now - c[k].get("t", 0) < TTL[k]
    if not fresh("ust"):
        try:
            u = (f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{yr}/all"
                 f"?type=daily_treasury_yield_curve&field_tdr_date_value={yr}&page&_format=csv")
            v = parse_treasury(_get(u))
            if v:
                c["ust"] = {"t": now, "v": v}
        except Exception:  # noqa: BLE001
            pass
    if not fresh("eia"):
        try:
            v = parse_eia(_get("https://ir.eia.gov/wpsr/table1.csv"))
            if v:
                c["eia"] = {"t": now, "v": v}
        except Exception:  # noqa: BLE001
            pass
    if not fresh("bls"):
        try:
            body = json.dumps({"seriesid": list(BLS)}).encode()
            v = parse_bls(json.loads(_get("https://api.bls.gov/publicAPI/v1/timeseries/data/", body, {"Content-Type": "application/json"}, 30)))
            if v:
                c["bls"] = {"t": now, "v": v}
        except Exception:  # noqa: BLE001
            pass
    try:
        CACHE.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return {k: c[k]["v"] for k in ("ust", "eia", "bls") if c.get(k)}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    CACHE.unlink(missing_ok=True)
    print(json.dumps(build(), ensure_ascii=False, indent=1))
