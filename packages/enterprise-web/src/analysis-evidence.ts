import { z } from "zod";
import {
  AnalysisError, define, count, id, object, records, probability, utc, magnitude,
  nonnegative, requireDistinct, rounded, group, mean,
} from "./analysis-core.ts";

const energy = define("Simulate battery dispatch",
  "Replay net demand and generation in energy intervals. Measure unserved demand, curtailment and state of charge.",
  object({ capacityKWh: nonnegative, initialKWh: nonnegative, limitKW: nonnegative,
    chargeEfficiency: probability.gt(0), dischargeEfficiency: probability.gt(0),
    intervals: records(object({ hours: z.number().min(1 / 3600).max(24), demandKWh: nonnegative, generationKWh: nonnegative })) }),
  { capacityKWh: 10, initialKWh: 0, limitKW: 5, chargeEfficiency: 0.95, dischargeEfficiency: 0.9,
    intervals: [{ hours: 1, demandKWh: 1, generationKWh: 7 }, { hours: 1, demandKWh: 6, generationKWh: 0 }] },
  ({ capacityKWh, initialKWh, limitKW, chargeEfficiency, dischargeEfficiency, intervals }) => {
    if (initialKWh > capacityKWh) throw new AnalysisError("Initial charge exceeds battery capacity.");
    let charge = initialKWh, unserved = 0, curtailed = 0;
    const rows = intervals.map(({ hours, demandKWh, generationKWh }, index) => {
      const deficit = demandKWh - generationKWh;
      const delivered = Math.min(Math.max(0, deficit), limitKW * hours, charge * dischargeEfficiency);
      const absorbed = Math.min(Math.max(0, -deficit), limitKW * hours, (capacityKWh - charge) / chargeEfficiency);
      charge = Math.max(0, Math.min(capacityKWh, charge + absorbed * chargeEfficiency - delivered / dischargeEfficiency));
      const unmet = Math.max(0, deficit - delivered);
      const spill = Math.max(0, -deficit - absorbed);
      unserved += unmet;
      curtailed += spill;
      return { Interval: index + 1, "Charge (kWh)": rounded(charge), "Unserved (kWh)": rounded(unmet),
        "Curtailed (kWh)": rounded(spill) };
    });
    return { metrics: { Intervals: rows.length, "Final charge (kWh)": rounded(charge), "Unserved demand (kWh)": rounded(unserved),
      "Curtailed generation (kWh)": rounded(curtailed) }, rows };
  });

const entry = object({ transactionId: id, currency: z.string().regex(/^[A-Z]{3}$/),
  minorUnits: z.number().int().min(-1e12).max(1e12) });
const settlement = define("Reconcile settlement entries",
  "Compare expected and posted balances per transaction and currency using exact integer minor units.",
  object({ expected: records(entry), posted: z.array(entry).max(2000) }),
  { expected: [{ transactionId: "T-01", currency: "USD", minorUnits: 1025 }],
    posted: [{ transactionId: "T-01", currency: "USD", minorUnits: 1020 }] },
  ({ expected, posted }) => {
    const key = (row: z.output<typeof entry>) => JSON.stringify([row.transactionId, row.currency]);
    const expectedGroups = group(expected, key), postedGroups = group(posted, key);
    const keys = new Set([...expectedGroups.keys(), ...postedGroups.keys()]);
    const sum = (rows?: z.output<typeof entry>[]) => rows?.reduce((total, row) => total + row.minorUnits, 0) ?? 0;
    const rows = Array.from(keys, pair => {
      const expectedRows = expectedGroups.get(pair), postedRows = postedGroups.get(pair);
      const { transactionId, currency } = (expectedRows ?? postedRows)![0];
      const expectedMinor = sum(expectedRows), postedMinor = sum(postedRows);
      return { Transaction: transactionId, Currency: currency, "Expected minor units": expectedMinor, "Posted minor units": postedMinor,
        "Difference": postedMinor - expectedMinor, Status: !expectedRows ? "Unexpected" : !postedRows ? "Missing" :
          expectedMinor === postedMinor ? "Matched" : "Mismatch" };
    });
    return { metrics: { Transactions: rows.length, "Exceptions": rows.filter(row => row.Status !== "Matched").length }, rows };
  });

