import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import chan
import session_chan as s
from test_chan import A, rows

NOW = datetime(2026, 11, 17, 8, 10, tzinfo=s.KST)


def kr_quote(now=NOW):
    return {"datas": [{"itemCode": "005930", "marketStatus": "PREOPEN",
        "closePriceRaw": "150", "localTradedAt": now.isoformat(),
        "overMarketPriceInfo": {"tradingSessionType": "PRE_MARKET", "overMarketStatus": "OPEN",
            "overPrice": "175", "localTradedAt": now.isoformat()},
        "integratedPriceInfo": {"openPrice": "170", "highPrice": "180", "lowPrice": "165"}}]}


def us_data(day="2026-11-17", regular_end="16:00"):
    def at(day, hm):
        return datetime.fromisoformat(day+"T"+hm).replace(tzinfo=s.NY).timestamp()
    points = [(at("2026-11-16", "16:05"), [300, 310, 290, 305]),
              (at(day, "08:00"), [100, 103, 99, 102]),
              (at(day, "10:00"), [102, 108, 101, 106]),
              (at(day, "16:05"), [106, 109, 105, 107])]
    return {"timestamp": [p[0] for p in points],
        "indicators": {"quote": [{key: [p[1][i] for p in points]
            for i,key in enumerate(("open","high","low","close"))}]},
        "meta": {"currentTradingPeriod": {
            "pre": {"start":at(day,"04:00"),"end":at(day,"09:30")},
            "regular": {"start":at(day,"09:30"),"end":at(day,regular_end)},
            "post": {"start":at(day,regular_end),"end":at(day,"20:00")}}}}


