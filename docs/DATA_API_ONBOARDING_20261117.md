# 2026-11-17 무료 데이터 API 연결 공동 작업 — Claude · Codex

운영자 요청: 오늘부터 KRX·ECOS·LS증권·Alpaca·Finnhub·SEC EDGAR 가입/발급을 직접 진행하고 완료 상태를 전달한다. Claude와 Codex는 같은 인계를 읽고 Oracle 연결·TRL 반영을 순차 검증한다. 아직 키 발급·승인·Oracle 연결 완료로 표시하지 않는다.

## 역할과 진행 순서
- 운영자: 개인 계정 생성, 본인인증, 약관 동의, 서비스 이용신청/승인, 키 발급. 비밀값을 채팅·공개문서·저장소에 남기지 않는다.
- Claude: 발급 상태와 서비스별 기능/이용조건 확인, 기존 provider·어댑터 유무와 작업 대상 파일을 이 문서/OPERATIONS_HANDOFF에 기록. Codex 작업 중 같은 파일 동시 편집은 피한다.
- Codex: Oracle에서 조회 전용 인증·실제 응답·원천 시각·단위·시장/통화·호출제한 검증, 출처 점수판/캐시/TTL/실패 처리를 적용하고 검증 증거를 남긴다.
- 신청 순서: 승인 대기 가능한 KRX 먼저 신청 → ECOS → LS 계좌/API 신청 → Alpaca Paper → Finnhub → SEC 연락처 설정. 승인/발급 완료된 것부터 연결해도 된다.
- 상태: 신청 전 → 신청 완료 → 승인/키 발급 → 비공개 설정 등록 → Oracle 조회 성공 → 기간/출처 대조 → TRL 반영. 키 있음과 API 접근 성공, 공개 사용 허용을 같은 상태로 보지 않는다.

## 서비스별 운영자 작업·검증 범위
| 서비스 | 운영자 작업 | 알려줄 상태(값 제외) | TRL 첫 사용 범위 |
|---|---|---|---|
| KRX Open API | 정보데이터시스템 가입, 인증키/서비스 신청 화면 안내에 따라 주식·지수 일별 데이터 신청. 승인 순서·기간은 실제 신청 화면 기준 | 신청한 서비스명, 승인/대기, 키 발급 여부 | 거래소 일별 확정값 대조. 실시간 시세로 취급하지 않음 |
| 한국은행 ECOS | Open API 안내에서 키 신청 | 키 발급 여부·사용승인 상태 | 금리·환율 등 통계의 관측기간/공표주기 표시. 장중 체결값과 구분 |
| LS증권 | 계좌 개설·로그인 → 사용등록/해지 → xingAPI 등록 → OPEN API 신청 → App Key/Secret | 계좌/API 등록 완료, 실전/모의 키 구분, 키 발급 여부 | 기존 lsapi.py의 국내지수/주가 조회부터. 뉴스·해외선물은 실제 TR/권한 확인 전 지원한다고 단정하지 않음 |
| Alpaca | 무료 Paper 계정 대시보드에서 키/시크릿 발급 | Paper 키 발급 여부, Basic 등급 | 무료 미국 IEX 시세와 허용된 뉴스 조회 시험. 전체 거래소 실시간 SIP와 구분 |
| Finnhub | 계정 생성·대시보드 키 발급 | 무료 등급·키 발급 여부 | 해당 등급에서 허용되는 기업 뉴스·실적일정 시험. 엔드포인트별 권한/호출 한도/현재 가격표 재확인 |
| SEC EDGAR | 요청 식별에 쓸 연락용 이메일 결정 | 이메일 설정 준비 여부(주소 공개 안 함) | 공개 공시 submissions/XBRL 조회. 독자용 공개 데이터 API는 회원가입·API 키 불필요 |

