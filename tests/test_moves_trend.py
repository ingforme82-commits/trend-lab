import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from moves import ASSETS, detect  # noqa: E402

WTI = next(a for a in ASSETS if a[0] == "WTI")
NQ = next(a for a in ASSETS if a[0] == "NQ")


def series(slope_pct_per_min: float, n: int = 240):
    rows, px = [], 100.0
    for i in range(n):
        wig = 0.02 if i % 2 else -0.02                       # 작은 잔물결
        if i >= 150:                                         # 150분째부터 천천히 상승
            px *= 1 + slope_pct_per_min / 100
        rows.append((i * 60_000, px + wig))
    return rows


class TrendTest(unittest.TestCase):
    def test_wti_slow_1pct_hour_detected(self):
        mv = detect(WTI, series(0.02))                       # 60분에 약 +1.2%
        self.assertTrue(any(m["move"] >= 1.0 for m in mv), mv)

    def test_wti_flat_not_detected(self):
        self.assertEqual(detect(WTI, series(0.0)), [])

    def test_nasdaq_same_slow_rise_not_forced(self):          # 1시간 1% 기준은 유가만
        self.assertFalse(any(m["move"] >= 1.0 for m in detect(NQ, series(0.02))))


if __name__ == "__main__":
    unittest.main()
