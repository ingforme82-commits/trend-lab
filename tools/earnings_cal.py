"""📅 미국 빅테크·주요 섹터 실적 일정 — Finnhub 일정 ↔ 야후 일정 교차 확인 → data/earnings.json(사이트 '실적 일정' 칸).

운영자 11/18: "엔비디아 등 미국 빅테크 주요 종목 섹터 실적 발표 알려주고 TRL 업데이트" · "출처들 항상 크로스체크".
- 날짜: 두 출처가 같으면 '확정', 야후가 회사 확정(isEarningsDateEstimate=False)인데 Finnhub 와 다르면 야후 날짜 + '출처 다름',
  야후가 추정이면 '추정'. 시각: 장전(bmo) = 미 동부 오전 → 한국 같은 날 밤, 장마감 뒤(amc) → 한국 다음 날 아침
- 예상치: Finnhub 컨센서스(EPS·매출). 발표 뒤 실제치·차이(%)도 넣는다. 출처마다 예상치가 다를 수 있다고 표기
- 수치·일정만(해석 없음). 실행: python tools/earnings_cal.py [--days 35]
"""

from __future__ import annotations

import http.cookiejar
import json
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE.parent / "data" / "earnings.json"

# 종목: (이름, 섹터)
WATCH = {
    "NVDA": ("엔비디아", "반도체"), "AVGO": ("브로드컴", "반도체"), "MU": ("마이크론", "반도체"), "MRVL": ("마벨", "반도체"),
    "ADI": ("아나로그디바이스", "반도체"), "AMD": ("AMD", "반도체"), "INTC": ("인텔", "반도체"), "QCOM": ("퀄컴", "반도체"),
    "TSM": ("TSMC", "반도체"), "ASML": ("ASML", "반도체 장비"), "AMAT": ("어플라이드머티리얼즈", "반도체 장비"),
    "LRCX": ("램리서치", "반도체 장비"), "KLAC": ("KLA", "반도체 장비"), "KEYS": ("키사이트", "반도체 장비"),
    "SNPS": ("시놉시스", "반도체 설계 SW"), "CDNS": ("케이던스", "반도체 설계 SW"), "CIEN": ("시에나", "광통신"),
    "COHR": ("코히런트", "광통신"), "LITE": ("루멘텀", "광통신"),
    "AAPL": ("애플", "빅테크"), "MSFT": ("마이크로소프트", "빅테크"), "GOOGL": ("알파벳", "빅테크"), "AMZN": ("아마존", "빅테크"),
    "META": ("메타", "빅테크"), "TSLA": ("테슬라", "빅테크"),
    "ORCL": ("오라클", "AI 인프라·클라우드"), "DELL": ("델", "AI 서버"), "HPE": ("HPE", "AI 서버"), "SMCI": ("슈퍼마이크로", "AI 서버"),
    "HPQ": ("HP", "PC"), "NTAP": ("넷앱", "스토리지"), "WDC": ("웨스턴디지털", "스토리지"), "STX": ("씨게이트", "스토리지"),
    "CRM": ("세일즈포스", "소프트웨어"), "ADBE": ("어도비", "소프트웨어"), "INTU": ("인튜이트", "소프트웨어"), "WDAY": ("워크데이", "소프트웨어"),
    "SNOW": ("스노우플레이크", "소프트웨어"), "MDB": ("몽고DB", "소프트웨어"), "ADSK": ("오토데스크", "소프트웨어"), "NOW": ("서비스나우", "소프트웨어"),
    "PLTR": ("팔란티어", "소프트웨어"), "PANW": ("팔로알토", "보안"), "CRWD": ("크라우드스트라이크", "보안"), "ZS": ("지스케일러", "보안"),
    "OKTA": ("옥타", "보안"), "ACN": ("액센츄어", "IT 서비스"),
    "WMT": ("월마트", "소비"), "COST": ("코스트코", "소비"), "TGT": ("타깃", "소비"), "HD": ("홈디포", "소비"), "LOW": ("로우스", "소비"),
    "TJX": ("TJX", "소비"), "NKE": ("나이키", "소비"), "LULU": ("룰루레몬", "소비"), "BBY": ("베스트바이", "소비"),
    "DE": ("디어", "산업재"), "CAT": ("캐터필러", "산업재"), "FDX": ("페덱스", "운송"),
    "BABA": ("알리바바", "중국"), "PDD": ("PDD", "중국"), "JD": ("징둥", "중국"),
}
HOUR = {"bmo": "장전", "amc": "장마감 뒤", "dmh": "장중"}


