"""📡 텔레그램 통합 정리 — 등록 채널 글을 주제별로 묶어 한눈에 (live_news 가 1분마다 호출)

- 재료: news.json 에 이미 실린 텔레그램 글만(목표주가·투자의견·추천 글은 live_news 에서 이미 빠짐).
- 최근 3시간(글이 적으면 12시간) → 주제(tags 첫 번째)별로 나누고,
  같은 내용(글자 2개씩 겹침 비율)이 여러 채널에 나오면 한 줄로 묶는다.
- 주제 순서: 언급한 채널 수 → 글 수. 줄 순서: 채널 수 → 중요도 → 최근.
- 채널 상태: 채널별 마지막 글 시각·수집 시각(수집이 멈췄는지 바로 보이게).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone

TG_KINDS = ("텔레그램", "시황 분석", "증권사 시황")
EXCLUDE = {"김치터미널"}        # 해외 속보 채널은 '전체 속보'에 이미 다 실림 — 통합 정리는 리서치·시황 방 위주
WIN_H, WIN_H_QUIET = 3, 18
CHAT = re.compile(r"ㅋㅋ|ㅎㅎ|ㅠㅠ|^.{0,30}[?？]\s*$")   # 잡담 한 줄은 빼기
TOPICS_MAX, LINES_MAX = 8, 3


def _norm(t: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t or "").lower()


def _grams(t: str) -> set[str]:
    s = _norm(t)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _same(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.5


def _clusters(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for it in sorted(items, key=lambda x: x["ts"]):
        g = _grams(it["text"])
        for c in out:
            if _same(g, c["g"]):
                c["items"].append(it)
                break
        else:
            out.append({"g": g, "items": [it]})
    res = []
    for c in out:
        its = c["items"]
        srcs = list(dict.fromkeys(i["src"] for i in its))
        best = max(its, key=lambda i: (i.get("imp", 0), len(i["text"])))
        res.append({"text": best["text"], "sub": best.get("sub", ""), "srcs": srcs, "n": len(its),
                    "first": its[0]["ts"], "last": its[-1]["ts"], "imp": max(i.get("imp", 0) for i in its),
                    "hot": any(i.get("hot") for i in its)})
    res.sort(key=lambda c: (-len(c["srcs"]), -c["imp"], -c["last"]))
    return res


def channel_status(db_path, names: dict[str, str]) -> list[dict]:
    """채널별 마지막 글·수집 시각(ms). 사이트에 '멈춘 채널'이 바로 보이게."""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        rows = con.execute(
            "select channel_username, max(posted_at), max(collected_at) from messages group by channel_username").fetchall()
        con.close()
    except Exception:  # noqa: BLE001
        return []
    ms = lambda s: int(datetime.fromisoformat(s).astimezone(timezone.utc).timestamp() * 1000) if s else None  # noqa: E731
    out = [{"name": names.get(u, u), "post": ms(p), "got": ms(c)} for u, p, c in rows if u in names]
    return sorted(out, key=lambda r: -(r["post"] or 0))


def build(items: list[dict], now_ms: int, db_path=None, names: dict[str, str] | None = None,
          polled_ms: int | None = None) -> dict:
    tg = [dict(i, text=re.sub(r"^\s*<\s*", "", i["text"])) for i in items
          if i.get("kind") in TG_KINDS and i.get("text") and i.get("src") not in EXCLUDE and not CHAT.search(i["text"])]
    win = WIN_H
    pick = [i for i in tg if now_ms - i["ts"] <= win * 3600e3]
    if len(pick) < 15:
        win = WIN_H_QUIET
        pick = [i for i in tg if now_ms - i["ts"] <= win * 3600e3]
    by: dict[str, list[dict]] = {}
    for it in pick:
        by.setdefault((it.get("tags") or ["기타"])[0], []).append(it)
    topics = []
    for name, its in by.items():
        cl = _clusters(its)
        topics.append({"name": name, "n": len(its), "ch": len({i["src"] for i in its}),
                       "lines": [{k: v for k, v in c.items() if k != "g"} for c in cl[:LINES_MAX]]})
    topics.sort(key=lambda t: (t["name"] == "기타", -t["ch"], -t["n"]))
    out = {"at": now_ms, "win_h": win, "n": len(pick), "ch": len({i["src"] for i in pick}),
           "topics": topics[:TOPICS_MAX]}
    if polled_ms:
        out["polled"] = polled_ms
    if db_path and names:
        out["channels"] = channel_status(db_path, names)
    return out


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from live_news import CHANNELS, DB
    j = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    d = build(j["items"], int(datetime.now(timezone.utc).timestamp() * 1000), DB, CHANNELS)
    print(f"창 {d['win_h']}시간 · 글 {d['n']} · 채널 {d['ch']}")
    for t in d["topics"]:
        print(f"■ {t['name']} 글 {t['n']} · 채널 {t['ch']}")
        for ln in t["lines"]:
            print(f"   - [{len(ln['srcs'])}채널 {ln['n']}건] {ln['text'][:90]}  ({', '.join(ln['srcs'][:4])})")
    print(len(d.get("channels", [])), "채널 상태")
