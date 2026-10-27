import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from flows import parse_trader, parse_trend, pick_top  # noqa: E402


class PickTopTest(unittest.TestCase):
    def test_union_of_change_and_value(self):
        tk = {f"{i}.KQ": f"s{i}" for i in range(6)}
        q = {f"{i}.KQ": {"px": 100, "chg": float(i), "val": float(10 - i) * 1e9} for i in range(6)}
        q["9.KQ"] = None
        rows = pick_top(tk, q, n=2)
        self.assertEqual([r["code"] for r in rows], ["5", "4", "1", "0"])   # 등락 상위 5·4 + 대금 상위 0·1, 등락률 순
        self.assertEqual(rows[0]["name"], "s5")

    def test_missing_quote_skipped(self):
        self.assertEqual(pick_top({"1.KS": "a"}, {}), [])


class TrendTest(unittest.TestCase):
    def test_amounts_and_5day(self):
        items = [{"localTradedAt": "2026-10-27", "krx": {"foreignNetVolume": "-100", "organizationNetVolume": "50", "individualNetVolume": "50", "closingPrice": "1000"}},
                 {"localTradedAt": "2026-10-26", "krx": {"foreignNetVolume": "200", "organizationNetVolume": "-10", "individualNetVolume": "0", "closingPrice": "500"}}]
        r = parse_trend(items)
        self.assertEqual(r["day"], "2026-10-27")
        self.assertEqual(r["frgn"], -100_000)
        self.assertEqual(r["frgn5"], -100_000 + 100_000)
        self.assertEqual(r["org5"], 50_000 - 5_000)
        self.assertEqual(r["n5"], 2)

    def test_empty(self):
        self.assertIsNone(parse_trend([]))
        self.assertIsNone(parse_trend([{"krx": None}]))


class TraderTest(unittest.TestCase):
    def test_today_only(self):
        d = [{"date": "2026-10-27", "foreignTrader": {"netSales": -50}}]
        self.assertEqual(parse_trader(d, "2026-10-27", 1000), {"qty": -50, "amt": -50_000})
        self.assertIsNone(parse_trader(d, "2026-10-28", 1000))
        self.assertIsNone(parse_trader([], "2026-10-27", 1000))


if __name__ == "__main__":
    unittest.main()
