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
MAX_ITEMS = 200
PER_SOURCE = {"김치터미널": 90}          # 출처별 최대 건수(나머지 출처는 30)

# 텔레그램 채널 → 사이트에 보일 출처 이름
CHANNELS = {
    "KimchiTerminal": "김치터미널", "cahier_de_market": "카이에 드 마켓", "realtime_stock_news": "실시간 주식뉴스",
    "YeouidoStory2": "여의도스토리", "Badonions": "나쁜양파", "one_going": "요약하는 고잉", "YoungTiger_stock": "영리한타이거",
    "corevalue": "가치투자클럽", "tRadarnewsdesk": "유안타 뉴스라운지", "yuantais": "유안타 투자전략", "yuantaresearch": "유안타 리서치",
    "YSKoreaSemi": "유안타 반도체", "kiwoom_semibat": "키움 반도체·2차전지", "anna7673": "유안타 2차전지", "growthbio": "그로쓰리서치",
    "huhpharm": "허혜민 제약바이오", "KB_EPC_MJ": "KB 건설", "HanaResearchTelecom": "하나 통신", "china_kis": "메리츠 중국",
}
FAST = ("KimchiTerminal", "cahier_de_market", "realtime_stock_news")

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
]

BROKER = re.compile(r"목표주가|목표가|TP\s|투자의견|BUY|매수\(유지\)|Preview|프리뷰|리서치센터|Analyst|\(02-\d|투자포인트|"
                    r"\[[^\]\n]*증권|상향 조정|하향 조정|비중\s?확대|비중\s?축소|Overweight|Underweight|Outperform|등급|"
                    r"price target|upgrade|downgrade|initiates|reiterate|Buy rating|Sell rating|top pick|stocks? to buy|"
                    r"should you buy|buy now|best stocks|stock to watch|stock picks?|stocks with|how to invest|dividend stocks|undervalued", re.I)
