"""Check the public collector snapshot before it is used for CIO research."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import urllib.request

FEED = "https://raw.githubusercontent.com/ingforme82-commits/trend-lab/live/news.json"
MINUTE = 60000


def age_minutes(value, now):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        return None
    if value > now + MINUTE:
        return None
    return round(max(0, now - value) / MINUTE, 1)


def summarize(snapshot, now, max_feed_age):
    health = snapshot.get("health") or {}
    rss = health.get("rss") or {}
    tg = health.get("tg") or {}
    translation = health.get("tr") or {}
    age = age_minutes(snapshot.get("updated"), now)
    releases = snapshot.get("items")
    issues = []
    warnings = []
    if age is None or age > max_feed_age:
        issues.append("feed_timestamp_missing_or_stale")
    if not isinstance(releases, list):
        issues.append("news_items_unavailable")
    rss_age = age_minutes(rss.get("at"), now)
    tg_poll_age = age_minutes(tg.get("got"), now)
    if rss_age is None or rss_age > max_feed_age:
        warnings.append("rss_snapshot_missing_or_old")
    if rss.get("fail"):
        warnings.append("rss_partial_failure")
    if tg.get("refresh") is False or tg_poll_age is None or tg_poll_age > max_feed_age:
        warnings.append("telegram_collection_unconfirmed")
    if translation.get("fail"):
        warnings.append("translations_pending_original_retained")
    latest = lambda rows, key: max((row[key] for row in rows if isinstance(row, dict) and age_minutes(row.get(key), now) is not None), default=None)
    return {
        "checked_at": datetime.fromtimestamp(now / 1000, timezone.utc).isoformat(),
        "status": "hold" if issues else "degraded" if warnings else "ready_for_research",
        "issues": issues,
        "warnings": warnings,
        "feed_age_minutes": age,
        "latest_headline_age_minutes": age_minutes(latest(releases or [], "ts"), now),
        "latest_reaction_age_minutes": age_minutes(latest(snapshot.get("moves") or [], "end"), now),
        "rss_poll_age_minutes": rss_age,
        "telegram_poll_age_minutes": tg_poll_age,
        "rss_received": rss.get("ok"),
        "rss_total": rss.get("total"),
        "translations_pending": translation.get("fail"),
        "execution_ready": False,
        "execution_review_requires": ["daily_channel_context", "synchronized_market_bars", "cio_review"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, help="Read an existing snapshot")
    parser.add_argument("--max-feed-age", type=float, default=15, help="Operational review limit in minutes")
    args = parser.parse_args()
    if not math.isfinite(args.max_feed_age) or args.max_feed_age <= 0:
        parser.error("--max-feed-age must be positive and finite")
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    try:
        if args.snapshot:
            snapshot = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
        else:
            request = urllib.request.Request(FEED + f"?t={now // MINUTE}", headers={"User-Agent": "TRL feed check"})
            with urllib.request.urlopen(request, timeout=8) as response:
                snapshot = json.load(response)
        result = summarize(snapshot, now, args.max_feed_age)
    except (OSError, ValueError, TypeError, AttributeError):
        result = {"status": "hold", "issues": ["feed_unavailable"], "execution_ready": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "hold" else 0


if __name__ == "__main__":
    sys.exit(main())