def kst_when(d: str, hour: str) -> str:
    """미 동부 날짜·시간대 → 한국 시각 표기(겨울 기준 14시간 차)."""
    x = date.fromisoformat(d)
    if hour == "amc":
        n = x + timedelta(days=1)
        return f"{n.month}/{n.day} 06시 이후"
    if hour == "bmo":
        return f"{x.month}/{x.day} 밤 21~22시"
    return "시각 미정"


def merge(fh: dict, yh: dict | None, today: str | None = None) -> dict:
    """Finnhub 일정 1줄 + 야후 일정 → 날짜 확인 상태. 야후 날짜가 이미 지났고 Finnhub 날짜가 그 뒤면 야후 미갱신(지난 분기)."""
    d = fh["date"]
    today = today or date.today().isoformat()
    if yh and yh.get("dates") and max(yh["dates"]) < min(d, today):
        return {"date": d, "check": "1곳(Finnhub) · 야후는 지난 분기 날짜"}
    if not yh or not yh.get("dates"):
        return {"date": d, "check": "1곳(Finnhub)"}
    if d in yh["dates"]:
        return {"date": d, "check": "확정" if not yh["est"] else "두 곳 일치(회사 미확정)"}
    if not yh["est"]:
        return {"date": yh["dates"][0], "check": f"출처 다름 — 회사 확정 {yh['dates'][0]} · Finnhub {d}"}
    return {"date": d, "check": f"추정 — Finnhub {d} · 야후 {yh['dates'][0]}"}


def surprise(act, est):
    return round((act / est - 1) * 100, 1) if act is not None and est not in (None, 0) else None


def _yahoo():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0")]
    try:
        op.open("https://fc.yahoo.com", timeout=10)
    except Exception:  # noqa: BLE001
        pass
    crumb = op.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10).read().decode()

    def get(sym: str) -> dict | None:
        try:
            d = json.loads(op.open(f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules=calendarEvents&crumb={crumb}",
                                   timeout=10).read())
            e = d["quoteSummary"]["result"][0]["calendarEvents"]["earnings"]
            return {"dates": [x["fmt"] for x in e.get("earningsDate", [])], "est": bool(e.get("isEarningsDateEstimate"))}
        except Exception:  # noqa: BLE001
            return None
    return get


def build(days: int = 35, back: int = 2) -> dict:
    import finnhub
    today = date.today()
    d1, d2 = (today - timedelta(days=back)).isoformat(), (today + timedelta(days=days)).isoformat()
    rows = [r for r in finnhub._get("calendar/earnings", **{"from": d1, "to": d2}).get("earningsCalendar", []) if r["symbol"] in WATCH]
    try:
        yget = _yahoo()
    except Exception:  # noqa: BLE001
        yget = lambda s: None  # noqa: E731
    items = []
    for r in rows:
        yh = yget(r["symbol"])
        time.sleep(0.15)
        m = merge(r, yh)
        name, sector = WATCH[r["symbol"]]
        hour = r.get("hour") or ""
        items.append({
            "sym": r["symbol"], "name": name, "sector": sector, "date": m["date"], "hour": HOUR.get(hour, "시각 미정"),
            "kst": kst_when(m["date"], hour), "kst_date": (date.fromisoformat(m["date"]) + timedelta(days=1 if hour == "amc" else 0)).isoformat(),
            "check": m["check"],
            "eps_est": r.get("epsEstimate"), "rev_est": r.get("revenueEstimate"),
            "eps_act": r.get("epsActual"), "rev_act": r.get("revenueActual"),
            "eps_sur": surprise(r.get("epsActual"), r.get("epsEstimate")), "rev_sur": surprise(r.get("revenueActual"), r.get("revenueEstimate")),
        })
    rank = {"장전": 0, "장중": 1, "장마감 뒤": 2}
    items.sort(key=lambda x: (x["date"], rank.get(x["hour"], 3), x["sym"]))
    return {"updated": datetime.now().strftime("%Y-%m-%d %H:%M"), "range": [d1, d2],
            "note": "일정: Finnhub·야후 교차 확인 · 예상치: Finnhub 컨센서스(출처마다 다를 수 있음) · 한국 시각은 미국 겨울 시간 기준",
            "items": items}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    n = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 35
    out = build(n)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in out["items"]:
        print(x["date"], x["hour"], x["sym"], x["name"], x["sector"], x["check"])
