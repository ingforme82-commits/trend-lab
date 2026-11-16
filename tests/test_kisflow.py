import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from kisflow import merge, parse_est, parse_prog  # noqa: E402


def row(h, amt, q):
    return {"bsop_hour": h, "whol_smtn_ntby_tr_pbmn": str(amt), "whol_smtn_ntby_qty": str(q)}


class T(unittest.TestCase):
    def test_prog_split(self):                             # 11/16 09:15 삼성전자 실측: KRX +192.1억, NXT −171.1억 = 통합 +21.0억
        p = parse_prog({"output": [row("091549", 19210000000, 9000), row("091538", 1, 1)]},
                       {"output": [row("091541", -17110000000, -8000)]}, "2026-11-16")
        self.assertEqual(p["amt"], 2100000000); self.assertEqual(p["hm"], "09:15"); self.assertEqual(p["q"], 1000)

    def test_prog_premarket_only(self):
        p = parse_prog({}, {"output": [row("084900", -500000000, -100)]}, "2026-11-16")
        self.assertIsNone(p["krx"]); self.assertEqual(p["amt"], -500000000)

    def test_prog_empty(self):
        self.assertIsNone(parse_prog({}, {}, "2026-11-16"))

    def test_est_latest_round(self):
        d = {"output2": [{"bsop_hour_gb": "1", "frgn_fake_ntby_qty": "1000", "orgn_fake_ntby_qty": "0", "sum_fake_ntby_qty": "1000"},
                         {"bsop_hour_gb": "2", "frgn_fake_ntby_qty": "1500", "orgn_fake_ntby_qty": "-300", "sum_fake_ntby_qty": "1200"},
                         {"bsop_hour_gb": "3", "frgn_fake_ntby_qty": "0", "orgn_fake_ntby_qty": "0", "sum_fake_ntby_qty": "0"}]}
        e = parse_est(d, "2026-11-16")
        self.assertEqual((e["round"], e["frgn_q"], e["org_q"]), ("2차", 1500, -300))

    def test_est_none_before_release(self):
        self.assertIsNone(parse_est({"output2": []}, "2026-11-16"))

    def test_merge_keeps_kb_5day(self):
        r = {"code": "005930", "px": 200000, "prog": {"amt": 1, "amt5": 99}}
        merge(r, {"005930": {"amt": 5, "krx": 3, "nxt": 2}}, {"005930": {"round": "1차", "frgn_q": 10, "org_q": -5}})
        self.assertEqual(r["prog"]["amt5"], 99); self.assertEqual(r["prog"]["amt"], 5)
        self.assertEqual(r["est"], {"round": "1차", "frgn": 2000000, "org": -1000000})


if __name__ == "__main__":
    unittest.main()
