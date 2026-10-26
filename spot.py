"""🔥 이번 주 화제 종목 켜기·끄기 (data/site.json 의 spotlight)

  python spot.py list
  python spot.py on TSLA --name 테슬라 --market 미국 --hl xyz:TSLA --yf TSLA \
      --kw "테슬라|Tesla|TSLA|머스크" --reason "스페이스X 합병 논의 속 3개월 최고" --push
  python spot.py on 005930 --name 삼성전자 --market 한국 --hl xyz:SMSN --yf 005930.KS --kw "삼성전자" --reason "..." --push
  python spot.py off TSLA --push          # 끄기(기록은 남김, 다시 on 하면 그대로 켜짐)
  python spot.py on OPTICAL --name 광통신·네트워크 --market 미국 --hl xyz:LITE       --members "LITE=루멘텀,COHR=코히런트,CIEN=시에나" --kw "루멘텀|광통신|코히런트" --reason "..." --push   # 종목군
- 켜진 종목(군)은 사이트 '🔥 오늘의 주요 종목군' 칸에서 8초마다 번갈아 보인다(점·화살표로 넘김).

- --hl: 하이퍼리퀴드 24시간 종목(있으면 실시간 + 1분봉 차트), --yf: 야후 심볼(정규장 시세)
- --kw: 관련 속보를 고르는 말(| 로 구분)
- 화면: '실시간 시세' 칸의 '🔥 이번 주 화제 종목' 카드(가격·오늘 관련 속보·1분봉 차트·관련 속보 보기)
- 뉴스·가격 움직임이 많은 종목을 보여 주는 칸이며 종목 추천이 아니다. --reason 에는 사실만 쓴다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "data" / "site.json"


def push(msg: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
    subprocess.run(["git", "pull", "-q", "--rebase", "--autostash"], cwd=ROOT, check=True)
    subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)
    print("push 완료 — 1~2분 뒤 사이트에 반영됩니다(가격은 5분 안에)")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("on"); p.add_argument("id")
    for k in ("name", "market", "hl", "yf", "kw", "reason"):
        p.add_argument(f"--{k}")
    p.add_argument("--members", help='종목군: "LITE=루멘텀,COHR=코히런트,CIEN=시에나" (야후 심볼=이름)')
    p.add_argument("--push", action="store_true")
    p = sub.add_parser("off"); p.add_argument("id"); p.add_argument("--push", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args()
    site = json.loads(SITE.read_text(encoding="utf-8"))
    spots = site.setdefault("spotlight", [])
    if a.cmd == "list":
        for s in spots:
            print(f"{'ON ' if s.get('on') else 'off'} {s['id']:8s} {s.get('name')} ({s.get('market')}) since {s.get('since')} — {s.get('reason', '')}")
        return
    s = next((x for x in spots if x["id"] == a.id), None)
    if a.cmd == "off":
        if not s:
            raise SystemExit("없는 종목입니다")
        s["on"] = False
        s["until"] = datetime.now().strftime("%Y-%m-%d")
    else:
        if not s:
            if not a.name:
                raise SystemExit("처음 켜는 종목은 --name 이 필요합니다")
            s = {"id": a.id}
            spots.append(s)
        for k in ("name", "market", "hl", "yf", "kw", "reason"):
            v = getattr(a, k)
            if v is not None:
                s[k] = v
        if a.members:
            s["members"] = dict(x.split("=", 1) for x in a.members.split(",") if "=" in x)
        s.setdefault("kw", s.get("name", a.id))
        s["on"] = True
        s["since"] = datetime.now().strftime("%Y-%m-%d")
        s.pop("until", None)
    SITE.write_text(json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{a.id} {'켜짐' if s['on'] else '꺼짐'}")
    if getattr(a, "push", False):
        push(f"화제 종목 {a.cmd}: {a.id}")


if __name__ == "__main__":
    main()
