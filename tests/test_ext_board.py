import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from ext_board import events, items_of  # noqa: E402

T = 1793617875000


def row(chg, live=True, sym="KORU"):
    return {"sym": sym, "name": "한국 3배", "sess": "pre", "px": 11.86, "base": 10.63, "chg": chg, "at": T, "live": live, "stale": not live}


class ExtBoardTest(unittest.TestCase):
    def test_steps_once(self):
        st = {}
        self.assertEqual(len(events([row(11.57)], st, T / 1000)), 2)       # 5%·10% 둘 다
        self.assertEqual(events([row(12.0)], st, T / 1000), [])            # 같은 날·세션은 다시 안 냄
        its = items_of(st)
        self.assertEqual(len(its), 1)
        self.assertIn("10% 넘게 상승", its[0]["text"])

    def test_small_or_stale_ignored(self):
        st = {}
        self.assertEqual(events([row(3.0), row(-8.0, live=False, sym="X")], st, T / 1000), [])

    def test_drop_text_and_expiry(self):
        st = {}
        events([row(-6.0)], st, T / 1000)
        self.assertIn("5% 넘게 하락", items_of(st)[0]["text"])
        events([], st, T / 1000 + 37 * 3600)
        self.assertEqual(st, {})


if __name__ == "__main__":
    unittest.main()
