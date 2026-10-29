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
    if os.environ.get("BILLING_IDENTITY") == "clerk":
        durable_store = bool(os.environ.get("CLERK_SECRET_KEY") and os.environ.get("CLERK_ISSUER")
            and os.environ.get("CLERK_AUTHORIZED_PARTIES") and os.environ.get("FIRESTORE_PROJECT_ID")
            and (os.environ.get("FIRESTORE_SERVICE_ACCOUNT_JSON") or os.environ.get("FIRESTORE_USE_ADC") == "true")
            and len(os.environ.get("WORKSPACE_AUDIT_SECRET", "")) >= 32)
        if production and not os.environ.get("CLERK_SECRET_KEY", "").startswith("sk_live_"):
            durable_store = False
    common = bool(key and os.environ.get("STRIPE_WEBHOOK_SECRET") and durable_store
                  and (not production or live))
    periods = {period: bool(common and os.environ.get(name, "").startswith("price_"))
               for period, name in (("monthly", "PRICE_RESEARCHER_MONTHLY"),
                                    ("annual", "PRICE_RESEARCHER_ANNUAL"))}
    return {"provider": "stripe", "ready": all(periods.values()), "periods": periods,
            "mode": "live" if common and live else "test" if common else "unavailable",
            "currency": "USD", "monthly_usd": 19, "annual_usd": 190,
            "first_period_discount_pct": 50 if os.environ.get("STRIPE_FIRST_PERIOD_COUPON") else 0}

def _req(method: str, path: str, form: dict | None = None, *, idempotency=None) -> dict:
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key: raise BillingNotConfigured("Stripe is not configured on this deployment (STRIPE_SECRET_KEY missing). Join the waitlist instead — no payment can be taken yet.")
    data = urllib.parse.urlencode(form or {}, doseq=True).encode() if form is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/x-www-form-urlencoded",
                 **({"Idempotency-Key": idempotency} if idempotency else {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read(2_000_000).decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Stripe request failed (HTTP {e.code}).") from None

def create_checkout(user: dict, price_id: str, success_url: str, cancel_url: str,
                    period: str = "monthly") -> dict:
    if period not in ("monthly", "annual"):
        raise ValueError("period must be monthly or annual")
    if not checkout_configuration()["periods"][period]:
        raise BillingNotConfigured("Subscription checkout is not available yet. No payment was taken.")
    expected = os.environ.get("PRICE_RESEARCHER_ANNUAL" if period == "annual" else "PRICE_RESEARCHER_MONTHLY", "")
    if price_id != expected:
        raise BillingNotConfigured("The selected plan is not configured.")
    validate_price(price_id, period)
    return _req("POST", "/checkout/sessions", {
        "mode": "subscription", "line_items[0][price]": price_id, "line_items[0][quantity]": 1,
        "success_url": success_url, "cancel_url": cancel_url,
        "client_reference_id": str(user["id"]), "customer_email": user["email"],
        "metadata[user_id]": str(user["id"]),
        "subscription_data[metadata][user_id]": str(user["id"])})

def validate_price(price_id, period):
    price = _req("GET", "/prices/" + urllib.parse.quote(price_id, safe=""))
    recurrence = price.get("recurring") or {}
    if (not price.get("active") or price.get("currency") != "usd"
        or price.get("unit_amount") != (19000 if period == "annual" else 1900)
        or recurrence.get("interval") != ("year" if period == "annual" else "month")
        or recurrence.get("interval_count") != 1
        or os.environ.get("VERCEL_ENV") == "production" and not price.get("livemode")):
        raise BillingNotConfigured("The Stripe price does not match the displayed plan.")

def create_portal(customer_id: str, return_url: str) -> dict:
    return _req("POST", "/billing_portal/sessions", {"customer": customer_id, "return_url": return_url})

def verify_webhook(raw_body: bytes, sig_header: str, secret: str | None = None,
                   tolerance: int = 300) -> dict:
    """Verify a Stripe webhook signature and return the parsed event.
    Raises ValueError on any mismatch — callers must reject before parsing state."""
    secret = secret if secret is not None else os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret: raise BillingNotConfigured("Webhook secret not configured (STRIPE_WEBHOOK_SECRET).")
    if len(raw_body) > 1_000_000 or len(sig_header) > 4096:
        raise ValueError("webhook budget exceeded")
    parts = [kv.split("=", 1) for kv in sig_header.split(",") if "=" in kv]
    timestamps = [v for k,v in parts if k == "t"]
    signatures = [v for k,v in parts if k == "v1"]
    if len(timestamps) != 1 or not signatures:
        raise ValueError("malformed Stripe-Signature header")
    ts = timestamps[0]
    if abs(time.time() - int(ts)) > tolerance: raise ValueError("webhook timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise ValueError("webhook signature mismatch")
    return json.loads(raw_body.decode())

# --- entitlements -----------------------------------------------------------
LIMITS = {
    "explorer":   {"mc_runs": 200, "server_scenes": 10, "sam_video": False, "byok": False},
    "researcher": {"mc_runs": 2000, "server_scenes": 5000, "sam_video": True, "byok": True},   # None = unlimited
    "team":       {"mc_runs": None, "server_scenes": 5000, "sam_video": True, "byok": True},
}

def entitlements(plan: str) -> dict:
    return {"plan": plan, **LIMITS.get(plan, LIMITS["explorer"])}

class PaymentRequired(RuntimeError):
    def __init__(self, capability: str, plan: str):
        super().__init__(f"'{capability}' requires the Researcher plan (current: {plan})")
        self.capability, self.plan = capability, plan
