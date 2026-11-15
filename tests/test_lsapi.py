"""lsapi — LS증권 조회 전용 모듈."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import lsapi  # noqa: E402


class LsTest(unittest.TestCase):
    def test_order_tr_blocked(self):
        with self.assertRaises(PermissionError):
            lsapi.call("CSPAT00601", {})

    def test_sign(self):
        self.assertEqual(lsapi._signed("1.25", "5"), -1.25)
        self.assertEqual(lsapi._signed("-1.25", "2"), 1.25)
        self.assertEqual(lsapi._signed("0", "3"), 0.0)

    def test_index_parse(self):
        out = {"pricejisu": "5,290.53", "sign": "5", "diffjisu": "0.98", "jniljisu": "5342.89"}
        with mock.patch.object(lsapi, "call", lambda tr, ib: out):
            x = lsapi.index_now("KOSPI")
        self.assertEqual((x["px"], x["chg"], x["prev"]), (5290.53, -0.98, 5342.89))

    def test_no_keys_empty(self):
        with mock.patch.object(lsapi, "_keys", lambda: None), mock.patch.object(lsapi, "_down", lambda why=None: why), \
                mock.patch.object(lsapi, "TOKEN", Path("__nope__.json")):
            self.assertIsNone(lsapi._token())


if __name__ == "__main__":
    unittest.main()
