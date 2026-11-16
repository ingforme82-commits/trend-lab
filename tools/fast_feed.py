"""Expose only the latest validated, successfully published public snapshot.

The isolated Oracle runner writes candidate-news.json before publication and
status.json afterwards. Never expose a new candidate with an older success status.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path.home() / '.local/share/trl/site-runtime'
PUBLIC = {'updated', 'items', 'moves', 'series', 'sectors', 'leaders', 'health', 'world', 'spot',
          'dow', 'us10y', 'ust', 'official', 'kr', 'reg', 'ext', 'momentum', 'lev', 'watch',
          'flows', 's7', 'trending', 'tgsum', 'brief', 'rt_url', 'srcscore', 'auto_issues', 'runtime', 'connectivity24'}


def read_public(root=ROOT):
    candidate, status = root / 'candidate-news.json', root / 'status.json'
    if candidate.is_symlink() or status.is_symlink():
        raise ValueError('Symlink rejected')
    before = status.stat()
    meta = json.loads(status.read_text(encoding='utf-8'))
    stamp = candidate.stat()
    if stamp.st_mtime_ns > before.st_mtime_ns or stamp.st_size > 4 * 1024 * 1024:
        raise ValueError('Unpublished candidate')
    if meta.get('mode') != 'publish' or meta.get('published') is not True or meta.get('validation_issues') != []:
        raise ValueError('Publication not verified')
    data = json.loads(candidate.read_text(encoding='utf-8'))
    runtime = data.get('runtime') or {}
    if runtime.get('executor') != 'oracle' or not re.fullmatch('[a-f0-9]{40}', str(meta.get('source_revision', ''))) or runtime.get('source_revision') != meta.get('source_revision'):
        raise ValueError('Revision mismatch')
    after = status.stat()
    if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size) or candidate.stat().st_mtime_ns != stamp.st_mtime_ns:
        raise ValueError('Snapshot changed while reading')
    if not isinstance(data.get('items'), list) or not isinstance(data.get('updated'), (int, float)):
        raise ValueError('Invalid public snapshot')
    payload = json.dumps({key: value for key, value in data.items() if key in PUBLIC}, ensure_ascii=False, allow_nan=False).encode()
    return payload, '"' + hashlib.sha256(payload).hexdigest()[:24] + '"'
