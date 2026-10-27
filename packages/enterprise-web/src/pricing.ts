/** Marketing quote math, not a payment authorization or a provider coupon. */
export const LAUNCH_PROMOTION = Object.freeze({ percentOff: 50, billingCycles: 1 });

export type PlanPrice = Readonly<{
  id: string;
  currency: "USD";
  monthlyCents: number;
  annualCents: number;
}>;

export function firstPeriodQuote(plan: PlanPrice, period: "month" | "year") {
  if (period !== "month" && period !== "year") throw new Error("invalid_billing_period");
  if (plan.currency !== "USD" || !/^[a-z][a-z0-9_-]{0,63}$/.test(plan.id)) {
    throw new Error("invalid_plan_configuration");
  }
  const normalCents = period === "month" ? plan.monthlyCents : plan.annualCents;
  if (!Number.isSafeInteger(normalCents) || normalCents < 0 || normalCents > 100_000_000) {
    throw new Error("invalid_integer_cent_price");
  }
  // Half-up rounding is explicit for integer-cent display. The payment provider
  // remains authoritative for taxes and final invoice calculations.
  const initialCents = Math.round(normalCents * (100 - LAUNCH_PROMOTION.percentOff) / 100);
  return Object.freeze({
    planId: plan.id,
    period,
    currency: plan.currency,
    initialCents,
    renewalCents: normalCents,
    discountCents: normalCents - initialCents,
    billingCycles: 1,
    label: period === "month" ? "First month only" : "First year only",
  });
}

/** Advertising must be disabled until the actual provider promotion is set up. */
export function promotionReady(config: { enabled: boolean; code: string; providerVerified: boolean }) {
  return config.enabled === true && config.providerVerified === true
    && /^[A-Z0-9_-]{3,40}$/.test(config.code);
}
