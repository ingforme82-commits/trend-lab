"""⏰ 정시 브리핑 발행: 06:10(미국 마감 직후 이른 아침 — 운영자 06:30 기상·고객 소통, 11/12 추가) · 07:20(밤사이 점검) · 14:00(국내 장중 점검) · 15:30(국내 종가, 15:35 실행) · 20:05(넥장 마감·프리장 선물·유가) · 22:15(미국 개장 전) → data/briefs.json 에 기록하고 push.

  python tools/brief_slot.py 0720      # 또는 1400 / 2005 / 2215
  python tools/brief_slot.py 1400 --dry   # 검증만(기록·push 안 함)

- 중복 방지: 같은 날 같은 슬롯 기록이 있으면 건너뜀 + 실행 잠금 파일(10분 지나면 무효)
- 재시도: 검증 실패 시 2분 간격 최대 3번(매번 최신 news.json 다시 받음)
- 발행 차단: 데이터가 오래됐거나, 수집이 실패했거나, 출처 없는 항목이 있으면 기록하지 않고 이유를 로그에 남긴다(종료 코드 2)
- 내용은 수치·사실·출처만(해석·추천 없음, AI 문장 생성 없음)
"""

from __future__ import annotations

import json
import os
import sys
import subprocess
if sys.platform == "win32":  # pythonw로 예약 실행될 때 git·gh 검은 창이 뜨지 않게
    _run = subprocess.run
    def _quiet_run(*a, **k):
        k.setdefault("creationflags", 0x08000000)  # CREATE_NO_WINDOW
        return _run(*a, **k)
    subprocess.run = _quiet_run
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
BRIEFS = ROOT / "data" / "briefs.json"
CHECKS = ROOT / "data" / "checkpoints.json"
LOCK = ROOT / "tools" / "brief_slot.lock"
LOG = ROOT / "tools" / "brief_slot.log"
KST = timezone(timedelta(hours=9))
REPO = "ingforme82-commits/trend-lab"
SLOTS = {"0610": ("06:10", "미국 마감 직후 · 밤사이 이슈 · 오늘 체크포인트"), "0720": ("07:20", "밤사이 점검 · 미국 마감 · 오늘 체크포인트"), "1400": ("14:00", "국내 장중 점검 · 섹터 · 주요 종목"), "1530": ("15:30", "국내 증시 마감(종가) · 섹터 · 수급"),
         "2005": ("20:05", "넥스트레이드 마감 · 미국 프리장 선물·유가 점검"), "2215": ("22:15", "미국 개장 전 선물·유가 점검")}
EVE = {"2005", "2215"}
MORNING = {"0610", "0720"}
KR_DAY = {"1400", "1530"}                 # 국내 섹터·모멘텀·수급·상위 종목을 담는 슬롯
KAKAO = {"0610"}                          # 발행하면 카톡 나에게 요약도 보냄(11/12 운영자)
SITE = "https://ingforme82-commits.github.io/trend-lab/"                 # 미국 마감 결과·10년물·오늘 체크포인트를 담는 아침 슬롯
MIN = 60_000


