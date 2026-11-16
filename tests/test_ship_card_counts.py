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
            and n.name in {"refresh_ship_card_counts", "ship_card_update", "ship_period_proof", "quarter_numbers", "describe", "_chg", "eok"}]
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



class PeriodProofTests(unittest.TestCase):
    def rows(self):
        return [dict(account_nm=a, sj_div="IS", bsns_year="2026", reprt_code="11014",
                     thstrm_dt="2026.07.01 ~ 2026.09.30", thstrm_amount=v,
                     fs_div="CFS", currency="KRW", rcept_no="20261116001622")
                for a, v in [("매출액", "17,800,000,000"), ("영업이익", "400,000,000")]]

    def test_matching_three_month_accounts_have_source_proof(self):
        self.assertIn("OpenDART|2026Q3|2026-07-01|2026-09-30|CFS|20261116001622",
                      namespace["ship_period_proof"](self.rows()))

    def test_prior_quarter_cumulative_year_and_mixed_basis_are_rejected(self):
        for field, value in [("reprt_code", "11012"), ("bsns_year", "2025"),
                             ("thstrm_dt", "2026.01.01 ~ 2026.09.30"),
                             ("thstrm_dt", "2026.04.01 ~ 2026.06.30"),
                             ("fs_div", "OFS"), ("rcept_no", "20261116000000"),
                             ("thstrm_amount", ""), ("currency", "USD")]:
            with self.subTest(field=field, value=value):
                rows = self.rows()
                rows[0][field] = value
                self.assertEqual(namespace["ship_period_proof"](rows), "")

    def test_api_response_with_old_quarter_never_uses_old_numbers(self):
        rows = self.rows()
        old_rows = [dict(r, reprt_code="11012", thstrm_dt="2026.04.01 ~ 2026.06.30",
                         thstrm_amount="18,900,000,000") for r in rows]
        namespace["_get"] = lambda url: json.dumps(dict(list=old_rows + rows)).encode()
        output = namespace["quarter_numbers"]("fixture", "00000000", "분기보고서 (2026.09)")
        self.assertIn("매출액 178억", output)
        self.assertFalse(any("189억" in x for x in output))
        self.assertTrue(any(x.startswith("검증정보: OpenDART|2026Q3") for x in output))

    def test_api_cumulative_dates_return_no_quarter_numbers(self):
        rows = [dict(r, thstrm_dt="2026.01.01 ~ 2026.09.30") for r in self.rows()]
        namespace["_get"] = lambda url: json.dumps(dict(list=rows)).encode()
        self.assertEqual(namespace["quarter_numbers"]("fixture", "00000000", "분기보고서 (2026.09)"), [])

    def test_strict_card_rejects_unproven_numbers_without_changing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "card.json"
            original = json.dumps(dict(items=[dict(tag="ship", points=["미확인"],
                verification_policy="period_source_required")]))
            path.write_text(original, encoding="utf-8")
            self.assertFalse(update("A", "분기보고서 (2026.06)", "20261116",
                                    ["매출액 189억", "영업이익 -1억"], path))
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_strict_card_accepts_both_numbers_with_matching_period_and_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "card.json"
            path.write_text(json.dumps(dict(items=[dict(tag="ship", points=[], pending=["A"],
                verification_policy="period_source_required")])), encoding="utf-8")
            proof = namespace["ship_period_proof"](self.rows())
            self.assertTrue(update("A", "분기보고서 (2026.09)", "20261116",
                                   ["매출액 178억", "영업이익 4억", proof], path))
            card = json.loads(path.read_text(encoding="utf-8"))["items"][0]
            self.assertIn("26Q3", card["points"][0])
            self.assertIn("OpenDART", card["points"][0])
            self.assertEqual(card["unverified_count"], 0)


if __name__ == "__main__":
    unittest.main()
