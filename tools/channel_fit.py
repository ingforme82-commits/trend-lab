"""지정된 하락 구간의 두 기준점을 유지하고 추가 접촉만 센다. 선을 임의로 재맞추지 않는다."""
from __future__ import annotations

import math


def anchored_side(values: list[float], dates: list[str], start: int, second_start: str, last: int,
                  upper: bool, *, tolerance_pct: float = 0.75, min_spacing: int = 3) -> dict | None:
    if len(values) != len(dates) or not (0 <= start < last < len(values)):
        return None
    if not all(math.isfinite(v) and v > 0 for v in values[:last + 1]):
        return None
    tolerance, spacing = float(tolerance_pct), int(min_spacing)
    if not math.isfinite(tolerance) or not 0 <= tolerance <= 2 or spacing < 1:
        raise ValueError("Invalid contact settings")
    candidates = [i for i in range(start + 1, last + 1)
                  if dates[i] >= second_start and i - start >= spacing]
    if not candidates:
        return None
    # 과거 방식의 외곽선: 기존 첫 기준점을 유지하고 이후 가장 바깥 고점/저점을 연결.
    second = (max if upper else min)(candidates, key=lambda i: (values[i] - values[start]) / (i - start))
    slope = (values[second] - values[start]) / (second - start)
    intercept = values[start] - slope * start
    hits = sorted([start, second])
    for i in range(start + 1, last):
        if i in hits or any(abs(i - j) < spacing for j in hits):
            continue
        before, value, after = values[i - 1:i + 2]
        if value == before:
            continue  # 같은 평평한 구간을 여러 접촉으로 세지 않는다.
        pivot = value >= before and value >= after if upper else value <= before and value <= after
        line = slope * i + intercept
        if pivot and line > 0 and abs(value / line - 1) * 100 <= tolerance + 1e-9:
            hits.append(i)
            hits.sort()
    overlap = 0.0
    active_overlap = 0.0
    for i in range(start, last + 1):
        line = slope * i + intercept
        if line <= 0:
            overlap = float("inf")
            active_overlap = float("inf")
            break
        penetration = (values[i] / line - 1) * 100 if upper else (1 - values[i] / line) * 100
        overlap = max(overlap, penetration)
        if i >= second:
            active_overlap = max(active_overlap, penetration)
    return {"slope": slope, "intercept": intercept, "touches": hits, "anchors": [start, second],
            "start": start, "verified": active_overlap <= tolerance + 1e-9,
            "max_overlap_pct": overlap if math.isfinite(overlap) else None,
            "active_overlap_pct": active_overlap if math.isfinite(active_overlap) else None}


def support_path(values: list[float], dates: list[str], pivot_dates: list[str], last: int,
                 *, tolerance_pct: float = 0.75) -> dict | None:
    """지정한 실제 저점 세 개를 잇는다. 직선 적합/가짜 접촉 없이 마지막 구간을 연장."""
    if len(pivot_dates) != 3 or len(set(pivot_dates)) != 3:
        return None
    try:
        hits = [dates.index(day) for day in pivot_dates]
    except ValueError:
        return None
    if hits != sorted(hits) or hits[-1] > last or not all(math.isfinite(values[i]) and values[i] > 0 for i in hits):
        return None
    def line(i):
        a, b = (hits[0], hits[1]) if i <= hits[1] else (hits[1], hits[2])
        return values[a] + (values[b] - values[a]) * (i - a) / (b - a)
    overlap = max([0.0] + [(1 - values[i] / line(i)) * 100 for i in range(hits[0], last + 1) if line(i) > 0])
    active = max([0.0] + [(1 - values[i] / line(i)) * 100 for i in range(hits[-1], last + 1) if line(i) > 0])
    slope = (values[hits[-1]] - values[hits[-2]]) / (hits[-1] - hits[-2])
    return {"slope": slope, "intercept": values[hits[-1]] - slope * hits[-1],
            "touches": hits, "anchors": hits, "start": hits[0], "verified": active <= tolerance_pct + 1e-9,
            "max_overlap_pct": overlap, "active_overlap_pct": active,
            "path": [[i, values[i]] for i in hits]}
