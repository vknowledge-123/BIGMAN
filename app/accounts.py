"""Local account database. Opaque sessions, Argon2 passwords and encrypted TOTP secrets."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.fernet import Fernet
import pyotp
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class DisplaySettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    volume_enabled: bool = False
    volume_min: int = Field(default=100000, ge=0, le=9_007_199_254_740_991)
    price_enabled: bool = False
    price_max: float = Field(default=250, ge=0, allow_inf_nan=False)
    circuit_enabled: bool = True
    setup: Literal['all', 'possible', 'redwala', 'retest'] = 'all'


class AccountError(ValueError):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def email_address(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}", value):
        raise AccountError('Enter a valid email address.')
    return value


class Accounts:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.ready = False
        self.password_slots = threading.BoundedSemaphore(2)
        self.hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
        self.dummy = self.hasher.hash(secrets.token_urlsafe(32))

    @contextmanager
    def db(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            if not self.ready:
                db.execute('PRAGMA journal_mode=WAL')
                db.executescript('''
                  CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    password TEXT NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL,
                    secret TEXT, mfa INTEGER NOT NULL DEFAULT 0, last_counter INTEGER NOT NULL DEFAULT -1,
                    created REAL NOT NULL);
                  CREATE TABLE IF NOT EXISTS challenges (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    purpose TEXT NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
                  CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    csrf TEXT NOT NULL, expires REAL NOT NULL, seen REAL NOT NULL);
                  CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL);
                  CREATE TABLE IF NOT EXISTS preferences (id INTEGER PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL);
                  CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, actor TEXT, subject TEXT, action TEXT NOT NULL, at REAL NOT NULL);
                ''')
                self.ready = True
            try:
                with db:
                    yield db
            finally:
                db.close()

    def cipher(self):
        with self.lock:
            key = self.path.with_suffix('.key')
            if not key.exists():
                # Never silently replace a lost key for already encrypted accounts.
                with self.db() as db:
                    if db.execute('SELECT 1 FROM users WHERE secret IS NOT NULL LIMIT 1').fetchone():
                        raise AccountError('Account encryption key is missing. Restore the server backup.', 503)
                key.parent.mkdir(parents=True, exist_ok=True)
                try:
                    fd = os.open(key, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError:
                    pass
                else:
                    with os.fdopen(fd, 'wb') as f:
                        f.write(Fernet.generate_key())
            return Fernet(key.read_bytes().strip())

    @contextmanager
    def password_work(self):
        # Argon2 uses 64 MiB per job. Do not let public requests exhaust RAM.
        if not self.password_slots.acquire(blocking=False):
            raise AccountError('Sign-in is busy. Please retry shortly.', 429)
        try:
            yield
        finally:
            self.password_slots.release()

    def hash_password(self, password):
        with self.password_work():
            return self.hasher.hash(password)

    @staticmethod
    def _throttle_db(db, key, maximum, seconds, now):
        row = db.execute('SELECT * FROM limits WHERE key=?', (digest(key),)).fetchone()
        if row and row['started'] > now-seconds and row['count'] >= maximum:
            raise AccountError('Too many attempts. Please try again later.', 429)
        started, count = (row['started'], row['count']+1) if row and row['started'] > now-seconds else (now, 1)
        db.execute('INSERT OR REPLACE INTO limits VALUES (?,?,?)', (digest(key), started, count))

    def throttle(self, key, maximum, seconds=900):
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM limits WHERE started < ?', (now-86400,))
            self._throttle_db(db, key, maximum, seconds, now)

    def create(self, email, password, name, *, admin=False):
        email = email_address(email)
        if not 12 <= len(password) <= 128:
            raise AccountError('Use a password between 12 and 128 characters.')
        name = name.strip()
        if not 1 <= len(name) <= 80:
            raise AccountError('Enter a display name (1–80 characters).')
        hashed = self.hash_password(password)
        uid = secrets.token_hex(16)
        with self.db() as db:
            try:
                db.execute('INSERT INTO users(id,email,name,password,role,status,created) VALUES (?,?,?,?,?,?,?)',
                    (uid,email,name,hashed,'admin' if admin else 'member','active' if admin else 'pending',time.time()))
            except sqlite3.IntegrityError:
                raise AccountError('Unable to create this account. Sign in if you are already registered.') from None
            self.audit(db, 'local-console' if admin else uid, uid, 'admin_created' if admin else 'signup')
        return uid

    @staticmethod
    def audit(db, actor, subject, action):
        db.execute('INSERT INTO audit(actor,subject,action,at) VALUES (?,?,?,?)', (actor,subject,action,time.time()))

    def password_login(self, email, password):
        email = email_address(email)
        with self.db() as db:
            row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        try:
            with self.password_work():
                self.hasher.verify(row['password'] if row else self.dummy, password)
        except (VerificationError, InvalidHashError):
            raise AccountError('Email or password is incorrect.', 401) from None
        if row is None or row['status'] == 'suspended':
            raise AccountError('Email or password is incorrect.', 401)
        return self.challenge(row['id'])

    def challenge(self, uid):
        cipher = self.cipher()  # Initialise the key before opening a write transaction.
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            if not row or row['status'] == 'suspended':
                raise AccountError('Access unavailable.', 403)
            enroll = not row['mfa']
            secret = cipher.decrypt(row['secret'].encode()).decode() if row['secret'] else pyotp.random_base32()
            if not row['secret']:
                db.execute('UPDATE users SET secret=? WHERE id=?', (cipher.encrypt(secret.encode()).decode(),uid))
            db.execute('DELETE FROM challenges WHERE user_id=? OR expires < ?', (uid,time.time()))
            db.execute('INSERT INTO challenges VALUES (?,?,?,?,0)', (digest(token),uid,'enroll' if enroll else 'login',time.time()+300))
            result = {'challenge':token,'enrollment':enroll}
            if enroll:
                result.update(secret=secret, uri=pyotp.TOTP(secret).provisioning_uri(name=row['email'], issuer_name='Turnover Scanner'))
            return result

    def verify(self, token, code):
        cipher = self.cipher()
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            challenge = db.execute('SELECT * FROM challenges WHERE token=?', (digest(token),)).fetchone()
            if not challenge or challenge['expires'] < now or challenge['attempts'] >= 5:
                raise AccountError('Verification expired. Sign in again.', 401)
            db.execute('UPDATE challenges SET attempts=attempts+1 WHERE token=?', (digest(token),))
            row = db.execute('SELECT * FROM users WHERE id=?', (challenge['user_id'],)).fetchone()
            if not row or row['status'] == 'suspended':
                db.commit()
                raise AccountError('Access unavailable.', 403)
            # Account budget survives obtaining a new password challenge or changing IP.
            self._throttle_db(db, 'otp:account:'+row['id'], 10, 900, now)
            secret = cipher.decrypt(row['secret'].encode()).decode()
            otp = pyotp.TOTP(secret)
            counter = int(now//30)
            matches = [n for n in (counter-1,counter,counter+1) if n > row['last_counter']
                       and secrets.compare_digest(otp.at(n*30),code)] if re.fullmatch(r'[0-9]{6}',code) else []
            if not matches:
                db.commit()  # Failed attempts must survive rollback of the HTTP error.
                raise AccountError('Invalid or already-used code. Use the next code from your authenticator.', 401)
            db.execute('UPDATE users SET mfa=1,last_counter=? WHERE id=?', (max(matches),row['id']))
            db.execute('DELETE FROM challenges WHERE user_id=?', (row['id'],))
            db.execute('DELETE FROM sessions WHERE expires < ? OR seen < ?', (now,now-1800))
            db.execute('DELETE FROM sessions WHERE user_id=? AND token NOT IN (SELECT token FROM sessions WHERE user_id=? ORDER BY seen DESC LIMIT 4)', (row['id'],row['id']))
            session, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES (?,?,?,?,?)', (digest(session),row['id'],csrf,now+43200,now))
            self.audit(db,row['id'],row['id'],'mfa_enrolled' if challenge['purpose']=='enroll' else 'login')
            return session, {'id':row['id'],'email':row['email'],'name':row['name'],'role':row['role'],'status':row['status'],'csrf':csrf}

    def identity(self, token):
        if not token:
            return None
        now = time.time()
        with self.db() as db:
            row = db.execute('''SELECT u.id,u.email,u.name,u.role,u.status,s.csrf FROM sessions s
                JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND s.seen>?
                AND u.mfa=1 AND u.status != 'suspended' ''', (digest(token),now,now-1800)).fetchone()
            if not row:
                return None
            db.execute('UPDATE sessions SET seen=? WHERE token=?', (now,digest(token)))
            return dict(row)

    def logout(self, token):
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (digest(token or ''),))

    def users(self):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT id,email,name,role,status,mfa,created FROM users ORDER BY created DESC LIMIT 1000')]

    def status(self, uid, status, actor):
        if status not in ('active','suspended'):
            raise AccountError('Unsupported status.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            if not row or row['role'] != 'member':
                raise AccountError('Select a regular member account.', 400)
            if status == 'active' and not row['mfa']:
                raise AccountError('The member must finish authenticator setup before approval.')
            db.execute('UPDATE users SET status=? WHERE id=?', (status,uid))
            if status == 'suspended':
                db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
                db.execute('DELETE FROM challenges WHERE user_id=?', (uid,))
            self.audit(db,actor,uid,'access_'+status)

    def reset(self, email, *, password=None, mfa=False):
        email = email_address(email)
        if password is not None and not 12 <= len(password) <= 128:
            raise AccountError('Password must contain 12–128 characters.')
        hashed = self.hash_password(password) if password else None
        with self.db() as db:
            row = db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
            if not row:
                raise AccountError('Account not found.')
            if hashed:
                db.execute('UPDATE users SET password=? WHERE id=?', (hashed,row['id']))
            if mfa:
                db.execute('UPDATE users SET secret=NULL,mfa=0,last_counter=-1 WHERE id=?', (row['id'],))
            db.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
            db.execute('DELETE FROM challenges WHERE user_id=?', (row['id'],))
            self.audit(db,'local-console',row['id'],'credentials_reset')

    def display(self, settings=None):
        with self.db() as db:
            if settings is not None:
                db.execute('''INSERT INTO preferences VALUES (1,?,1) ON CONFLICT(id)
                    DO UPDATE SET payload=excluded.payload,revision=preferences.revision+1''', (settings.model_dump_json(),))
            row = db.execute('SELECT * FROM preferences WHERE id=1').fetchone()
            return {'settings':DisplaySettings.model_validate_json(row['payload']).model_dump() if row else DisplaySettings().model_dump(),
                    'revision':row['revision'] if row else 0}
