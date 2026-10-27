import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from official import parse_bls, parse_eia, parse_treasury  # noqa: E402

UST = """Date,"1 Mo","3 Mo","2 Yr","10 Yr","30 Yr"
10/26/2026,4.11,4.22,4.68,5.00,5.31
10/23/2026,4.11,4.22,4.69,5.00,5.33
"""
EIA = '''"STUB_1","10/16/26","10/9/26","Difference","Percent Change","10/17/25","Difference","Percent Change"
"Crude Oil","695.200","698.560","-3.361","-0.500","831.388","-136.188","-16.400"
"Commercial (Excluding SPR)","412.517","415.577","-3.061","-0.700","422.824","-10.307","-2.400"
"Distillate Fuel Oil","104.286","102.611","1.674","1.600","115.551","-11.266","-9.700"
'''


class OfficialTest(unittest.TestCase):
    def test_treasury(self):
        r = parse_treasury(UST)
        self.assertEqual(r["date"], "2026-10-26")
        self.assertEqual(r["rates"]["2Y"], {"v": 4.68, "bp": -1})
        self.assertEqual((r["s10_2"], r["s10_3m"]), (32, 78))

    def test_eia(self):
        r = parse_eia(EIA)
        self.assertEqual(r["week"], "2026-10-16")
        self.assertEqual([x["name"] for x in r["items"]], ["상업용 원유", "정제유(디젤 등)"])
        self.assertEqual(r["items"][0]["chg"], -3.061)

    def test_bls(self):
        js = {"Results": {"series": [
            {"seriesID": "CUUR0000SA0", "data": [{"year": "2026", "period": "M09", "value": "103.7"}, {"year": "2025", "period": "M09", "value": "100.0"}]},
            {"seriesID": "CES0000000001", "data": [{"year": "2026", "period": "M09", "value": "160029"}, {"year": "2026", "period": "M08", "value": "160000"}]},
            {"seriesID": "LNS14000000", "data": [{"year": "2026", "period": "M09", "value": "4.2"}]}]}}
        r = {x["name"]: x for x in parse_bls(js)}
        self.assertEqual(r["CPI"]["v"], 3.7)
        self.assertEqual(r["비농업 고용"]["v"], 29)
        self.assertEqual(r["실업률"]["v"], 4.2)


if __name__ == "__main__":
    unittest.main()
