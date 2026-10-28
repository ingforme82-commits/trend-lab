"""실시간 속보 → 사이트 '주요 시황' 띠 · '실시간 속보·지수 반응' 칸 (1분마다 예약 실행)

  python tools/live_news.py          # 수집 → news.json → GitHub live 브랜치에 올리기
  python tools/live_news.py --dry    # 올리지 않고 화면에만 출력

소스
- 텔레그램: 속보 채널 3개는 1분마다, 등록된 채널 전체는 10분마다(tg_research/fast_news.py)
- 뉴스 사이트 RSS(5분마다): Seeking Alpha, CNBC, MarketWatch, Investing(영문·한국어), 연합뉴스 경제, 한국경제 증권

원칙
- 헤드라인 한 줄(140자)과 출처 이름만 싣는다. 사이트 방문자를 외부로 보내지 않도록 원문 링크는 넣지 않는다.
- 증권사 리포트·목표주가·종목 추천·광고 글은 뺀다(유사투자자문 방지).
- 지수 변화(속보 이후 나스닥100·코스피200·WTI)는 사이트에서 하이퍼리퀴드 분봉으로 계산한다.
"""

from __future__ import annotations

import base64
import email.utils
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TGR = Path(os.environ.get("TRL_TG_DIR", r"C:\projects\market-site\tg_research"))   # 텔레 수집기(메인 PC 전용)
TGR_PY = TGR / ".venv" / "Scripts" / "python.exe"
DB = TGR / "data" / "tgr.sqlite3"
REPO = "ingforme82-commits/trend-lab"
BRANCH = "live"
LOG = ROOT / "tools" / "live_news.log"
RSS_CACHE = ROOT / "tools" / "rss_cache.json"
KST = timezone(timedelta(hours=9))
NO_WINDOW = 0x08000000 if os.name == "nt" else 0     # 예약 실행 때 검은 창이 뜨지 않게

KEEP_H = 30
KEEP_H_STRAT = 48          # 증권사 시황·분석 글은 아침·마감에 몰려 있어 더 길게
MAX_STRAT = 80
MAX_ITEMS = 500
PER_SOURCE = {"김치터미널": 250}         # 출처별 최대 건수(나머지 출처는 PER_DEFAULT) — 2026-10-28 모든 채널 새 글 싣기로 늘림
PER_DEFAULT = 80

# 텔레그램 채널 → 사이트에 보일 출처 이름
CHANNELS = {
    "KimchiTerminal": "김치터미널", "cahier_de_market": "카이에 드 마켓", "realtime_stock_news": "실시간 주식뉴스",
    "YeouidoStory2": "여의도스토리", "Badonions": "나쁜양파", "one_going": "요약하는 고잉", "YoungTiger_stock": "영리한타이거",
    "corevalue": "가치투자클럽", "tRadarnewsdesk": "유안타 뉴스라운지", "yuantais": "유안타 투자전략", "yuantaresearch": "유안타 리서치",
    "YSKoreaSemi": "유안타 반도체", "kiwoom_semibat": "키움 반도체·2차전지", "anna7673": "유안타 2차전지", "growthbio": "그로쓰리서치",
    "huhpharm": "허혜민 제약바이오", "KB_EPC_MJ": "KB 건설", "HanaResearchTelecom": "하나 통신", "china_kis": "메리츠 중국",
    # 증권사 시황·전략·매크로 (2026-10-27 추가)
    "hedgecat0301": "키움 한지영(전략)", "HANAStrategy": "하나 주식전략", "HANA_Macro": "하나 매크로", "Meritz_strategy": "메리츠 투자전략",
    "stephenlee_meritz": "메리츠 매크로", "shStrategy": "신한 주식전략", "daishinstrategy": "대신 전략·시황", "eqmirae": "미래에셋 전략",
    "hanwhastrategy": "한화 투자전략", "lim_econ": "한화 경제", "hmsecstrat": "현대차 투자전략", "kisthemacro": "한투 매크로",
    "huhjae": "유진 허재환(전략)", "SK_Research_Asset": "SK 자산전략", "KiwoomResearch": "키움 리서치",
}
FAST = ("KimchiTerminal", "cahier_de_market", "realtime_stock_news")
REFRESH: dict = {}
# 시황·전략 글(긴 분석) — 제목 + 요약 한 줄로 싣고 '시황·전략'으로 묶는다
BROKER_STRAT = {"hedgecat0301", "HANAStrategy", "HANA_Macro", "Meritz_strategy", "stephenlee_meritz", "shStrategy", "daishinstrategy",
                "eqmirae", "hanwhastrategy", "lim_econ", "hmsecstrat", "kisthemacro", "huhjae", "SK_Research_Asset", "KiwoomResearch",
                "yuantais", "tRadarnewsdesk"}
