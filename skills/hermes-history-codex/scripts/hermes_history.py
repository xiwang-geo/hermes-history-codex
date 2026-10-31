#!/usr/bin/env python3
"""Bounded, read-only Hermes session discovery and transcript retrieval. Python 3.10+."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time


def databases():
    """Discover known homes, including named profiles, without reading config/secrets."""
    homes = []
    if os.environ.get('HERMES_HOME'):
        homes.append(Path(os.environ['HERMES_HOME']).expanduser())
    homes.append(Path.home() / '.hermes')
    if os.environ.get('LOCALAPPDATA'):
        homes.append(Path(os.environ['LOCALAPPDATA']) / 'hermes')
    found = []
    for home in homes:
        candidates = [home / 'state.db']
        profiles = home / 'profiles'
        if profiles.is_dir():
            candidates.extend(sorted(profiles.glob('*/state.db')))
        for path in candidates:
            if path.is_file() and str(path.resolve()) not in found:
                found.append(str(path.resolve()))
    return found


def connect(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError('Database does not exist; use discover or --db PATH.')
    # Do not use immutable=1: it ignores a live WAL and may omit recent messages.
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'sessions', 'messages'} <= tables:
        conn.close()
        raise ValueError('Not a supported Hermes state.db (sessions/messages missing).')
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
    deadline = time.monotonic() + 5
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    return conn


def columns(conn, table):
    # table is an internal constant, not user input. Description avoids PRAGMA permissions.
    return {d[0] for d in conn.execute('SELECT * FROM ' + table + ' LIMIT 0').description}


def local_time(value):
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).astimezone().isoformat() if value else None


def date_bound(value, end=False):
    day = dt.date.fromisoformat(value)
    if end:
        day += dt.timedelta(days=1)
    # astimezone() treats a naive datetime as the host's local civil time, including DST.
    return dt.datetime.combine(day, dt.time()).astimezone().timestamp()


def redact(text):
    text = re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{10,}', 'Bearer [REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{16,}', '[REDACTED]', text)
    text = re.sub(r'(?i)(\b(?:api[_-]?key|access[_-]?token|password|secret)\b\s*[=:]\s*[\"\']?)[^\s\"\',;]{6,}', r'\1[REDACTED]', text)
    return text


def readable(value):
    if value is None:
        return ''
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return redact(str(value))
    if isinstance(data, str):
        return redact(data)
    if isinstance(data, list):
        return redact('\n'.join(b.get('text', '') for b in data if isinstance(b, dict) and b.get('type') in ('text', 'input_text', 'output_text')))
    # Unknown structured content is not automatically unpacked (may contain reasoning/tools).
    return '[Structured content omitted: unsupported shape]'


def literal_like(value):
    return '%' + value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def message_clause(conn, include_inactive=False, include_tools=False, alias='m'):
    cols = columns(conn, 'messages')
    conditions = []
    if not include_tools:
        conditions.append(f"{alias}.role IN ('user','assistant')")
    if 'active' in cols and not include_inactive:
        conditions.append(f'COALESCE({alias}.active,1)=1')
    return conditions


def search(conn, query='', limit=8, since=None, until=None, all_sources=False, include_hidden=False):
    if len(query) > 200:
        raise ValueError('Query is too long; use at most 200 characters.')
    terms = query.split()
    if len(terms) > 8:
        raise ValueError('Use at most eight search terms.')
    cols = columns(conn, 'sessions')
    for required in ['id', 'title', 'source', 'started_at']:
        if required not in cols:
            raise ValueError('Unsupported session schema: missing ' + required)
    activity = 'COALESCE(' + ','.join('s.' + c for c in ['last_activity_at', 'ended_at', 'started_at'] if c in cols) + ')'
    where, params = [], []
    if not all_sources:
        where.append("s.source NOT IN ('cron','subagent','tool')")
    if 'hidden' in cols and not include_hidden:
        where.append('COALESCE(s.hidden,0)=0')
    if since:
        where.append(activity + ' >= ?'); params.append(date_bound(since))
    if until:
        where.append(activity + ' < ?'); params.append(date_bound(until, end=True))
    msgfilter = message_clause(conn)
    for term in terms:
        where.append("(s.title LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM messages m WHERE m.session_id=s.id AND " + ' AND '.join(msgfilter + ["m.content LIKE ? ESCAPE '\\'"]) + '))')
        params.extend([literal_like(term), literal_like(term)])
    title_score = '0' if not terms else 'CASE WHEN s.title LIKE ? ESCAPE \'\\\' THEN 1 ELSE 0 END'
    score_params = [] if not terms else [literal_like(query)]
    sql = f'SELECT s.id,s.title,s.source,s.started_at,{activity} AS activity,{title_score} AS title_match FROM sessions s'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY title_match DESC,activity DESC,s.id LIMIT ?'
    rows = conn.execute(sql, score_params + params + [limit + 1]).fetchall()
    result = []
    for row in rows[:limit]:
        item = dict(row)
        item['started_at'] = local_time(item['started_at'])
        item['last_active'] = local_time(item.pop('activity'))
        item['title'] = redact(item['title'] or '(untitled)')
        result.append(item)
    return {'sessions': result, 'more_results': len(rows) > limit, 'date_filter': 'session last activity; host local calendar dates', 'query': query}


def read(conn, session_id, after_id=0, limit=40, max_chars=4000, include_tools=False, include_inactive=False):
    meta = conn.execute('SELECT id,title,source,parent_session_id,end_reason FROM sessions WHERE id=?', [session_id]).fetchone()
    if meta is None:
        raise ValueError('Session not found in this database.')
    filters = message_clause(conn, include_inactive, include_tools)
    filters += ['m.session_id=?', 'm.id>?']
    rows = conn.execute('SELECT m.id,m.role,m.content,m.timestamp FROM messages m WHERE ' + ' AND '.join(filters) + ' ORDER BY m.id LIMIT ?', [session_id, after_id, limit + 1]).fetchall()
    items, budget, last = [], 50000, after_id
    for row in rows[:limit]:
        if budget <= 0:
            break
        text = readable(row['content'])
        cap = min(max_chars, budget)
        excerpt = text[:cap]
        items.append({'id': row['id'], 'role': row['role'], 'timestamp': local_time(row['timestamp']), 'content': excerpt, 'characters': len(text), 'truncated': len(text) > cap})
        budget -= len(excerpt); last = row['id']
    more = len(rows) > len(items)
    metadata = dict(meta)
    metadata['title'] = redact(metadata['title'] or '(untitled)')
    return {'session': metadata, 'messages': items, 'more_messages': more, 'next_after_id': last if more else None, 'scope': 'Selected session segment only; parent/branch/compression records are not silently merged.', 'include_inactive': include_inactive, 'redaction': 'Best-effort credential patterns only; not a complete privacy filter.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', help='Explicit state.db path; otherwise discover a single database.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('discover')
    find = sub.add_parser('search')
    find.add_argument('query', nargs='?', default='')
    find.add_argument('--limit', type=int, default=8)
    find.add_argument('--since', help='YYYY-MM-DD, inclusive, host local date')
    find.add_argument('--until', help='YYYY-MM-DD, inclusive, host local date')
    find.add_argument('--all-sources', action='store_true')
    find.add_argument('--include-hidden', action='store_true')
    get = sub.add_parser('read')
    get.add_argument('session_id')
    get.add_argument('--after-id', type=int, default=0)
    get.add_argument('--limit', type=int, default=40)
    get.add_argument('--max-chars', type=int, default=4000)
    get.add_argument('--include-tools', action='store_true')
    get.add_argument('--include-inactive', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.command == 'discover':
            print(json.dumps({'databases': databases()}, ensure_ascii=False, indent=2)); return 0
        candidates = [args.db] if args.db else databases()
        if len(candidates) != 1:
            raise ValueError('Expected one database; run discover and select with --db PATH.')
        if not 1 <= args.limit <= (50 if args.command == 'search' else 200):
            raise ValueError('Limit out of range (search 1..50; read 1..200).')
        if args.command == 'read' and (args.after_id < 0 or not 100 <= args.max_chars <= 20000):
            raise ValueError('Invalid cursor or max-chars (100..20000).')
        conn = connect(candidates[0])
        try:
            if args.command == 'search':
                if args.since and args.until and args.since > args.until:
                    raise ValueError('since must not be later than until.')
                result = search(conn, args.query, args.limit, args.since, args.until, args.all_sources, args.include_hidden)
            else:
                result = read(conn, args.session_id, args.after_id, args.limit, args.max_chars, args.include_tools, args.include_inactive)
        finally:
            conn.close()
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (ValueError, sqlite3.Error, OSError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
