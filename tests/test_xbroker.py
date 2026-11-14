"""증권사 교차 확인 — 다수 일치 값 채택."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from xbroker import consensus  # noqa: E402


class XbrokerTest(unittest.TestCase):
    def test_majority_wins_and_off_reported(self):
        r = consensus({"키움": (209000.0, 0.48), "한투": (209000.0, 0.48), "NH": (209000.0, 0.48), "네이버": (208500.0, 0.24)}, "stk")
        self.assertEqual(r["px"], 209000.0)
        self.assertEqual(r["agree"], ["키움", "한투", "NH"])
        self.assertEqual(r["off"], {"네이버": 208500.0})

    def test_index_tolerance(self):
        r = consensus({"키움": (5290.53, -0.98), "한투": (5290.54, -0.98), "네이버": (5290.53, -0.98)}, "idx")
        self.assertEqual(len(r["agree"]), 3)
        self.assertEqual(r["off"], {})

    def test_tie_uses_priority(self):
        r = consensus({"KB": (208500.0, None), "NH": (209000.0, 0.48)}, "stk")
        self.assertEqual(r["px"], 209000.0)                 # 1:1 이면 우선순위(NH > KB)

    def test_chg_from_agreeing_source(self):
        r = consensus({"NH": (824.78, None), "키움": (824.78, -1.05)}, "idx")
        self.assertEqual(r["chg"], -1.05)


if __name__ == "__main__":
    unittest.main()
