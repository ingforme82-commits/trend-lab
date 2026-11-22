"""텔레 글에 붙은 사진·PDF 에서 글자 꺼내기(2단계, 11/22 운영자 승인 A안) — live_news 가 1분마다 조금씩 부른다.

- 새로 내려받지 않는다. 수집기(market-site/tg_research)가 이미 받아 둔 파일(messages.media_path)만 읽는다.
- 사진: 무료 Tesseract(kor+eng). 서버에 `tesseract` 명령이 없으면 조용히 건너뛰고 상태에 '미설치'만 남긴다.
  (pytesseract 패키지는 쓰지 않는다 — 명령을 직접 부르므로 apt 설치만 있으면 된다)
- PDF: pypdf 로 앞 PDF_PAGES 쪽 글자만. 20MB 넘어 수집기가 글자만 남긴 'pdf_text_only'(.txt)는 그 글자를 읽는다.
- 처리 결과는 tools/media_text.sqlite3 에 캐시(같은 파일·같은 크기면 다시 처리하지 않음). 저장하는 글자도 앞 KEEP_CHARS 자만.
- 사이트(news.json)에는 여기서 만든 '제목 + 한 줄(120자 이내)'만 나간다(live_news). 본문 전문은 싣지 않는다.
- 1분 회차 부하: 회차당 사진 MAX_OCR_PER_RUN 장 · PDF MAX_PDF_PER_RUN 개 · 전체 BUDGET_S 초 안에서만(상수는 이 파일 한 곳).
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

CACHE_DB = Path(__file__).resolve().parent / "media_text.sqlite3"

# ── 회차당 처리 한도(보수적 기본값 — 근거는 티켓 인수인계, CTO 확인 필요) ──
MAX_OCR_PER_RUN = 2        # 사진 OCR 장수/회차
MAX_PDF_PER_RUN = 3        # PDF 개수/회차
BUDGET_S = 8.0             # 회차당 전체 시간 예산(초) — tg_research/fast_news.py 의 PDF_BUDGET 과 같은 값
OCR_TIMEOUT_S = 8          # tesseract 한 장 제한(초)
PDF_PAGES = 2              # PDF 앞 몇 쪽만
PDF_MAX_MB = 20            # 이보다 큰 PDF 는 읽지 않음(수집기 pdf_max_size_mb 와 같은 기준)
MAX_TRY = 2                # 실패한 파일 재시도 횟수(넘으면 포기)
KEEP_CHARS = 600           # 캐시에 남기는 글자 수(제목·한 줄 뽑는 데 충분한 만큼만)
TITLE_MAX, SUB_MAX = 80, 120
NO_WINDOW = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

HEALTH: dict = {}
_status: dict = {}


def tesseract_status() -> str:
    """'정상' · '미설치'(명령 없음) · '한국어 데이터 없음'(tesseract-ocr-kor 없음). 한 번만 확인."""
    if "ocr" in _status:
        return _status["ocr"]
    exe = shutil.which("tesseract")
    if not exe:
        _status["ocr"] = "미설치"
        return _status["ocr"]
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        langs = set((out.stdout or "").split()) | set((out.stderr or "").split())
        _status["ocr"] = "정상" if "kor" in langs else "한국어 데이터 없음"
    except Exception:  # noqa: BLE001
        _status["ocr"] = "미설치"
    _status["exe"] = exe
    return _status["ocr"]


def pdf_status() -> str:
    if "pdf" not in _status:
        try:
            import pypdf  # noqa: F401
            _status["pdf"] = "정상"
        except Exception:  # noqa: BLE001
            _status["pdf"] = "미설치"
    return _status["pdf"]


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(str(CACHE_DB), timeout=5)
    con.execute("create table if not exists media_text (path text primary key, size integer, kind text, ok integer, "
                "text text, tries integer, at real)")
    return con


def lookup(paths: list[str]) -> dict[str, dict]:
    """캐시에 있는 결과 {path: {ok, text, tries, size}} (읽기만)."""
    if not paths or not CACHE_DB.exists():
        return {}
    con = _con()
    try:
        out = {}
        for i in range(0, len(paths), 500):
            chunk = paths[i:i + 500]
            for p, size, ok, text, tries in con.execute(
                    f"select path, size, ok, text, tries from media_text where path in ({','.join('?' * len(chunk))})", chunk):
                out[p] = {"size": size, "ok": bool(ok), "text": text or "", "tries": tries or 0}
        return out
    finally:
        con.close()


def _size(path: str) -> int | None:
    try:
        return Path(path).stat().st_size
    except OSError:
        return None


def ocr_image(path: str, timeout: float) -> str:
    exe = _status.get("exe") or shutil.which("tesseract")
    done = subprocess.run([exe, path, "stdout", "-l", "kor+eng"], capture_output=True, timeout=max(1.0, timeout),
                          creationflags=NO_WINDOW)
    if done.returncode != 0:
        raise RuntimeError(f"tesseract 종료코드 {done.returncode}")
    return done.stdout.decode("utf-8", "replace")


def pdf_text(path: str, deadline: float | None = None) -> str:
    """앞 PDF_PAGES 쪽 글자. deadline(time.monotonic 기준)을 넘기면 다음 쪽은 읽지 않는다(이상한 PDF 하나가 회차를 붙잡지 않게)."""
    p = Path(path)
    if p.suffix.lower() == ".txt":                     # 수집기가 큰 PDF 대신 남긴 글자 파일
        return p.read_text(encoding="utf-8", errors="replace")[:5000]
    if p.stat().st_size > PDF_MAX_MB * 1024 * 1024:
        raise RuntimeError("PDF 너무 큼")
    from pypdf import PdfReader
    reader = PdfReader(str(p))
    if reader.is_encrypted:
        raise RuntimeError("암호 PDF")
    out = []
    for pg in reader.pages[:PDF_PAGES]:
        out.append(pg.extract_text() or "")
        if deadline is not None and time.monotonic() > deadline:
            break
    return "\n".join(out)


def process(cands: list[tuple[str, str]], budget_s: float | None = None) -> dict:
    """cands = [(kind 'ocr'|'pdf', path)] 최신 글 먼저. 캐시에 없는 것만 회차 한도 안에서 처리. 상태를 HEALTH 에 남긴다."""
    t0 = time.monotonic()
    budget = BUDGET_S if budget_s is None else min(BUDGET_S, budget_s)
    h = {"ocr": tesseract_status() if any(k == "ocr" for k, _ in cands) else _status.get("ocr", "확인 안 함"),
         "pdf": pdf_status() if any(k == "pdf" for k, _ in cands) else _status.get("pdf", "확인 안 함"),
         "done_ocr": 0, "done_pdf": 0, "fail": 0, "wait": 0, "ms": 0}
    seen = lookup([p for _, p in cands])
    todo = []
    for kind, path in cands:
        size = _size(path)
        c = seen.get(path)
        if size is None:
            continue                                  # 파일 없음(다른 PC 경로 등) — 처리 대상 아님
        if c and c["size"] == size and (c["ok"] or c["tries"] >= MAX_TRY):
            continue
        if (kind == "ocr" and h["ocr"] != "정상") or (kind == "pdf" and h["pdf"] != "정상"):
            continue                                  # 미설치 — 조용히 건너뜀
        todo.append((kind, path, size, (c or {}).get("tries", 0) if c and c["size"] == size else 0))
    n = {"ocr": 0, "pdf": 0}
    lim = {"ocr": MAX_OCR_PER_RUN, "pdf": MAX_PDF_PER_RUN}
    con = _con() if todo else None
    try:
        for kind, path, size, tries in todo:
            left = budget - (time.monotonic() - t0)
            if n[kind] >= lim[kind] or left <= 0.5:
                h["wait"] += 1
                continue
            n[kind] += 1
            try:
                raw = ocr_image(path, min(OCR_TIMEOUT_S, left)) if kind == "ocr" else pdf_text(path, t0 + budget)
                text = re.sub(r"[ \t]+", " ", raw).strip()[:KEEP_CHARS]
                ok = 1 if text else 0
            except Exception:  # noqa: BLE001
                text, ok = "", 0
            con.execute("insert or replace into media_text values (?,?,?,?,?,?,?)",
                        (path, size, kind, ok, text, tries + 1, time.time()))
            con.commit()
            h["done_" + kind] += ok
            h["fail"] += 1 - ok
    finally:
        if con is not None:
            con.close()
    h["ms"] = int((time.monotonic() - t0) * 1000)
    HEALTH.clear()
    HEALTH.update(h)
    return h


# ── 꺼낸 글자 → 제목 한 줄 + 요약 한 줄 ──
_SKIP = re.compile(r"https?://|www\.|Compliance|본\s?자료는|투자\s?판단|무단\s?(?:복제|배포)|저작권|All rights|Disclaimer|"
                   r"☎|\d{2,3}-\d{3,4}-\d{4}|@\w|Analyst|애널리스트|\bRA\b|^\W*\d{1,3}\W*$|텔레그램\s?채널|t\.me/|"
                   r"^\W*\d{4}[.\-/년]\s?\d{1,2}[.\-/월]\s?\d{1,2}일?\W*(?:\([월화수목금토일]\))?\W*$", re.I)


# 한글·영문·숫자·한자·흔한 기호 밖의 글자(깨진 글꼴에서 나오는 다른 문자권)
_ODD = re.compile(r"[^\x00-\x7F -ÿ가-힣ㄱ-ㅎㅏ-ㅣ一-鿿 -➿　-〿＀-￯]")


def _good(line: str) -> bool:
    """OCR 잡음 줄 거르기: 글자(한글·영문·숫자)가 대부분이고 8자 이상."""
    s = line.strip()
    if len(s) < 8 or _SKIP.search(s):
        return False
    if (" " not in s and not re.search(r"[가-힣]", s) and len(s) >= 13) or re.search(r"[A-Z!]{10,}", s) or _ODD.search(s):
        return False                                  # 글꼴이 깨진 PDF 글자('*OWFTUNFOU4USBUFHZ'·'ਬݺр NZPVOHH…')
    if not re.search(r"[가-힣]", s) and not re.search(r"[a-z]{3,}", s):
        return False                                  # 한글 없는 줄은 소문자 낱말이 있어야(대문자 덩어리 '*7 "QQFOEJY Q' 제외)
    letters = len(re.findall(r"[0-9A-Za-z가-힣]", s))
    return letters >= len(s.replace(" ", "")) * 0.6


def headline(text: str) -> tuple[str, str]:
    """(제목 ≤TITLE_MAX, 한 줄 ≤SUB_MAX). 쓸 줄이 없으면 ("", "")."""
    lines = [re.sub(r"\s+", " ", ln).strip(" -—:•▶►▷◆◇■□※·|[]") for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if _good(ln)]
    if not lines:
        return "", ""
    cut = lambda s, n: s if len(s) <= n else s[:n - 1].rstrip() + "…"  # noqa: E731
    title = cut(lines[0], TITLE_MAX)
    sub = next((cut(ln, SUB_MAX) for ln in lines[1:] if len(ln) >= 15 and ln not in title), "")
    return title, sub
