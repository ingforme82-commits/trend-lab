import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from moves import group_moments, level_cross, region, session_of, us_open_gap  # noqa: E402

KST = lambda *a: int(datetime(*a, tzinfo=timezone.utc).timestamp() * 1000) - 9 * 3600_000


class RegionTest(unittest.TestCase):
    def test_region(self):
        self.assertEqual(region({"kind": "섹터 시세", "text": "💾 미국 반도체 섹터: 브로드컴 +3.6%"}), "US")
        self.assertEqual(region({"kind": "섹터 시세", "text": "🇰🇷 한국 반도체 섹터: 하이닉스 +5%"}), "KR")
        self.assertEqual(region({"text": "시장 개장 후 나스닥 26,299"}), "US")
        self.assertEqual(region({"text": "한은: AI발 금융 취약성 누적"}), "KR")
        self.assertEqual(region({"text": "AI 무역이 부활하면서 기술주 상승"}), "")


class SessionTest(unittest.TestCase):
    def test_k200_sessions(self):
        self.assertEqual(session_of("K200", KST(2026, 10, 27, 10, 0)), "정규장")
        self.assertEqual(session_of("K200", KST(2026, 10, 27, 22, 35)), "야간선물 시간")
        self.assertEqual(session_of("K200", KST(2026, 10, 28, 2, 0)), "야간선물 시간")
        self.assertEqual(session_of("K200", KST(2026, 10, 27, 17, 0)), "장외(24시간 지수)")

    def test_us_sessions_and_open(self):
        self.assertEqual(session_of("SP", KST(2026, 10, 27, 23, 0)), "미국 정규장")      # 서머타임: 22:30 개장
        self.assertEqual(session_of("NQ", KST(2026, 10, 27, 19, 36)), "프리마켓")
        self.assertEqual(us_open_gap(KST(2026, 10, 27, 22, 35)), 5)
        self.assertIsNone(us_open_gap(KST(2026, 11, 3, 22, 35)))                      # 해제 후엔 23:30 개장


class GroupTest(unittest.TestCase):
    def test_same_moment_one_group(self):
        ms = [{"id": "a", "start": 0}, {"id": "b", "start": 3 * 60_000}, {"id": "c", "start": 5 * 60_000}, {"id": "d", "start": 20 * 60_000}]
        group_moments(ms)
        self.assertEqual([m["grp"] for m in ms], ["a", "a", "a", "d"])


class LevelTest(unittest.TestCase):
    M = 60_000

    def rows(self, prices):
        return [(i * self.M, p) for i, p in enumerate(prices)]

    def test_wti_below_100(self):
        ev = level_cross("WTI", "WTI", "pct", self.rows([100.2, 100.1, 99.95, 99.9, 99.85, 99.8, 99.7]))
        self.assertEqual([(e["level"], e["move"] < 0) for e in ev], [(100, True)])
        self.assertEqual(ev[0]["start"], 2 * self.M)

    def test_hover_without_buffer_ignored(self):
        self.assertEqual(level_cross("WTI", "WTI", "pct", self.rows([100.05, 99.97, 99.96, 99.95, 99.97, 99.96])), [])

    def test_bounce_back_not_held(self):
        self.assertEqual(level_cross("WTI", "WTI", "pct", self.rows([100.2, 99.8, 99.7, 100.1, 100.2, 100.3])), [])

    def test_recross_keeps_latest(self):
        p = [100.3, 99.8, 99.7, 99.6, 99.6, 100.3, 100.4, 100.5, 100.4, 99.8, 99.7, 99.6, 99.5]
        ev = level_cross("WTI", "WTI", "pct", self.rows(p))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["start"], 9 * self.M)


if __name__ == "__main__":
    unittest.main()
