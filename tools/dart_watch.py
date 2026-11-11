"""📑 실적·IR 공시 감시 → 카톡 나에게(텔레그램 봇을 켜면 텔레그램). 조선·반도체 소부장, 케이프 필수(2026-11-11~12 운영자 요청).

  python tools/dart_watch.py            # 1회 확인(예약 작업: 평일 07~21시 10분마다, 실행 PC 한 대만)
  python tools/dart_watch.py --dry      # 알림 없이 새로 잡힐 공시만 표시
  python tools/dart_watch.py --list     # 감시 회사·최근 실적 공시 표

- 출처: OpenDART(키: 환경변수 DART_API_KEY 또는 ~/.dart/.env) → 키가 없거나 실패하면 KIND(키 없음, 종목코드 검색).
- 잡는 공시: 영업(잠정)실적 · 분기/반기/사업보고서 · 기업설명회(IR) · 매출액또는손익구조 변동 · 결산실적공시 예고.
- 분기보고서는 OpenDART 주요계정으로 매출액·영업이익·순이익과 작년 같은 분기 대비를 붙인다(키 있을 때).
- 처음 실행 때는 이미 나온 공시를 '본 것'으로만 기록하고 알리지 않는다. 사실·수치만, 매수·매도 권유 없음.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg_alert import alert  # noqa: E402

# 감시 회사(이름: 종목코드). 다른 업종도 같은 방식으로 추가. MUST 는 알림 맨 앞에 ⭐.
MUST = {"케이프"}
SEMI = {
    "한미반도체": "042700", "이오테크닉스": "039030", "원익IPS": "240810", "주성엔지니어링": "036930", "리노공업": "058470",
    "ISC": "095340", "피에스케이": "319660", "테스": "095610", "유진테크": "084370", "하나마이크론": "067310", "티씨케이": "064760",
    "솔브레인": "357780", "동진쎄미켐": "005290", "테크윙": "089030", "HPSP": "403870", "파크시스템스": "140860", "에스티아이": "039440",
    "코미코": "183300", "이수페타시스": "007660", "심텍": "222800", "대덕전자": "353200", "티에스이": "131290", "네패스": "033640",
    "에프에스티": "036810", "케이씨텍": "281820", "원익QnC": "074600", "제우스": "079370", "피에스케이홀딩스": "031980", "디아이": "003160",
    "엘오티베큠": "083310", "미코": "059090", "와이씨": "232140", "오로스테크놀로지": "322310", "넥스틴": "348210",
    "에이디테크놀로지": "200710", "가온칩스": "399720", "고영": "098460", "에스앤에스텍": "101490", "하나머티리얼즈": "166090",
    "월덱스": "101160", "케이씨": "029460", "비씨엔씨": "146320", "코리아써키트": "007810", "대주전자재료": "078600", "인텍플러스": "064290",
    "프로텍": "053610", "SFA반도체": "036540", "두산테스나": "131970", "엑시콘": "092870", "GST": "083450", "저스템": "417840",
    "마이크로컨텍솔": "098120", "큐알티": "405100", "덕산하이메탈": "077360", "한솔케미칼": "014680", "이녹스첨단소재": "272290",
    "PI첨단소재": "178920",
}
SHIP = {
    "케이프": "064820", "한국카본": "017960", "동성화인텍": "033500", "세진중공업": "075580", "삼영엠텍": "054540",
    "인화정공": "101930", "엔케이": "085310", "일승": "333430", "대창솔루션": "096350", "SK오션플랜트": "100090",
    "STX엔진": "077970", "디케이락": "105740", "화인베스틸": "133820", "케이에스피": "073010", "HJ중공업": "097230",
    "성광벤드": "014620", "태광": "023160", "하이록코리아": "013030", "비엠티": "086670", "한라IMS": "092460",
    "오리엔탈정공": "014940", "한화엔진": "082740", "HD현대마린솔루션": "443060", "HD현대마린엔진": "071970",
    "삼성중공업": "010140", "한화오션": "042660", "HD한국조선해양": "009540", "HD현대중공업": "329180",
}
WATCH = {**SHIP, **SEMI}
GROUP = {**{c: "🚢 조선" for c in SHIP.values()}, **{c: "💾 반도체 소부장" for c in SEMI.values()}}
DIGEST_HOUR = 18                         # 평일 18시 이후 첫 실행 때 '오늘 실적 발표 종목' 요약 1회
DIGEST_FLAG = Path.home() / ".tg_notify" / "dart_digest_day.txt"
KEYWORDS = re.compile(r"잠정|분기보고서|반기보고서|사업보고서|기업설명회|손익구조|결산실적공시")
HOME = Path.home()
STATE = HOME / ".tg_notify" / "dart_seen.json"
CORP_CACHE = HOME / ".dart" / "corp_codes.json"
UA = {"User-Agent": "Mozilla/5.0"}


def dart_key() -> str:
    k = os.environ.get("DART_API_KEY", "").strip()
    if not k and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                k = str(winreg.QueryValueEx(h, "DART_API_KEY")[0]).strip()
        except OSError:
            pass
    if not k:
        try:
            for line in (HOME / ".dart" / ".env").read_text(encoding="utf-8-sig").splitlines():
                if line.startswith("DART_API_KEY="):
                    k = line.split("=", 1)[1].strip()
        except OSError:
            pass
    return k


def _get(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 20) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, data=data, headers={**UA, **(headers or {})}), timeout=timeout).read()


def corp_codes(key: str) -> dict[str, str]:
    """종목코드 → DART 고유번호(일주일 캐시)."""
    try:
        c = json.loads(CORP_CACHE.read_text(encoding="utf-8"))
        if time.time() - c["at"] < 7 * 86400:
            return c["map"]
    except Exception:  # noqa: BLE001
        pass
    z = zipfile.ZipFile(BytesIO(_get(f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={key}", timeout=60)))
    x = z.read(z.namelist()[0]).decode("utf-8")
    m = {s: c for c, s in re.findall(r"<corp_code>(\d+)</corp_code>\s*<corp_name>[^<]*</corp_name>\s*"
                                      r"(?:<corp_eng_name>[^<]*</corp_eng_name>\s*)?<stock_code>(\d{6})</stock_code>", x)}
    CORP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CORP_CACHE.write_text(json.dumps({"at": time.time(), "map": m}), encoding="utf-8")
    return m


def from_dart(key: str, name: str, code: str, cc: str, bgn: str, end: str) -> list[dict]:
    j = json.loads(_get(f"https://opendart.fss.or.kr/api/list.json?crtfc_key={key}&corp_code={cc}&bgn_de={bgn}&end_de={end}&page_count=100"))
    if j.get("status") not in ("000", "013"):          # 013 = 조회된 데이터 없음
        raise RuntimeError(f"DART {j.get('status')} {j.get('message')}")
    return [{"id": r["rcept_no"], "name": name, "code": code, "cc": cc, "date": r["rcept_dt"], "title": " ".join(r["report_nm"].split()),
             "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"} for r in j.get("list", [])]


def from_kind(name: str, code: str, bgn: str, end: str) -> list[dict]:
    body = urllib.parse.urlencode({"method": "searchDetailsSub", "currentPageSize": "100", "pageIndex": "1", "orderMode": "1",
                                   "orderStat": "D", "forward": "details_sub", "searchCorpName": name, "searchCodeType": "char",
                                   "repIsuSrtCd": "A" + code, "allRepIsuSrtCd": "A" + code,
                                   "fromDate": f"{bgn[:4]}-{bgn[4:6]}-{bgn[6:]}", "toDate": f"{end[:4]}-{end[4:6]}-{end[6:]}"}).encode()
    t = _get("https://kind.krx.co.kr/disclosure/details.do", body, {"X-Requested-With": "XMLHttpRequest"}).decode("utf-8", "replace")
    out = []
    for r in re.findall(r"<tr.*?</tr>", t, re.S)[1:]:
        td = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", x)).split()) for x in re.findall(r"<td.*?</td>", r, re.S)]
        if len(td) >= 4 and td[2] == name:
            acpt = re.search(r"openDisclsViewer\('(\d+)'", r)
            out.append({"id": "K" + (acpt.group(1) if acpt else f"{td[1]}|{td[3]}"), "name": name, "code": code, "cc": "",
                        "date": td[1][:10].replace("-", ""), "title": td[3],
                        "url": f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={acpt.group(1)}" if acpt else ""})
    return out


def eok(v: float) -> str:
    return f"{v / 1e12:,.2f}조" if abs(v) >= 1e12 else f"{v / 1e8:,.0f}억"


def quarter_numbers(key: str, cc: str, title: str) -> list[str]:
    """분기보고서 → 주요계정(매출액·영업이익·순이익) 이번 분기와 작년 같은 분기. 실패하면 빈 목록."""
    m = re.search(r"\((\d{4})\.(\d{2})\)", title)
    if not (key and cc and m):
        return []
    rc = {"03": "11013", "06": "11012", "09": "11014", "12": "11011"}.get(m.group(2))
    try:
        j = json.loads(_get(f"https://opendart.fss.or.kr/api/fnlttSinglAcnt.json?crtfc_key={key}&corp_code={cc}"
                            f"&bsns_year={m.group(1)}&reprt_code={rc}"))
    except Exception:  # noqa: BLE001
        return []
    rows = j.get("list") or []
    fs = "CFS" if any(r.get("fs_div") == "CFS" for r in rows) else "OFS"
    num = lambda v: float(str(v).replace(",", "")) if str(v or "").replace(",", "").lstrip("-").isdigit() else None
    out = []
    for acc in ("매출액", "영업이익", "당기순이익"):
        r = next((r for r in rows if r.get("fs_div") == fs and r.get("account_nm", "").replace(" ", "").startswith(acc)), None)
        if not r:
            continue
        cur, prev = num(r.get("thstrm_amount")), num(r.get("frmtrm_q_amount") or r.get("frmtrm_amount"))
        if cur is None:
            continue
        yoy = f" (작년 같은 분기 {eok(prev)}, {(cur / prev - 1) * 100:+.0f}%)" if prev and prev > 0 else f" (작년 같은 분기 {eok(prev)})" if prev is not None else ""
        out.append(f"{acc} {eok(cur)}{yoy}")
    if out:
        out.append("연결 기준" if fs == "CFS" else "별도 기준")
    return out


def market_dart(key: str, bgn: str, end: str) -> list[dict]:
    """기간 안 시장 전체 정기공시(A)·거래소공시(I) 중 실적·IR 관련만. 회사마다 묻지 않아 호출이 적다."""
    out = []
    for ty in ("A", "I"):
        page = 1
        while True:
            j = json.loads(_get(f"https://opendart.fss.or.kr/api/list.json?crtfc_key={key}&bgn_de={bgn}&end_de={end}"
                                f"&pblntf_ty={ty}&page_no={page}&page_count=100"))
            if j.get("status") == "013":
                break
            if j.get("status") != "000":
                raise RuntimeError(f"DART {j.get('status')} {j.get('message')}")
            for r in j.get("list", []):
                t = " ".join(r["report_nm"].split())
                if KEYWORDS.search(t) and r.get("stock_code"):
                    out.append({"id": r["rcept_no"], "name": r["corp_name"], "code": r["stock_code"], "cc": r["corp_code"],
                                "date": r["rcept_dt"], "title": t, "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"})
            if page >= int(j.get("total_page") or 1) or page >= 40:
                break
            page += 1
    return out


def collect(days: int = 14) -> tuple[list[dict], str, list[dict]]:
    """(감시 회사 공시, 출처, 시장 전체 실적 공시 — DART 키 있을 때만)."""
    end = datetime.now()
    bgn, endd = (end - timedelta(days=days)).strftime("%Y%m%d"), end.strftime("%Y%m%d")
    key = dart_key()
    if key:
        try:
            allm = market_dart(key, bgn, endd)
            codes = set(WATCH.values())
            return sorted([d for d in allm if d["code"] in codes], key=lambda d: d["date"]), "OpenDART", allm
        except Exception:  # noqa: BLE001
            pass
    out = []
    for name, code in WATCH.items():                      # 키 없음·실패 → KIND 회사별
        try:
            out += [d for d in from_kind(name, code, bgn, endd) if KEYWORDS.search(d["title"])]
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)
    return sorted(out, key=lambda d: d["date"]), "KIND" + ("" if key else "(DART 키 없음)"), []


def deliver(kind: str, key: str, text: str) -> bool:
    """텔레그램 봇이 켜져 있으면 텔레그램, 아니면 카톡 '나에게'(카톡 OFF 여도 이 알림은 보냄 — 11/12 운영자 지시)."""
    try:
        from tg_alert import _env, _ready
        e = _env()
        if e.get("TG_ALERT_ON") == "1" and _ready(e):
            return alert(kind, key, text)
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.path.insert(0, r"C:\projects\market-site\trader")
        from kakao_notify import notify
        return notify(f"🔔 [{kind}] {datetime.now():%m/%d %H:%M}\n{text}", force=True)
    except Exception as e:  # noqa: BLE001
        print(f"[알림 실패] {e}")
        alert(kind, key, text)                              # 미리 보기 기록이라도
        return False


REPORTED = Path.home() / ".tg_notify" / "dart_reported.json"
QUARTER_START = "20261001"                # 이번 실적 시즌 시작(3분기). 다음 시즌엔 바꾼다


def reported(found: list[dict] | None = None) -> dict[str, str]:
    """이번 시즌 실적(잠정실적·분기보고서)을 낸 감시 회사 {종목코드: 날짜}. 없으면 시즌 처음부터 한 번 훑어 만든다."""
    try:
        r = json.loads(REPORTED.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        r = None
    if r is None:                                       # 처음: 회사별로 시즌 처음부터(시장 전체 훑기는 페이지가 너무 많음)
        end, key, extra = datetime.now().strftime("%Y%m%d"), dart_key(), []
        cmap = corp_codes(key) if key else {}
        for name, code in WATCH.items():
            try:
                extra += (from_dart(key, name, code, cmap[code], QUARTER_START, end) if cmap.get(code)
                          else from_kind(name, code, QUARTER_START, end))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.15)
        found = extra + (found or [])
        r = {}
    for d in found or []:
        if re.search(r"잠정|분기보고서|손익구조", d["title"]) and d["date"] >= QUARTER_START:
            r.setdefault(d["code"], d["date"])
    REPORTED.parent.mkdir(parents=True, exist_ok=True)
    REPORTED.write_text(json.dumps(r), encoding="utf-8")
    return r


def digest(allm: list[dict], now: datetime, dry: bool) -> None:
    """평일 18시 이후 첫 실행 때 오늘 시장 전체 실적 발표(잠정실적·분기보고서) 회사 요약 1회. DART 키 있을 때만."""
    day = now.strftime("%Y%m%d")
    try:
        done = DIGEST_FLAG.read_text(encoding="utf-8").strip() == day
    except OSError:
        done = False
    if not allm or (not dry and (done or now.weekday() >= 5 or now.hour < DIGEST_HOUR)):
        return
    today = [d for d in allm if d["date"] == day and re.search(r"잠정|분기보고서|손익구조", d["title"])]
    names: dict[str, str] = {}
    for d in today:
        names.setdefault(d["name"], d["code"])
    mine = [f"{'⭐ ' if n in MUST else ''}{n} {GROUP[c]}" for n, c in names.items() if c in GROUP]
    others = [n for n, c in names.items() if c not in GROUP]
    done_codes = set(reported())
    left = [("⭐ " if n in MUST else "") + n for n, c in WATCH.items() if c not in done_codes]
    text = "\n".join([f"📋 오늘({now:%m/%d}) 실적 발표 {len(names)}곳",
                      "관심: " + (", ".join(mine) if mine else "없음"),
                      f"그 밖 {len(others)}곳: " + (", ".join(others[:60]) or "-") + (" …" if len(others) > 60 else ""),
                      f"아직 3분기 실적 전 관심 종목 {len(left)}곳: " + (", ".join(left) or "없음"),
                      "출처 OpenDART (잠정실적·분기보고서)"])
    if dry:
        print(text)
        return
    deliver("실적요약", day, text)
    DIGEST_FLAG.write_text(day, encoding="utf-8")


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    dry, lst = "--dry" in sys.argv, "--list" in sys.argv
    now = datetime.now()
    if not (dry or lst) and STATE.exists() and not (now.weekday() < 5 and 7 <= now.hour < 21):
        return                                             # 첫 실행(기록 없음)은 시간과 상관없이 기록부터
    found, src, allm = collect(40 if lst else 14)
    if lst:
        print(f"감시 {len(WATCH)}곳 · 출처 {src}")
        for d in found:
            print(f"  {d['date']} {d['name']} {d['title']}")
        return
    try:
        seen = set(json.loads(STATE.read_text(encoding="utf-8")))
        first = False
    except Exception:  # noqa: BLE001
        seen, first = set(), True
    new = [d for d in found if d["id"] not in seen]
    key = dart_key()
    for d in new:
        if first:
            continue
        extra = quarter_numbers(key, d.get("cc", ""), d["title"]) if "분기보고서" in d["title"] or "반기보고서" in d["title"] else []
        ttl = "🎤 IR 예정" if "기업설명회" in d["title"] else "📑 실적 공시"
        star = "⭐ " if d["name"] in MUST else ""
        text = "\n".join([f"{star}{ttl} · {d['name']}({d['code']}) {GROUP.get(d['code'], '')}", d["title"],
                          f"접수 {d['date'][4:6]}/{d['date'][6:]}"] + extra + ([d["url"]] if d["url"] else []) + [f"출처 {src}"])
        if dry:
            print(text + "\n")
        else:
            deliver("실적공시", d["id"], text)
    if not dry:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(sorted(seen | {d["id"] for d in found})), encoding="utf-8")
        reported(found)
    digest(allm, now, dry)
    print(f"{now:%m-%d %H:%M} 공시 {len(found)}건 · 새 공시 {0 if first else len(new)}건{' (첫 실행: 기록만)' if first else ''} · {src}")


if __name__ == "__main__":
    main()
