"""Persistence seam.

Today: SQLite (stdlib) — file path from DATABASE_URL=sqlite:///<path>, else
`data/frontiersight.db` locally, `/tmp/frontiersight.db` on Vercel (per-instance,
ephemeral: accounts/scenes survive a warm instance, not a cold redeploy).
When a real DATABASE_URL (Postgres) is provided, swap the implementation behind
these functions — call sites must not change. Tables: users, sessions,
subscriptions, scenes, waitlist, quotes, stripe_events, user_keys, audit_log.
"""
from __future__ import annotations
import hashlib, json, os, sqlite3, threading, time
from pathlib import Path

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

def _path() -> Path:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///"))
    if os.environ.get("VERCEL"):
        return Path("/tmp/frontiersight.db")
    return Path(__file__).resolve().parents[2] / "data" / "frontiersight.db"

def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        p = _path(); p.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(p, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL, pw_hash TEXT NOT NULL, pw_salt TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
          expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS subscriptions(user_id INTEGER PRIMARY KEY, stripe_customer_id TEXT,
          stripe_sub_id TEXT, price_id TEXT, status TEXT NOT NULL DEFAULT 'none',
          current_period_end REAL, cancel_at_period_end INTEGER DEFAULT 0, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS scenes(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
          name TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS waitlist(id INTEGER PRIMARY KEY, email TEXT, plan TEXT,
          created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY, company TEXT, email TEXT,
          seats TEXT, needs TEXT, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS stripe_events(id TEXT PRIMARY KEY, processed_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS user_keys(user_id INTEGER PRIMARY KEY, kind TEXT NOT NULL,
          ciphertext TEXT NOT NULL, last4 TEXT NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, user_id INTEGER,
          org TEXT, action TEXT NOT NULL, detail TEXT, ts REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS org_members(user_id INTEGER PRIMARY KEY, org TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'member', created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS support_tickets(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
          subject TEXT NOT NULL, message TEXT NOT NULL, plan TEXT, status TEXT NOT NULL DEFAULT 'open',
          created_at REAL NOT NULL);
        """)
        try: _conn.execute("ALTER TABLE scenes ADD COLUMN org TEXT")
        except Exception: pass
        try: _conn.execute("ALTER TABLE users ADD COLUMN clerk_id TEXT")
        except Exception: pass
        _conn.commit()
    return _conn

def q(sql: str, args: tuple = ()) -> list:
    with _lock:
        cur = db().execute(sql, args); rows = cur.fetchall(); db().commit(); return rows

def one(sql: str, args: tuple = ()):
    rows = q(sql, args); return rows[0] if rows else None

# --- passwords & sessions -------------------------------------------------
def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return dk.hex(), salt.hex()

def verify_password(password: str, pw_hash: str, pw_salt: str) -> bool:
    import hmac
    dk, _ = hash_password(password, bytes.fromhex(pw_salt))
    return hmac.compare_digest(dk, pw_hash)

def new_session(user_id: int) -> str:
    import secrets
    token = secrets.token_urlsafe(32)
    th = hashlib.sha256(token.encode()).hexdigest()
    q("INSERT OR REPLACE INTO sessions(token_hash, user_id, expires_at) VALUES(?,?,?)",
      (th, user_id, time.time() + 30 * 86400))
    return token

def user_for_token(token: str | None):
    if not token: return None
    th = hashlib.sha256(token.encode()).hexdigest()
    row = one("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
              "WHERE s.token_hash = ? AND s.expires_at > ?", (th, time.time()))
    return dict(row) if row else None

def audit(user_id, action: str, detail: str = "", org: str = ""):
    q("INSERT INTO audit_log(user_id, org, action, detail, ts) VALUES(?,?,?,?,?)",
      (user_id, org, action, detail[:500], time.time()))

def plan_for(user_id: int) -> str:
    """Entitlement source of truth: an active/trialing/past-due(in grace)
    subscription at a Researcher price, or an org (Team) entitlement row."""
    sub = one("SELECT * FROM subscriptions WHERE user_id = ?", (user_id,))
    if sub and sub["status"] in ("active", "trialing", "past_due") and sub["price_id"]:
        if sub["price_id"].startswith("clerk:"):  # Clerk Billing plan slug is authoritative
            return "researcher" if sub["price_id"] == "clerk:researcher" else "explorer"
        configured = {p for p in (os.environ.get("PRICE_RESEARCHER_MONTHLY", ""),
                                  os.environ.get("PRICE_RESEARCHER_ANNUAL", "")) if p}
        if not configured or sub["price_id"] in configured:
            return "researcher"
    row = one("SELECT detail FROM audit_log WHERE user_id = ? AND action = 'org_provisioned' ORDER BY ts DESC", (user_id,))
    if row: return "team"
    return "explorer"


def provision_clerk_user(clerk_id: str, email: str, name: str):
    """Find-or-create the local user linked to a Clerk identity.
    Clerk owns the credential; the local password hash is random and unusable,
    so first-party password login can never collide with a Clerk account."""
    import time as _t
    row = one("SELECT * FROM users WHERE clerk_id=?", (clerk_id,))
    if row: return dict(row)
    row = one("SELECT * FROM users WHERE email=?", (email.lower(),)) if email else None
    if row:
        q("UPDATE users SET clerk_id=? WHERE id=?", (clerk_id, row["id"]))
        return dict(one("SELECT * FROM users WHERE id=?", (row["id"],)))
    pw_hash, pw_salt = hash_password("clerk-managed-" + clerk_id)
    q("INSERT INTO users(email, name, pw_hash, pw_salt, created_at, clerk_id) VALUES(?,?,?,?,?,?)",
      (email.lower() or f"{clerk_id}@clerk.local", name or "Clerk user", pw_hash, pw_salt, _t.time(), clerk_id))
    return dict(one("SELECT * FROM users WHERE clerk_id=?", (clerk_id,)))
