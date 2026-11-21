import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import keystore  # noqa: E402
import linktitle as lt  # noqa: E402
import live_news as ln  # noqa: E402

URL = "https://n.news.naver.com/mnews/article/014/0005607482"


class Page:
    def __init__(self, body: bytes):
        self.body = body

    def read(self, n):
        return self.body


class LinkTitleRetry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "c.json"
        lt._state["left"] = 10

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, now, fail):
        def opener(req, timeout):
            if fail:
                raise OSError("dns")
            return Page(b'<meta property="og:title" content="Title here">')
        with patch.object(lt, "CACHE", self.cache), patch.object(lt.time, "time", lambda: now), \
             patch.object(lt.urllib.request, "urlopen", opener):
            return lt.title_for(URL)

    def test_failure_is_retried_later(self):
        self.assertIsNone(self.call(1000, fail=True))
        self.assertIsNone(self.call(1000 + 60, fail=False))          # 15분 전엔 다시 안 받음
        self.assertEqual(self.call(1000 + 16 * 60, fail=False)[0], "Title here")

    def test_legacy_none_retried(self):
        self.cache.write_text(json.dumps({URL: None}), encoding="utf-8")
        self.assertEqual(self.call(5, fail=False)[0], "Title here")

    def test_gives_up_after_max(self):
        t = 0
        for _ in range(lt.MAX_TRY):
            self.call(t, fail=True)
            t += 10 ** 6
        self.assertIsNone(self.call(t, fail=False))


class SectorAnalystLinks(unittest.TestCase):
    def test_daily_sector_note_kept(self):
        text = ("유안타 리서치센터\n데일리 섹터 News & Comments(11/20)_5\n\n■ 금융 우도형(02-3770-5589)\n"
                "▶글로벌 기업 주가\n- 하락: Morgan Stanley -3.4%\n"
                "금융권 해외 부동산 부실 우려\n- link: https://buly.kr/a\n- link: https://buly.kr/b\n- link: https://buly.kr/c\n"
                "유안타 리서치센터 기업분석팀 채널\nhttps://t.me/yuantaresearch\n")
        h, sub, _ = ln.clean_line(text, with_sub=True)
        self.assertTrue(h.startswith("데일리 섹터 News & Comments"), h)
        self.assertNotIn("link", sub)


class LocalBase(unittest.TestCase):
    def test_windows_without_localappdata(self):
        with patch.dict(keystore.os.environ, {"LOCALAPPDATA": ""}):
            self.assertEqual(keystore.local_base("nt"), Path.home() / "AppData" / "Local")


if __name__ == "__main__":
    unittest.main()
