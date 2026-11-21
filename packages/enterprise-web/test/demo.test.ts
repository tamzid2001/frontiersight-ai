import assert from 'node:assert/strict'
import test from 'node:test'
import { captureDemo, compareDemo, demoReport, type DemoSnapshot } from '../src/demo.ts'

const baseline = {inputs:{rate:0,enabled:false},results:{outcome:'hold',details:null}}
const next = {inputs:{rate:7,enabled:true},results:{outcome:'go',note:'example'}}

test('captures independent snapshots and exports a versioned pair', () => {
  const source = {inputs:{rate:0},results:{outcome:'hold'}}
  const capture = captureDemo(source)
  source.inputs.rate = 10
  assert.equal(capture.inputs.rate,0)
  const now = new Date('2026-11-21T12:00:00Z')
  const report = demoReport('test-scenario',next,baseline,now)
  assert.deepEqual(report,{schema_version:1,provenance:'illustrative_demo',scenario:'test-scenario',generated_at:now.toISOString(),baseline,current:next})
  assert.equal(demoReport('test-scenario',next,null,now).baseline,null)
})

test('checks invalid and oversized report values without coercion', () => {
  const invalid = [NaN,Infinity,{},'x'.repeat(4001),undefined]
  for (const value of invalid) assert.throws(() => captureDemo({inputs:{value},results:{}} as DemoSnapshot))
  assert.throws(() => captureDemo({inputs:{'':0},results:{}}))
  assert.throws(() => captureDemo({inputs:{['x'.repeat(101)]:0},results:{}}))
  assert.throws(() => captureDemo({inputs:Object.fromEntries(Array.from({length:33},(_,i)=>[String(i),i])),results:{}}))
})

test('compares changed and missing fields and preserves false and zero', () => {
  const diff = compareDemo(baseline,next)
  assert.deepEqual(diff.inputs[0],{field:'rate',baseline:0,current:7,changed:true})
  assert.deepEqual(diff.inputs[1],{field:'enabled',baseline:false,current:true,changed:true})
  assert.deepEqual(diff.results[1],{field:'details',baseline:null,current:null,changed:false})
  assert.deepEqual(diff.results[2],{field:'note',baseline:null,current:'example',changed:true})
})
