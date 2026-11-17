import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from channel_fit import fit_side, fit_recent_side
from chan import channel, state


def side_values():
    values = [200 - 2 * i - 8 for i in range(28)]
    for i in (2, 8, 14, 20):
        values[i] = 200 - 2 * i
    return values, [f"{i:02d}" for i in range(28)]


def market_rows():
    rows = []
    for i in range(32):
        hi = 200 - i if i in (2, 8, 14, 20, 26) else 192 - i
        lo = 100 - i * .5 if i in (0, 6, 12, 18, 24) else 108 - i * .5
        close = 150 - i * .8
        rows.append([(datetime(2026, 10, 20) + timedelta(days=i)).strftime("%m/%d"),
                     close - 1, hi, lo, close])
    anchors = {"hi1": ["10/22", "10/24"], "hi2": ["10/28", "11/10"],
               "lo1": ["10/20", "10/22"], "lo2": ["10/26", "11/10"]}
    return rows, anchors


class ContactTests(unittest.TestCase):
    def test_recent_pivots_can_replace_an_unsupported_old_anchor(self):
        values, days = side_values()
        values[2] *= 1.3
        result = fit_recent_side(values, days, 2, "08", 26, True)
        self.assertTrue(result["verified"])
        self.assertGreater(result["start"], 2)
        self.assertGreaterEqual(len(result["touches"]), 3)

    def test_crossed_lines_are_not_a_verified_channel_state(self):
        self.assertEqual(state({"channel_width_valid": False, "channel_valid": False}, 100., False), "채널선 교차·재확인")

    def test_three_or_more_independent_touches_verified(self):
        values, days = side_values()
        result = fit_side(values, days, 2, "08", 26, True)
        self.assertTrue(result["verified"])
        self.assertGreaterEqual(len(result["touches"]), 3)
        self.assertAlmostEqual(result["slope"], -2)
        self.assertTrue(all(b - a >= 3 for a, b in zip(result["touches"], result["touches"][1:])))

    def test_slight_overlap_is_allowed_but_strict_line_is_not(self):
        values, days = side_values()
        values[24] = (200 - 2 * 24) * 1.005
        soft = fit_side(values, days, 2, "08", 26, True, tolerance_pct=.75)
        strict = fit_side(values, days, 2, "08", 26, True, tolerance_pct=0)
        self.assertTrue(soft["verified"])
        self.assertLessEqual(soft["max_overlap_pct"], .75)
        self.assertFalse(strict["verified"])

    def test_large_historical_penetration_is_not_accepted(self):
        values, days = side_values()
        values[24] = (200 - 2 * 24) * 1.08
        result = fit_side(values, days, 2, "08", 26, True)
        self.assertFalse(result["verified"])

    def test_one_flat_plateau_is_not_two_independent_touches(self):
        values = [90.] * 22
        values[0] = 100.
        values[5:13] = [100.] * 8
        result = fit_side(values, [f"{i:02d}" for i in range(22)], 0, "05", 20, True)
        self.assertFalse(result["verified"])
        self.assertLess(len(result["touches"]), 3)

    def test_current_bar_is_not_used_to_find_the_third_touch(self):
        values = [90.] * 22
        values[0] = values[6] = values[20] = 100.
        days = [f"{i:02d}" for i in range(22)]
        result = fit_side(values, days, 0, "05", 19, True)
        self.assertFalse(result["verified"])
        self.assertNotIn(20, result["touches"])

    def test_two_touches_stay_unverified_and_do_not_confirm_breakout(self):
        values = [90.] * 22
        values[0] = values[6] = 100.
        result = fit_side(values, [f"{i:02d}" for i in range(22)], 0, "05", 20, True)
        self.assertFalse(result["verified"])
        self.assertEqual(state({"channel_valid": False}, 999., False), "접촉 검증 대기")

    def test_channel_requires_both_sides_three_touches(self):
        rows, anchors = market_rows()
        result = channel(rows, anchors, last_closed=True)
        self.assertTrue(result["channel_valid"])
        self.assertGreaterEqual(len(result["hi"]), 3)
        self.assertGreaterEqual(len(result["lo"]), 3)
        self.assertTrue(result["channel_width_valid"])
        self.assertTrue(all(i < len(rows) - 1 for i in result["hi"] + result["lo"]))

    def test_in_progress_bar_cannot_move_a_valid_fitted_line(self):
        rows, anchors = market_rows()
        first = channel(rows, anchors)
        rows[-1][2] *= 10
        rows[-1][3] *= .1
        second = channel(rows, anchors)
        self.assertEqual(first["hi"], second["hi"])
        self.assertEqual(first["lo"], second["lo"])
        self.assertAlmostEqual(first["su"], second["su"])
        self.assertAlmostEqual(first["sl"], second["sl"])

    def test_invalid_data_and_settings_are_rejected(self):
        values, days = side_values()
        values[10] = float("nan")
        self.assertIsNone(fit_side(values, days, 2, "08", 26, True))
        values, days = side_values()
        with self.assertRaises(ValueError):
            fit_side(values, days, 2, "08", 26, True, tolerance_pct=5)

    def test_indices_share_one_group_in_kospi_kosdaq_order(self):
        config = json.loads((Path(__file__).resolve().parents[1] / "data" / "channels.json").read_text(encoding="utf-8"))
        self.assertEqual(config["groups"][0]["cc"], "kr_index")
        self.assertEqual(config["groups"][0]["items"], [["KOSPI", "코스피"], ["KOSDAQ", "코스닥"]])
        self.assertEqual(config["contact_rules"]["min_touches"], 3)


if __name__ == "__main__":
    unittest.main()
