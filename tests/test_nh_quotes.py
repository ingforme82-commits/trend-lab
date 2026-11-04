import sys
import unittest
from unittest.mock import patch
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from nh_quotes import normalize, gh, NO_WINDOW


class NhQuotesTest(unittest.TestCase):
    def test_github_reads_and_writes_hide_child_console(self):
        with patch("nh_quotes.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout="{}")) as run:
            gh(["test"])
            self.assertEqual(run.call_args.kwargs["creationflags"], NO_WINDOW)
            gh(["test"], {"branch": "quotes"})
            self.assertEqual(run.call_args.kwargs["creationflags"], NO_WINDOW)

    def test_day_quote_uses_regular_close_and_query_time(self):
        quote = normalize({"marketperiod_cls": "3", "trdprc": 101, "normal_trdprc": 100, "pctchng": 99}, 123456)
        self.assertEqual((quote["sess"], quote["chg"], quote["checked_at"]), ("day", 1, 123456))
        self.assertNotIn("at", quote)
        self.assertTrue(quote["live"])

    def test_regular_is_not_extended(self):
        quote = normalize({"marketperiod_cls": "1", "trdprc": 101, "normal_trdprc": 100}, 123456)
        self.assertFalse(quote["live"])
        self.assertTrue(quote["stale"])

    def test_bad_price_or_session_rejected(self):
        for code, base in (("9", 100), ("3", 0)):
            with self.assertRaises(ValueError):
                normalize({"marketperiod_cls": code, "trdprc": 101, "normal_trdprc": base}, 123456)
