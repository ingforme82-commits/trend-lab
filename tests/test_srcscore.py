import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import srcscore  # noqa: E402


class SrcScoreTest(unittest.TestCase):
    def test_rank_promotes_fast_agreeing_source(self):
        d = {}
        for _ in range(12):
            srcscore.record("kr", "키움", True, secs=9.0, agree=False, data=d, now=1000)
            srcscore.record("kr", "한투", True, secs=0.5, agree=True, data=d, now=1000)
        self.assertEqual(srcscore.rank("kr", ["키움", "한투", "NH"], data=d), ["한투", "키움", "NH"])

    def test_few_records_keep_default(self):
        d = {}
        srcscore.record("kr", "NH", True, secs=0.1, data=d)
        self.assertEqual(srcscore.rank("kr", ["키움", "NH"], data=d), ["키움", "NH"])

    def test_cooldown_after_repeated_fails(self):
        d = {}
        for _ in range(srcscore.FAIL_MAX):
            srcscore.record("kr", "KB", False, data=d, now=1000)
        self.assertTrue(srcscore.skip("kr", "KB", now=1000 + 10, data=d))
        self.assertFalse(srcscore.skip("kr", "KB", now=1000 + srcscore.COOLDOWN + 1, data=d))
        srcscore.record("kr", "KB", True, data=d, now=2000)
        self.assertEqual(d["kr"]["KB"]["fails"], 0)

    def test_stale_value_scores_lower(self):
        fresh, stale = {"ok": 1, "agree": 1, "age": 0}, {"ok": 1, "agree": 1, "age": 60}
        self.assertGreater(srcscore.score(fresh), srcscore.score(stale))


if __name__ == "__main__":
    unittest.main()
