"""텔레그램 채널별 수집·게시 점검(2026-11-21). 키·본문은 출력하지 않는다.

  python tools/tg_check.py            # 채널마다: 30시간 글 수 · 마지막 글/수집 시각 · 사이트에 실린 수 · 뺀 이유
  python tools/tg_check.py --hours 6

읽는 법
  - 'DB에 없음'     → 수집기(fast_news.py·config.yaml)에 채널이 등록 안 됐거나 가입이 안 된 것
  - 마지막 수집이 오래됨 → 전체 채널 수집(--all)이 안 돌고 있음(tools/.tg_all_at 시각 확인)
  - 읽음은 많은데 실림 0 → 걸러내기(stockrec·broker·links·empty 등)에 걸린 것
  - '조용함'          → 기간 안에 채널이 글을 안 올린 것(수집 문제 아님, 마지막 글 날짜 확인)
  - DB 전체 마지막 수집이 오래됨 → 이 PC는 수집을 안 하고 있음. 사이트 실행이 Oracle이면(market-site/oracle/site_executor.json)
    PC의 DB는 멈춰 있는 게 정상 — 점검은 Oracle 서버에서 `python3 tools/tg_check.py`
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import live_news as ln  # noqa: E402

KST = timezone(timedelta(hours=9))


def fmt(iso: str | None) -> str:
    if not iso:
        return "-"
    return datetime.fromisoformat(iso).astimezone(KST).strftime("%m-%d %H:%M")


WHY = {"stockrec": "목표가·투자의견", "broker": "리포트 머리말", "links": "링크 모음", "empty": "사진·PDF만",
       "link_only": "링크만(제목 못 받음)", "short": "너무 짧음", "junk": "홍보 말투"}


def site_owner() -> str:
    try:
        cfg = ln.TGR.parent / "oracle" / "site_executor.json"
        return json.loads(cfg.read_text(encoding="utf-8-sig")).get("owner", "pc")
    except (OSError, ValueError):
        return "pc"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=30)
    a = ap.parse_args()
    if not ln.DB.exists():
        print(f"텔레 DB 없음: {ln.DB} — 이 PC에는 수집기가 없거나 경로(TRL_TG_DIR)가 다릅니다.")
        return 1
    con = sqlite3.connect(str(ln.DB))
    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=a.hours)).isoformat()
    rows = {r[0]: r[1:] for r in con.execute(
        "select channel_username, max(posted_at), max(collected_at), sum(posted_at >= ?) from messages group by channel_username", (since,))}
    last_any = con.execute("select max(collected_at) from messages").fetchone()[0]
    owner = site_owner()
    print("사이트 실행 담당:", owner)
    if last_any:
        lag_h = (now - datetime.fromisoformat(last_any)).total_seconds() / 3600
        print(f"DB 전체 마지막 수집: {fmt(last_any)} ({lag_h:.1f}시간 전)")
        if lag_h > 0.5:
            print("  ⚠ 30분 넘게 새로 들어온 글이 없음 — " + (
                "사이트를 Oracle이 돌리므로 이 PC DB는 멈춰 있는 게 정상. Oracle 서버에서 다시 실행하세요." if owner == "oracle"
                else "fast_news.py 가 안 돌고 있음(트렌드랩_속보갱신 작업·텔레 세션·live_news.log 확인)."))
    try:
        stamp = float(ln.ALL_STAMP.read_text(encoding="utf-8"))
        print("전체 채널 수집 마지막 성공:", datetime.fromtimestamp(stamp, KST).strftime("%m-%d %H:%M:%S"))
    except (OSError, ValueError):
        print("전체 채널 수집 마지막 성공: 기록 없음(이 PC에서 새 코드가 아직 한 번도 안 돌았음)")
    ln.from_telegram()
    stats = ln.TG_STATS
    print(f"\n{'채널':24} {'최근'+str(a.hours)+'h':>6} {'마지막 글':>11} {'마지막 수집':>11} {'읽음':>4} {'실림':>4}  판정")
    for user, name in ln.CHANNELS.items():
        if user not in rows:
            print(f"{name:24} {'DB에 없음 — config.yaml 미등록 또는 텔레 계정 미가입':>40}")
            continue
        last_post, last_got, n = rows[user]
        s = stats.get(name, {})
        why = ", ".join(f"{WHY.get(k, k)} {v}" for k, v in s.items() if k not in ("read", "kept"))
        if not n and not s.get("read"):
            days = (now - datetime.fromisoformat(last_post)).total_seconds() / 86400 if last_post else 0
            why = f"조용함(마지막 글 {days:.1f}일 전)"
        elif s.get("read") and not s.get("kept"):
            why = "⚠ 전부 걸러짐: " + why
        print(f"{name:24} {n or 0:>6} {fmt(last_post):>11} {fmt(last_got):>11} {s.get('read', 0):>4} {s.get('kept', 0):>4}  {why}")
    extra = sorted(set(rows) - set(ln.CHANNELS))
    if extra:
        print("\n수집은 되지만 사이트 채널 목록(CHANNELS)에 없는 채널:", ", ".join(extra))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
