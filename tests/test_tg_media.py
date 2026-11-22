"""텔레 링크·첨부 글자·분류 오류·주말 쉼 (dev-20261122-1500). 외부 연결·텔레그램 API·tesseract 실행 없음(모두 가짜)."""
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import live_news as ln  # noqa: E402
import media_text as mt  # noqa: E402
import tg_digest as td  # noqa: E402

KST = timezone(timedelta(hours=9))
NAVER = "https://n.news.naver.com/mnews/article/001/0015000000"


def fake_pdf(path: Path, lines: list[str]) -> None:
    """글자 있는 최소 PDF(영문 — 기본 글꼴). pypdf 가 읽을 수 있는 xref 포함."""
    body = "BT /F1 12 Tf 72 720 Td " + " ".join(f"({t}) Tj 0 -16 Td" for t in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(body)} >>\nstream\n{body}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    path.write_bytes(out)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "tgr.sqlite3"
        p = [patch.object(ln, "DB", self.db), patch.object(mt, "CACHE_DB", self.dir / "media_text.sqlite3"),
             patch.object(ln, "log", lambda *_: None)]
        for x in p:
            x.start()
            self.addCleanup(x.stop)
        mt._status.clear()
        self.addCleanup(mt._status.clear)

    def tearDown(self):
        self.tmp.cleanup()

    def make_db(self, rows):
        """rows = [(채널, 본문, media_type, media_path)]"""
        con = sqlite3.connect(self.db)
        con.execute("create table if not exists messages (channel_username text, posted_at text, text text, collected_at text, "
                    "media_type text, media_path text)")
        now = datetime.now(timezone.utc) - timedelta(minutes=5)
        con.executemany("insert into messages values (?,?,?,?,?,?)",
                        [(c, (now + timedelta(seconds=i)).isoformat(), t, now.isoformat(), m, p) for i, (c, t, m, p) in enumerate(rows)])
        con.commit()
        con.close()

    def image(self, name="a.jpg"):
        p = self.dir / name
        p.write_bytes(b"\xff\xd8fakejpeg" + name.encode())
        return str(p)


