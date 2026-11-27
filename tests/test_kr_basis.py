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

    def test_weekend_after_close_uses_nxt_last_and_prev_krx_base(self):
        # 11/28 운영자: 토요일에 금요일(11/20) 카드 — 통합 = 넥장 20시 마지막 체결, 등락 기준 = 전일 KRX 종가
        now = datetime(2026, 11, 21, 4, 0, tzinfo=chan.KST)
        at = int(datetime(2026, 11, 20, 19, 58, tzinfo=chan.KST).timestamp() * 1000)
        nq = {"px": 1110000.0, "at": at, "day": "2026-11-20", "session": "애프터"}
        u = {**U, "11/20": 1113000.0}                           # 네이버 일봉 최근일 = KRX 종가
        with mock.patch.object(chan, "uni_closes", return_value=u), mock.patch.object(chan, "krx_closes", return_value=K):
            b = chan.kr_basis("000660", ROWS, now, nq)
        self.assertEqual(b["uni_close"], 1110000.0)
        self.assertEqual(b["krx_close"], 1113000)
        self.assertEqual(b["base"], 1183000)                     # 0.00% 가 아니라 전일 KRX 대비
        self.assertFalse(b["nxt_none"])
        self.assertAlmostEqual(b["uni_sma5_closed"], (1118 + 1100 + 1164 + 1190 + 1110) * 1000 / 5)

    def test_weekend_no_nxt_trade_is_krx(self):
        now = datetime(2026, 11, 21, 4, 0, tzinfo=chan.KST)
        with mock.patch.object(chan, "uni_closes", return_value={**U, "11/20": 1113000.0}),                 mock.patch.object(chan, "krx_closes", return_value=K):
            b = chan.kr_basis("122630", ROWS, now, None)
        self.assertEqual(b["uni_close"], 1113000.0)
        self.assertTrue(b["nxt_none"])
        self.assertEqual(b["base"], 1183000)


class JpFill(unittest.TestCase):
    def test_kis_fills_missing_day(self):
        import types
        fake = types.SimpleNamespace(get=lambda *a, **k: {"output2": [
            {"xymd": "20261127", "open": "7950", "high": "8562", "low": "7821", "clos": "8450"},
            {"xymd": "20261126", "open": "7209", "high": "7895", "low": "7207", "clos": "7762"}]})
        now = datetime(2026, 11, 28, 4, 0, tzinfo=chan.KST)
        with mock.patch.dict(sys.modules, {"kis": fake}):
            rows = chan._jp_fill_kis("285A.T", [["11/25", 1, 1, 1, 6895.0], ["11/26", 1, 1, 1, 7762.0]], now)
        self.assertEqual(rows[-1], ["11/27", 7950.0, 8562.0, 7821.0, 8450.0])
        self.assertEqual(len(rows), 3)


if __name__ == "__main__":
    unittest.main()