class SessionTests(unittest.TestCase):
    def test_kr_pre_uses_real_integrated_ohlc(self):
        q=s.parse_kr(kr_quote(),NOW)["005930"]
        self.assertEqual(q["ohlc"],[170,180,165,175])
        self.assertEqual(q["session"],"NXT 프리")
        self.assertTrue(q["provider_open"])

    def test_kr_regular_does_not_reuse_old_pre_quote(self):
        now=NOW.replace(hour=10)
        raw=kr_quote()
        d=raw["datas"][0]
        d.update(marketStatus="OPEN",closePriceRaw="174",localTradedAt=now.isoformat())
        d["overMarketPriceInfo"]["overMarketStatus"]="CLOSE"
        q=s.parse_kr(raw,now)["005930"]
        self.assertEqual(q["session"],"정규장")
        self.assertEqual(q["ohlc"][-1],174)

    def test_missing_integrated_ohlc_does_not_invent_flat_candle(self):
        raw=kr_quote(); raw["datas"][0]["integratedPriceInfo"]={}
        self.assertEqual(s.parse_kr(raw,NOW),{})

    def test_kr_old_day_naive_time_future_and_invalid_prices_rejected(self):
        for stamp in ((NOW-timedelta(days=1)).isoformat(),NOW.replace(tzinfo=None).isoformat(),
                      (NOW+timedelta(minutes=3)).isoformat()):
            raw=kr_quote();raw["datas"][0]["overMarketPriceInfo"]["localTradedAt"]=stamp
            self.assertEqual(s.parse_kr(raw,NOW),{})
        raw=kr_quote();raw["datas"][0]["overMarketPriceInfo"]["overPrice"]="Infinity"
        self.assertEqual(s.parse_kr(raw,NOW),{})

    def test_us_combines_same_day_pre_regular_post_only(self):
        now=datetime(2026,11,17,16,8,tzinfo=s.NY)
        q=s.parse_us(us_data(),now)
        self.assertEqual(q["ohlc"],[100,109,99,107])
        self.assertEqual(q["day"],"2026-11-17")
        self.assertEqual(q["session"],"애프터마켓")
        self.assertTrue(q["provider_open"])
        self.assertEqual(q["time_kind"],"1분봉 시작")

    def test_us_previous_session_is_not_live_in_new_session(self):
        raw=us_data()
        raw["timestamp"]=raw["timestamp"][:-1]
        for values in raw["indicators"]["quote"][0].values():values.pop()
        q=s.parse_us(raw,datetime(2026,11,17,16,8,tzinfo=s.NY))
        self.assertFalse(q["provider_open"])
        self.assertEqual(q["active_session"],"애프터마켓")

    def test_us_early_close_uses_provider_session_boundaries(self):
        raw=us_data(regular_end="13:00")
        q=s.parse_us(raw,datetime(2026,11,17,16,8,tzinfo=s.NY))
        self.assertTrue(q["provider_open"])
        self.assertEqual(q["session"],"애프터마켓")

    def test_us_dst_uses_new_york_not_fixed_est(self):
        q=s.parse_us(us_data(day="2026-06-17"),datetime(2026,6,17,16,8,tzinfo=s.NY))
        self.assertEqual(datetime.fromtimestamp(q["source_at"]/1000,s.KST).hour,5)
        self.assertTrue(chan._open_now("us",datetime(2026,6,17,22,35,tzinfo=s.KST)))
        self.assertFalse(chan._open_now("us",datetime(2026,6,18,5,0,tzinfo=s.KST)))

    def test_display_appends_pre_day_without_mutating_regular_rows(self):
        regular=rows(); original=copy.deepcopy(regular)
        q=s.parse_kr(kr_quote(),NOW)["005930"]
        view=s.display(regular,q,A,{},now=NOW,channel=chan.channel,candle=chan.candle,state=chan.state)
        self.assertEqual(regular,original)
        self.assertEqual(view["rows"][-1],["11/17",170,180,165,175])
        self.assertEqual(view["px"],175)
        self.assertEqual(view["ma5"],155)
        self.assertFalse(view["signal_eligible"])
        self.assertNotEqual(view["state"],"돌파 확인")

    def test_stale_rechecked_against_source_not_query_time(self):
        q=s.parse_kr(kr_quote(),NOW)["005930"]
        q["checked_at"]=int((NOW+timedelta(minutes=10)).timestamp()*1000)
        view=s.display(rows(),q,A,{},now=NOW+timedelta(minutes=10),
            channel=chan.channel,candle=chan.candle,state=chan.state)
        self.assertTrue(view["stale"]);self.assertFalse(view["live"])
        self.assertEqual(view["state"],"자료 확인 중")

    def test_closed_session_last_quote_is_not_live_or_confirmed(self):
        q=s.parse_kr(kr_quote(),NOW)["005930"];q["provider_open"]=False
        view=s.display(rows(),q,A,{},now=NOW+timedelta(hours=13),
            channel=chan.channel,candle=chan.candle,state=chan.state)
        self.assertFalse(view["live"]);self.assertNotEqual(view["state"],"돌파 확인")
        self.assertIn("마감",view["quality_note"])

    def test_malformed_ohlc_and_older_day_do_not_roll_back_chart(self):
        q=s.parse_kr(kr_quote(),NOW)["005930"]
        q["ohlc"]=[]
        self.assertIsNone(s.display(rows(),q,A,{},now=NOW,channel=chan.channel,candle=chan.candle,state=chan.state))
        q["ohlc"]=[170,180,165,175];q["day"]="2026-11-13"
        self.assertIsNone(s.display(rows(),q,A,{},now=NOW,channel=chan.channel,candle=chan.candle,state=chan.state))

    def test_cache_hit_does_not_extend_ttl_or_replace_source_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"cache.json";p.write_text(json.dumps({"kr":{"t":100,"raw":kr_quote()}}))
            g=[{"cc":"kr","items":[["005930","fixture"]]}]
            with patch.object(s.time,"time",return_value=120),patch.object(s,"_request",side_effect=AssertionError("network")):
                result,errors=s.collect(g,NOW,p)
            self.assertFalse(errors)
            self.assertEqual(json.loads(p.read_text())["kr"]["t"],100)
            self.assertEqual(result["005930"]["checked_at"],100000)
            self.assertEqual(result["005930"]["source_at"],int(NOW.timestamp()*1000))

    def test_network_failure_isolated_and_not_served_as_fresh_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(s,"_request",side_effect=OSError("offline")):
                result,errors=s.collect([{"cc":"kr","items":[["005930","fixture"]]}],NOW,Path(folder)/"c.json")
            self.assertEqual(result,{})
            self.assertEqual(errors,["kr 확장세션 OSError"])

    def test_extension_breakout_does_not_change_regular_state_or_signals(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);cfg={"anchors":A,"rule":"fixture","groups":[
                {"cc":"kr","country":"한국","sector":"fixture","items":[["005930","fixture"]]}]}
            (p/"config.json").write_text(json.dumps(cfg),encoding="utf-8")
            # At least twenty bars for the existing build guard.
            regular=rows()+[["11/17",150,160,140,150]]
            q=s.parse_kr(kr_quote(),NOW)["005930"]
            with patch.object(chan,"CONF",p/"config.json"),patch.object(chan,"LOG",p/"log.json"), \
                 patch.object(chan,"bars",return_value=(regular,False)),patch.object(chan,"_nxt_quotes",return_value={}), \
                 patch.object(s,"collect",return_value=({"005930":q},[])):
                result=chan.build(NOW)
            item=result["groups"][0]["items"][0]
            self.assertEqual(item["px"],150)
            self.assertEqual(item["display"]["px"],175)
            self.assertEqual(result["signals"],[])
            self.assertNotEqual(item["display"]["state"],"돌파 확인")


