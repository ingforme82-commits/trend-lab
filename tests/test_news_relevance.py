"""운영 피드에서 발견한 분류 누락·사회기사 유입 회귀 검사(외부 연결 없음)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from live_news import tags_of
from newsgroup import group, market_item


class RelevanceTest(unittest.TestCase):
    def test_semiconductor_entities(self):
        for title in ["엔비디아 수출 규제 완화", "젠슨황, CEO 복귀 논의", "Jensen Huang Discusses Comeback as Nvidia Chief With Allies, FT Says", "NVDA earnings", "AMD results", "Broadcom AI contracts"]:
            with self.subTest(title=title):
                self.assertIn("반도체", tags_of(title))

    def test_semiconductor_survives_two_tag_limit(self):
        self.assertIn("반도체", tags_of("WTI 급등·연준 금리, 엔비디아 실적 주목"))
        self.assertLessEqual(len(tags_of("WTI 급등·연준 금리, 엔비디아 실적 주목")), 2)

    def test_nonmarket_exam_news_removed_from_all_channels(self):
        headlines = ["세무사 시험장 AI 부정행위 처벌", "세무사 수석 합격 취소 수순", "AI 없는 수습세무사 평가", "국가자격시험 AI 안경 또 적발", "Korea’s Top Scorer in Tax Accountant Exam Admits to AI Cheating"]
        for title in headlines:
            for kind in ["뉴스", "시황 분석", "증권사 시황", "텔레그램"]:
                with self.subTest(title=title, kind=kind):
                    self.assertEqual(group([dict(ts=1, src="A", kind=kind, text=title, tags=["AI·빅테크"])]), [])

    def test_real_smart_glasses_market_story_kept(self):
        for title in ["메타 AI 안경 매출 증가", "삼성전자 AI 안경 부품 공급 계약", "세무사 시험 AI 안경 논란, 메타 주가 영향 분석"]:
            self.assertIsNotNone(market_item(dict(text=title, tags=["AI·빅테크"])))

    def test_cached_telegram_tags_repaired_without_mutation(self):
        item = dict(ts=1, src="A", kind="시황 분석", text="젠슨황, CEO 복귀 논의", tags=["시황"])
        self.assertIn("반도체", group([item])[0]["tags"])
        self.assertEqual(item["tags"], ["시황"])

    def test_translated_original_and_merged_tags(self):
        a = dict(ts=1, src="A", text="황 CEO 복귀 논의", orig="Nvidia chief discusses comeback", tags=["AI·빅테크", "연준·금리"])
        b = dict(a, ts=2, src="B")
        result = group([a, b])[0]
        self.assertIn("반도체", result["tags"])
        self.assertEqual(result["verify"], "unconfirmed")
        self.assertFalse(result["hot"])

    def test_unrelated_ai_and_amd_substrings_not_semiconductors(self):
        for title in ["OpenAI 서비스 출시", "Meta AI 안경 매출 증가", "Amsterdam bond market"]:
            self.assertNotIn("반도체", tags_of(title))


if __name__ == "__main__":
    unittest.main()
