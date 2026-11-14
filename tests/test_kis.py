"""한투 조회 모듈 + 뉴스 출처 연결."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import kis  # noqa: E402
import live_news  # noqa: E402
from newsgroup import group  # noqa: E402


class KisTest(unittest.TestCase):
    def setUp(self):
        self._nt = kis.news_titles

    def tearDown(self):
        kis.news_titles = self._nt

    def test_orders_blocked(self):
        for tr in ("TTTC0802U", "VTTC0802U", "CTSC9115R"):
            with self.assertRaises(PermissionError):
                kis.get("/uapi/domestic-stock/v1/trading/order-cash", tr, {})

    def test_market_news_kept_and_outlet_is_source(self):
        import time
        now = int(time.time() * 1000)
        kis.news_titles = lambda: [
            {"ts": now, "src": "연합뉴스", "text": "BofA \"연준, 다음 달부터 3회 연속 금리 인상\"…1월 전망 추가", "codes": []},
            {"ts": now, "src": "이데일리", "text": "퍼스트 내셔널, 보통주 분기 현금 배당 11.8% 인상…주당 0.19달러", "codes": []},
            {"ts": now, "src": "헤럴드경제", "text": "“맘껏 드세요” 복스런 신부, 행복한 결혼 장면인 줄 알았는데…숨은 ‘반전’", "codes": []},
        ]
        out = live_news.fetch_kis()
        self.assertEqual([x["src"] for x in out], ["연합뉴스"])
        self.assertEqual(out[0]["via"], "한투")

    def test_two_outlets_via_kis_verify_multi(self):
        a = {"ts": 0, "src": "연합뉴스", "kind": "뉴스", "text": "美 10월 도매물가 전년 대비 6.5% 상승 약 4년 만 최고치", "tags": ["연준·금리"], "hot": True}
        b = {"ts": 60_000, "src": "조선경제i", "kind": "뉴스", "text": "美 10월 도매물가 전년 대비 6.5% 상승… 약 4년 만 최고치", "tags": ["연준·금리"], "hot": True}
        g = group([a, b])[0]
        self.assertEqual(g["verify"], "multi")
        self.assertTrue(g["hot"])


if __name__ == "__main__":
    unittest.main()
