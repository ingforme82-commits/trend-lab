import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import rt_kis  # noqa: E402

KM = {("H0STCNT0", "005930"): "SMSN", ("H0UNCNT0", "000660"): "SKHX", ("H0UPCNT0", "0001"): "KOSPI", ("HDFSCNT0", "DNASNVDA"): "NVDA", ("HDFSCNT0", "NVDA"): "NVDA"}


class RtTest(unittest.TestCase):
    def test_stock_down_sign(self):
        r = rt_kis.parse("0|H0STCNT0|001|005930^093354^208000^5^-1000^-0.48^x^y", KM)
        self.assertEqual(r[0]["key"], "SMSN")
        self.assertEqual((r[0]["px"], r[0]["ref"], r[0]["chg"]), (208000.0, 209000.0, -0.48))

    def test_multi_record_takes_last(self):
        a, b = "0001^0900^5300.00^2^10.00^1^2^3^4^0.19", "0001^0901^5310.00^2^20.00^1^2^3^4^0.38"
        r = rt_kis.parse(f"0|H0UPCNT0|002|{a}^{b}", KM)
        self.assertEqual((r[0]["px"], r[0]["ref"]), (5310.0, 5290.0))

    def test_us(self):
        f = ["DNASNVDA", "NVDA", "4", "20261116", "20261116", "100000", "20261117", "000000", "1", "2", "3", "160.00", "2", "2.00", "1.27"]
        r = rt_kis.parse("0|HDFSCNT0|001|" + "^".join(f), KM)
        self.assertEqual((r[0]["key"], r[0]["ref"], r[0]["chg"]), ("NVDA", 158.0, 1.27))

    def test_session_switch(self):
        kst = timezone(timedelta(hours=9))
        mon10 = datetime(2026, 11, 16, 10, tzinfo=kst).timestamp()
        mon23 = datetime(2026, 11, 16, 23, tzinfo=kst).timestamp()
        self.assertEqual(rt_kis.subs_now(mon10)[0][2], "KOSPI")
        self.assertEqual(rt_kis.subs_now(mon23)[0][2], "SOXL")
        self.assertEqual(len(rt_kis.subs_now(mon10)), rt_kis.MAX_SUBS)

    def test_nxt_after_market(self):
        r = rt_kis.parse("0|H0UNCNT0|001|000660^183012^612000^2^7000^1.16^x", KM)
        self.assertEqual((r[0]["key"], r[0]["ref"], r[0]["mk"]), ("SKHX", 605000.0, "NXT"))
        r = rt_kis.parse("0|H0UNCNT0|001|000660^101500^612000^2^7000^1.16^x", KM)
        self.assertEqual(r[0]["mk"], "KRX+NXT")

    def test_nxt_session_windows(self):
        kst = timezone(timedelta(hours=9))
        at = lambda h, mi=0, d=16: rt_kis.subs_now(datetime(2026, 11, d, h, mi, tzinfo=kst).timestamp())
        self.assertEqual([x[2] for x in at(8, 10)], ["SMSN", "SKHX"])      # NXT 프리마켓
        self.assertEqual(at(9)[0][2], "KOSPI")
        self.assertEqual(at(15, 29)[0][2], "KOSPI")
        self.assertEqual(at(15, 30)[0][2], "SMSN")                          # NXT 애프터마켓
        self.assertEqual(at(19, 59)[1][2], "SKHX")
        self.assertEqual(at(20)[0][2], "SOXL")
        self.assertEqual(at(10, 0, 21)[0][2], "SOXL")                       # 토요일

    def test_ack_json_ignored(self):
        self.assertEqual(rt_kis.parse('{"header":{}}', KM), [])


if __name__ == "__main__":
    unittest.main()