def log(msg: str) -> None:
    line = f"{datetime.now(KST):%m-%d %H:%M:%S} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def validate(slot: str, d: dict, now_ms: int) -> list[str]:
    """발행을 막는 문제 목록(빈 목록이면 발행 가능). 순수 함수 — tests/test_brief_slot.py"""
    bad = []
    up = d.get("updated", 0)
    if now_ms - up > 10 * MIN:
        bad.append(f"속보 데이터가 {round((now_ms - up) / MIN)}분 전 것(10분 초과)")
    h = d.get("health") or {}
    tg, rss = h.get("tg") or {}, h.get("rss") or {}
    if tg.get("refresh") is False:
        bad.append("텔레그램 수집 실패")
    if not tg.get("last") or now_ms - tg["last"] > 3 * 60 * MIN:
        bad.append("텔레그램 속보 채널 새 글이 3시간 넘게 없음")
    if rss.get("total") and rss.get("ok", 0) < rss["total"] / 2:
        bad.append(f"RSS 절반 이상 실패({rss.get('ok')}/{rss.get('total')})")
    b = d.get("brief") or {}
    if not b:
        bad.append("브리핑 데이터 없음")
    for k in ("macro", "heads"):
        for x in b.get(k) or []:
            if not x.get("src") or not x.get("ts"):
                bad.append(f"출처·시각 없는 항목: {x.get('text', '')[:30]}")
    if len(b.get("futures") or []) < 6:
        bad.append("24시간 선물 시세 누락(6개 미만)")
    if slot in MORNING:
        reg = d.get("reg") or {}
        if not reg.get("SP500") or not reg.get("XYZ100"):
            bad.append("미국 정규장 마감 시세 누락")
        elif now_ms - min(reg["SP500"]["at"], reg["XYZ100"]["at"]) > (80 if datetime.fromtimestamp(now_ms / 1000, KST).weekday() == 0 else 30) * 60 * MIN:
            bad.append("미국 정규장 마감 시세가 너무 오래된 값(평일 30시간·월요일 80시간 기준)")   # 월요일 07:20 은 금요일 마감이 마지막(11/9 차단 수정)
        if not (d.get("us10y") or {}).get("px"):
            bad.append("미 10년물 금리 누락")
    if slot == "1530":
        kr = d.get("kr") or {}
        if not kr.get("KOSPI") or not kr.get("KR200"):
            bad.append("한국 지수 시세 누락")
        elif kr["KOSPI"].get("open"):
            bad.append("한국 정규장이 아직 열려 있음(종가 전)")
        elif datetime.fromtimestamp(kr["KOSPI"]["at"] / 1000, KST).strftime("%Y-%m-%d") != datetime.fromtimestamp(now_ms / 1000, KST).strftime("%Y-%m-%d"):
            bad.append("오늘 국내 종가가 아님(휴장일 가능)")
        if not [r for c in d.get("sectors") or [] for r in c.get("rows", []) if r.get("cur") == "KRW"]:
            bad.append("국내 섹터 시세 누락")
    if slot == "1400":
        kr = d.get("kr") or {}
        if not kr.get("KOSPI") or not kr.get("KR200"):
            bad.append("한국 지수 실시간 시세 누락")
        elif not kr["KOSPI"].get("open"):
            bad.append("한국 정규장이 열려 있지 않음(휴장일 가능)")
        elif now_ms - kr["KOSPI"]["at"] > 10 * MIN:
            bad.append("한국 지수 시세가 10분 넘게 지연")
        kr_rows = [r for c in d.get("sectors") or [] for r in c.get("rows", []) if r.get("cur") == "KRW"]
        if not kr_rows:
            bad.append("국내 섹터 시세 누락")
        elif sum(1 for r in kr_rows if r.get("stale")) > len(kr_rows) * 0.2:
            bad.append("국내 섹터 종목 20% 넘게 전일 값")
    return bad


def compose(slot: str, d: dict, day: str) -> dict:
    """기록할 내용(수치·출처만)."""
    b = dict(d.get("brief") or {})
    label, title = SLOTS[slot]
    rec = {"day": day, "slot": label, "title": title, **b, "at": int(time.time() * 1000), "reg": d.get("reg") or {}}
    if slot in MORNING:
        try:
            cps = json.loads(CHECKS.read_text(encoding="utf-8"))
            rec["checkpoints"] = [{"time": c.get("time", ""), "title": c["title"]} for c in cps if c.get("date") == day][:8]
        except Exception:  # noqa: BLE001
            rec["checkpoints"] = []
    if (d.get("lev") or {}).get("items"):
        rec["lev"] = d["lev"]                             # SOXL·KORU 점검
    if (d.get("watch") or {}).get("items"):
        rec["watch"] = d["watch"]                         # 운영자 관전 포인트(07:20엔 마감 결과)
    if slot in EVE:
        rec["eve"] = d.get("eve") or {}
    if slot in KR_DAY:
        kr_secs = [c for c in d.get("sectors") or [] if any(r.get("cur") == "KRW" for r in c.get("rows", []))]
        rec["momentum"] = (d.get("momentum") or {}).get("sectors", [])
        rec["flows"] = [{"name": g["name"], "icon": g.get("icon", ""), "rows": sorted(g["rows"], key=lambda r: -(r.get("val") or 0))[:5]}
                        for g in (d.get("flows") or {}).get("groups", [])]
        rec["kr_top"] = sorted(({"name": r["name"], "sector": c["name"], "chg": r["chg"], "val": r.get("val")}
                                for c in kr_secs for r in c["rows"]), key=lambda x: -x["chg"])[:8]
    return rec


