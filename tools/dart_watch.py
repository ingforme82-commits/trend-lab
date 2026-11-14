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
    "에스엔시스": "0008Z0", "대한조선": "439260",
}
WATCH = {**SHIP, **SEMI}
GROUP = {**{c: "🚢 조선" for c in SHIP.values()}, **{c: "💾 반도체 소부장" for c in SEMI.values()}}
DIGEST_HOUR = 18                         # 평일 18시 이후 첫 실행 때 '오늘 실적 발표 종목' 요약 1회
DIGEST_FLAG = Path.home() / ".tg_notify" / "dart_digest_day.txt"
IR_KEYWORDS = re.compile(r"기업\s*설명회|컨퍼런스\s*콜|컨콜|conference\s*call", re.I)
KEYWORDS = re.compile(r"잠정|분기보고서|반기보고서|사업보고서|손익구조|결산실적공시|실적\s*발표|경영\s*실적|" + IR_KEYWORDS.pattern, re.I)
HOME = Path.home()
# 배당 근거 공시 — MUST 회사만(2026-11-14 운영자: 케이프는 배당 목적 분할매수, 배당·기준일·자본준비금 감액 확인)
DIV_KEYWORDS = re.compile(r"배당|감액|자본준비금|주주명부폐쇄|기준일|자기주식|주식소각|주주환원|주주총회소집", re.I)
MUST_CODES = {WATCH[n] for n in MUST}


def wanted(title: str, code: str) -> bool:
    """실적·IR 공시(감시 회사 전체) 또는 배당 근거 공시(MUST 회사만)."""
    return bool(KEYWORDS.search(title) or (code in MUST_CODES and DIV_KEYWORDS.search(title)))


