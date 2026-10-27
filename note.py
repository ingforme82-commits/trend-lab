"""변곡점 '💡 해석' 노트 — 자동 감지된 가격 변화에 사람이 쓴 해석을 붙인다.

  python note.py add --from "2026-10-27 00:40" --to "2026-10-27 01:00" --assets WTI BRENT \
      --title "한 줄 제목" --text "해석 2~3문장" --push
  python note.py list
  python note.py remove n-20261027-0040 --push

- 자산 코드: NQ(나스닥100) K200(코스피200) WTI BRENT GOLD US10Y(미 10년물) DXY(달러)
- 화면: 시간이 겹치는 같은 자산의 변곡점 카드·1분봉 차트에 '💡 해석'으로 붙는다.
- 자동 화면은 사실(시각·수치)만, 해석은 이 노트로만 싣는다(운영자 책임 문장).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "notes.json"
CODES = {"NQ", "K200", "WTI", "BRENT", "GOLD", "US10Y", "DXY"}


def iso(s: str) -> str:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").strftime("%Y-%m-%dT%H:%M:00+09:00")


def push(msg: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
    subprocess.run(["git", "pull", "-q", "--rebase", "--autostash"], cwd=ROOT, check=True)
    subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)
    print("push 완료 — 1~2분 뒤 사이트에 반영됩니다")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("--from", dest="frm", required=True, help='"YYYY-MM-DD HH:MM" (한국 시간)')
    p.add_argument("--to", required=True)
    p.add_argument("--assets", nargs="+", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--push", action="store_true")
    p = sub.add_parser("remove"); p.add_argument("id"); p.add_argument("--push", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args()
    notes = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else []
    if a.cmd == "list":
        for n in notes:
            print(f"{n['id']}  {n['from'][5:16]}~{n['to'][11:16]}  {','.join(n['assets'])}  {n['title']}")
        return
    if a.cmd == "remove":
        notes = [n for n in notes if n["id"] != a.id]
    else:
        bad = [x for x in a.assets if x not in CODES]
        if bad:
            raise SystemExit(f"모르는 자산 코드: {bad} (가능: {sorted(CODES)})")
        nid = "n-" + a.frm.replace("-", "").replace(" ", "-").replace(":", "")
        notes = [n for n in notes if n["id"] != nid] + [{"id": nid, "from": iso(a.frm), "to": iso(a.to), "assets": a.assets,
                                                          "title": a.title, "text": a.text, "by": "운영자"}]
    notes.sort(key=lambda n: n["from"], reverse=True)
    DATA.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"노트 {len(notes)}개")
    if a.push:
        push("해석 노트 갱신")


if __name__ == "__main__":
    main()
