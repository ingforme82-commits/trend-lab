"""11/20 운영자: 5일선 = 통합 종가(넥장 20시), 등락률 기준가 = KRX 종가 — 두 줄을 섞지 않는다."""
import sys, unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import chan  # noqa: E402

ROWS = [[d, 1, 1, 1, c] for d, c in [("11/16", 1118000.0), ("11/17", 1100000.0), ("11/18", 1164000.0), ("11/19", 1190000.0), ("11/20", 1113000.0)]]
U = {"11/16": 1118000.0, "11/17": 1100000.0, "11/18": 1164000.0, "11/19": 1190000.0}
K = {"2026-11-16": 1120000, "2026-11-17": 1098000, "2026-11-18": 1144000, "2026-11-19": 1183000}


class KrBasis(unittest.TestCase):
    def run_at(self, hm, nq=None):
        now = datetime(2026, 11, 20, hm // 100, hm % 100, tzinfo=chan.KST)
        with mock.patch.object(chan, "uni_closes", return_value=U), mock.patch.object(chan, "krx_closes", return_value=K):
            return chan.kr_basis("000660", ROWS, now, nq)

    def test_intraday_base_is_krx_and_ma5_is_integrated(self):
        b = self.run_at(1100)
        self.assertEqual(b["base"], 1183000)                       # 기준가 = 11/19 KRX 종가
        self.assertAlmostEqual(b["ma5"], (1118 + 1100 + 1164 + 1190 + 1113) * 1000 / 5)
        self.assertAlmostEqual(b["ma5_krx"], (1120 + 1098 + 1144 + 1183 + 1113) * 1000 / 5)
        self.assertEqual(b["krx_close_day"], "11/19")              # 장중엔 오늘 종가 아직 없음

    def test_after_20_uses_nxt_last_for_integrated(self):
        at = int(datetime(2026, 11, 20, 19, 59, tzinfo=chan.KST).timestamp() * 1000)
        b = self.run_at(2010, {"px": 1099000.0, "at": at})
        self.assertEqual(b["uni_close"], 1099000.0)
        self.assertEqual(b["krx_close"], 1113000)
        self.assertEqual(b["uni_close_day"], "11/20")


if __name__ == "__main__":
    unittest.main()