const yieldAnalysis = define("Measure die yield",
  "Compute per-wafer yield and nominal Wilson 95% intervals. Exclude untested die and flag spatial dependence when interpreting intervals.",
  object({ dies: records(object({ wafer: id, x: z.number().int().min(-10000).max(10000), y: z.number().int().min(-10000).max(10000),
    status: z.enum(["pass", "fail", "untested"]) })) }),
  { dies: [{ wafer: "W-01", x: 0, y: 0, status: "pass" }, { wafer: "W-01", x: 0, y: 1, status: "fail" },
    { wafer: "W-01", x: 1, y: 0, status: "untested" }] },
  ({ dies }) => {
    requireDistinct(dies.map(die => JSON.stringify([die.wafer, die.x, die.y])), "die coordinate on one wafer");
    const rows = Array.from(group(dies, die => die.wafer), ([wafer, batches]) => {
      const passed = batches.filter(die => die.status === "pass").length;
      const tested = batches.filter(die => die.status !== "untested").length;
      const row = { Wafer: wafer, Tested: tested, Passed: passed, Untested: batches.length - tested };
      if (!tested) return { ...row, "Yield (%)": null, "Wilson lower (%)": null, "Wilson upper (%)": null };
      const p = passed / tested, zSquared = 1.95996398454 ** 2;
      const divisor = 1 + zSquared / tested;
      const center = (p + zSquared / (2 * tested)) / divisor;
      const half = Math.sqrt(zSquared * (p * (1 - p) / tested + zSquared / (4 * tested ** 2))) / divisor;
      return { ...row, "Yield (%)": rounded(100 * p), "Wilson lower (%)": rounded(100 * Math.max(0, center - half)),
        "Wilson upper (%)": rounded(100 * Math.min(1, center + half)) };
    });
    return { metrics: { Wafers: rows.length, "Die records": dies.length }, rows };
  });

const health = define("Calculate aggregate incidence",
  "Use one pre-aggregated case count and denominator per reporting region. Counts from 1 through 9 are suppressed, including in exports.",
  object({ regions: records(object({ region: id, cases: count, population: count.min(1) })) }),
  { regions: [{ region: "Region A", cases: 120, population: 90000 }, { region: "Region B", cases: 4, population: 16000 }] },
  ({ regions }) => {
    requireDistinct(regions.map(row => row.region), "reporting region");
    const rows = regions.map(({ region, population, cases }) => {
      if (cases > population) throw new AnalysisError("A case count exceeds its denominator.");
      const suppress = cases > 0 && cases < 10;
      return { Region: region, Cases: suppress ? null : cases, Population: population,
        "Cases per 100,000": suppress ? null : rounded(100000 * cases / population), Status: suppress ? "Suppressed" : "Reportable" };
    });
    return { metrics: { Regions: rows.length, "Suppressed regions": rows.filter(row => row.Status === "Suppressed").length }, rows };
  });

const species = object({ coefficient: count.min(1).max(10000),
  atoms: z.record(z.string().regex(/^[A-Z][a-z]?$/), count.min(1).max(10000)).refine(x => Object.keys(x).length > 0, "Supply at least one element.") });
const chemistry = define("Verify elemental accounting",
  "Check conservation across an explicit materials ledger. Supply element counts per formula unit and known coefficients.",
  object({ inputs: z.array(species).min(1).max(100), outputs: z.array(species).min(1).max(100) }),
  { inputs: [{ coefficient: 1, atoms: { Ca: 1, C: 1, O: 3 } }],
    outputs: [{ coefficient: 1, atoms: { Ca: 1, O: 1 } }, { coefficient: 1, atoms: { C: 1, O: 2 } }] },
  ({ inputs, outputs }) => {
    const accumulate = (side: z.output<typeof species>[]) => {
      const totals = new Map<string, number>();
      for (const item of side) for (const [element, number] of Object.entries(item.atoms)) {
        totals.set(element, (totals.get(element) ?? 0) + item.coefficient * number);
      }
      return totals;
    };
    const before = accumulate(inputs), after = accumulate(outputs);
    const rows = Array.from(new Set([...before.keys(), ...after.keys()])).sort().map(element => ({
      Element: element, "Input atoms": before.get(element) ?? 0, "Output atoms": after.get(element) ?? 0,
      Difference: (after.get(element) ?? 0) - (before.get(element) ?? 0),
    }));
    return { metrics: { Elements: rows.length, Balance: rows.some(row => row.Difference) ? "Unbalanced" : "Conserved" }, rows };
  });