if __name__=="__main__":
    unittest.main()


class IntegratedHistoryTests(unittest.TestCase):
    def test_us_history_includes_pre_and_after_for_each_day(self):
        quote = s.parse_us(us_data(), datetime(2026,11,17,16,8,tzinfo=s.NY))
        self.assertEqual(quote["history"],[
            {"day":"2026-11-16","ohlc":[300,310,290,305]},
            {"day":"2026-11-17","ohlc":[100,109,99,107]}])

    def test_previous_integrated_candle_replaces_regular_candle_without_mutation(self):
        regular = rows()
        original = copy.deepcopy(regular)
        q = s.parse_kr(kr_quote(),NOW)["005930"]
        q["history"] = [{"day":"2026-11-16","ohlc":[150,170,130,160]}]
        view = s.display(regular,q,A,{},now=NOW,channel=chan.channel,candle=chan.candle,state=chan.state)
        self.assertEqual(view["rows"][-2],["11/16",150,170,130,160])
        self.assertEqual(regular,original)
        self.assertEqual(view["integrated_history_days"],1)

    def test_archive_survives_a_day_rollover_and_uses_minute_us_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"cache.json"
            calls = []
            def fetch(url):
                calls.append(url)
                return kr_quote() if "naver" in url else {"chart":{"result":[us_data()]}}
            groups = [{"cc":"kr","items":[["005930","fixture"]]},
                      {"cc":"us","items":[["MU","fixture"]]}]
            with patch.object(s,"_request",side_effect=fetch):
                result, errors = s.collect(groups,NOW,path)
            self.assertFalse(errors)
            self.assertTrue(any("interval=1m" in url and "includePrePost=true" in url and "range=7d" in url for url in calls))
            saved = json.loads(path.read_text())
            self.assertIn("2026-11-17",saved["_history"]["005930"])
            # 다음 거래일 수집: 전날 통합 OHLC는 유지한다.
            next_now = NOW + timedelta(days=1)
            with patch.object(s.time,"time",return_value=10**10),patch.object(s,"_request",return_value=kr_quote(next_now)):
                result, errors = s.collect(groups[:1],next_now,path)
            self.assertFalse(errors)
            self.assertEqual([h["day"] for h in result["005930"]["history"]],["2026-11-17","2026-11-18"])
