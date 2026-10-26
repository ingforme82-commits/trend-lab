"""그룹 스터디 소개 블로그 글(txt + html) 만들기 — python tools/make_intro.py
사이트 데이터(studies/books/curriculum)를 그대로 쓴다. 저장 위치는 환경변수 TRL_BLOG_DIR(기본: 블로그시황 폴더)."""
import json, os, shutil
from html import escape as E
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("TRL_BLOG_DIR", r"C:\Users\이가영\Documents\블로그시황"))
URL = "https://ingforme82-commits.github.io/trend-lab/"
STEM = "20261027_그룹스터디소개_추세추종_독서토론"
PHOTO_DIR = OUT / "20261027_그룹스터디소개_사진"

studies = {s["id"]: s for s in json.loads((SITE / "data/studies.json").read_text(encoding="utf-8"))}
books = json.loads((SITE / "data/books.json").read_text(encoding="utf-8"))
cur = json.loads((SITE / "data/curriculum.json").read_text(encoding="utf-8"))

# (회차 id, 사진 번호(0부터, None=대표), 블로그용 짧은 소개, 참석자 한마디 번호)
MONTHS = [
    ("2026-05-09", None, "양재 베델회관에서 첫 오프라인 정기 스터디를 열었습니다. 실제 차트와 시황 자료를 화면에 띄우고, 화이트보드에 추세추종의 기본 관점을 함께 정리했습니다.", 0),
    ("2026-06-20", None, "참석자마다 자신의 매매 방식과 시장을 보는 관점을 꺼내 놓았습니다. 같은 시장도 사람마다 기준이 다르다는 것을 확인하고, 각자의 매매 습관을 돌아봤습니다.", 0),
    ("2026-07-11", None, "시장 유동성이 어디에 몰려 있는지, 대형 반도체주의 수급 주체가 어떻게 바뀌는지 짚었습니다. 참석자 기업 분석 발표와 미국 주식·블록체인 이야기도 나눴습니다.", 0),
    ("2026-08-08", None, "연간 커리큘럼의 첫 주제. '잘한 손절은 결과가 좋았던 손절이 아니라, 정해둔 규칙대로 실행한 손절'이라는 기준 하나로 시작했습니다. 손절의 세 종류(가격 -3% · 5일선 종가 이탈 · 일정 기간 무반응)와 실행이 안 되는 이유(규칙의 공백 · 도구의 불일치 · 사이즈 과다)를 정리하고, 각자의 손절 사례를 같은 양식으로 발표했습니다.", 0),
    ("2026-09-12", None, "지지·저항선을 감이 아니라 논리로 긋는 법(거래량·전고점·전저점·이평선)을 정리하고, 참석자 전원이 자기 차트에 선을 그어 와서 '왜 그 자리였는가'를 발표했습니다. 잘된 것만 보여주기 없기가 규칙이었습니다.", 2),
    ("2026-10-17", None, "이동평균선은 움직이는 지지와 저항입니다. AI·반도체 조정 국면을 차트와 함께 보며, 산업의 성장과 주가의 상승은 항상 같은 타이밍으로 움직이지 않는다는 점, 장기 전망과 단기 대응을 나눠서 가격과 수급으로 확인하는 법을 이야기했습니다.", None),
    ("2026-10-26", None, "성장주 발굴 독서 토론의 첫 모임. 코스톨라니의 책으로 '돈 + 심리 = 트렌드', 코스톨라니의 달걀(지금이 어느 국면인가), 물타기와 공포 매수의 차이를 짚었습니다. 마무리는 '기대하거나 예측하지 말고, 확인하면서 대응합시다.'", None),
]
LABEL = {"regular": "📈 정기 스터디", "book": "📚 독서 토론"}
DOW = "월화수목금토일"


def md(d):
    from datetime import date
    y, m, dd = map(int, d.split("-"))
    return f"{m}월 {dd}일({DOW[date(y, m, dd).weekday()]})"


def photo(s, idx):
    ph = s["photos"]
    p = ph[s.get("cover", 0) if idx is None else idx]
    return p


shutil.rmtree(PHOTO_DIR, ignore_errors=True)
PHOTO_DIR.mkdir(exist_ok=True)
txt, html = [], []
title = "[그룹 스터디 소개] 조영근 추세추종 리서치 랩 — 5월부터 이어온 정기 스터디 6회, 독서 토론의 시작, 그리고 2027년까지의 커리큘럼"
tags = "#추세추종 #추세추종매매 #주식스터디 #오프라인스터디 #양재스터디 #독서토론 #투자책 #성장주 #손절 #지지와저항 #이동평균선 #Envelope #코스톨라니 #마이클모부신 #트렌드리서치랩 #주식공부 #원칙매매 #그룹스터디 #스터디모집 #투자성향테스트"
summary = ("2026년 5월 서울 양재 베델회관에서 시작한 추세추종 그룹 스터디가 10월까지 6번 열렸고, 10월부터는 '성장주 발굴 독서 토론'이 더해졌습니다. "
           "그동안의 사진과 내용, 2027년까지의 연간 커리큘럼, 독서 토론 선정 도서 10권을 Trend Research Lab 사이트의 스터디 아카이브에 한곳으로 정리했습니다.")