ANALYSIS = {"cahier_de_market", "Badonions", "corevalue"}
# 개별 종목 매매 판단으로 읽힐 수 있는 글(모든 채널 공통으로 뺀다)
STOCKREC = re.compile(r"목표주가|목표가|TP\s|투자의견|BUY\b|매수\(유지\)|Outperform|Overweight|Underweight|비중\s?확대|비중\s?축소|"
                      r"상향 조정|하향 조정|커버리지 개시|Initiat", re.I)

# (출처 이름, 주소, 언어)
FEEDS = [
    ("Seeking Alpha", "https://seekingalpha.com/market_currents.xml", "en"),
    ("Seeking Alpha", "https://seekingalpha.com/feed.xml", "en"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "en"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "en"),
    ("Investing.com", "https://www.investing.com/rss/news_25.rss", "en"),
    ("인베스팅", "https://kr.investing.com/rss/news.rss", "ko"),
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml", "ko"),
    ("한국경제", "https://www.hankyung.com/feed/finance", "ko"),
    # 해외 원출처 직접 번역 (2026-10-27 추가)
    ("FT", "https://www.ft.com/markets?format=rss", "en"),
    ("FT", "https://www.ft.com/world?format=rss", "en"),
    ("BBC", "https://feeds.bbci.co.uk/news/business/rss.xml", "en"),
    ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "en"),
    ("가디언", "https://www.theguardian.com/business/rss", "en"),
    ("SCMP", "https://www.scmp.com/rss/92/feed", "en"),
    ("알자지라", "https://www.aljazeera.com/xml/rss/all.xml", "en"),
    ("CNBC", "https://www.cnbc.com/id/100727362/device/rss/rss.html", "en"),
    ("Oilprice", "https://oilprice.com/rss/main", "en"),
    ("미 연준", "https://www.federalreserve.gov/feeds/press_all.xml", "en"),
    ("미 EIA", "https://www.eia.gov/rss/todayinenergy.xml", "en"),
]

BROKER = re.compile(r"목표주가|목표가|TP\s|투자의견|BUY|매수\(유지\)|Preview|프리뷰|리서치센터|Analyst|\(02-\d|투자포인트|"
                    r"\[[^\]\n]*증권|상향 조정|하향 조정|비중\s?확대|비중\s?축소|Overweight|Underweight|Outperform|등급|"
                    r"price target|upgrade|downgrade|initiates|reiterate|Buy rating|Sell rating|top pick|stocks? to buy|"
                    r"should you buy|buy now|best stocks|stock to watch|stock picks?|stocks with|how to invest|dividend stocks|undervalued", re.I)
JUNK = re.compile(r"광고|이벤트|구독|무료\s?리딩|수익\s?보장|가입|추천주|급등주|리딩방|쿠폰|할인|sponsored|podcast|webinar|at close of trade|stocks (?:higher|lower) at close"
                  # 자기 홍보 말투(2026-10-28): 채널 오픈 안내 · "저희가/저희 채널" · 관심·참여 부탁 · 입장 링크
                  r"|채널\s*(?:을|를)?\s*(?:새로\s*)?오픈|오픈했습니다|저희\s?(?:채널|팀)|저희가\s*이번에|관심\s*부탁|많관부|입장\s*(?:하기|링크|방법)|문의\s*주세요", re.I)
