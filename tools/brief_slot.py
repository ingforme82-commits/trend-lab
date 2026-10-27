"""⏰ 정시 브리핑 발행: 07:20(밤사이 점검) · 14:00(국내 장중 점검) → data/briefs.json 에 기록하고 push.

  python tools/brief_slot.py 0720      # 또는 1400
  python tools/brief_slot.py 1400 --dry   # 검증만(기록·push 안 함)

- 중복 방지: 같은 날 같은 슬롯 기록이 있으면 건너뜀 + 실행 잠금 파일(10분 지나면 무효)
- 재시도: 검증 실패 시 2분 간격 최대 3번(매번 최신 news.json 다시 받음)
- 발행 차단: 데이터가 오래됐거나, 수집이 실패했거나, 출처 없는 항목이 있으면 기록하지 않고 이유를 로그에 남긴다(종료 코드 2)
- 내용은 수치·사실·출처만(해석·추천 없음, AI 문장 생성 없음)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIEFS = ROOT / "data" / "briefs.json"
CHECKS = ROOT / "data" / "checkpoints.json"
LOCK = ROOT / "tools" / "brief_slot.lock"
LOG = ROOT / "tools" / "brief_slot.log"
KST = timezone(timedelta(hours=9))
REPO = "ingforme82-commits/trend-lab"
SLOTS = {"0720": ("07:20", "밤사이 점검 · 미국 마감 · 오늘 체크포인트"), "1400": ("14:00", "국내 장중 점검 · 섹터 · 주요 종목")}
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
    if slot == "0720":
        reg = d.get("reg") or {}
        if not reg.get("SP500") or not reg.get("XYZ100"):
            bad.append("미국 정규장 마감 시세 누락")
        elif now_ms - min(reg["SP500"]["at"], reg["XYZ100"]["at"]) > 30 * 60 * MIN:
            bad.append("미국 정규장 마감 시세가 30시간 넘게 지난 값")
        if not (d.get("us10y") or {}).get("px"):
            bad.append("미 10년물 금리 누락")
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
    if slot == "0720":
        try:
            cps = json.loads(CHECKS.read_text(encoding="utf-8"))
            rec["checkpoints"] = [{"time": c.get("time", ""), "title": c["title"]} for c in cps if c.get("date") == day][:8]
        except Exception:  # noqa: BLE001
            rec["checkpoints"] = []
    if slot == "1400":
        kr_secs = [c for c in d.get("sectors") or [] if any(r.get("cur") == "KRW" for r in c.get("rows", []))]
        rec["momentum"] = (d.get("momentum") or {}).get("sectors", [])
        rec["kr_top"] = sorted(({"name": r["name"], "sector": c["name"], "chg": r["chg"], "val": r.get("val")}
                                for c in kr_secs for r in c["rows"]), key=lambda x: -x["chg"])[:8]
    return rec


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


def main() -> int:
    slot = next((a for a in sys.argv[1:] if a in SLOTS), None)
    if not slot:
        print(__doc__)
        return 1
    dry = "--dry" in sys.argv
    label = SLOTS[slot][0]
    day = datetime.now(KST).strftime("%Y-%m-%d")
    if not dry:
        git("pull", "-q", "--rebase", "--autostash")
        if already(day, label):
            log(f"{label} 이미 발행됨 — 건너뜀")
            return 0
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 600:
            log(f"{label} 다른 실행이 진행 중 — 건너뜀")
            return 0
        LOCK.write_text(str(os.getpid()), encoding="utf-8")
    try:
        bad = ["시작 전"]
        for n in range(3):
            if n:
                time.sleep(120)
            try:
                d = fetch()
            except Exception as e:  # noqa: BLE001
                bad = [f"news.json 받기 실패: {e}"]
                log(f"{label} 시도 {n + 1}/3 실패: {bad[0]}")
                continue
            bad = validate(slot, d, int(time.time() * 1000))
            if not bad:
                break
            log(f"{label} 시도 {n + 1}/3 검증 실패: " + " / ".join(bad))
        if bad:
            log(f"{label} 발행 차단 — " + " / ".join(bad))
            return 2
        rec = compose(slot, d, day)
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
        return 0
    finally:
        if not dry and LOCK.exists():
            LOCK.unlink()


if __name__ == "__main__":
    sys.exit(main())
