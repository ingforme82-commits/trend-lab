import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from watch import analyze, conds, series_events  # noqa: E402

D = lambda d, o, h, l, c: {"d": d, "o": o, "h": h, "l": l, "c": c}
PAST = [D("10-16", 101, 104, 93, 93.67), D("10-19", 104, 105, 98, 98.65), D("10-20", 94.5, 102.6, 91.4, 97.55),
        D("10-21", 102.9, 106.1, 99.3, 103.24), D("10-22", 90.6, 93.4, 80.2, 82.11), D("10-23", 81.6, 87.6, 80.8, 83.56),
        D("10-26", 85.9, 93.15, 84.2, 90.5)]


class WatchTest(unittest.TestCase):
    def test_gap_ma5_three(self):
        r = analyze(PAST, {"o": 95.03, "h": 96.0, "l": 94.1, "c": 95.87})
        self.assertEqual(r["streak_prev"], 2)
        self.assertEqual(r["gap"], 5.01)
        self.assertTrue(r["gap_over_high"])
        self.assertAlmostEqual(r["ma5"], round((103.24 + 82.11 + 83.56 + 90.5 + 95.87) / 5, 2))
        self.assertTrue(r["over_ma5"] and r["three"])
        self.assertEqual(r["streak"], 3)

    def test_bearish_today_breaks(self):
        r = analyze(PAST, {"o": 95.0, "h": 96.0, "l": 88.0, "c": 91.0})
        self.assertFalse(r["bull"])
        self.assertFalse(r["three"])
        self.assertEqual(r["streak"], 0)

    def test_level_hits_and_preopen(self):
        past = [D("a", 11.7, 12.51, 11.8, 11.92), D("b", 10.9, 11.8, 10.7, 11.34), D("c", 12.3, 12.37, 11.3, 11.94), D("d", 10.5, 11.2, 10.3, 10.89)]
        r = analyze(past, None, 12)
        self.assertNotIn("px", r)
        self.assertEqual([h["d"] for h in r["level_hits"]], ["a", "c"])
        self.assertAlmostEqual(r["to_level"], round((12 / 10.89 - 1) * 100, 2))


class FlipTest(unittest.TestCase):
    X = {"sym": "SOXL", "px": 94.9, "o": 95.0, "prev": 90.5, "ma5": 91.0, "streak_prev": 2}

    def test_margin_holds_judgement(self):
        self.assertIsNone(conds(dict(self.X, px=95.05))["bull"])          # 시가 ±0.15% 안 = 보류
        self.assertFalse(conds(dict(self.X, px=94.5))["bull"])

    def test_series_flip_below_open_breaks_three(self):
        ser = [(1, 95.5), (2, 96.5), (3, 95.02), (4, 94.6), (5, 94.9)]
        ev = series_events(dict(self.X, px=94.9), ser)
        self.assertEqual([(e["ts"], e["k"], e["up"]) for e in ev], [(4, "bull", False)])
        self.assertIn("무산 중", ev[0]["text"])

    def test_ma5_break(self):
        ev = series_events(dict(self.X, px=89.0), [(1, 93.0), (2, 89.0)])
        self.assertIn(("ma5", False), [(e["k"], e["up"]) for e in ev])


class LatestEventsTest(unittest.TestCase):
    def test_superseded_removed(self):
        from watch import latest_events
        ev = [{"ts": 1, "sym": "SOXL", "k": "level", "up": False, "text": "아래로"}, {"ts": 2, "sym": "SOXL", "k": "level", "up": True, "text": "도달"},
              {"ts": 3, "sym": "SOXL", "k": "bull", "up": False, "text": "음봉"}, {"ts": 2, "sym": "KORU", "k": "bull", "up": True, "text": "양봉"}]
        out = latest_events(ev)
        self.assertEqual([(e["sym"], e["k"], e["text"]) for e in out], [("SOXL", "bull", "음봉"), ("SOXL", "level", "도달"), ("KORU", "bull", "양봉")])
        self.assertEqual([e["n"] for e in out], [1, 2, 1])


if __name__ == "__main__":
    unittest.main()
