# AGENTS.md — Trend Research Lab 사이트 작업 규칙 (Codex · Claude Code 공통)

조영근 추세추종 리서치 랩의 공개 랜딩 페이지입니다. GitHub Pages로 배포됩니다.
- 사이트: https://ingforme82-commits.github.io/trend-lab/
- 저장소: https://github.com/ingforme82-commits/trend-lab (공개)
- `main`에 push하면 1~2분 뒤 사이트에 반영됩니다. 빌드 과정이 없는 정적 사이트(HTML·CSS·JS + JSON)입니다.

## 반드시 지킬 것
1. **답변·문구는 한국어.** 사이트 문구는 쉬운 말로 씁니다.
2. **투자 권유 금지(유사투자자문).** 매수·매도 권유, 목표가, 종목 추천, 수익 보장 표현은 쓰지 않습니다. 사실·수치·일정·교육 내용만 씁니다.
3. **개인정보.** 참석자 이름은 '참석자'로 익명 처리하고, 운영자 본인 코멘트는 '운영자'로 표시합니다. 아이만 나온 사진은 올리지 않습니다. 사진을 내려 달라는 요청이 오면 바로 내립니다(`study.py hide-photo`).
4. **비밀 정보 금지.** 카카오·텔레그램 키, 토큰, `.env`는 이 저장소에 절대 넣지 않습니다(공개 저장소).
5. **표현.** '모임'이 아니라 **'그룹 스터디'**라고 씁니다. 정기 스터디 회차는 2026년 5월부터 이어서 셉니다(5/9=1회 … 10/17=6회, 11/14=7회). 독서 토론은 따로 셉니다(10/26=1회).
6. **`live` 브랜치는 건드리지 않습니다.** 메인 PC 예약 작업이 10분마다 속보(`news.json`)를 올리는 자동 브랜치입니다.
7. **사이트 밖으로 내보내는 링크를 만들지 않습니다.** 속보·뉴스에는 출처 이름만 텍스트로 적고 원문 링크는 달지 않습니다. 방문자 동선의 목표는 사이트 → 오픈채팅 → 오프라인 그룹 스터디입니다. 다만 **속보·뉴스 영역(띠, 속보 목록, 차트 창)에는 홍보 문구를 끼워 넣지 않습니다** — 뉴스에 집중해 오래 머무르고 많이 클릭하게 하는 것이 우선입니다(2026-10-27 운영자 결정). 오픈채팅·스터디 안내는 첫 화면, 그룹 스터디 칸, 성향 테스트 결과에서 합니다.
8. 커밋하기 전에 `git pull --rebase`로 최신본을 받습니다. 메인 PC 자동 작업과 다른 PC 작업이 같은 `main`에 올라갑니다.

