import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from xcheck import judge, num_conflict, nums_ko, query_of, similar, tier_of  # noqa: E402

TS = 1_800_000_000_000


class BasicTest(unittest.TestCase):
    def test_query(self):
        self.assertEqual(query_of("Yemeni Houthi rebels launch attack on Saudi Arabia's RAS Tanura refinery"), "Yemeni Houthi Saudi Arabia RAS")

    def test_similar(self):
        a = "Yemeni Houthi rebels launch attack on Saudi Arabia's RAS Tanura refinery in the Gulf"
        b = "Yemen's Houthis say they launched an attack on Saudi Ras Tanura oil refinery"
        self.assertGreaterEqual(similar(a, b), 0.45)
        self.assertEqual(similar("Iran talks", "Iran oil"), 0.0)             # 겹친 단어 3개 미만

    def test_tier(self):
        self.assertEqual(tier_of("Reuters"), "major")
        self.assertEqual(tier_of("Bloomberg.com"), "major")
        self.assertEqual(tier_of("PR Newswire"), "official")
        self.assertEqual(tier_of("Kurdistan24"), "other")


class NumTest(unittest.TestCase):
    def test_ko_units_and_dates_ignored(self):
        n = nums_ko("코카콜라 2026년 3분기 순매출: 134억 달러, 10월 28일, 0.3% 상승")
        self.assertEqual(n["usd"], {134e8})
        self.assertEqual(n["pct"], {0.3})

    def test_conflict(self):
        self.assertFalse(num_conflict("순매출 134억 달러", "Coca-Cola revenue $13.4 billion"))
        self.assertTrue(num_conflict("나스닥 선물 0.5% 상승", "Nasdaq futures rise 1.5%"))
        self.assertFalse(num_conflict("나스닥 선물 상승", "Nasdaq futures rise 1.5%"))           # 한쪽에만 수치

    def test_compound_dollars(self):
        self.assertEqual(nums_ko("1억 7,600만 달러")["usd"], {176_000_000})
        self.assertEqual(nums_ko("2조 3억 4,500만 달러")["usd"], {2_000_345_000_000})
        self.assertFalse(num_conflict("1억 7,600만 달러", "$176M"))
        self.assertFalse(num_conflict("1억 7,600만 달러", "$176,000,000"))
        self.assertTrue(num_conflict("1억 7,600만 달러", "$160M"))


class JudgeTest(unittest.TestCase):
    EN = "Yemeni Houthi rebels launch attack on Saudi Arabia's RAS Tanura refinery in the Gulf"

    def test_major_ok(self):
        c = [{"title": "Yemen's Houthis say they launched an attack on Saudi Ras Tanura oil refinery", "src": "Reuters", "ts": TS},
             {"title": "Unrelated story about Apple iPhone sales", "src": "CNBC", "ts": TS}]
        r = judge("후티 반군 라스타누라 공격", self.EN, c, TS)
        self.assertEqual((r["st"], r["src"]), ("ok", ["Reuters"]))

    def test_other_ref_and_old(self):
        c = [{"title": "Houthis launched attack on Saudi Ras Tanura refinery", "src": "Some Blog", "ts": TS}]
        self.assertEqual(judge("x", self.EN, c, TS)["st"], "ref")
        self.assertIsNone(judge("x", self.EN, [dict(c[0], ts=TS - 13 * 3600_000)], TS))

    def test_diff(self):
        c = [{"title": "Nasdaq 100 futures rise 1.5%, S&P 500 futures up 0.9% premarket", "src": "Reuters", "ts": TS}]
        r = judge("나스닥 100 선물 0.5% 상승, S&P 500 선물 0.3% 상승", "Nasdaq 100 futures up 0.5%, S&P 500 futures rise 0.3%", c, TS)
        self.assertEqual(r["st"], "diff")


class RunTest(unittest.TestCase):
    def test_cached_numeric_result_is_rechecked(self):
        import json
        import tempfile
        import time
        from unittest.mock import patch
        import xcheck

        text = "비트코인 ETF 순유입액 1억 7,600만 달러"
        now = int(time.time() * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"
            for tier, expected in (("other", "ref"), ("major", "ok")):
                cache.write_text(json.dumps({text[:100]: {"first": now, "n": 1, "res": {
                    "st": "diff", "en": "Bitcoin ETF: $176M Net Inflow", "tier": tier,
                    "src": ["Reuters" if tier == "major" else "blockchain.news"], "score": 0.57,
                }}}), encoding="utf-8")
                items = [{"src": "김치터미널", "text": text, "ts": now, "verify": "single"}]
                with patch.object(xcheck, "CACHE", cache), patch.object(xcheck, "_check") as check:
                    self.assertEqual(xcheck.run(items, []), 0)
                    check.assert_not_called()
                self.assertEqual(items[0]["xc"]["st"], expected)
                self.assertEqual(items[0]["verify"], "multi" if tier == "major" else "single")

    def test_every_checked_item_is_cached(self):
        import tempfile
        import time
        import xcheck
        tmp = Path(tempfile.mkdtemp()) / "c.json"
        old, oldc = xcheck.CACHE, xcheck._check
        xcheck.CACHE, xcheck._check = tmp, lambda it, rss: None
        try:
            now = int(time.time() * 1000)
            items = [{"src": "김치터미널", "text": f"속보 {i}", "ts": now} for i in range(7)]
            self.assertEqual(xcheck.run(items, []), 5)
            import json
            self.assertEqual(len(json.loads(tmp.read_text(encoding="utf-8"))), 5)
            self.assertEqual(xcheck.run(items, []), 2)                       # 나머지 2건, 처음 5건은 10분 뒤 재시도
        finally:
            xcheck.CACHE, xcheck._check = old, oldc


if __name__ == "__main__":
    unittest.main()
