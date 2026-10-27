import { test } from "node:test";
import assert from "node:assert/strict";
import { firstPeriodQuote, promotionReady } from "../src/pricing.ts";

test("50 percent promotion applies to one month or one annual invoice; renewals stay full price", () => {
  const plan = { id: "pro", currency: "USD" as const, monthlyCents: 4900, annualCents: 46800 };
  const monthly = firstPeriodQuote(plan, "month"), annual = firstPeriodQuote(plan, "year");
  assert.equal(monthly.initialCents, 2450); assert.equal(monthly.renewalCents, 4900);
  assert.equal(annual.initialCents, 23400); assert.equal(annual.renewalCents, 46800);
  assert.equal(monthly.billingCycles, 1); assert.equal(annual.billingCycles, 1);
  assert.equal(annual.label, "First year only");
  assert.equal(firstPeriodQuote({ ...plan, monthlyCents: 0 }, "month").initialCents, 0);
  assert.equal(firstPeriodQuote({ ...plan, monthlyCents: 1 }, "month").initialCents, 1);
});

test("promotion needs explicit provider verification, not just a marketing flag", () => {
  assert.ok(promotionReady({ enabled: true, code: "LAUNCH50", providerVerified: true }));
  assert.equal(promotionReady({ enabled: true, code: "LAUNCH50", providerVerified: false }), false);
  assert.equal(promotionReady({ enabled: false, code: "LAUNCH50", providerVerified: true }), false);
  assert.equal(promotionReady({ enabled: true, code: "bad code", providerVerified: true }), false);
});

test("pricing configuration rejects fractional cents, invalid periods and currencies", () => {
  const plan = { id: "pro", currency: "USD" as const, monthlyCents: 4900, annualCents: 46800 };
  for (const monthlyCents of [NaN, Infinity, -1, 3.14, Number.MAX_SAFE_INTEGER]) {
    assert.throws(() => firstPeriodQuote({ ...plan, monthlyCents }, "month"));
  }
  assert.throws(() => firstPeriodQuote(plan, "week" as never));
  assert.throws(() => firstPeriodQuote({ ...plan, currency: "EUR" as never }, "month"));
  assert.throws(() => firstPeriodQuote({ ...plan, id: "bad plan" }, "month"));
});
