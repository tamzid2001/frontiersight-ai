export type DemoValue = string | number | boolean | null
export type DemoFields = Readonly<Record<string, DemoValue>>
export type DemoSnapshot = {
  inputs: DemoFields
  results: DemoFields
}

export function captureDemo(snapshot: DemoSnapshot): DemoSnapshot {
  const clean = (fields: DemoFields): DemoFields => {
    const entries = Object.entries(fields)
    if (entries.length > 32) throw new RangeError('The demo report has too many fields.')
    return Object.fromEntries(entries.map(([name, value]) => {
      if (!name.trim() || name.length > 100) throw new TypeError('Invalid demo field label.')
      if (typeof value === 'number' && !Number.isFinite(value)) throw new TypeError('Invalid demo number.')
      if (typeof value === 'string' && value.length > 4000) throw new RangeError('A demo field is too long.')
      if (value !== null && !['string','number','boolean'].includes(typeof value)) throw new TypeError('Invalid demo value.')
      return [name, value]
    }))
  }
  return {inputs: clean(snapshot.inputs), results: clean(snapshot.results)}
}

export function compareDemo(baseline: DemoSnapshot, current: DemoSnapshot) {
  const rows = (before: DemoFields, after: DemoFields) =>
    [...new Set([...Object.keys(before), ...Object.keys(after)])].map(field => ({
      field,
      baseline: before[field] ?? null,
      current: after[field] ?? null,
      changed: !Object.is(before[field] ?? null, after[field] ?? null),
    }))
  return {inputs: rows(baseline.inputs, current.inputs), results: rows(baseline.results, current.results)}
}

export function demoReport(scenario: string, current: DemoSnapshot, baseline: DemoSnapshot | null, now = new Date()) {
  return {
    schema_version: 1,
    provenance: 'illustrative_demo',
    scenario,
    generated_at: now.toISOString(),
    baseline: baseline ? captureDemo(baseline) : null,
    current: captureDemo(current),
  }
}
