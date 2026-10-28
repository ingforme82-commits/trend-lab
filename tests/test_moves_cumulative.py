"""유가 누적 등락·급변 중복 제거·뉴스 시각 연결 회귀 검사."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import moves

M = 60_000
T = 1793188800000
WTI = next(a for a in moves.ASSETS if a[0] == "WTI")


def trend(change=3, minutes=180):
    return [(T + i * M, 100 * (1 + change / 100) ** (i / minutes)) for i in range(minutes + 1)]


class CumulativeTest(unittest.TestCase):
    def test_slow_three_percent_missed_by_old_detector(self):
        rows = trend()
        self.assertEqual(moves.detect(WTI, rows), [])
        result = moves.cumulative_moves(WTI, rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["kind"], "cumulative")
        self.assertEqual(result[0]["move"], 3)

    def test_hourly_up_and_down(self):
        for change in (1.6, -1.6):
            result = moves.cumulative_moves(WTI, trend(change, 60))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["move"], change)

    def test_brent_supported_other_assets_unchanged(self):
        brent = next(a for a in moves.ASSETS if a[0] == "BRENT")
        self.assertTrue(moves.cumulative_moves(brent, trend()))
        self.assertEqual(moves.cumulative_moves(moves.ASSETS[0], trend()), [])

    def test_small_moves_ignored(self):
        self.assertEqual(moves.cumulative_moves(WTI, trend(0.9, 180)), [])

    def test_wti_exact_one_percent_both_windows_and_directions(self):
        for minutes in (60, 180):
            for change in (1.0, -1.0):
                result = moves.cumulative_moves(WTI, trend(change, minutes))
                self.assertTrue(result)
                self.assertEqual(result[-1]["move"], change)

    def test_wti_one_percent_with_intermediate_noise(self):
        rows = [(T+i*M, 100+i/60 + (0.1 if i%2 else 0)) for i in range(61)]
        result = moves.cumulative_moves(WTI, rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["move"], 1.0)

    def test_brent_threshold_not_lowered(self):
        brent = next(a for a in moves.ASSETS if a[0] == "BRENT")
        self.assertEqual(moves.cumulative_moves(brent, trend(1.0, 60)), [])

    def test_empty_and_flat(self):
        self.assertEqual(moves.cumulative_moves(WTI, []), [])
        self.assertEqual(moves.cumulative_moves(WTI, [(T + i*M, 100) for i in range(181)]), [])

    def test_data_gap_not_a_trend(self):
        rows = [(t + (30*M if i > 90 else 0), p) for i, (t, p) in enumerate(trend())]
        self.assertEqual(moves.cumulative_moves(WTI, rows), [])

    def test_oscillation_not_a_trend(self):
        rows = [(T + i*M, 100 + (1 if i%2 else -1)) for i in range(181)]
        self.assertEqual(moves.cumulative_moves(WTI, rows), [])

    def test_non_positive_price_ignored(self):
        rows = trend()
        rows[90] = (rows[90][0], 0)
        self.assertEqual(moves.cumulative_moves(WTI, rows), [])

    def test_overlapping_signals_have_coherent_prices(self):
        cumulative = moves.cumulative_moves(WTI, trend())[0]
        rapid = {**cumulative, "start": T+150*M, "end": T+180*M,
                 "from": 102, "to": 103, "move": 0.98, "ratio": 5}
        rapid.pop("kind")
        result = moves.merge_moves([rapid, cumulative])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["from"], 100)
        self.assertEqual(result[0]["to"], 103)
        self.assertEqual(result[0]["move"], 3)

    def test_news_during_trend_linked_later_news_excluded(self):
        rows = trend()
        def news(minute, text, tags=None, kind="해외 뉴스"):
            return {"ts": T+minute*M, "text": text, "tags": tags or ["중동·유가"],
                    "src": "테스트", "kind": kind}
        items = [news(-10, "이란 협상"), news(70, "EIA 원유재고 감소"),
                 news(140, "호르무즈 항행 경고"), news(190, "뒤늦은 보도"),
                 news(90, "반도체 실적", ["반도체"]), news(80, "가격 자동 집계", kind="관전 포인트")]
        with patch.object(moves, "fetch", side_effect=lambda a: rows if a[0]=="WTI" else []):
            result, _ = moves.analyze(items)
        event = next(m for m in result if m.get("kind") == "cumulative")
        self.assertEqual(len(result), 1)
        self.assertEqual(set(event["news"]), {items[0]["ts"], items[1]["ts"], items[2]["ts"]})
        self.assertTrue(all(event["start"]-15*M <= t <= event["end"] for t in event["news"]))
        self.assertEqual({n["lag"] for n in event["items"]}, {-10, 70, 140})
        self.assertNotIn(items[3]["ts"], event["news"])
        self.assertNotIn(items[4]["ts"], event["news"])
        self.assertNotIn(items[5]["ts"], event["news"])

    def test_no_matching_news_no_fabrication(self):
        with patch.object(moves, "fetch", side_effect=lambda a: trend() if a[0]=="WTI" else []):
            result, _ = moves.analyze([])
        self.assertEqual(result[0]["news"], [])
        self.assertEqual(result[0]["items"], [])


if __name__ == "__main__":
    unittest.main()
