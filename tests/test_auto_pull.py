import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from auto_pull import decide  # noqa: E402


class AutoPullTest(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(decide(True, 0, 3), "skip_dirty")       # 고치던 파일 있으면 건드리지 않음
        self.assertEqual(decide(False, 0, 0), "up_to_date")
        self.assertEqual(decide(False, 0, 2), "ff")              # 깃허브만 새로우면 빨리 감기
        self.assertEqual(decide(False, 1, 0), "ahead_only")
        self.assertEqual(decide(False, 1, 2), "diverged")        # 갈라지면 자동 합치기 안 함


if __name__ == "__main__":
    unittest.main()
