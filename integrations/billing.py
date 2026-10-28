"""Stripe billing seam (stdlib client) + entitlements.

No keys -> BillingNotConfigured, and every surface says so honestly.
With STRIPE_SECRET_KEY set (test or live): Checkout/Portal sessions are created
over the Stripe API, and webhook signatures are verified with HMAC-SHA256
exactly as Stripe specifies (t + '.' + raw body, v1 scheme, 5-minute tolerance).
Card data never touches this server."""
from __future__ import annotations
import hashlib, hmac, json, os, time, urllib.parse, urllib.request, urllib.error

API = "https://api.stripe.com/v1"

class BillingNotConfigured(RuntimeError):
    code = "BILLING_NOT_CONFIGURED"

def configured() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY", "").strip())


def checkout_configuration() -> dict:
    """Public availability, never secret values or unverified payment claims."""
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    production = os.environ.get("VERCEL_ENV") == "production"
    live = key.startswith(("sk_live_", "rk_live_"))
    # This legacy account store is SQLite. Vercel's /tmp cannot durably retain
    # subscriptions, webhook receipts or sessions; do not collect payments there.
    database_url = os.environ.get("DATABASE_URL", "")
    durable_store = (not bool(os.environ.get("VERCEL"))
                     and (not database_url or database_url.startswith("sqlite:///"))
                     and not database_url.startswith(("sqlite:////tmp/", "sqlite:////private/tmp/")))
    common = bool(key and os.environ.get("STRIPE_WEBHOOK_SECRET") and durable_store
                  and (not production or live))
    periods = {period: bool(common and os.environ.get(name, "").startswith("price_"))
               for period, name in (("monthly", "PRICE_RESEARCHER_MONTHLY"),
                                    ("annual", "PRICE_RESEARCHER_ANNUAL"))}
    return {"provider": "stripe", "ready": all(periods.values()), "periods": periods,
            "mode": "live" if common and live else "test" if common else "unavailable",
            "currency": "USD", "monthly_usd": 19, "annual_usd": 190}

def _req(method: str, path: str, form: dict | None = None) -> dict:
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key: raise BillingNotConfigured("Stripe is not configured on this deployment (STRIPE_SECRET_KEY missing). Join the waitlist instead — no payment can be taken yet.")
    data = urllib.parse.urlencode(form or {}, doseq=True).encode() if form is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Stripe HTTP {e.code}: {e.read().decode()[:300]}") from e

def create_checkout(user: dict, price_id: str, success_url: str, cancel_url: str,
                    period: str = "monthly") -> dict:
    if period not in ("monthly", "annual"):
        raise ValueError("period must be monthly or annual")
    if not checkout_configuration()["periods"][period]:
        raise BillingNotConfigured("Subscription checkout is not available yet. No payment was taken.")
    expected = os.environ.get("PRICE_RESEARCHER_ANNUAL" if period == "annual" else "PRICE_RESEARCHER_MONTHLY", "")
    if price_id != expected:
        raise BillingNotConfigured("The selected plan is not configured.")
    price = _req("GET", "/prices/" + urllib.parse.quote(price_id, safe=""))
    recurrence = price.get("recurring") or {}
    if (not price.get("active") or price.get("currency") != "usd"
        or price.get("unit_amount") != (19000 if period == "annual" else 1900)
        or recurrence.get("interval") != ("year" if period == "annual" else "month")
        or recurrence.get("interval_count") != 1
        or os.environ.get("VERCEL_ENV") == "production" and not price.get("livemode")):
        raise BillingNotConfigured("The Stripe price does not match the displayed plan.")
    return _req("POST", "/checkout/sessions", {
        "mode": "subscription", "line_items[0][price]": price_id, "line_items[0][quantity]": 1,
        "success_url": success_url, "cancel_url": cancel_url,
        "client_reference_id": str(user["id"]), "customer_email": user["email"],
        "metadata[user_id]": str(user["id"]),
        "subscription_data[metadata][user_id]": str(user["id"])})

def create_portal(customer_id: str, return_url: str) -> dict:
    return _req("POST", "/billing_portal/sessions", {"customer": customer_id, "return_url": return_url})

def verify_webhook(raw_body: bytes, sig_header: str, secret: str | None = None,
                   tolerance: int = 300) -> dict:
    """Verify a Stripe webhook signature and return the parsed event.
    Raises ValueError on any mismatch — callers must reject before parsing state."""
    secret = secret if secret is not None else os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret: raise BillingNotConfigured("Webhook secret not configured (STRIPE_WEBHOOK_SECRET).")
    parts = dict(kv.split("=", 1) for kv in sig_header.split(",") if "=" in kv)
    ts, sig = parts.get("t"), parts.get("v1")
    if not ts or not sig: raise ValueError("malformed Stripe-Signature header")
    if abs(time.time() - int(ts)) > tolerance: raise ValueError("webhook timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig): raise ValueError("webhook signature mismatch")
    return json.loads(raw_body.decode())

# --- entitlements -----------------------------------------------------------
LIMITS = {
    "explorer":   {"mc_runs": 200, "server_scenes": 10, "sam_video": False, "byok": False},
    "researcher": {"mc_runs": 2000, "server_scenes": None, "sam_video": True, "byok": True},   # None = unlimited
    "team":       {"mc_runs": None, "server_scenes": None, "sam_video": True, "byok": True},
}

def entitlements(plan: str) -> dict:
    return {"plan": plan, **LIMITS.get(plan, LIMITS["explorer"])}

class PaymentRequired(RuntimeError):
    def __init__(self, capability: str, plan: str):
        super().__init__(f"'{capability}' requires the Researcher plan (current: {plan})")
        self.capability, self.plan = capability, plan
