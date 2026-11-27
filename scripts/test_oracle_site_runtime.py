"""oracle_site_runtime 브리핑 크기 제한·1MB 초과 raw 읽기 (11/28)."""
import base64
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle_site_runtime as rt  # noqa: E402


class RuntimeTest(unittest.TestCase):
    def test_trim_keeps_newest_under_limit(self):
        hist = [{"day": f"d{i}", "pad": "x" * 1000} for i in range(50)]
        out = rt.trim_history(hist, limit=20_000)
        self.assertEqual(out[0]["day"], "d0")
        self.assertLessEqual(len(json.dumps(out, ensure_ascii=False, indent=1).encode()), 20_000)
        self.assertGreater(len(out), 5)

    def test_trim_keeps_at_least_one(self):
        self.assertEqual(len(rt.trim_history([{"pad": "x" * 5000}], limit=10)), 1)

    def test_content_decoded_or_raw_fallback(self):
        data = [{"day": "2026-11-28"}]
        cur = {"content": base64.b64encode(json.dumps(data).encode()).decode()}
        self.assertEqual(rt.decode_content(cur, "data/briefs.json", "main"), data)
        with mock.patch.object(rt, "command", return_value=json.dumps(data)) as cmd:
            self.assertEqual(rt.decode_content({"content": "", "encoding": "none"}, "data/briefs.json", "main"), data)
            self.assertIn("Accept: application/vnd.github.raw", cmd.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
