import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from kbprog import parse  # noqa: E402


class KbProgTest(unittest.TestCase):
    def test_parse(self):
        rows = [{"dt": "20261028", "nt_b_amt": "328675518", "nt_b_q": "1397205"}, {"dt": "20261027", "nt_b_amt": "-6032933", "nt_b_q": "-27359"}]
        v = parse(rows)
        self.assertEqual(v["day"], "2026-10-28")
        self.assertAlmostEqual(v["amt"], 328675518000)          # 천 원 → 원
        self.assertAlmostEqual(v["amt5"], 322642585000)
        self.assertEqual(v["n5"], 2)

    def test_empty(self):
        self.assertIsNone(parse([]))
        self.assertIsNone(parse([{"dt": "x"}]))


if __name__ == "__main__":
    unittest.main()
