import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from moves import level_cross


class Wti100Test(unittest.TestCase):
    """WTI 관전 기준선 하향 이탈(11/12 운영자: 100달러 → 85달러)."""
    def test_small_immediate_cross_from_exactly_level(self):
        events = level_cross("WTI", "WTI", "pct", [(0, 85), (60000, 84.99)])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["start"], 60000)
        self.assertEqual(events[0]["level"], 85)

    def test_staying_below_does_not_repeat(self):
        events = level_cross("WTI", "WTI", "pct", [(0, 85.01), (60000, 84.99), (120000, 84.98)])
        self.assertEqual(len(events), 1)

    def test_touch_is_not_break(self):
        self.assertEqual(level_cross("WTI", "WTI", "pct", [(0, 85.01), (60000, 85)]), [])

    def test_recross_is_new_event(self):
        rows = [(0, 85), (60000, 84.99), (120000, 85), (180000, 84.98)]
        self.assertEqual(len(level_cross("WTI", "WTI", "pct", rows)), 2)
