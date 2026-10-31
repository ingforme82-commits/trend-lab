import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from spot_auto import apply, big_movers, in_window, reason, score, stats, streak  # noqa: E402

AT = int(datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc).timestamp() * 1000)   # 뉴욕 10/27 11:00


class WindowTest(unittest.TestCase):
    def test_dst_and_standard(self):
        KST = timezone(timedelta(hours=9))
        self.assertTrue(in_window(datetime(2026, 10, 27, 23, 0, tzinfo=KST)))     # 서머타임: 개장 22:30
        self.assertFalse(in_window(datetime(2026, 10, 28, 0, 0, tzinfo=KST)))     # 90분 뒤
        self.assertTrue(in_window(datetime(2026, 11, 4, 0, 0, tzinfo=KST)))       # 해제 후: 개장 23:30
        self.assertFalse(in_window(datetime(2026, 11, 3, 23, 0, tzinfo=KST)))     # 개장 전
        self.assertFalse(in_window(datetime(2026, 10, 31, 23, 0, tzinfo=KST)))    # 토요일


class StatsTest(unittest.TestCase):
    def test_basic(self):
        q = {"A": {"px": 110, "prev": 100, "open": 105, "at": AT}, "B": {"px": 95, "prev": 100, "open": 100, "at": AT},
             "C": {"px": 120, "prev": 100, "open": 110, "at": AT}}
        st = stats({"A": "에이", "B": "비", "C": "씨"}, q, "2026-10-27")
        self.assertAlmostEqual(st["avg"], 8.33, places=2)
        self.assertEqual((st["k"], st["n"]), (2, 3))
        self.assertEqual(st["best"]["name"], "씨")

    def test_holiday_or_old_quotes(self):
        q = {"A": {"px": 110, "prev": 100, "open": 105, "at": AT}, "B": {"px": 110, "prev": 100, "at": AT}}
        self.assertIsNone(stats({"A": "a", "B": "b"}, q, "2026-10-28"))

    def test_score_and_reason(self):
        st = {"avg": -3.0, "op": -1.0, "same": 1.0, "n": 5, "k": 5, "best": {"name": "x", "chg": -6.0}}
        self.assertAlmostEqual(score(st, 20), 3 * 1.5 + 0.5 + 1.5)
        r = reason(st, 0, "22:30", 30)
        self.assertIn("5종목 중 5종목 하락", r)
        self.assertIn("최저 x -6.00%", r)
        self.assertNotIn("속보", r)


class ApplyTest(unittest.TestCase):
    def test_apply(self):
        pool = {"G1": {"name": "g1", "kw": "a", "members": {"A": "a"}, "hl": "xyz:A"}, "G2": {"name": "g2", "kw": "b", "members": {"B": "b"}}}
        spots = [{"id": "ASIA", "pin": True, "on": True}, {"id": "TSLA", "on": True}, {"id": "G2", "on": True, "since": "2026-10-20", "hl": "old"}]
        out = apply(spots, pool, [("G2", "r2"), ("G1", "r1")], "2026-10-27")
        self.assertEqual([s["id"] for s in out], ["G2", "G1", "TSLA", "ASIA"])
        self.assertEqual(out[0]["since"], "2026-10-20")          # 이어서 켜진 종목군은 시작일 유지
        self.assertNotIn("hl", out[0])
        self.assertEqual(out[1]["since"], "2026-10-27")
        self.assertFalse(out[2]["on"])
        self.assertTrue(out[3]["on"])


    def test_streak_and_movers(self):
        self.assertEqual(streak([1, -1, 0.5, 0.2, 0.1]), 3)
        self.assertEqual(streak([1, -0.1]), 0)
        st = [{"sym": "A", "chg": -20, "mcap": 5e10}, {"sym": "B", "chg": -15, "mcap": 5e10}, {"sym": "C", "chg": -12, "mcap": 5e10},
              {"sym": "D", "chg": 9, "mcap": 5e10}, {"sym": "E", "chg": -30, "mcap": 1e9}, {"sym": "F", "chg": 3, "mcap": 9e11}]
        self.assertEqual([x["sym"] for x in big_movers(st)], ["A", "B", "D"])   # 한 방향 최대 2개, 소형주·작은 등락 제외

    def test_singles_kept_three_days(self):
        spots = [{"id": "GOOGL", "yf": "GOOGL", "auto": True, "on": True, "since": "2026-10-31"},
                 {"id": "OLD", "yf": "OLD", "auto": True, "on": True, "since": "2026-10-20"}]
        out = apply(spots, {}, [], "2026-11-03", [{"id": "INTC", "name": "인텔", "yf": "INTC"}])
        self.assertEqual([(s["id"], s["on"]) for s in out], [("INTC", True), ("GOOGL", True), ("OLD", False)])


if __name__ == "__main__":
    unittest.main()
