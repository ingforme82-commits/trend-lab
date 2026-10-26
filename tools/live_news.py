"""텔레그램 속보 → 사이트 '실시간 속보' 칸 (10분마다 예약 실행)

  python tools/live_news.py          # 텔레 새로고침 → news.json 만들기 → GitHub live 브랜치에 올리기
  python tools/live_news.py --dry    # 올리지 않고 화면에만 출력

- 사이트는 raw.githubusercontent.com/.../live/news.json 을 읽는다(Pages 다시 빌드 없음, 최대 몇 분 캐시).
- 뉴스 채널의 '헤드라인'만 짧게(140자) 출처·원문 링크와 함께 싣는다. 증권사 리포트·목표주가·종목 추천 글은 뺀다.
- 지수 변화(속보 이후 나스닥100·코스피200·WTI 등락)는 사이트에서 하이퍼리퀴드 분봉으로 계산한다.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TGR = Path(os.environ.get("TRL_TG_DIR", r"C:\projects\market-site\tg_research"))   # 텔레 수집기(메인 PC 전용)
TGR_PY = TGR / ".venv" / "Scripts" / "python.exe"
DB = TGR / "data" / "tgr.sqlite3"
REPO = "ingforme82-commits/trend-lab"
BRANCH = "live"
LOG = Path(__file__).resolve().parents[1] / "tools" / "live_news.log"
KST = timezone(timedelta(hours=9))

CHANNELS = {"KimchiTerminal": "김치 텔레그램", "cahier_de_market": "카이에 드 마켓", "realtime_stock_news": "실시간 뉴스"}
KEEP_H = 36
MAX_ITEMS = 80

BROKER = re.compile(r"목표주가|목표가|TP\s|투자의견|BUY|Buy|매수\(유지\)|Preview|프리뷰|리서치센터|Analyst|\(02-\d|투자포인트|"
                    r"\[[^\]\n]*증권|상향 조정|하향 조정|비중 확대|비중 축소|Overweight|Underweight|Outperform|등급")
JUNK = re.compile(r"광고|이벤트|구독|무료\s?리딩|수익\s?보장|가입|추천주|급등주|리딩방")
TAGS = [
    ("중동·유가", r"이란|이스라엘|호르무즈|후티|사우디|카타르|레바논|헤즈볼라|유가|원유|WTI|브렌트|OPEC|오펙|천연가스|LNG|정유|핵무기|핵 활동|핵시설|핵협상|핵 프로그램|NPT|우라늄"),
    ("연준·금리", r"연준|Fed|FOMC|파월|금리|국채|채권|CPI|PCE|고용|물가|재무부|바이백|달러"),
    ("AI·빅테크", r"앤스로픽|앤트로픽|Anthropic|OpenAI|오픈AI|엔비디아|NVIDIA|마이크로소프트|MSFT|알파벳|구글|메타|아마존|애플|"
                 r"테슬라|스페이스X|xAI|AI|데이터센터|GPU|IPO|상장"),
    ("반도체", r"반도체|하이닉스|삼성전자|마이크론|TSMC|HBM|메모리|D램|낸드|SOX|램리서치|ASML"),
    ("보안·코인", r"해킹|해커|유출|사이버|보안|비트코인|이더리움|코인|암호화폐|가상자산|Coinbase|코인베이스|월렛|거래소"),
    ("러·우", r"러시아|우크라|푸틴|젤렌스키|크렘린|스타링크"),
    ("한국", r"코스피|코스닥|한국|원/달러|원화|한은|금감원|국토부|정부"),
    ("지수", r"나스닥|S&P|다우|선물|지수|VIX"),
]
HOT = re.compile(r"속보|긴급|Breaking|사상 최고|사상최고|급등|급락|폭락|폭등|공격|미사일|공습|휴전|합의|핵무기|해킹|IPO|상장|파산|"
                 r"금리 (?:인상|인하)|서킷|사이드카|최고치|최저치")


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(KST):%m-%d %H:%M} {msg}\n")


def refresh() -> None:
    if TGR_PY.exists():
        subprocess.run([str(TGR_PY), "run.py", "once", "--no-classify"], cwd=TGR, capture_output=True, timeout=300,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def headline(text: str) -> str:
    t = re.sub(r"https?://\S+", "", text or "")
    t = re.sub(r"[*_`#>]+", "", t)
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not lines:
        return ""
    h = lines[0]
    if len(h) < 25 and len(lines) > 1:            # '$TSLA -' 같은 머리말만 있으면 다음 줄 이어 붙임
        h = f"{h} {lines[1]}"
    h = re.sub(r"\s+", " ", h).strip(" -—:")
    return h[:140] + ("…" if len(h) > 140 else "")


def bigrams(s: str) -> set[str]:
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def build() -> dict:
    con = sqlite3.connect(str(DB))
    since = (datetime.now(timezone.utc) - timedelta(hours=KEEP_H)).isoformat()
    q = f"select channel_username, msg_id, posted_at, text from messages where posted_at >= ? and channel_username in ({','.join('?' * len(CHANNELS))}) order by posted_at desc"
    rows = con.execute(q, (since, *CHANNELS)).fetchall()
    items, seen = [], []
    for ch, mid, posted, text in rows:
        if not text or BROKER.search(text) or JUNK.search(text):
            continue
        h = headline(text)
        if len(h) < 12:
            continue
        g = bigrams(h)
        if any(len(g & s) / max(1, len(g | s)) >= 0.5 for s in seen):
            continue
        seen.append(g)
        ts = datetime.fromisoformat(posted).astimezone(timezone.utc)
        tags = [n for n, pat in TAGS if re.search(pat, text[:400])][:2] or ["기타"]
        items.append({"ts": int(ts.timestamp() * 1000), "src": CHANNELS[ch], "url": f"https://t.me/{ch}/{mid}",
                      "text": h, "tags": tags, "hot": bool(HOT.search(h))})
        if len(items) >= MAX_ITEMS:
            break
    return {"updated": int(datetime.now(timezone.utc).timestamp() * 1000), "items": items}


def gh(*args: str, input_: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, input=input_, encoding="utf-8")


def ensure_branch() -> None:
    if gh("api", f"repos/{REPO}/branches/{BRANCH}").returncode == 0:
        return
    sha = json.loads(gh("api", f"repos/{REPO}/git/ref/heads/main").stdout)["object"]["sha"]
    gh("api", "-X", "POST", f"repos/{REPO}/git/refs", "-f", f"ref=refs/heads/{BRANCH}", "-f", f"sha={sha}")


def upload(data: dict) -> bool:
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
        for it in data["items"][:25]:
            t = datetime.fromtimestamp(it["ts"] / 1000, KST)
            print(f"{t:%m/%d %H:%M} [{'/'.join(it['tags'])}]{' 🔴' if it['hot'] else ''} {it['text']}")
        print(f"총 {len(data['items'])}건")
        return
    try:
        changed = upload(data)
        log(f"{len(data['items'])}건 {'올림' if changed else '변화 없음'}")
    except Exception as e:  # noqa: BLE001
        log(f"실패: {e}")


if __name__ == "__main__":
    main()
