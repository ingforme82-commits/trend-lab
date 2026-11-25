"""Publish Taiwanese and Japanese index snapshots independently of live news."""
import base64
import json

from market_extra import _taiex, _yf
from nh_quotes import REPO, gh


def collect():
    taiwan = _taiex()
    japan = _yf("^N225")
    rows = []
    if taiwan:
        rows.append({**taiwan, "sym": "TAIEX", "name": "가권지수", "region": "대만"})
    if japan and japan["px"] and japan["prev"]:
        px, low = japan["px"], japan.get("low")
        row = {"sym": "^N225", "name": "니케이225", "region": "일본", "px": px,
               "at": japan["at"], "chg": round((px / japan["prev"] - 1) * 100, 2)}
        if low and 0 < low <= px:
            row.update(low=low, rebound=round((px / low - 1) * 100, 2))
        rows.append(row)
    return rows


def main():
    rows = collect()
    if not rows:
        raise RuntimeError("Asian index sources unavailable")
    endpoint = f"repos/{REPO}/contents/asia-quotes.json"
    try:
        current = gh([endpoint + "?ref=quotes"])
    except RuntimeError:
        current = {}
    previous = json.loads(base64.b64decode(current["content"])) if current else []
    merged = {row["sym"]: row for row in previous}
    for row in rows:
        if row["at"] >= merged.get(row["sym"], {}).get("at", 0):
            merged[row["sym"]] = row
    updated = list(merged.values())
    if updated == previous:
        return
    payload = {"branch": "quotes", "message": "Update Asian index quotes",
               "content": base64.b64encode(json.dumps(updated, ensure_ascii=False).encode()).decode()}
    if current:
        payload["sha"] = current["sha"]
    gh(["--method", "PUT", endpoint], payload)


if __name__ == "__main__":
    main()
