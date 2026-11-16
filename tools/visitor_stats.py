"""Anonymous daily browser counts and 120-second visible-page presence.

No IP, user agent, referrer, identity or trading data is stored. This is an
approximate client-reported browser counter, not authenticated people or an audit.
Only the private operations process reads aggregates; the public route accepts writes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
import time

ORIGIN = 'https://ingforme82-commits.github.io'
WINDOW = 120
KST = timezone(timedelta(hours=9))


def valid(payload):
    return isinstance(payload, dict) and set(payload) == {'browser', 'page'} and all(
        isinstance(payload[key], str) and re.fullmatch('[a-f0-9]{32}', payload[key])
        for key in ('browser', 'page'))


def connect(path: Path):
    if path.is_symlink():
        raise ValueError('Visitor database symlink rejected')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.exists():
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
    connection = sqlite3.connect(path, timeout=3)
    connection.execute('PRAGMA busy_timeout=3000')
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS days(day TEXT PRIMARY KEY, visits INTEGER NOT NULL DEFAULT 0, views INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS browsers(day TEXT, browser TEXT, PRIMARY KEY(day,browser));
        CREATE TABLE IF NOT EXISTS pages(day TEXT, page TEXT, browser TEXT, seen REAL, PRIMARY KEY(day,page));
        CREATE INDEX IF NOT EXISTS presence_seen ON pages(seen);
    ''')
    return connection


def heartbeat(path: Path, payload, now=None):
    if not valid(payload):
        raise ValueError('Invalid presence payload')
    now = time.time() if now is None else now
    date = datetime.fromtimestamp(now, KST)
    day = date.date().isoformat()
    with closing(connect(path)) as db, db:
        db.execute('INSERT OR IGNORE INTO days(day) VALUES (?)', (day,))
        new_browser = db.execute('INSERT OR IGNORE INTO browsers VALUES (?,?)', (day, payload['browser'])).rowcount
        # A page id has a fixed browser owner. A conflicting replay cannot change it.
        new_page = db.execute('INSERT OR IGNORE INTO pages VALUES (?,?,?,?)', (day, payload['page'], payload['browser'], now)).rowcount
        db.execute('UPDATE pages SET seen=? WHERE day=? AND page=? AND browser=?', (now, day, payload['page'], payload['browser']))
        db.execute('UPDATE days SET visits=visits+?, views=views+? WHERE day=?', (new_browser, new_page, day))
        db.execute('DELETE FROM browsers WHERE day < ?', ((date.date() - timedelta(days=30)).isoformat(),))
        db.execute('DELETE FROM pages WHERE day < ?', ((date.date() - timedelta(days=2)).isoformat(),))


def summary(path: Path, now=None):
    now = time.time() if now is None else now
    if not path.is_file() or path.is_symlink():
        return {'available': False, 'online': None, 'today': None, 'total_visits': None, 'reason': 'NO_COLLECTION_YET'}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            day = datetime.fromtimestamp(now, KST).date().isoformat()
            today = db.execute('SELECT visits,views FROM days WHERE day=?', (day,)).fetchone()
            totals = db.execute('SELECT COALESCE(SUM(visits),0), COALESCE(SUM(views),0), MIN(day) FROM days').fetchone()
            online = db.execute('SELECT COUNT(DISTINCT browser) FROM pages WHERE day=? AND seen>=? AND seen<=?', (day, now-WINDOW, now)).fetchone()[0]
            last = db.execute('SELECT MAX(seen) FROM pages').fetchone()[0]
            days = db.execute('SELECT day,visits,views FROM days ORDER BY day DESC LIMIT 7').fetchall()
        return {'available': True, 'online': online, 'window_seconds': WINDOW,
                'today': {'day': day, 'browsers': today[0] if today else 0, 'pageviews': today[1] if today else 0},
                'total_visits': totals[0], 'total_pageviews': totals[1], 'since': totals[2],
                'last_received_at': last, 'days': [{'day': row[0], 'browsers': row[1], 'pageviews': row[2]} for row in days],
                'approximate': True, 'unique_people_verified': False}
    except (OSError, sqlite3.Error):
        return {'available': False, 'online': None, 'today': None, 'total_visits': None, 'reason': 'READ_FAILED'}
