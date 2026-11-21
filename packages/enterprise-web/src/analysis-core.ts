import { z } from "zod";

export type Cell = string | number | null;
export type Findings = { metrics: Record<string, Cell>; rows?: Record<string, Cell>[] };
export const MAX_INPUT_BYTES = 512 * 1024;
export const id = z.string().trim().min(1).max(120);
export const count = z.number().int().min(0).max(1_000_000_000);
export const magnitude = z.number().min(-1e9).max(1e9);
export const nonnegative = magnitude.min(0);
export const probability = z.number().min(0).max(1);
export const utc = z.iso.datetime();
export const records = <T extends z.ZodType>(schema: T) => z.array(schema).min(1).max(2000);
export const object = z.strictObject;
export const mean = (xs: number[]) => xs.reduce((sum, x) => sum + x, 0) / xs.length;
export const rounded = (x: number) => Number(x.toPrecision(10));
export const percentile = (xs: number[], p: number) => xs.slice().sort((a, b) => a - b)[Math.ceil(xs.length * p) - 1];

export class AnalysisError extends Error {
  readonly status: number;

  constructor(message: string, status = 400) {
    super(message);
    this.status = status;
  }
}

export interface AnalysisDefinition {
  title: string;
  description: string;
  example: Record<string, unknown>;
  schema: z.ZodType;
  run: (input: unknown) => Findings;
}

export function define<T extends z.ZodType<Record<string, unknown>>>(
  title: string, description: string, schema: T, example: z.input<T>,
  compute: (input: z.output<T>) => Findings,
): AnalysisDefinition {
  return {
    title, description, example: example as Record<string, unknown>, schema,
    run(input) {
      const parsed = schema.safeParse(input);
      if (!parsed.success) {
        throw new AnalysisError(parsed.error.issues.slice(0, 5).map(issue =>
          `${issue.path.join(".") || "Input"} — ${issue.message}`).join("; "));
      }
      return compute(parsed.data);
    },
  };
}

export function group<T, K>(rows: T[], key: (row: T) => K): Map<K, T[]> {
  const groups = new Map<K, T[]>();
  for (const row of rows) {
    const k = key(row);
    const bucket = groups.get(k);
    if (bucket) bucket.push(row);
    else groups.set(k, [row]);
  }
  return groups;
}

export function requireDistinct(values: string[], label: string) {
  if (new Set(values).size !== values.length) throw new AnalysisError(`Duplicate ${label}.`);
}

export function parseInput(text: string): unknown {
  if (new TextEncoder().encode(text).length > MAX_INPUT_BYTES) {
    throw new AnalysisError("JSON exceeds the 512 KiB input limit.");
  }
  try {
    return JSON.parse(text.replace(/^\uFEFF/, ""));
  } catch {
    throw new AnalysisError("Enter a valid JSON object. Load the example to see the required fields.");
  }
}

export function criticalPath(tasks: { id: string; durationMs: number; dependencies: string[] }[]) {
  requireDistinct(tasks.map(t => t.id), "task ID");
  const states = new Map(tasks.map(task => [task.id, { task, waiting: new Set(task.dependencies),
    downstream: [] as string[], start: 0, predecessor: null as string | null }]));
  const queue: string[] = [];
  for (const [key, state] of states) {
    if (!state.waiting.size) queue.push(key);
    for (const dep of state.waiting) {
      const parent = states.get(dep);
      if (!parent) throw new AnalysisError(`Task ${key} references unknown dependency ${dep}.`);
      parent.downstream.push(key);
    }
  }
  let endpoint: string | null = null;
  let duration = -1;
  const rows: Record<string, Cell>[] = [];
  for (const key of queue) {
    const state = states.get(key)!;
    const finish = state.start + state.task.durationMs;
    rows.push({ Task: key, "Earliest start (ms)": state.start, "Earliest finish (ms)": finish });
    if (finish >= duration) {
      endpoint = key;
      duration = finish;
    }
    for (const next of state.downstream) {
      const child = states.get(next)!;
      if (child.predecessor === null || finish > child.start) {
        child.start = finish;
        child.predecessor = key;
      }
      child.waiting.delete(key);
      if (!child.waiting.size) queue.push(next);
    }
  }
  if (queue.length !== tasks.length) throw new AnalysisError("Dependencies contain a cycle.");
  const path = [];
  while (endpoint !== null) {
    path.push(endpoint);
    endpoint = states.get(endpoint)!.predecessor;
  }
  return { metrics: { Tasks: tasks.length, "Critical path (ms)": duration, "Path": path.reverse().join(" → ") }, rows };
}
