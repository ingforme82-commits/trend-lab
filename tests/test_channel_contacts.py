import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from channel_fit import anchored_side
from chan import channel, state


def values():
    high = [190 - i for i in range(28)]
    high[2], high[14] = 198, 186
    return high, [f"{i:02d}" for i in range(28)]


class ContactTests(unittest.TestCase):
    def test_two_anchors_are_usable_without_a_third_touch(self):
        high, dates = values()
        line = anchored_side(high, dates, 2, "10", 26, True)
        self.assertEqual(line["anchors"], [2, 14])
        self.assertEqual(line["touches"], [2, 14])
        self.assertTrue(line["verified"])

    def test_extra_touch_does_not_move_the_line(self):
        high, dates = values()
        first = anchored_side(high, dates, 2, "10", 26, True)
        high[8] = 192 * .997
        second = anchored_side(high, dates, 2, "10", 26, True)
        self.assertEqual(first["anchors"], second["anchors"])
        self.assertAlmostEqual(first["slope"], second["slope"])
        self.assertAlmostEqual(first["intercept"], second["intercept"])
        self.assertEqual(second["touches"], [2, 8, 14])

    def test_remote_old_segment_is_not_searched_to_force_three_touches(self):
        high, dates = values()
        high[0] = high[6] = 205
        line = anchored_side(high, dates, 2, "10", 26, True)
        self.assertEqual(line["start"], 2)
        self.assertEqual(line["anchors"], [2, 14])

    def test_slight_overlapping_contact_is_counted_without_refitting(self):
        high, dates = values()
        high[8] = 192 * 1.005
        # 두 번째 기준 구간보다 이른 접촉이라 두 기준점을 바꾸지 않는다.
        line = anchored_side(high, dates, 2, "10", 26, True)
        self.assertEqual(line["anchors"], [2, 14])
        self.assertEqual(line["touches"], [2, 8, 14])
        self.assertTrue(line["verified"])
        self.assertAlmostEqual(line["max_overlap_pct"], .5)

    def test_prior_crossing_is_reported_without_changing_the_recent_reference(self):
        high, dates = values()
        high[8] = 192 * 1.08
        line = anchored_side(high, dates, 2, "10", 26, True)
        self.assertEqual(line["anchors"], [2, 14])
        self.assertAlmostEqual(line["max_overlap_pct"], 8.)
        self.assertEqual(line["active_overlap_pct"], 0.)
        self.assertTrue(line["verified"])

    def test_close_points_are_not_counted_as_independent_extra_touches(self):
        high, dates = values()
        high[13] = 187 * .999
        line = anchored_side(high, dates, 2, "10", 26, True)
        self.assertNotIn(13, line["touches"])
        self.assertEqual(len(line["touches"]), 2)

    def test_current_closed_bar_does_not_move_the_reference_line(self):
        rows = []
        for i in range(30):
            hi = 200 - i if i in (2, 14) else 192 - i
            lo = 100 - i * .5 if i in (0, 12) else 108 - i * .5
            rows.append([(datetime(2026, 10, 20) + timedelta(days=i)).strftime("%m/%d"), 140, hi, lo, 141])
        anchors = {"hi1": ["10/22", "10/24"], "hi2": ["11/01", "11/10"],
                   "lo1": ["10/20", "10/22"], "lo2": ["11/01", "11/10"]}
        first = channel(rows, anchors, last_closed=True)
        rows[-1][2] *= 3
        rows[-1][3] *= .1
        second = channel(rows, anchors, last_closed=True)
        self.assertEqual(first["hi"], second["hi"])
        self.assertEqual(first["lo"], second["lo"])
        self.assertEqual(first["su"], second["su"])
        self.assertEqual(first["sl"], second["sl"])
        self.assertEqual(first["touch_required"], 2)

    def test_two_point_usable_channel_can_still_show_breakout_and_breakdown(self):
        ch = dict(channel_valid=True, channel_width_valid=True, up_now=100, lo_now=80, ma5=99, gap_next=0)
        self.assertEqual(state(ch, 105, False), "돌파 확인")
        self.assertEqual(state(ch, 105, True), "돌파 시도(장중)")
        self.assertEqual(state(ch, 79, False), "하단 이탈")

    def test_bad_data_and_settings_are_rejected(self):
        high, dates = values()
        high[4] = float("nan")
        self.assertIsNone(anchored_side(high, dates, 2, "10", 26, True))
        high, dates = values()
        with self.assertRaises(ValueError):
            anchored_side(high, dates, 2, "10", 26, True, tolerance_pct=8)

    def test_indices_stay_together_and_minimum_is_two(self):
        conf = json.loads((Path(__file__).resolve().parents[1] / "data" / "channels.json").read_text(encoding="utf-8"))
        self.assertEqual(conf["groups"][0]["items"], [["KOSPI", "코스피"], ["KOSDAQ", "코스닥"]])
        self.assertEqual(conf["contact_rules"]["min_touches"], 2)
        self.assertEqual(conf["contact_rules"]["method"], "fixed_two_anchor")


if __name__ == "__main__":
    unittest.main()
