"""Published financial-card invariants; no network or notifications."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ShipAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads((ROOT / "data" / "ship-earnings-2026q3.json").read_text(encoding="utf-8"))
        cls.card = next(x for x in json.loads((ROOT / "data" / "headline.json").read_text(encoding="utf-8"))["items"]
                        if x["tag"] == "🚢 조선기자재 3분기 실적")

    def test_each_company_has_period_basis_source_and_no_unverified_numbers(self):
        rows = self.audit["records"]
        self.assertEqual(len({r["name"] for r in rows}), 31)
        for r in rows:
            with self.subTest(company=r["name"]):
                self.assertTrue(r["source_name"])
                self.assertTrue(r["source_url"].startswith("https://"))
                self.assertEqual((r["period_start"], r["period_end"], r["months"]),
                                 ("2026-07-01", "2026-09-30", 3))
                if r["status"] == "materials_matched":
                    self.assertIn(r["basis"], ("연결", "별도"))
                    self.assertIsInstance(r["revenue"], (int, float))
                    self.assertIsInstance(r["operating_profit"], (int, float))
                else:
                    self.assertIsNone(r["revenue"])
                    self.assertIsNone(r["operating_profit"])

    def test_card_totals_and_each_displayed_source_match_audit(self):
        rows = self.audit["records"]
        matched = [r for r in rows if r["status"] == "materials_matched"]
        self.assertEqual(len(matched), self.card["materials_matched_count"])
        self.assertEqual(len(rows) - len(matched), self.card["unverified_count"])
        for r in rows:
            line = next(p for p in self.card["points"] if f" {r['name']} — " in p)
            self.assertIn("26Q3", line)
            self.assertIn(r["source_name"], line)
            self.assertEqual("미확인" in line, r["status"] != "materials_matched")

    def test_prior_quarter_correction_is_preserved(self):
        r = next(r for r in self.audit["records"] if r["name"] == "대창솔루션")
        self.assertEqual((r["revenue"], r["operating_profit"]), (178, 4))
        self.assertEqual(r["receipt_no"], "20261116001622")
        self.assertTrue(any("26Q2" in p and "189" in p for p in self.card["points"]))


if __name__ == "__main__":
    unittest.main()
