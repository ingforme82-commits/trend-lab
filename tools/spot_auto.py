"""🔥 오늘의 주요 종목군 자동 교체 — 미국 정규장 개장 30분 뒤(서머타임 23:00 / 해제 후 00:00 KST)에 실행.

  python tools/spot_auto.py            # 시간 창(개장 후 20~75분) 안일 때만 실행, data/site.json 고치고 push
  python tools/spot_auto.py --dry      # 시간과 상관없이 계산만 출력(기록·push 안 함)
  python tools/spot_auto.py --force    # 시간 창 밖이어도 실행
  python tools/spot_auto.py --last     # 주말·휴장일에 직전 거래일 마감 기준으로 바로 교체

- 후보: data/spot_pool.json 의 종목군(미국). 야후 5분봉으로 전일 종가 대비·개장 후 등락을 계산한다.
- 점수 = |평균 등락| × (0.5 + 같은 방향 종목 비율) + 개장 후 |평균 등락| × 0.5 + 관련 속보 수(최근 12시간, 최대 10) × 0.15
- 상위 3개를 켜고, 나머지 자동 종목군은 끈다. pin 이 있는 종목군(한국·일본 등)은 건드리지 않는다.
- 📈 연일 상승: 종목군 평균 일간 등락이 3일 이상 연속 플러스인 종목군 1개(연속 일수·5일 합계 순)를 더한다.
- ⚡ 급등락 대형주: 미국 시가총액 상위 600종목(네이버, tools/leaders.us) 중 시총 300억 달러 이상·|등락| 5% 이상을
  등락 폭 순으로 최대 3개(한 방향 최대 2개) 개별 종목 카드로 더한다. 관련 속보는 화면에서 카드에 자동으로 붙는다.
- 선정 이유(reason)는 수치로만 자동 작성한다(해석·추천 없음).
- 미국 휴장일(정규장 시세가 오늘 것이 아님)이면 바꾸지 않는다.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "data" / "site.json"
POOL = ROOT / "data" / "spot_pool.json"
LOG = ROOT / "tools" / "spot_auto.log"
KST = timezone(timedelta(hours=9))
PICK = 3
BIG_MCAP, BIG_CHG, N_BIG = 3e10, 5.0, 3
REPO = "ingforme82-commits/trend-lab"


def log(msg: str) -> None:
    line = f"{datetime.now(KST):%m-%d %H:%M:%S} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def ny_now(now: datetime | None = None) -> datetime:
    from zoneinfo import ZoneInfo
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))


def in_window(now: datetime) -> bool:
    """미국 평일 정규장 개장(09:30 ET) 후 20~75분."""
    ny = ny_now(now)
    m = ny.hour * 60 + ny.minute - (9 * 60 + 30)
    return ny.weekday() < 5 and 20 <= m <= 75


def _yq(sym: str) -> dict | None:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range=1d&interval=5m"
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=12).read())["chart"]["result"][0]
        m, q = r["meta"], r["indicators"]["quote"][0]
        opens = [o for o in (q.get("open") or []) if o]
        return {"px": m.get("regularMarketPrice"), "prev": m.get("chartPreviousClose"), "open": opens[0] if opens else None,
                "at": (m.get("regularMarketTime") or 0) * 1000}
    except Exception:  # noqa: BLE001
        return None


# ── 순수 함수(tests/test_spot_auto.py) ──
def stats(members: dict[str, str], q: dict[str, dict | None], today_ny: str) -> dict | None:
    rows = []
    for sym, name in members.items():
        d = q.get(sym)
        if not d or not d.get("px") or not d.get("prev"):
            continue
        if datetime.fromtimestamp(d["at"] / 1000, timezone.utc).astimezone(ny_now().tzinfo).strftime("%Y-%m-%d") != today_ny:
            continue                                                   # 오늘 정규장 시세가 아님(휴장·거래정지)
        rows.append({"name": name, "chg": (d["px"] / d["prev"] - 1) * 100, "op": (d["px"] / d["open"] - 1) * 100 if d.get("open") else 0.0})
    if len(rows) < max(2, len(members) // 2):
        return None
    avg = sum(r["chg"] for r in rows) / len(rows)
    same = sum(1 for r in rows if (r["chg"] > 0) == (avg > 0)) / len(rows)
    best = max(rows, key=lambda r: r["chg"] if avg > 0 else -r["chg"])
    return {"avg": round(avg, 2), "op": round(sum(r["op"] for r in rows) / len(rows), 2), "same": same, "n": len(rows),
            "k": sum(1 for r in rows if (r["chg"] > 0) == (avg > 0)), "best": {"name": best["name"], "chg": round(best["chg"], 2)}}


def streak(series: list[float]) -> int:
    """일간 평균 등락 목록(오래된 → 최근) 끝에서부터 연속 플러스 일수."""
    n = 0
    for v in reversed(series):
        if v <= 0:
            break
        n += 1
    return n


def group_daily(members: dict[str, str], daily: dict[str, dict | None]) -> list[float]:
    """종목군 구성 종목의 일간 등락(%) 평균 — 모든 종목에 공통인 날짜만."""
    rows = [daily[s] for s in members if daily.get(s)]
    if len(rows) < max(2, len(members) // 2):
        return []
    days = sorted(set.intersection(*(set(r) for r in rows)))
    return [sum(r[d] for r in rows) / len(rows) for d in days]


def big_movers(stocks: list[dict], n: int = N_BIG) -> list[dict]:
    """시총 BIG_MCAP 이상·|등락| BIG_CHG 이상 종목을 등락 폭 순으로, 한 방향 최대 2개."""
    c = sorted((s for s in stocks if s.get("mcap", 0) >= BIG_MCAP and abs(s.get("chg", 0)) >= BIG_CHG), key=lambda s: -abs(s["chg"]))
    out, up, dn = [], 0, 0
    for s in c:
        if (s["chg"] > 0 and up >= 2) or (s["chg"] < 0 and dn >= 2):
            continue
        out.append(s)
        up, dn = up + (s["chg"] > 0), dn + (s["chg"] < 0)
        if len(out) >= n:
            break
    return out


def single_entry(s: dict, label: str, hl_ok: set[str]) -> dict:
    """급등락 대형주 → spotlight 개별 종목 항목(사실만)."""
    ko = re.escape((s.get("name") or s["sym"]).split()[0])
    en = re.escape(s["eng"].split()[0]) if s.get("eng") else ""
    kw = "|".join(x for x in [ko, en, r"\b" + re.escape(s["sym"]) + r"\b"] if x)
    e = {"id": s["sym"], "name": s.get("name") or s["sym"], "market": "미국", "yf": s["sym"], "kw": kw,
         "kind": "⚡ 급등 대형주" if s["chg"] > 0 else "⚡ 급락 대형주",
         "reason": f"{label} {s['chg']:+.2f}% · 시가총액 약 {round(s['mcap'] / 1e8):,}억 달러" + (f" · 업종 {s['ind']}" if s.get("ind") else "")}
    if f"xyz:{s['sym']}" in hl_ok:
        e["hl"] = f"xyz:{s['sym']}"
    return e


def score(st: dict, news: int) -> float:
    return abs(st["avg"]) * (0.5 + st["same"]) + abs(st["op"]) * 0.5 + min(news, 10) * 0.15


def reason(st: dict, news: int, open_kst: str, mins: int) -> str:
    up = st["avg"] > 0
    s = (f"미국 개장({open_kst}) 후 {mins}분 · 평균 {st['avg']:+.2f}%(전일 종가 대비) · 개장 후 {st['op']:+.2f}% · "
         f"{st['n']}종목 중 {st['k']}종목 {'상승' if up else '하락'} · {'최고' if up else '최저'} {st['best']['name']} {st['best']['chg']:+.2f}%")
    return s + (f" · 관련 속보 {news}건(12시간)" if news else "")


def apply(spots: list[dict], pool: dict, picks: list[tuple[str, str]], day: str, singles: list[dict] | None = None,
          kinds: dict[str, str] | None = None) -> list[dict]:
    """singles(개별 종목) → picks=[(id, reason)] 순서대로 켜고, 다른 자동 종목군·단일 종목은 끈다. pin 은 그대로(맨 뒤)."""
    by = {s["id"]: s for s in spots}
    singles = [x for x in (singles or []) if x["id"] not in {i for i, _ in picks}]
    keep_ids = {i for i, _ in picks} | {x["id"] for x in singles}
    out = []
    for e in singles:
        s = by.get(e["id"], {"id": e["id"]})
        for k in ("hl", "members"):
            s.pop(k, None)
        s.update(e, on=True, auto=True)
        if not by.get(e["id"], {}).get("on"):
            s["since"] = day
        s.pop("until", None)
        out.append(s)
    for i, rs in picks:
        p = pool[i]
        s = by.get(i, {"id": i})
        s.update(name=p["name"], market="미국", kw=p["kw"], members=p["members"], reason=rs, on=True, auto=True)
        s.pop("yf", None)
        if (kinds or {}).get(i):
            s["kind"] = kinds[i]
        else:
            s.pop("kind", None)
        if p.get("hl"):
            s["hl"] = p["hl"]
        else:
            s.pop("hl", None)
        if not by.get(i, {}).get("on"):
            s["since"] = day
        s.pop("until", None)
        out.append(s)
    d0 = datetime.strptime(day, "%Y-%m-%d")
    kept = len(singles)
    for s in spots:
        if s["id"] in keep_ids:
            continue
        if (s.get("on") and s.get("auto") and s.get("yf") and kept < 5 and s.get("since")
                and (d0 - datetime.strptime(s["since"], "%Y-%m-%d")).days <= 3):   # 급등락 대형주는 3일간 유지(주말 포함)
            out.insert(kept, s)
            kept += 1
            continue
        if not s.get("pin") and s.get("on"):
            s["on"] = False
            s["until"] = day
        out.append(s)
    pins = [s for s in out if s.get("pin")]
    return [s for s in out if not s.get("pin")] + pins


def _daily(sym: str) -> dict | None:
    """야후 일봉 1개월 → {날짜: 일간 등락%}."""
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range=1mo&interval=1d"
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=12).read())["chart"]["result"][0]
        off = r["meta"].get("gmtoffset", 0)
        bars = [(datetime.fromtimestamp(t + off, timezone.utc).strftime("%Y-%m-%d"), c)
                for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]
        return {bars[i][0]: (bars[i][1] / bars[i - 1][1] - 1) * 100 for i in range(1, len(bars))}
    except Exception:  # noqa: BLE001
        return None


def _hl_names() -> set[str]:
    """하이퍼리퀴드 xyz 종목 이름(1분봉 차트 가능 여부)."""
    try:
        req = urllib.request.Request("https://api.hyperliquid.xyz/info", data=json.dumps({"type": "metaAndAssetCtxs", "dex": "xyz"}).encode(),
                                     headers={"Content-Type": "application/json"})
        return {u["name"] for u in json.loads(urllib.request.urlopen(req, timeout=12).read())[0]["universe"]}
    except Exception:  # noqa: BLE001
        return set()


def _us_all() -> list[dict]:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import leaders
        return leaders.us()["all"]
    except Exception:  # noqa: BLE001
        return []


def _news() -> list[dict]:
    try:
        r = subprocess.run(["gh", "api", f"repos/{REPO}/contents/news.json?ref=live", "-H", "Accept: application/vnd.github.raw"],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        return json.loads(r.stdout).get("items", [])
    except Exception:  # noqa: BLE001
        return []


def git(*a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=120)


def main() -> int:
    if sys.stdout:                                                     # 예약 작업(pythonw)에서는 stdout 이 없다
        sys.stdout.reconfigure(encoding="utf-8")
    dry, force, last = "--dry" in sys.argv, "--force" in sys.argv, "--last" in sys.argv
    now = datetime.now(timezone.utc)
    if not (dry or force or last or in_window(now)):
        return 0                                                       # 서머타임/해제 두 시각 중 맞는 쪽만 실행
    ny = ny_now(now)
    today_ny = ny.strftime("%Y-%m-%d")
    open_kst = ny.replace(hour=9, minute=30, second=0, microsecond=0).astimezone(KST)
    mins = max(0, int((now - open_kst).total_seconds() // 60))
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    syms = sorted({s for p in pool.values() for s in p["members"]})
    with ThreadPoolExecutor(max_workers=8) as ex:
        q = dict(zip(syms, ex.map(_yq, syms)))
        daily = dict(zip(syms, ex.map(_daily, syms)))
    if dry or last:                                                    # 확인용·--last: 장 전·주말이면 직전 거래일 기준
        days = [datetime.fromtimestamp(d["at"] / 1000, timezone.utc).astimezone(ny.tzinfo).strftime("%Y-%m-%d") for d in q.values() if d and d.get("at")]
        today_ny = max(days, default=today_ny)
    items = [it for it in _news() if now.timestamp() * 1000 - it["ts"] < 12 * 3600_000]
    ranked = []
    for gid, p in pool.items():
        st = stats(p["members"], q, today_ny)
        if not st:
            continue
        rx = re.compile(p["kw"])
        n = sum(1 for it in items if rx.search(it["text"]))
        ranked.append((score(st, n), gid, st, n))
    ranked.sort(key=lambda x: -x[0])
    for sc, gid, st, n in ranked:
        print(f"{sc:6.2f} {pool[gid]['name']:<14} 평균 {st['avg']:+.2f}% 개장후 {st['op']:+.2f}% {st['k']}/{st['n']} 속보 {n}")
    if len(ranked) < PICK:
        log(f"종목군 교체 건너뜀 — 오늘({today_ny}) 미국 정규장 시세가 충분하지 않음(휴장 가능, {len(ranked)}개)")
        return 2
    picks = [(gid, reason(st, n, f"{open_kst:%H:%M}", mins)) for _, gid, st, n in ranked[:PICK]]
    # 📈 연일 상승 종목군
    runs = {}
    for gid, p in pool.items():
        ser = group_daily(p["members"], daily)
        if ser:
            runs[gid] = (streak(ser), sum(ser[-5:]))
    picks = [(g, rs + (f" · 평균 {runs[g][0]}일 연속 상승" if runs.get(g, (0, 0))[0] >= 2 else "")) for g, rs in picks]
    kinds = {}
    cand = sorted((v[0], v[1], g) for g, v in runs.items() if v[0] >= 3 and g not in {x for x, _ in picks})
    if cand:
        k, r5, g = cand[-1]
        picks.append((g, f"평균 {k}일 연속 상승 · 최근 5거래일 합계 {r5:+.2f}%(일봉 종가 기준)"))
        kinds[g] = "📈 연일 상승"
        print(f"연일 상승: {pool[g]['name']} {k}일 {r5:+.2f}%")
    else:
        print("연일 상승: 3일 이상 연속 상승한 종목군 없음 — " + ", ".join(f"{pool[g]['name']} {v[0]}일" for g, v in sorted(runs.items(), key=lambda x: -x[1][0])[:3]))
    # ⚡ 급등락 대형주
    dd0 = datetime.strptime(today_ny, "%Y-%m-%d")
    past = dry or (last and today_ny != ny.strftime("%Y-%m-%d"))
    label = f"{dd0.month}/{dd0.day}({'월화수목금토일'[dd0.weekday()]}) 정규장" + ("" if past else f" 개장 후 {mins}분")
    singles = [single_entry(x, label, _hl_names()) for x in big_movers(_us_all())]
    for e in singles:
        print("급등락:", e["name"], "—", e["reason"])
    if last and today_ny != ny.strftime("%Y-%m-%d"):                   # 지난 거래일 마감 기준으로 고르면 이유 앞머리를 바꾼다
        dd = datetime.strptime(today_ny, "%Y-%m-%d")
        tag = f"{dd.month}/{dd.day}({'월화수목금토일'[dd.weekday()]}) 미국 정규장 마감 기준"
        picks = [(gid, re.sub(r"^미국 개장\([^)]*\) 후 \d+분", tag, rs)) for gid, rs in picks]
    if dry:
        for gid, rs in picks:
            print("선정:", pool[gid]["name"], "—", rs)
        return 0
    git("pull", "-q", "--rebase", "--autostash")
    site = json.loads(SITE.read_text(encoding="utf-8"))
    site["spotlight"] = apply(site.get("spotlight", []), pool, picks, datetime.now(KST).strftime("%Y-%m-%d"), singles, kinds)
    SITE.write_text(json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        (ROOT / "tools" / "world_cache.json").unlink()                 # 다음 1분 갱신 때 새 종목군 시세를 바로 받게
    except OSError:
        pass
    git("add", "data/site.json")
    if git("diff", "--cached", "--quiet").returncode == 0:
        log("종목군 변화 없음")
        return 0
    git("commit", "-q", "-m", f"오늘의 주요 종목군 자동 교체 {today_ny}: " + ", ".join([e["name"] for e in singles] + [pool[g]["name"] for g, _ in picks]))
    for _ in range(3):
        git("pull", "-q", "--rebase", "--autostash")
        if git("push", "-q").returncode == 0:
            break
    log("종목군 교체: " + " / ".join([e["name"] for e in singles] + [pool[g]["name"] for g, _ in picks]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