JUNK = re.compile(r"광고|이벤트|구독|무료\s?리딩|수익\s?보장|가입|추천주|급등주|리딩방|쿠폰|할인|sponsored|podcast|webinar", re.I)
TAGS = [
    ("중동·유가", r"이란|이스라엘|호르무즈|후티|사우디|카타르|레바논|헤즈볼라|유가|원유|WTI|브렌트|OPEC|오펙|천연가스|LNG|정유|핵무기|핵 활동|NPT|우라늄|"
                r"\bIran|Israel|Hormuz|Houthi|Saudi|\boil\b|crude|Brent|OPEC|natural gas"),
    ("연준·금리", r"연준|Fed\b|FOMC|파월|금리|국채|채권|CPI|PCE|물가|고용지표|비농업|실업|재무부|바이백|달러|Treasury|yield|inflation|payroll|Powell|rate cut|rate hike"),
    ("AI·빅테크", r"앤스로픽|앤트로픽|Anthropic|OpenAI|오픈AI|엔비디아|NVIDIA|Nvidia|마이크로소프트|Microsoft|MSFT|알파벳|Alphabet|구글|Google|메타|Meta\b|"
                 r"아마존|Amazon|애플|Apple|테슬라|Tesla|스페이스X|SpaceX|xAI|\bAI\b|데이터센터|data center|GPU|IPO|상장"),
    ("반도체", r"반도체|하이닉스|삼성전자|마이크론|Micron|TSMC|HBM|메모리|D램|DRAM|낸드|NAND|SOX|램리서치|ASML|chip|semiconductor"),
    ("보안·코인", r"해킹|해커|유출|사이버|보안|비트코인|이더리움|코인|암호화폐|가상자산|Coinbase|코인베이스|월렛|거래소|hack|breach|bitcoin|crypto"),
    ("러·우", r"러시아|우크라|푸틴|젤렌스키|크렘린|스타링크|Russia|Ukrain|Putin|Kremlin"),
    ("한국", r"코스피|코스닥|한국|원/달러|원화|한은|KOSPI|Korea"),
    ("2차전지·바이오", r"2차전지|이차전지|배터리|양극재|리튬|ESS|바이오|제약|신약|임상|FDA|battery|biotech"),
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


def clean_line(text: str) -> str:
    t = re.sub(r"https?://\S+", "", text or "")
    t = re.sub(r"[*_`#>]+", "", t)
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    # 머리말 줄 버리기: '[키움 이차전지 권준수]' 같은 작성자 표기, 너무 짧은 줄
    while lines and (re.fullmatch(r"\[[^\]]{1,40}\]", lines[0]) or len(lines[0]) < 6):
        lines.pop(0)
    if not lines:
        return ""
    h = lines[0]
    if len(h) < 25 and len(lines) > 1:            # '$TSLA -' 같은 머리말만 있으면 다음 줄 이어 붙임
        h = f"{h} {lines[1]}"
    h = re.sub(r"\s+", " ", h).strip(" -—:")
    h = re.sub(r"\s*—\s*[A-Za-z][\w .&]{1,30}$", "", h)  # 끝의 '— Fox News' 같은 외부 출처 꼬리 제거
    return h[:140] + ("…" if len(h) > 140 else "")


def tags_of(text: str) -> list[str]:
    return [n for n, pat in TAGS if re.search(pat, text[:500])][:2]


def from_telegram() -> list[dict]:
    if not DB.exists():
        return []
    con = sqlite3.connect(str(DB))
    since = (datetime.now(timezone.utc) - timedelta(hours=KEEP_H)).isoformat()
    q = f"select channel_username, posted_at, text from messages where posted_at >= ? and channel_username in ({','.join('?' * len(CHANNELS))})"
    out = []
    for ch, posted, text in con.execute(q, (since, *CHANNELS)):
        if not text or BROKER.search(text) or JUNK.search(text):
            continue
        if len(re.findall(r"https?://", text)) >= 3 or text.lstrip().startswith("<"):   # 링크 모음·보고서 모음 글
            continue
        h = clean_line(text)
        if len(h) < 12:
            continue
        tg = tags_of(text)
        if ch not in FAST and not tg:                  # 섹터 채널은 시장 관련 키워드가 있는 글만
            continue
        ts = datetime.fromisoformat(posted).astimezone(timezone.utc)
        out.append({"ts": int(ts.timestamp() * 1000), "src": CHANNELS[ch], "kind": "텔레그램", "text": h,
                    "tags": tg or ["기타"], "hot": bool(HOT.search(h))})
    return out


def fetch_rss() -> list[dict]:
    """RSS는 5분마다만 새로 받고, 그 사이에는 저장해 둔 것을 쓴다."""
    try:
        cache = json.loads(RSS_CACHE.read_text(encoding="utf-8"))
        if datetime.now(timezone.utc).timestamp() - cache["at"] < 280:
            return cache["items"]
    except Exception:  # noqa: BLE001
        cache = {"items": []}
    items, cutoff = [], datetime.now(timezone.utc) - timedelta(hours=KEEP_H)
    for name, url, lang in FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (TrendResearchLab news reader)"})
            root = ET.fromstring(urllib.request.urlopen(req, timeout=12).read())
        except Exception as e:  # noqa: BLE001
            log(f"RSS 실패 {name}: {type(e).__name__}")
            continue
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
    if items:
        RSS_CACHE.write_text(json.dumps({"at": datetime.now(timezone.utc).timestamp(), "items": items}, ensure_ascii=False), encoding="utf-8")
        return items
    return cache["items"]


def bigrams(s: str) -> set[str]:
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s.lower())
    return {s[i:i + 2] for i in range(len(s) - 1)}


def build() -> dict:
    allitems = sorted(from_telegram() + fetch_rss(), key=lambda x: -x["ts"])
    items, seen, per = [], [], {}
    for it in allitems:
        if per.get(it["src"], 0) >= PER_SOURCE.get(it["src"], 30):   # 한 출처가 목록을 다 차지하지 않게
            continue
        g = bigrams(it["text"])
        if any(len(g & s) / max(1, len(g | s)) >= 0.5 for s in seen):   # 같은 소식이 여러 곳에 올라온 경우 한 번만
            continue
        seen.append(g)
        items.append(it)
        per[it["src"]] = per.get(it["src"], 0) + 1
        if len(items) >= MAX_ITEMS:
            break
    return {"updated": int(datetime.now(timezone.utc).timestamp() * 1000), "items": items}


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
    if old and old.get("items") == data["items"]:
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
        refresh()
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
