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


if __name__ == "__main__":
    unittest.main()
