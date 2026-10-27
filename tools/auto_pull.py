"""깃허브 자동 받기(10분마다, 예약 작업 '트렌드랩_깃풀') — 안전 모드.

규칙(저장소마다):
- 고치던 파일(추적 중인 파일 변경)이 있으면 건너뛴다 — 작업 중인 내용을 건드리지 않는다
- 깃허브에만 새 커밋이 있으면 빨리 감기(--ff-only)로 받는다
- 내 PC에도 안 올린 커밋이 있어 갈라졌으면 받지 않고 기록만 남긴다(자동 합치기·강제 덮어쓰기 없음)
기록: tools/auto_pull.log (git 제외)
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

REPOS = [Path(r"C:\projects\trend-lab-site"), Path(r"C:\projects\market-site")]
LOG = Path(__file__).resolve().parent / "auto_pull.log"
NO_WINDOW = 0x08000000


def git(repo: Path, *a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW)


def log(msg: str) -> None:
    line = f"{datetime.now():%m-%d %H:%M} {msg}"
    try:
        lines = LOG.read_text(encoding="utf-8").splitlines()[-500:] if LOG.exists() else []
        LOG.write_text("\n".join(lines + [line]) + "\n", encoding="utf-8")
    except OSError:
        pass


def decide(dirty: bool, ahead: int, behind: int) -> str:
    """무엇을 할지(순수 함수): skip_dirty / up_to_date / ff / diverged / ahead_only"""
    if dirty:
        return "skip_dirty"
    if behind == 0:
        return "ahead_only" if ahead else "up_to_date"
    return "diverged" if ahead else "ff"


def pull(repo: Path) -> str:
    if not (repo / ".git").exists():
        return "저장소 없음"
    if git(repo, "fetch", "-q").returncode != 0:
        return "fetch 실패(네트워크?)"
    up = git(repo, "rev-parse", "--abbrev-ref", "@{u}")
    if up.returncode != 0:
        return "원격 브랜치 연결 없음 — 건너뜀"
    dirty = bool(git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip())
    ab = git(repo, "rev-list", "--left-right", "--count", "HEAD...@{u}").stdout.split()
    ahead, behind = (int(ab[0]), int(ab[1])) if len(ab) == 2 else (0, 0)
    act = decide(dirty, ahead, behind)
    if act == "ff":
        r = git(repo, "merge", "--ff-only", "-q", "@{u}")
        return f"받음 {behind}개" if r.returncode == 0 else f"받기 실패: {r.stderr.strip()[:120]}"
    return {"skip_dirty": f"고치던 파일 있음 — 건너뜀(깃허브 새 커밋 {behind}개)", "up_to_date": "최신",
            "ahead_only": f"안 올린 커밋 {ahead}개 있음(받을 것 없음)",
            "diverged": f"갈라짐: 내 커밋 {ahead}·깃허브 {behind} — 자동으로 합치지 않음, 직접 확인 필요"}[act]


def main() -> None:
    for repo in REPOS:
        res = pull(repo)
        if res != "최신":
            log(f"{repo.name}: {res}")


if __name__ == "__main__":
    main()
