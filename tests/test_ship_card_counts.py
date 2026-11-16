"""Offline regression checks: no watcher main, network or notifications."""
import ast
from datetime import datetime
import json
from pathlib import Path
import re
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "dart_watch.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
selected = [n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name in {"refresh_ship_card_counts", "ship_card_update"}]
namespace = dict(re=re, json=json, Path=Path, datetime=datetime,
                 HEADLINE=Path("unused"), SHIP_CARD="ship")
exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), namespace)
refresh = namespace["refresh_ship_card_counts"]
update = namespace["ship_card_update"]


class ShipCardTests(unittest.TestCase):
    def test_counts_unique_filings_not_notes_or_stale_pending(self):
        card = dict(points=["✔ 11/16 A — 매출액 1억", "✔ 11/17 A — 매출액 2억",
                            "✔ 11/16 B — 실적 공시 나옴(숫자는 공시 원문 확인)",
                            "🔎 설명"], pending=["A", "C", "C"], title="22곳 발표 · 9곳 대기")
        refresh(card)
        self.assertEqual(card["reported_count"], 2)
        self.assertEqual(card["pending"], ["C"])
        self.assertEqual(card["unverified_count"], 1)
        self.assertNotIn("22곳", card["title"])
        self.assertIn("미발표 1곳", card["title"])

    def run_update(self, extra, existing=None):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "card.json"
            card = dict(tag="ship", points=existing or [], pending=["A"],
                        title_summary="연결·별도 구분", title="오래된 제목")
            path.write_text(json.dumps(dict(items=[card, dict(tag="other", title="keep")])),
                            encoding="utf-8")
            result = update("A", "분기보고서", "20261116", extra, path)
            return result, json.loads(path.read_text(encoding="utf-8"))

    def test_missing_revenue_change_does_not_borrow_profit_change(self):
        ok, data = self.run_update(["매출액 10억", "영업이익 2억 (작년 같은 분기 대비 +20%)"])
        self.assertTrue(ok)
        line = data["items"][0]["points"][0]
        self.assertIn("매출액 10억 · 영업이익 2억 (+20%)", line)
        self.assertEqual(data["items"][0]["pending"], [])
        self.assertNotIn("미발표", data["items"][0]["title"])
        self.assertEqual(data["items"][1], dict(tag="other", title="keep"))

    def test_placeholder_is_reported_but_unverified(self):
        ok, data = self.run_update([])
        self.assertTrue(ok)
        self.assertEqual(data["items"][0]["reported_count"], 1)
        self.assertEqual(data["items"][0]["unverified_count"], 1)

    def test_empty_filing_does_not_erase_verified_number(self):
        ok, data = self.run_update([], ["✔ 11/13 A — 매출액 10억"])
        self.assertFalse(ok)
        self.assertEqual(data["items"][0]["points"], ["✔ 11/13 A — 매출액 10억"])


if __name__ == "__main__":
    unittest.main()