TAGS = [
    ("중동·유가", r"이란|이스라엘|호르무즈|후티|사우디|카타르|레바논|헤즈볼라|유가|원유|WTI|브렌트|OPEC|오펙|천연가스|LNG|정유|핵무기|핵 활동|NPT|우라늄|"
                r"\bIran|Israel|Hormuz|Houthi|Saudi|\boil\b|crude|Brent|OPEC|natural gas"),
    ("연준·금리", r"연준|Fed\b|FOMC|파월|금리|국채|채권|CPI|PCE|물가|고용지표|비농업|실업|재무부|바이백|달러|Treasury|yield|inflation|payroll|Powell|rate cut|rate hike"),
    ("AI·빅테크", r"앤스로픽|앤트로픽|Anthropic|OpenAI|오픈AI|엔비디아|NVIDIA|Nvidia|마이크로소프트|Microsoft|MSFT|알파벳|Alphabet|구글|Google|메타|Meta\b|"
                 r"아마존|Amazon|애플|Apple|테슬라|Tesla|스페이스X|SpaceX|xAI|\bAI\b|데이터센터|data center|GPU|IPO|상장"),
    ("반도체", r"반도체|하이닉스|삼성전자|이오테크닉스|디아이티|제주반도체|코미코|하나마이크론|SK스퀘어|마이크론|Micron|TSMC|HBM|메모리|D램|DRAM|낸드|NAND|SOX|램리서치|ASML|chip|semiconductor"),
    ("사이버보안", r"해킹|해커|유출|사이버|보안|랜섬|hack|breach|cyber|ransomware|security|시스코|Cisco|크라우드스트라이크|CrowdStrike|"
                 r"팔로알토|Palo Alto|지스케일러|Zscaler|옥타|Okta|클라우드플레어|Cloudflare|포티넷|Fortinet|데이터도그|Datadog|센티넬원|SentinelOne|"
                 r"루브릭|Rubrik|세일포인트|SailPoint"),
    ("코인", r"비트코인|이더리움|코인|암호화폐|가상자산|Coinbase|코인베이스|월렛|bitcoin|crypto|ether"),
    ("러·우", r"러시아|우크라|푸틴|젤렌스키|크렘린|스타링크|Russia|Ukrain|Putin|Kremlin"),
    ("한국", r"코스피|코스닥|한국|원/달러|원화|한은|KOSPI|Korea"),
    ("환율", r"환율|원/달러|달러/원|원화|엔화|엔/달러|달러/엔|위안화|달러인덱스|DXY|외환|yen|currency|forex"),
    ("원전", r"원전|원자력|SMR|소형모듈원자로|두산에너빌리티|한전기술|우라늄|nuclear|Oklo|오클로|NuScale|뉴스케일|Constellation|Cameco"),
    ("방산", r"방산|방위산업|K9|K2 전차|레드백|천무|한화에어로|LIG넥스원|현대로템|한국항공우주|KAI|Lockheed|록히드|Raytheon|defense contractor"),
    ("조선", r"조선|선박|LNG선|컨테이너선|수주|HD현대중공업|한화오션|삼성중공업|HD한국조선|케이프|한국카본|동성화인텍|세진중공업|성광벤드|보냉재|기자재|선박엔진|shipbuild|MASGA|마스가"),
    ("2차전지", r"2차전지|이차전지|배터리|양극재|음극재|리튬|ESS|LG에너지|삼성SDI|에코프로|포스코퓨처엠|POSCO홀딩스|포스코홀딩스|엔켐|코스모신소재|대주전자재료|천보|battery|lithium"),
    ("바이오", r"바이오|제약|신약|임상|FDA|비만|ADC|biotech|pharma"),
    ("지수", r"나스닥|S&P|다우|선물|지수|VIX|Nasdaq|Dow\b|S&P 500|futures|stocks|Wall Street"),
]
HOT = re.compile(r"속보|긴급|Breaking|사상 최고|사상최고|급등|급락|폭락|폭등|공격|미사일|공습|휴전|합의|핵무기|해킹|IPO|파산|"
                 r"금리 (?:인상|인하)|서킷|사이드카|최고치|최저치|record high|plunge|soar|surge|tumble|ceasefire|missile|attack|"
                 r"bankrupt|hack|rate cut|rate hike|all-time high", re.I)


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(KST):%m-%d %H:%M} {msg}\n")


def refresh() -> None:
    """텔레 받기: 1분마다 속보 채널 3개, 10분마다(분이 0으로 끝날 때) 전체 채널."""
    if not TGR_PY.exists():
        return
    args = [str(TGR_PY), "fast_news.py"] + (["--all"] if datetime.now(KST).minute % 10 == 0 else [])
    subprocess.run(args, cwd=TGR, capture_output=True, timeout=55,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=NO_WINDOW)


BYLINE = re.compile(r"☎|☏|T\.\s?\d|\d{2,3}-\d{3,4}-\d{4}|@\w|애널리스트|Analyst|자료\s?링크|링크\s?[:▶]|^[-=_]{3,}$|"
                    r"^\W*\[[^\]]{0,40}(증권|리서치|전략|매크로|퀀트|Research)[^\]]*\]\W*$|^\W*(안녕하세요|안녕하십니까)", re.I)


