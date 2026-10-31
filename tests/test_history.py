"""Synthetic fixtures only; never opens the user's Hermes history."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/hermes-history-codex/scripts/hermes_history.py'
spec = importlib.util.spec_from_file_location('history', SCRIPT)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'state.db'
        c = sqlite3.connect(self.db)
        c.executescript('''
        CREATE TABLE sessions(id TEXT PRIMARY KEY,title TEXT,source TEXT,started_at REAL,
            ended_at REAL,last_activity_at REAL,hidden INTEGER DEFAULT 0,
            parent_session_id TEXT,end_reason TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,
            timestamp REAL,active INTEGER DEFAULT 1);
        ''')
        sessions = [('one','水同位素建模','gui',1000,1001,1002,0,None,None),
                    ('two','Other topic','local',1000,1001,1003,0,None,None),
                    ('cron','水同位素建模','cron',1000,1001,1004,0,None,None),
                    ('hidden','Hidden','gui',1000,1001,1005,1,None,None)]
        c.executemany('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?)', sessions)
        messages = [(1,'one','user','Discuss rain and water isotopes',1000,1),
                    (2,'one','assistant','A'*500,1001,1),
                    (3,'one','tool','private tool payload',1001,1),
                    (4,'one','user','abandoned branch',1001,0),
                    (5,'two','user','literal 100% and under_score',1001,1),
                    (6,'two','assistant','old topic NEW_SECRET',1001,0)]
        c.executemany('INSERT INTO messages VALUES(?,?,?,?,?,?)', messages)
        c.commit(); c.close()
        self.before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.c = h.connect(self.db)

    def tearDown(self):
        self.c.close()
        self.assertEqual(self.before, hashlib.sha256(self.db.read_bytes()).hexdigest())
        self.tmp.cleanup()

    def test_title_and_content_search(self):
        self.assertEqual(h.search(self.c,'同位素')['sessions'][0]['id'],'one')
        self.assertEqual(h.search(self.c,'rain isotopes')['sessions'][0]['id'],'one')
        self.assertEqual(h.search(self.c,'NEW_SECRET')['sessions'],[])

    def test_sql_and_like_literals(self):
        self.assertEqual(h.search(self.c,"' OR 1=1 --")['sessions'],[])
        self.assertEqual([x['id'] for x in h.search(self.c,'100%')['sessions']],['two'])
        self.assertEqual(h.search(self.c,'missing_')['sessions'],[])

    def test_default_sources_and_hidden(self):
        self.assertEqual(len(h.search(self.c)['sessions']),2)
        self.assertEqual(len(h.search(self.c,all_sources=True,include_hidden=True)['sessions']),4)

    def test_pagination_and_roles(self):
        first = h.read(self.c,'one',limit=1)
        self.assertTrue(first['more_messages'])
        second = h.read(self.c,'one',after_id=first['next_after_id'])
        self.assertEqual([x['id'] for x in second['messages']],[2])
        self.assertFalse(second['more_messages'])
        self.assertEqual(len(h.read(self.c,'one',include_tools=True,include_inactive=True)['messages']),4)

    def test_truncation(self):
        record = h.read(self.c,'one',max_chars=100)['messages'][1]
        self.assertTrue(record['truncated'])
        self.assertEqual(record['characters'],500)
        self.assertEqual(len(record['content']),100)

    def test_readonly(self):
        with self.assertRaises(sqlite3.DatabaseError):
            self.c.execute("UPDATE sessions SET title='changed'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.c.execute('PRAGMA query_only=OFF')
        self.assertEqual(self.c.execute('SELECT count(*) FROM sessions').fetchone()[0],4)

    def test_no_database_creation(self):
        missing = Path(self.tmp.name) / 'missing.db'
        with self.assertRaises(ValueError): h.connect(missing)
        self.assertFalse(missing.exists())

    def test_redaction_and_structured_content(self):
        self.assertNotIn('verysecretvalue',h.readable('api_key=verysecretvalue'))
        self.assertNotIn('abcdefghijklmno',h.readable('Bearer abcdefghijklmno'))
        blocks = json.dumps([{'type':'text','text':'visible'},{'type':'thinking','text':'not-visible'}])
        self.assertEqual(h.readable(blocks),'visible')

    def test_date_boundaries(self):
        self.assertEqual(h.search(self.c,since='2030-01-01')['sessions'],[])
        self.assertTrue(h.search(self.c,until='2030-01-01')['sessions'])
        self.assertGreater(h.date_bound('2026-10-30',True),h.date_bound('2026-10-30'))

    def test_missing_session(self):
        with self.assertRaises(ValueError): h.read(self.c,'not-there')

    def test_live_wal_visibility(self):
        # Reader must include committed WAL rows, not use immutable snapshots.
        other = Path(self.tmp.name) / 'wal.db'
        writer = sqlite3.connect(other)
        writer.execute('PRAGMA journal_mode=WAL')
        writer.executescript('CREATE TABLE sessions(id TEXT); CREATE TABLE messages(id INTEGER);')
        writer.execute("INSERT INTO sessions VALUES('wal-only')"); writer.commit()
        reader = h.connect(other)
        self.assertEqual(reader.execute('SELECT id FROM sessions').fetchone()[0],'wal-only')
        reader.close(); writer.close()


if __name__ == '__main__': unittest.main()