## 비공개 설정·기존 코드 확인
- 기존 공통 저장 경로: 환경변수 또는 ~/.config/trendlab/keys.env, 권한600. 새 공급자 키는 기존 설정에 병합한다. PC 파일로 서버 전체 keys.env를 덮어써 기존 공급자 설정을 지우지 않는다.
- 기존 LS 이름: LS_APP_KEY, LS_APP_SECRET. LS 조회 어댑터 tools/lsapi.py 및 brokers_check.py 있음.
- 신규 공급자 권장 이름(아직 확정 구현/배포되지 않은 제안): KRX_API_KEY, ECOS_API_KEY, APCA_API_KEY_ID, APCA_API_SECRET_KEY, FINNHUB_API_KEY, SEC_USER_AGENT. 실제 구현 전 공통 keystore/내보내기 허용목록과 각 어댑터가 같은 이름을 쓰도록 합의한다.
- 확인한 keystore.NAMES에는 위 신규 공급자 이름이 아직 없다. 기존 keys_export.py만 실행해서 신규 키까지 전송됐다고 판정하지 않는다.
- tools/krx.py는 현재 네이버 polling 한국시세 어댑터다. 이름만 보고 거래소 Open API가 이미 연결됐다고 해석하거나 파일을 덮어쓰지 않는다. 공식 KRX 어댑터는 별도 이름으로 설계한다.
- 키/시크릿/연락용 이메일은 공개 문서에 적지 않는다. 연결 상태 보고는 서비스·키 존재 여부·응답 성공 여부·오류 유형만.
- 초기 전부 조회 전용. 계좌 주문·실주문·새 자동매매 실행자/타이머 변경은 이번 가입 작업과 분리한다.

## 실제 조회를 통과한 뒤 남길 증거
1. Oracle DNS/TCP/TLS/인증/조회 응답을 구분.
2. 원천 이벤트 시각과 수집 시각, 세션/시장, 지연 또는 마지막 종가, 통화·단위 기록.
3. NVDA·TSM·SOXL 등 교차 대조는 같은 세션·같은 시각대·같은 시세 범위로 비교. IEX 한 거래소 가격을 미국 전체 통합 가격과 불일치로 단정하지 않음.
4. 오류/429/권한 부족은 캐시/재시도 제한·상태 표시로 처리하고 오래된 값에 현재 시각만 붙이지 않음.
5. KRX/ECOS 일별·월별 데이터를 실시간 피드로 표시하지 않음. 데이터 공표 주기마다 적합하게 조회.
6. 공개 TRL 게시/이용자 재배포 가능 범위는 공급자별 계약/플랜 조건을 확인한 항목만 활성화. 미확인 조건을 무료 연결 완료로 넘기지 않음.
7. SEC는 식별 가능한 User-Agent·연락처 설정, 공식 fair-access 속도 제한 이하로 캐시·백오프 적용. Oracle 접근 성공은 별도 실측.
8. 기간 검증: 실적은 회계연도/시작·종료일/3개월·누적/연결·별도 확인. 이번 케이프 사례처럼 출처와 운영자 확인이 충돌하면 미확인 유지.

## 이어서 진행 중인 TSMC 관찰
- main 0ca76d2: data/channels.json에 미국 파운드리 TSM/TSMC ADR 추가(16종목).
- 미국장 개장 직후 공개 live 14:31 UTC에서 기존6개 미국 종목은 11/17 live=true로 전환됨. 같은 게시본에는 TSM이 아직 없어 Oracle 설정 반영은 검증 중.
- 기존 trader/chan_rules.py 연결은 있지만 TSM은 NH 자동주문 UNIVERSE에 추가하지 않았다. 신규 주문종목/그룹분모·비중을 바꾼 것으로 보고하지 않는다.
- 채널 계산은 Yahoo 시간봉 조회+1분 캐시이므로 틱 실시간이라고 부르지 않는다. 원천시각 검증/거래일/DST·휴장/낡은데이터 차단은 추가 점검 필요.

## 공식 확인 자료(2026-11-17)
- KRX: https://openapi.krx.co.kr/ (동적 화면으로 세부 신청 절차는 현재 화면에서 확인 필요)
- ECOS: https://ecos.bok.or.kr/api/ (동적 화면으로 즉시 발급/소요시간을 보장하지 않음)
- LS 선행등록 안내: https://openapi.ls-sec.co.kr/about-openapi
- LS 사용안내: https://openapi.ls-sec.co.kr/howto-use
- Alpaca Paper 키 안내: https://alpaca.markets/learn/access-free-market-data
- Alpaca Basic 시세 범위: https://docs.alpaca.markets/us/docs/about-market-data-api
- Finnhub: https://finnhub.io/docs/api · https://finnhub.io/pricing (이 환경에서 동적 본문 미확인, 구체 요금/한도 확정하지 않음)
- SEC 공개 API: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC User-Agent/접근 제한: https://www.sec.gov/about/webmaster-frequently-asked-questions