def div_numbers(key: str, rcept_no: str) -> list[str]:
    """배당결정·기준일·주총소집 공시 본문에서 숫자만 뽑는다(원문 그대로, 권유 없음)."""
    if not (key and rcept_no.isdigit()):
        return []
    try:
        z = zipfile.ZipFile(BytesIO(_get(f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={key}&rcept_no={rcept_no}", timeout=30)))
        t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", z.read(n).decode("utf-8", "replace"))) for n in z.namelist())
        t = " ".join(t.split())
    except Exception:  # noqa: BLE001
        return []
    out = []
    for lb, pat, unit in (("배당구분", r"배당구분\s+(\S+)", ""), ("1주당 배당금", r"1주당 배당금\(원\)\s+보통주식\s+([\d,]+)", "원"),
                          ("시가배당율", r"시가배당율\(%\)\s+보통주식\s+([\d.]+)", "%"),
                          ("기준일", r"(?:배당기준일|기준일)\s+(\d{4}-\d{2}-\d{2})", ""),
                          ("지급 예정", r"배당금지급 예정일자\s+(\d{4}-\d{2}-\d{2})", ""),
                          ("자본준비금", r"(자본준비금[^.]{0,80}감액[^.]{0,60})", "")):
        m = re.search(pat, t)
        if m:
            out.append(f"{lb} {m.group(1)}{unit}")
    return out
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
    data = {}
    for acc in ("매출액", "영업이익", "당기순이익"):
        r = next((r for r in rows if r.get("fs_div") == fs and r.get("account_nm", "").replace(" ", "").startswith(acc)), None)
        if r and num(r.get("thstrm_amount")) is not None:
            data[acc] = {"cur": num(r.get("thstrm_amount")), "yoy": num(r.get("frmtrm_q_amount") or r.get("frmtrm_amount")), "qoq": None}
    return describe(data, "연결 기준" if fs == "CFS" else "별도 기준") if data else []


UNIT = {"원": 1, "천원": 1e3, "백만원": 1e6, "억원": 1e8}


def prelim_numbers(key: str, rcept_no: str) -> list[str]:
    """영업(잠정)실적 공시 원문(OpenDART document.xml) → 이번 분기·직전 분기·작년 같은 분기 + 회사 설명. 실패하면 빈 목록."""
    if not (key and rcept_no.isdigit()):
        return []
    try:
        z = zipfile.ZipFile(BytesIO(_get(f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={key}&rcept_no={rcept_no}", timeout=30)))
        x = z.read(z.namelist()[0]).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return []
    cells = [c.strip() for c in html.unescape(re.sub(r"<[^>]+>", "|", x)).split("|") if c.strip()]
    unit = 1e6
    for c in cells:
        m = re.search(r"단위\s*:\s*(천원|백만원|억원|원)", c)
        if m:
            unit = UNIT[m.group(1)]
            break
    val = lambda s: float(s.replace(",", "")) if re.fullmatch(r"-?[\d,]+(\.\d+)?", s or "") else None
    data = {}
    for acc, label in (("매출액", "매출액"), ("영업이익", "영업이익"), ("당기순이익", "당기순이익")):
        for i, c in enumerate(cells[:-8]):
            if c.replace(" ", "").startswith(label) and cells[i + 1] == "당해실적":
                cur, qoq_b, yoy_b = val(cells[i + 2]), val(cells[i + 3]), None
                tail = cells[i + 4:i + 9]                          # 전기대비%, 흑자적자, 전년동기, 전년대비%, 흑자적자
                nums = [val(t) for t in tail]
                # '-' 가 섞여 칸 수가 일정하지 않아 전년동기실적은 '전기대비 칸 2개' 다음 숫자로 잡는다
                yoy_b = nums[2] if len(nums) > 2 else None
                if cur is not None:
                    data[acc] = {"cur": cur * unit, "qoq": qoq_b * unit if qoq_b is not None else None,
                                 "yoy": yoy_b * unit if yoy_b is not None else None}
                break
    note = ""
    for i, c in enumerate(cells):
        if "기타 투자판단과 관련한 중요사항" in c:
            note = " ".join(cells[i + 1:i + 6])
            break
    out = describe(data, "연결 기준" if "연결" in x[:4000] else "별도 기준") if data else []
    note = re.sub(r"\s+", " ", re.sub(r"관련\s*공시.*$", "", note))
    boiler = re.compile(r"K-?IFRS|국제회계기준|외부감사|감사인|검토를 받지|잠정\s*영업실적|잠정치|편의를|홈페이지|변경될 수|달라질 수|게재할|요약 자료")
    note = " ".join(s.strip(" -※") for s in re.split(r"(?<=[.다])\s+|\s-\s|※", note) if s.strip(" -※") and not boiler.search(s))
    if note and not re.fullmatch(r"[-\s]*", note):
        out.append("📝 회사 설명: " + note[:220] + ("…" if len(note) > 220 else ""))
    return out


def _chg(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return ""
    if b > 0 and a > 0:
        p = (a / b - 1) * 100
        return "보합" if abs(p) < 0.5 else f"{p:+.0f}%"
    if b <= 0 < a:
        return "흑자전환"
    if a <= 0 < b:
        return "적자전환"
    return "적자지속" if a < 0 and b < 0 else ""


def describe(d: dict, basis: str) -> list[str]:
    """숫자 줄 + 해석(사실 기반 규칙, 매수·매도 권유 아님)."""
    out = []
    for acc in ("매출액", "영업이익", "당기순이익"):
        v = d.get(acc)
        if not v:
            continue
        parts = [f"작년 같은 분기 대비 {_chg(v['cur'], v['yoy'])}" if _chg(v["cur"], v["yoy"]) else "",
                 f"직전 분기 대비 {_chg(v['cur'], v['qoq'])}" if _chg(v["cur"], v["qoq"]) else ""]
        out.append(f"{acc} {eok(v['cur'])}" + (f" ({' · '.join(p for p in parts if p)})" if any(parts) else ""))
    out.append(basis)
    s, o, n = d.get("매출액"), d.get("영업이익"), d.get("당기순이익")
    why = []
    if s and o and s["cur"]:
        m_now = o["cur"] / s["cur"] * 100
        m_y = o["yoy"] / s["yoy"] * 100 if s.get("yoy") and o.get("yoy") is not None else None
        m_q = o["qoq"] / s["qoq"] * 100 if s.get("qoq") and o.get("qoq") is not None else None
        line = f"영업이익률 {m_now:.1f}%"
        if m_y is not None:
            line += f" (작년 {m_y:.1f}% → {m_now - m_y:+.1f}%p)"
        if m_q is not None:
            line += f" · 직전 분기 {m_q:.1f}%"
        why.append(line)
        sg = s["cur"] / s["yoy"] - 1 if s.get("yoy") else None
        og = (o["cur"] - o["yoy"]) if o.get("yoy") is not None else None
        if sg is not None and og is not None:
            better = m_y is not None and m_now > m_y
            if sg > 0.03 and og > 0:
                why.append("매출·이익·이익률 모두 개선" if better else "매출이 늘어 이익도 늘었지만 이익률은 하락(원가·비용 증가)")
            elif sg > 0.03 and og <= 0:
                why.append("매출은 늘었지만 이익이 줄어 원가·비용 부담 확인 필요")
            elif sg <= -0.03 and og > 0:
                why.append("매출은 줄었지만 이익은 늘어 수익성(제품 구성·비용 절감) 개선")
            elif sg <= -0.03 and og <= 0:
                why.append("매출과 이익이 함께 줄어 업황·수주 둔화 신호")
            else:
                why.append("매출은 작년과 비슷, 이익은 " + ("개선" if og > 0 else "악화"))
        if o.get("qoq") is not None and s.get("qoq"):
            up_q, up_y = o["cur"] > o["qoq"], og is not None and og > 0
            why.append("직전 분기 대비 영업이익 " + ("증가" if up_q else "감소") +
                       (" — 작년 대비와 같은 방향" if up_q == up_y else " — 작년 대비와 반대 방향(최근 흐름 " + ("회복" if up_q else "둔화") + ")"))
    if o and n and o.get("cur") and n.get("cur") is not None:
        if (o["cur"] > 0) != (n["cur"] > 0) or (o.get("yoy") and n.get("yoy") and (o["cur"] > o["yoy"]) != (n["cur"] > n["yoy"])):
            why.append("영업이익과 순이익 방향이 달라 영업 외 요인(금융자산 평가·환율·일회성 손익) 영향 — 회사 설명 확인")
    if why:
        out.append("💡 해석: " + " / ".join(why))
    return out


def price_now(code: str) -> str:
    """공시 뒤 주가(KB 현재가, 실패하면 빈 문자열)."""
    try:
        sys.path.insert(0, r"C:\projects\market-site\trader")
        from kb_tool import tr
        q = tr("ivu10140", {"shrt_cd": code, "excg_clsf": "0"})
        px, base = float(q.get("now_prc") or 0), float(q.get("sprc") or 0)
        return f"📈 주가 {px:,.0f}원 ({(px / base - 1) * 100:+.2f}%, {datetime.now():%H:%M} KB)" if px and base else ""
    except Exception:  # noqa: BLE001
        return ""


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
                if r.get("stock_code") and wanted(t, r["stock_code"]):
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
            out += [d for d in from_kind(name, code, bgn, endd) if wanted(d["title"], code)]
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)
    return sorted(out, key=lambda d: d["date"]), "KIND" + ("" if key else "(DART 키 없음)"), []


def deliver(kind: str, key: str, text: str) -> bool:
    """TRL 앱 푸시(등록 기기가 있으면 항상) + 텔레그램 봇이 켜져 있으면 텔레그램, 아니면 카톡 '나에게'
    (카톡 OFF면 카톡은 보내지 않고 기록만 — 11/14 운영자: 카톡 예외 폐지)."""
    try:                                                    # 📲 앱 푸시: 첫 줄=제목, 나머지=본문, 본문 속 첫 링크를 누르면 열림
        from push_notify import SITE, push
        lines = [x for x in text.splitlines() if x.strip()]
        link = next((x.strip() for x in lines if x.strip().startswith("http")), SITE)
        body = "\n".join(x for x in lines[1:] if not x.strip().startswith("http"))[:500]
        push(f"TRL · {lines[0][:60]}" if lines else f"TRL · {kind}", body, link, key[:60])
    except Exception:  # noqa: BLE001
        pass
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


HEADLINE = Path(__file__).resolve().parents[1] / "data" / "headline.json"
SHIP_CARD = "🚢 조선기자재 3분기 실적"      # 주요 이슈 카드(운영자 11/12 요청: 앱에서 실시간). 카드가 있을 때만 갱신


def ship_card_update(name: str, title: str, date: str, extra: list[str], path: Path = HEADLINE) -> bool:
    """조선 감시 회사의 실적 공시가 새로 잡히면 주요 이슈 카드 맨 위에 한 줄 넣고 '발표 대기'에서 뺀다.
    카드(태그 SHIP_CARD)가 없으면 아무것도 하지 않는다. 숫자는 공시 원문 그대로(권유 없음)."""
    if not re.search(r"잠정|분기보고서|반기보고서|손익구조", title):
        return False
    try:
        h = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    it = next((x for x in h.get("items", []) if x.get("tag") == SHIP_CARD), None)
    if not it:
        return False
    nums = [e.split(" (")[0] for e in extra if re.match(r"(매출액|영업이익|당기순이익) ", e)][:2]
    chg = [m.group(1) for e in extra if re.match(r"(매출액|영업이익) ", e)
           for m in [re.search(r"작년 같은 분기 대비 ([^·)]+)", e)] if m][:2]
    body = " · ".join(f"{n} ({c.strip()})" if i < len(chg) else n for i, (n, c) in enumerate(zip(nums, chg + [""] * 2)))
    line = f"✔ {date[4:6]}/{date[6:]} {name} — " + (body or "실적 공시 나옴(숫자는 공시 원문 확인)")
    pts = [p for p in it.get("points", []) if not p.startswith(f"✔ {date[4:6]}/{date[6:]} {name} ")]
    pending = [n for n in it.get("pending", []) if n != name]
    pts = [line] + [p for p in pts if not p.startswith("⏳")]
    if pending:
        pts.append("⏳ 발표 대기: " + " · ".join(pending))
    it.update(points=pts, pending=pending, when=f"{datetime.now():%m/%d %H시 %M분} 자동 갱신")
    h["updated"] = f"{datetime.now():%Y-%m-%d %H:%M}"
    path.write_text(json.dumps(h, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


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
    card = False
    for d in new:
        if first:
            continue
        extra = (quarter_numbers(key, d.get("cc", ""), d["title"]) if "분기보고서" in d["title"] or "반기보고서" in d["title"]
                 else prelim_numbers(key, d["id"]) if re.search(r"잠정|손익구조", d["title"])
                 else div_numbers(key, d["id"]) if DIV_KEYWORDS.search(d["title"]) else [])
        if not IR_KEYWORDS.search(d["title"]):
            extra.append(price_now(d["code"]))
        extra = [e for e in extra if e]
        ttl = ("🎤 IR·컨퍼런스콜" if IR_KEYWORDS.search(d["title"]) else "📑 실적 공시" if KEYWORDS.search(d["title"])
               else "💰 배당·주주환원 공시")
        star = "⭐ " if d["name"] in MUST else ""
        text = "\n".join([f"{star}{ttl} · {d['name']}({d['code']}) {GROUP.get(d['code'], '')}", d["title"],
                          f"접수 {d['date'][4:6]}/{d['date'][6:]}"] + extra + ([d["url"]] if d["url"] else []) + [f"출처 {src}"])
        if dry:
            print(text + "\n")
        else:
            deliver("실적공시", d["id"], text)
            if GROUP.get(d["code"]) == "🚢 조선" and ship_card_update(d["name"], d["title"], d["date"], extra):
                card = True
    if not dry and card:
        try:
            from ops import push as git_push
            git_push(f"주요 이슈 자동: {SHIP_CARD} 갱신", ["data/headline.json"])
        except Exception as e:  # noqa: BLE001
            print(f"[카드 push 실패] {e}")
    if not dry:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(sorted(seen | {d["id"] for d in found})), encoding="utf-8")
        reported(found)
    digest(allm, now, dry)
    print(f"{now:%m-%d %H:%M} 공시 {len(found)}건 · 새 공시 {0 if first else len(new)}건{' (첫 실행: 기록만)' if first else ''} · {src}")


if __name__ == "__main__":
    main()
