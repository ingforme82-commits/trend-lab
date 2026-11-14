"""📊 오늘 시황(자동) 카드."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import market_card as mc  # noqa: E402

KST = timezone(timedelta(hours=9))
ms = lambda *a: int(datetime(*a, tzinfo=KST).timestamp() * 1000)  # noqa: E731


def data():
    return {"s7": {"day": "2026-11-13", "kospi": {"px": 5290.53, "chg": -0.98, "frgn": -5419.0, "org": -59.0, "ind": 145.0, "prog": -1926.0,
                                                  "arb": -434.0, "nonarb": -1491.0, "up": 454, "dn": 420},
                   "s7": {"pts": -16.32, "share": 31, "ex_chg": -1.54}},
            "leaders": {"kr": {"industry": [{"name": "은행", "chg": 3.58}, {"name": "건설", "chg": 3.03}]}},
            "items": [{"ts": ms(2026, 11, 13, 10, 30), "src": "연합뉴스", "text": "코스피, 외국인 매도에 하락 전환"}],
            "moves": [{"asset": "KOSPI", "name": "코스피", "start": ms(2026, 11, 13, 10, 19), "end": ms(2026, 11, 13, 13, 19),
                       "move": -3.07, "news": [ms(2026, 11, 13, 10, 30)]}]}


IDX = {"001": {"px": 5290.53, "chg": -0.98, "up": 454, "down": 420}, "101": {"px": 699.66, "chg": 0.45, "up": 1023, "down": 649}}
MINS = {"001": [(ms(2026, 11, 13, 9, 0), 5459.01), (ms(2026, 11, 13, 9, 11), 5501.86), (ms(2026, 11, 13, 14, 31), 5261.64),
                (ms(2026, 11, 13, 15, 29), 5290.53)], "101": []}


class MarketCardTest(unittest.TestCase):
    def setUp(self):
        self._head = mc.HEAD
        self.tmp = tempfile.TemporaryDirectory()
        mc.HEAD = Path(self.tmp.name) / "headline.json"
        mc.HEAD.write_text('{"items": []}', encoding="utf-8")

    def tearDown(self):
        mc.HEAD = self._head
        self.tmp.cleanup()

    def test_close_card_facts(self):
        c = mc.compose(data(), ms(2026, 11, 13, 15, 40), IDX, MINS)
        self.assertTrue(c["main"])
        self.assertTrue(c["title"].startswith("마감 — 코스피 5,290.53(-0.98%)"))
        self.assertIn("장중 고점 대비 -3.8%", c["title"])
        self.assertEqual(c["until"], "2026-11-16")                 # 금요일 → 다음 거래일 월요일
        joined = "\n".join(c["points"])
        self.assertIn("고가 5,501.86(09:11) · 저가 5,261.64(14:31)", joined)
        self.assertIn("외국인 -5,419억", joined)
        self.assertIn("변곡점 10:19~13:19 코스피 -3.07% — 시각이 겹친 뉴스: 연합뉴스", joined)
        self.assertNotRegex(joined, r"매수하|매도하|추천|목표가")

    def test_manual_card_keeps_main(self):
        mc.HEAD.write_text(json.dumps({"items": [{"tag": "📊 오늘 시황", "until": "2026-11-13", "when": "11/13(금) 09시 48분 기준"}]},
                                      ensure_ascii=False), encoding="utf-8")
        self.assertFalse(mc.compose(data(), ms(2026, 11, 13, 15, 40), IDX, MINS)["main"])

    def test_phase_and_due(self):
        self.assertEqual(mc.phase(datetime(2026, 11, 14, 12, 0, tzinfo=KST)), "")      # 토요일
        self.assertEqual(mc.phase(datetime(2026, 11, 13, 8, 30, tzinfo=KST)), "")
        self.assertEqual(mc.phase(datetime(2026, 11, 13, 10, 0, tzinfo=KST)), "장중")
        self.assertEqual(mc.phase(datetime(2026, 11, 13, 16, 0, tzinfo=KST)), "마감")
        now = ms(2026, 11, 13, 10, 0)
        self.assertFalse(mc.due("장중", {"day": "2026-11-13", "at": now - 10 * 60_000}, now, "2026-11-13"))
        self.assertTrue(mc.due("장중", {"day": "2026-11-13", "at": now - 31 * 60_000}, now, "2026-11-13"))
        self.assertTrue(mc.due("마감", {"day": "2026-11-13", "phase": "장중"}, now, "2026-11-13"))
        self.assertFalse(mc.due("마감", {"day": "2026-11-13", "phase": "마감"}, now, "2026-11-13"))

    def test_weekend_no_card(self):
        self.assertIsNone(mc.compose(data(), ms(2026, 11, 14, 12, 0), IDX, MINS))


if __name__ == "__main__":
    unittest.main()
