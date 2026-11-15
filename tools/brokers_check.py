"""4개 증권사(키움·한투·NH·KB) 연결 점검 — PC·Oracle 공통, 조회만. 키 값은 출력하지 않는다.

  python3 tools/brokers_check.py           # 표로 출력
  python3 tools/brokers_check.py --json    # API 등록부(registry) 형식 JSON(비밀값 없음)

각 증권사: 키 있음/없음 → 토큰 → 대표 조회 1건(지수·주가·뉴스·선물) → 걸린 시간·실패 이유.
결과는 상태 폴더 brokers_status.json 에도 남긴다(공개 저장소 아님). 실패해도 다른 증권사 점검은 계속한다.
Oracle 주의: 키움은 등록한 IP에서만 열린다 → 서버 공인 IP를 openapi.kiwoom.com 에 등록해야 한다.
"""

from __future__ import annotations

import json
import platform
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402


def _t(fn):
    t = time.time()
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__}: {str(e)[:120]}"
    return ok, detail, round(time.time() - t, 2)


def kiwoom_check():
    import kiwoom
    kiwoom.DOWN.unlink(missing_ok=True)
    x = kiwoom.index_now("001")
    if not x:
        why = kiwoom._down() or "응답 없음"
        hint = " — 이 서버 공인 IP를 openapi.kiwoom.com 에 등록했는지 확인" if "토큰" in why or "IP" in why or "8050" in why else ""
        return False, why + hint
    return True, f"코스피 {x['px']:,.2f} ({x['chg']:+.2f}%) · 상승 {x['up']}/하락 {x['down']}"


def kis_check():
    import kis
    kis.DOWN.unlink(missing_ok=True)
    x = kis.index_now("0001")
    n = kis.news_titles()
    if not x and not n:
        return False, kis._down() or "응답 없음"
    return bool(x and n), (f"코스피 {x['px']:,.2f}" if x else "지수 실패") + f" · 뉴스 제목 {len(n)}건"


def nh_check():
    import nhfut
    nhfut.CACHE.unlink(missing_ok=True)
    q = nhfut.quotes()
    if not q:
        return False, "선물 조회 실패(NHPLUG_APP_KEY·nhplug 패키지·운영 토큰 확인)"
    return True, " · ".join(f"{v['name']} {v['px']:,.2f}({v['chg']:+.2f}%)" for v in q.values())


def kb_check():
    import kbprog
    try:
        (kbprog.TOKDIR / "kb_down.txt").unlink(missing_ok=True)
    except OSError:
        pass
    try:                                                   # 11/15 Codex: Oracle에서 KB 포트 연결 시간 초과 — TCP부터 따로 확인
        socket.create_connection(("developer.kbsec.com", 32484), timeout=6).close()
    except OSError as e:
        return False, f"KB 서버 TCP 연결 실패(developer.kbsec.com:32484, {type(e).__name__}) — 서버 방화벽/KB 측 IP 제한 확인"
    q = kbprog.fetch_quotes(["005930"])
    return (True, f"삼성전자 {q['005930']:,.0f}원(통합)") if q.get("005930") else (False, "토큰·시세 응답 없음")


CHECKS = {
    "키움": ("KIWOOM_APP_KEY", "KIWOOM_SECRET_KEY", kiwoom_check, "국내 지수·주가·1분봉(조회 전용, 등록 IP 필요)"),
    "한투": ("KIS_APP_KEY", "KIS_APP_SECRET", kis_check, "뉴스 제목·업종지수(조회 전용)"),
    "NH": ("NHPLUG_APP_KEY", "NHPLUG_APP_SECRET", nh_check, "코스피200 주간·야간선물·CME 지수선물·주가(조회 전용, ~/.nhplug)"),
    "KB": ("KB_APP_KEY", "KB_APP_SECRET", kb_check, "주가(통합)·종목별 프로그램매매(조회 전용)"),
}


def run() -> dict:
    out = {"host": socket.gethostname(), "os": platform.system(), "at": int(time.time() * 1000),
           "keys_file": str(keystore.keys_file()), "keys_file_exists": keystore.keys_file().exists(), "providers": {}}
    for name, (a, b, fn, scope) in CHECKS.items():
        key = keystore.has(a) and keystore.has(b)
        ok, detail, sec = _t(fn) if key else (False, "키 없음", 0.0)
        out["providers"][name] = {"key": key, "ok": ok, "detail": detail, "sec": sec, "scope": scope, "mode": "read-only"}
    try:
        keystore.write_private(keystore.state_dir() / "brokers_status.json", json.dumps(out, ensure_ascii=False))
    except OSError:
        pass
    return out


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    r = run()
    if "--json" in sys.argv:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    print(f"{r['host']} ({r['os']}) · 키 파일 {r['keys_file']} {'있음' if r['keys_file_exists'] else '없음'}")
    for n, v in r["providers"].items():
        print(f"  {'✅' if v['ok'] else '❌'} {n:<3} 키 {'있음' if v['key'] else '없음'} · {v['sec']}s · {v['detail']}")
    sys.exit(0 if all(v["ok"] for v in r["providers"].values()) else 2)


if __name__ == "__main__":
    main()