def _lines(text: str) -> list[str]:
    t = re.sub(r"https?://\S+", "", text or "")
    t = re.sub(r"[*_`#>]+", "", t)
    out = []
    for ln in t.splitlines():
        s = re.sub(r"\s+", " ", ln).strip(" -—:•▶►▷◆◇■□※·")
        if len(s) < 6 or BYLINE.search(s):
            continue
        out.append(s)
    return out


def clean_line(text: str, with_sub: bool = False) -> tuple[str, str, str]:
    """(제목, 요약 한 줄). 작성자·연락처·인사말 줄은 건너뛴다."""
    lines = _lines(text)
    while lines and re.fullmatch(r"\[[^\]]{1,40}\]", lines[0]):
        lines.pop(0)
    if not lines:
        return "", "", ""
    h, rest = lines[0], lines[1:]
    if len(h) < 25 and rest:                      # '$TSLA -' 같은 머리말만 있으면 다음 줄 이어 붙임
        h, rest = f"{h} {rest[0]}", rest[1:]
    # 맨 앞 '📮[메리츠증권 퀀트/ETF 이상현]' 같은 작성자 표기 떼기(남는 글이 충분할 때만)
    h2 = re.sub(r"^\W*\[[^\]]{1,40}\]\s*", "", h)
    h = h2 if len(h2) >= 12 else h
    orig = ""
    mo = re.search(r"\s*[—–]\s*([A-Za-z][\w .&']{1,30}|[가-힣][가-힣A-Za-z ]{1,14})$", h) or re.search(r":\s*([A-Z]{2,8})$", h)
    if mo:                                         # 끝의 '— Fox News', ': ISNA' 같은 원출처 꼬리 → 따로 보관
        orig, h = mo.group(1).strip(), h[:mo.start()]
    h = h.strip(" -—:")
    sub = ""
    if with_sub:
        for r in rest:
            if len(r) >= 15 and r not in h:
                sub = r[:120] + ("…" if len(r) > 120 else "")
                break
    return h[:140] + ("…" if len(h) > 140 else ""), sub, orig


def tags_of(text: str) -> list[str]:
    return [n for n, pat in TAGS if re.search(pat, text[:500])][:2]


URL_ONLY = re.compile(r"^\s*(https?://\S+)\s*$")


def link_title(url: str):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from linktitle import title_for
        return title_for(url)
    except Exception:  # noqa: BLE001
        return None


def from_telegram() -> list[dict]:
    if not DB.exists():
        return []
    con = sqlite3.connect(str(DB))
    since = (datetime.now(timezone.utc) - timedelta(hours=KEEP_H_STRAT)).isoformat()
    cut = datetime.now(timezone.utc) - timedelta(hours=KEEP_H)
    q = f"select channel_username, posted_at, text, collected_at from messages where posted_at >= ? and channel_username in ({','.join('?' * len(CHANNELS))})"
    out = []
    for ch, posted, text, collected in con.execute(q, (since, *CHANNELS)):
        if ch not in BROKER_STRAT and ch not in ANALYSIS and datetime.fromisoformat(posted) < cut:
            continue                                   # 시황·전략 글만 48시간, 나머지는 30시간
        if not text or STOCKREC.search(text) or JUNK.search(text):
            continue
        strat, analysis = ch in BROKER_STRAT, ch in ANALYSIS
        if not (strat or analysis):
            # 일반 채널: 증권사 리포트 머리말·링크 모음·보고서 모음 글은 뺀다
            if BROKER.search(text) or len(re.findall(r"https?://", text)) >= 3 or text.lstrip().startswith("<"):
                continue
        h, sub, orig = clean_line(text, with_sub=strat or analysis)
        lm = URL_ONLY.match(text)
        if lm:                                          # 링크만 올린 글 → 기사 제목·언론사(링크는 싣지 않음)
            got_t = link_title(lm.group(1))
            if not got_t:
                continue
            h, orig = got_t
        if len(h) < 12 or re.fullmatch(r"[\w.\-]+\.(?:com|co\.kr|kr|net|io)", h, re.I):   # 사이트 주소만 있는 글
            continue
        tg = tags_of(text)
        # 시장 키워드가 없는 글도 싣는다('기타', 중요도 낮게) — 2026-10-28 운영자 요청
        ts = datetime.fromisoformat(posted).astimezone(timezone.utc)
        try:
            got = int(datetime.fromisoformat(collected).astimezone(timezone.utc).timestamp() * 1000)
        except Exception:  # noqa: BLE001
            got = None
        it = {"ts": int(ts.timestamp() * 1000), "got": got, "src": CHANNELS[ch],
              "kind": "증권사 시황" if strat else "시황 분석" if analysis else "텔레그램",
              "text": h, "tags": tg or (["시황"] if strat or analysis else ["기타"]), "hot": bool(HOT.search(h))}
        if sub:
            it["sub"] = sub
        if orig:
            it["osrc"] = orig                          # 원출처(예: Fox News) — 화면에 '○○ · 김치터미널 경유'로 표시
        out.append(it)
    return out


