r"""PC에 있는 증권사·DART 키를 Oracle 비공개 키 파일 형식으로 한 번 내보낸다(값은 화면에 출력하지 않음).

- 담는 키: 키움·한투·KB·NH 앱키/시크릿, OpenDART. NH 는 앱키·시크릿만(계좌·PIN 등 나머지 설정은 담지 않음).
- 일부만: python tools\keys_export.py NHPLUG   ← 이름에 NHPLUG 가 든 키만
- 이 파일은 저장소 밖(사용자 폴더)에만 만든다. GitHub·카톡·메일로 보내지 않는다(scp 는 암호화 전송).
- 서버 주소·사용자는 이 공개 저장소에 적지 않는다 → PC 환경변수 TRL_ORACLE_HOST·TRL_ORACLE_KEY(키 파일 경로, 값: 비공개 trl-company infra\servers.md).

[1] PC PowerShell (Windows PowerShell 5.1, 한 줄씩. cmd 문법(퍼센트 환경변수·del)과 앰퍼샌드 두 개 연결은 쓰지 않는다 — 대신 ; 와 if ($?))
  cd C:\projects\trend-lab-site
  python tools\keys_export.py
  if (-not ($env:TRL_ORACLE_HOST -and $env:TRL_ORACLE_KEY)) { Write-Host "TRL_ORACLE_HOST/TRL_ORACLE_KEY 없음 - trl-company infra\servers.md 의 설정 줄을 먼저 실행" }
  $key = $env:TRL_ORACLE_KEY
  scp -i $key "$env:USERPROFILE\trl_keys_for_oracle.env" "${env:TRL_ORACLE_HOST}:trl_keys_new.env"
  if ($?) { Remove-Item "$env:USERPROFILE\trl_keys_for_oracle.env"; Write-Host "PC 사본 삭제" }
  ssh -i $key $env:TRL_ORACLE_HOST

[2] 서버 (리눅스, 위 ssh 접속 후 bash) — 기존 keys.env 를 덮어쓰지 않고 덧붙인다.
    keystore 는 같은 이름이 여러 줄이면 첫 줄을 읽으므로, 새로 보낸 이름의 옛 줄만 빼고 끝에 붙인다(서버에만 있는 키는 그대로).
  umask 077; mkdir -p ~/.config/trendlab; f=~/.config/trendlab/keys.env; n=~/trl_keys_new.env; touch "$f"
  cp -p "$f" "$f.bak.$(date +%Y%m%d%H%M%S)"
  names=$(grep -oE '^[A-Za-z0-9_]+=' "$n" | tr -d '=' | paste -sd'|' -)
  { grep -vE "^(${names})=" "$f"; cat "$n"; } > "$f.tmp" && mv "$f.tmp" "$f" && rm -f "$n"
  chmod 600 "$f" "$f".bak.*
  python3 ~/projects/trend-lab-site/tools/brokers_check.py
  (점검이 정상이면 백업 삭제: rm ~/.config/trendlab/keys.env.bak.*)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

OUT = Path.home() / "trl_keys_for_oracle.env"


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    lines, have = ["# TRL Oracle 비공개 키 파일 — 저장소·공개 위치에 두지 말 것. 권한 600."], []
    only = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    for n in keystore.NAMES:
        if only and only not in n:
            continue
        v = keystore.get(n)
        if v:
            lines.append(f"{n}={v}")
            have.append(n)
    if not have:
        print("내보낼 키가 없습니다.")
        return
    keystore.write_private(OUT, "\n".join(lines) + "\n")
    print(f"만듦: {OUT} ({len(have)}개: {', '.join(have)}) — 값은 출력하지 않음")
    if not (os.environ.get("TRL_ORACLE_HOST") and os.environ.get("TRL_ORACLE_KEY")):
        print(r"주의: PC 환경변수 TRL_ORACLE_HOST·TRL_ORACLE_KEY 가 없음 — trl-company infra\servers.md 의 설정 줄을 먼저 실행")
    print("다음 절차:\n")
    print(next_steps())


def next_steps() -> str:
    """docstring 의 [1] PC PowerShell · [2] 서버 bash 절차(화면 출력용)."""
    doc = __doc__ or ""
    i = doc.find("[1] PC PowerShell")
    return doc[i:].rstrip() if i >= 0 else ""


if __name__ == "__main__":
    main()
