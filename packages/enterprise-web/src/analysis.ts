import { z } from "zod";
import { AnalysisError, type AnalysisDefinition, type Findings } from "./analysis-core.ts";
import { comparePixels, evidence } from "./analysis-evidence.ts";
import { operations } from "./analysis-operations.ts";

export { AnalysisError, MAX_INPUT_BYTES, parseInput } from "./analysis-core.ts";
export { comparePixels };

const definitions: Record<string, AnalysisDefinition> = { ...operations, ...evidence };
export type AnalysisReport = Findings & {
  schemaVersion: "1.0";
  product: string;
  analysis: string;
  inputSource: "example" | "user_supplied" | "public_api";
  source?: string;
};

export function getAnalysis(siteId: string) {
  return Object.hasOwn(definitions, siteId) ? definitions[siteId] : undefined;
}

export function analysisGuide(siteId: string) {
  const definition = getAnalysis(siteId);
  if (!definition) return undefined;
  const { schema, title, description, example } = definition;
  return { title, description, example, schema: z.toJSONSchema(schema, { io: "input" }) };
}

export function runAnalysis(siteId: string, input: unknown,
  inputSource: AnalysisReport["inputSource"] = "user_supplied", source?: string): AnalysisReport {
  const definition = getAnalysis(siteId);
  if (!definition) throw new AnalysisError("This product has no standalone analyzer.");
  return { schemaVersion: "1.0", product: siteId, analysis: definition.title, inputSource,
    ...(source ? { source } : {}), ...definition.run(input) };
}
