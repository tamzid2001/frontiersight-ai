"""Clerk identity integration (accurate, key-gated).

- Publishable key is public by design and safe to expose to the browser.
- Session JWTs are verified server-side against the instance JWKS
  (RS256, issuer = the Frontend API host encoded in the publishable key).
  No secret key is needed for verification; CLERK_SECRET_KEY is only for
  Backend API calls, which this integration does not make.
- Clerk is the identity provider; FrontierSight sessions/entitlements are
  issued locally after verification (POST /api/auth/clerk-sync), so every
  downstream system (scenes, BYOK, gates) keeps working unchanged.
- Webhooks use Clerk's Svix signing scheme, verified exactly as documented.
"""
from __future__ import annotations
import base64, hashlib, hmac, json, os, time, urllib.request

_jwks_cache: dict = {"at": 0.0, "keys": {}}

def publishable_key() -> str:
    return os.environ.get("CLERK_PUBLISHABLE_KEY", "").strip()

def enabled() -> bool:
    return bool(publishable_key())

def verified_profile(user_id: str) -> dict:
    """Read identity attributes from Clerk, never from the caller's JSON.
    A verified token identifies a subject, not an arbitrary posted email."""
    import re
    if not isinstance(user_id, str) or not re.fullmatch(r"user_[A-Za-z0-9_-]{1,120}", user_id):
        raise ValueError("invalid Clerk subject")
    secret = os.environ.get("CLERK_SECRET_KEY", "").strip()
    if not secret:
        raise RuntimeError("CLERK_BACKEND_NOT_CONFIGURED")
    from clerk_backend_api import Clerk
    with Clerk(bearer_auth=secret, timeout_ms=5000) as client:
        profile = client.users.get(user_id=user_id)
    if profile.id != user_id:
        raise ValueError("Clerk profile subject mismatch")
    primary = next((email for email in profile.email_addresses
                    if email.id == profile.primary_email_address_id
                    and email.verification and email.verification.status == "verified"), None)
    return {"email": primary.email_address if primary else user_id + "@clerk.local",
            "name": " ".join(value for value in (profile.first_name, profile.last_name) if value)[:120] or "Clerk user"}

def frontend_api_host() -> str:
    """pk_test_<base64(host$)> -> host (documented key format)."""
    key = publishable_key()
    if "_" not in key: raise ValueError("malformed Clerk publishable key")
    payload = key.split("_", 2)[-1]
    host = base64.b64decode(payload + "=" * (-len(payload) % 4)).decode().rstrip("$")
    return host

def _fetch_jwks(host: str) -> dict:
    with urllib.request.urlopen(f"https://{host}/.well-known/jwks.json", timeout=15) as r:
        return json.loads(r.read().decode())

def _public_key(host: str, kid: str):
    now = time.time()
    if now - _jwks_cache["at"] > 3600 or host not in _jwks_cache.get("host", ""):
        doc = _fetch_jwks(host)
        _jwks_cache.update({"at": now, "host": host,
                            "keys": {k["kid"]: k for k in doc.get("keys", [])}})
    jwk = _jwks_cache["keys"].get(kid)
    if not jwk: raise ValueError("unknown signing key (kid)")
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
    n = int.from_bytes(base64.urlsafe_b64decode(jwk["n"] + "=" * (-len(jwk["n"]) % 4)), "big")
    e = int.from_bytes(base64.urlsafe_b64decode(jwk["e"] + "=" * (-len(jwk["e"]) % 4)), "big")
    return RSAPublicNumbers(e, n).public_key()

def verify_session_token(token: str, host: str | None = None, leeway: int = 10) -> dict:
    """Verify a Clerk session JWT. Returns claims; raises ValueError on any failure."""
    host = host or frontend_api_host()
    parts = token.split(".")
    if len(parts) != 3: raise ValueError("malformed JWT")
    def dec(seg: str) -> bytes:
        return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))
    header = json.loads(dec(parts[0])); claims = json.loads(dec(parts[1]))
    if header.get("alg") != "RS256": raise ValueError("unexpected JWT alg")
    key = _public_key(host, header.get("kid", ""))
    from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.exceptions import InvalidSignature
    try:
        key.verify(dec(parts[2]), f"{parts[0]}.{parts[1]}".encode(), PKCS1v15(), SHA256())
    except InvalidSignature:
        raise ValueError("JWT signature invalid")
    now = time.time()
    if claims.get("iss") != f"https://{host}": raise ValueError("JWT issuer mismatch")
    if now > float(claims.get("exp", 0)) + leeway: raise ValueError("JWT expired")
    if claims.get("nbf") and now + leeway < float(claims["nbf"]): raise ValueError("JWT not yet valid")
    if not claims.get("sub"): raise ValueError("JWT has no subject")
    return claims

def verify_svix(raw_body: bytes, headers: dict, secret: str | None = None) -> dict:
    """Verify a Clerk (Svix) webhook. Raises ValueError on failure."""
    secret = secret if secret is not None else os.environ.get("CLERK_WEBHOOK_SIGNING_SECRET", "")
    if not secret: raise RuntimeError("WEBHOOK_NOT_CONFIGURED: CLERK_WEBHOOK_SIGNING_SECRET missing")
    key = base64.b64decode(secret.removeprefix("whsec_"))
    msg_id = headers.get("svix-id", ""); ts = headers.get("svix-timestamp", "")
    sig_header = headers.get("svix-signature", "")
    if not msg_id or not ts or not sig_header: raise ValueError("missing svix headers")
    if abs(time.time() - int(ts)) > 300: raise ValueError("webhook timestamp outside tolerance")
    signed = f"{msg_id}.{ts}.".encode() + raw_body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    candidates = [part.split(",", 1)[1] for part in sig_header.split(" ") if part.startswith("v1,")]
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise ValueError("webhook signature mismatch")
    return json.loads(raw_body.decode())
