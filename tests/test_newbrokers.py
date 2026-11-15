import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import dbapi  # noqa: E402
import tossapi  # noqa: E402


class NewBrokersTest(unittest.TestCase):
    def test_db_quote_sign_from_diff(self):
        q = dbapi._q({"Prpr": "208000", "PrdyVrss": "-1000", "PrdyCtrt": "0.48"})
        self.assertEqual((q["px"], q["ref"], q["chg"]), (208000.0, 209000.0, -0.48))

    def test_db_empty(self):
        self.assertIsNone(dbapi._q({}))

    def test_read_only_guards(self):
        with self.assertRaises(PermissionError):
            tossapi.get("/api/v1/orders", {})
        with self.assertRaises(PermissionError):
            dbapi.call("/api/v1/trading/kr-stock/order", "UJ", "005930")


if __name__ == "__main__":
    unittest.main()