## 2026-11-18 미국 정부 공식 자료 보강·가입 진행 상태
- 운영자 SEC 이메일 회원가입 완료 보고. 독자용 공개 submissions/XBRL API는 가입·API 키가 필요 없으며 연락처를 포함한 식별 User-Agent 설정 필요. 이메일은 공개 문서에 기록하지 않음. SEC_CONTACT_EMAIL 비공개 설정 준비 요청 중.
- 현재 코드 확인: live_news.py의 연준 보도자료·연설/백악관/BEA RSS, official.py의 재무부 일별금리/EIA 주간재고/BLS 통계 조회 존재. 코드 존재와 Oracle 최신 수집 성공을 구분. 중복 수집기 추가보다 기존 경로 상태 검증 우선.
- 보강 순서: SEC NVDA 대표 submissions 조회 → NVDA/TSM/MU 등 watchlist CIK 검증 → 8-K/10-Q/10-K/6-K/20-F 이벤트 정규화 → 출처/접수번호/제출시각/대상기간·개정여부 대조 후 기존 뉴스 파이프라인 연결. 접수일·보고기간·달력분기를 혼동하지 않고 단순 metadata만으로 당분기 실적 확정 금지.
- 정책/거시 우선순위: Fed(FOMC·발언), BLS(물가·고용), BEA(GDP·PCE), Treasury(국채), EIA(원유), White House·상무부 BIS(관세·수출통제). 검증된 공식 RSS/API만 사용; 차단/빈응답은 실패 상태로 유지하고 우회 성공으로 표시하지 않음.
- 관측 시각/수집 시각·수정치 구분, accession 중복 제거, 캐시·백오프, SEC 공식 상한10req/s보다 낮은 순차 조회. 회원가입만으로 실연결/공개게재/실시간 알림 완료라고 보고하지 않음.
- 사용자 제공 Oracle 결과 01:34KST: ECOS 기준금리58행 조회 PASS(최신관측20261115), KRX kospi_dd_trd/kosdaq_dd_trd HTTP401. 두 키 비공개등록,기존키보존. TRL 자동게시 미변경.
- LS는 최근 계좌개설 제한으로 보류(사용자 보고). Alpaca Paper·Finnhub 키 로컬존재 확인, 실제 Oracle 신규조회 결과는 대기. 전체 API 성공으로 표시 금지.


## 2026-11-18 운영자: 모든 출처를 역할별로 활용
- 무료 연결 실측과 활용을 우선. 이번 지시는 유료 구독 구매/결제 승인으로 해석하지 않음. X·Alpaca Plus·Massive 등은 부족한 기능과 비용을 확인한 뒤 별도 결정.
- 역할: 기존 증권사=시세·시장 수급 대조, Alpaca=허용된 미국 뉴스/시세, Finnhub=허용된 기업뉴스·일정, SEC=기업공시 사실 확인, Fed/BLS/BEA/Treasury/EIA/백악관/BIS=거시·정책 원자료, ECOS/KRX=국내 공식 통계·확정값 대조. 지원/등급 미확인 항목은 예정 기능으로 유지.
- 실행 순서: (1) 오라클 전체 REST 조회 결과 수령·분류 (2) ECOS 최초 정상 데이터 TRL 반영 경로 구현 (3) Alpaca/Finnhub 인증·권한·원천시각 대조 (4) SEC 연락처 비공개설정·대표 공시 조회 (5) KRX401 해결·LS계좌제한해제 후 검증. 동시 편집 전 Claude/Codex가 이 문서와 최신 코드를 확인.
- 뉴스 이벤트 표준: 원천 출처·이벤트 식별자·관련 종목/섹터·최초 발표시각·수집시각·수정 여부·확인상태. 재게시 기사는 독립 취재 매체 수에 중복 계산하지 않음. 제목 주장과 확인하려는 주장 방향이 다르면 교차검증 성공으로 처리하지 않음.
- 가격 반응 관찰: 발표 전 기준값과 이후5/15/30분, 동일 시장/세션/통화/피드·가격원천시각을 저장. IEX와SIP·지수현물과합성상품 비교는범위차이를명시. 데이터누락은0수익/0변동으로채우지않음. 시간상동반움직임을뉴스원인으로단정하지않음.
- 운영실 목표: 공급자별설정유무·마지막실제조회성공·원천시각·지연·오류코드·대체출처·TRL반영상태. 키등록/REST성공/WebSocket연속수신/공개게시/모의전략활용을별도단계로표시.
- 매매 반영은우선관찰기록으로검증. 뉴스추가만으로자동주문조건변경/실행자전환하지않음. PC꺼짐독립운영/브로커완전대사/중복주문방지검증완료로오인금지. 기존주문·타이머변경없음.
- 현재확인상태는상단실측기록유지: ECOS조회PASS,KRX401,Alpaca/Finnhub오라클결과대기,SEC연락처준비대기,LS보류. 이 절은실행계획이며신규구현·모든연결완료기록이아님.