def fetch_rss() -> list[dict]:
    """RSS는 5분마다만 새로 받고, 그 사이에는 저장해 둔 것을 쓴다."""
    try:
        cache = json.loads(RSS_CACHE.read_text(encoding="utf-8"))
        if datetime.now(timezone.utc).timestamp() - cache["at"] < 280:
            RSS_HEALTH.update(cache.get("health", {}))
            return cache["items"]
    except Exception:  # noqa: BLE001
        cache = {"items": []}
    ok, fail = [], []
    items, cutoff = [], datetime.now(timezone.utc) - timedelta(hours=KEEP_H)
    for name, url, lang in FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (TrendResearchLab news reader)"})
            root = ET.fromstring(urllib.request.urlopen(req, timeout=12).read())
        except Exception as e:  # noqa: BLE001
            log(f"RSS 실패 {name}: {type(e).__name__}")
            fail.append(name)
            continue
        ok.append(name)
        for it in root.iter("item"):
            title = unescape(re.sub(r"<[^>]+>", "", (it.findtext("title") or "")).strip())
            pub = it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date") or ""
            try:
                dt = email.utils.parsedate_to_datetime(pub) if "," in pub else datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=KST if lang == "ko" else timezone.utc)
            except Exception:  # noqa: BLE001
                continue
            if dt < cutoff or len(title) < 12 or BROKER.search(title) or JUNK.search(title):
                continue
            tg = tags_of(title)
            if not tg:                                  # 시장과 관계없는 일반 기사는 뺀다
                continue
            h = re.sub(r"\s+", " ", title)
            items.append({"ts": int(dt.timestamp() * 1000), "src": name, "kind": "해외 뉴스" if lang == "en" else "뉴스",
                          "lang": lang, "text": h[:140] + ("…" if len(h) > 140 else ""), "tags": tg, "hot": bool(HOT.search(h))})
    health = {"at": int(datetime.now(timezone.utc).timestamp() * 1000), "ok": len(ok), "fail": fail, "total": len(FEEDS)}
    RSS_HEALTH.update(health)
    if items:
        RSS_CACHE.write_text(json.dumps({"at": datetime.now(timezone.utc).timestamp(), "items": items, "health": health}, ensure_ascii=False), encoding="utf-8")
        return items
    return cache["items"]


TR_CACHE = ROOT / "tools" / "translate_cache.json"
SEEN_CACHE = ROOT / "tools" / "seen_cache.json"         # RSS 기사 첫 수집 시각(보도 시각과 구분)
RSS_HEALTH: dict = {}


def _claude_translate(titles: list[str]) -> dict[str, str]:
    """Claude(크레딧이 있을 때만). 실패하면 빈 dict — 키 값은 tg_research/.env에서 읽고 출력하지 않는다."""
    env = TGR / ".env"
    key = ""
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        return {}
    body = {"model": "claude-haiku-5-5", "max_tokens": 4000, "messages": [{"role": "user", "content":
            "다음 영문 금융 뉴스 헤드라인을 자연스러운 한국어 뉴스 제목으로 번역해. 회사명·티커는 원문 유지, 과장 없이. "
            "입력과 같은 순서의 JSON 문자열 배열만 출력해.\n" + json.dumps(titles, ensure_ascii=False)}]}
    try:
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                     headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        out = json.loads(urllib.request.urlopen(req, timeout=40).read())["content"][0]["text"]
        arr = json.loads(out[out.index("["): out.rindex("]") + 1])
        return {t: k for t, k in zip(titles, arr) if isinstance(k, str) and k.strip()}
    except Exception:  # noqa: BLE001  (크레딧 없음 등)
        return {}


def _google_translate(title: str) -> str:
    import urllib.parse
    u = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": title})
    r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read())
    return "".join(x[0] for x in r[0] if x and x[0]).strip()


