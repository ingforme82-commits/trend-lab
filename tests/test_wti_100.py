import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from moves import level_cross


class Wti100Test(unittest.TestCase):
    def test_small_immediate_cross_from_exactly_100(self):
        events = level_cross("WTI", "WTI", "pct", [(0, 100), (60000, 99.99)])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["start"], 60000)
        self.assertEqual(events[0]["level"], 100)

    def test_staying_below_does_not_repeat(self):
        events = level_cross("WTI", "WTI", "pct", [(0, 100.01), (60000, 99.99), (120000, 99.98)])
        self.assertEqual(len(events), 1)

    def test_touch_is_not_break(self):
        self.assertEqual(level_cross("WTI", "WTI", "pct", [(0, 100.01), (60000, 100)]), [])

    def test_recross_is_new_event(self):
        rows = [(0, 100), (60000, 99.99), (120000, 100), (180000, 99.98)]
        self.assertEqual(len(level_cross("WTI", "WTI", "pct", rows)), 2)
