import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from s7 import KST, calc, is_common, krx_regular, prev_mcap  # noqa: E402


class S7Test(unittest.TestCase):
    def test_common(self):
        self.assertTrue(is_common("005930"))
        self.assertFalse(is_common("005935"))
        self.assertFalse(is_common("00088K"))

    def test_prev_mcap(self):
        self.assertAlmostEqual(prev_mcap(110, 110, 10, 1), 100)
        self.assertAlmostEqual(prev_mcap(90, 90, 10, -1), 100)

    def test_calc(self):
        rows = [{"code": "005930", "chg": 10.0, "pmcap": 300}, {"code": "005935", "chg": 5.0, "pmcap": 50},
                {"code": "000660", "chg": -10.0, "pmcap": 100}]
        s = calc(rows, kospi_prev=1000, kospi_pts=30, total_prev=1000)
        self.assertEqual(rows[0]["pts"], 30.0)      # 1000 × 30% × 10%
        self.assertEqual(rows[1]["pts"], 0.0)       # 우선주는 지수 미포함
        self.assertIsNone(rows[1]["w"])
        self.assertEqual(rows[2]["pts"], -10.0)
        self.assertEqual(s["pts"], 20.0)
        self.assertEqual(s["w"], 40.0)
        self.assertEqual(s["ex_pts"], 10.0)
        self.assertAlmostEqual(s["ex_chg"], 10 / 600 * 100, places=2)
        self.assertEqual(s["share"], 67)


    def test_krx_regular(self):
        from datetime import datetime
        self.assertTrue(krx_regular(datetime(2026, 10, 30, 14, 0, tzinfo=KST)))
        self.assertFalse(krx_regular(datetime(2026, 10, 30, 23, 50, tzinfo=KST)))   # 마감 뒤 NXT 시간
        self.assertFalse(krx_regular(datetime(2026, 10, 31, 10, 0, tzinfo=KST)))    # 토요일


if __name__ == "__main__":
    unittest.main()
