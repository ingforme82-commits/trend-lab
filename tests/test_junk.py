import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from live_news import JUNK  # noqa: E402


class JunkTest(unittest.TestCase):
    def test_promo_blocked(self):
        for t in ["✅ 그로쓰리서치 IPO 채널 오픈 ✅ 저희가 이번에 개인 및 기관 투자자분들을 위한 IPO 전문 분석 채널을 오픈했습니다.",
                  "저희 채널에서 매일 시황을 정리합니다. 많은 관심 부탁드립니다",
                  "텔레그램 채널을 새로 오픈했습니다"]:
            self.assertTrue(JUNK.search(t), t)

    def test_news_kept(self):
        for t in ["오픈AI, 구글 TPU 구매 추진…엔비디아 의존도 낮추나",
                  "‘최대 2650조원’ 앤스로픽 상장 신청… “AI 인프라 1064조 투자”",
                  "Google은 클라우드 플레이북을 변경하여 더 많은 AI 칩을 판매하기 위해 파트너를 모집합니다",
                  "[마켓라이브] 코스피 6% 급등...10거래일 만에 6000선 마감",
                  "[단독] 보스턴다이내믹스, 아틀라스 1만대분 부품 발주…나무가·씨티알 등 참여",
                  "SK하이닉스 CEO \"저희는 HBM4 공급을 늘릴 계획\"",
                  "카카오, AI 서비스 정식 오픈"]:
            self.assertFalse(JUNK.search(t), t)


if __name__ == "__main__":
    unittest.main()
