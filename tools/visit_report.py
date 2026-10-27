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
from pathlib import Path
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
    return {k: get(f"{k}-{s}") for k in ("v", "pv", "kakao", "quiz", "share", "news", "chart", "move")}


def market_lines(now: datetime) -> list[str]:
    """사이트 속보 데이터에서: 최근 24시간 많이 나온 종목, 화제 종목, (월요일) 교체 후보."""
    try:
        u = "https://api.github.com/repos/ingforme82-commits/trend-lab/contents/news.json?ref=live"
        req = urllib.request.Request(u, headers={"Accept": "application/vnd.github.raw+json", "User-Agent": "trl"})
        d = json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception:  # noqa: BLE001
        return []
    out = [""]
    tr = d.get("trending") or []
    if tr:
        out.append("■ 최근 24시간 뉴스에 많이 나온 종목")
        out.append("   " + " · ".join(f"{t['name']} {t['n']}" for t in tr[:5]))
    sp = d.get("spot") or []
    if sp:
        out.append("■ 이번 주 화제 종목(사이트 표시 중): " + ", ".join(f"{s['name']}({s.get('since', '')}~)" for s in sp))
    if now.weekday() == 0 and tr:
        on = {s["name"] for s in sp}
        cand = [t["name"] for t in tr if t["name"] not in on][:3]
        if cand:
            out.append(f"   → 월요일: 화제 종목을 바꿀까요? 후보 {', '.join(cand)} (spot.py on/off)")
    mv = d.get("moves") or []
    if mv:
        m = max(mv[:20], key=lambda x: x.get("ratio", 0))
        out.append(f"■ 최근 가장 큰 변곡점: {m['name']} {m['move']:+}{'bp' if m['unit'] == 'bp' else '%'}")
    return out if len(out) > 1 else []


def main() -> None:
    now = datetime.now(KST)
    y, t = day(now - timedelta(days=1)), day(now)
    tot = {k: get(f"{k}-total") for k in ("v", "pv", "kakao", "quiz", "share", "news", "chart", "move")}
    tot["u"] = get("u-total")
    yd = (now - timedelta(days=1))
    line = lambda d: f"방문자 {d['v']}명 · 클릭(페이지뷰) {d['pv']}회\n   오픈채팅 클릭 {d['kakao']} · 성향테스트 {d['quiz']}(공유 {d['share']}) · 속보 클릭 {d['news']} · 차트 열기 {d['chart']} · 변곡점 클릭 {d['move']}"
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
        *market_lines(now),
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
    save_brief()


def save_brief() -> None:
    """사이트 '지난 브리핑'용으로 오늘 12시 브리핑을 data/briefs.json 에 저장하고 올린다."""
    import subprocess
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    try:
        u = "https://api.github.com/repos/ingforme82-commits/trend-lab/contents/news.json?ref=live"
        req = urllib.request.Request(u, headers={"Accept": "application/vnd.github.raw+json", "User-Agent": "trl"})
        d = json.loads(urllib.request.urlopen(req, timeout=20).read())
        from brief import save
        if not d.get("brief") or not save(d["brief"]):
            return
        nw = 0x08000000 if os.name == "nt" else 0
        for cmd in (["git", "add", "data/briefs.json"], ["git", "commit", "-q", "-m", "시장 브리핑 저장"],
                    ["git", "pull", "-q", "--rebase", "--autostash"], ["git", "push", "-q"]):
            subprocess.run(cmd, cwd=root, check=True, creationflags=nw)
        print("브리핑 저장·push 완료")
    except Exception as e:  # noqa: BLE001
        print(f"브리핑 저장 건너뜀: {e}")


if __name__ == "__main__":
    main()