class Tags(unittest.TestCase):
    def test_blackpink_jisoo_not_index(self):
        self.assertNotIn("지수", ln.tags_of("블랙핑크 지수, 공항 패션 화보 같은 미모"))
        self.assertTrue(ln.NONMKT.search("블랙핑크 지수, 공항 패션 화보 같은 미모"))      # RSS 에서는 연예 기사로 빠짐

    def test_cyber_lobby_not_security(self):
        self.assertNotIn("사이버보안", ln.tags_of("[현장에서] 사이버 객장에서 만난 '삼전 20층' 개미"))
        self.assertNotIn("사이버보안", ln.tags_of("외국인 자금 유출 지속, 보안 검색대 앞 인파"))

    def test_existing_topics_kept(self):
        self.assertIn("지수", ln.tags_of("코스피 지수 2%↑"))
        self.assertIn("한국", ln.tags_of("코스피 지수 2%↑"))
        self.assertIn("지수", ln.tags_of("나스닥 선물 1% 하락"))
        self.assertIn("사이버보안", ln.tags_of("랜섬웨어 공격으로 공장 가동 중단"))
        self.assertIn("사이버보안", ln.tags_of("SK텔레콤 해킹 여파"))
        self.assertIn("AI·빅테크", ln.tags_of("메타플랫폼스 실적 발표"))
        self.assertIn("AI·빅테크", ln.tags_of("OpenAI IPO 준비"))

    def test_broad_words_removed(self):
        self.assertNotIn("AI·빅테크", ln.tags_of("증시 추가하락 시 정부 카드는 상장 요건 완화"))
        self.assertNotIn("AI·빅테크", ln.tags_of("메타버스 테마 약세"))
        self.assertNotIn("지수", ln.tags_of("추석 선물 세트 매출 증가"))

    # ── CTO 검증 보완(11/22): 실데이터 리허설에서 빠졌던 실제 기사 → 원래 주제 유지 ──
    def test_real_index_headlines_kept(self):
        for t in ["대만 벤치마크 지수 6% 이상 폭락", "독일 DAX 지수 2% 하락한 24,954.40 기록",
                  "일본 조기 거래: 10년물 국채(JGB) 선물 0.15포인트 상승; 니케이 225 선물 3.63% 하락",
                  '골드만삭스 "공포 지수 9점 육박"', "CATL, 항셍 테크 지수 편입 예정", "● 주요 지수 SSE 3,577.62pt (-0.3%)",
                  "CSI 300 지수 1% 상승", "영국 FTSE 100 반등", "유로 STOXX 50 약세", "대만 가권지수 급락",
                  "중국 베이징 50 지수, 거래 중 3% 급락.", "필리핀 증시 하락세 지속, 지수 5,360.19 터치",
                  "12월 KOSPI200·KOSDAQ150 정기변경 발표"]:
            with self.subTest(t=t):
                self.assertIn("지수", ln.tags_of(t))

    def test_economic_indicators_not_index(self):
        for t in ["CBS, 네덜란드 11월 소비자 신뢰지수 -32로 개선(10월 -34 대비)", "프랑스 기업 환경 지수(FRENCH BUSINESS CLIMATE) 실제치 95",
                  "캐나다 생산자물가지수(PPI) 전월 대비 0.3% 상승", "소비자 신뢰지수 상승", "미국 경기선행지수 하락", "경기종합지수 발표",
                  "프랑스 11월 기업 신뢰지수 95로 하락; 예상치 96 하회",
                  "PMI 지수 52.1", "상하이 주석 선물 하락세 지속",
                  "한소희, 금발의 韓 마릴린 먼로···흑발 블랙핑크 지수와 대비되는 화보"]:
            with self.subTest(t=t):
                self.assertNotIn("지수", ln.tags_of(t))

    def test_personal_data_leak_is_security(self):
        for t in ["한전, 고객 등 개인정보 150여만건 유출…", "한전, 개인정보 152만명분 유출", "사이버 취약점 경보 발령"]:
            with self.subTest(t=t):
                self.assertIn("사이버보안", ln.tags_of(t))
        for t in ["라이트 미국 에너지부 장관: 어제는 호르무즈 해협을 통한 유출 규모가 역대 최대였음",
                  "시리아 내부보안군, 레바논 밀수 목적의 무기 화물 압수"]:
            with self.subTest(t=t):
                self.assertNotIn("사이버보안", ln.tags_of(t))


class LinkPosts(Base):
    def test_link_title_post_topic_from_title(self):
        self.make_db([("realtime_stock_news", NAVER, "photo", None),
                      ("realtime_stock_news", f"속보 {NAVER}/2", "photo", None)])
        titles = {NAVER: ("독일 DAX 지수 2% 하락", "연합뉴스"), NAVER + "/2": ("한전, 개인정보 152만명분 유출", "뉴스1")}
        with patch.object(ln, "link_title", lambda u: titles[u]):
            out = ln.from_telegram()
        self.assertEqual({i["text"]: i["tags"][0] for i in out},
                         {"독일 DAX 지수 2% 하락": "지수", "한전, 개인정보 152만명분 유출": "사이버보안"})

    def test_short_words_plus_link_uses_article_title(self):
        self.make_db([("realtime_stock_news", f"속보 {NAVER}", "photo", None)])
        with patch.object(ln, "link_title", lambda u: ("코스피 장중 2% 급락, 외국인 1조 매도", "연합뉴스")):
            out = ln.from_telegram()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["text"], "코스피 장중 2% 급락, 외국인 1조 매도")
        self.assertEqual(out[0]["osrc"], "연합뉴스")
        self.assertEqual(out[0].get("sub"), "속보")
        self.assertNotIn("http", str(out[0]))
        self.assertEqual(ln.TG_STATS["실시간 주식뉴스"]["kept"], 1)

    def test_title_failure_counted_as_link_fail(self):
        self.make_db([("realtime_stock_news", f"속보 {NAVER}", "photo", None),
                      ("realtime_stock_news", NAVER, "photo", None)])
        with patch.object(ln, "link_title", lambda u: None):
            self.assertEqual(ln.from_telegram(), [])
        s = ln.TG_STATS["실시간 주식뉴스"]
        self.assertEqual((s.get("link_fail"), s.get("link_only"), s.get("short")), (1, 1, None))

    def test_long_post_with_link_unchanged(self):
        self.make_db([("realtime_stock_news", f"미 국채 10년물 금리 4.5% 돌파, 달러 강세 이어져 {NAVER}", "photo", None)])
        with patch.object(ln, "link_title", lambda u: self.fail("긴 글은 링크 제목을 받지 않는다")):
            out = ln.from_telegram()
        self.assertTrue(out[0]["text"].startswith("미 국채 10년물"))


