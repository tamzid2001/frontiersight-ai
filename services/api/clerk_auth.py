"""Official Clerk session verification. Identity is never read from JSON/UI state."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from urllib.parse import urlparse


class WorkspaceError(ValueError):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


@dataclass(frozen=True)
class Identity:
    user_id: str
    org_id: str | None
    org_role: str | None
    plan: str
    token_scopes: tuple[str, ...] | None = None

    def __post_init__(self):
        if (not re.fullmatch(r"user_[A-Za-z0-9_-]{1,120}", self.user_id)
            or self.org_id is not None and not re.fullmatch(r"org_[A-Za-z0-9_-]{1,120}", self.org_id)
            or self.plan not in ("explorer", "researcher", "team")):
            raise WorkspaceError(401, "invalid_identity")

    @property
    def tenant(self):
        return "org_" + self.org_id if self.org_id else "user_" + self.user_id

    @property
    def administrator(self):
        return not self.org_id or self.org_role == "org:admin"


def _origin(value: str, production: bool) -> str:
    parsed = urlparse(value)
    if (parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password
        or parsed.scheme not in ("https", "http") or not parsed.hostname
        or parsed.scheme != "https" and (production or parsed.hostname not in ("localhost", "127.0.0.1"))):
        raise WorkspaceError(503, "invalid_clerk_origin")
    return value


def authenticate(authorization: str, env=None) -> Identity:
    env = os.environ if env is None else env
    if not re.fullmatch(r"Bearer [^\s]{20,16384}", authorization):
        raise WorkspaceError(401, "authentication_required")
    secret, issuer = env.get("CLERK_SECRET_KEY", ""), env.get("CLERK_ISSUER", "")
    parties = [x.strip() for x in env.get("CLERK_AUTHORIZED_PARTIES", "").split(",") if x.strip()]
    if not secret or not issuer or not parties:
        raise WorkspaceError(503, "clerk_not_configured")
    production = env.get("VERCEL_ENV") == "production"
    _origin(issuer, production)
    for party in parties:
        _origin(party, production)
    from clerk_backend_api import Clerk
    from clerk_backend_api.security import AuthenticateRequestOptions
    import httpx
    with Clerk(bearer_auth=secret, timeout_ms=5000) as client:
        try:
            state = client.authenticate_request(httpx.Request("GET", parties[0] + "/api/scenes",
                headers={"Authorization": authorization}), AuthenticateRequestOptions(
                    secret_key=secret, jwt_key=env.get("CLERK_JWT_KEY", "").replace("\\n", "\n") or None,
                    authorized_parties=parties, accepts_token=["session_token"], clock_skew_in_ms=1000))
        except Exception:
            raise WorkspaceError(401, "invalid_session") from None
    claims = state.payload or {}
    if not state.is_signed_in or claims.get("iss") != issuer or claims.get("azp") not in parties or claims.get("v") != 2:
        raise WorkspaceError(401, "invalid_session")
    user_id = claims.get("sub", "")
    org = claims.get("o") or {}
    if not isinstance(org, dict) or not re.fullmatch(r"user_[A-Za-z0-9_-]{1,120}", user_id):
        raise WorkspaceError(401, "invalid_identity")
    org_id, role = org.get("id"), org.get("rol")
    if org_id is not None and (not isinstance(org_id, str) or not re.fullmatch(r"org_[A-Za-z0-9_-]{1,120}", org_id)
                               or not isinstance(role, str) or not re.fullmatch(r"[A-Za-z0-9_:-]{1,80}", role)):
        raise WorkspaceError(401, "invalid_organization")
    # Pin plan ownership to the active entity; personal Pro cannot upgrade a free org.
    prefix = "o:" if org_id else "u:"
    plans = claims.get("pla", "")
    plans = set(plans.split(",")) if isinstance(plans, str) else set()
    paid = any(prefix + plan in plans for plan in ("pro", "enterprise", "researcher", "team"))
    plan = ("team" if org_id else "researcher") if paid else "explorer"
    return Identity(user_id, org_id, "org:" + role.removeprefix("org:") if role else None, plan)
