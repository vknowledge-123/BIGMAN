"""Small transactional cache updates, independent of credentials/settings JSON."""
from contextlib import contextmanager
from pathlib import Path
from datetime import date
import json
import sqlite3
import threading
import os
from weakref import WeakValueDictionary


_locks = WeakValueDictionary()
_locks_guard = threading.Lock()


class HistoryCache:
    def __init__(self, path: Path):
        self.path = path
        self._ready = False
        # Multiple ConfigStore instances can open the same database concurrently.
        # Share their lock, including WAL/schema initialization (which can fail
        # immediately with SQLITE_BUSY even with a connection busy timeout).
        key = os.path.normcase(str(path.resolve()))
        with _locks_guard:
            self._lock = _locks.setdefault(key, threading.RLock())

    @contextmanager
    def connection(self):
        with self._lock:
            db = sqlite3.connect(self.path, timeout=15)
            try:
                if not self._ready:
                    db.execute('PRAGMA journal_mode=WAL')
                    db.executescript('''
                        CREATE TABLE IF NOT EXISTS prepared (
                            symbol TEXT NOT NULL, session TEXT NOT NULL, payload TEXT NOT NULL,
                            PRIMARY KEY(symbol, session));
                        CREATE TABLE IF NOT EXISTS closes (symbol TEXT PRIMARY KEY, price REAL NOT NULL);
                        CREATE TABLE IF NOT EXISTS history (
                            kind TEXT NOT NULL, instrument TEXT NOT NULL, payload TEXT NOT NULL,
                            PRIMARY KEY(kind, instrument));
                    ''')
                    self._ready = True
                with db:
                    yield db
            finally:
                db.close()

    def update(self, entries=None, closes=None, *, legacy=False):
        rows = []
        for symbol, value in (entries or {}).items():
            daily = value.get('daily_filter') or {}
            session = max(str(daily.get('session_date') or ''), str(value.get('volume_session') or ''))
            rows.append((symbol.upper(), session, json.dumps(value, separators=(',', ':'), allow_nan=False)))
        with self.connection() as db:
            suffix = ('DO NOTHING' if legacy else "DO UPDATE SET payload=excluded.payload WHERE "
                      "COALESCE(json_extract(excluded.payload, '$.cached_at'), '') >= "
                      "COALESCE(json_extract(prepared.payload, '$.cached_at'), '')")
            db.executemany('INSERT INTO prepared VALUES (?,?,?) ON CONFLICT(symbol,session) ' + suffix, rows)
            suffix = 'DO NOTHING' if legacy else 'DO UPDATE SET price=excluded.price'
            db.executemany('INSERT INTO closes VALUES (?,?) ON CONFLICT(symbol) ' + suffix,
                           [(s.upper(), p) for s,p in (closes or {}).items() if p is not None])
            # Keep recent session snapshots; raw history below supports rolling reuse.
            for symbol, session, _ in rows:
                if session:
                    db.execute("DELETE FROM prepared WHERE symbol=? AND session < date(?, '-14 days')", (symbol, session))

    def load(self):
        with self.connection() as db:
            entries = {s:json.loads(p) for s,p in db.execute('''SELECT p.symbol,p.payload FROM prepared p
                JOIN (SELECT symbol,MAX(session) AS session FROM prepared GROUP BY symbol) latest
                ON latest.symbol=p.symbol AND latest.session=p.session''')}
            closes = dict(db.execute('SELECT symbol,price FROM closes'))
        return entries, closes

    def get(self, kind, instrument):
        with self.connection() as db:
            row = db.execute('SELECT payload FROM history WHERE kind=? AND instrument=?', (kind,instrument)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, kind, instrument, value):
        payload = json.dumps(value, separators=(',', ':'), allow_nan=False)
        with self.connection() as db:
            # A historical replay must not overwrite newer live coverage.
            row = db.execute('SELECT payload FROM history WHERE kind=? AND instrument=?', (kind,instrument)).fetchone()
            if row:
                try:
                    existing_day = date.fromisoformat(json.loads(row[0]).get('through', ''))
                    incoming_day = date.fromisoformat(value.get('through', ''))
                except (ValueError, TypeError):
                    pass  # Malformed coverage must not prevent cache repair.
                else:
                    if existing_day > incoming_day:
                        return
            db.execute('INSERT INTO history VALUES (?,?,?) ON CONFLICT(kind,instrument) DO UPDATE SET payload=excluded.payload',
                       (kind,instrument,payload))
