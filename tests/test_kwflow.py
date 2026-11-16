import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from kwflow import merge, parse  # noqa: E402

ROWS = [{"dt": "20261116", "frgnr_invsr": "-621003", "orgn": "172932", "ind_invsr": "435032"},
        {"dt": "20261113", "frgnr_invsr": "5655", "orgn": "-67038", "ind_invsr": "56445"}]


class T(unittest.TestCase):
    def test_today_row_million_won(self):                  # 11/16 삼성전자 실측: 외국인 -621,003백만 = -6,210억
        v = parse(ROWS, "20261116")
        self.assertEqual(v["frgn"], -621003 * 1_000_000); self.assertEqual(v["org"], 172932 * 1_000_000)

    def test_no_today_row(self):
        self.assertIsNone(parse(ROWS, "20261117"))

    def test_zero_is_not_yet(self):
        self.assertIsNone(parse([{"dt": "20261117", "frgnr_invsr": "0", "orgn": "0", "ind_invsr": "0"}], "20261117"))

    def test_merge(self):
        r = {"code": "005930"}
        merge(r, {"005930": {"frgn": -1e9, "org": None, "hm": "09:25"}})
        self.assertEqual(r["est_kw"], {"frgn": -1e9, "org": None, "hm": "09:25"})


if __name__ == "__main__":
    unittest.main()
