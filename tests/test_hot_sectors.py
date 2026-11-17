import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from hot_sectors import is_pref, pick  # noqa: E402

G = [{"kind": "theme", "no": 1, "name": "A", "avg": 1.0, "n": 10, "up": 6},
     {"kind": "theme", "no": 2, "name": "B", "avg": 6.0, "n": 5, "up": 5},
     {"kind": "theme", "no": 3, "name": "C", "avg": 0.5, "n": 10, "up": 3},
     {"kind": "industry", "no": 4, "name": "D", "avg": 1.0, "n": 10, "up": 3}]
M = {"111110": ["theme:1", "industry:4"], "222220": ["theme:1", "industry:4"], "333330": ["theme:3"], "444440": ["theme:3"]}
R = [{"code": "111110", "name": "가", "chg": 29.9, "val": 1e10}, {"code": "222220", "name": "나", "chg": 16.0, "val": 1e9},
     {"code": "333330", "name": "다", "chg": 14.0, "val": 1e9}, {"code": "444440", "name": "라", "chg": 150.0, "val": 1e9}]


def test_pick_rules():
    res = pick(G, M, R)
    names = [x["name"] for x in res]
    assert names[0] == "A" and res[0]["limit_n"] == 1 and res[0]["hot_n"] == 2
    assert res[0]["also"] == ["D"]          # 같은 급등 종목 묶음은 합침
    assert "B" in names                      # 평균 +5% 이상
    assert "C" not in names                  # 14% 는 급등 아님, 150% 는 이상치(신규 상장 등)


def test_none_when_quiet():
    assert pick(G[:1] + G[2:], M, [{"code": "111110", "name": "가", "chg": 16.0, "val": 0}]) == []


def test_pref():
    assert is_pref("계양전기우", "012205") and is_pref("동양2우B", "001527") and not is_pref("계양전기", "012200")
