import { z } from "zod";
import { AnalysisError } from "./analysis-core.ts";

const github = z.object({ workflow_runs: z.array(z.object({
  id: z.number().int().positive(), workflow_id: z.number().int().positive(),
  head_sha: z.string().regex(/^[a-f0-9]{40}$/i), head_branch: z.string().nullable(), event: z.string(),
  conclusion: z.string().nullable(),
})) });
const nws = z.object({ features: z.array(z.object({ properties: z.object({
  timestamp: z.iso.datetime({ offset: true }), temperature: z.object({ value: z.number().nullable(), unitCode: z.string() }),
}) })) });

async function providerJson(url: string, accept: string, fetcher: typeof fetch): Promise<unknown> {
  const response = await fetcher(url, {
    headers: { accept, "user-agent": "Quantura Research (hello@quantura.studio)",
      ...(url.startsWith("https://api.github.com/") ? { "x-github-api-version": "2026-03-10" } : {}) },
    redirect: "error", signal: AbortSignal.timeout(8000), next: { revalidate: 300 },
  } as RequestInit);
  if (!response.ok) {
    throw new AnalysisError(response.status === 404 ? "The public source could not be found." :
      response.status === 403 || response.status === 429 ? "The public provider denied the request or is rate limited." :
        "The public provider is temporarily unavailable.", response.status === 404 ? 404 :
      response.status === 403 || response.status === 429 ? 429 : 502);
  }
  const reader = response.body?.getReader();
  if (!reader) throw new AnalysisError("The provider returned an empty response.", 502);
  let received = 0;
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let text = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.length;
      if (received > 1024 * 1024) throw new AnalysisError("The provider response exceeds one MiB.", 502);
      text += decoder.decode(value, { stream: true });
    }
    return JSON.parse(text + decoder.decode());
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export const sourceGuides = {
  "flaky-test-forensics": { label: "Public GitHub repository (owner/repository)", placeholder: "actions/checkout", button: "Import GitHub Actions runs" },
  "atmospheric-calibrated-forecast-platform": { label: "US observation station ID", placeholder: "KJFK", button: "Import NWS temperatures" },
} as const;

export async function loadPublicSource(site: string, identifier: string, fetcher: typeof fetch = fetch) {
  if (site === "flaky-test-forensics") {
    if (!/^[a-zA-Z0-9][a-zA-Z0-9-]{0,38}\/[a-zA-Z0-9_.-]{1,100}$/.test(identifier) ||
        [".", ".."].includes(identifier.split("/")[1])) throw new AnalysisError("Enter a public repository as owner/repository.");
    const source = `https://api.github.com/repos/${identifier}/actions/runs?status=completed&per_page=50`;
    const result = github.parse(await providerJson(source, "application/vnd.github+json", fetcher));
    const runs = result.workflow_runs.filter(row => row.conclusion === "success" || row.conclusion === "failure").map(row => ({
      runId: String(row.id), check: String(row.workflow_id), revision: row.head_sha,
      context: `${row.event} / ${row.head_branch ?? "(no branch)"}`.slice(0, 120),
      outcome: row.conclusion === "success" ? "pass" : "fail",
    }));
    if (!runs.length) throw new AnalysisError("The public repository has no success or failure in its latest 50 completed runs.");
    return { source, data: { runs } };
  }
  if (site === "atmospheric-calibrated-forecast-platform") {
    if (!/^[A-Z0-9]{3,8}$/.test(identifier)) throw new AnalysisError("Enter a US station ID, such as KJFK.");
    const source = `https://api.weather.gov/stations/${identifier}/observations?limit=48`;
    const result = nws.parse(await providerJson(source, "application/geo+json", fetcher));
    const readings = new Map<string, number>();
    for (const { properties } of result.features) {
      if (properties.temperature.unitCode === "wmoUnit:degC" && properties.temperature.value !== null) {
        readings.set(new Date(properties.timestamp).toISOString(), properties.temperature.value);
      }
    }
    if (!readings.size) throw new AnalysisError("The station did not return recent Celsius readings.");
    return { source, data: { unit: "°C", observations: Array.from(readings, ([at, value]) => ({ at, value })) } };
  }
  throw new AnalysisError("This analysis has no public source importer.");
}
