"""Synchronize selected official BEA releases into the TRL checkpoints."""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.request
from zoneinfo import ZoneInfo

SOURCE = "https://www.bea.gov/news/schedule"
LABEL = "미국 BEA 공식 발표 일정"
MARKER = "bea-release"
ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")
DATE = re.compile(r"\b([A-Z][a-z]+)\s+(\d{1,2})\s+(\d{1,2}:\d{2})\s*([AP]M)\b", re.I)


class ScheduleRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.parts = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.parts = []

    def handle_endtag(self, tag):
        if tag == "tr" and self.parts is not None:
            self.rows.append(" ".join(" ".join(self.parts).split()))
            self.parts = None

    def handle_data(self, data):
        if self.parts is not None and data.strip():
            self.parts.append(data.strip())


def events(page, today):
    parser = ScheduleRows()
    parser.feed(page)
    by_time = defaultdict(set)
    dated_rows = 0
    matched_rows = 0
    for row in parser.rows:
        found = DATE.search(row)
        if not found:
            continue
        dated_rows += 1
        lower = row.lower()
        kind = "pce" if "personal income and outlays" in lower else "gdp" if "gdp (" in lower else None
        if not kind:
            continue
        month, day, clock, period = found.groups()
        try:
            release = datetime.strptime(f"{today.year} {month} {day} {clock} {period.upper()}", "%Y %B %d %I:%M %p").replace(tzinfo=ET)
            if today.month == 12 and release.month == 1:
                release = release.replace(year=today.year + 1)
        except ValueError as error:
            raise ValueError("Unrecognized BEA release date") from error
        matched_rows += 1
        kst = release.astimezone(KST)
        if today <= kst.date() <= today + timedelta(days=14):
            by_time[kst].add(kind)
    if not dated_rows or not matched_rows:
        raise ValueError("Official calendar format changed or no BEA releases could be verified")
    titles = {"pce": "미국 PCE 물가", "gdp": "미국 GDP 발표"}
    notes = {
        "pce": "헤드라인·근원 PCE와 발표 직후 미 국채금리·달러·나스닥 선물 반응을 확인합니다.",
        "gdp": "성장률 수정 여부와 발표 직후 미 국채금리·달러의 방향을 확인합니다.",
    }
    return [
        {"date": when.date().isoformat(), "time": when.strftime("%H:%M"),
         "title": " · ".join(titles[kind] for kind in ("pce", "gdp") if kind in kinds),
         "note": notes["pce"] if "pce" in kinds else notes["gdp"],
         "source": LABEL, "managed_by": MARKER}
        for when, kinds in sorted(by_time.items())
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path)
    parser.add_argument("--checkpoints", type=Path, default=Path("data/checkpoints.json"))
    args = parser.parse_args()
    today = datetime.now(KST).date()
    if args.html:
        page = args.html.read_text(encoding="utf-8")
    else:
        req = urllib.request.Request(SOURCE, headers={"User-Agent": "TRL calendar sync"})
        with urllib.request.urlopen(req, timeout=20) as response:
            page = response.read().decode("utf-8")
    verified = events(page, today)
    original = json.loads(args.checkpoints.read_text(encoding="utf-8"))
    if not verified:
        print("No verified releases in the 14-day window. Existing checkpoints retained.")
        return
    if not all(isinstance(x, dict) and isinstance(x.get("date"), str) for x in original):
        raise ValueError("Invalid checkpoint dataset")
    # Keep editorial and historical entries. The existing combined BEA row is migrated once.
    kept = [row for row in original if not (
        row["date"] >= today.isoformat() and (
            row.get("managed_by") == MARKER or
            (row.get("source") == LABEL and row.get("title") == "미국 10월 PCE 물가 · 3분기 GDP 잠정치"
             and all(any(title in item["title"] for item in verified) for title in ("PCE", "GDP")))
        )
    )]
    merged = sorted(kept + verified, key=lambda row: (row["date"], row.get("time") or ""))
    if merged != original:
        temporary = args.checkpoints.with_suffix(".tmp")
        temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        temporary.replace(args.checkpoints)
    print(f"Verified {len(verified)} official BEA checkpoint slots.")


if __name__ == "__main__":
    main()