OCR_TEXT = "11월 셋째 주 시장 정리\n외국인 반도체 순매수 전환, 코스피 4,000선 회복 시도\n|||~~ ##\n" + "긴 본문 문장 " * 200


class Media(Base):
    def run_ocr(self, out_text=OCR_TEXT, n=1):
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            class R:
                returncode = 0
                stdout = "kor\neng\n" if "--list-langs" in args else out_text.encode()
                stderr = ""
            return R()
        imgs = [self.image(f"{i}.jpg") for i in range(n)]
        self.make_db([("one_going", "", "photo", p) for p in imgs])
        with patch.object(mt.shutil, "which", lambda _: "/usr/bin/tesseract"), patch.object(mt.subprocess, "run", fake_run):
            h = mt.process([("ocr", p) for p in imgs])
        return h, [c for c in calls if "--list-langs" not in c]

    def test_no_tesseract_skips_quietly(self):
        p = self.image()
        self.make_db([("one_going", "", "photo", p)])
        with patch.object(mt.shutil, "which", lambda _: None):
            ln.prep_media()
            out = ln.from_telegram()
        self.assertEqual(ln.MEDIA_STATS["ocr"], "미설치")
        self.assertEqual(out, [])
        self.assertEqual(ln.TG_STATS["요약하는 고잉"]["media_wait"], 1)

    def test_ocr_title_and_one_line_only(self):
        h, calls = self.run_ocr()
        self.assertEqual((h["done_ocr"], h["fail"], len(calls)), (1, 0, 1))
        out = ln.from_telegram()
        self.assertEqual(len(out), 1)
        it = out[0]
        self.assertEqual(it["via"], "ocr")
        self.assertEqual(it["text"], "11월 셋째 주 시장 정리")
        self.assertTrue(it["sub"].startswith("외국인 반도체 순매수"))
        self.assertLessEqual(len(it["text"]), mt.TITLE_MAX)
        self.assertLessEqual(len(it["sub"]), mt.SUB_MAX)
        self.assertNotIn("긴 본문 문장 긴 본문", str(it))           # 본문 전문 없음
        self.assertEqual(ln.TG_STATS["요약하는 고잉"]["media_ocr"], 1)

    def test_cached_not_processed_twice(self):
        self.run_ocr()
        h, calls = self.run_ocr()
        self.assertEqual((h["done_ocr"], len(calls)), (0, 0))

    def test_per_run_cap(self):
        h, calls = self.run_ocr(n=5)
        self.assertEqual(len(calls), mt.MAX_OCR_PER_RUN)
        self.assertEqual(h["wait"], 5 - mt.MAX_OCR_PER_RUN)

    def test_target_price_in_image_excluded(self):
        self.run_ocr(out_text="삼성전자 실적 리뷰\n목표주가 12만원 상향, 투자의견 매수 유지\n")
        self.assertEqual(ln.from_telegram(), [])
        self.assertEqual(ln.TG_STATS["요약하는 고잉"]["stockrec"], 1)

    def test_report_channel_photo_not_ocr(self):
        self.assertIsNone(ln.media_kind("YoungTiger_stock", "photo"))
        self.assertIsNone(ln.media_kind("YoungTiger_stock", "pdf"))          # 증권사 리포트 PDF 채널 제외
        self.assertIsNone(ln.media_kind("one_going", "pdf"))
        self.assertEqual(ln.media_kind("HANAStrategy", "pdf"), "pdf")
        self.assertEqual(ln.media_kind("HANAStrategy", "photo"), "ocr")

    def test_headline_limits(self):
        t, s = mt.headline("가" * 300 + "\n" + "나" * 300)
        self.assertLessEqual(len(t), 80)
        self.assertLessEqual(len(s), 120)
        self.assertEqual(mt.headline("|||\n~~\n12\n2026.11.20\n"), ("", ""))


