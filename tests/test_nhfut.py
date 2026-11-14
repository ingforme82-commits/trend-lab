"""NH 선물 조회 모듈: 월물 코드·세션·조회 전용."""
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import nhfut  # noqa: E402

KST = timezone(timedelta(hours=9))


class NhFutTest(unittest.TestCase):
    def test_k200_roll(self):
        self.assertEqual(nhfut.k200_code(date(2026, 11, 15)), "KA016C000")     # 26년 12월물
        self.assertEqual(nhfut.k200_code(date(2026, 12, 10)), "KA016C000")     # 만기일까지
        self.assertEqual(nhfut.k200_code(date(2026, 12, 11)), "KA0173000")     # 다음 날 27년 3월물

    def test_cme_roll(self):
        self.assertEqual(nhfut.cme_code("ES", date(2026, 11, 15)), "ESZ26")
        self.assertEqual(nhfut.cme_code("NQ", date(2026, 12, 10)), "NQH27")    # 만기 8일 전부터 다음 분기물

    def test_session(self):
        self.assertEqual(nhfut.k200_session(datetime(2026, 11, 13, 10, 0, tzinfo=KST)), "day")
        self.assertEqual(nhfut.k200_session(datetime(2026, 11, 13, 20, 0, tzinfo=KST)), "night")
        self.assertEqual(nhfut.k200_session(datetime(2026, 11, 15, 10, 0, tzinfo=KST)), "night")   # 일요일: 마지막 야간

    def test_quote_only(self):
        with self.assertRaises(PermissionError):
            nhfut._call("/krfuture/order/v1/buy", {})


if __name__ == "__main__":
    unittest.main()
