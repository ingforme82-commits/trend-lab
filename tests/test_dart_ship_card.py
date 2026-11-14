import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from dart_watch import SHIP_CARD, ship_card_update  # noqa: E402


def card(tmp: Path, pending: list[str]) -> Path:
    p = tmp / "headline.json"
    p.write_text(json.dumps({"items": [
        {"tag": "📊 오늘 시황", "title": "다른 카드", "points": ["x"]},
        {"tag": SHIP_CARD, "title": "t", "points": ["✔ 11/06 한화엔진 — 영업이익 409억", "⏳ 발표 대기: " + " · ".join(pending)],
         "pending": pending},
    ]}, ensure_ascii=False), encoding="utf-8")
    return p


class ShipCardTest(unittest.TestCase):
    def test_adds_line_and_removes_pending(self):
        with tempfile.TemporaryDirectory() as d:
            p = card(Path(d), ["케이에스피", "케이프"])
            extra = ["매출액 320억 (작년 같은 분기 대비 +32.2% · 직전 분기 대비 +1.9%)",
                     "영업이익 45억 (작년 같은 분기 대비 +50.0%)", "연결 기준", "💡 해석: ..."]
            self.assertTrue(ship_card_update("케이에스피", "영업(잠정)실적(공정공시)", "20261113", extra, p))
            it = json.loads(p.read_text(encoding="utf-8"))["items"][1]
            self.assertEqual(it["points"][0], "✔ 11/13 케이에스피 — 매출액 320억 (+32.2%) · 영업이익 45억 (+50.0%)")
            self.assertEqual(it["points"][-1], "⏳ 발표 대기: 케이프")
            self.assertEqual(it["pending"], ["케이프"])
            self.assertIn("한화엔진", it["points"][1])

    def test_no_numbers_and_last_pending(self):
        with tempfile.TemporaryDirectory() as d:
            p = card(Path(d), ["케이프"])
            self.assertTrue(ship_card_update("케이프", "분기보고서 (2026.09)", "20261116", [], p))
            it = json.loads(p.read_text(encoding="utf-8"))["items"][1]
            self.assertTrue(it["points"][0].startswith("✔ 11/16 케이프 — 실적 공시 나옴"))
            self.assertFalse(any(x.startswith("⏳") for x in it["points"]))

    def test_ignores_ir_and_missing_card(self):
        with tempfile.TemporaryDirectory() as d:
            p = card(Path(d), ["케이프"])
            self.assertFalse(ship_card_update("케이프", "기업설명회(IR) 개최", "20261113", [], p))
            q = Path(d) / "empty.json"
            q.write_text('{"items": []}', encoding="utf-8")
            self.assertFalse(ship_card_update("케이프", "영업(잠정)실적", "20261113", [], q))


    def test_monthly_order_disclosure_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = card(Path(d), ["케이프"])
            self.assertFalse(ship_card_update("케이프", "영업(잠정)실적(공정공시)", "20261019", [], p))

    def test_one_line_per_company(self):
        with tempfile.TemporaryDirectory() as d:
            p = card(Path(d), ["케이프"])
            q = ["매출액 4,136억 (작년 같은 분기 대비 +39%)", "영업이익 409억 (작년 같은 분기 대비 +54%)"]
            self.assertTrue(ship_card_update("한화엔진", "분기보고서 (2026.09)", "20261113", q, p))
            pts = json.loads(p.read_text(encoding="utf-8"))["items"][1]["points"]
            self.assertEqual([x for x in pts if "한화엔진" in x], ["✔ 11/13 한화엔진 — 매출액 4,136억 (+39%) · 영업이익 409억 (+54%)"])
            self.assertFalse(ship_card_update("한화엔진", "분기보고서 (2026.09)", "20261114", [], p))


if __name__ == "__main__":
    unittest.main()
