"""⛔ 2026-10-28 운영자 결정: 블로그 분석 글은 사이트에 싣지 않는다. 이 명령은 실행되지 않게 막아 두었다.

블로그 글(txt+html)을 사이트 '시황 업데이트' '블로그 분석 글' 칸에 올린다.

  python publish.py "C:\\...\\블로그시황\\20261026_xxx.txt"          # 피드에 추가(같은 글이면 갱신)
  python publish.py <txt> [<txt> ...] --push                        # 추가 후 git commit·push(사이트 반영)
  python publish.py --remove <slug> [--push]                        # 피드에서 빼기

- html은 같은 이름의 .html을 posts/<slug>.html로 복사한다. 글 끝의 모임 CTA는 사이트에
  별도 섹션이 있어서 빼고 올린다(지난 모임 안내가 남지 않게).
- 제목·요약·소제목·작성 시각은 txt에서 읽는다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "data" / "posts.json"
OUT = ROOT / "posts"

CATS = [
    ("모임·스터디", r"모임|스터디|독서 ?토론|커리큘럼"),
    ("시황", r"시황|장전|마감|장중|장초반|내일국장|월요장전"),
    ("유가·중동", r"유가|WTI|브렌트|이란|호르무즈|중동|후티"),
    ("반도체·AI", r"반도체|하이닉스|메모리|HBM|AI|엔비디아|GPU"),
    ("미국주식", r"미국|나스닥|S&P|테슬라|스페이스X|빅테크"),
    ("금리·환율", r"금리|채권|FOMC|환율|국채"),
    ("섹터·텔레", r"섹터|텔레|주간정리|조선|전력"),
]


def parse(txt: Path) -> dict:
    lines = txt.read_text(encoding="utf-8").splitlines()
    body = "\n".join(lines).split("━━━━━━━━━━━━━━━", 1)[0]
    title = lines[0].strip()
    tags = next((l for l in lines[1:6] if l.strip().startswith("#")), "")
    m = re.search(r"📌 한 줄 요약[^\n]*\n(.+?)(?:\n\s*\n|\n\()", body, re.S)
    summary = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    ts = re.search(r"\((\d{1,2})/(\d{1,2})[^)]*?(\d{1,2}):(\d{2})\s*KST", body) or         re.search(r"📌 한 줄 요약 \(()()(\d{1,2}):(\d{2})", body)
    if ts:
        time = f"{int(ts.group(3)):02d}:{ts.group(4)}"
    else:  # 시각 표시가 없으면 파일 저장 시각(이 PC는 KST)
        import datetime as _dt
        time = _dt.datetime.fromtimestamp(txt.stat().st_mtime).strftime("%H:%M")
    secs = [re.sub(r"\s+—.*$", "", s).strip() for s in re.findall(r"^\S+ \d+\. (.+)$", body, re.M)]
    if not secs:
        secs = [l.split(" ", 1)[1].strip() for l in body.splitlines()
                if re.match(r"^[^\w\s#\-\[(※→①-⑩]", l) and 2 < len(l) < 40 and " " in l and "요약" not in l]
    stem = txt.stem
    date = f"{stem[:4]}-{stem[4:6]}-{stem[6:8]}"
    hay = f"{title} {tags}"
    cats = [c for c, pat in CATS if re.search(pat, title if c == "시황" else hay)][:3]
    return {"slug": stem, "date": date, "time": time or "00:00", "title": title, "summary": summary,
            "sections": secs[:8], "tags": re.findall(r"#(\S+)", tags)[:12], "cats": cats or ["시황"],
            "url": f"posts/{stem}.html"}


def copy_html(txt: Path) -> None:
    src = txt.with_suffix(".html")
    if not src.exists():
        raise SystemExit(f"html이 없습니다: {src}")
    s = src.read_text(encoding="utf-8")
    i = s.find("<!-- CTA")
    if i >= 0:
        j = s.find('<p style="font-size:13px;color:#888;">※', i)
        s = s[:i] + (s[j:] if j >= 0 else "</div>\n</body>\n</html>\n")
    back = ('<p style="margin:0 0 18px;font-size:14px;"><a href="../index.html#feed" '
            'style="color:#9a7330;text-decoration:none;font-weight:bold;">← Trend Research Lab 블로그 분석 글</a></p>\n')
    s = re.sub(r"(<body[^>]*>\s*(?:<!--.*?-->\s*)?<div[^>]*>)", r"\1\n" + back, s, count=1, flags=re.S)
    OUT.mkdir(exist_ok=True)
    (OUT / f"{txt.stem}.html").write_text(s, encoding="utf-8")


def load() -> list[dict]:
    return json.loads(POSTS.read_text(encoding="utf-8")) if POSTS.exists() else []


def save(items: list[dict]) -> None:
    items.sort(key=lambda p: (p["date"], p["time"]), reverse=True)
    POSTS.parent.mkdir(exist_ok=True)
    POSTS.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def push(msg: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_sitemap.py")], cwd=ROOT)   # 검색용 sitemap 갱신
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        print("바뀐 내용 없음")
        return
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
    # 다른 PC·Codex에서 먼저 올린 수정이 있으면 받아서 합친 뒤 올린다
    subprocess.run(["git", "pull", "-q", "--rebase", "--autostash"], cwd=ROOT, check=True)
    subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)
    print("push 완료 — 1~2분 뒤 사이트에 반영됩니다")


def main():
    raise SystemExit('블로그 분석 글은 사이트에 싣지 않기로 했습니다(2026-10-28). publish.py 는 꺼져 있습니다.')


def _main_disabled() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_push = "--push" in sys.argv
    items = load()
    if "--remove" in sys.argv:
        items = [p for p in items if p["slug"] not in args]
        for a in args:
            (OUT / f"{a}.html").unlink(missing_ok=True)
        save(items)
        print(f"삭제: {', '.join(args)}")
        if do_push:
            push(f"피드에서 제거: {', '.join(args)}")
        return
    added = []
    for a in args:
        txt = Path(a)
        p = parse(txt)
        copy_html(txt)
        items = [x for x in items if x["slug"] != p["slug"]] + [p]
        added.append(p["title"])
        print(f"추가: {p['date']} {p['time']} {p['title'][:50]} | 분류 {p['cats']} | 소제목 {len(p['sections'])}개")
    save(items)
    if do_push and added:
        push("블로그 분석 글: " + added[-1][:60])


if __name__ == "__main__":
    main()
