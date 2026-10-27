import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from importance import level, score  # noqa: E402
from linktitle import outlet_of, parse_meta  # noqa: E402


class ImportanceTest(unittest.TestCase):
    def test_analysis_explaining_rise_is_high(self):
        it = {"text": "하드웨어 상승 특히 네오클 급등 출발", "kind": "시황 분석", "tags": ["AI·빅테크"], "hot": True}
        self.assertEqual(level(score(it)), "상")

    def test_pivot_and_key_person(self):
        it = {"text": "트럼프: 베네수엘라산 원유 100만 배럴을 수입할 것", "kind": "텔레그램", "tags": ["중동·유가"], "pivot": True}
        self.assertGreaterEqual(score(it), 60)

    def test_misc_is_low(self):
        self.assertEqual(level(score({"text": "점심 메뉴 추천 받습니다", "kind": "텔레그램", "tags": ["기타"]})), "하")

    def test_curated_analysis_starts_mid(self):
        self.assertEqual(level(score({"text": "CXMT 증설과 장기계약 요청에 대한 생각입니다", "kind": "시황 분석", "tags": ["반도체"]})), "중")

    def test_bounds(self):
        it = {"text": "속보 트럼프 연준 금리 때문에 나스닥 3% 급락", "kind": "관전 포인트", "tags": ["지수"], "pivot": True, "hot": True,
              "verify": "official", "nsrc": 9, "xc": {"st": "ok"}}
        self.assertEqual(score(it), 100)


class LinkTitleTest(unittest.TestCase):
    def test_meta(self):
        page = '<html><head><meta property="og:site_name" content="한국경제"><meta property="og:title" content="[단독] 에코프로 &amp; 양극재"></head>'
        self.assertEqual(parse_meta(page), ("[단독] 에코프로 & 양극재", "한국경제"))
        self.assertEqual(parse_meta("<title>제목만 있는 페이지</title>"), ("제목만 있는 페이지", None))

    def test_outlet(self):
        self.assertEqual(outlet_of("https://www.hankyung.com/article/1"), "한국경제")
        self.assertEqual(outlet_of("https://n.news.naver.com/x", "매일경제"), "매일경제")
        self.assertEqual(outlet_of("https://unknown.example.com/a"), "unknown.example.com")


if __name__ == "__main__":
    unittest.main()