def kakao_text(rec: dict) -> str:
    """카톡용 짧은 요약(수치·출처만). 사이트 맨 위 띠와 같은 내용 + 주요 뉴스 3건."""
    pc = lambda v: "" if v is None else f"{v:+.2f}%"  # noqa: E731
    reg, ust = rec.get("reg") or {}, rec.get("ust") or {}
    L = [f"🌄 {rec['day'][5:].replace('-', '/')} {rec['slot']} TRL 새벽 브리핑", rec.get("title", "")]
    if reg.get("SP500"):
        L.append(f"미국 마감 S&P500 {pc(reg['SP500'].get('chg'))} · 나스닥100 {pc((reg.get('XYZ100') or {}).get('chg'))}"
                 + (f" · SOXL {pc(reg['SOXL'].get('chg'))}" if reg.get("SOXL") else "") + (f" · KORU {pc(reg['KORU'].get('chg'))}" if reg.get("KORU") else ""))
    if (ust.get("10Y") or {}).get("px"):
        L.append(f"미 10년물 {ust['10Y']['px']:.3f}%")
    fut = {f["name"]: f for f in rec.get("futures") or []}
    sel = [f"{n} {pc(fut[n].get('chg'))}" for n in ("코스피200", "나스닥100", "WTI", "금", "달러인덱스", "원/달러") if n in fut]
    if sel:
        L.append("24시간: " + " · ".join(sel))
    heads = rec.get("heads") or []
    if heads:
        L.append("주요 뉴스")
        L += [f"- {h.get('text', '')[:70]} ({h.get('src', '')})" for h in heads[:3]]
    cps = rec.get("checkpoints") or []
    if cps:
        L.append("오늘: " + ", ".join(((c.get("time") + " ") if c.get("time") else "") + c["title"] for c in cps[:3]))
    L.append(SITE)
    return chr(10).join(x for x in L if x)


