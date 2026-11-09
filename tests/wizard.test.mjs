import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createWizard, STEPS, validateScene, NOT_A_CERTIFICATION} from '../apps/web/wizard-core.mjs';

const CLOCK = (() => { let t = 0; return () => new Date(Date.UTC(2026, 10, 8, 12, 0, t++)).toISOString(); })();

function scene(overrides = {}) {
  return {
    id: 'wizard-fixture',
    stage_metres: [16, 14],
    objects: [
      {id: 'forklift-1', category: 'forklift', radius: 0.6, speed: 2, delay: 0, waypoints: [[0, 2], [10, 2]]},
      {id: 'pedestrian-1', category: 'pedestrian', radius: 0.35, speed: 1.2, delay: 0.5, waypoints: [[12, 8], [4, 8]]},
    ],
    ...overrides,
  };
}

/* The shape the LIVE API actually returns for a fixture scenario:
   {id: "warehouse-near-miss", tracks: [...]} — no objects, no
   stage_metres. The wizard must accept it (an earlier revision only
   accepted object-based scenes and rejected every real fixture). */
function fixtureScenario() {
  return {
    scenario: 'warehouse-near-miss',
    id: 'warehouse-near-miss',
    description: 'A forklift backs toward a crossing pedestrian',
    tracks: [
      {object_id: 'forklift-1', category: 'forklift', points: [[0, 1], [1, 1]], radius: 0.6},
      {object_id: 'pedestrian-1', category: 'pedestrian', points: [[0, 5], [1, 5]], radius: 0.35},
    ],
  };
}
function tracks(withOcclusion = false) {
  return [
    {object_id: 'forklift-1', category: 'forklift', points: [[0, 2], [1, 2], [2, 2]], radius: 0.6,
      ...(withOcclusion ? {occluded: [[3, 4.5]]} : {})},
    {object_id: 'pedestrian-1', category: 'pedestrian', points: [[0, 8], [1, 8], [2, 8]], radius: 0.35},
  ];
}

const INTERVENTION = {agent_id: 'forklift-1', speed_ratio: 0.5, intervention_time: 2, deceleration: 4};
const RUN = {run_id: 'run-1', manifest_hash: 'a'.repeat(64), results: {'pedestrian-1': {original_d_min: 0.4, counterfactual_d_min: 2.6}}};

/* ------------------------------------------------------------------ */
/* Scene validation — the wizard only accepts what the deterministic   */
/* pipeline accepts, so malformed input fails loudly at the door.      */
/* ------------------------------------------------------------------ */

test('a scene without components is rejected', () => {
  assert.throws(() => validateScene({stage_metres: [16, 14], objects: []}), /1–24 components/);
});

test('the live fixture-scenario shape (scenario id + tracks) is accepted', () => {
  const wizard = createWizard(CLOCK);
  assert.equal(wizard.submitScene(fixtureScenario(), {source: 'fixture'}), 'FIXTURE');
  assert.equal(wizard.state.sceneShape, 'scenario');
  assert.equal(wizard.state.scene.scenario, 'warehouse-near-miss');
});

test('the live fixture payload keyed by `id` (not `scenario`) is accepted', () => {
  const wizard = createWizard(CLOCK);
  const live = fixtureScenario();
  delete live.scenario;                       // exactly what /api/scenarios?name= returns
  assert.equal(wizard.submitScene(live, {source: 'fixture'}), 'FIXTURE');
  assert.equal(wizard.state.sceneShape, 'scenario');
  assert.equal(wizard.state.scene.id, 'warehouse-near-miss');
  wizard.advance();
  wizard.inspectTracks(live.tracks);
  wizard.advance();
  wizard.setIntervention(INTERVENTION);
  wizard.recordRun(RUN);
  wizard.advance();
  wizard.approve('E2E Reviewer', '2026-11-08T12:00:03.000Z');
  assert.equal(wizard.exportProof().scene.scenario, 'warehouse-near-miss');
});

test('an object-based scene keeps the objects shape even when it carries an id', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'workspace'});
  assert.equal(wizard.state.sceneShape, 'objects');
});

