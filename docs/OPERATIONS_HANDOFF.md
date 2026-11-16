# TRL 운영 인계 — Claude · Codex
최종 정리: 2026-11-16 02시(KST), Claude. 지난 기록은 git 이력과 `docs/archive/`에 있다.

## 시작 순서
1. 이 저장소 `AGENTS.md`와 이 문서를 읽는다. 대화 기억만으로 운영 상태를 추정하지 않는다.
2. 비공개 market-site의 `docs/AGENT_LOG.md` 맨 아래(최신 인계)와 `docs/RUNBOOK_KR.md`(한국장 대응)를 읽는다.
3. 수정 전 최신 코드를 받고, 끝나면 검증·커밋·push 후 이 문서·AGENT_LOG에 남긴다.

## 지금 운영 구조(11/16 기준)
| 무엇 | 어디서 | 비고 |
|---|---|---|
| 속보 매분·정시 브리핑(06:10·07:20·12:00·14:00·15:30·20:05·22:15) | **Oracle 서버**(일본 리전, 129.203.145.164) | market-site `oracle/site_executor.json` owner=oracle. PC의 live_news는 gate가 건너뜀 |
| 실시간 체결(KIS 웹소켓) → 사이트 2초 | Oracle systemd `trl-rt_kis`·`trl-rt_serve` | Cloudflare 무료 빠른 터널, 주소는 news.json `rt_url`(재시작 때 바뀌어도 자동) |
| 서버 자동 업데이트 | Oracle systemd `trl-autopull.timer`(5분) | `scripts/oracle_autopull.sh` — ff-only pull, 실시간 코드 바뀌면 서비스 재시작 |
| NH 모의매매(한국·미국) | **LG PC** 예약 작업 | market-site `feature/trader-nh-mock` trader/ |
| KB 조회 | **PC만** | KB가 해외 IP 차단(KB 공지) — Oracle 불가 |

서버 처음 설치·다시 설치: `bash scripts/oracle_rt_setup.sh`(cloudflared·서비스 3개). 저장소 경로 `~/projects/trend-lab-site`, `~/projects/market-site`.

## 증권사·출처(조회 전용 — 주문 경로는 모듈에서 막음)
- 키 찾는 순서: 환경변수 → `~/.config/trendlab/keys.env` → Windows 레지스트리(`tools/keystore.py`). 키 값은 출력·커밋 금지.
- 점검: `python3 tools/brokers_check.py` — 11/16: 키움·한투·NH·KB ✅, LS·토스·DB 키 대기.
- 교차 확인 `tools/xbroker.py`: 키움·한투·NH·KB·LS·토스·DB·네이버 → 다수 일치 값. 기준을 섞지 않음(KRX 정규장 / 통합 NXT 포함).
- **출처 점수판** `tools/srcscore.py`: 성공률·일치율·응답 시간·신선도로 우선순위 자동 조정, 3번 연속 실패면 10분 쉼. 사이트 시세 칸 아래 '📊 출처 점수판'.
- KIS 웹소켓 제약(11/16 실측): **키당 접속 1개, 동시 3종목**. PC에서 `rt_kis.py`를 돌리면 서버 접속이 끊긴다. 한국장 08~16시 코스피·코스피200·코스닥, 그 밖 SOXL·SKHY·KORU.
- 키움: 서버 IP 등록 + User-Agent 필요. 한투 업종코드 2001(코스피200) REST는 HTTP 500(웹소켓은 됨).
- 새 키 받을 이름: `LS_APP_KEY/LS_APP_SECRET`, `TOSS_CLIENT_ID/TOSS_CLIENT_SECRET`(허용 IP에 Oracle IP), `DB_APP_KEY/DB_APP_SECRET`. 받으면 PC 등록 → `python tools/keys_export.py LS_ TOSS_ DB_` → scp → 서버 chmod 600 → PC 파일 삭제 → 서버 brokers_check.

## 화면 기준(11/16)
- 모든 등락률 옆에 **기준 숫자**: 코스피200 주간선물=전일 종가, 야간선물=주간 종가, CME=전일 정산가, 하이퍼리퀴드=24시간 전(장 밖 한국 종목은 '종가 시각 가격'), 국채=전일 금리.
- 원/달러·달러인덱스 칸 = CNBC 24시간(실패 시 야후 24시간, 더 최근 값 자동 선택). 하이퍼리퀴드 환율은 거래 멈춤이라 안 씀.
- 미국 반도체 묶음: SOXL → DRAM(라운드힐 메모리 ETF) → **SKHY**(SK하이닉스 ADR, **10주 = 원주 1주**, 원주 환산가·프리미엄 표시 — 11/13 약 +43%) → MU.
- 화면 파일을 바꾸면 `index.html`의 `?v=`와 `sw.js` VERSION을 같이 올린다(안 올리면 앱이 옛 파일을 계속 씀 — 11/16 점수판 미표시 원인). 지금 trl-app-v12.
- 💰 수급(운영자 11/16): 08~09시는 종목별 프로그램(한투 `tools/kisflow.py`, KRX·넥스트레이드 나눠 합계)으로 외국인 흐름을 가늠, 09:20~ 외국인·09:50~ 기관 장중 추정 가집계('추정 n차')가 나오면 외국인·기관 칸을 그 값으로. 확정치는 장 마감 뒤 네이버. 한투 TR 허용 목록에 `HHPTJ`(투자자 추정, 조회) 추가.
- WTI 관전 기준 85달러. 미국 채권 휴장일은 `market_extra.py UST_HOLIDAYS_2026`(다음 해 갱신 필요).

## 남은 일
1. LS·토스·DB 키 → 연결·첫 응답 필드 확인(DB 필드명은 비공식 래퍼 기준).
2. 11/16 08시 이후 실시간 체결 값이 사이트에 '실시간 체결'로 뜨는지 확인(장 밖에는 구독 성공까지만 확인).
3. live·quotes 데이터 브랜치 이력이 큼 — 정리는 운영자 결정 필요('live 직접 수정 금지').
4. 무료 터널은 서버 재시작 때 주소가 바뀐다(자동 전달됨). 고정 주소가 필요하면 도메인(연 1~2만 원) — 운영자 확인 뒤.
