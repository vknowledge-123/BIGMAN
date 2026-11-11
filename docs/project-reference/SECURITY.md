# Security hardening and deployment

Updated 11 November 2026. These controls reduce common attack risks; they are not a guarantee against every vulnerability, distributed denial-of-service attack, stolen device, or compromised server.

## Protections implemented

| Area | Protection |
|---|---|
| Authentication | Argon2id password hashes, mandatory Google Authenticator-compatible TOTP, no public admin creation, admin approval for members |
| Password guessing | Persistent per-account and per-IP attempt budgets; invalid credentials return a generic login error; changing `X-Forwarded-For` does not change the application's client address |
| OTP guessing/replay | Five attempts per five-minute challenge; ten verification attempts per account per 15 minutes across fresh challenges; previously accepted time steps cannot be reused |
| Password-hash resource exhaustion | At most two concurrent Argon2 operations (64 MiB each); overload receives HTTP 429 instead of queuing unlimited hash work |
| Sessions | Random opaque tokens, only token digests stored, HttpOnly/SameSite=Strict cookies, Secure on HTTPS, 12-hour expiry and 30-minute inactivity expiry; at most five sessions per account; logout, suspension and credential reset revoke sessions |
| Authorization | All scanner controls, settings, credentials, backtests and algo APIs require administrator access; approved members receive a whitelisted, filtered read-only result API |
| CSRF | Same-origin checks on all HTTP routes; session CSRF tokens on authenticated writes; public authentication accepts JSON plus the application's explicit request header |
| Script injection | Untrusted text/attribute values are escaped before HTML rendering; account labels use textContent; CSP allows only local scripts and blocks inline/eval scripts, plugins and framing |
| SQL injection | Account and cache SQL uses bound parameters; malicious account names remain data, not executable SQL |
| Flooding | Bounded global/per-client token buckets run before expensive route handling; authentication has additional early throttling; bucket memory is capped, and overload fails closed |
| Oversized/slow requests | URL/header/body limits, ten-second body-read timeout, at most 16 simultaneous body readers; streamed bodies are counted, not trusted from Content-Length alone |
| Parser abuse | Only JSON write bodies; compressed and multipart bodies rejected; deeply nested/invalid JSON and ambiguous body lengths rejected; large CSV upload routes require admin/CSRF authorization before buffering |
| Browser boundaries | Host/origin checks on all routes, no permissive CORS, no-store responses, nosniff, frame denial, restricted permissions and HTTPS HSTS |
| Error disclosure | Validation responses omit submitted input/context, including passwords and OTP values; unexpected errors return a generic message instead of traceback/exception contents |
| API discovery/private files | Public `/docs` and `/redoc` disabled; `/openapi.json` is admin-only; `/health` exposes only the application identity; static HTML routes blocked and private data remains outside the static directory |
| Monitoring | `scanner.security` reports rejected-request status codes at most once per status per minute, without request bodies, query strings, cookies or credentials; existing account audit events remain in the account DB |

No regular-expression blacklist of words such as `script` or `SELECT` is used. Context-aware escaping, parameterized SQL, authorization and bounded input processing are the actual defenses. Broker feeds and execution workers do not pass through the HTTP request limiter.

## Exact default limits

- Global HTTP: refill 300 requests/second, burst 600.
- Per ASGI client IP: refill 10 requests/second, burst 120.
- Authentication POST requests: additional refill 1/second per IP, burst 12, including malformed authentication requests.
- Persistent signup: 8/IP/15 minutes; 200 globally/15 minutes.
- Persistent login and OTP endpoints: 40/IP/15 minutes for each action; 600 globally/minute for each action.
- Password login: 10 attempts per normalized email/15 minutes. OTP: 10 attempts per account/15 minutes, across fresh challenges. These count attempts, including successful ones. Expiration is automatic; no permanent lockout is used.
- Rate responses include `Retry-After`. Browser polling counts as authenticated session activity. Different users sharing one NAT/proxy can share IP budgets; size and test hosting capacity before increasing limits.
- URL path: 2,048 bytes; query: 4,096 bytes; combined headers: 16 KiB.
- Authentication body: 16 KiB. Other JSON bodies: 256 KiB. Admin CSV preview/apply envelope: 13 MiB, allowing JSON escaping around the existing **2 MiB actual CSV limit**.
- JSON nesting: maximum 32 levels. Body read: 10 seconds. Maximum simultaneous body readers: 16.

