import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import quote_xcheck as q
import ecos
import finnhub


def test_judge():
    assert q.judge(100, 100.4, 0, 60_000) == "일치"
    assert q.judge(100, 101, 0, 60_000) == "불일치"
    assert q.judge(100, 101, 0, 600_000) == "시차"
    assert q.judge(100, 101, 0, 0, 1.5) == "일치"


def test_kr_rows_before_ecos_update():
    kr = {"KOSPI": {"px": 4968.48, "prev": 5100.59}}
    r = q.kr_rows(kr, {"kospi": [("20261113", 5290.53), ("20261116", 5100.5)]})
    assert r[0]["res"] == "불일치" and r[0]["v"] == 5100.5


def test_kr_rows_after_ecos_update():
    kr = {"KOSPI": {"px": 4968.48, "prev": 5100.5}}
    r = q.kr_rows(kr, {"kospi": [("20261116", 5100.5), ("20261117", 4968.48)]})
    assert [x["res"] for x in r] == ["일치", "일치"]


def test_ecos_parse():
    js = {"StatisticSearch": {"row": [{"TIME": "20261117", "DATA_VALUE": "1335"}, {"TIME": "x", "DATA_VALUE": ""}]}}
    assert ecos.parse(js) == [("20261117", 1335.0)]


def test_finnhub_parse():
    assert finnhub.parse_quote({"c": 0}) is None
    assert finnhub.parse_quote({"c": 10, "dp": 1.234, "pc": 9.9, "h": 11, "l": 9, "t": 1})["chg"] == 1.23
    assert finnhub.surprise({"epsActual": 2.6, "epsEstimate": 2.5, "revenueActual": None, "revenueEstimate": 1}) == {"eps": 4.0, "rev": None}
