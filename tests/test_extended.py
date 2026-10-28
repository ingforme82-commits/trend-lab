import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from extended import build_one, session_of  # noqa: E402

PER = {"pre": {"start": 1000, "end": 2000}, "regular": {"start": 2000, "end": 3000}, "post": {"start": 3000, "end": 4000}}


class ExtTest(unittest.TestCase):
    def test_session(self):
        self.assertEqual(session_of(1500, 500, PER), "pre")
        self.assertEqual(session_of(2500, 2500, PER), "reg")
        self.assertEqual(session_of(3500, 2999, PER), "post")
        self.assertEqual(session_of(800, 600, PER), "post")    # 전 거래일 애프터마켓
        self.assertEqual(session_of(600, 600, PER), "reg")

    def test_premarket_live(self):
        meta = {"regularMarketPrice": 100.0, "regularMarketTime": 500, "currentTradingPeriod": PER}
        r = build_one(meta, [1500, 1600], [103.0, None], now=1700)
        self.assertEqual((r["sess"], r["px"], r["base"], r["chg"], r["live"], r["stale"]), ("pre", 103.0, 100.0, 3.0, True, False))

    def test_stale_and_regular(self):
        meta = {"regularMarketPrice": 100.0, "regularMarketTime": 500, "currentTradingPeriod": PER}
        self.assertTrue(build_one(meta, [1000], [99.0], now=1000 + 16 * 60)["stale"])   # 15분 넘게 체결 없음
        self.assertIsNone(build_one(meta, [2500], [101.0], now=2600))                     # 정규장 중이면 시간외 없음
        self.assertIsNone(build_one({"regularMarketTime": 1}, [1500], [1.0], now=1600))   # 기준가 없음


if __name__ == "__main__":
    unittest.main()
