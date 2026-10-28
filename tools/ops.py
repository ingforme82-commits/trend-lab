"""🛠 운영 도구 — Claude 사용량이 다 찼을 때 Codex(또는 운영자)가 PowerShell 에서 이어서 쓰는 명령 모음.

  powershell -File scripts\\ops.ps1 status                      # 예약 작업·실시간 갱신·중복 기록·KB 키 상태 점검
  powershell -File scripts\\ops.ps1 run                         # 속보·시세 수집 1회 실행(예약 작업이 멈췄을 때)
  powershell -File scripts\\ops.ps1 watch -Memo "..." -Soxl 102 -Koru 12 [-Push]   # 관전 포인트(운영자 메모·가격대)
  powershell -File scripts\\ops.ps1 issue -Tag "📊 오늘 시황" -Title "..." -Points "첫째|둘째" -Source "..." [-Until 2026-10-30] [-Push]
  powershell -File scripts\\ops.ps1 issue-remove -Tag "📊 오늘 시황" [-Push]
  powershell -File scripts\\ops.ps1 alias -Pattern "젤렌스키" -Name "젤렌스키" [-Push]   # 같은 발언자 묶음 추가
  powershell -File scripts\\ops.ps1 test                        # 테스트
  powershell -File scripts\\ops.ps1 push -Message "..."         # 커밋·push(작성자 조영근)

원칙(AGENTS.md 와 같음): 사실·수치만, 매수·매도 권유·목표가 금지, 키·토큰 값 출력 금지, live 브랜치 직접 수정 금지.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
AUTHOR = ["-c", "user.name=조영근", "-c", "user.email=ingforme82@gmail.com"]
TRAILER = "\n\nCo-Authored-By: Codex (ops.py)"


def sh(*a: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(list(a), cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=check)


def push(msg: str, paths: list[str]) -> None:
    sh("git", "pull", "-q", "--rebase", "--autostash")
    sh("git", "add", *paths)
    if not sh("git", "diff", "--cached", "--quiet").returncode:
        print("바뀐 것 없음 — push 생략")
        return
    r = sh("git", *AUTHOR, "commit", "-q", "-m", msg + TRAILER)
    if r.returncode:
        print("커밋 실패:", r.stderr.strip()[:300]); return
    r = sh("git", "push", "-q")
    print("push 완료 — 1~2분 뒤 사이트 반영" if not r.returncode else "push 실패: " + r.stderr.strip()[:300])


def status(_a) -> None:
    now = datetime.now(KST)
    print(f"== 점검 {now:%Y-%m-%d %H:%M} KST ==")
    r = sh("powershell", "-NoProfile", "-Command",
           "Get-ScheduledTask | Where-Object {$_.TaskName -like '트렌드랩*'} | ForEach-Object { $i=$_|Get-ScheduledTaskInfo; "
           "'{0} | {1} | 마지막 {2:MM-dd HH:mm} | 결과 {3}' -f $_.TaskName,$_.State,$i.LastRunTime,$i.LastTaskResult }")
    print("[예약 작업]\n" + (r.stdout.strip() or "(없음 — 예약 작업 미등록?)"))
    log = ROOT / "tools" / "live_news.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        print("[수집 기록 끝 5줄]\n  " + "\n  ".join(lines[-5:]))
        err = [x for x in lines[-200:] if "건너뜀" in x or "실패" in x]
        if err:
            print("[최근 경고]\n  " + "\n  ".join(err[-6:]))
    try:
        req = urllib.request.Request("https://api.github.com/repos/ingforme82-commits/trend-lab/contents/news.json?ref=live",
                                     headers={"Accept": "application/vnd.github.raw+json", "User-Agent": "trendlab-ops"})
        d = json.loads(urllib.request.urlopen(req, timeout=15).read())
        age = (time.time() * 1000 - d.get("updated", 0)) / 60000
        print(f"[사이트 실시간 데이터] {datetime.fromtimestamp(d['updated'] / 1000, KST):%m-%d %H:%M} 갱신 · {age:.0f}분 전 · 속보 {len(d.get('items', []))}건"
              + ("  ⚠ 5분 넘게 멈춤 → 'ops.ps1 run' 또는 예약 작업 확인" if age > 5 else "  ✅ 정상"))
        L = d.get("leaders") or {}
        for k in ("kr", "us"):
            b = L.get(k) or {}
            if b.get("industry"):
                print(f"  주도 업종({k}): " + " · ".join(f"{g['name']} {g['chg']:+.2f}%" for g in b["industry"][:3]))
    except Exception as e:  # noqa: BLE001
        print("[사이트 실시간 데이터] 확인 실패:", type(e).__name__)
    dl = ROOT / "tools" / "dupcheck.log"
    if dl.exists():
        print("[묶이지 않은 연속 앞머리(최근)] — 실제 발언자면 'ops.ps1 alias'로 추가\n  " + "\n  ".join(dl.read_text(encoding="utf-8").splitlines()[-8:]))
    has = lambda n: bool(os.environ.get(n)) or _reg(n)
    print(f"[KB 키] KB_APP_KEY {'있음' if has('KB_APP_KEY') else '없음'} · KB_APP_SECRET {'있음' if has('KB_APP_SECRET') else '없음'} (값은 표시하지 않음)")
    g = sh("git", "status", "--short")
    print("[git] " + ("변경 없음" if not g.stdout.strip() else "\n" + g.stdout.rstrip()))


def _reg(n: str) -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
            return bool(winreg.QueryValueEx(h, n)[0])
    except OSError:
        return False


def run(_a) -> None:
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "live_news.py")], cwd=ROOT)
    print("수집 1회 완료" if r.returncode == 0 else f"수집 실패(코드 {r.returncode}) — tools/live_news.log 확인")


def watch(a) -> None:
    p = ROOT / "data" / "watch.json"
    w = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    day = a.date or datetime.now(KST).strftime("%Y-%m-%d")
    items = []
    for sym, name, lv in (("SOXL", "SOXL (미국 반도체 3배)", a.soxl), ("KORU", "KORU (한국 3배)", a.koru)):
        it = {"sym": sym, "name": name, "date": day, "focus": ["gap", "ma5", "three"] + (["level"] if lv else [])}
        if lv:
            it["level"] = int(lv) if float(lv).is_integer() else lv
        items.append(it)
    w = {"date": day, "title": a.title or w.get("title") or "오늘 밤 미국장 관전 포인트",
         "memo": a.memo if a.memo is not None else w.get("memo", ""), "items": items}
    p.write_text(json.dumps(w, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"관전 포인트 저장: {day} · SOXL {a.soxl or '-'} · KORU {a.koru or '-'} · 메모 {len(w['memo'])}자")
    if a.push:
        push(f"관전 포인트 갱신 {day}: SOXL {a.soxl or '-'} · KORU {a.koru or '-'}", ["data/watch.json"])


def issue(a) -> None:
    p = ROOT / "data" / "headline.json"
    h = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"items": []}
    pts = [x.strip() for x in (a.points or "").split("|") if x.strip()]
    if not a.title or not pts:
        sys.exit("제목(-Title)과 내용(-Points '첫째|둘째')이 필요합니다")
    bad = re.compile(r"매수\s*추천|매도\s*추천|목표\s*가|사세요|파세요|강력\s*매수|추천\s*종목")
    if bad.search(a.title + " ".join(pts)):
        sys.exit("매수·매도 권유·목표가 표현은 넣을 수 없습니다(사실·수치만)")
    now = datetime.now(KST)
    it = {"tag": a.tag, "title": a.title, "when": a.when or f"{now:%m/%d} {now:%H시 %M분} 기준",
          "until": a.until or (now + timedelta(days=1)).strftime("%Y-%m-%d"), "points": pts, "source": a.source or ""}
    h["items"] = [it] + [x for x in h.get("items", []) if x.get("tag") != a.tag]
    h["updated"] = f"{now:%Y-%m-%d %H:%M}"
    p.write_text(json.dumps(h, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"주요 이슈 저장: [{a.tag}] {a.title} ({len(pts)}줄, ~{it['until']})")
    if a.push:
        push(f"주요 이슈: {a.tag} {a.title}", ["data/headline.json"])


def issue_remove(a) -> None:
    p = ROOT / "data" / "headline.json"
    h = json.loads(p.read_text(encoding="utf-8"))
    n0 = len(h.get("items", []))
    h["items"] = [x for x in h.get("items", []) if x.get("tag") != a.tag]
    p.write_text(json.dumps(h, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"주요 이슈 삭제: {n0 - len(h['items'])}건")
    if a.push:
        push(f"주요 이슈 내림: {a.tag}", ["data/headline.json"])


def alias(a) -> None:
    p = ROOT / "tools" / "newsgroup.py"
    s = p.read_text(encoding="utf-8")
    try:
        re.compile(a.pattern)
    except re.error as e:
        sys.exit(f"정규식 오류: {e}")
    line = f'    (r"{a.pattern}", "{a.name}"),\n'
    if f'"{a.name}")' in s:
        sys.exit(f"이미 있는 묶음 이름: {a.name}")
    anchor = "]\n_ALIAS = "
    if anchor not in s:
        sys.exit("ALIAS 목록 위치를 찾지 못함 — tools/newsgroup.py 직접 확인")
    p.write_text(s.replace(anchor, line + anchor, 1), encoding="utf-8")
    print(f"발언자 묶음 추가: {a.name} ← {a.pattern}")
    t = test(None)
    if a.push and t == 0:
        push(f"속보 묶음 발언자 추가: {a.name}", ["tools/newsgroup.py"])


def test(_a) -> int:
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
    print("테스트:", " / ".join(tail))
    return r.returncode


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="트렌드랩 운영 도구(Codex·운영자용)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(f=status)
    sub.add_parser("run").set_defaults(f=run)
    p = sub.add_parser("watch"); p.add_argument("--memo"); p.add_argument("--soxl", type=float); p.add_argument("--koru", type=float)
    p.add_argument("--title"); p.add_argument("--date"); p.add_argument("--push", action="store_true"); p.set_defaults(f=watch)
    p = sub.add_parser("issue"); p.add_argument("--tag", required=True); p.add_argument("--title"); p.add_argument("--points")
    p.add_argument("--source"); p.add_argument("--when"); p.add_argument("--until"); p.add_argument("--push", action="store_true"); p.set_defaults(f=issue)
    p = sub.add_parser("issue-remove"); p.add_argument("--tag", required=True); p.add_argument("--push", action="store_true"); p.set_defaults(f=issue_remove)
    p = sub.add_parser("alias"); p.add_argument("--pattern", required=True); p.add_argument("--name", required=True); p.add_argument("--push", action="store_true"); p.set_defaults(f=alias)
    sub.add_parser("test").set_defaults(f=test)
    p = sub.add_parser("push"); p.add_argument("--message", required=True)
    p.set_defaults(f=lambda a: push(a.message, ["data", "tools", "tests", "news.js", "app.js", "chart.js", "style.css", "index.html", "study.html", "AGENTS.md"]))
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