S = 'style="margin:0 0 10px;"'
H2 = lambda t: f'<h2 style="font-size:21px;margin:34px 0 14px;padding-left:10px;border-left:5px solid #b8862b;color:#1d2433;">{t}</h2>'
BOX = lambda inner, bg="#f6f7fa", bd="#e6e8ee": f'<div style="background:{bg};border:1px solid {bd};border-radius:12px;padding:14px 16px;margin:0 0 14px;">{inner}</div>'

html.append(f'<h1 style="font-size:26px;line-height:1.4;margin:0 0 14px;color:#0f1b2d;">{E(title)}</h1>')
html.append(f'<p style="color:#2563c9;font-size:14px;margin:0 0 20px;">{E(tags)}</p>')
html.append(BOX(f'<p style="margin:0 0 6px;font-weight:bold;color:#9a7330;">📌 한 줄 요약</p><p style="margin:0;">{E(summary)}</p>', "#fbf3e3", "#e6cf9f"))
txt += [title, "", tags, "", "📌 한 줄 요약", summary, ""]

# 1. 두 가지 모임
html.append(H2("1. 강의만 듣는 모임이 아니라, 그룹 스터디입니다"))
GS = "각자 차트와 매매 기록을 가져와 같은 양식으로 발표하고, 서로 질문하고 피드백합니다. 매달 두 번 만납니다."
html.append(f'<p {S}>{E(GS)}</p>')
txt += [GS, ""]
two = [("📈 추세추종 정기 스터디", "매월 둘째 주 토요일 오전 10시", "지난 주제 연결 복습 → 본 주제 강의 → 실차트 적용 → 케이스 발표 및 Q&A. 매달 한 주제씩, 매매 한 사이클의 순서대로 배웁니다."),
       ("📚 성장주 발굴 독서 토론", "매월 마지막 주 월요일 오전 10시", "선정 도서 10권을 한 달에 한 권씩. 책 한 권과 그 달의 시장을 함께 놓고 이야기합니다.")]
txt.append("1. 강의만 듣는 모임이 아니라, 그룹 스터디입니다")
for n, r, d in two:
    html.append(BOX(f'<p style="margin:0 0 4px;font-size:17px;font-weight:bold;color:#7a5413;">{n}</p><p style="margin:0 0 6px;font-size:14px;color:#9a7330;">🗓️ {r} · 📍 서울 양재시민의숲역 베델회관 7층</p><p style="margin:0;">{d}</p>', "#fffaf0", "#e6cf9f"))
    txt += [f"{n} — {r}", d, ""]
steps = [("성향 테스트", "처음 오시는 분은 사이트의 '나의 투자 스타일 테스트'(11문항)로 내 스타일과 조심할 습관을 확인하고 결과를 오픈채팅방에 공유"),
         ("미니 특강", "지난 주제 연결 복습 → 이번 달 주제"),
         ("케이스 발표", "각자 차트·매매 기록을 같은 양식으로 발표(잘된 것만 보여주기 없기)"),
         ("피드백·복기", "질의응답, 다음 달까지 실천할 규칙 한 가지")]
html.append(BOX('<p style="margin:0 0 8px;font-weight:bold;color:#0f1b2d;">🧭 그룹 스터디 진행 방식</p>' + "".join(f'<p style="margin:0 0 6px;"><b style="color:#9a7330;">{i}. {a}</b> — {E(b)}</p>' for i, (a, b) in enumerate(steps, 1)) + f'<p style="margin:10px 0 0;"><a href="{URL}#quiz" style="color:#9a7330;font-weight:bold;">👉 나의 투자 스타일 테스트 하러 가기</a></p>'))
txt += ["🧭 그룹 스터디 진행 방식"] + [f"{i}. {a} — {b}" for i, (a, b) in enumerate(steps, 1)] + [f"👉 나의 투자 스타일 테스트: {URL}#quiz", ""]
html.append(f'<p {S}>참가비는 무료이고, 커피·와이파이·장소도 무료입니다. 교육 목적의 그룹 스터디로 특정 종목을 추천하지 않습니다.</p>')
txt += ["📍 서울 양재시민의숲역 베델회관 7층 · 참가비 무료 · 커피·와이파이·장소 무료 · 교육 목적 그룹 스터디(종목 추천 없음)", ""]

