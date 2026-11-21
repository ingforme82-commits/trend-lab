import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import live_news as ln  # noqa: E402


class Done:
    def __init__(self, code):
        self.returncode = code


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stamp = Path(self.tmp.name) / ".tg_all_at"
        self.py = Path(self.tmp.name) / "python.exe"
        self.py.write_text("")
        ln.REFRESH.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def run_refresh(self, code=0):
        calls = []
        with patch.object(ln, "ALL_STAMP", self.stamp), patch.object(ln, "TGR_PY", self.py), \
             patch.object(ln.subprocess, "run", side_effect=lambda args, **kw: calls.append(args) or Done(code)):
            ln.refresh()
        return calls[0]

    def test_full_collection_not_tied_to_clock_minute(self):
        self.assertIn("--all", self.run_refresh())            # 기록 없음 → 분과 상관없이 전체
        self.assertTrue(self.stamp.exists())
        self.assertNotIn("--all", self.run_refresh())         # 방금 끝났으면 속보 채널만

    def test_due_after_nine_minutes(self):
        self.stamp.write_text(str(datetime.now(timezone.utc).timestamp() - 9 * 60 - 1))
        self.assertIn("--all", self.run_refresh())

    def test_failed_full_run_retried_next_time(self):
        with patch.object(ln, "log"):
            self.assertIn("--all", self.run_refresh(code=1))
        self.assertFalse(self.stamp.exists())
        self.assertIn("--all", self.run_refresh())


class FilterTest(unittest.TestCase):
    def rows(self, items):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "tgr.sqlite3"
        con = sqlite3.connect(db)
        con.execute("create table messages (channel_username text, posted_at text, text text, collected_at text)")
        now = datetime.now(timezone.utc) - timedelta(minutes=5)
        con.executemany("insert into messages values (?,?,?,?)", [(c, now.isoformat(), t, now.isoformat()) for c, t in items])
        con.commit()
        con.close()
        with patch.object(ln, "DB", db):
            return ln.from_telegram()

    def test_sector_analyst_fact_post_is_shown(self):
        out = self.rows([("YSKoreaSemi", "[유안타증권 반도체 백길현]\n11월 DRAM 고정거래가격 전월 대비 12% 상승, 서버 DDR5 강세 지속\n☎ 02-3770-0000")])
        self.assertEqual([i["src"] for i in out], ["유안타 반도체"])
        self.assertNotIn("백길현", out[0]["text"])
        self.assertEqual(ln.TG_STATS["유안타 반도체"]["kept"], 1)

    def test_target_price_still_blocked_for_analysts(self):
        out = self.rows([("YSKoreaSemi", "[유안타증권 반도체] SK하이닉스 목표주가 상향, 투자의견 BUY 유지")])
        self.assertEqual(out, [])
        self.assertEqual(ln.TG_STATS["유안타 반도체"]["stockrec"], 1)

    def test_general_channel_broker_header_still_dropped(self):
        out = self.rows([("realtime_stock_news", "[하나증권 리서치센터] 오늘의 리포트 요약 — 반도체 업황 점검 자료")])
        self.assertEqual(out, [])
        self.assertEqual(ln.TG_STATS["실시간 주식뉴스"]["broker"], 1)


if __name__ == "__main__":
    unittest.main()
