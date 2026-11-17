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
