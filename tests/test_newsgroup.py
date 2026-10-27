"""python -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from newsgroup import group, verify_of  # noqa: E402

M = 60_000


def it(ts, src, text, **kw):
    return {"ts": ts, "src": src, "text": text, "tags": kw.pop("tags", ["한국"]), "kind": kw.pop("kind", "텔레그램"), **kw}


class GroupTest(unittest.TestCase):
    def test_same_story_grouped_first_report_kept(self):
        a = it(0, "김치터미널", "한국 3분기 GDP 전분기 대비 1.0% 성장, 예상치 0.7% 상회")
        b = it(3 * M, "연합뉴스", "한국 3분기 GDP 전분기 대비 1.0% 성장 예상치 0.7% 상회", kind="뉴스")
        out = group([b, a])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["src"], "김치터미널")          # 최초 보도
        self.assertEqual(out[0]["ts"], 0)
        self.assertEqual(out[0]["also"], [{"src": "연합뉴스", "ts": 3 * M}])
        self.assertEqual(out[0]["verify"], "multi")
        self.assertEqual(out[0]["nsrc"], 2)

    def test_same_source_repeat_is_single(self):
        a = it(0, "김치터미널", "니케이 선물 장 초반 1.8% 상승")
        b = it(M, "김치터미널", "니케이 선물, 장 초반 1.8% 상승")
        out = group([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["verify"], "single")
        self.assertNotIn("also", out[0])

    def test_different_stories_not_grouped(self):
        out = group([it(0, "A", "니케이 선물 장 초반 1.8% 상승"), it(M, "B", "WTI 원유 선물 2% 하락, 재고 증가")])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["ts"], M)                       # 최신 먼저

    def test_window_limit(self):
        out = group([it(0, "A", "니케이 선물 장 초반 1.8% 상승"), it(7 * 60 * M, "B", "니케이 선물 장 초반 1.8% 상승")])
        self.assertEqual(len(out), 2)

    def test_rumor_unconfirmed_even_if_multi(self):
        a = it(0, "A", "소식통에 따르면 A사, B사 인수 협상 중")
        b = it(M, "B", "소식통에 따르면 A사 B사 인수 협상 중")
        self.assertEqual(group([a, b])[0]["verify"], "unconfirmed")
        self.assertEqual(verify_of([it(0, "X", "Apple reportedly plans new chip")]), "unconfirmed")

    def test_same_channel_different_osrc_is_single(self):
        a = it(0, "김치터미널", "OpenAI, 지수 시간 가설이 거짓임을 증명했다고 밝힘", osrc="OpenAI")
        b = it(M, "김치터미널", "OpenAI 지수 시간 가설이 거짓임을 증명했다고 밝힘")
        self.assertEqual(group([a, b])[0]["verify"], "single")

    def test_official(self):
        self.assertEqual(verify_of([it(0, "미 연준", "FOMC statement")]), "official")

    def test_sector_and_strat_not_grouped_or_verified(self):
        s1 = it(0, "섹터 시세 감시", "한국 반도체 섹터: 삼성전자 +5%", kind="섹터 시세")
        s2 = it(M, "섹터 시세 감시", "한국 반도체 섹터: 삼성전자 +5%", kind="섹터 시세")
        out = group([s1, s2])
        self.assertEqual(len(out), 2)
        self.assertNotIn("verify", out[0])

    def test_input_not_mutated(self):
        a = it(0, "A", "니케이 선물 장 초반 1.8% 상승")
        group([a, it(M, "B", "니케이 선물 장 초반 1.8% 상승")])
        self.assertNotIn("also", a)

    def test_tags_merge_drop_etc(self):
        a = it(0, "A", "니케이 선물 장 초반 1.8% 상승", tags=["기타"])
        b = it(M, "B", "니케이 선물 장 초반 1.8% 상승", tags=["지수"])
        self.assertEqual(group([a, b])[0]["tags"], ["지수"])


if __name__ == "__main__":
    unittest.main()
