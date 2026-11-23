import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from chan import candle, channel, levels, nxt_view, nxt_window, sector_view, state  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

A = {"hi1": ["10/26", "10/31"], "hi2": ["11/09", "11/13"], "lo1": ["10/19", "10/24"], "lo2": ["11/03", "11/12"]}


def rows():
    # 10/20~11/16 하락 채널: 고점 10/28 200 → 11/11 170, 저점 10/22 150 → 11/05 120
    days = ["10/20", "10/21", "10/22", "10/23", "10/27", "10/28", "10/29", "10/30", "11/02", "11/03", "11/04", "11/05",
            "11/06", "11/09", "11/10", "11/11", "11/12", "11/13", "11/16"]
    hi = {"10/28": 200, "11/11": 170}; lo = {"10/22": 150, "11/05": 120}
    out = []
    for d in days:
        h = hi.get(d, 160); l = lo.get(d, 140)
        out.append([d, 150, h, l, 150])
    return out


class T(unittest.TestCase):
    def test_channel_lines(self):
        ch = channel(rows(), A)
        self.assertEqual([rows()[i][0] for i in ch["hi"]], ["10/28", "11/11"])
        self.assertAlmostEqual(ch["su"], -3.0)                    # 30 내림 / 10봉
        self.assertAlmostEqual(ch["up_now"], 170 - 3 * 3)

    def test_state_needs_ma5(self):                               # 운영자 11/17: 채널 돌파는 5일선도 같이
        ch = {"up_now": 100, "lo_now": 80, "ma5": 110, "gap_next": -1}
        self.assertEqual(state(ch, 105, False), "채널 위·5일선 아래")
        ch["ma5"] = 100
        self.assertEqual(state(ch, 105, False), "돌파 확인")
        self.assertEqual(state(ch, 105, True), "돌파 시도(장중)")
        self.assertEqual(state(ch, 100.5, False), "돌파 관찰·상단 근접")     # +1% 안은 돌파 아님(11/19: 5일선 위·상단 3% 안 = 돌파 관찰)
        self.assertEqual(state(ch, 79, False), "하단 이탈")

    def test_breakout_needs_prior_high(self):                    # 운영자 11/19: 채널 상단 +1%와 수평 저항(전고점)을 같이
        ch = {"up_now": 100, "lo_now": 80, "ma5": 100, "gap_next": -1, "res_h": 110}
        self.assertEqual(state(ch, 105, False), "채널 돌파·전고점 아래")
        self.assertEqual(state(ch, 111, False), "돌파 확인")
        self.assertEqual(state({**ch, "gap_next": -6}, 94, False), "채널 안")   # 채널선만 가깝고 전고점 +17% → 근접 아님

    def test_levels_swing_high(self):
        r = [["d%d" % i, 10, h, h - 5, h - 2] for i, h in enumerate([20, 21, 22, 30, 22, 21, 20, 19, 25, 18, 17, 16, 15, 14])]
        lv = levels(r, 15)
        self.assertEqual((lv["res_h"], lv["res_day"]), (25, "d8"))     # 현재가 바로 위 스윙 고점(좌우 3봉)

    def test_sector_needs_weakest(self):                         # 운영자 11/19: 대장만 갈 수 없다
        a = {"name": "대장", "code": "A", "px": 120, "up_now": 100, "res_h": 110, "state": "돌파 확인"}
        b = {"name": "약체", "code": "B", "px": 90, "up_now": 100, "res_h": 105, "state": "채널 안"}
        v = sector_view([a, b])
        self.assertEqual((v["state"], v["broke"], v["laggard"]), ("섹터 돌파 아님", 1, "약체"))
        self.assertEqual(sector_view([a, {**b, "px": 111, "state": "돌파 확인"}])["state"], "섹터 돌파 확인")

    def test_nxt_window(self):
        kst = timezone(timedelta(hours=9))
        at = lambda h, m=0, d=18: nxt_window(datetime(2026, 11, d, h, m, tzinfo=kst))
        self.assertTrue(at(8)); self.assertTrue(at(8, 49)); self.assertFalse(at(8, 50)); self.assertFalse(at(9)); self.assertFalse(at(15, 29))
        self.assertTrue(at(15, 30)); self.assertTrue(at(21)); self.assertFalse(at(7, 59)); self.assertFalse(at(16, 0, 21))

    def test_nxt_view_after_and_pre(self):
        r = rows()
        ch = channel(r, A)
        after = nxt_view(r, ch, 175.0, "11/16")                  # 오늘 봉(11/16) 있음 → 오늘 칸 선, 종가 자리에 넥장가
        self.assertEqual(after["session"], "애프터")
        self.assertAlmostEqual(after["up"], round(ch["up_now"], 2))
        self.assertAlmostEqual(after["ma5"], round((150 * 4 + 175) / 5, 2))
        self.assertEqual(after["state"], "돌파 시도(넥장)")      # 상단 161 +1% 위 · 5일선 155 위
        pre = nxt_view(r, ch, 150.0, "11/17")                    # 오늘 봉 전 → 다음 칸 선
        self.assertEqual(pre["session"], "프리")
        self.assertAlmostEqual(pre["up"], round(ch["up_next"], 2))
        self.assertAlmostEqual(pre["ma5"], 150.0)

    def test_candles(self):
        self.assertEqual(candle(100, 112, 99, 111, 100)["kind"], "bigup")
        self.assertEqual(candle(100, 101, 90, 100.5, 100)["kind"], "hammer")
        self.assertEqual(candle(100, 110, 99.5, 100.8, 100)["kind"], "shoot")
        self.assertEqual(candle(100, 103, 97, 100.2, 100)["kind"], "doji")
        self.assertEqual(candle(100, 100, 100, 100, 100)["kind"], "flat")


if __name__ == "__main__":
    unittest.main()
