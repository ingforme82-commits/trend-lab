import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import leaders  # noqa: E402
from leaders import pct_rank, score, us_groups  # noqa: E402


class LeadersTest(unittest.TestCase):
    def test_pct_rank(self):
        self.assertEqual(pct_rank([1, 3, 2]), [0.0, 100.0, 50.0])
        self.assertEqual(pct_rank([5]), [100.0])

    def test_score_order(self):
        gs = [{"name": "a", "chg": 1.0, "val": 10, "up": 1, "n": 4}, {"name": "b", "chg": 5.0, "val": 50, "up": 4, "n": 4}]
        out = score(gs)
        self.assertEqual(out[0]["name"], "b")
        self.assertEqual(out[0]["score"], 100.0)          # 50 + 30 + 20
        self.assertEqual(out[1]["breadth"], 25.0)

    def test_us_groups_weighted(self):
        st = [{"sym": "A", "ind": "반도체", "chg": 10.0, "mcap": 300, "val": 1}, {"sym": "B", "ind": "반도체", "chg": -2.0, "mcap": 100, "val": 5},
              {"sym": "C", "ind": "반도체", "chg": 0.0, "mcap": 100, "val": 2}, {"sym": "D", "ind": "은행", "chg": 1.0, "mcap": 1, "val": 1}]
        g = us_groups(st)
        self.assertEqual(len(g), 1)                       # 3종목 미만 업종은 뺌
        self.assertEqual(g[0]["chg"], 5.6)                # (3000 - 200 + 0) / 500
        self.assertEqual(g[0]["up"], 1)
        self.assertEqual([r["sym"] for r in g[0]["rows"]], ["B", "C", "A"])

    def test_changes_alert(self):
        tmp = Path(__file__).resolve().parent / "_leaders_state_test.json"
        try:
            with mock.patch.object(leaders, "STATE", tmp):
                now = datetime(2026, 10, 28, 10, 0, tzinfo=timezone(timedelta(hours=9)))
                g = lambda n: {"name": n, "chg": 1.0, "up": 1, "n": 2, "score": 50}
                d1 = {"kr": {"open": True, "industry": [g("반도체"), g("기계"), g("조선")]}}
                self.assertEqual(leaders.changes(d1, now), [])          # 첫 기록은 알림 없음
                d2 = {"kr": {"open": True, "industry": [g("기계"), g("반도체"), g("방산")]}}
                txt = [x["text"] for x in leaders.changes(d2, now)]
                self.assertTrue(any("1위 → 기계" in t for t in txt))
                self.assertTrue(any("새로 진입: 방산" in t for t in txt))
                self.assertEqual(leaders.changes(d2, now), [])          # 같은 상태면 다시 알리지 않음
        finally:
            tmp.unlink(missing_ok=True)


class ChinaLeadersTest(unittest.TestCase):
    """11/28 3a: 중국·홍콩 업종 주도 + 상한가 집계."""
    def test_krw_hangeul(self):
        from leaders import krw_hangeul
        self.assertEqual(krw_hangeul("3조 559억원"), 3.0559e12)
        self.assertEqual(krw_hangeul("6,323억원"), 6.323e11)
        self.assertEqual(krw_hangeul("-"), 0.0)

    def test_limit_and_groups(self):
        from leaders import cn_groups, cn_limit, cn_rows
        self.assertEqual(cn_limit("688347", "SHANGHAI"), 20.0)
        self.assertEqual(cn_limit("002371", "SHENZHEN"), 10.0)
        self.assertIsNone(cn_limit("01347", "HONG_KONG"))
        def st(code, ratio, ind, val="100억원", up=True):
            return {"stockEndType": "stock", "symbolCode": code, "reutersCode": code + ".X", "stockName": code,
                    "fluctuationsRatioRaw": str(ratio), "compareToPreviousPrice": {"code": "2" if up else "5"},
                    "industryCodeType": {"industryGroupKor": ind}, "accumulatedTradingValueKrwHangeul": val,
                    "marketValueKrwHangeul": "1조원", "closePriceRaw": "10"}
        rows = cn_rows([st("688347", "20.00", "반도체"), st("603986", "10.00", "반도체"), st("688825", "12.97", "반도체"),
                        st("601288", "2.00", "은행", up=False), st("04338", "0", "소프트웨어", val="-")], "SHANGHAI")
        self.assertEqual(len(rows), 4)                              # 거래 없는 종목 제외
        self.assertTrue(rows[0]["name"].endswith("상한가"))
        self.assertFalse(rows[2]["limit_up"])
        g = [x for x in cn_groups(rows) if x["name"] == "반도체"][0]
        self.assertEqual((g["n"], g["limit_up"]), (3, 2))
        hk = cn_rows([st("01347", "20.69", "반도체")], "HONG_KONG")
        self.assertFalse(hk[0]["limit_up"])                         # 홍콩은 제한폭 없음


if __name__ == "__main__":
    unittest.main()


class RisingGroupsTest(unittest.TestCase):
    def test_positive_average_and_at_least_half_rising(self):
        rows = [{"name":"급락","chg":-7,"n":4,"up":0},
                {"name":"한종목편중","chg":2,"n":10,"up":2},
                {"name":"확산","chg":1,"n":4,"up":3},
                {"name":"보합","chg":0,"n":4,"up":2}]
        self.assertEqual([g["name"] for g in leaders.rising_groups(rows)],["확산"])