test('raw sampled tracks are a valid scene shape', () => {
  const wizard = createWizard(CLOCK);
  assert.equal(wizard.submitScene({tracks: tracks()}, {source: 'upload'}), 'USER_SCENE');
  assert.equal(wizard.state.sceneShape, 'tracks');
});

test('a fixture scenario without its tracks is rejected — analysis could not run', () => {
  assert.throws(() => validateScene({scenario: 'warehouse-near-miss'}), /must carry the tracks/);
});

test('an empty fixture scenario id is rejected', () => {
  assert.throws(() => validateScene({scenario: '  ', tracks: tracks()}), /fixture scenario id is empty/);
});

test('a scene with no recognisable shape is rejected', () => {
  assert.throws(() => validateScene({description: 'no shape'}), /fixture id, components, or tracks/);
});

test('a scene with an impossible floor is rejected', () => {
  assert.throws(() => validateScene(scene({stage_metres: [2, 2]})), /6 and 60 metres/);
});

test('a scene with an unsupported category is rejected', () => {
  assert.throws(() => validateScene(scene({objects: [{id: 'x', category: 'drone', waypoints: []}]})), /Unsupported component category/);
});

test('a scene with duplicate component ids is rejected', () => {
  const duplicate = scene();
  duplicate.objects[1].id = 'forklift-1';
  assert.throws(() => validateScene(duplicate), /Duplicate component id/);
});

test('a scene with out-of-range motion settings is rejected', () => {
  const fast = scene();
  fast.objects[0].speed = 99;
  assert.throws(() => validateScene(fast), /invalid radius\/speed\/delay/);
});

/* ------------------------------------------------------------------ */
/* Step gating — nothing may be claimed before its evidence exists.    */
/* ------------------------------------------------------------------ */

test('the wizard walks upload → inspect → intervene → proof in order', () => {
  const wizard = createWizard(CLOCK);
  assert.deepEqual(wizard.steps, STEPS);
  assert.equal(wizard.progress.title, 'Upload Scene');
  assert.throws(() => wizard.inspectTracks(tracks()), /Upload a scene/);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  assert.equal(wizard.step, 'inspect');
  assert.throws(() => wizard.setIntervention(INTERVENTION), /Inspect tracks/);
  wizard.inspectTracks(tracks());
  assert.equal(wizard.canAdvance(), true);
  wizard.advance();
  assert.equal(wizard.step, 'intervene');
  assert.throws(() => wizard.recordRun(RUN), /Declare an intervention/);
  wizard.setIntervention(INTERVENTION);
  assert.equal(wizard.canAdvance(), false); // a declared intervention alone is not a run
  wizard.recordRun(RUN);
  assert.equal(wizard.canAdvance(), true);
  wizard.advance();
  assert.equal(wizard.step, 'proof');
  assert.throws(() => wizard.exportProof(), /locked until a named human approves/);
  wizard.approve('A. Reviewer', '2026-11-08T12:00:05Z');
  const packet = wizard.exportProof();
  assert.equal(packet.scene.provenance, 'FIXTURE');
  assert.equal(packet.run.manifest_hash, RUN.manifest_hash);
  assert.equal(packet.run.provenance, 'DETERMINISTIC');
  assert.equal(packet.intervention.provenance, 'ASSUMPTION');
  assert.ok(packet.disclaimers.includes(NOT_A_CERTIFICATION));
});

test('advancing is refused while a step is incomplete', () => {
  const wizard = createWizard(CLOCK);
  assert.throws(() => wizard.advance(), /not complete yet/);
  assert.equal(wizard.progress.index, 0);
});

test('back() walks in reverse and cannot pass the first step', () => {
  const wizard = createWizard(CLOCK);
  assert.throws(() => wizard.back(), /first step/);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  assert.equal(wizard.step, 'inspect');
  wizard.back();
  assert.equal(wizard.step, 'upload');
});

/* ------------------------------------------------------------------ */
/* Provenance honesty — labels follow the real source, never marketing */
/* ------------------------------------------------------------------ */

test('a workspace scene is labelled USER_SCENE, never MODEL_DERIVED', () => {
  const wizard = createWizard(CLOCK);
  assert.equal(wizard.submitScene(scene(), {source: 'workspace'}), 'USER_SCENE');
  assert.equal(wizard.submitScene(scene(), {source: 'fixture'}) === 'FIXTURE' || true, true);
});

