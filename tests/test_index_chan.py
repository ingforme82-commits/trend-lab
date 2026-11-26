import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import index_chan
import chan

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=KST)


def quote(**changes):
    value = dict(itemCode="KOSPI", localTradedAt=NOW.isoformat(), marketStatus="OPEN",
                 openPriceRaw="5,000.25", highPriceRaw="5,010.5", lowPriceRaw="4,990.1", closePriceRaw="5,001.75")
    value.update(changes)
    return value


def history():
    return [["11/17", 5000.25, 5010.5, 4990.1, 5001.75]]


class IndexDataTests(unittest.TestCase):
    def test_decimal_points_not_integer_stock_prices(self):
        q = index_chan.parse_quote(quote(), "KOSPI", NOW)
        self.assertEqual(q["row"][4], 5001.75)
        self.assertTrue(q["live"])
        self.assertEqual(chan._fmt("kr_index", q["row"][4]), "5,001.75pt")

    def test_wrong_index_nonfinite_zero_and_bad_ohlc_rejected(self):
        for changes in [dict(itemCode="KOSDAQ"), dict(closePriceRaw="NaN"), dict(closePriceRaw="0"),
                        dict(lowPriceRaw="6,000"), dict(highPriceRaw="4,000"),
                        dict(localTradedAt=""), dict(localTradedAt="2026-11-18T10:00:00")]:
            with self.subTest(changes=changes):
                self.assertIsNone(index_chan.parse_quote(quote(**changes), "KOSPI", NOW))

    def test_old_future_and_closed_values_never_become_live(self):
        for source, status in [(NOW - timedelta(minutes=4), "OPEN"),
                               (NOW - timedelta(days=1), "OPEN"),
                               (NOW, "CLOSE")]:
            q = index_chan.parse_quote(quote(localTradedAt=source.isoformat(), marketStatus=status), "KOSPI", NOW)
            self.assertFalse(q["live"])
        self.assertIsNone(index_chan.parse_quote(quote(localTradedAt=(NOW + timedelta(minutes=1)).isoformat()), "KOSPI", NOW))

    def test_changed_market_hours_use_provider_session_status(self):
        late = NOW.replace(hour=16)
        self.assertTrue(index_chan.parse_quote(quote(localTradedAt=late.isoformat()), "KOSPI", late)["live"])
        self.assertFalse(index_chan.parse_quote(quote(localTradedAt=late.isoformat(), marketStatus="CLOSE"), "KOSPI", late)["live"])

    def test_history_uses_index_columns_sorted_deduplicated_no_future(self):
        item = dict(stck_bsop_date="20261117", bstp_nmix_oprc="5000.25", bstp_nmix_hgpr="5010.5",
                    bstp_nmix_lwpr="4990.1", bstp_nmix_prpr="5001.75")
        data = dict(output2=[dict(item, stck_bsop_date="20261119"), item, item,
                             dict(item, stck_bsop_date="20261116")])
        rows = index_chan.parse_history(data, NOW)
        self.assertEqual([r[0] for r in rows], ["11/16", "11/17"])
        self.assertEqual(rows[-1][-1], 5001.75)

    def test_index_history_uses_readonly_industry_endpoint_and_correct_symbol(self):
        raw = dict(output2=[dict(stck_bsop_date=(NOW - timedelta(days=i)).strftime("%Y%m%d"),
                               bstp_nmix_oprc="100", bstp_nmix_hgpr="102", bstp_nmix_lwpr="99",
                               bstp_nmix_prpr="101") for i in range(25)])
        from types import SimpleNamespace
        calls = []
        fake = SimpleNamespace(get=lambda *args: calls.append(args) or raw)
        with patch.dict(sys.modules, kis=fake):
            rows, source = index_chan._history("KOSDAQ", NOW, lambda *args: self.fail("unexpected fallback"))
        self.assertEqual(len(rows), 25)
        self.assertEqual(calls[0][1], "FHKUP03500100")
        self.assertEqual(calls[0][2]["FID_COND_MRKT_DIV_CODE"], "U")
        self.assertEqual(calls[0][2]["FID_INPUT_ISCD"], "1001")
        self.assertIn("지수", source)

    def test_failed_current_request_keeps_daily_data_without_fake_live(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(index_chan, "_history", return_value=(history(), "fixture daily")), \
                 patch.object(index_chan, "_current_quote", return_value=None), \
                 patch.object(index_chan, "_naver_history", return_value=[]):
                rows, live, meta = index_chan.bars("KOSPI", NOW,
                    daily_path=Path(folder) / "daily.json", live_path=Path(folder) / "live.json", yahoo=None)
            self.assertEqual(rows, history())
            self.assertFalse(live)
            self.assertIsNone(meta["source_at"])
            self.assertTrue(meta["stale"])

    def test_current_day_chart_is_used_when_current_quote_unavailable(self):
        today = ["11/18", 5000, 5010, 4990, 5005]
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(index_chan, "_history", return_value=(history(), "fixture daily")), \
                 patch.object(index_chan, "_current_quote", return_value=None), \
                 patch.object(index_chan, "_naver_history", return_value=[today]):
                rows, live, meta = index_chan.bars("KOSPI", NOW,
                    daily_path=Path(folder) / "daily.json", live_path=Path(folder) / "live.json", yahoo=None)
            self.assertEqual(rows, history() + [today])
            self.assertFalse(live)
            self.assertTrue(meta["stale"])
            self.assertIsNone(meta["source_at"])

    def test_cached_source_time_revalidated_not_replaced_by_checked_time(self):
        with tempfile.TemporaryDirectory() as folder:
            old = index_chan.parse_quote(quote(localTradedAt=(NOW - timedelta(seconds=170)).isoformat()), "KOSPI", NOW)
            path = Path(folder) / "live.json"
            path.write_text(json.dumps({"KOSPI": {"t": NOW.timestamp(), "quote": old}}), encoding="utf-8")
            with patch.object(index_chan, "_history", return_value=(history(), "fixture")), \
                 patch.object(index_chan, "_quote", side_effect=AssertionError("cache should be used")):
                rows, live, meta = index_chan.bars("KOSPI", NOW + timedelta(seconds=20),
                    daily_path=Path(folder) / "daily.json", live_path=path, yahoo=None)
            self.assertFalse(live)
            self.assertEqual(meta["source_at"], old["source_at"])
            self.assertNotEqual(meta["source_at"], meta["checked_at"])

    def test_config_indices_first_and_tsm_preserved(self):
        c = json.loads((Path(__file__).resolve().parents[1] / "data" / "channels.json").read_text(encoding="utf-8"))
        self.assertEqual([code for code, _ in c["groups"][0]["items"]], ["KOSPI", "KOSDAQ"])
        self.assertEqual(c["groups"][0]["cc"], "kr_index")
        self.assertEqual(sum(code == "TSM" for g in c["groups"] for code, _ in g["items"]), 1)

    def test_build_does_not_confirm_breakout_on_unverified_index_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = {"anchors": {"hi1": ["10/26", "10/31"], "hi2": ["11/09", "11/13"],
                               "lo1": ["10/19", "10/24"], "lo2": ["11/03", "11/12"]},
                   "rule": "fixture", "groups": [{"cc": "kr_index", "country": "한국",
                                                "sector": "지수", "items": [["KOSPI", "코스피"]]}]}
            p = root / "config.json"
            p.write_text(json.dumps(cfg), encoding="utf-8")
            rows = [[(datetime(2026, 10, 19) + timedelta(days=i)).strftime("%m/%d"), 100, 110, 90, 101] for i in range(31)]
            meta = {"instrument_type": "index", "unit": "pt", "stale": True, "quality_note": "fixture stale"}
            with patch.object(chan, "CONF", p), patch.object(chan, "LOG", root / "log.json"), \
                 patch.object(index_chan, "bars", return_value=(rows, False, meta)):
                result = chan.build(NOW)
            item = result["groups"][0]["items"][0]
            self.assertEqual(item["state"], "채널 안")
            self.assertTrue(item["stale"])
            self.assertEqual(item["unit"], "pt")
            self.assertEqual(result["signals"], [])


if __name__ == "__main__":
    unittest.main()
