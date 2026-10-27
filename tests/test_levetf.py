import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from leadership import sector_momentum  # noqa: E402
from levetf import extra_stats  # noqa: E402

D = lambda c, h=None, l=None: {"o": c, "h": h or c, "l": l or c, "c": c}


class ExtraStatsTest(unittest.TestCase):
    def test_ma20_range_volume(self):
        past = [D(100 + i, 101 + i, 99 + i) for i in range(25)]
        r = extra_stats(past, {"o": 120, "h": 130, "l": 118, "c": 125}, 50, [100] * 25)
        self.assertAlmostEqual(r["ma20"], round((sum(100 + i for i in range(6, 25)) + 125) / 20, 2))
        self.assertEqual(r["hi20"], 130)
        self.assertEqual(r["lo20"], 104)
        self.assertEqual(r["vol_ratio"], 0.5)
        self.assertTrue(r["over_ma20"])

    def test_preopen_uses_last_close(self):
        past = [D(10)] * 20
        r = extra_stats(past, None, None, [])
        self.assertEqual(r["vs_ma20"], 0.0)
        self.assertIsNone(r["vol_ratio"])


class MomentumRefTest(unittest.TestCase):
    def test_foreign_sector_not_mixed_into_domestic_share(self):
        kr = [{"score": 50, "chg": 1, "above5": True, "val": 1e12, "avgval": 1e12}]
        us = [{"score": 50, "chg": 1, "above5": True, "val": 3e9, "avgval": 1e9}]
        out = {s["name"]: s for s in sector_momentum({"A": kr, "B": kr, "미국 반도체": us}, {"미국 반도체": 1.5})}
        self.assertEqual(out["A"]["share_shift"], 1.0)                 # 달러 금액이 원화 합계에 섞이지 않음
        self.assertEqual(out["미국 반도체"]["share_shift"], 2.0)       # (3/1) ÷ QQQ 1.5


if __name__ == "__main__":
    unittest.main()
