"""Durable intent/state journal and one-process execution ownership."""
import json
import os
from pathlib import Path
import sqlite3
import threading
from contextlib import contextmanager


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.owner_file = None
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, session_id TEXT, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def acquire(self):
        with self.lock:
            if self.owner_file:
                return
            handle = open(str(self.path) + '.lock', 'a+b')
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    if handle.read(1) == b'':
                        handle.write(b'0')
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except Exception:
                handle.close()
                raise RuntimeError('Another process owns this algo journal; do not run multiple trading servers')
            self.owner_file = handle

    def release(self):
        with self.lock:
            if self.owner_file:
                self.owner_file.close()
                self.owner_file = None

    def load(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM sessions')]

    def save(self, record, event=None):
        with self.lock, self.connect() as db:
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?, ?)',
                       (record['id'], json.dumps(record, allow_nan=False)))
            if event is not None:
                db.execute('INSERT INTO events(session_id, payload) VALUES (?, ?)',
                           (record['id'], json.dumps(event, allow_nan=False)))

    def settings(self, value=None):
        with self.lock, self.connect() as db:
            if value is not None:
                db.execute('INSERT OR REPLACE INTO settings VALUES (1, ?)', (json.dumps(value, allow_nan=False),))
                return value
            row = db.execute('SELECT payload FROM settings WHERE id=1').fetchone()
            return json.loads(row[0]) if row else {}
