"""거래소 KRX Open API(무료, data-dbg.krx.co.kr) — 공식 일별 종가(장 마감 뒤 정산·교차 확인용).

키: KRX_API_KEY(keystore), 헤더 AUTH_KEY. 서비스별 이용신청·승인이 있어야 한다(없으면 401 "Unauthorized API Call").
- status()          → 서비스별 승인 여부
- index_day(date)   → 코스피 시리즈 일별
- etf_day(date)     → ETF 일별
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

BASE = "https://data-dbg.krx.co.kr/svc/apis/"
SERVICES = {"코스피 지수 일별": "idx/kospi_dd_trd", "코스닥 지수 일별": "idx/kosdaq_dd_trd",
            "유가증권 종목 일별": "sto/stk_bydd_trd", "ETF 일별": "etp/etf_bydd_trd"}


def _get(path: str, date: str) -> list[dict]:
    key = keystore.get("KRX_API_KEY")
    if not key:
        raise RuntimeError("KRX_API_KEY 없음")
    req = urllib.request.Request(f"{BASE}{path}?basDd={date}", headers={"AUTH_KEY": key})
    return json.loads(urllib.request.urlopen(req, timeout=20).read()).get("OutBlock_1", [])


def status(date: str) -> dict:
    out = {}
    for name, path in SERVICES.items():
        try:
            out[name] = f"OK {len(_get(path, date))}건"
        except urllib.error.HTTPError as e:
            out[name] = f"HTTP {e.code}" + (" (이용신청 승인 필요)" if e.code == 401 else "")
        except Exception as e:  # noqa: BLE001
            out[name] = f"오류 {type(e).__name__}"
    return out


def index_day(date: str) -> list[dict]:
    return _get(SERVICES["코스피 지수 일별"], date)


def etf_day(date: str) -> list[dict]:
    return _get(SERVICES["ETF 일별"], date)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(status(sys.argv[1] if len(sys.argv) > 1 else "20261117"))