const pair = object({ at: utc, p10: magnitude, p50: magnitude, p90: magnitude });
const forecast = define("Evaluate forecast calibration",
  "Compare a single variable’s P10/P50/P90 forecasts against observations with matching UTC timestamps and units.",
  object({ unit: id, forecasts: records(pair), observations: records(object({ at: utc, value: magnitude })) }),
  { unit: "°C", forecasts: [{ at: "2026-01-02T10:00:00Z", p10: 8, p50: 10, p90: 12 },
    { at: "2026-01-02T11:00:00Z", p10: 8, p50: 10, p90: 12 }], observations: [
    { at: "2026-01-02T10:00:00Z", value: 11 }, { at: "2026-01-02T11:00:00Z", value: 13 }] },
  ({ unit, forecasts, observations }) => {
    requireDistinct(forecasts.map(row => String(Date.parse(row.at))), "forecast time");
    requireDistinct(observations.map(row => String(Date.parse(row.at))), "observation time");
    const observed = new Map(observations.map(row => [Date.parse(row.at), row.value]));
    const matched = forecasts.flatMap(row => {
      if (row.p10 > row.p50 || row.p50 > row.p90) throw new AnalysisError(`Quantiles cross at ${row.at}.`);
      const value = observed.get(Date.parse(row.at));
      return value === undefined ? [] : [{ ...row, value }];
    });
    if (!matched.length) throw new AnalysisError("No observation timestamp matches a forecast timestamp.");
    const levels = [["p10", 0.1], ["p50", 0.5], ["p90", 0.9]] as const;
    const rows = levels.map(([key, level]) => ({ Quantile: key.toUpperCase(),
      "Empirical CDF (%)": rounded(100 * matched.filter(row => row.value <= row[key]).length / matched.length),
      "Mean pinball loss": rounded(mean(matched.map(row => {
        const error = row.value - row[key];
        return error >= 0 ? level * error : (level - 1) * error;
      }))) }));
    return { metrics: { Unit: unit, Pairs: matched.length, "Unmatched forecasts": forecasts.length - matched.length,
      "P10–P90 coverage (%)": rounded(100 * matched.filter(row => row.value >= row.p10 && row.value <= row.p90).length / matched.length),
      "Median forecast bias": rounded(mean(matched.map(row => row.p50 - row.value))),
      "Median forecast MAE": rounded(mean(matched.map(row => Math.abs(row.p50 - row.value)))),
      "Mean interval width": rounded(mean(matched.map(row => row.p90 - row.p10))) }, rows };
  });

const rgba = z.string().min(8).max(350_000).regex(/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/);
export function comparePixels(before: Uint8Array, after: Uint8Array, width: number, height: number, tolerance: number) {
  if (before.length !== width * height * 4 || after.length !== before.length) {
    throw new AnalysisError("RGBA byte counts must match the image dimensions.");
  }
  let changed = 0, maximumDelta = 0;
  let left = width, top = height, right = -1, bottom = -1;
  for (let i = 0; i < before.length; i += 4) {
    const alpha = Math.abs(before[i + 3] - after[i + 3]);
    const channelDelta = (channel: number) => Math.abs(before[i + channel] * before[i + 3] - after[i + channel] * after[i + 3]) / 255;
    const delta = Math.max(alpha, channelDelta(0), channelDelta(1), channelDelta(2));
    maximumDelta = Math.max(delta, maximumDelta);
    if (delta <= tolerance) continue;
    changed++;
    const x = (i / 4) % width, y = Math.floor(i / 4 / width);
    left = Math.min(left, x); top = Math.min(top, y); right = Math.max(right, x); bottom = Math.max(bottom, y);
  }
  return { metrics: { Width: width, Height: height, "Changed pixels": changed,
    "Changed pixels (%)": rounded(100 * changed / (width * height)), "Maximum channel difference": rounded(maximumDelta),
    "Difference bounds (x, y, width, height)": changed ? `${left}, ${top}, ${right - left + 1}, ${bottom - top + 1}` : null } };
}

const image = define("Compare two screenshots",
  "Measure changed pixels and the difference bounds. Compare PNG, JPEG or WebP files locally, or supply base64 RGBA pixels.",
  object({ width: count.min(1).max(4096), height: count.min(1).max(4096), tolerance: count.max(255), baselineRgba: rgba, candidateRgba: rgba }),
  { width: 2, height: 1, tolerance: 0, baselineRgba: "AAAA//////8=", candidateRgba: "/wAA//////8=" },
  ({ width, height, tolerance, baselineRgba, candidateRgba }) => comparePixels(
    Uint8Array.from(atob(baselineRgba), char => char.charCodeAt(0)),
    Uint8Array.from(atob(candidateRgba), char => char.charCodeAt(0)), width, height, tolerance));

export const evidence = {
  "visual-regression-evaluator": image,
  "energy-grid-operations-platform": energy, "financial-risk-settlement-platform": settlement,
  "semiconductor-yield-timing-platform": yieldAnalysis, "public-health-surveillance-platform": health,
  "chemistry-materials-provenance-platform": chemistry, "atmospheric-calibrated-forecast-platform": forecast,
};
