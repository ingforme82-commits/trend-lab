"""🔥 오늘의 주요 종목군 — 화면에 내보내기 전 매분 정리(2026-11-15 운영자: "중복되는 것도 있고, 중요도가 높지 않아 보이는 것도 있고").

1) 중복: 켜진 종목군의 구성 종목인 개별 카드(예: AMD ⊂ 미국 반도체, 코어위브·네비우스 ⊂ 네오클라우드)는 종목군 카드에 합친다.
2) 오래된 개별 카드: 가장 최근 선정일(since)보다 이전에 뽑힌 ⚡ 개별 카드는 뺀다(11/10·11/12 카드가 남던 문제).
3) 관련성: 개별 카드는 TRL 관심 종목군(spot_pool) 구성 종목이거나 최근 24시간 관련 속보 3건 이상일 때만(예: 누 홀딩스 제외).
4) 순서: 지금 |등락| + 최근 12시간 관련 속보(최대 10건 × 0.3) + 📈 연일 상승 0.5 — 상위 MAX 개. pin(한국·일본)은 맨 뒤 고정.
5) 한국·일본 카드 설명은 교차 확인된 한국 시세와 니케이로 매분 다시 쓴다(11/2 설명이 남던 문제).
수치·출처만 쓴다(추천 아님).
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "data" / "spot_pool.json"
KST = timezone(timedelta(hours=9))
MAX = 6
NEED_NEWS = 3


def _pool_syms() -> set[str]:
    try:
        p = json.loads(POOL.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return set()
    return {sym for g in p.values() for sym in (g.get("members") or {})}


def _hits(s: dict, items: list[dict], hours: int, now_ms: int) -> int:
    """관련 속보 수. 개별 종목은 한 글자 이름('누')이 한국어 문장에 걸리지 않게 2글자 이상 이름·영문 티커만."""
    if s.get("members") or s.get("avg"):
        pat = s.get("kw") or s.get("name") or ""
    else:
        parts = []
        for p in (s.get("kw") or "").split("|"):
            core = re.sub(r"\\b|\\\(|\\\)|[()]", "", p)
            if len(core) < 2:
                continue
            if re.fullmatch(r"[A-Za-z]{2,4}", core):        # 짧은 영문(Nu·AMD)은 단어 단위로만('Nuclear' 속 Nu 제외)
                p = rf"\b{core}\b"
            parts.append(p)
        pat = "|".join(parts) or re.escape(s.get("name") or "")
    try:
        rx = re.compile(pat, re.I)
    except re.error:
        return 0
    return sum(1 for n in items if now_ms - n["ts"] < hours * 3600_000
               and rx.search(n.get("text", "") + " " + n.get("orig", "") + " " + n.get("sub", "")))


def _pc(v) -> str:
    return "-" if v is None else f"{v:+.2f}%"


def asia_reason(kr: dict, world: list[dict]) -> str | None:
    if not kr.get("KOSPI"):
        return None
    k = kr["KOSPI"]
    when = ("장중 " + datetime.now(KST).strftime("%H:%M")) if k.get("open") else (
        (datetime.fromtimestamp(k["at"] / 1000, KST).strftime("%m/%d") + " 마감") if k.get("at") else "마감")
    parts = [f"코스피 {k['px']:,.2f}({_pc(k.get('chg'))})"]
    for key, nm in (("KOSDAQ", "코스닥"), ("SMSN", "삼성전자"), ("SKHX", "SK하이닉스")):
        if kr.get(key):
            parts.append(f"{nm} {_pc(kr[key].get('chg'))}")
    nk = next((w for w in world if "니케이" in w.get("name", "")), None)
    if nk:
        parts.append(f"니케이225 {_pc(nk.get('chg'))}")
    xc = k.get("xc")
    return f"{when} · " + " · ".join(parts) + (f" · 증권사 {xc} 일치" if xc else "")


def renew(spot: list[dict], items: list[dict], kr: dict | None = None, world: list[dict] | None = None,
          pool: set[str] | None = None, now_ms: int | None = None) -> list[dict]:
    now_ms = now_ms or int(time.time() * 1000)
    pool = _pool_syms() if pool is None else pool
    spot = [dict(s) for s in spot]
    groups = [s for s in spot if s.get("members") is not None or s.get("avg")]
    singles = [s for s in spot if s not in groups and not s.get("pin")]
    pins = [s for s in spot if s.get("pin") or s.get("id") == "ASIA"]
    groups = [g for g in groups if g not in pins]

    # 2) 오래된 개별 카드
    latest = max((s.get("since") or "" for s in singles), default="")
    singles = [s for s in singles if (s.get("since") or "") >= latest]
    # 1) 중복 → 종목군에 합침
    keep = []
    for s in singles:
        host = next((g for g in groups if any(m.get("sym") == s.get("id") for m in g.get("members") or [])), None)
        if host:
            host.setdefault("inc", []).append(f"{s['name']}({s.get('kind') or '개별'})")
            continue
        keep.append(s)
    # 3) 관련성
    singles = [s for s in keep if s.get("id") in pool or _hits(s, items, 24, now_ms) >= NEED_NEWS]
    for g in groups:
        if g.get("reason") and not g["reason"].startswith("선정 당시") and not (g.get("kind") or "").startswith("📈"):
            g["reason"] = "선정 당시 " + g["reason"]      # 지금 수치는 카드 머리(평균 등락)에, 이 줄은 뽑힐 때 수치
        if g.get("inc"):
            g["reason"] = (g.get("reason") or "") + " · 포함: " + ", ".join(g.pop("inc"))
    # 4) 순서
    def score(s: dict) -> float:
        return abs(s.get("chg") or 0) + min(_hits(s, items, 12, now_ms), 10) * 0.3 + (0.5 if (s.get("kind") or "").startswith("📈") else 0)
    ranked = sorted(groups + singles, key=lambda s: -score(s))[:MAX]
    for s in ranked:
        s["n12"] = _hits(s, items, 12, now_ms)
    # 5) 한국·일본 카드
    for p in pins:
        r = asia_reason(kr or {}, world or [])
        if r:
            p["reason"] = r
            p["since"] = datetime.now(KST).strftime("%Y-%m-%d")
    return ranked + pins
