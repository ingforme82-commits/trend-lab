"""출처 점수판 — 출처마다 응답 성공률·다른 출처와의 일치율·응답 시간·값의 신선도를 계속 기록하고,
점수가 높은 출처를 자동으로 앞에 세운다(2026-11-16 운영자: "멈춰 있지 말고 더 빠르고 정확한 방법으로 계속 진화").

- 점수 = 성공률 × 일치율 ÷ (1 + 응답초/5) ÷ (1 + 신선도분/30). 최근 값에 더 무게(지수 가중, ALPHA).
- 연속 실패 FAIL_MAX 번이면 COOLDOWN 동안 건너뛴다(그 뒤 한 번 다시 시도) → 멈춘 출처 때문에 늦어지지 않는다.
- 기록은 저장소 밖(keystore.state_dir()/srcscore.json). 그룹(예: 'kr', 'fx:원/달러')마다 따로 센다.

  python tools/srcscore.py      # 점수표
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keystore  # noqa: E402

FILE = keystore.state_dir() / "srcscore.json"
ALPHA = 0.1
FAIL_MAX, COOLDOWN = 3, 600
_LOCK = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(d: dict) -> None:
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(FILE)
    except OSError:
        pass


def _ew(old, new):
    return new if old is None else old + ALPHA * (new - old)


def record(group: str, src: str, ok: bool, secs: float | None = None, agree: bool | None = None,
           age_min: float | None = None, now: float | None = None, data: dict | None = None) -> dict:
    """한 번 조회한 결과를 기록. data 를 주면 파일 대신 그 dict 를 고친다(시험용)."""
    now = now or time.time()
    with _LOCK:
        d = _load() if data is None else data
        s = d.setdefault(group, {}).setdefault(src, {"n": 0, "fails": 0})
        s["n"] += 1
        s["ok"] = _ew(s.get("ok"), 1.0 if ok else 0.0)
        if ok:
            s["fails"] = 0
            s["last_ok"] = now
            if secs is not None:
                s["secs"] = _ew(s.get("secs"), secs)
            if agree is not None:
                s["agree"] = _ew(s.get("agree"), 1.0 if agree else 0.0)
            if age_min is not None:
                s["age"] = _ew(s.get("age"), max(0.0, age_min))
        else:
            s["fails"] = s.get("fails", 0) + 1
            if s["fails"] >= FAIL_MAX:
                s["skip_until"] = now + COOLDOWN
        s["at"] = now
        if data is None:
            _save(d)
        return s


def score(s: dict) -> float:
    return (s.get("ok", 1.0) * s.get("agree", 1.0)
            / (1 + (s.get("secs") or 0) / 5) / (1 + (s.get("age") or 0) / 30))


def skip(group: str, src: str, now: float | None = None, data: dict | None = None) -> bool:
    """쉬는 중이면 True. 쉬는 시간이 끝났으면 한 번 다시 시도(False)."""
    s = ((data if data is not None else _load()).get(group) or {}).get(src) or {}
    return (s.get("skip_until") or 0) > (now or time.time())


def rank(group: str, default: list[str], data: dict | None = None) -> list[str]:
    """점수 높은 순. 기록이 적은 출처(10번 미만)는 기본 순서 자리를 지킨다."""
    g = (data if data is not None else _load()).get(group) or {}
    known = {s: score(g[s]) for s in default if s in g and g[s].get("n", 0) >= 10}
    if not known:
        return list(default)
    out = list(default)
    slots = [i for i, s in enumerate(out) if s in known]
    for i, s in zip(slots, sorted(known, key=lambda x: -known[x])):
        out[i] = s
    return out


NAMES = {"kr": "국내 지수·주가(증권사 교차 확인)", "rt": "실시간 체결(웹소켓)", "fx:원/달러": "원/달러", "fx:달러인덱스": "달러인덱스"}


def summary(data: dict | None = None) -> list[dict]:
    """사이트 표시용: 그룹마다 점수 순 출처(키·값은 없음, 숫자만)."""
    d = data if data is not None else _load()
    now = time.time()
    out = []
    for g, srcs in sorted(d.items()):
        rows = [{"src": s, "score": round(score(v), 2), "ok": round(v.get("ok", 0), 2), "agree": round(v.get("agree", 1), 2),
                 "secs": round(v.get("secs") or 0, 1), "age": round(v.get("age") or 0), "n": v.get("n", 0),
                 "rest": (v.get("skip_until") or 0) > now}
                for s, v in sorted(srcs.items(), key=lambda kv: -score(kv[1]))]
        out.append({"group": g, "name": NAMES.get(g, g), "rows": rows})
    return out


def table(data: dict | None = None) -> list[str]:
    d = data if data is not None else _load()
    lines = []
    for g, srcs in sorted(d.items()):
        lines.append(f"[{g}]")
        for s, v in sorted(srcs.items(), key=lambda kv: -score(kv[1])):
            rest = f" · 쉬는 중 {int(v['skip_until'] - time.time())}초" if (v.get("skip_until") or 0) > time.time() else ""
            lines.append(f"  {s:<8} 점수 {score(v):.2f} · 성공 {v.get('ok', 0):.0%} · 일치 {v.get('agree', 1):.0%}"
                         f" · 응답 {v.get('secs') or 0:.1f}초 · 신선도 {v.get('age') or 0:.0f}분 · {v.get('n')}회{rest}")
    return lines


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(table()) or "기록 없음")
