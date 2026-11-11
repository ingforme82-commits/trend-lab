import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from ext_board import events, items_of  # noqa: E402

T = 1793617875000
S = T / 1000


def row(chg, live=True, sym="KORU"):
    return {"sym": sym, "name": "한국 3배", "sess": "pre", "px": 11.86, "base": 10.63, "chg": chg, "at": T, "live": live, "stale": not live}


class ExtBoardTest(unittest.TestCase):
    def test_steps_once(self):
        st = {}
        self.assertEqual(events([row(11.57)], st, S), [])                  # 첫 번째는 대기(한 번 튄 체결 거름)
        self.assertEqual(len(events([row(11.6)], st, S + 60)), 2)          # 다음 갱신에도 넘어 있으면 5%·10% 확정
        self.assertEqual(events([row(12.0)], st, S + 120), [])             # 같은 날·세션은 다시 안 냄
        its = items_of(st)
        self.assertEqual(len(its), 1)
        self.assertIn("10% 넘게 상승", its[0]["text"])

    def test_bad_tick_not_confirmed(self):
        st = {}
        events([row(-15.2, sym="MSFT")], st, S)                            # 11/12 MSFT -15% 잘못된 체결
        self.assertEqual(events([row(-0.2, sym="MSFT")], st, S + 60), [])  # 다음 갱신에 제자리 → 속보 없음
        self.assertEqual(items_of(st), [])

    def test_small_or_stale_ignored(self):
        st = {}
        self.assertEqual(events([row(3.0), row(-8.0, live=False, sym="X")], st, S), [])

    def test_drop_text_and_expiry(self):
        st = {}
        events([row(-6.0)], st, S)
        events([row(-6.1)], st, S + 60)
        self.assertIn("5% 넘게 하락", items_of(st)[0]["text"])
        events([], st, S + 37 * 3600)
        self.assertEqual({k: v for k, v in st.items() if k != "_pending"}, {})


if __name__ == "__main__":
    unittest.main()
