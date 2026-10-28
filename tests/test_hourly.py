import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import hourly  # noqa: E402
from hourly import slot_rank  # noqa: E402


class HourlyTest(unittest.TestCase):
    def test_slot_rank(self):
        start = {"a": 100, "b": 100, "c": 100, "d": 100}
        now = {"a": {"name": "A", "px": 110, "chg": 5, "val": 50e8}, "b": {"name": "B", "px": 102, "chg": 1, "val": 50e8},
               "c": {"name": "C", "px": 99, "chg": -1, "val": 50e8}, "d": {"name": "D", "px": 150, "chg": 9, "val": 1e8}}
        r = slot_rank(start, now, {"a": "반도체", "b": "반도체", "c": "반도체"}, min_val=30e8)
        self.assertEqual([x["name"] for x in r["stocks"]], ["A", "B", "C"])     # 거래대금 작은 D 제외
        self.assertEqual(r["stocks"][0]["slot"], 10.0)
        self.assertEqual(r["sectors"][0]["name"], "반도체")
        self.assertEqual(r["sectors"][0]["up"], 2)
        self.assertEqual((r["up"], r["n"]), (2, 3))

    def test_market_slots(self):
        st = {}
        p1 = {"a": {"name": "A", "px": 105, "chg": 5.0, "val": 1}}
        r = hourly._market(st, "kr", p1, {}, True, "2026-10-29", "09", 0)
        self.assertTrue(r["slots"][0]["gap"])                                # 첫 시간대는 전일 종가(100)부터
        self.assertAlmostEqual(r["slots"][0]["stocks"][0]["slot"], 5.0, places=2)
        p2 = {"a": {"name": "A", "px": 110, "chg": 10.0, "val": 1}}
        r = hourly._market(st, "kr", p2, {}, True, "2026-10-29", "10", 0)
        self.assertEqual([x["h"] for x in r["slots"]], ["10", "09"])          # 최신 시간대가 앞
        self.assertAlmostEqual(r["slots"][0]["stocks"][0]["slot"], 0.0, places=2)   # 10시 시작값 110 → 지금 110
        self.assertAlmostEqual(r["slots"][1]["stocks"][0]["slot"], 10.0, places=2)  # 09시: 100 → 10시 시작 110
        self.assertTrue(r["slots"][0]["live"])
        self.assertFalse(r["slots"][1]["live"])


if __name__ == "__main__":
    unittest.main()
