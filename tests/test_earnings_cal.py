import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import earnings_cal as e


def test_merge_states():
    fh = {"date": "2026-11-26"}
    assert e.merge(fh, {"dates": ["2026-11-26"], "est": False}, "2026-11-18")["check"] == "확정"
    m = e.merge(fh, {"dates": ["2026-12-01"], "est": False}, "2026-11-18")
    assert m["date"] == "2026-12-01" and m["check"].startswith("출처 다름")
    assert e.merge(fh, {"dates": ["2026-12-03"], "est": True}, "2026-11-18")["check"].startswith("추정")
    assert e.merge(fh, None, "2026-11-18")["check"] == "1곳(Finnhub)"


def test_merge_stale_yahoo():
    m = e.merge({"date": "2026-12-16"}, {"dates": ["2026-10-28"], "est": False}, "2026-11-18")
    assert m["date"] == "2026-12-16" and "지난 분기" in m["check"]


def test_kst_when_and_surprise():
    assert e.kst_when("2026-11-17", "amc") == "11/18 06시 이후"
    assert e.kst_when("2026-11-19", "bmo") == "11/19 밤 21~22시"
    assert e.kst_when("2026-11-24", "") == "시각 미정"
    assert e.surprise(3.86, 3.9542) == -2.4
    assert e.surprise(None, 1) is None