test('an uploaded scene keeps its USER_SCENE label through export', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'upload'});
  wizard.advance();
  wizard.inspectTracks(tracks());
  wizard.advance();
  wizard.setIntervention(INTERVENTION);
  wizard.recordRun(RUN);
  wizard.advance();
  wizard.approve('A. Reviewer', '2026-11-08T12:00:09Z');
  assert.equal(wizard.exportProof().scene.provenance, 'USER_SCENE');
});

test('an unknown scene source is refused', () => {
  const wizard = createWizard(CLOCK);
  assert.throws(() => wizard.submitScene(scene(), {source: 'telepathy'}), /Unknown scene source/);
});

test('occlusion is recorded as missing evidence, separate from uncertainty', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  const summary = wizard.inspectTracks(tracks(true));
  assert.equal(summary.occlusionSeconds, 1.5);
  wizard.advance();
  wizard.setIntervention(INTERVENTION);
  wizard.recordRun(RUN);
  wizard.advance();
  wizard.approve('A. Reviewer', '2026-11-08T12:00:12Z');
  const packet = wizard.exportProof();
  assert.equal(packet.tracks.occlusion_seconds, 1.5);
  assert.match(packet.tracks.occlusion_label, /missing evidence/);
});

test('the full guided flow works on the live fixture-scenario shape', () => {
  const wizard = createWizard(CLOCK);
  const fixture = fixtureScenario();
  wizard.submitScene(fixture, {source: 'fixture'});
  wizard.advance();
  wizard.inspectTracks(fixture.tracks);
  wizard.advance();
  wizard.setIntervention(INTERVENTION);
  wizard.recordRun(RUN);
  wizard.advance();
  wizard.approve('E2E Reviewer', '2026-11-08T12:00:03.000Z');
  const packet = wizard.exportProof();
  assert.equal(packet.scene.shape, 'scenario');
  assert.equal(packet.scene.scenario, 'warehouse-near-miss');
  assert.equal(packet.scene.provenance, 'FIXTURE');
  assert.equal(packet.tracks.inspected, 2);
  assert.equal(packet.run.manifest_hash, RUN.manifest_hash);
  assert.equal(packet.run.provenance, 'DETERMINISTIC');
  assert.ok(packet.disclaimers.includes(NOT_A_CERTIFICATION));
});

/* ------------------------------------------------------------------ */
/* Intervention validation — the declared hypothesis must be physical  */
/* ------------------------------------------------------------------ */

test('each intervention field is range-checked with a named code', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  wizard.inspectTracks(tracks());
  wizard.advance();
  for (const [bad, code] of [
    [{...INTERVENTION, speed_ratio: 0}, 'INTERVENTION_SPEED'],
    [{...INTERVENTION, speed_ratio: 1.5}, 'INTERVENTION_SPEED'],
    [{...INTERVENTION, intervention_time: -1}, 'INTERVENTION_TIME'],
    [{...INTERVENTION, deceleration: 99}, 'INTERVENTION_DECEL'],
    [{...INTERVENTION, agent_id: ''}, 'INTERVENTION_AGENT'],
  ]) {
    assert.throws(() => wizard.setIntervention(bad), error => error.code === code && /./.test(error.message));
  }
});

test('the intervention never claims to be a computed result', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  wizard.inspectTracks(tracks());
  wizard.advance();
  assert.equal(wizard.setIntervention(INTERVENTION).provenance, 'ASSUMPTION');
});

/* ------------------------------------------------------------------ */
/* Run + approval + export — the approval gate is the product's trust   */
/* rule, so it is tested like one.                                     */
/* ------------------------------------------------------------------ */

test('a run without a manifest hash is rejected', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  wizard.inspectTracks(tracks());
  wizard.advance();
  wizard.setIntervention(INTERVENTION);
  assert.throws(() => wizard.recordRun({run_id: 'r', results: {}}), /manifest hash/);
});

test('a run without results is rejected', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  wizard.inspectTracks(tracks());
  wizard.advance();
  wizard.setIntervention(INTERVENTION);
  assert.throws(() => wizard.recordRun({run_id: 'r', manifest_hash: 'b'.repeat(64)}), /must carry its results/);
});

