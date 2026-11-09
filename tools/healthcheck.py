"""🩺 실시간 점검 — 사이트 실시간 값이 멈췄는지, 멈췄다면 어디서 멈췄는지 바로 보이게 (운영자 11/9 지시).

  python tools/healthcheck.py          # 한 번 점검해서 결과 출력 + tools/health.json 저장
  예약: TrendLab_HealthCheck (5분마다, 창 없음) — 등록: scripts
egister_healthcheck.ps1

점검 항목(각각 정상 / 주의 / 문제 + 원인 설명):
  1 속보 수집기 — live_news.log 마지막 실행 시각, 최근 오류
  2 사이트 데이터 — 깃허브 live 브랜치 news.json 갱신 시각
  3 24시간 시세(하이퍼리퀴드) — 거래량 0 상품, 같은 값으로 오래 멈춘 상품
  4 CNBC 실시간 — 미 국채 2·10·30년, 달러인덱스·원/달러·엔/달러 마지막 체결 시각
  5 미국 시간외 시세판 — NH/야후 출처 수, 갱신 시각, 오래된 종목
  6 뉴스 RSS — 실패한 피드
  7 NH API — 토큰 갱신 + 시세 1건 조회(연결 유지 겸), 모의매매 주문 시간대는 건너뜀
  8 KB API — 10분 쉼(kb_down.txt) 여부
  9 예약 작업 — 트렌드랩_*·NH_MOCK_* 마지막 결과 코드, 반복 작업이 너무 오래 안 돈 것
 10 SOXL·KORU 시간외 — 사이트 카드에 보낼 시간외 값이 5분 안에 갱신됐는지
 11 사이트 배포 — 깃허브 페이지의 news.js·app.js·index.html 이 최신 커밋과 같은지(20분 넘게 다르면 문제)
새로 '문제'가 생기면 tg_alert(텔레그램 개인 알림, 꺼져 있으면 tools/alert_outbox.log)로 알리고 tools/healthcheck.log 에 남긴다.
키·토큰·계좌번호는 출력하지 않는다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
KST = ZoneInfo("Asia/Seoul")
OUT = TOOLS / "health.json"
LOG = TOOLS / "healthcheck.log"
STATE = TOOLS / "health_state.json"
NOW = time.time()
T = datetime.fromtimestamp(NOW, KST)
WEEKDAY = T.weekday() < 5
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
R: list[dict] = []


def add(area: str, level: str, msg: str, why: str = "") -> None:
    R.append({"area": area, "level": level, "msg": msg, "why": why})


def age(ms: float | None) -> float:
    return (NOW * 1000 - ms) / 60000 if ms else 1e9


def fmt_min(m: float) -> str:
    return "기록 없음" if m > 1e8 else f"{m:.0f}분 전" if m < 120 else f"{m / 60:.1f}시간 전"


def get_json(url: str, headers: dict | None = None, data: bytes | None = None, timeout: int = 15):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def us_closed_weekend() -> bool:
    """CNBC 환율·금리, 하이퍼리퀴드 지수·원자재가 쉬는 주말(토 07시 ~ 월 07시 KST 근처)."""
    wd, h = T.weekday(), T.hour
    return (wd == 5 and h >= 7) or wd == 6 or (wd == 0 and h < 7)


# 1 속보 수집기
def check_collector() -> None:
    try:
        lines = (TOOLS / "live_news.log").read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
    except OSError:
        add("속보 수집기", "문제", "live_news.log 없음", "수집 작업이 한 번도 안 돌았거나 경로가 바뀜"); return
    ok = [l for l in lines if "올림" in l or "변화 없음" in l]
    last = ok[-1][:11] if ok else ""
    try:
        lt = datetime.strptime(f"{T.year}-{last}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        m = (T - lt).total_seconds() / 60
    except ValueError:
        m = 1e9
    errs = [l for l in lines[-15:] if "실패" in l or "Error" in l or "오류" in l]
    if m > 5:
        add("속보 수집기", "문제", f"마지막 정상 실행 {fmt_min(m)}", "트렌드랩_속보갱신 작업 멈춤·PC 절전·파이썬 오류 — 아래 예약 작업 항목과 live_news.log 끝부분 확인")
    else:
        add("속보 수집기", "정상", f"마지막 실행 {fmt_min(m)}")
    if errs:
        uniq = sorted({e[12:].strip()[:60] for e in errs})
        add("속보 수집기", "주의", f"최근 오류 {len(errs)}줄: " + " / ".join(uniq[:4]), "해당 출처만 실패한 것이면 나머지는 정상 수집")


# 2 사이트 데이터
NEWS: dict = {}


def check_site() -> None:
    global NEWS
    try:
        NEWS = get_json("https://api.github.com/repos/ingforme82-commits/trend-lab/contents/news.json?ref=live",
                        {"Accept": "application/vnd.github.raw+json"})
    except Exception as e:  # noqa: BLE001
        try:
            subprocess.run(["git", "-C", str(TOOLS.parent), "fetch", "-q", "origin", "live"], timeout=40, creationflags=NO_WINDOW)
            NEWS = json.loads(subprocess.run(["git", "-C", str(TOOLS.parent), "show", "origin/live:news.json"], capture_output=True,
                                             timeout=40, creationflags=NO_WINDOW).stdout)
            add("사이트 데이터", "주의", f"깃허브 API 실패({type(e).__name__}) — git 으로 대신 받음", "API 호출 한도(시간당 60회) 초과일 가능성")
        except Exception as e2:  # noqa: BLE001
            add("사이트 데이터", "문제", f"news.json 못 받음({type(e2).__name__})", "인터넷 연결·깃허브 장애"); return
    m = age(NEWS.get("updated"))
    add("사이트 데이터", "문제" if m > 6 else "정상", f"news.json 갱신 {fmt_min(m)}",
        "수집기는 도는데 이 값이 오래됐으면 깃허브 push 실패(인증·충돌) — live_news.log 의 push 오류 확인" if m > 6 else "")


# 3 24시간 시세(하이퍼리퀴드) + 같은 값 멈춤 감지
def check_futures(state: dict) -> None:
    from brief import FUT
    try:
        meta, ctx = get_json("https://api.hyperliquid.xyz/info", {"Content-Type": "application/json"}, b'{"type":"metaAndAssetCtxs","dex":"xyz"}')
        c = {a["name"]: x for a, x in zip(meta["universe"], ctx)}
    except Exception as e:  # noqa: BLE001
        add("24시간 시세", "문제", f"하이퍼리퀴드 응답 없음({type(e).__name__})", "하이퍼리퀴드 API 장애 — 사이트 지수·유가 줄이 멈춤"); return
    dead = [n for s, n, _ in FUT if s in c and float(c[s].get("dayNtlVlm") or 0) == 0 and n not in ("달러인덱스", "원/달러", "엔/달러")]
    if dead and not us_closed_weekend():
        add("24시간 시세", "주의", "거래량 0 상품: " + " · ".join(dead), "하이퍼리퀴드에서 거래가 멈춘 상품 — 사이트에는 싣지 않음(대체 출처 필요)")
    seen = state.setdefault("px", {})
    stuck = []
    for f in (NEWS.get("brief") or {}).get("futures") or []:
        k, px = f["name"], f["px"]
        old = seen.get(k)
        if old and old["px"] == px:
            if (NOW - old["since"]) / 60 >= 45:
                stuck.append(f"{k} {px}({(NOW - old['since']) / 60:.0f}분째 같음)")
        else:
            seen[k] = {"px": px, "since": NOW}
    if stuck and not us_closed_weekend():
        add("24시간 시세", "문제", "값이 멈춤: " + " · ".join(stuck), "출처 상품 거래 중단 또는 수집 실패 — 다른 출처(CNBC·야후)로 바꿔야 함")
    elif not dead:
        add("24시간 시세", "정상", f"{len((NEWS.get('brief') or {}).get('futures') or [])}개 상품 갱신 중")


# 4 CNBC 실시간(금리·환율)
def check_cnbc() -> None:
    ust = NEWS.get("ust") or {}
    fx = {f["name"]: f for f in (NEWS.get("brief") or {}).get("futures") or [] if f.get("src") == "CNBC"}
    limit = 30
    bad = [f"미 {k.replace('Y', '년물')} {fmt_min(age(v.get('at')))}" for k, v in ust.items() if age(v.get("at")) > limit]
    bad += [f"{k} {fmt_min(age(v.get('at')))}" for k, v in fx.items() if age(v.get("at")) > limit]
    miss = [k for k in ("10Y",) if k not in ust] + [k for k in ("달러인덱스", "원/달러") if k not in fx]
    if us_closed_weekend():
        add("금리·달러(CNBC)", "정상", "주말 — 시장 휴장"); return
    if miss:
        add("금리·달러(CNBC)", "문제", "값 없음: " + " · ".join(miss), "CNBC 응답 실패 — brief.py cnbc_fx / market_extra.py ust 확인")
    if bad:
        add("금리·달러(CNBC)", "주의", "마지막 체결이 오래됨: " + " · ".join(bad), "아시아 새벽 등 거래가 뜸한 시간이면 정상일 수 있음")
    if not miss and not bad:
        t = ust.get("10Y", {})
        d = fx.get("달러인덱스", {})
        add("금리·달러(CNBC)", "정상", f"미 10년물 {t.get('px')}% ({fmt_min(age(t.get('at')))}) · 달러인덱스 {d.get('px')} ({fmt_min(age(d.get('at')))})")


# 5 미국 시간외 시세판
def check_ext() -> None:
    try:
        c = json.loads((TOOLS / "ext_board_cache.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        add("미국 시간외", "주의", "시세판 저장본 없음", "아직 한 번도 안 만들어졌거나 수집기 오류"); return
    m = (NOW - c["at"]) / 60
    rows = c["data"].get("rows") or []
    src = {}
    for r in rows:
        src[r.get("src") or "?"] = src.get(r.get("src") or "?", 0) + 1
    stale = [r["sym"] for r in rows if r.get("stale")]
    lv = "문제" if m > 5 and c["data"].get("live") else "정상"
    add("미국 시간외", lv, f"{c['data'].get('sess') or '세션 없음'} · {fmt_min(m)} 갱신 · 출처 " + " · ".join(f"{k} {v}" for k, v in src.items())
        + (f" · 오래된 체결 {len(stale)}종목" if stale else ""), "수집기가 시세판을 못 만들고 있음" if lv == "문제" else "")
    if src.get("야후") and not src.get("NH") and rows:
        add("미국 시간외", "주의", "NH 대신 전부 야후로 받는 중", "NH 오류 뒤 10분 쉼이거나 한국장 주문 시간대 — 아래 NH 항목 확인")


# 6 뉴스 RSS
def check_rss() -> None:
    h = (NEWS.get("health") or {}).get("rss") or {}
    fail = h.get("fail") or []
    if not h:
        add("뉴스 RSS", "주의", "상태 정보 없음"); return
    add("뉴스 RSS", "주의" if fail else "정상", f"{h.get('ok')}/{h.get('total')} 피드 정상" + (f" · 실패: {' · '.join(sorted(set(fail)))}" if fail else ""),
        "실패 피드는 그 출처만 빠지고 나머지는 계속 수집" if fail else "")


# 7 NH API (연결 유지)
def check_nh() -> None:
    try:
        from extended import nh_gap, nh_quote
    except Exception as e:  # noqa: BLE001
        add("NH API", "문제", f"모듈 오류 {type(e).__name__}"); return
    gap = nh_gap(NOW)
    if gap is None:
        add("NH API", "정상", "모의매매 주문 시간대 — 이번 점검은 건너뜀"); return
    try:
        q = nh_quote("SPY", NOW, gap)
        add("NH API", "정상", "토큰·시세 조회 정상" + (f" (SPY {q['sess']} ${q['px']})" if q else " (지금 정규장/휴장 — 시간외 값 없음)"))
    except urllib.error.HTTPError as e:
        add("NH API", "주의" if e.code == 429 else "문제", f"HTTP {e.code}", "429=초당 호출 한도(잠시 뒤 정상) · 401/403=키 만료·재발급 필요")
    except FileNotFoundError:
        add("NH API", "문제", "키 파일 없음(~/.nhplug/.env)", "키 파일 위치 확인 — 내용은 출력하지 않음")
    except Exception as e:  # noqa: BLE001
        add("NH API", "문제", f"{type(e).__name__}", "NH 서버 응답 없음 또는 토큰 발급 실패")


# 8 KB API
def check_kb() -> None:
    try:
        t = float((TOOLS / "kb_down.txt").read_text())
    except (OSError, ValueError):
        add("KB API", "정상", "최근 응답 없음 기록 없음"); return
    m = (NOW - t) / 60
    add("KB API", "주의" if m < 30 else "정상", f"마지막 응답 없음 {fmt_min(m)}" + (" — 10분 쉬는 중" if m < 10 else ""),
        "KB 서버 시간 초과 — 국내 시세는 NH로 대신 받음" if m < 30 else "")


# 9 예약 작업
REPEAT = {"트렌드랩_깃풀": 20, "TrendLab_HealthCheck": 15}


def check_tasks() -> None:
    ps = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-ScheduledTask | Where-Object { $_.TaskName -like '트렌드랩_*' -or $_.TaskName -like 'NH_MOCK_*' -or $_.TaskName -like 'TrendLab_*' } | ForEach-Object { "
          "$i = $_ | Get-ScheduledTaskInfo; [pscustomobject]@{n=$_.TaskName; s=[string]$_.State; r=$i.LastTaskResult; "
          "t=$(if ($i.LastRunTime) { $i.LastRunTime.ToString('s') } else { '' })} } | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=60, creationflags=NO_WINDOW)
        rows = json.loads(out.stdout.decode("utf-8", errors="replace") or "[]")
        rows = rows if isinstance(rows, list) else [rows]
    except Exception as e:  # noqa: BLE001
        add("예약 작업", "주의", f"목록 못 읽음({type(e).__name__})"); return
    bad = []
    for x in rows:
        n, r, s = x["n"], int(x.get("r") or 0), x.get("s")
        if s == "Disabled":
            continue
        # 0=성공, 267009=실행 중, 267011=아직 안 돈 것, 267014=사용자가 끝냄
        if r not in (0, 267009, 267011, 267014) and s != "Running":
            bad.append(f"{n}(코드 {r})")
        lim = REPEAT.get(n)
        if lim and x.get("t"):
            m = (T.replace(tzinfo=None) - datetime.fromisoformat(x["t"])).total_seconds() / 60
            if m > lim:
                bad.append(f"{n}({m:.0f}분째 안 돎)")
    add("예약 작업", "주의" if bad else "정상", f"{len(rows)}개 중 " + (f"확인 필요: {' · '.join(bad)}" if bad else "모두 정상"),
        "코드 1·2 = 스크립트 오류로 끝남(그 작업 로그 확인) · 오래 안 돎 = PC 절전·작업 꺼짐" if bad else "")


# 10 SOXL·KORU 시간외 — 사이트 카드가 실제로 보여 줄 값이 있는지
def check_lev() -> None:
    rows = {r["sym"]: r for r in ((NEWS.get("brief") or {}).get("ext") or {}).get("rows") or []}
    sess = ((NEWS.get("brief") or {}).get("ext") or {}).get("sess")
    if not ((NEWS.get("brief") or {}).get("ext") or {}).get("live"):
        add("SOXL·KORU 시간외", "정상", "지금은 시간외 세션 아님(정규장·휴장) — 카드에 정규장 값 표시"); return
    bad = [s for s in ("SOXL", "KORU") if s not in rows or age(rows[s].get("checked_at")) > 5]
    if bad:
        add("SOXL·KORU 시간외", "문제", f"{' · '.join(bad)} 시간외 값 없음/오래됨({sess})", "시간외 시세판(ext_board) 수집 실패 — 사이트 카드에 '마지막 체결'만 표시됨")
    else:
        add("SOXL·KORU 시간외", "정상", " · ".join(f"{s} {rows[s]['src']} ${rows[s]['px']} {rows[s]['chg']:+.2f}%" for s in ("SOXL", "KORU")))


# 11 배포 — 깃허브 페이지의 화면 코드가 최신 커밋과 같은지
def check_deploy() -> None:
    import hashlib
    base = "https://ingforme82-commits.github.io/trend-lab/"
    old = []
    for f in ("news.js", "app.js", "index.html"):
        try:
            local = subprocess.run(["git", "-C", str(TOOLS.parent), "show", f"origin/main:{f}"], capture_output=True, timeout=30, creationflags=NO_WINDOW).stdout
            remote = urllib.request.urlopen(urllib.request.Request(f"{base}{f}?t={int(NOW)}", headers={"Cache-Control": "no-cache"}), timeout=15).read()
            if hashlib.sha1(local.replace(b"\r\n", b"\n")).hexdigest() != hashlib.sha1(remote.replace(b"\r\n", b"\n")).hexdigest():
                old.append(f)
        except Exception as e:  # noqa: BLE001
            old.append(f"{f}({type(e).__name__})")
    st = state_ref.setdefault("deploy_old_since", None)
    if old:
        since = state_ref["deploy_old_since"] = st or NOW
        m = (NOW - since) / 60
        add("사이트 배포", "문제" if m > 20 else "정상", f"배포 대기 {m:.0f}분: {' · '.join(old)}",
            "깃허브 페이지 빌드 실패·지연 — gh api repos/ingforme82-commits/trend-lab/pages/builds 확인" if m > 20 else "")
    else:
        state_ref["deploy_old_since"] = None
        add("사이트 배포", "정상", "화면 코드가 최신 커밋과 같음(열린 창은 5분 안에 자동 새로고침)")


state_ref: dict = {}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    global state_ref
    state_ref = state
    for fn in (check_collector, check_site, lambda: check_futures(state), check_cnbc, check_ext, check_lev, check_rss, check_nh, check_kb, check_tasks, check_deploy):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            add(getattr(fn, "__name__", "점검"), "문제", f"점검 자체 오류 {type(e).__name__}: {str(e)[:80]}")
    worst = "문제" if any(r["level"] == "문제" for r in R) else "주의" if any(r["level"] == "주의" for r in R) else "정상"
    rep = {"at": int(NOW * 1000), "kst": T.strftime("%m-%d %H:%M"), "worst": worst, "items": R}
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    # 새로 생긴 '문제'만 알림·기록
    prev = set(state.get("problems") or [])
    now_p = {f"{r['area']}|{r['msg'][:40]}" for r in R if r["level"] == "문제"}
    new = [r for r in R if r["level"] == "문제" and f"{r['area']}|{r['msg'][:40]}" not in prev]
    if new:
        text = "🩺 실시간 점검 문제\n" + "\n".join(f"· {r['area']}: {r['msg']} — {r['why']}" for r in new)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{T:%m-%d %H:%M} {text}\n")
        try:
            from tg_alert import alert
            alert("실시간점검", "|".join(sorted(now_p))[:200], text)
        except Exception:  # noqa: BLE001
            pass
    fixed = prev - now_p
    if fixed:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{T:%m-%d %H:%M} ✅ 해결: {' / '.join(sorted(fixed))}\n")
    state["problems"] = sorted(now_p)
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    icon = {"정상": "🟢", "주의": "🟡", "문제": "🔴"}
    print(f"{icon[worst]} 실시간 점검 {T:%m-%d %H:%M} — 전체 {worst}")
    for r in R:
        print(f"{icon[r['level']]} {r['area']}: {r['msg']}" + (f"\n     ↳ {r['why']}" if r["why"] and r["level"] != "정상" else ""))


if __name__ == "__main__":
    import urllib.error  # noqa: F401  (check_nh 에서 씀)
    main()