class Pdf(Base):
    def test_deadline_stops_after_page(self):
        class Page:
            def __init__(self, t):
                self.t = t

            def extract_text(self):
                return self.t

        class Reader:
            is_encrypted = False

            def __init__(self, _):
                self.pages = [Page("first page"), Page("second page")]
        p = self.dir / "d.pdf"
        p.write_bytes(b"%PDF-1.4")
        fake = type(sys)("pypdf")
        fake.PdfReader = Reader
        with patch.dict(sys.modules, {"pypdf": fake}):
            self.assertEqual(mt.pdf_text(str(p), deadline=0), "first page")          # 이미 지난 마감 → 첫 쪽만
            self.assertEqual(mt.pdf_text(str(p)), "first page\nsecond page")

    def test_strategy_pdf_first_pages(self):
        p = self.dir / "s.pdf"
        fake_pdf(p, ["Weekly Strategy: KOSPI rebound after foreign selling eases", "Semiconductor exports rose for a third month in November"])
        self.make_db([("HANAStrategy", "", "pdf", str(p))])
        if mt.pdf_status() != "정상":                 # pypdf 없는 환경: 조용히 건너뛰고 상태만
            ln.prep_media()
            self.assertEqual(ln.MEDIA_STATS["pdf"], "미설치")
            self.assertEqual(ln.from_telegram(), [])
            self.skipTest("pypdf 미설치 — 미설치 처리만 확인")
        ln.prep_media()
        self.assertEqual(ln.MEDIA_STATS["done_pdf"], 1)
        out = ln.from_telegram()
        self.assertEqual(out[0]["via"], "pdf")
        self.assertTrue(out[0]["text"].startswith("Weekly Strategy"))
        self.assertTrue(out[0]["sub"].startswith("Semiconductor exports"))

    def test_pdf_with_target_price_excluded(self):
        p = self.dir / "r.txt"                         # 수집기가 큰 PDF 대신 남긴 글자 파일(pdf_text_only)
        p.write_text("Company Note\nTarget price raised to 120,000 won\n목표주가 120,000원 투자의견 BUY\n", encoding="utf-8")
        self.make_db([("HANAStrategy", "", "pdf_text_only", str(p))])
        with patch.dict(mt._status, {"pdf": "정상"}):
            ln.prep_media()
        self.assertEqual(ln.from_telegram(), [])
        self.assertEqual(ln.TG_STATS["하나 주식전략"]["stockrec"], 1)


class WeekendRest(unittest.TestCase):
    def ms(self, *a):
        return int(datetime(*a, tzinfo=KST).timestamp() * 1000)

    def test_friday_evening_post_on_sunday(self):
        self.assertEqual(td.rest_label(self.ms(2026, 11, 20, 17, 15), self.ms(2026, 11, 22, 14, 0)), "주말 쉼")

    def test_stopped_before_friday_close_not_rest(self):
        self.assertIsNone(td.rest_label(self.ms(2026, 11, 19, 10, 0), self.ms(2026, 11, 22, 14, 0)))

    def test_weekday_no_label(self):
        self.assertIsNone(td.rest_label(self.ms(2026, 11, 20, 17, 15), self.ms(2026, 11, 23, 9, 0)))

    def test_channel_status_field(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "t.sqlite3"
            con = sqlite3.connect(db)
            con.execute("create table messages (channel_username text, posted_at text, collected_at text)")
            con.execute("insert into messages values ('realtime_stock_news', '2026-11-20T08:15:40+00:00', '2026-11-20T08:16:00+00:00')")
            con.execute("insert into messages values ('KimchiTerminal', '2026-11-22T02:26:00+00:00', '2026-11-22T02:26:10+00:00')")
            con.commit()
            con.close()
            st = td.channel_status(db, {"realtime_stock_news": "실시간 주식뉴스", "KimchiTerminal": "김치터미널"},
                                   self.ms(2026, 11, 22, 14, 0))
        self.assertEqual({r["name"]: r.get("rest") for r in st}, {"실시간 주식뉴스": "주말 쉼", "김치터미널": None})   # 오늘 글 있음 → 표시 안 함


if __name__ == "__main__":
    unittest.main()
