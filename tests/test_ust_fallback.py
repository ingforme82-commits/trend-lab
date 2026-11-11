import sys
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import market_extra as market

class Response:
    def __init__(self, value):
        self.value = json.dumps(value).encode()
    def read(self):
        return self.value

class YieldTest(unittest.TestCase):
    def setUp(self):
        market._UST.clear()
        self.now = int(datetime.now(timezone.utc).timestamp() * 1000)
    def payload(self, minutes):
        at = datetime.fromtimestamp((self.now - minutes * 60000) / 1000, timezone.utc).isoformat()
        return {"FormattedQuoteResult": {"FormattedQuote": [
            {"symbol": "US" + k, "last": "5.0", "previous_day_closing": "4.9", "last_time": at}
            for k in ("2Y", "10Y", "30Y")
        ]}}
    def test_stale_cnbc_uses_newer_yahoo(self):
        yf = {"px": 4.95, "prev": 4.9, "bp": 5, "at": self.now - 60000, "src": "야후"}
        with patch.object(market.urllib.request, "urlopen", return_value=Response(self.payload(120))), patch.object(market, "_yield_yf", return_value=yf):
            result = market.ust()
        self.assertEqual(result["10Y"]["src"], "야후")
        self.assertFalse(result["10Y"]["stale"])
        self.assertTrue(result["2Y"]["stale"])
    def test_older_yahoo_cannot_replace_cnbc(self):
        yf = {"px": 4.8, "at": self.now - 180 * 60000, "src": "야후"}
        with patch.object(market.urllib.request, "urlopen", return_value=Response(self.payload(120))), patch.object(market, "_yield_yf", return_value=yf):
            result = market.ust()
        self.assertEqual(result["10Y"]["src"], "CNBC")
        self.assertTrue(result["10Y"]["stale"])
    def test_fresh_cnbc_does_not_query_yahoo(self):
        with patch.object(market.urllib.request, "urlopen", return_value=Response(self.payload(1))), patch.object(market, "_yield_yf") as yf:
            result = market.ust()
        yf.assert_not_called()
        self.assertFalse(result["10Y"]["stale"])
    def test_missing_cnbc_uses_yahoo(self):
        yf = {"px": 4.95, "at": self.now - 60000, "src": "야후"}
        with patch.object(market.urllib.request, "urlopen", side_effect=OSError), patch.object(market, "_yield_yf", side_effect=lambda _: dict(yf)):
            result = market.ust()
        self.assertEqual(result["10Y"]["src"], "야후")
    def test_veterans_day_uses_new_york_date(self):
        moment = datetime(2026, 11, 12, 2, tzinfo=timezone.utc).timestamp() * 1000
        self.assertIn("휴장일", market.ust_market_note(moment))
        self.assertEqual(market.ust_market_note(datetime(2026, 11, 12, 15, tzinfo=timezone.utc).timestamp() * 1000), "")

if __name__ == "__main__":
    unittest.main()
