"""스터디 일정·아카이브 관리 (사이트 data/studies.json, data/site.json)

일정·주제 바꾸기 (사이트 메인 카드, 상세 페이지, 커리큘럼 표시가 모두 따라 바뀜)
  python study.py edit 2026-11-14 --date 2026-11-21 --push        # 날짜 변경(id는 그대로)
  python study.py edit 2026-11-30 --time 19:30 --place "장소" --push
  python study.py edit 2026-11-30 --date-note "11/23로 앞당겨질 수 있습니다" --push   # 미정 안내('' 이면 지움)
  python study.py edit 2026-11-14 --title "새 주제" --theme "한 줄 설명" --summary "소개" --push

새 회차 만들기
  python study.py new 2026-12-12 --series regular --no 5 --title "캔들 패턴" --push
  python study.py new 2026-12-28 --series book --no 3 --title "책 제목" --book "『책』 — 저자" --push

사진·후기 올리기 (사진은 촬영 시각 순 정렬, 긴 변 1600px, GPS 등 메타데이터 제거)
  python study.py photos 2026-11-14 "C:\\사진폴더" [--replace] [--cover 3] --push
  python study.py notes 2026-11-14 후기.txt --push      # '## 소제목' 아래 줄은 문단, '> 참석자: 내용'은 참석자 한마디
  python study.py hide-photo 2026-08-08 5 --push        # 5번째 사진 내리기(게시 거부 요청 시)

공지 띠 (사이트 맨 위 금색 띠)
  python study.py notice "11/14 스터디가 11/21로 변경되었습니다" --until 2026-11-21 --push
  python study.py notice --clear --push

확인
  python study.py list
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "studies.json"
SITE = ROOT / "data" / "site.json"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def shrink(src: Path, dst: Path, size: int, quality: int) -> None:
    from PIL import Image, ImageOps
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")      # 휴대폰 사진 회전 맞추기
        im.thumbnail((size, size), Image.LANCZOS)
        im.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)   # exif 없이 저장 = GPS 제거


def shot_time(p: Path) -> datetime | None:
    from PIL import Image
    try:
        ex = Image.open(p).getexif()
        v = ex.get_ifd(0x8769).get(36867) or ex.get(306)
        if v:
            return datetime.strptime(v, "%Y:%m:%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        pass
    for fmt, n in (("%Y%m%d_%H%M%S", 15), ("%Y%m%d", 8)):
        s = p.stem.replace("KakaoTalk_", "")
        try:
            return datetime.strptime(s[:n], fmt)
        except ValueError:
            continue
    return None


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def save(p: Path, obj) -> None:
    if isinstance(obj, list):
        obj.sort(key=lambda s: s["date"], reverse=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def find(items: list[dict], sid: str) -> dict:
    s = next((x for x in items if x["id"] == sid), None)
    if s is None:
        raise SystemExit(f"없는 회차입니다: {sid}  (python study.py list 로 확인)")
    return s


def push(msg: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        print("바뀐 내용 없음")
        return
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
    # 다른 PC·Codex에서 먼저 올린 수정이 있으면 받아서 합친 뒤 올린다
    subprocess.run(["git", "pull", "-q", "--rebase", "--autostash"], cwd=ROOT, check=True)
    subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)
    print("push 완료 — 1~2분 뒤 사이트에 반영됩니다")


def after(a, msg: str) -> None:
    if getattr(a, "push", False):
        push(msg)


FIELDS = ("title", "theme", "book", "place", "summary", "time", "series")


def cmd_edit(a) -> None:
    items = load(DATA)
    s = find(items, a.id)
    old = dict(s)
    for k in FIELDS:
        v = getattr(a, k, None)
        if v is not None:
            s[k] = v
    if a.no is not None:
        s["no"] = a.no
    if a.date:
        s["date"] = a.date
        s.pop("date_note", None)            # 날짜가 확정되면 '바뀔 수 있음' 안내는 지운다
    if getattr(a, "date_note", None) is not None:
        s["date_note"] = a.date_note
        if not a.date_note:
            s.pop("date_note")
    save(DATA, items)
    ch = [f"{k}: {old.get(k)!r} → {s.get(k)!r}" for k in (*FIELDS, "date", "no") if old.get(k) != s.get(k)]
    print("\n".join(ch) or "바뀐 값 없음")
    after(a, f"스터디 수정: {s['id']} {s['title']}")


def cmd_new(a) -> None:
    items = load(DATA)
    if any(x["id"] == a.id for x in items):
        raise SystemExit("이미 있는 회차입니다. edit을 쓰세요.")
    site = load(SITE)
    s = {"id": a.id, "series": a.series, "no": a.no or 0, "date": a.date or a.id[:10], "time": a.time or "10:00",
         "title": a.title, "theme": a.theme or "", "book": a.book or "", "place": a.place or site["place"],
         "summary": a.summary or "", "highlights": [], "notes": [], "reviews": [], "photos": [], "materials": []}
    items.append(s)
    save(DATA, items)
    print(f"새 회차: {s['date']} {site['series'][s['series']]['short']} {s['title']}")
    after(a, f"스터디 추가: {s['date']} {s['title']}")


def cmd_photos(a) -> None:
    items = load(DATA)
    s = find(items, a.id)
    files: list[Path] = []
    captions: dict[str, str] = {}
    for p in map(Path, a.paths):
        if p.is_dir():
            cap = p / "captions.txt"
            if cap.exists():
                for line in cap.read_text(encoding="utf-8").splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        captions[k.strip()] = v.strip()
            files += [f for f in p.iterdir() if f.suffix.lower() in IMG_EXT]
        elif p.suffix.lower() in IMG_EXT:
            files.append(p)
        elif p.suffix.lower() in {".heic", ".heif"}:
            print(f"건너뜀(HEIC는 jpg로 바꿔서 넣어 주세요): {p.name}")
    out = ROOT / "study" / s["id"]
    if a.replace:
        for f in out.glob("[0-9]*.jpg"):
            f.unlink()
        for f in out.glob("t_[0-9]*.jpg"):
            f.unlink()
        s["photos"] = []
    out.mkdir(parents=True, exist_ok=True)
    rows = sorted(((shot_time(f) or datetime.min, f) for f in files), key=lambda r: r[0])
    n0 = max([int(Path(p["src"]).stem) for p in s["photos"]] + [0])
    for i, (t, f) in enumerate(rows, start=n0 + 1):
        name = f"{i:02d}.jpg"
        shrink(f, out / name, 1600, 82)
        shrink(f, out / f"t_{name}", 520, 78)
        same = t != datetime.min and t.strftime("%Y-%m-%d") == s["date"]
        s["photos"].append({"src": f"study/{s['id']}/{name}", "thumb": f"study/{s['id']}/t_{name}",
                            "caption": captions.get(f.name, captions.get(f.stem, "")),
                            "time": t.strftime("%H:%M") if same else "", "date": t.strftime("%Y-%m-%d") if t != datetime.min else ""})
    s["photos"].sort(key=lambda p: (p.get("date", ""), p.get("time", "")))
    if a.cover:
        s["cover"] = max(0, min(len(s["photos"]) - 1, a.cover - 1))
    save(DATA, items)
    print(f"사진 {len(rows)}장 추가 (총 {len(s['photos'])}장)")
    after(a, f"스터디 사진: {s['date']} {s['title']}")


def cmd_hide(a) -> None:
    items = load(DATA)
    s = find(items, a.id)
    if not 1 <= a.n <= len(s["photos"]):
        raise SystemExit(f"사진 번호는 1~{len(s['photos'])}")
    p = s["photos"].pop(a.n - 1)
    for k in ("src", "thumb"):
        (ROOT / p[k]).unlink(missing_ok=True)
    if s.get("cover", 0) >= len(s["photos"]):
        s["cover"] = 0
    save(DATA, items)
    print(f"사진 내림: {p['src']} ({p.get('caption', '')})")
    after(a, f"스터디 사진 내림: {s['date']}")


def cmd_notes(a) -> None:
    items = load(DATA)
    s = find(items, a.id)
    blocks, reviews, hl = [], [], []
    cur = None
    for line in Path(a.file).read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t:
            continue
        if t.startswith(">"):
            who, _, text = t.lstrip("> ").partition(":")
            reviews.append({"who": who.strip() if text else "참석자", "text": (text or who).strip()})
        elif t.startswith("!"):
            hl.append(t.lstrip("! ").strip())
        elif t.startswith("##"):
            cur = {"h": t.lstrip("#").strip(), "p": []}
            blocks.append(cur)
        elif cur is not None:
            cur["p"].append(t.lstrip("-• ").strip())
        else:
            blocks.append(t)
    s["notes"] = blocks
    if reviews:
        s["reviews"] = reviews
    if hl:
        s["highlights"] = hl
    save(DATA, items)
    print(f"내용 {len(blocks)}묶음, 핵심 {len(hl)}개, 참석자 한마디 {len(reviews)}개")
    after(a, f"스터디 후기: {s['date']} {s['title']}")


def cmd_notice(a) -> None:
    site = load(SITE)
    site["notice"] = {"text": "", "until": ""} if a.clear else {"text": a.text or "", "until": a.until or "", "pin": True}
    save(SITE, site)
    print("공지 삭제" if a.clear else f"공지: {a.text} (~{a.until or '계속'})")
    after(a, "공지 " + ("삭제" if a.clear else "변경"))


def cmd_list(a) -> None:
    site = load(SITE)
    today = datetime.now().strftime("%Y-%m-%d")
    for s in sorted(load(DATA), key=lambda x: x["date"]):
        se = site["series"].get(s["series"], {})
        mark = "예정" if s["date"] > today or (s["date"] == today and not s.get("photos")) else "    "
        print(f"{mark} {s['id']}  {s['date']} {s['time']}  {se.get("short", "")} {str(s["no"]) + "회" if s.get("no") else "":4} {s['title']}  (사진 {len(s.get('photos', []))})")
    if site.get("notice", {}).get("text"):
        print(f"\n공지: {site['notice']['text']} (~{site['notice'].get('until') or '계속'})")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, with_fields=True):
        p.add_argument("--push", action="store_true")
        if with_fields:
            for k in FIELDS:
                p.add_argument(f"--{k}")
            p.add_argument("--date")
            p.add_argument("--date-note", dest="date_note", help='날짜 변경 가능성 안내(빈 문자열 ""이면 지움)')
            p.add_argument("--no", type=int)

    p = sub.add_parser("edit"); p.add_argument("id"); common(p); p.set_defaults(f=cmd_edit)
    p = sub.add_parser("new"); p.add_argument("id"); common(p); p.set_defaults(f=cmd_new)
    p = sub.add_parser("photos"); p.add_argument("id"); p.add_argument("paths", nargs="+")
    p.add_argument("--replace", action="store_true"); p.add_argument("--cover", type=int); common(p, False); p.set_defaults(f=cmd_photos)
    p = sub.add_parser("hide-photo"); p.add_argument("id"); p.add_argument("n", type=int); common(p, False); p.set_defaults(f=cmd_hide)
    p = sub.add_parser("notes"); p.add_argument("id"); p.add_argument("file"); common(p, False); p.set_defaults(f=cmd_notes)
    p = sub.add_parser("notice"); p.add_argument("text", nargs="?"); p.add_argument("--until"); p.add_argument("--clear", action="store_true")
    common(p, False); p.set_defaults(f=cmd_notice)
    p = sub.add_parser("list"); p.set_defaults(f=cmd_list)
    a = ap.parse_args()
    if a.cmd == "new" and (not a.title or not a.series):
        raise SystemExit("new에는 --series(regular/book)와 --title이 필요합니다")
    a.f(a)


if __name__ == "__main__":
    main()
