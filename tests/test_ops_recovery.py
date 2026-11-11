import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import brief_slot
import healthcheck

KST = timezone(timedelta(hours=9))
class CatchUpTest(unittest.TestCase):
    def at(self, day, hour, minute):
        return datetime(2026, 11, day, hour, minute, tzinfo=KST)
    def test_waits_for_scheduled_task(self):
        self.assertEqual(brief_slot.due_slots(self.at(12, 14, 3)), [])
        self.assertEqual(brief_slot.due_slots(self.at(12, 14, 5)), ["1400"])
    def test_does_not_backfill_old_slots(self):
        self.assertEqual(brief_slot.due_slots(self.at(12, 14, 21)), [])
        self.assertEqual(brief_slot.due_slots(self.at(12, 2, 50)), [])
    def test_close_uses_1535_execution_time(self):
        self.assertEqual(brief_slot.due_slots(self.at(12, 15, 36)), [])
        self.assertEqual(brief_slot.due_slots(self.at(12, 15, 40)), ["1530"])
    def test_weekend_slots(self):
        self.assertEqual(brief_slot.due_slots(self.at(14, 6, 15)), ["0610"])
        self.assertEqual(brief_slot.due_slots(self.at(14, 14, 5)), [])
        self.assertEqual(brief_slot.due_slots(self.at(15, 6, 15)), [])
    def test_already_published_slot_not_replayed(self):
        with patch.object(brief_slot, "datetime", wraps=datetime) as dt, patch.object(brief_slot, "already", return_value=True), patch.object(brief_slot, "main") as main:
            dt.now.return_value = self.at(12, 20, 10)
            brief_slot.catch_up()
        main.assert_not_called()

class ApiCheckTest(unittest.TestCase):
    def setUp(self):
        healthcheck.R.clear()
    def run_kb(self, token, response):
        kb = SimpleNamespace(_token=Mock(return_value=token), _post=Mock(return_value=response), BASE="https://example.invalid")
        with patch.dict(sys.modules, {"kbprog": kb}):
            healthcheck.check_kb()
        return kb
    def test_kb_requires_successful_price(self):
        kb = self.run_kb("synthetic", {"dataHeader":{"resultCode":"200"}, "dataBody":{"now_prc":"100"}})
        kb._post.assert_called_once()
        self.assertEqual(healthcheck.R[-1]["level"], "정상")
    def test_kb_missing_key_is_not_normal(self):
        kb = self.run_kb(None, {})
        kb._post.assert_not_called()
        self.assertEqual(healthcheck.R[-1]["level"], "주의")
    def test_kb_empty_price_is_not_normal(self):
        self.run_kb("synthetic", {"dataHeader":{"resultCode":"200"}, "dataBody":{}})
        self.assertEqual(healthcheck.R[-1]["level"], "주의")

if __name__ == "__main__":
    unittest.main()
