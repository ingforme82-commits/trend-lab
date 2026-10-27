import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import brief  # noqa: E402
import krx  # noqa: E402
from brief_slot import validate  # noqa: E402

M = 60_000
NOW = 1_800_000_000_000


def good(slot: str) -> dict:
    d = {"updated": NOW - M,
         "health": {"tg": {"last": NOW - 5 * M, "refresh": True}, "rss": {"ok": 19, "total": 19}},
         "brief": {"futures": [{"name": str(i)} for i in range(8)],
                   "macro": [{"ts": NOW - 60 * M, "src": "김치터미널", "text": "GDP"}],
                   "heads": [{"ts": NOW - 10 * M, "src": "연합뉴스", "text": "x"}]},
         "us10y": {"px": 4.9},
         "reg": {"SP500": {"at": NOW - 8 * 60 * M}, "XYZ100": {"at": NOW - 8 * 60 * M}},
         "kr": {"KOSPI": {"open": True, "at": NOW - M}, "KR200": {"open": True, "at": NOW - M}},
         "sectors": [{"name": "한국 반도체", "rows": [{"cur": "KRW", "stale": False}] * 10}]}
    return d


class ValidateTest(unittest.TestCase):
    def test_good_passes(self):
        self.assertEqual(validate("0720", good("0720"), NOW), [])
        self.assertEqual(validate("1400", good("1400"), NOW), [])

    def test_stale_news_blocks(self):
        d = good("0720"); d["updated"] = NOW - 30 * M
        self.assertTrue(any("10분 초과" in x for x in validate("0720", d, NOW)))

    def test_tg_fail_blocks(self):
        d = good("0720"); d["health"]["tg"]["refresh"] = False
        self.assertIn("텔레그램 수집 실패", validate("0720", d, NOW))

    def test_rss_half_fail_blocks(self):
        d = good("0720"); d["health"]["rss"] = {"ok": 5, "total": 19}
        self.assertTrue(any("RSS" in x for x in validate("0720", d, NOW)))

    def test_missing_source_blocks(self):
        d = good("0720"); d["brief"]["heads"].append({"ts": NOW, "src": "", "text": "출처없음"})
        self.assertTrue(any("출처" in x for x in validate("0720", d, NOW)))

    def test_0720_needs_us_close(self):
        d = good("0720"); d["reg"] = {}
        self.assertTrue(any("미국 정규장" in x for x in validate("0720", d, NOW)))

    def test_1400_needs_open_kr(self):
        d = good("1400"); d["kr"]["KOSPI"]["open"] = False
        self.assertTrue(any("열려 있지 않음" in x for x in validate("1400", d, NOW)))
        d = good("1400"); d["kr"]["KOSPI"]["at"] = NOW - 30 * M
        self.assertTrue(any("지연" in x for x in validate("1400", d, NOW)))

    def test_1400_stale_sector_rows_block(self):
        d = good("1400"); d["sectors"][0]["rows"] = [{"cur": "KRW", "stale": True}] * 5 + [{"cur": "KRW", "stale": False}] * 5
        self.assertTrue(any("전일 값" in x for x in validate("1400", d, NOW)))


class NoonSaveTest(unittest.TestCase):
    def test_noon_save_keeps_other_slots(self):
        with tempfile.TemporaryDirectory() as t:
            brief.BRIEFS = Path(t) / "b.json"
            from datetime import datetime
            day = datetime.now(brief.KST).strftime("%Y-%m-%d")
            brief.BRIEFS.write_text(json.dumps([{"day": day, "slot": "07:20", "at": 1}]), encoding="utf-8")
            self.assertTrue(brief.save({"at": 0}))
            slots = sorted(h["slot"] for h in json.loads(brief.BRIEFS.read_text(encoding="utf-8")))
            self.assertEqual(slots, ["07:20", "12:00"])


class KrxParseTest(unittest.TestCase):
    def test_sign_from_code(self):
        base = {"closePrice": "95,000", "compareToPreviousClosePrice": "5,000", "localTradedAt": "2026-10-27T09:30:00+09:00"}
        self.assertEqual(krx._parse({**base, "compareToPreviousPrice": {"code": "5"}})["chg"], -5.0)
        self.assertEqual(krx._parse({**base, "compareToPreviousPrice": {"code": "2"}})["prev"], 90000)
        self.assertEqual(krx._parse({**base, "compareToPreviousPrice": {"code": "3"}, "compareToPreviousClosePrice": "0"})["chg"], 0.0)

    def test_trading_value_units(self):
        b = {"closePrice": "100", "compareToPreviousClosePrice": "0", "compareToPreviousPrice": {"code": "3"}}
        self.assertEqual(krx._parse({**b, "accumulatedTradingValue": "4,347억"})["val"], 4347e8)
        self.assertEqual(krx._parse({**b, "accumulatedTradingValue": "2,577,862백만"})["val"], 2577862e6)


if __name__ == "__main__":
    unittest.main()
