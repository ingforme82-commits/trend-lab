"""증권사·데이터 API 키와 상태 폴더 — Windows PC와 Oracle(리눅스) 공통. 2026-11-15 운영자: "오라클과 문제 없이 호환".

키 찾는 순서(먼저 나온 값):
  1) 프로세스 환경변수(systemd EnvironmentFile 포함)
  2) 비공개 키 파일 — TRL_KEYS_FILE 이 가리키는 파일, 없으면 ~/.config/trendlab/keys.env (KEY=VALUE 줄, 권한 600 권장)
  3) Windows 사용자 환경변수(레지스트리) — 예약 작업처럼 새 환경변수를 못 받은 PC 프로세스용
상태 폴더(토큰·캐시): Windows %LOCALAPPDATA%\\trendlab · 리눅스 $XDG_STATE_HOME/trendlab 또는 ~/.local/state/trendlab
키 값은 출력·로그·저장소에 남기지 않는다. 이 모듈은 값이 있다/없다만 알려 준다(has()).
"""

from __future__ import annotations

import os
from pathlib import Path

NAMES = ("KIWOOM_APP_KEY", "KIWOOM_SECRET_KEY", "KIS_APP_KEY", "KIS_APP_SECRET", "KB_APP_KEY", "KB_APP_SECRET", "DART_API_KEY")


def keys_file() -> Path:
    p = os.environ.get("TRL_KEYS_FILE", "").strip()
    return Path(p).expanduser() if p else Path.home() / ".config" / "trendlab" / "keys.env"


def _from_file(name: str) -> str:
    try:
        for line in keys_file().read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _from_registry(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
            return str(winreg.QueryValueEx(h, name)[0]).strip()
    except OSError:
        return ""


def get(name: str) -> str:
    return os.environ.get(name, "").strip() or _from_file(name) or _from_registry(name)


def pair(a: str, b: str) -> tuple[str, str] | None:
    x, y = get(a), get(b)
    return (x, y) if x and y else None


def has(name: str) -> bool:
    return bool(get(name))


def state_dir(osname: str | None = None) -> Path:
    if (osname or os.name) == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", "").strip() or (Path.home() / ".local" / "state"))
    d = base / "trendlab"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def write_private(path: Path, text: str) -> None:
    """토큰 파일 저장(리눅스에서는 소유자만 읽기·쓰기)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