# 2. 매달의 기록
html.append(H2("2. 5월부터 10월까지, 매달의 기록"))
txt.append("2. 5월부터 10월까지, 매달의 기록")
for sid, idx, blurb, rv in MONTHS:
    s = studies[sid]
    p = photo(s, idx)
    fn = f"{sid}_{Path(p['src']).name}"
    shutil.copy(SITE / p["src"], PHOTO_DIR / fn)
    lab = LABEL[s["series"]] + (f" {s['no']}회" if s.get("no") else "")
    quote = s["reviews"][rv]["text"] if rv is not None and s.get("reviews") else ""
    html.append(f'''<div style="border:1px solid #e6e8ee;border-radius:14px;overflow:hidden;margin:0 0 18px;">
<img src="{URL}{p['src']}" alt="{E(s['title'])}" style="width:100%;display:block;">
<div style="padding:14px 16px;">
<p style="margin:0 0 2px;font-size:13px;color:#9a7330;font-weight:bold;">{lab} · {md(s['date'])}</p>
<p style="margin:0 0 8px;font-size:18px;font-weight:bold;color:#0f1b2d;">{E(s['title'])}</p>
<p style="margin:0 0 8px;">{E(blurb)}</p>
{f'<p style="margin:0;padding:10px 12px;background:#fbf3e3;border-radius:10px;font-size:14px;color:#4a3d24;">💬 참석자 한마디 — "{E(quote)}"</p>' if quote else ''}
</div></div>''')
    txt += [f"[사진: {fn}]", f"{lab} · {md(s['date'])} 「{s['title']}」", blurb] + ([f'💬 참석자 한마디 — "{quote}"'] if quote else []) + [""]
html.append(f'<p {S}>회차별 전체 사진(촬영 시각 순)과 강의 내용은 <a href="{URL}#archive" style="color:#9a7330;font-weight:bold;">스터디 아카이브</a>에서 볼 수 있습니다.</p>')
txt += [f"📸 회차별 전체 사진과 내용: {URL}#archive", ""]

# 3. 커리큘럼
html.append(H2("3. 2027년까지의 연간 커리큘럼"))
txt.append("3. 2027년까지의 연간 커리큘럼")
html.append(f'<p {S}>{E(cur["why"])}</p>')
txt += [cur["why"], ""]
for part in cur["parts"]:
    rows = "".join(
        f'<tr><td style="padding:6px 8px;border-top:1px solid #eee;color:#9a7330;font-weight:bold;white-space:nowrap;">{(str(it["no"]) + "회") if it["no"] else "2년차"}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #eee;white-space:nowrap;font-size:14px;">{it["date"].replace("-", ".")}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #eee;">{E(it["topic"])}{" ✅" if it["date"] < "2026-10-27" and len(it["date"]) == 10 else ""}</td></tr>' for it in part["items"])
    html.append(f'<div style="border:1px solid #e6e8ee;border-radius:12px;padding:12px 14px;margin:0 0 12px;"><p style="margin:0 0 4px;font-weight:bold;color:#0f1b2d;">{E(part["name"])}</p><p style="margin:0 0 8px;font-size:14px;color:#5b6474;">{E(part["desc"])}</p><table style="width:100%;border-collapse:collapse;">{rows}</table></div>')
    txt.append(f"■ {part['name']}")
    txt += [f"  {(str(it['no']) + '회') if it['no'] else '2년차'} {it['date'].replace('-', '.')} {it['topic']}{' ✅' if it['date'] < '2026-10-27' and len(it['date']) == 10 else ''}" for it in part["items"]]
    txt.append("")
html.append(f'<p style="font-size:13px;color:#888;">{E(cur["note"])}</p>')

# 4. 도서
html.append(H2("4. 독서 토론 선정 도서 10권"))
txt.append("4. 독서 토론 선정 도서 10권")
bimg = studies["2026-10-26"]["photos"][0]
fn = f"2026-10-26_books_{Path(bimg['src']).name}"
shutil.copy(SITE / bimg["src"], PHOTO_DIR / fn)
html.append(f'<img src="{URL}{bimg["src"]}" alt="선정 도서 10권" style="width:100%;max-width:520px;display:block;margin:0 auto 14px;border-radius:12px;">')
txt.append(f"[사진: {fn}]")
li = []
for i, b in enumerate(books["books"], 1):
    st = studies.get(b["study"]) if b["study"] else None
    when = f" — {md(st['date'])} {'완료' if st['date'] < '2026-10-27' else '예정'}" if st else ""
    li.append(f'<li style="margin:4px 0;"><b>{E(b["title"])}</b> · {E(b["author"])}<span style="color:#c0392b;font-size:14px;">{E(when)}</span></li>')
    txt.append(f"{i}. {b['title']} · {b['author']}{when}")
