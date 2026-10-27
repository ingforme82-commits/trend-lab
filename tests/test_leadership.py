import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from leadership import build, indicators, pct_rank, score, sector_momentum  # noqa: E402

NOW = 1_800_000_000_000


class PctRankTest(unittest.TestCase):
    def test_basic_and_ties(self):
        self.assertEqual(pct_rank({"a": 1, "b": 2, "c": 3}), {"a": 0.0, "b": 50.0, "c": 100.0})
        r = pct_rank({"a": 1, "b": 1, "c": 3})
        self.assertEqual(r["a"], r["b"])
        self.assertEqual(r["a"], 25.0)

    def test_none_and_single(self):
        self.assertEqual(pct_rank({"a": None, "b": 5}), {"b": 50.0})
        self.assertEqual(pct_rank({"a": None}), {})

    def test_negative_values(self):
        r = pct_rank({"a": -5, "b": -1, "c": 2})
        self.assertLess(r["a"], r["b"])


class IndicatorTest(unittest.TestCase):
    def test_values(self):
        hist = {"closes": [100, 100, 100, 100], "vals": [10.0] * 20, "hi3m": 110}
        ind = indicators({"px": 110, "chg": 5.0, "val": 15.0}, hist, 2.0)
        self.assertAlmostEqual(ind["tva"], 1.5)
        self.assertAlmostEqual(ind["rs"], 3.0)
        self.assertAlmostEqual(ind["ma5"], (110 / 102 - 1) * 100)      # 5일선 = (400+110)/5 = 102
        self.assertAlmostEqual(ind["high"], 0.0)

    def test_missing(self):
        ind = indicators({"px": 100, "chg": None, "val": None}, None, 1.0)
        self.assertEqual(ind, {"tva": None, "rs": None, "ma5": None, "high": None})

    def test_short_history(self):
        ind = indicators({"px": 100, "chg": 1, "val": 5}, {"closes": [1, 2], "vals": [1] * 5}, 0)
        self.assertIsNone(ind["tva"])
        self.assertIsNone(ind["ma5"])


class ScoreTest(unittest.TestCase):
    def test_weighted_and_renormalized(self):
        raw = {"a": {"tva": 3, "rs": 3, "ma5": 3, "high": 3},
               "b": {"tva": 1, "rs": 1, "ma5": 1, "high": 1},
               "c": {"tva": 2, "rs": None, "ma5": 2, "high": 2}}
        s = score(raw)
        self.assertEqual(s["a"]["score"], 100.0)
        self.assertEqual(s["b"]["score"], 0.0)
        self.assertEqual(s["c"]["used"], ["tva", "ma5", "high"])      # 누락 지표 빼고 다시 나눔
        self.assertEqual(s["c"]["score"], 50.0)

    def test_all_missing(self):
        self.assertIsNone(score({"a": {"tva": None, "rs": None, "ma5": None, "high": None}})["a"]["score"])


class SectorTest(unittest.TestCase):
    def test_order(self):
        hot = [{"score": 90, "chg": 5, "above5": True, "val": 30, "avgval": 10}] * 3
        cold = [{"score": 10, "chg": -2, "above5": False, "val": 5, "avgval": 10}] * 3
        out = sector_momentum({"A": cold, "B": hot})
        self.assertEqual(out[0]["name"], "B")
        self.assertEqual(out[0]["up"], 100.0)
        self.assertGreater(out[0]["share_shift"], 1)


class BuildTest(unittest.TestCase):
    def test_stale_row_drops_today_indicators(self):
        cards = [{"name": "S", "rows": [
            {"sym": "1.KS", "name": "가", "px": 110, "chg": 5, "val": 15, "cur": "KRW", "at": NOW, "stale": False},
            {"sym": "2.KQ", "name": "나", "px": 90, "chg": -1, "val": 5, "cur": "KRW", "at": NOW, "stale": True},
            {"sym": "X", "name": "미국", "px": 1, "chg": 1, "cur": "USD", "at": NOW}]}]
        hist = {s: {"closes": [100] * 4, "vals": [10.0] * 20, "hi3m": 120, "last": "2026-10-26"} for s in ("1.KS", "2.KQ")}
        idx = {"^KS11": {"chg": 2.0, "at": NOW, "status": "OPEN"}, "^KQ11": {"chg": 1.0, "at": NOW, "status": "OPEN"}}
        r = build(cards, idx, hist, NOW)
        self.assertEqual([x["sym"] for x in r["stocks"]], ["1.KS", "2.KQ"])   # 미국 종목 제외, 점수 순
        b = next(x for x in r["stocks"] if x["sym"] == "2.KQ")
        self.assertEqual(b["note"], "지연")
        self.assertEqual(sorted(b["used"]), ["high", "ma5"])
        a = r["stocks"][0]
        self.assertAlmostEqual(a["raw"]["rs"], 3.0)                         # 코스피 대비
        self.assertEqual(r["sectors"][0]["name"], "S")


if __name__ == "__main__":
    unittest.main()
