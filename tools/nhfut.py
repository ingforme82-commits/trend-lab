"""NH PLUG 선물 시세 — 조회 전용(코스피200 선물 주간·야간, CME E-mini S&P500·나스닥100). 2026-11-15 운영자 요청.

- 하이퍼리퀴드 24시간 지수(대체 지표)는 주말에도 거래돼 '거래소 야간장 이후' 움직임까지 섞인다
  (11/15: 대체 지수 종가 이후 -2.8% vs 실제 코스피200 야간선물 -0.72%). 실제 선물을 함께 보여 준다.
- 키·토큰: market-site 매매 도구와 같은 ~/.nhplug 설정·토큰 저장소(nhplug 패키지). 토큰 재발급은 보안 알림이 가므로 공유 캐시 재사용.
- 시세 경로만 허용(주문·계좌 경로는 막음). 실패하면 빈 값 → 부르는 쪽은 건너뛴다. 결과 50초 캐시(저장소 밖).

  python tools/nhfut.py     # 연결 점검
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
VENV = Path(r"C:\projects\market-site\trader\.venv\Lib\site-packages")
LIVE = "https://api.nhplug.com:8443"
CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "trendlab" / "nhfut.json"
ALLOW = ("/krfuture/quote/", "/gbfuture/quote/", "/krstock/quote/")   # 시세 조회 경로만(주식 현재가는 증권사 교차 확인용)
MON = "123456789ABC"                                       # KRX 월 코드(10·11·12월 = A·B·C)
CME_MON = {3: "H", 6: "M", 9: "U", 12: "Z"}


def _nth_weekday(y: int, m: int, wd: int, n: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def k200_code(today: date | None = None) -> str:
    """코스피200 선물 최근월물 코드(예: 26년 12월물 KA016C000). 분기월 둘째 목요일 만기 다음 날부터 다음 월물."""
    t = today or datetime.now(KST).date()
    y, m = t.year, t.month
    while True:
        qm = ((m - 1) // 3 + 1) * 3
        if t <= _nth_weekday(y, qm, 3, 2):
            return f"KA01{y % 10}{MON[qm - 1]}000"
        m = qm + 1
        if m > 12:
            y, m = y + 1, 1
        t = date(y, m, 1)


def cme_code(root: str, today: date | None = None) -> str:
    """CME E-mini 최근월(예: ESZ26). 만기(셋째 금요일) 8일 전부터 다음 분기물(거래량 이동)."""
    t = today or datetime.now(KST).date()
    y, m = t.year, t.month
    while True:
        qm = ((m - 1) // 3 + 1) * 3
        if t < _nth_weekday(y, qm, 4, 3) - timedelta(days=8):
            return f"{root}{CME_MON[qm]}{y % 100:02d}"
        m = qm + 1
        if m > 12:
            y, m = y + 1, 1
        t = date(y, m, 1)


def _call(path: str, inp: dict) -> dict:
    if not path.startswith(ALLOW):
        raise PermissionError("NH 선물 모듈은 시세 조회만 한다")
    if str(VENV) not in sys.path:
        sys.path.append(str(VENV))
    from nhplug import call
    saved = os.environ.get("NHPLUG_BASE_URL")
    os.environ["NHPLUG_BASE_URL"] = LIVE                  # 시세는 운영 서버(설정은 모의투자 주소여도)
    try:
        return call(path, inp)
    finally:
        if saved is None:
            os.environ.pop("NHPLUG_BASE_URL", None)
        else:
            os.environ["NHPLUG_BASE_URL"] = saved


def _first(d: dict, key: str) -> dict:
    o = d.get(key) or {}
    return (o[0] if o else {}) if isinstance(o, list) else o


def _f(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def k200_session(now: datetime | None = None) -> str:
    """지금 보여 줄 세션: 평일 08:45~15:45 주간, 그 밖은 마지막 야간(야간장 18:00~다음 날 06:00)."""
    k = (now or datetime.now(KST)).astimezone(KST)
    m = k.hour * 60 + k.minute
    return "day" if k.weekday() < 5 and 8 * 60 + 45 <= m < 15 * 60 + 45 else "night"


def quotes() -> dict:
    """{'K200F': {...}, 'ES': {...}, 'NQ': {...}} — name·px·chg(%)·sess·code·at. 실패한 항목은 빠진다."""
    try:
        c = json.loads(CACHE.read_text(encoding="utf-8"))
        if time.time() - c["at"] < 50:
            return c["data"]
    except Exception:  # noqa: BLE001
        pass
    out: dict = {}
    now_ms = int(time.time() * 1000)
    try:
        # 현재가 API(day·night)는 부호가 비고 등락률이 절댓값이라, 기간별 시세(일봉)의 부호 있는 전일 대비를 쓴다(11/15 확인).
        # 주간: 그대로(전일 주간 종가 대비) · 야간: 마지막 주간 종가 대비로 계산
        code, sess = k200_code(), k200_session()
        dp = _call("/krfuture/quote/v1/dayPeriod", {"iem_cd": code, "mrkt_div_cls_code": "F", "edate": datetime.now(KST).strftime("%Y%m%d"),
                                                     "array_cnt": "2", "maxavg": "", "gubun": "1", "xtick": "001", "today_cls_code": "0",
                                                     "out1_scale_change": "0", "out2_scale_change": "0"})
        o = _first(dp, "Output_0")
        dpx, dvs = _f(o.get("prpr")), _f(o.get("prdy_vrss"))
        if dp.get("rsp_cd") == "00000" and dpx:
            item = {"name": "코스피200 주간선물", "px": dpx, "chg": round(dvs / (dpx - dvs) * 100, 2) if dvs is not None and dpx != dvs else None,
                    "sess": "day", "base": "전일 종가", "code": code, "at": now_ms, "src": "NH"}
            if sess == "night":
                n = _first(_call("/krfuture/quote/v1/night", {"iem_cd": code}), "Output_0")
                npx = _f(n.get("prpr"))
                if npx:
                    item.update(name="코스피200 야간선물", px=npx, chg=round((npx / dpx - 1) * 100, 2), sess="night", base="주간 종가",
                                day_px=dpx)
            out["K200F"] = item
    except Exception:  # noqa: BLE001
        pass
    for key, root, name in (("ES", "ES", "S&P500 선물(CME)"), ("NQ", "NQ", "나스닥100 선물(CME)")):
        try:
            code = cme_code(root)
            d = _call("/gbfuture/quote/v1/current", {"exnm": "FCME", "iem_cd": code})
            o = _first(d, "Output_0")
            px, rt = _f(o.get("last")), _f(o.get("rate"))
            if d.get("rsp_cd") == "00000" and px:
                out[key] = {"name": name, "px": px, "chg": rt, "code": code, "at": now_ms, "src": "NH"}
        except Exception:  # noqa: BLE001
            continue
    if out:
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps({"at": time.time(), "data": out}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return out


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    CACHE.unlink(missing_ok=True)
    q = quotes()
    if not q:
        print("NH 선물 조회 실패(키·토큰·접속 확인: ~/.nhplug/.env)")
    for v in q.values():
        print(f"{v['name']} [{v['code']}] {v['px']:,.2f} ({v['chg']:+.2f}%)")


if __name__ == "__main__":
    main()
