# Admin-hosted scanner and member access

Implemented 11 November 2026. Run **one central server** with the administrator's Dhan credentials. Share the HTTPS website URL with members. They do not need a project ZIP, Python, Dhan credentials, or a separate market-data connection.

For the additional request/login hardening, exact limits and deployment options, read [SECURITY.md](SECURITY.md).

## First administrator

From the project folder in Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/manage_users.py create-admin --email owner@example.com
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Replace the example email with yours. The management command privately prompts for a password (12–128 characters), repeats it, and asks for a display name. No default administrator or password exists. If `.venv` already exists, skip its creation. macOS/Linux equivalents use `python3.11` and `.venv/bin/python`.

Open `http://127.0.0.1:8000/login`. Enter email/password, scan the QR code with Google Authenticator, and submit its current six-digit code. The manual setup key is available if scanning is inconvenient. Subsequent logins require email/password and a fresh code. Keep the server's time synchronized.

The admin dashboard retains the existing credentials, CSV, scanner, cache, settings, backtest, and algo controls. Save the **administrator's** Dhan client ID/token there. All members read the same server's computed results; additional members do not create Dhan subscriptions or candle/quote requests.

## Signup and approval

1. Member opens `/signup`, enters name/email/password, and enrolls Google Authenticator.
2. After confirming the code, the member sees **Awaiting administrator approval**, with no scanner data.
3. Admin opens **Member access**, selects **Refresh**, and clicks **Approve** beside that account. Approval is disabled until authenticator enrollment is complete.
4. The member's page automatically becomes a read-only dashboard. It shows confirmed Possible Candidate and Redwala rows, badges, turnover, volume information, prices and circuit distances. No member settings, backtests, credentials, or algo actions are exposed.
5. **Suspend** immediately revokes that member's sessions and outstanding login challenges. The open page detects this on its next poll. **Restore access** allows a suspended member to sign in again; it does not restore old sessions.

Email is an account identifier. This version does **not** verify email ownership or send email, password-reset links, or approval notifications. The admin should check the identity of applicants before approval. Signup never grants an administrator role; administrator creation is local-console only.

## Shared settings and existing scanner behavior

Scanner filters remain server settings, changed only by the admin. Display volume, maximum stock price, circuit-band toggle and setup selection are now saved centrally in `auth.sqlite3`, rather than depending on each browser's localStorage. Admin edits are serialized and saved automatically; wait for **Shared settings saved** before navigating away. Failed saves show **Retry** and keep the unsaved draft. A browser refresh loads server settings.

Members receive confirmed Possible Candidates and Redwala only. Choosing Retest-only in the admin's shared setup selector therefore leaves the member dashboard empty. Existing admin views can still show preparation/provisional rows and Retest Break. Member counts refer only to their displayed confirmed rows.

Priority is unchanged: the complete Possible Candidate + Resistance Break + Resistance Break Open + First Candle High Break combination first; Redwala + First Candle Low Break + First Candle PDL Cross second (second-candle PDL badge is optional); remaining rows next. Each group sorts by first-candle turnover descending. The default verified circuit-band >=20% rule, UC Away %, LC Away %, volume minimum and maximum-price display rules are enforced on the member **backend**, not merely hidden by JavaScript.

Member pages poll every two seconds and reuse a shared snapshot cached for at most one second. An admin display-setting revision invalidates that snapshot immediately. Thus dashboard propagation is generally around 1–3 seconds plus network latency. Market-data ingestion, candidate confirmation, and order execution retain their existing timings and throttles. Members cannot run trades. Admin logout does not stop the scanner or running algos.

## Public HTTPS hosting

The source is ready for hosting, but implementation does not register a domain or deploy a public server. Use a server that stays running during trading and an HTTPS reverse proxy. Keep Uvicorn bound to localhost; expose only the proxy. Run **one worker**, without `--reload`, so there is only one scanner, Dhan feed and order engine.

Example PowerShell environment and server command, with an HTTPS proxy on the same machine:

```powershell
$env:SCANNER_PUBLIC_ORIGIN = 'https://scanner.example.com'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
```

Use your real HTTPS domain. Configure the service environment to preserve this variable after reboot. An example Caddy configuration is:

```text
scanner.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

The domain must point to your server, and ports 80/443 must reach the proxy for certificate issuance and HTTPS. Configure the proxy to preserve Host and set the correct forwarded scheme/client address; trust only that proxy's IP in Uvicorn, never arbitrary forwarded headers. Remote requests are rejected without the configured HTTPS origin. Local development permits localhost HTTP. Existing local launchers are for local use; use the service command above for hosting. Broker order requirements, including the configured static-IP requirement, still apply to the admin's broker integration.

HTTPS sets Secure, HttpOnly, SameSite=Strict session cookies. Requests from other origins are rejected. Mutations additionally require a session CSRF token, while public login/signup use same-origin JSON with an explicit request header. Security headers disable framing and restrict scripts to the application's own assets.

## Storage, recovery, and backups

| File | Contents |
|---|---|
| `data/auth.sqlite3` (plus SQLite WAL files while running) | Accounts, Argon2id password hashes, encrypted TOTP secrets, hashed opaque session/challenge IDs, approval state, rate counters, shared display settings, account audit events |
| `data/auth.key` | Encryption key for TOTP secrets; keep together with a protected database backup |
| Existing `data/` config/cache/algo files | Admin Dhan credentials, history and trading state; unchanged by account signup |

Keep the server's `data/` directory private, with OS permissions restricted to the service account and administrator. Do not include it in distributed ZIP files, source repositories or public web directories. The encryption key resides on the same server, so protect the machine as well as the database. Back up using SQLite's backup API, or stop the service before copying all database/key files. Never copy only an actively written `.sqlite3` file while ignoring its WAL. Losing `auth.key` requires restoring it; the app refuses to silently replace a key used by existing accounts.

Local operator recovery commands:

```powershell
.\.venv\Scripts\python.exe scripts/manage_users.py reset-password --email member@example.com
.\.venv\Scripts\python.exe scripts/manage_users.py reset-mfa --email member@example.com
```

Resetting either revokes all sessions and login challenges for that account. MFA reset requires typing `RESET`; next login enrolls a new authenticator. Approval status is retained. Verify the person's identity before recovery. There are no recovery codes or public password-reset endpoints in this version. Additional admins use the same `create-admin` command.

Passwords are hashed with Argon2id; TOTP secrets are encrypted with Fernet. Session IDs are stored as SHA-256 digests. At most five sessions are retained per account. Sessions expire after 12 hours or 30 minutes without authenticated activity; an open polling dashboard counts as activity. OTP challenges last five minutes, allow five failed codes, and reject previously accepted time steps. Login/signup/verification have persistent per-IP and global limits; login and OTP verification also have account-specific limits across fresh challenges. See SECURITY.md for exact budgets. A successfully entered code cannot be reused for another login in the same time step—wait for the next code.

## Validation and operational limits

Automated tests cover actual password/TOTP authentication, approval and suspension, every existing admin API's member/anonymous denial, CSRF/origin restrictions, secure cookies, replay prevention, session expiry, encrypted storage, shared display settings, and desktop/mobile signup-to-dashboard flows. Market/broker data is simulated during testing; no real orders or customer accounts are created.

This is a single-process, SQLite-backed hosted application, not a horizontally replicated platform. No public-host deployment, independent security assessment, or high-concurrency capacity benchmark has been performed as part of this change. Validate server sizing and operating procedures before broad distribution.
