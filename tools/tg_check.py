"""텔레그램 채널별 수집·게시 점검(2026-11-21). 키·본문은 출력하지 않는다.

  python tools/tg_check.py            # 채널마다: 30시간 글 수 · 마지막 글/수집 시각 · 사이트에 실린 수 · 뺀 이유
  python tools/tg_check.py --hours 6

읽는 법
  - 'DB에 없음'     → 수집기(fast_news.py·config.yaml)에 채널이 등록 안 됐거나 가입이 안 된 것
  - 마지막 수집이 오래됨 → 전체 채널 수집(--all)이 안 돌고 있음(tools/.tg_all_at 시각 확인)
  - 읽음은 많은데 실림 0 → 걸러내기(stockrec·broker·links·empty 등)에 걸린 것
"""
from __future__ import annotations

import argparse
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=30)
    a = ap.parse_args()
    if not ln.DB.exists():
        print(f"텔레 DB 없음: {ln.DB} — 이 PC에는 수집기가 없거나 경로(TRL_TG_DIR)가 다릅니다.")
        return 1
    con = sqlite3.connect(str(ln.DB))
    since = (datetime.now(timezone.utc) - timedelta(hours=a.hours)).isoformat()
    rows = {r[0]: r[1:] for r in con.execute(
        "select channel_username, max(posted_at), max(collected_at), sum(posted_at >= ?) from messages group by channel_username", (since,))}
    try:
        stamp = float(ln.ALL_STAMP.read_text(encoding="utf-8"))
        print("전체 채널 수집 마지막 성공:", datetime.fromtimestamp(stamp, KST).strftime("%m-%d %H:%M:%S"))
    except (OSError, ValueError):
        print("전체 채널 수집 마지막 성공: 기록 없음(새 코드가 아직 한 번도 성공 못 함)")
    ln.from_telegram()
    stats = ln.TG_STATS
    print(f"\n{'채널':24} {'최근'+str(a.hours)+'h':>6} {'마지막 글':>11} {'마지막 수집':>11} {'읽음':>4} {'실림':>4}  뺀 이유")
    for user, name in ln.CHANNELS.items():
        if user not in rows:
            print(f"{name:24} {'DB에 없음 — 수집기에 채널 미등록/미가입':>40}")
            continue
        last_post, last_got, n = rows[user]
        s = stats.get(name, {})
        why = ", ".join(f"{k} {v}" for k, v in s.items() if k not in ("read", "kept"))
        print(f"{name:24} {n or 0:>6} {fmt(last_post):>11} {fmt(last_got):>11} {s.get('read', 0):>4} {s.get('kept', 0):>4}  {why}")
    extra = sorted(set(rows) - set(ln.CHANNELS))
    if extra:
        print("\n수집은 되지만 사이트 채널 목록(CHANNELS)에 없는 채널:", ", ".join(extra))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
