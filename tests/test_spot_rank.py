"""🔥 종목군 매분 정리."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from spot_rank import renew  # noqa: E402

NOW = 1_794_700_000_000
N = lambda t: {"ts": NOW - 3600_000, "text": t}  # noqa: E731


def spots():
    return [
        {"id": "AMD", "name": "AMD", "kw": r"AMD\(어드밴스드|Advanced|\bAMD\b", "kind": "⚡ 급락 대형주", "since": "2026-11-14", "chg": 1.2},
        {"id": "NU", "name": "누 홀딩스", "kw": r"누|Nu|\bNU\b", "kind": "⚡ 급등 대형주", "since": "2026-11-14", "chg": 0.0},
        {"id": "SKYD", "name": "스카이댄스", "kw": "스카이댄스|Skydance", "kind": "⚡ 급락 대형주", "since": "2026-11-11", "chg": -0.9},
        {"id": "USSEMI", "name": "미국 반도체", "kw": "엔비디아|반도체", "members": [{"sym": "AMD"}, {"sym": "NVDA"}], "avg": True,
         "chg": 3.9, "reason": "평균 -4.22%"},
        {"id": "ENERGY", "name": "정유·에너지", "kw": "유가", "members": [{"sym": "XOM"}], "avg": True, "chg": 1.1, "kind": "📈 연일 상승",
         "reason": "4일 연속 상승"},
        {"id": "ASIA", "name": "한국·일본 증시", "pin": True, "members": [], "reason": "11/2 마감 …"},
    ]


class SpotRankTest(unittest.TestCase):
    def test_cleanup(self):
        items = [N("Nuclear power stocks rally"), N("Nu Skin earnings"), N("엔비디아 하락에 반도체 약세")]
        kr = {"KOSPI": {"px": 5290.53, "chg": -0.98, "at": NOW, "open": False, "xc": "3/3"}, "SMSN": {"chg": 0.48}}
        out = renew(spots(), items, kr, [{"name": "니케이225", "chg": 0.53}], pool={"AMD", "NVDA", "XOM"}, now_ms=NOW)
        ids = [s["id"] for s in out]
        self.assertNotIn("AMD", ids)                       # 미국 반도체에 합침
        self.assertIn("포함: AMD", out[ids.index("USSEMI")]["reason"])
        self.assertTrue(out[ids.index("USSEMI")]["reason"].startswith("선정 당시"))
        self.assertNotIn("NU", ids)                        # 관심 종목군 밖·관련 속보 부족('Nuclear' 속 Nu는 안 셈)
        self.assertNotIn("SKYD", ids)                      # 이전 선정일
        self.assertEqual(ids[-1], "ASIA")                  # pin 맨 뒤
        self.assertIn("코스피 5,290.53(-0.98%)", out[-1]["reason"])
        self.assertIn("증권사 3/3 일치", out[-1]["reason"])
        self.assertEqual(ids[0], "USSEMI")                 # 상승폭 큰 순


if __name__ == "__main__":
    unittest.main()


class RisingOnlyTest(unittest.TestCase):
    def test_large_decline_and_zero_are_not_leading_groups(self):
        candidates = [
            {"id":"QUANTUM","name":"양자컴퓨팅","members":[{"sym":"Q"}],"avg":True,"chg":-8.0},
            {"id":"FLAT","name":"보합","members":[{"sym":"F"}],"avg":True,"chg":0.0},
            {"id":"UP","name":"강세","members":[{"sym":"U"}],"avg":True,"chg":1.2}]
        result = renew(candidates,[],pool={"Q","F","U"},now_ms=NOW)
        self.assertEqual([x["id"] for x in result],["UP"])