def already(day: str, label: str) -> bool:
    try:
        return any(h.get("day") == day and h.get("slot") == label for h in json.loads(BRIEFS.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return False


def fetch() -> dict:
    r = subprocess.run(["gh", "api", f"repos/{REPO}/contents/news.json?ref=live", "-H", "Accept: application/vnd.github.raw"],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return json.loads(r.stdout)


def git(*a: str) -> None:
    subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, timeout=120)


def due_slots(now: datetime) -> list[str]:
    """정시 실행을 5분 기다린 뒤, 20분 이내 누락만 현재 자료로 보완한다."""
    result = []
    for slot in SLOTS:
        if now.weekday() >= 5 and not (slot == "0610" and now.weekday() == 5):
            continue
        hour, minute = (15, 35) if slot == "1530" else (int(slot[:2]), int(slot[2:]))
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        lag = (now - scheduled).total_seconds() / 60
        if 5 <= lag <= 20:
            result.append(slot)
    return result


def catch_up() -> None:
    """실행 PC의 정상 수집 직후만 호출. 과거 슬롯을 최신 시세로 소급 작성하지 않는다."""
    now = datetime.now(KST)
    for slot in due_slots(now):
        if not already(now.strftime("%Y-%m-%d"), SLOTS[slot][0]):
            try:
                main(slot, delayed=True)
            except Exception as exc:  # noqa: BLE001
                log(f"{SLOTS[slot][0]} 누락 보완 실패: {type(exc).__name__}")


def main(slot: str | None = None, delayed: bool = False) -> int:
    slot = slot or next((a for a in sys.argv[1:] if a in SLOTS), None)
    if not slot:
        print(__doc__)
        return 1
    dry = "--dry" in sys.argv
    label = SLOTS[slot][0]
    day = datetime.now(KST).strftime("%Y-%m-%d")
    if not dry:
        try:
            git("pull", "-q", "--rebase", "--autostash")
        except (subprocess.SubprocessError, OSError) as exc:
            log(f"{label} 최신 코드 받기 실패: {type(exc).__name__}")
            return 1
        if already(day, label):
            log(f"{label} 이미 발행됨 — 건너뜀")
            return 0
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 600:
            log(f"{label} 다른 실행이 진행 중 — 건너뜀")
            return 0
        if LOCK.exists():
            if time.time() - LOCK.stat().st_mtime < 600:
                log(f"{label} 다른 실행이 진행 중 — 건너뜀")
                return 0
            try:
                LOCK.unlink()
            except FileNotFoundError:
                pass
        try:
            with LOCK.open("x", encoding="utf-8") as lock:
                lock.write(str(os.getpid()))
        except FileExistsError:
            log(f"{label} 다른 실행이 잠금을 얻음 — 건너뜀")
            return 0
    try:
        if not dry and already(day, label):
            return 0
        bad = ["시작 전"]
        attempts = 1 if delayed else 3
        for n in range(attempts):
            if n:
                time.sleep(120)
            try:
                d = fetch()
            except Exception as e:  # noqa: BLE001
                bad = [f"news.json 받기 실패: {e}"]
                log(f"{label} 시도 {n + 1}/{attempts} 실패: {bad[0]}")
                continue
            bad = validate(slot, d, int(time.time() * 1000))
            if not bad and slot in EVE:
                from evening import check, make as evening
                d["eve"] = evening(d)
                bad = check(d["eve"])
            if not bad:
                break
            log(f"{label} 시도 {n + 1}/3 검증 실패: " + " / ".join(bad))
        if bad:
            log(f"{label} 발행 차단 — " + " / ".join(bad))
            return 2
        rec = compose(slot, d, day)
        if delayed:
            rec["delayed"] = True
            rec["title"] += " · 지연 발행(표시 시각의 최신 자료)"
        if dry:
            print(json.dumps({k: rec[k] for k in ("day", "slot", "title")}, ensure_ascii=False), "검증 통과(--dry, 기록 안 함)")
            return 0
        hist = json.loads(BRIEFS.read_text(encoding="utf-8")) if BRIEFS.exists() else []
        hist = [rec] + [h for h in hist if not (h.get("day") == day and h.get("slot") == label)]
        BRIEFS.write_text(json.dumps(hist[:120], ensure_ascii=False, indent=1), encoding="utf-8")
        git("add", "data/briefs.json")
        git("commit", "-q", "-m", f"정시 브리핑 {day} {label}")
        for n in range(3):                                   # push 충돌 시 재시도
            try:
                git("pull", "-q", "--rebase", "--autostash")
                git("push", "-q")
                break
            except subprocess.CalledProcessError:
                if n == 2:
                    raise
                time.sleep(20)
        log(f"{label} 발행 완료")
        if slot in KAKAO:
            try:
                from dart_watch import deliver
                deliver("브리핑", f"{day}-{label}", kakao_text(rec))
                log(f"{label} 카톡 요약 보냄")
            except Exception as e:  # noqa: BLE001
                log(f"{label} 카톡 요약 실패 {type(e).__name__}")
        return 0
    finally:
        if not dry and LOCK.exists():
            LOCK.unlink()


if __name__ == "__main__":
    sys.exit(main())
