"""3회 이상 독립 접촉을 검증하는 채널선. 허용 오차는 운영 설정이며 예측 신뢰도 수치가 아니다."""
from __future__ import annotations

import math


def _contacts(values: list[float], pivots: list[int], slope: float, intercept: float,
              tolerance: float, spacing: int) -> list[int]:
    hits = []
    for i in pivots:
        line = slope * i + intercept
        if line <= 0 or abs(values[i] / line - 1) * 100 > tolerance + 1e-9:
            continue
        if not hits or i - hits[-1] >= spacing:
            hits.append(i)
    return hits


def fit_side(values: list[float], dates: list[str], start: int, second_start: str, last: int,
             upper: bool, *, tolerance_pct: float = 0.75, min_spacing: int = 3,
             min_touches: int = 3) -> dict | None:
    """마지막 진행 봉은 호출자가 last에서 제외. 붙어 있는 같은 고점/저점은 한 접촉만 센다."""
    if not (0 <= start < last < len(values)):
        return None
    if len(dates) != len(values) or not all(math.isfinite(v) and v > 0 for v in values[:last + 1]):
        return None
    tolerance = float(tolerance_pct)
    spacing = int(min_spacing)
    required = max(3, int(min_touches))
    if not math.isfinite(tolerance) or not 0 <= tolerance <= 2 or spacing < 1:
        raise ValueError("Invalid contact settings")
    # 오른쪽 이웃까지 닫힌 봉만 확정 피벗으로 사용한다. 첫 기준점은 기존 기준 구간의 극값.
    pivots = [start]
    for i in range(start + 1, last):
        before, value, after = values[i - 1:i + 2]
        if value == before:
            continue  # 같은 평평한 고점·저점 구간 끝을 새 접촉으로 중복 계산하지 않는다.
        turn = (value >= before and value >= after and (value > before or value > after)) if upper else (
            value <= before and value <= after and (value < before or value < after))
        if turn:
            pivots.append(i)
    candidates = [i for i in pivots[1:] if dates[i] >= second_start and i - start >= spacing]
    # 실제 접촉이 부족해도 기존 외곽 기준선은 참고용으로 남긴다.
    eligible = [i for i in range(start + 1, last + 1) if dates[i] >= second_start]
    if not eligible:
        return None
    edge = (max if upper else min)(eligible, key=lambda i: (values[i] - values[start]) / (i - start))
    candidates = sorted(set(candidates + [edge]))
    best = None
    fallback = None
    for second in candidates:
        slope = (values[second] - values[start]) / (second - start)
        intercept = values[start] - slope * start
        hits = _contacts(values, pivots, slope, intercept, tolerance, spacing)
        if len(hits) >= required:
            # 3점 이상을 함께 맞추되 약간의 관통은 허용 오차 안에서만 인정한다.
            mean_x = sum(hits) / len(hits)
            mean_y = sum(values[i] for i in hits) / len(hits)
            denominator = sum((i - mean_x) ** 2 for i in hits)
            if denominator:
                slope = sum((i - mean_x) * (values[i] - mean_y) for i in hits) / denominator
                intercept = mean_y - slope * mean_x
                hits = _contacts(values, pivots, slope, intercept, tolerance, spacing)
        violation = 0.0
        for i in range(start, last + 1):
            line = slope * i + intercept
            if line <= 0:
                violation = float("inf")
                break
            overlap = (values[i] / line - 1) * 100 if upper else (1 - values[i] / line) * 100
            violation = max(violation, overlap)
        errors = [abs(values[i] / (slope * i + intercept) - 1) * 100 for i in hits]
        valid = len(hits) >= required and start in hits and violation <= tolerance + 1e-9
        candidate = {"slope": slope, "intercept": intercept, "touches": hits or [start],
                     "start": start, "anchors": [start, second], "verified": valid,
                     "max_overlap_pct": violation if math.isfinite(violation) else None, "max_touch_error_pct": max(errors, default=0.0)}
        if valid:
            score = (len(hits), hits[-1] - hits[0], -sum(errors) / len(errors), -violation)
            if best is None or score > best[0]:
                best = (score, candidate)
        if second == edge:
            fallback = candidate
    return best[1] if best else fallback


def fit_recent_side(values: list[float], dates: list[str], preferred_start: int, second_start: str,
                    last: int, upper: bool, **rules) -> dict | None:
    """기존 기준선 우선. 3회 접촉이 없으면 최근 관찰 창의 확정 피벗에서 대안을 찾는다."""
    reference = fit_side(values, dates, preferred_start, second_start, last, upper, **rules)
    if reference and reference["verified"]:
        return reference
    best = None
    for start in range(1, last - 5):
        before, value, after = values[start - 1:start + 2]
        if value == before:
            continue
        turn = value >= before and value >= after if upper else value <= before and value <= after
        if not turn:
            continue
        candidate = fit_side(values, dates, start, "", last, upper, **rules)
        if not candidate or not candidate["verified"]:
            continue
        hits = candidate["touches"]
        score = (len(hits), hits[-1] - hits[0], -candidate["max_touch_error_pct"], hits[-1])
        if best is None or score > best[0]:
            best = (score, candidate)
    return best[1] if best else reference
