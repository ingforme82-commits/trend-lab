"""TRL 시세 교차 확인 — 게시된 news.json 값을 Finnhub · Alpaca(IEX) · 한국은행 ECOS와 대조.

운영자 11/18: "출처들 항상 크로스체크". (속보 문장 대조는 xcheck.py, 이 파일은 숫자 대조)
- 0.5% 넘게 어긋나고 조회 시각 차이가 5분 안이면 '불일치', 시각 차이가 크면 '시차'(다른 시점끼리 비교하지 않음)
- 한국 지수: TRL 전일 종가 ↔ ECOS 공식 종가(ECOS 는 하루 늦게 들어옴)
결과: tools/quote_xcheck.log(한 줄 JSON) · --alert 이면 불일치를 tg_alert 개인 알림(같은 종목 하루 1번)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import keystore  # noqa: E402

NEWS = "https://raw.githubusercontent.com/ingforme82-commits/trend-lab/live/news.json"
LOG = HERE / "quote_xcheck.log"
TOL_PCT, TOL_MS = 0.5, 5 * 60_000
US = ("SOXL", "KORU", "SKHY", "MU", "DRAM")
LEV = {"SOXL", "KORU"}                     # 3배 ETF 는 1분에도 1% 움직임 → 허용폭 1.5%


def judge(a: float, b: float, at_a: int, at_b: int, tol: float = TOL_PCT) -> str:
    if not a or not b:
        return "없음"
    if abs(at_a - at_b) > TOL_MS:
        return "시차"
    return "일치" if abs(a / b - 1) * 100 <= tol else "불일치"


def _iso_ms(s: str) -> int:
    s = s.replace("Z", "")
    if "." in s:
        a, b = s.split(".", 1)
        s = f"{a}.{b[:6]}"
    return int(datetime.fromisoformat(s + "+00:00").timestamp() * 1000)


def alpaca_trades(syms) -> dict:
    p = keystore.pair("ALPACA_API_KEY", "ALPACA_SECRET_KEY") or keystore.pair("APCA_API_KEY_ID", "APCA_API_SECRET_KEY")
    if not p or not syms:
        return {}
    req = urllib.request.Request(f"https://data.alpaca.markets/v2/stocks/trades/latest?symbols={','.join(syms)}&feed=iex",
                                 headers={"APCA-API-KEY-ID": p[0], "APCA-API-SECRET-KEY": p[1]})
    d = json.loads(urllib.request.urlopen(req, timeout=15).read()).get("trades", {})
    return {s: {"px": t["p"], "at": _iso_ms(t["t"])} for s, t in d.items()}


def kr_rows(kr: dict, ser: dict) -> list[dict]:
    """TRL 종가(px)가 ECOS 어느 날 종가와 같으면 그날·전날을 대조, 아직 ECOS 에 없으면 전일 종가(prev)만 마지막 ECOS 값과 대조."""
    out = []
    for k, n in (("KOSPI", "kospi"), ("KOSDAQ", "kosdaq")):
        t, rows = kr.get(k), ser.get(n) or []
        if not t or not rows:
            continue
        hit = [i for i, (_, v) in enumerate(rows) if abs(v - t["px"]) < 0.02]
        if hit:
            i = hit[-1]
            out.append({"item": f"{k} 종가({rows[i][0]})", "trl": t["px"], "src": "ECOS", "v": rows[i][1], "res": "일치"})
            if i > 0:
                out.append({"item": f"{k} 전일 종가({rows[i-1][0]})", "trl": round(t["prev"], 2), "src": "ECOS", "v": rows[i - 1][1],
                            "res": "일치" if abs(t["prev"] - rows[i - 1][1]) < 0.02 else "불일치"})
        else:
            d, v = rows[-1]
            out.append({"item": f"{k} 전일 종가({d})", "trl": round(t["prev"], 2), "src": "ECOS", "v": v,
                        "res": "일치" if abs(t["prev"] - v) < 0.02 else "불일치"})
    return out


def run(alert: bool = False) -> list[dict]:
    import finnhub
    trl = json.loads(urllib.request.urlopen(f"{NEWS}?t={int(time.time())}", timeout=20).read())
    rows: list[dict] = []
    lev = {i["sym"]: i for i in (trl.get("lev") or {}).get("items", [])}
    live = [s for s in US if s in lev and lev[s].get("open")]
    try:
        al = alpaca_trades(live)
    except Exception:  # noqa: BLE001
        al = {}
    for s in live:
        t = lev[s]
        at = t.get("at") or trl["updated"]
        tol = 1.5 if s in LEV else TOL_PCT
        try:
            f = finnhub.quote(s)
        except Exception:  # noqa: BLE001
            f = None
        if f:
            rows.append({"item": s, "trl": t["px"], "src": "Finnhub", "v": f["px"], "dt_s": round(abs(at - f["at"]) / 1000),
                         "res": judge(t["px"], f["px"], at, f["at"], tol)})
        if s in al:
            rows.append({"item": s, "trl": t["px"], "src": "Alpaca IEX", "v": al[s]["px"], "dt_s": round(abs(at - al[s]["at"]) / 1000),
                         "res": judge(t["px"], al[s]["px"], at, al[s]["at"], tol)})
        time.sleep(0.2)
    try:
        import ecos
        rows += kr_rows(trl.get("kr") or {}, {n: ecos.series(n) for n in ("kospi", "kosdaq")})
    except Exception:  # noqa: BLE001
        pass
    rec = {"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "trl_updated": trl.get("updated"), "rows": rows}
    with LOG.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    bad = [r for r in rows if r["res"] == "불일치"]
    if alert and bad:
        try:
            import tg_alert
            for r in bad:
                tg_alert.alert("quote_xcheck", f"{datetime.now():%Y%m%d}-{r['item']}-{r['src']}",
                               f"TRL 시세 불일치 {r['item']}: TRL {r['trl']} / {r['src']} {r['v']}")
        except Exception:  # noqa: BLE001
            pass
    return rows


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for r in run("--alert" in sys.argv):
        print(f"{r['item']:<14} TRL {r['trl']:<10} {r['src']:<10} {r['v']:<10} {r['res']}  시각차 {r.get('dt_s', '-')}초")
