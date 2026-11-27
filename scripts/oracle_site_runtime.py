"""Oracle site runner: independent site owner, isolated caches, no trading/alerts."""
from __future__ import annotations

import argparse
import base64
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import types
from zoneinfo import ZoneInfo

HOME = Path.home()
MS = HOME / 'projects/market-site'
SITE = HOME / 'projects/trend-lab-site'
STATE = HOME / '.local/share/trl/site-runtime'
REPO = 'ingforme82-commits/trend-lab'
KST = ZoneInfo('Asia/Seoul')


def command(args, *, timeout=120):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Child command failed')
    return result.stdout


def owner():
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location('oracle_site_role', MS / 'failover/site_role.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.site_owner()


def require_owner():
    if owner() != 'oracle':
        raise RuntimeError('Oracle is not site execution owner')


def snapshot():
    revision = command(['git', '-C', str(SITE), 'rev-parse', 'HEAD']).strip()
    if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise RuntimeError('Invalid source revision')
    target = STATE / ('source-' + revision)
    if target.is_symlink():
        raise RuntimeError('Symlink snapshot rejected')
    if not target.exists():
        raw = subprocess.run(['git', '-C', str(SITE), 'archive', 'HEAD', 'tools', 'data'],
                             check=True, capture_output=True).stdout
        target.mkdir(mode=0o700)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            entries = [m for m in archive.getmembers() if Path(m.name).name != '.env'
                       and not m.name.endswith(('.session', '.key', '.pem'))]
            archive.extractall(target, members=entries, filter='data')
        (target / '.ready').write_text(revision, encoding='utf-8')
    if not (target / '.ready').is_file():
        raise RuntimeError('Incomplete snapshot; preserve for review')
    return target, revision


@contextlib.contextmanager
def build_guard():
    from test_trl_collection import install_network_guards
    install_network_guards()
    original = subprocess.run
    def blocked(*args, **kwargs):
        raise RuntimeError('Subprocess disabled inside site generation')
    subprocess.run = blocked
    try:
        yield
    finally:
        subprocess.run = original


def load_modules(root):
    sys.path.insert(0, str(root / 'tools'))
    alerts = types.ModuleType('tg_alert')
    alerts.alert = lambda *args, **kwargs: False
    sys.modules['tg_alert'] = alerts
    kakao = types.ModuleType('kakao_notify')
    kakao.notify = lambda *args, **kwargs: False
    sys.modules['kakao_notify'] = kakao
    import live_news
    live_news._claude_translate = lambda titles: {}
    live_news._alert = alerts.alert
    live_news.DB = HOME / '.local/share/trl/telegram/tgr.sqlite3'
    live_news.TGR = HOME / '.local/share/trl/telegram'
    live_news.refresh = lambda: (_ for _ in ()).throw(RuntimeError('Use isolated collector'))
    # Run automatic card composition locally; never nested publication.
    for name in ('macro_issue', 'move_issue'):
        module = __import__(name)
        update = module.update
        module.update = lambda data, original=update: original(data, push=False)
    return live_news


def base_issues(data, now_ms):
    # Reuse existing publication contract, including Telegram/RSS checks.
    import brief_slot
    problems = brief_slot.validate('1200', data, now_ms)
    if not data.get('items'):
        problems.append('No news items')
    if not data.get('sectors'):
        problems.append('No sector cards')
    return problems


def generate_news(root, revision):
    # Collector prints metadata only; full child output is not forwarded.
    command([sys.executable, str(HOME / 'telegram_collect_once.py')], timeout=120)
    collected = json.loads((HOME / '.local/share/trl/telegram/collection-report.json').read_text(encoding='utf-8'))
    completed = datetime.fromisoformat(collected['finished_at'])
    age = (datetime.now(timezone.utc)-completed).total_seconds()
    if (not 0 <= age <= 180 or collected.get('channels_failed')
            or collected.get('channels_ok') != collected.get('channels_configured')):
        raise RuntimeError('Telegram collection incomplete or old')
    warning_sections = []
    with build_guard(), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        live = load_modules(root)
        live.log = lambda message: warning_sections.append(str(message).split(':', 1)[0][:100])
        live.REFRESH.update(ok=True, at=int(completed.timestamp()*1000))
        data = live.build()
        issues = base_issues(data, int(time.time()*1000))
    data['runtime'] = {'executor': 'oracle', 'generated_at': int(time.time()*1000),
                       'source_revision': revision, 'notifications_enabled': False}
    # Independent 24h probe does not replace cash, exchange futures or yield values.
    try:
        from live24 import collect
        data['connectivity24'] = collect()
    except Exception as error:
        data['connectivity24'] = {'error_type': type(error).__name__}
    return data, live, warning_sections, issues


def gh_json(args, payload=None):
    if payload is None:
        return json.loads(command(['gh', 'api', *args]))
    with tempfile.TemporaryDirectory(dir=STATE, prefix='publish-') as directory:
        request = Path(directory) / 'request.json'
        request.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        return json.loads(command(['gh', 'api', *args, '--input', str(request)]))


BRIEFS_MAX_BYTES = 900_000   # GitHub contents API 는 1MB 넘는 파일의 content 를 빈 값으로 준다(11/26 브리핑 전부 실패 원인)


def decode_content(current, path, ref):
    """contents API 응답 → JSON. 1MB 넘어 content 가 비면 raw 로 다시 받는다."""
    if current.get('content'):
        return json.loads(base64.b64decode(current['content']))
    raw = command(['gh', 'api', '-H', 'Accept: application/vnd.github.raw', f'repos/{REPO}/contents/{path}?ref={ref}'])
    return json.loads(raw)


def trim_history(history, limit=BRIEFS_MAX_BYTES):
    """최신부터 담고, 인코딩 크기가 limit 를 넘으면 오래된 기록부터 뺀다(최소 1건)."""
    history = list(history)
    while len(history) > 1 and len(json.dumps(history, ensure_ascii=False, indent=1).encode()) > limit:
        history.pop()
    return history


def fetch_news():
    current = gh_json([f'repos/{REPO}/contents/news.json?ref=live'])
    return decode_content(current, 'news.json', 'live')


def slot_due(slot, now):
    if now.weekday() >= (6 if slot == '0610' else 5):
        return False
    hour, minute = (15, 35) if slot == '1530' else (int(slot[:2]), int(slot[2:]))
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return 0 <= (now-scheduled).total_seconds() <= 20*60


def publish_brief(slot, root):
    now = datetime.now(KST)
    if slot == '1200':
        due = 0 <= (now-now.replace(hour=12, minute=0, second=0, microsecond=0)).total_seconds() <= 20*60
    else:
        due = slot_due(slot, now)
    if not due:
        return {'status': 'SKIPPED_OUTSIDE_SLOT_WINDOW', 'slot': slot}
    sys.path.insert(0, str(root / 'tools'))
    import brief_slot
    data = fetch_news()
    with build_guard(), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        issues = brief_slot.validate(slot, data, int(time.time()*1000))
        if not issues and slot in brief_slot.EVE:
            from evening import make, check
            data['eve'] = make(data)
            issues = check(data['eve'])
    if issues:
        return {'status': 'BLOCKED_BY_DATA_VALIDATION', 'slot': slot, 'issues': issues}
    day = now.strftime('%Y-%m-%d')
    record = ({'day': day, 'slot': '12:00', **data['brief']} if slot == '1200'
              else brief_slot.compose(slot, data, day))
    label = record['slot']
    endpoint = f'repos/{REPO}/contents/data/briefs.json'
    for attempt in range(3):
        current = gh_json([endpoint + '?ref=main'])
        history = decode_content(current, 'data/briefs.json', 'main')
        if any(item.get('day') == day and item.get('slot') == label for item in history):
            return {'status': 'ALREADY_PUBLISHED', 'slot': slot}
        history = trim_history([record, *history][:120])
        require_owner()
        try:
            gh_json(['--method', 'PUT', endpoint], {
                'branch': 'main', 'sha': current['sha'], 'message': f'Oracle 정시 브리핑 {day} {label}',
                'content': base64.b64encode(json.dumps(history, ensure_ascii=False, indent=1).encode()).decode()})
            return {'status': 'PUBLISHED', 'slot': slot}
        except RuntimeError:
            if attempt == 2:
                raise
            time.sleep(2)
    raise RuntimeError('Brief publication failed')


def main():
    import fcntl
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('news', 'brief'))
    parser.add_argument('--slot', choices=('0610','0720','1200','1400','1530','2005','2215'))
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'linux':
        raise SystemExit('Run on Oracle Ubuntu only')
    os.umask(0o077)
    for path in (STATE, *STATE.parents):
        if path.is_symlink():
            raise RuntimeError('Symlink runtime directory rejected')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.publish:
        require_owner()
    if args.action == 'brief' and (not args.slot or not args.publish):
        raise RuntimeError('Brief publishing requires --slot and --publish; use trial validation for previews')
    with (STATE / 'run.lock').open('a') as lock:
        deadline = time.monotonic() + (300 if args.action == 'brief' else 0)   # 11/27 12:00·14:00 은 90초 대기로 BUSY 실패 → 5분(회차 창 20분 안)
        while True:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    print('BUSY: another site job is running.')
                    return 2 if args.action == 'brief' else 0
                time.sleep(2)
        root, revision = snapshot()
        if args.action == 'brief':
            result = publish_brief(args.slot, root)
            print(json.dumps(result, ensure_ascii=False))
            return 2 if result['status'] == 'BLOCKED_BY_DATA_VALIDATION' else 0
        data, live, warnings, issues = generate_news(root, revision)
        (STATE / 'candidate-news.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        result = {'at': datetime.now(KST).isoformat(), 'source_revision': revision,
                  'mode': 'publish' if args.publish else 'shadow', 'items': len(data.get('items', [])),
                  'telegram': (data.get('health') or {}).get('tg'),
                  'sectors': len(data.get('sectors') or []), 'warnings': sorted(set(warnings)),
                  'validation_issues': issues, 'published': False}
        if args.publish and not issues:
            require_owner()
            live.CMP_KEYS = (*live.CMP_KEYS, 'runtime', 'connectivity24')
            result['published'] = bool(live.upload(data))
        (STATE / 'status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if issues else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('Site job failed:', type(error).__name__, '(no exception details emitted)')
        raise SystemExit(2) from None
