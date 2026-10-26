"""스터디 아카이브에 사진·내용을 올린다.

  python study.py 2026-10-26 --photos "C:\\사진폴더" --push
  python study.py 2026-10-26 --notes 후기.txt --summary "한 줄 소개" --push
  python study.py 2026-12-12 --title "새 스터디" --theme "주제" --book "책" --photos 폴더 --push   # 새 회차

옵션
  --photos 폴더 또는 파일들   jpg·png·webp. 폴더 안 captions.txt("파일명: 설명" 한 줄씩)가 있으면 설명으로 쓴다.
                              기존 사진 뒤에 추가된다. 처음부터 다시 올리려면 --replace-photos.
  --notes 텍스트 파일         '## 소제목' 줄로 묶음을 나누고, 그 아래 줄들은 문단. 소제목 없이 써도 된다.
  --cover N                   목록 카드에 쓸 사진 번호(1부터). 기본은 첫 사진.
  --title/--theme/--book/--place/--summary/--time   값 바꾸기
  --material "이름|주소"       자료 링크 추가(여러 번 가능)
  --remove                    이 회차 삭제
  --push                      git commit·push(사이트 반영, 1~2분)

사진은 긴 변 1600px로 줄이고, 촬영 위치(GPS) 같은 메타데이터는 모두 지운 뒤 올린다.
공개 사이트이므로 참석자 얼굴이 나온 사진은 본인 동의를 받은 것만 올린다.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "studies.json"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def load() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else []


def save(items: list[dict]) -> None:
    items.sort(key=lambda s: s["date"], reverse=True)
    DATA.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def shrink(src: Path, dst: Path, size: int, quality: int) -> None:
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)          # 휴대폰 사진 회전 맞추기
        im = im.convert("RGB")
        im.thumbnail((size, size), Image.LANCZOS)
        im.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)   # exif 없이 저장 = GPS 제거


def add_photos(s: dict, paths: list[str], replace: bool) -> int:
    files: list[Path] = []
    captions: dict[str, str] = {}
    for p in map(Path, paths):
        if p.is_dir():
            cap = p / "captions.txt"
            if cap.exists():
                for line in cap.read_text(encoding="utf-8").splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        captions[k.strip()] = v.strip()
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in IMG_EXT)
        elif p.suffix.lower() in IMG_EXT:
            files.append(p)
        elif p.suffix.lower() in {".heic", ".heif"}:
            print(f"건너뜀(HEIC는 jpg로 바꿔서 넣어 주세요): {p.name}")
    out = ROOT / "study" / s["id"]
    if replace:
        shutil.rmtree(out, ignore_errors=True)
        s["photos"] = []
    out.mkdir(parents=True, exist_ok=True)
    n0 = len(s["photos"])
    for i, f in enumerate(files, start=n0 + 1):
        name = f"{i:02d}.jpg"
        shrink(f, out / name, 1600, 82)
        shrink(f, out / f"t_{name}", 520, 78)
        s["photos"].append({"src": f"study/{s['id']}/{name}", "thumb": f"study/{s['id']}/t_{name}",
                            "caption": captions.get(f.name, captions.get(f.stem, ""))})
    return len(files)


def parse_notes(path: str) -> list:
    blocks: list = []
    cur: dict | None = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t:
            continue
        if t.startswith("##"):
            cur = {"h": t.lstrip("#").strip(), "p": []}
            blocks.append(cur)
        elif cur is not None:
            cur["p"].append(t.lstrip("-• ").strip())
        else:
            blocks.append(t)
    return blocks


def push(msg: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        print("바뀐 내용 없음")
        return
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
    subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)
    print("push 완료 — 1~2분 뒤 사이트에 반영됩니다")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="스터디 날짜 YYYY-MM-DD (같은 날 두 번이면 2026-10-26-2처럼)")
    ap.add_argument("--photos", nargs="+")
    ap.add_argument("--replace-photos", action="store_true")
    ap.add_argument("--notes")
    ap.add_argument("--cover", type=int)
    ap.add_argument("--material", action="append", default=[])
    for k in ("title", "theme", "book", "place", "summary", "time"):
        ap.add_argument(f"--{k}")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    items = load()
    sid = a.date
    s = next((x for x in items if x["id"] == sid), None)
    if a.remove:
        items = [x for x in items if x["id"] != sid]
        shutil.rmtree(ROOT / "study" / sid, ignore_errors=True)
        save(items)
        print(f"삭제: {sid}")
        if a.push:
            push(f"스터디 아카이브 삭제: {sid}")
        return
    if s is None:
        if not a.title:
            raise SystemExit("새 회차는 --title이 필요합니다")
        s = {"id": sid, "date": sid[:10], "time": "", "title": "", "theme": "", "book": "",
             "place": "서울 양재시민의숲역 베델회관 7층", "summary": "", "notes": [], "photos": [], "materials": []}
        items.append(s)
    for k in ("title", "theme", "book", "place", "summary", "time"):
        if getattr(a, k) is not None:
            s[k] = getattr(a, k)
    if a.photos:
        print(f"사진 {add_photos(s, a.photos, a.replace_photos)}장 추가 (총 {len(s['photos'])}장)")
    if a.notes:
        s["notes"] = parse_notes(a.notes)
        print(f"내용 {len(s['notes'])}묶음")
    if a.cover:
        s["cover"] = max(0, min(len(s["photos"]) - 1, a.cover - 1))
    for m in a.material:
        name, _, url = m.partition("|")
        s["materials"].append({"name": name.strip(), "url": url.strip()})
    save(items)
    print(f"저장: {s['date']} {s['title']}")
    if a.push:
        push(f"스터디 아카이브: {s['date']} {s['title']}")


if __name__ == "__main__":
    main()
