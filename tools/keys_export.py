"""PC에 있는 증권사·DART 키를 Oracle 비공개 키 파일 형식으로 한 번 내보낸다(값은 화면에 출력하지 않음).

  python tools/keys_export.py                       # %USERPROFILE%\\trl_keys_for_oracle.env 생성
  scp %USERPROFILE%\\trl_keys_for_oracle.env <오라클사용자>@<서버IP>:~/.config/trendlab/keys.env
  (서버) chmod 600 ~/.config/trendlab/keys.env && python3 ~/projects/trend-lab-site/tools/brokers_check.py
  (PC)   del %USERPROFILE%\\trl_keys_for_oracle.env  ← 옮긴 뒤 바로 지운다

- 담는 키: 키움·한투·KB·NH 앱키/시크릿, OpenDART. NH 는 앱키·시크릿만(계좌·PIN 등 나머지 설정은 담지 않음).
- 일부만: python tools/keys_export.py NHPLUG   ← 이름에 NHPLUG 가 든 키만
- 이 파일은 저장소 밖(사용자 폴더)에만 만든다. GitHub·카톡·메일로 보내지 않는다(scp 는 암호화 전송).
"""

from __future__ import annotations

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
    print("다음: scp 로 서버 ~/.config/trendlab/keys.env 에 복사 → 서버에서 chmod 600 → brokers_check.py → 이 파일 삭제")


if __name__ == "__main__":
    main()
