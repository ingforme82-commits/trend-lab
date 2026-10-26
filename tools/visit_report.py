"""사이트 방문 현황 → 내 카톡(나에게 보내기). 매일 12:00 예약 실행.

  python tools/visit_report.py          # 카톡 전송
  python tools/visit_report.py --dry    # 화면에만 출력

숫자는 count.js가 올린 abacus 카운터(trendlab-ing82)에서 읽는다. 날짜는 한국 시간 기준.
  v  = 방문자(하루에 브라우저 1개당 1명)   pv = 페이지뷰(클릭 수)
  u  = 처음 온 사람 누적(순방문자)          kakao = 오픈채팅 버튼 클릭   quiz = 성향 테스트 완료   news = 속보 클릭(차트에서 확인)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

NS = "trendlab-ing82"
KST = timezone(timedelta(hours=9))
SITE = "https://ingforme82-commits.github.io/trend-lab/"
START = "2026-10-27"          # 집계 시작일


def get(key: str) -> int:
    try:
        with urllib.request.urlopen(f"https://abacus.jasoncameron.dev/get/{NS}/{key}", timeout=15) as r:
            return int(json.loads(r.read())["value"])
    except Exception:  # noqa: BLE001  (키가 아직 없으면 404 = 0)
        return 0


def day(d: datetime) -> dict[str, int]:
    s = d.strftime("%Y%m%d")
    return {k: get(f"{k}-{s}") for k in ("v", "pv", "kakao", "quiz", "share", "news", "chart")}


def main() -> None:
    now = datetime.now(KST)
    y, t = day(now - timedelta(days=1)), day(now)
    tot = {k: get(f"{k}-total") for k in ("v", "pv", "kakao", "quiz", "share", "news", "chart")}
    tot["u"] = get("u-total")
    yd = (now - timedelta(days=1))
    line = lambda d: f"방문자 {d['v']}명 · 클릭(페이지뷰) {d['pv']}회\n   오픈채팅 클릭 {d['kakao']} · 성향테스트 {d['quiz']}(공유 {d['share']}) · 속보 클릭 {d['news']} · 차트 열기 {d['chart']}"
    msg = "\n".join([
        f"📊 Trend Research Lab 방문 현황 ({now:%m/%d %H:%M})",
        "",
        f"■ 어제 {yd.month}/{yd.day}(하루 전체)",
        "   " + line(y),
        f"■ 오늘 0시~지금",
        "   " + line(t),
        f"■ 누적 ({START[5:].replace('-', '/')}부터)",
        f"   순방문자 {tot['u']}명 · 방문 {tot['v']}회 · 클릭 {tot['pv']}회",
        f"   오픈채팅 클릭 {tot['kakao']} · 성향테스트 {tot['quiz']}(공유 {tot['share']})",
        "",
        SITE,
    ])
    if "--dry" in sys.argv:
        print(msg)
        return
    sys.path.insert(0, os.environ.get("TRL_KAKAO_DIR", r"C:\projects\market-site\trader"))   # 카톡 모듈(메인 PC 전용)
    from kakao_notify import notify
    ok = notify(msg)
    print("전송 성공" if ok else "전송 실패")


if __name__ == "__main__":
    main()