html.append(f'<ol style="margin:0 0 12px;padding-left:22px;">{"".join(li)}</ol>')
html.append(f'<p {S}>11월에는 마이클 모부신의 『운과 실력의 성공 방정식』으로 "내 수익은 운이었을까, 실력이었을까"를 결과가 아니라 과정으로 평가하는 법을 이야기합니다. 11월 30일(월)이 기본 일정이며, 11월 23일(월)로 한 주 앞당겨질 수 있습니다. 확정되면 오픈채팅과 사이트에서 바로 안내합니다.</p>')
txt += ["", "11월에는 마이클 모부신의 『운과 실력의 성공 방정식』으로 \"내 수익은 운이었을까, 실력이었을까\"를 결과가 아니라 과정으로 평가하는 법을 이야기합니다. 11월 30일(월)이 기본 일정이며, 11월 23일(월)로 한 주 앞당겨질 수 있습니다. 확정되면 오픈채팅과 사이트에서 바로 안내합니다.", ""]

# 5. 사이트
html.append(H2("5. 모임 밖에서도: Trend Research Lab 사이트"))
txt.append("5. 모임 밖에서도: Trend Research Lab 사이트")
feats = ["📊 실시간 시세 — 코스피200·EWY·나스닥100·WTI·브렌트 등 24시간 해외 프록시",
         "🔴 실시간 속보 · 지수 반응 — 텔레그램 속보 헤드라인과, 그 시각 이후 나스닥100·코스피200·WTI가 얼마나 움직였는지",
         "📰 블로그 분석 글 — 블로그에 올린 시황·섹터 분석 모음",
         "🧭 나의 투자 스타일 테스트 — 11문항, 스타일·위험 감수 수준·조심할 매매 습관(답변은 저장되지 않음)",
         "📸 스터디 아카이브 · 연간 커리큘럼 · 선정 도서"]
html.append('<ul style="margin:0 0 12px;padding-left:20px;">' + "".join(f'<li style="margin:4px 0;">{E(f)}</li>' for f in feats) + "</ul>")
html.append(f'<p style="text-align:center;margin:16px 0;"><a href="{URL}" style="display:inline-block;background:#0f1b2d;color:#fff;font-weight:bold;text-decoration:none;padding:12px 22px;border-radius:10px;">🌐 Trend Research Lab 바로가기</a></p>')
txt += feats + [f"🌐 {URL}", ""]

# 정리
closing = ("매달 한 주제씩 쌓아 온 6번의 그룹 스터디는 '기준을 세운다'는 첫 단계를 지나 11월 '추세와 흐름'으로 이어집니다. "
           "독서 토론은 10권의 책으로 시장을 보는 생각의 폭을 넓힙니다. 차트로 기준을 세우고, 책으로 생각을 넓히고, 서로의 매매를 숫자로 확인하는 그룹 스터디입니다.")
html.append(BOX(f'<p style="margin:0 0 6px;font-weight:bold;color:#0f1b2d;">💡 정리</p><p style="margin:0;">{E(closing)}</p>', "#eef3fb", "#c9d7ef"))
txt += ["💡 정리", closing, ""]

cta_html = (OUT / "_cta.html").read_text(encoding="utf-8")
cta_txt = (OUT / "_cta.txt").read_text(encoding="utf-8")
txt.append(cta_txt)
(OUT / f"{STEM}.txt").write_text("\n".join(txt), encoding="utf-8")
page = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>그룹 스터디 소개</title></head>
<body style="margin:0;background:#ffffff;">
<!-- 블로그 붙여넣기: 브라우저에서 이 파일을 열고 Ctrl+A → Ctrl+C → 블로그 편집기에 Ctrl+V. 사진이 안 붙으면 같은 폴더의 '{PHOTO_DIR.name}' 사진을 직접 올리세요 -->
<div style="max-width:760px;margin:0 auto;padding:24px 16px;font-family:'Noto Sans KR','Malgun Gothic',sans-serif;color:#222;line-height:1.75;font-size:16px;">
{chr(10).join(html)}
{cta_html}
<p style="font-size:13px;color:#888;">※ 본 글은 투자 참고용이며, 투자 판단의 최종 책임은 본인에게 있습니다.</p>
</div></body></html>'''
(OUT / f"{STEM}.html").write_text(page, encoding="utf-8")
print(OUT / f"{STEM}.html", len(list(PHOTO_DIR.iterdir())), "photos")