# 무료 번역이 자주 틀리는 고유명사: (영문, 잘못된 번역들, 바른 표기)
GLOSSARY = [("Anthropic", ("인류학적", "인류학", "인류의", "인류"), "앤트로픽"), ("Apple", ("사과",), "애플"),
            ("Shell", ("껍데기", "쉘"), "셸"), ("Target", ("표적", "목표"), "타깃"), ("Snap", ("스냅",), "스냅"),
            ("Fed", ("먹이를 주었다", "먹인"), "연준"), ("Brent", ("브렌트",), "브렌트")]


def fix_terms(en: str, ko: str) -> str:
    for word, wrongs, right in GLOSSARY:
        if re.search(r"\b" + word + r"\b", en) and right not in ko:
            for w in wrongs:
                if w in ko:
                    ko = ko.replace(w, right, 1)
                    break
    return ko


def translate(items: list[dict]) -> None:
    """영문 헤드라인을 한국어로 바꾼다(원문은 orig에 보관). 번역은 저장해 두고 다시 하지 않는다."""
    try:
        cache = json.loads(TR_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cache = {}
    todo = list(dict.fromkeys(it["text"] for it in items if it.get("lang") == "en" and it["text"] not in cache))
    if todo:
        got = {}
        if cache.get("_claude_off_until", 0) < datetime.now(timezone.utc).timestamp():
            got = _claude_translate(todo[:60])
            if not got:                                   # 크레딧 없음 → 1시간 동안 Claude 시도 안 함
                cache["_claude_off_until"] = datetime.now(timezone.utc).timestamp() + 3600
        for t in todo[:80]:
            if t not in got:
                try:
                    got[t] = _google_translate(t)
                except Exception:  # noqa: BLE001
                    pass
        cache.update({k: v for k, v in got.items() if v})
        keep = {it["text"] for it in items}
        cache = {k: v for k, v in cache.items() if k in keep or k.startswith("_")}   # 오래된 번역 정리
        TR_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    for it in items:
        if it.get("lang") == "en" and cache.get(it["text"]):
            it["orig"], it["text"] = it["text"], fix_terms(it["text"], cache[it["text"]].rstrip(".。 "))
            it["tr"] = "auto"                               # 자동 번역(원문은 orig)
        elif it.get("lang") == "en":
            it["tr"] = "fail"                               # 번역 실패 → 영문 원문 그대로


def mark_seen(items: list[dict]) -> None:
    """RSS 기사는 수집 시각이 없으므로 이 컴퓨터가 처음 본 시각을 기록해 got 으로 붙인다(3일 보관)."""
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    try:
        seen = json.loads(SEEN_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        seen = {"_boot": now}                            # 첫 실행: 이미 있던 기사는 수집 시각을 알 수 없음(0)
    boot = seen.get("_boot", 0)
    for it in items:
        k = f"{it['src']}|{it['ts']}|{it.get('orig') or it['text']}"[:200]
        if k not in seen:
            seen[k] = 0 if now - boot < 120_000 else now
        it["got"] = max(seen[k], it["ts"]) if seen[k] else None
    seen = {k: v for k, v in seen.items() if k == "_boot" or (v and now - v < 3 * 86400_000) or (not v and now - boot < 3 * 86400_000)}
    SEEN_CACHE.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")


def bigrams(s: str) -> set[str]:
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s.lower())
    return {s[i:i + 2] for i in range(len(s) - 1)}


def build() -> dict:
    rss = fetch_rss()
    translate(rss)
    sector_items, sector_cards = [], []
    try:                                                  # 섹터 시세 감시(가격 변화를 뉴스처럼)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sector_watch import run as sector_run
        sector_items, sector_cards = sector_run()
    except Exception as e:  # noqa: BLE001
        log(f"섹터 감시 건너뜀: {type(e).__name__}: {e}")
    leaders = None
    try:                                                  # 🏁 오늘의 주도 섹터(자동, 한국 업종·테마 / 미국 업종)
        from leaders import build as leaders_build, changes as leaders_changes
        leaders = leaders_build()
        umap = (leaders.get("us") or {}).pop("map", {}) or {}
        for c in sector_cards:                            # 미국 종목에도 시가총액·거래대금(네이버) → 화면 정렬
            for r in c.get("rows", []):
                m = umap.get(r.get("sym"))
                if m and r.get("cur") != "KRW":
                    r.setdefault("mcap", m["mcap"]); r.setdefault("val", m["val"])
        t_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        for ch in leaders_changes(leaders):
            sector_items.append({"ts": t_ms, "got": t_ms, "src": "트렌드랩 자동 집계", "kind": "주도 섹터", "text": ch["text"],
                                 "tags": ["한국" if ch["mkt"] == "kr" else "미국"], "hot": True})
    except Exception as e:  # noqa: BLE001
        log(f"주도 섹터 건너뜀: {type(e).__name__}: {e}")
    tg_items = from_telegram()
    mark_seen(rss)
    from newsgroup import group
    allitems = group(tg_items + rss + sector_items)          # 같은 사건은 하나로(최초 보도 기준, 후속 출처는 also)
    items, per = [], {}
    n_strat = n_other = 0
    for it in allitems:
        strat = it.get("kind") in ("증권사 시황", "시황 분석")
        if (strat and n_strat >= MAX_STRAT) or (not strat and n_other >= MAX_ITEMS):
            continue
        if per.get(it["src"], 0) >= PER_SOURCE.get(it["src"], PER_DEFAULT):   # 한 출처가 목록을 다 차지하지 않게
            continue
        items.append(it)
        per[it["src"]] = per.get(it["src"], 0) + 1
        if strat:
            n_strat += 1
        else:
            n_other += 1
    try:                                                  # 📊 중요도(0~100, 상·중·하) — 변곡점·교차 확인 결과까지 반영되도록 아래에서 한 번 더
        from importance import apply as importance
        importance(items)
    except Exception as e:  # noqa: BLE001
        log(f"중요도 건너뜀: {type(e).__name__}: {e}")
    try:                                                  # 🌐 김치터미널 속보 ↔ 해외 언론 원문 헤드라인 교차 확인
        from xcheck import run as xcheck
        xcheck(items, rss, lambda en: fix_terms(en, _google_translate(en)))
    except Exception as e:  # noqa: BLE001
        log(f"외신 교차 확인 건너뜀: {type(e).__name__}: {e}")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    tg_last = max((i["ts"] for i in tg_items if i["src"] in {CHANNELS[c] for c in FAST if c in CHANNELS}), default=0)
    tg_got = max((i.get("got") or 0 for i in tg_items), default=0)
    en = [i for i in items if i.get("lang") == "en"]
    out = {"updated": now_ms, "items": items, "moves": [], "series": {}, "sectors": sector_cards, "leaders": leaders,
           "health": {"tg": {"last": tg_last, "got": tg_got, "refresh": REFRESH.get("ok"), "n": len(tg_items)},
                      "rss": dict(RSS_HEALTH), "tr": {"auto": sum(1 for i in en if i.get("tr") == "auto"), "fail": sum(1 for i in en if i.get("tr") == "fail")},
                      "groups": sum(1 for i in items if i.get("also"))}}
    try:                                                  # 변곡점 감지 + 직전 뉴스 연결(실패해도 속보는 그대로)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from moves import analyze
        out["moves"], out["series"] = analyze(items)
    except Exception as e:  # noqa: BLE001
        log(f"변곡점 감지 건너뜀: {type(e).__name__}: {e}")
    try:                                                  # 해외 지수·화제 종목·많이 나온 종목
        from market_extra import dow, kr_now, reg_quotes, trending, us10y, ust, world_and_spot
        out["world"], out["spot"] = world_and_spot()
        out["dow"] = dow()
        out["us10y"] = us10y()
        out["ust"] = ust()
        try:
            from official import build as official
            out["official"] = official()
        except Exception as e:  # noqa: BLE001
            log(f"공식 데이터 건너뜀: {type(e).__name__}: {e}")
        out["kr"] = kr_now()
        out["reg"] = reg_quotes()
        try:
            from leadership import public as momentum
            out["momentum"] = momentum(sector_cards)
        except Exception as e:  # noqa: BLE001
            log(f"섹터 모멘텀 건너뜀: {type(e).__name__}: {e}")
        try:
            from levetf import build as lev
            out["lev"] = lev()
        except Exception as e:  # noqa: BLE001
            log(f"SOXL·KORU 점검 건너뜀: {type(e).__name__}: {e}")
        try:
            from watch import build as watch
            out["watch"] = watch()
            for e in (out["watch"] or {}).get("events", [])[:12]:          # 관전 포인트 조건 전환 → 속보 목록에도
                out["items"].append({"ts": e["ts"], "got": e["ts"], "src": "트렌드랩 자동 집계", "kind": "관전 포인트",
                                     "text": "👀 " + e["text"] + (f" · 오늘 {e['n']}번째 전환" if e.get("n", 1) > 1 else ""), "tags": ["반도체" if e["sym"] == "SOXL" else "한국", "지수"], "hot": True})
            out["items"].sort(key=lambda i: -i["ts"])
        except Exception as e:  # noqa: BLE001
            log(f"관전 포인트 건너뜀: {type(e).__name__}: {e}")
        try:
            from flows import build as flows
            out["flows"] = flows()
        except Exception as e:  # noqa: BLE001
            log(f"주도주 수급 건너뜀: {type(e).__name__}: {e}")
        try:
            from s7 import build as s7
            out["s7"] = s7()
        except Exception as e:  # noqa: BLE001
            log(f"S7 건너뜀: {type(e).__name__}: {e}")
        out["trending"] = trending(items)
    except Exception as e:  # noqa: BLE001
        log(f"해외 지수·종목 건너뜀: {type(e).__name__}: {e}")
    try:                                                  # 📊 중요도 최종(변곡점 pivot·관전 포인트 반영)
        from importance import apply as importance
        importance(out["items"])
    except Exception as e:  # noqa: BLE001
        log(f"중요도 건너뜀: {type(e).__name__}: {e}")
    try:                                                  # 📋 시장 브리핑(사이트 표시용 요약)
        from brief import make as make_brief
        out["brief"] = make_brief(out)
    except Exception as e:  # noqa: BLE001
        log(f"브리핑 건너뜀: {type(e).__name__}: {e}")
    return out


def gh(*args: str, input_: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, input=input_, encoding="utf-8", creationflags=NO_WINDOW)


def ensure_branch() -> None:
    if gh("api", f"repos/{REPO}/branches/{BRANCH}").returncode == 0:
        return
    sha = json.loads(gh("api", f"repos/{REPO}/git/ref/heads/main").stdout)["object"]["sha"]
    gh("api", "-X", "POST", f"repos/{REPO}/git/refs", "-f", f"ref=refs/heads/{BRANCH}", "-f", f"sha={sha}")


def upload(data: dict) -> bool:
    try:
        return _upload(data)
    except RuntimeError as e:
        if "409" in str(e) or "does not match" in str(e):   # 다른 실행과 겹침 → 최신 파일 기준으로 한 번 더
            return _upload(data)
        raise


def _upload(data: dict) -> bool:
    ensure_branch()
    cur = gh("api", f"repos/{REPO}/contents/news.json?ref={BRANCH}")
    sha, old = None, None
    if cur.returncode == 0:
        j = json.loads(cur.stdout)
        sha = j["sha"]
        try:
            old = json.loads(base64.b64decode(j["content"]).decode("utf-8"))
        except Exception:  # noqa: BLE001
            old = None
    if old and all(old.get(k) == data.get(k) for k in ("items", "moves", "world", "spot", "trending", "sectors", "dow", "us10y", "ust", "kr", "momentum", "flows", "s7", "leaders", "watch", "lev", "official")):
        return False                                   # 바뀐 글 없음 → 커밋 안 함
    body = {"message": f"속보 갱신 {datetime.now(KST):%m-%d %H:%M}", "branch": BRANCH,
            "content": base64.b64encode(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode()}
    if sha:
        body["sha"] = sha
    r = gh("api", "-X", "PUT", f"repos/{REPO}/contents/news.json", "--input", "-", input_=json.dumps(body))
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return True


def main() -> None:
    dry = "--dry" in sys.argv
    if not dry:
        try:
            refresh()
            REFRESH["ok"] = True
        except Exception as e:  # noqa: BLE001  (텔레 수집이 늦어도 저장된 글과 RSS로 계속 진행)
            REFRESH["ok"] = False
            log(f"텔레 수집 건너뜀: {type(e).__name__}")
    data = build()
    if dry:
        from collections import Counter
        for it in data["items"][:40]:
            t = datetime.fromtimestamp(it["ts"] / 1000, KST)
            print(f"{t:%m/%d %H:%M} [{it['src']}][{'/'.join(it['tags'])}]{' 🔴' if it['hot'] else ''} {it['text']}")
        print(f"총 {len(data['items'])}건", Counter(i["src"] for i in data["items"]).most_common())
        return
    try:
        changed = upload(data)
        log(f"{len(data['items'])}건 {'올림' if changed else '변화 없음'}")
    except Exception as e:  # noqa: BLE001
        log(f"실패: {e}")


if __name__ == "__main__":
    main()
