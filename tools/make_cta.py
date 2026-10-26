"""블로그 글 끝 모임 안내(CTA)를 사이트 일정 데이터로 만든다.

  python tools/make_cta.py
→ C:\\Users\\이가영\\Documents\\블로그시황\\_cta.html, _cta.txt
다음 정기 스터디와 다음 독서 토론을 날짜 순으로 넣는다. study.py로 일정을 바꾸면 자동으로 다시 만든다.
"""

from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(r"C:\Users\이가영\Documents\블로그시황")
SITE_URL = "https://ingforme82-commits.github.io/trend-lab/"
DOW = "월화수목금토일"


def when(s: dict) -> str:
    d = datetime.strptime(s["date"], "%Y-%m-%d")
    h, m = map(int, (s.get("time") or "10:00").split(":"))
    t = f"{'오전' if h < 12 else '오후'} {h % 12 or 12}시" + (f" {m}분" if m else "")
    return f"{d.year}년 {d.month}월 {d.day}일({DOW[d.weekday()]}) {t}"


def main(quiet: bool = False) -> None:
    site = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))
    items = json.loads((ROOT / "data" / "studies.json").read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")
    up = sorted((s for s in items if s["date"] > today or (s["date"] == today and not s.get("photos"))), key=lambda s: s["date"])
    picks = [x for x in (next((s for s in up if s["series"] == k), None) for k in ("regular", "book")) if x]
    picks.sort(key=lambda s: s["date"])

    h, t = [], []
    for s in picks:
        se = site["series"][s["series"]]
        no = f" {s['no']}회" if s.get("no") else ""
        h.append(f'''  <div style="background:#fffaf0;border:1px solid #e6cf9f;border-radius:12px;padding:12px 14px;margin:0 0 10px;">
    <p style="margin:0 0 2px;font-size:13px;color:#9a7330;font-weight:bold;">{se["emoji"]} {escape(se["name"])}{no}</p>
    <p style="margin:0 0 6px;font-size:19px;font-weight:bold;color:#7a5413;">「{escape(s["title"])}」</p>
    {f'<p style="margin:0 0 6px;font-size:14px;">{escape(s["theme"])}</p>' if s.get("theme") else ""}
    <p style="margin:0;font-size:15px;">🗓️ <b>일시</b> : {when(s)}{f'<br><span style="color:#c0392b;font-size:13px;">※ {escape(s["date_note"])}</span>' if s.get("date_note") else ""}<br>📍 <b>장소</b> : {escape(s.get("place") or site["place"])}{f"<br>📖 <b>함께 읽을 책</b> : {escape(s['book'])}" if s.get("book") else ""}</p>
  </div>''')
        t += [f"{se['emoji']} {se['name']}{no} 「{s['title']}」"]
        if s.get("theme"):
            t.append(s["theme"])
        t += [f"🗓️ 일시 : {when(s)}"] + ([f"   ※ {s['date_note']}"] if s.get("date_note") else []) + [f"📍 장소 : {s.get('place') or site['place']}"]
        if s.get("book"):
            t.append(f"📖 함께 읽을 책 : {s['book']}")
        t.append("")

    rules = " / ".join(f"{v['short']}: {v['rule']}" for v in site["series"].values())
    html = f'''<!-- CTA (항상 글 마지막) -->
<div style="border:2px solid #b8862b;border-radius:14px;background:linear-gradient(135deg,#fdf8ee,#fbefd6);padding:20px 22px;margin:30px 0 16px;">
  <p style="margin:0 0 4px;font-size:13px;color:#9a7330;letter-spacing:1px;">조영근 추세추종 리서치 랩 | Trend Research Lab</p>
  <p style="margin:0 0 12px;font-size:20px;font-weight:bold;color:#7a5413;">다가오는 그룹 스터디</p>
{chr(10).join(h)}
  <p style="margin:0 0 12px;padding:10px 12px;background:#fffaf0;border:1px dashed #d4a85a;border-radius:10px;font-size:14px;">🅿️ <b>주차</b> : {escape(site["parking"])}<br>☕ <b>무료 제공</b> : {escape(site["free"])}</p>
  <p style="margin:0 0 12px;">카카오톡 오픈채팅방에 100명 이상이 함께하고 있습니다. ({escape(rules)})<br>
  ① 온라인 시황분석: 선물·금리·유가·환율·해외 프록시<br>
  ② 오프라인 정기 스터디 · 독서 토론</p>
  <p style="margin:0 0 12px;font-size:14px;">📸 지난 그룹 스터디 사진과 내용, 연간 커리큘럼: <a href="{SITE_URL}#archive" style="color:#9a7330;font-weight:bold;">Trend Research Lab 스터디 아카이브</a></p>
  <p style="margin:0;text-align:center;"><a href="{site["kakao"]}" style="display:inline-block;background:#fee500;color:#191919;font-weight:bold;text-decoration:none;padding:12px 22px;border-radius:10px;">💬 카카오톡 오픈채팅 참여하기</a></p>
  <p style="margin:10px 0 0;text-align:center;font-size:13px;">{site["kakao"]}</p>
  <p style="margin:12px 0 0;font-size:12px;color:#8a7a5a;">본 그룹 스터디는 교육 목적이며, 특정 종목을 추천하지 않고 수익을 보장하지 않습니다.</p>
</div>
'''
    txt = "\n".join([
        "━━━━━━━━━━━━━━━",
        "조영근 추세추종 리서치 랩 | Trend Research Lab",
        "다가오는 그룹 스터디", "", *t,
        f"🅿️ 주차 : {site['parking']}",
        f"☕ 무료 제공 : {site['free']}", "",
        "카카오톡 오픈채팅방에 100명 이상이 함께하고 있습니다.",
        "① 온라인 시황분석: 선물·금리·유가·환율·해외 프록시",
        "② 오프라인 정기 스터디 · 독서 토론", "",
        f"📸 지난 그룹 스터디 사진·내용·커리큘럼: {SITE_URL}#archive", "",
        "💬 카카오톡 오픈채팅 참여하기", site["kakao"], "",
        "본 그룹 스터디는 교육 목적이며, 특정 종목을 추천하지 않고 수익을 보장하지 않습니다.",
        "━━━━━━━━━━━━━━━", "",
        "※ 본 글은 투자 참고용이며, 투자 판단의 최종 책임은 본인에게 있습니다.", ""])
    OUT.mkdir(exist_ok=True)
    (OUT / "_cta.html").write_text(html, encoding="utf-8")
    (OUT / "_cta.txt").write_text(txt, encoding="utf-8")
    if not quiet:
        print(f"CTA 갱신: {', '.join(s['date'] + ' ' + s['title'] for s in picks)}")


if __name__ == "__main__":
    main()
