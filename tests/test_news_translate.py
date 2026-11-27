import copy
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import news_translate as t

TITLE="Nvidia forecast lifts Nasdaq futures ahead of earnings"
KO="엔비디아 전망에 실적 발표 앞두고 나스닥 선물 상승"


class TranslationTests(unittest.TestCase):
    def test_detects_unlabelled_english_but_keeps_korean_ticker_headlines(self):
        self.assertTrue(t.needs_translation({"text":TITLE,"kind":"텔레그램"}))
        self.assertFalse(t.needs_translation({"text":"NVDA·TSM 실적 확인","lang":"ko"}))
        self.assertFalse(t.needs_translation({"text":"CPI 2.3%"}))

    def test_batch_ids_keep_articles_matched(self):
        with patch.object(t,"_get",return_value=[[["__TRL_0__ 첫 번째 번역\n__TRL_1__ 두 번째 번역","",None]]]):
            out=t.google_batch(["First headline for stock market","Second headline for stock market"])
        self.assertEqual(list(out.values()),["첫 번째 번역","두 번째 번역"])

    def test_batch_missing_reordered_or_repeated_ids_rejected(self):
        for out in ("__TRL_1__ 번역 __TRL_0__ 번역","__TRL_0__ 번역","__TRL_0__ 번역 __TRL_0__ 번역"):
            with patch.object(t,"_get",return_value=[[[out]]]):
                with self.assertRaises(ValueError):t.google_batch(["First headline for stock market","Second headline for stock market"])

    def test_korean_headline_with_english_names_is_not_translated(self):
        self.assertFalse(t.needs_translation({"text":"마이크론 CEO·CTO - TomorrowX Summit 발언"}))

    def test_broken_batch_retries_each_title_without_pausing_provider(self):
        titles=["First headline for stock market today","Second headline for stock market today"]
        items=[{"text":x,"lang":"en","ts":i} for i,x in enumerate(titles)]
        def fake(batch):
            if len(batch)>1: raise t.BatchShapeError("ids")
            return {batch[0]:"번역 "+batch[0][:5]}
        with tempfile.TemporaryDirectory() as folder,patch.object(t,"google_batch",side_effect=fake),patch.object(t,"memory_one",side_effect=AssertionError("fallback")):
            stats=t.run(items,path=Path(folder)/"c.json",now=1000)
        self.assertEqual([i["tr"] for i in items],["auto","auto"])
        self.assertNotIn("google",stats["provider_backoff_until"])

    def test_english_echo_and_quota_messages_are_not_success(self):
        self.assertFalse(t.valid_translation(TITLE,TITLE))
        self.assertFalse(t.valid_translation(TITLE,"MYMEMORY WARNING 한도 초과"))
        self.assertFalse(t.valid_translation(TITLE,None))

    def test_cache_survives_run_and_preserves_original_source_time(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"cache.json"
            item={"text":TITLE,"ts":123,"got":456,"src":"Reuters","lang":"en"}
            with patch.object(t,"google_batch",return_value={TITLE:KO}),patch.object(t,"memory_one",side_effect=AssertionError("fallback")):
                stats=t.run([item],path=p,now=1000)
            self.assertEqual(item["orig"],TITLE);self.assertEqual(item["text"],KO)
            self.assertEqual((item["ts"],item["got"],item["src"]),(123,456,"Reuters"))
            self.assertEqual(item["tr"],"auto");self.assertEqual(stats["translated"],1)
            repeat={"text":TITLE,"ts":123,"lang":"en"}
            with patch.object(t,"google_batch",side_effect=AssertionError("cache")):
                t.run([repeat],path=p,now=1061)
            self.assertEqual(repeat["text"],KO)

    def test_existing_translated_item_is_not_retranslated(self):
        item={"text":KO,"orig":TITLE,"tr":"auto","lang":"en","ts":1}
        with tempfile.TemporaryDirectory() as folder,patch.object(t,"google_batch",side_effect=AssertionError("already translated")):
            t.run([item],path=Path(folder)/"c.json",now=1000)
        self.assertEqual(item["text"],KO)

    def test_http429_backoff_and_bounded_fallback(self):
        error=urllib.error.HTTPError("https://provider.invalid",429,"rate limit",{},None)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"c.json"
            with patch.object(t,"google_batch",side_effect=error),patch.object(t,"memory_one",return_value=KO):
                item={"text":TITLE,"lang":"en","ts":1}
                stats=t.run([item],path=p,now=1000)
            self.assertEqual(item["tr_provider"],"mymemory")
            self.assertEqual(stats["errors"],{"google:HTTP_429":1})
            self.assertEqual(stats["provider_backoff_until"]["google"],1600)

    def test_memory_daily_limit_is_never_exceeded(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"c.json";p.write_text(json.dumps({"policy":t.POLICY,
                "memory":{"day":"1970-01-01","chars":4790},"off":{"google":2000}}))
            with patch.object(t,"google_batch",side_effect=AssertionError("backoff")),patch.object(t,"memory_one",side_effect=AssertionError("daily limit")):
                item={"text":TITLE,"lang":"en","ts":1};stats=t.run([item],path=p,now=1000)
            self.assertEqual(item["tr"],"fail");self.assertEqual(stats["fallback_chars_today"],4790)
            self.assertEqual(item["orig"],TITLE)

    def test_retry_wait_does_not_slide_forever_on_short_poll_interval(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"c.json"
            with patch.object(t,"google_batch",side_effect=OSError()),patch.object(t,"memory_one",side_effect=OSError()):
                t.run([{"text":TITLE,"lang":"en","ts":1}],path=p,now=1000)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["retry"][TITLE],1060)
            with patch.object(t,"google_batch",side_effect=AssertionError("not due")),patch.object(t,"memory_one",side_effect=AssertionError("not due")):
                t.run([{"text":TITLE,"lang":"en","ts":1}],path=p,now=1055)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["retry"][TITLE],1060)

    def test_call_budget_shared_between_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"c.json";p.write_text(json.dumps({"policy":t.POLICY,"budget":{"start":1000,"calls":8}}))
            with patch.object(t,"google_batch",side_effect=AssertionError("budget")),patch.object(t,"memory_one",side_effect=AssertionError("budget")):
                item={"text":TITLE,"lang":"en","ts":1};stats=t.run([item],path=p,now=1010)
            self.assertEqual(stats["pending"],1)

    def test_valid_legacy_cache_migrates_without_paid_api(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"legacy.json";p.write_text(json.dumps({TITLE:KO,"_claude_off_until":123}))
            with patch.object(t,"google_batch",side_effect=AssertionError("legacy")):
                item={"text":TITLE,"lang":"en","ts":1}
                t.run([item],path=Path(folder)/"new.json",legacy_path=p,now=1000)
            self.assertEqual(item["text"],KO)

    def test_translation_failure_is_explicit_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(t,"google_batch",side_effect=OSError()),patch.object(t,"memory_one",side_effect=OSError()):
                item={"text":TITLE,"lang":"en","ts":1}
                stats=t.run([item],path=Path(folder)/"c.json",now=1000)
            self.assertEqual(item["text"],TITLE)
            self.assertEqual(item["tr_status"],"retry_pending")
            self.assertEqual(stats["pending"],1)

    def test_live_pipeline_translates_before_grouping_all_sources(self):
        source=(Path(__file__).resolve().parents[1]/"tools/live_news.py").read_text(encoding="utf-8")
        self.assertIn("translate(rss + tg_items + kis_items)",source)
        self.assertLess(source.index("translate(rss + tg_items + kis_items)"),source.index("allitems = group("))
        self.assertNotIn("translate(rss)\n",source)


    def test_retry_after_is_honored_and_error_remains_observable(self):
        error=urllib.error.HTTPError("https://provider.invalid",429,"limit",{"Retry-After":"1200"},None)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"c.json"
            with patch.object(t,"google_batch",side_effect=error),patch.object(t,"memory_one",return_value=KO):
                stats=t.run([{"text":TITLE,"lang":"en","ts":1}],path=p,now=1000)
            self.assertEqual(stats["provider_backoff_until"]["google"],2200)
            with patch.object(t,"google_batch",side_effect=AssertionError("paused")):
                stats=t.run([{"text":TITLE,"lang":"en","ts":1}],path=p,now=1061)
            self.assertEqual(stats["last_errors"]["google"]["code"],"HTTP_429")

    def test_crosscheck_obeys_the_same_provider_backoff_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"c.json"
            p.write_text(json.dumps({"policy":t.POLICY,"off":{"google":2000}}))
            with patch.object(t,"_get",side_effect=AssertionError("network forbidden")):
                with self.assertRaises(RuntimeError):
                    t.google_search_one("한국어 기사 제목",path=p,now=1000)

    def test_crosscheck_reserves_shared_budget_and_cache_is_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"c.json"
            p.write_text(json.dumps({"policy":t.POLICY,"budget":{"start":1000,"calls":7}}))
            with patch.object(t,"_get",return_value=[[["Nvidia earnings improve the market"]]]):
                first=t.google_search_one("엔비디아 실적",path=p,now=1010)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["budget"]["calls"],8)
            with patch.object(t,"_get",side_effect=AssertionError("cached or budget")):
                self.assertEqual(t.google_search_one("엔비디아 실적",path=p,now=1011),first)
                with self.assertRaises(RuntimeError):
                    t.google_search_one("다른 기사 제목",path=p,now=1011)

    def test_crosscheck_429_pauses_headline_translation_too(self):
        error=urllib.error.HTTPError("https://provider.invalid",429,"limit",{},None)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"c.json"
            with patch.object(t,"_get",side_effect=error):
                with self.assertRaises(urllib.error.HTTPError):
                    t.google_search_one("엔비디아 실적",path=p,now=1000)
            with patch.object(t,"google_batch",side_effect=AssertionError("same global pause")),patch.object(t,"memory_one",return_value=KO):
                item={"text":TITLE,"lang":"en","ts":1}
                t.run([item],path=p,now=1010)
            self.assertEqual(item["tr_provider"],"mymemory")


if __name__=="__main__":unittest.main()