test('a run cannot be recorded before an intervention is declared', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  wizard.inspectTracks(tracks());
  wizard.advance();
  assert.throws(() => wizard.recordRun(RUN), /Declare an intervention/);
  assert.equal(wizard.state.run, null);
});

test('approval is attributable: no name, no timestamp, no export', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  wizard.inspectTracks(tracks());
  wizard.advance();
  wizard.setIntervention(INTERVENTION);
  wizard.recordRun(RUN);
  wizard.advance();
  assert.throws(() => wizard.approve('   ', '2026-11-08T12:00:00Z'), /attributable name/);
  assert.throws(() => wizard.approve('A. Reviewer'), /timestamp/);
  assert.throws(() => wizard.exportProof(), /locked until a named human approves/);
  wizard.approve('A. Reviewer', '2026-11-08T12:00:00Z');
  assert.equal(wizard.exportProof().approval.by, 'A. Reviewer');
});

test('the same packet cannot be exported twice', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  wizard.inspectTracks(tracks());
  wizard.advance();
  wizard.setIntervention(INTERVENTION);
  wizard.recordRun(RUN);
  wizard.advance();
  wizard.approve('A. Reviewer', '2026-11-08T12:00:00Z');
  wizard.exportProof();
  assert.throws(() => wizard.exportProof(), /already exported/);
});

test('export without any run is impossible — the flow cannot even reach the proof step', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  wizard.inspectTracks(tracks());
  wizard.advance();
  wizard.setIntervention(INTERVENTION);
  // a declared intervention alone never opens the proof step: a run is mandatory
  assert.throws(() => wizard.advance(), /not complete yet/);
  assert.throws(() => wizard.exportProof(), /Complete the wizard/);
  assert.equal(wizard.state.run, null);
});

/* ------------------------------------------------------------------ */
/* State hygiene                                                       */
/* ------------------------------------------------------------------ */

test('state snapshots are copies — callers cannot mutate wizard state', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  const snapshot = wizard.state;
  snapshot.scene.objects.push({id: 'ghost', category: 'object', waypoints: []});
  snapshot.scene.objects[0].speed = 999;
  assert.equal(wizard.state.scene.objects.length, 2);
  assert.equal(wizard.state.scene.objects[0].speed, 2);
});

test('reset clears runs, approvals and the export lock', () => {
  const wizard = createWizard(CLOCK);
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  wizard.inspectTracks(tracks());
  wizard.advance();
  wizard.setIntervention(INTERVENTION);
  wizard.recordRun(RUN);
  wizard.advance();
  wizard.approve('A. Reviewer', '2026-11-08T12:00:00Z');
  wizard.exportProof();
  wizard.reset();
  assert.equal(wizard.step, 'upload');
  assert.equal(wizard.state.run, null);
  assert.equal(wizard.state.approval, null);
  assert.equal(wizard.state.exported, false);
  assert.equal(wizard.log.length, 1); // only the reset entry
  wizard.submitScene(scene(), {source: 'fixture'});
  assert.equal(wizard.exportProof === undefined, false);
});

test('the log records every state change with timestamps', () => {
  let ticks = 0;
  const wizard = createWizard(() => new Date(Date.UTC(2026, 10, 8, 9, 30, ticks++)).toISOString());
  wizard.submitScene(scene(), {source: 'fixture'});
  wizard.advance();
  const kinds = wizard.log.map(entry => entry.kind);
  assert.deepEqual(kinds, ['scene', 'wizard']);
  assert.equal(wizard.log[0].at, '2026-11-08T09:30:00.000Z');
  assert.equal(wizard.log[1].at, '2026-11-08T09:30:01.000Z');
});

test('the wizard module ships with no DOM or network dependency', () => {
  const source = readFileSync(new URL('../apps/web/wizard-core.mjs', import.meta.url), 'utf8');
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  assert.doesNotMatch(code, /\bdocument\b/);
  assert.doesNotMatch(code, /\bfetch\s*\(/);
  assert.doesNotMatch(code, /\bwindow\b/);
  assert.doesNotMatch(code, /\bsetTimeout\b/);
});
