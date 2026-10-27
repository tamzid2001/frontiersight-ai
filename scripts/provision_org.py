"""Provision a Team/Enterprise organisation (sales-led, manual by design).

Usage:
  DATABASE_URL=sqlite:///data/frontiersight.db \
  python3 scripts/provision_org.py --org "Acme Safety" --email ops@acme.example --role owner

Creates the org membership for an existing signed-up user, marks the Team
entitlement (plan_for() reads the org_provisioned audit row), and records the
provisioning in the org audit log. SSO/SAML is then configured in the identity
provider for this org — see docs/PAID_PLANS_INTEGRATION_PROMPT.md.
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.api import store

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--org", required=True); p.add_argument("--email", required=True)
    p.add_argument("--role", default="owner", choices=["owner", "admin", "member"])
    a = p.parse_args()
    user = store.one("SELECT id FROM users WHERE email=?", (a.email.lower(),))
    if not user:
        print(f"no account for {a.email} — the user must sign up first"); return 2
    store.q("INSERT OR REPLACE INTO org_members(user_id, org, role, created_at) VALUES(?,?,?,?)",
            (user["id"], a.org, a.role, time.time()))
    store.audit(user["id"], "org_provisioned", f"{a.org} ({a.role})", org=a.org)
    print(f"provisioned: {a.email} -> org '{a.org}' as {a.role}; plan now: {store.plan_for(user['id'])}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
