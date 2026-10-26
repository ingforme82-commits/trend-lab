"""📋 시장 브리핑 — 카톡 리포트의 시장 부분을 사이트에도 (실시간 + 매일 12시 저장해 후속 확인)

- make(out): news.json 내용으로 브리핑 요약을 만든다(가장 큰 변곡점·섹터 강약·많이 나온 종목·해외 지수·화제 종목).
- save(brief): data/briefs.json 에 하루 한 번(12시 리포트 때) 저장한다. 최근 60일 보관.
사실·수치 요약만 담는다(해석·추천 없음).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIEFS = ROOT / "data" / "briefs.json"
KST = timezone(timedelta(hours=9))


def make(out: dict) -> dict:
    now = datetime.now(timezone.utc).timestamp() * 1000
    items = {it["ts"]: it for it in out.get("items", [])}
    mv = [m for m in out.get("moves", []) if now - m["start"] < 24 * 3600_000]
    top = sorted(mv, key=lambda m: -m.get("ratio", 0))[:3]
    moves = [{"name": m["name"], "asset": m["asset"], "move": m["move"], "unit": m["unit"], "start": m["start"], "end": m["end"],
              "ratio": m["ratio"], "news": [it["text"] for it in (m.get("items") or [items[t] for t in m.get("news", []) if t in items])][:1]}
             for m in top]
    sectors = []
    for c in out.get("sectors", []):
        rows = c.get("rows") or []
        if not rows:
            continue
        sectors.append({"name": c["name"], "icon": c.get("icon", ""), "avg": c["avg"],
                        "best": {"name": rows[0]["name"], "chg": rows[0]["chg"]}, "worst": {"name": rows[-1]["name"], "chg": rows[-1]["chg"]},
                        "flags": sum(1 for r in rows if r.get("flags"))})
    world = out.get("world", [])
    w = {"up": sum(1 for x in world if x["chg"] > 0), "down": sum(1 for x in world if x["chg"] < 0)}
    if world:
        b, k = max(world, key=lambda x: x["chg"]), min(world, key=lambda x: x["chg"])
        w.update(best={"name": b["name"], "chg": b["chg"]}, worst={"name": k["name"], "chg": k["chg"]})
    return {"at": int(now), "moves": moves, "trending": [{"name": t["name"], "n": t["n"]} for t in out.get("trending", [])[:5]],
            "sectors": sectors, "world": w, "spot": [{"name": s["name"], "chg": s.get("chg")} for s in out.get("spot", [])]}


def save(brief: dict) -> bool:
    """오늘(한국 날짜) 기록이 없으면 저장. 저장했으면 True."""
    day = datetime.now(KST).strftime("%Y-%m-%d")
    try:
        hist = json.loads(BRIEFS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        hist = []
    old = next((h for h in hist if h.get("day") == day), None)
    if old and datetime.fromtimestamp(old["at"] / 1000, KST).hour >= 11:
        return False                                      # 오늘 12시 기록이 이미 있음
    hist = [{"day": day, **brief}] + [h for h in hist if h.get("day") != day]   # 이른 시각 임시 기록은 12시 기록으로 바꾼다
    BRIEFS.write_text(json.dumps(hist[:60], ensure_ascii=False, indent=1), encoding="utf-8")
    return True
