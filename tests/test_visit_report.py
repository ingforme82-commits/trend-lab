import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("visit_report", Path(__file__).resolve().parents[1] / "tools" / "visit_report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class VisitReportTest(unittest.TestCase):
    def test_default_only_saves_site_brief_without_notification_import(self):
        real_import = __import__
        def guarded_import(name, *args, **kwargs):
            if "kakao" in name:
                self.fail("Kakao module must never load")
            return real_import(name, *args, **kwargs)
        with patch.object(report.sys, "argv", ["visit_report.py"]), patch.object(report, "save_brief") as save, patch.object(report, "get", side_effect=AssertionError("No report collection needed")), patch("builtins.__import__", side_effect=guarded_import), contextlib.redirect_stdout(io.StringIO()):
            report.main()
        save.assert_called_once_with()
