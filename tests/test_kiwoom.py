"""키움 조회 모듈 + 실제 코스피·코스닥 변곡점(moves) 연결."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import kiwoom  # noqa: E402
import moves  # noqa: E402

KST = timezone(timedelta(hours=9))
M = 60_000
T0 = int(datetime(2026, 11, 13, 10, 0, tzinfo=KST).timestamp() * 1000)   # 금요일 10시(정규장)


def noisy_fall(n=120, start=5450.0, drop=0.0006):
    """1분마다 오르내리면서 꾸준히 빠지는 실제 지수 모양(1분 효율은 낮고 5분 효율은 높음)."""
    rows, v = [], start
    for i in range(n):
        v *= 1 - drop
        rows.append((T0 + i * M, round(v * (1.0015 if i % 2 else 0.9985), 2)))
    return rows


class KiwoomModuleTest(unittest.TestCase):
    def test_orders_blocked(self):
        with self.assertRaises(PermissionError):
            kiwoom.call("kt10000", "/api/dostk/ordr", {})

    def test_num_strips_direction_sign(self):
        self.assertEqual(kiwoom._num("-529053"), 529053.0)
        self.assertEqual(kiwoom._num("+699.66"), 699.66)
        self.assertIsNone(kiwoom._num(""))


class KiwoomMovesTest(unittest.TestCase):
    def setUp(self):
        self._fetch = moves.fetch

    def tearDown(self):
        moves.fetch = self._fetch

    def test_noisy_real_index_fall_detected(self):
        a = next(x for x in moves.ASSETS if x[0] == "KOSPI")
        ev = moves.cumulative_moves(a, noisy_fall())
        self.assertTrue(ev and ev[0]["move"] < -0.8)

    def test_k200_dup_dropped_in_session_only(self):
        k = {"asset": "KOSPI", "start": T0, "end": T0 + 60 * M, "move": -1.2}
        same = {"asset": "K200", "start": T0 + 5 * M, "end": T0 + 50 * M, "move": -1.4}
        opp = {"asset": "K200", "start": T0 + 5 * M, "end": T0 + 50 * M, "move": 1.1}
        night = {"asset": "K200", "start": T0 + 10 * 3600_000, "end": T0 + 10 * 3600_000 + 30 * M, "move": -1.0}
        out = moves.drop_k200_dup([k, same, opp, night])
        self.assertNotIn(same, out)
        self.assertIn(opp, out)
        self.assertIn(night, out)

    def test_news_linked_to_kospi_move(self):
        rows = noisy_fall()
        moves.fetch = lambda a: rows if a[0] == "KOSPI" else []
        news = [{"ts": T0 + 20 * M, "src": "연합뉴스", "kind": "뉴스", "text": "코스피, 외국인 반도체 매도에 하락 폭 확대",
                 "tags": ["한국", "반도체"], "imp": 50}]
        mv, series = moves.analyze(news)
        k = [m for m in mv if m["asset"] == "KOSPI"]
        self.assertTrue(k and k[0]["session"] == "정규장")
        self.assertEqual(k[0]["news"], [T0 + 20 * M])
        self.assertTrue(news[0].get("pivot"))
        self.assertTrue(series["KOSPI"])

    def test_no_kiwoom_is_skipped(self):
        moves.fetch = lambda a: []
        mv, series = moves.analyze([])
        self.assertEqual(mv, [])
        self.assertEqual(series["KOSDAQ"], [])


if __name__ == "__main__":
    unittest.main()
