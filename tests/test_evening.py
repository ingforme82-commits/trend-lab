import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from evening import check, metrics, oil_heads, price_at, tonight, us_open_kst  # noqa: E402

KST = timezone(timedelta(hours=9))
C = lambda t, o, h, l, c: {"t": t, "T": t + 299_999, "o": str(o), "h": str(h), "l": str(l), "c": str(c)}


class PriceTest(unittest.TestCase):
    def test_price_at_uses_finished_candle(self):
        cs = [C(0, 100, 101, 99, 100), C(300_000, 100, 105, 100, 104), C(600_000, 104, 104, 90, 95)]
        self.assertEqual(price_at(cs, 600_000), 104.0)      # 600000 직전에 끝난 봉
        self.assertIsNone(price_at(cs, 100))

    def test_metrics(self):
        cs = [C(0, 100, 101, 99, 100), C(300_000, 100, 110, 100, 104)]
        m = metrics(cs, 110, {"kr": 300_000, "nx": 0}, 300_000)
        self.assertEqual(m["kr"], 10.0)
        self.assertIsNone(m["nx"])
        self.assertEqual((m["lo"], m["hi"]), (100.0, 110.0))


class TonightTest(unittest.TestCase):
    def test_window(self):
        now = datetime(2026, 10, 28, 20, 5, tzinfo=KST)
        cps = [{"date": "2026-10-28", "time": "23:30", "title": "원유재고"}, {"date": "2026-10-29", "time": "03:00", "title": "FOMC"},
               {"date": "2026-10-29", "time": "09:00", "title": "장 시작"}, {"date": "2026-10-28", "time": "", "title": "실적"},
               {"date": "2026-10-28", "time": "10:00", "title": "지난 일정"}]
        self.assertEqual([c["title"] for c in tonight(cps, now)], ["실적", "원유재고", "FOMC"])
        self.assertEqual(tonight(cps, now)[2]["time"], "10/29 03:00")


class OilHeadsTest(unittest.TestCase):
    def test_filter_and_dedupe(self):
        now = 10 * 3600_000 * 2
        items = [{"ts": now - 1000, "text": "카타르: 이란은 이웃 국가들에 대한 위협을 중단해야 함", "tags": ["중동·유가"], "src": "a"},
                 {"ts": now - 2000, "text": "카타르: 이란은 이웃 국가들에 대한 위협을 중단하고 성의를 보여야 함", "tags": ["중동·유가"], "src": "a"},
                 {"ts": now - 3000, "text": "엔비디아 상승", "tags": ["반도체"], "src": "a"},
                 {"ts": now - 13 * 3600_000, "text": "오래된 유가 뉴스", "tags": ["중동·유가"], "src": "a"}]
        self.assertEqual(len(oil_heads(items, now)), 1)


class MiscTest(unittest.TestCase):
    def test_us_open_dst(self):
        self.assertEqual(us_open_kst(datetime(2026, 10, 27, 20, 0, tzinfo=KST)), "22:30")   # 서머타임
        self.assertEqual(us_open_kst(datetime(2026, 11, 3, 20, 0, tzinfo=KST)), "23:30")    # 해제 후

    def test_check(self):
        self.assertTrue(check({"fut": [], "oil": []}))
        ok = {"fut": [{"kr": 1}] * 4, "oil": [{"name": "WTI", "kr": 1}, {"name": "브렌트", "kr": 0.5}]}
        self.assertEqual(check(ok), [])


if __name__ == "__main__":
    unittest.main()