The in-memory ingress limiter resets at restart and assumes the documented single-worker deployment. Account/IP authentication budgets survive restarts in SQLite. Distributed enforcement across multiple servers requires a separate shared rate-limit system; multiple scanner workers are not supported by the current trading architecture.

## Installing the update

Use the project's virtual environment so upgrading this application does not change unrelated Python projects:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Skip virtual-environment creation if it already exists. Updated requirements pin compatible FastAPI, Starlette, Requests, cryptography, pyOpenSSL and pytest versions. Dhan's SDK version and scanner/algo rules are unchanged. Existing users, approvals, passwords, TOTP enrollment and encryption keys are retained; do not delete `data/auth.sqlite3` or `data/auth.key`.

Restart the application to activate updated code and packages. Do not interrupt an active live algo to perform an update; follow the existing exit/reconciliation procedure first. The Windows launcher uses `.venv` when present, disables proxy-header trust for local operation, and checks `/health` instead of the now-protected API schema.

## Required public-host configuration

Use HTTPS, a firewall and a maintained reverse proxy. Keep Uvicorn reachable only from the proxy. Set the exact public origin and trust forwarded headers only from the proxy's address:

```powershell
$env:SCANNER_PUBLIC_ORIGIN = 'https://scanner.example.com'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header --no-access-log --h11-max-incomplete-event-size 16384
```

Replace the domain with yours. Do not use `--forwarded-allow-ips '*'` on an externally reachable server. Preserve the Host header and let the proxy set the correct forwarded scheme/client address. No `--reload` in production. Run the service as a dedicated OS account without administrator privileges, restrict `data/` permissions, protect database/key backups, and keep the OS and proxy patched.

Configure proxy-level body, header, connection and idle-read limits too: application middleware runs only after the server has received HTTP headers. An example local Caddy reverse proxy is in [MEMBER_HOSTING.md](MEMBER_HOSTING.md); apply a 13 MiB request body limit and suitable connection/read limits there. Large network floods require hosting-provider/CDN/WAF DDoS protection before traffic reaches this machine. These external controls are documented here, not provisioned automatically.

## Verification and ongoing maintenance

The security tests use disposable databases, synthetic market data and browser payloads. They cover route authorization, cross-origin/host rejection, private-file probes, malformed/oversized/streamed requests, parser depth, request flooding, credential/OTP budgets, rate persistence, bounded password work, SQL-injection strings and stored XSS in both dashboards. No real orders are placed.

Run the tests and dependency check after updates:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# Install pip-audit in a separate audit environment if preferred.
.\.venv\Scripts\python.exe -m pip install pip-audit
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

The resolved requirements audit on this change reported **zero known vulnerabilities across 42 dependencies**. That is a database check at one point in time, not proof of zero unknown vulnerabilities. The review found and replaced vulnerable dependency versions; repeat the check regularly. No third-party penetration test or public-host DDoS simulation was performed.

Email ownership is still not automatically verified; the administrator must verify applicants before approval. MFA recovery remains a local operator procedure. Existing authorized-admin business-error messages can include diagnostic scanner/broker information; these endpoints are never accessible to members. Protect the hosting machine: a person with access to its files can read the key beside the encrypted account database.

References used in the review: [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), [OWASP denial-of-service guidance](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html), [FastAPI trusted-proxy configuration](https://fastapi.tiangolo.com/advanced/behind-a-proxy/), and [Starlette security release notes](https://starlette.dev/release-notes/).