## 구조
| 파일 | 내용 |
|---|---|
| `index.html` · `style.css` · `app.js` | 메인 페이지. 시세, 체크포인트, 시황 피드, 성향 테스트, 그룹 스터디, 아카이브, 커리큘럼, 도서 |
| `news.js` | 맨 위 '주요 시황' 띠 + 실시간 속보·지수 반응. `live` 브랜치 `news.json`(텔레 34개 채널 — 속보 3 + 섹터·뉴스 16 + 증권사 시황·전략 15 — + Seeking Alpha·CNBC·MarketWatch·Investing·연합뉴스·한국경제 RSS)과 Hyperliquid 5분봉 |
| `count.js` | 방문자 집계(abacus 카운터 `trendlab-ing82`). `?me=1`로 연 브라우저는 세지 않음 |
| `study.html` | 회차별 기록 페이지(`study.html?id=2026-08-08`) |
| `data/studies.json` | **그룹 스터디 회차 전체(지난 기록과 예정).** 날짜·주제·사진·후기 |
| `data/site.json` | 공지 띠(`notice`), 카톡 링크, 장소, 주차, 시리즈 이름·규칙 |
| `data/curriculum.json` | 정기 스터디 연간 커리큘럼 |
| `data/books.json` | 독서 토론 선정 도서 10권(`study`에 회차 id를 넣으면 날짜가 연결됨) |
| `data/checkpoints.json` | 이번 주 시장 체크포인트(지난 날짜는 자동으로 숨김) |
| `data/posts.json` · `posts/` | 블로그 시황 글 피드(`publish.py`로 추가) |
| `study/<id>/` | 회차별 사진(웹용 1600px, 메타데이터 제거) |
| `data/growth.json` · `study/growth/` · `tools/growth_photos.py` | 📒 가치 투자 성장 스토리(아카이브 칩, `study.html?id=growth`): 운영자 개인 공부 사진. **운영자 외 얼굴은 모두 모자이크**. `detect` → `review`(내 PC 확인 페이지에서 본인 상자만 지움·놓친 얼굴 추가) → `apply --push`. 원본·작업 파일(boxes.json)은 저장소 밖 |
| `publish.py` | 블로그 글(txt+html)을 피드에 추가 |
| `study.py` | 일정 수정, 새 회차, 사진·후기 올리기, 공지 띠 |
| `tools/make_cta.py` | 블로그 글 끝 그룹 스터디 안내(CTA)를 데이터로 생성 |
| `tools/make_intro.py` | 그룹 스터디 소개 블로그 글 생성 |
| `tools/moves.py` | 변곡점 감지(1분봉 10분·30분 급변, 평소 변동폭의 4배 이상) + 직전 15분 관련 뉴스 연결. 🔴 빨간 점은 이 뉴스에만 |
| `data/site.json` spotlight · `spot.py` | 🔥 이번 주 화제 종목(주 단위로 on/off, 추천 아님 표시). `python spot.py on TSLA --name 테슬라 ... --push` / `off` |
| `data/sectors.json` · `tools/sector_watch.py` | 섹터 시세 감시(사이버보안·미국/한국 반도체·원전·미국 원전SMR·방산·2차전지·조선 8개 섹터, 86종목(사이버보안은 ETF 3개 포함), 사이트에서는 접힌 카드 → 누르면 종목). 하루 ±3%·3개월 고점 돌파·52주 신고가 3% 이내가 생기면 속보 목록에 '섹터 시세'로. 섹터를 늘리려면 sectors.json에 추가 |
| `report.js` | 🔎 시황 리포트 만들기(블로그 분석 글 칸 입력창): 주제어 → 시세·변곡점·속보·섹터·해석 노트·블로그 글·체크포인트를 블로그 형식으로 자동 정리(AI 문장 생성 없음, 해석·전망 없음). `?q=유가` 주소로 바로 열림. 입력하면 블로그 글 목록도 검색 |
| `tools/brief.py` · `data/briefs.json` | 📋 시장 브리핑: 실시간 요약(news.json brief) + 매일 12시 기록(visit_report가 저장·push). 사이트에서 지난 기록·연속 화제·섹터 평균 변화로 후속 확인 |
| `tools/market_extra.py` | 해외 지수(니케이·상하이·CSI300·항셍·대만EWT·DAX·CAC40·유로스톡스50), 화제 종목 시세, 최근 24시간 많이 나온 종목 |
| `data/notes.json` · `note.py` | 변곡점 '💡 해석' 노트(운영자가 쓴 해석 → 블로그 분석 글 연결). 자동 화면은 사실·수치만, 해석은 노트로만 |
| `tools/live_news.py` · `tools/visit_report.py` | 메인 PC 전용(텔레 수집기·카톡 모듈 필요). 예약 작업이 실행 |

## 자주 하는 작업
```bash
pip install -r requirements.txt          # Pillow (사진 줄이기용)

python study.py list                                           # 회차 목록
python study.py edit 2026-11-30 --date 2026-11-23 --push        # 날짜 변경(id는 처음 날짜 그대로)
python study.py edit 2026-11-14 --title "..." --theme "..." --summary "..." --push
python study.py edit 2026-11-30 --date-note "11/23로 앞당겨질 수 있습니다" --push   # 미정 안내('' 이면 지움)
python study.py new 2026-12-12 --series regular --no 8 --title "캔들 패턴 · 종·시·저·고" --push
python study.py new 2026-12-28 --series book --no 3 --title "책 제목" --book "『책』 — 저자" --push
python study.py photos 2026-11-14 "사진폴더" --cover 3 --push   # 촬영 시각 순 정렬, GPS 제거
python study.py notes 2026-11-14 후기.txt --push               # '## 소제목', '! 핵심', '> 참석자: 말'
python study.py hide-photo 2026-08-08 5 --push                 # 5번째 사진 내리기
python study.py notice "📢 안내 문구" --until 2026-11-21 --push / notice --clear --push
python publish.py "블로그시황/20261027_xxx.txt" --push         # 같은 이름 .html 필요
python note.py add --from "2026-10-27 00:40" --to "2026-10-27 01:00" --assets WTI BRENT --title "..." --text "..." --post 블로그글파일이름 --push
```
JSON을 직접 고쳐도 됩니다. 고친 뒤에는 `python -m json.tool data/studies.json > /dev/null`으로 형식을 확인하고 커밋·push 합니다.

## 다른 PC에서 쓰는 법
```bash
git clone https://github.com/ingforme82-commits/trend-lab.git
cd trend-lab && pip install -r requirements.txt
# 블로그 글 저장 위치를 바꾸려면: set TRL_BLOG_DIR=D:\블로그 (Windows) / export TRL_BLOG_DIR=~/blog
```
- 텔레 속보 자동 갱신(`트렌드랩_속보갱신`, 10분마다)과 방문 카톡 리포트(`트렌드랩_방문리포트`, 매일 12:00)는 **메인 PC에서만** 돌아갑니다. 다른 PC에서는 등록하지 않습니다(중복 전송 방지).
- 미리보기: `python -m http.server 8000` 후 http://localhost:8000. 로컬 주소는 방문자로 세지 않습니다.

## 확인 방법
- JS 문법: `node --check app.js news.js count.js`
- 화면: 휴대폰 너비(390px)와 PC(1280px) 둘 다 확인합니다. 가로 스크롤이 생기면 안 됩니다.
