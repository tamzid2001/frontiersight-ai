/* Guided first-run proof wizard — Upload Scene → Inspect Tracks →
   Change an Intervention → Review Proof.

   Pure state machine: no DOM, no fetch, no timers. The browser layer
   (app.js) feeds it REAL API responses; this module only decides what
   may advance, what each step is allowed to claim, and what an
   exported proof packet must contain.

   Honesty rules enforced here (they mirror the repository's trust rule):
     - a proof packet can never be produced without a recorded run AND a
       named human approval (export is locked otherwise);
     - every step carries an explicit provenance label — FIXTURE /
       USER_SCENE / ASSUMPTION / DETERMINISTIC — and a scene is never
       labelled MODEL_DERIVED by this wizard (no model call happens here);
     - occluded tracks are recorded as missing evidence, separate from
       numerical uncertainty;
     - the exported packet states that it is not a safety certification.

   ESM core: imported by tests/wizard.test.mjs under node --test and
   loaded in the browser via dynamic import (same pattern as
   scenery-core.mjs). */

const STEPS = ['upload', 'inspect', 'intervene', 'proof'];

const STEP_TITLES = {
  upload: 'Upload Scene',
  inspect: 'Inspect Tracks',
  intervene: 'Change an Intervention',
  proof: 'Review Proof',
};

const CATEGORIES = ['forklift', 'pedestrian', 'robot', 'vehicle', 'cyclist', 'shelf', 'object'];
const SOURCE_LABELS = { fixture: 'FIXTURE', workspace: 'USER_SCENE', upload: 'USER_SCENE' };
const MAX_OBJECTS = 24;
const NOT_A_CERTIFICATION =
  'Conditional prediction under declared assumptions. Not a safety certification.';

function fail(message, code) {
  const error = new Error(message);
  if (code) error.code = code;
  return error;
}

function validateTracks(tracks) {
  if (!Array.isArray(tracks) || !tracks.length) throw fail('Tracks are required to inspect.', 'TRACKS_REQUIRED');
  for (const track of tracks) {
    if (!track || typeof track.object_id !== 'string' || !track.object_id)
      throw fail('Every track needs an object id.', 'TRACK_ID');
    if (!Array.isArray(track.points) || !track.points.length)
      throw fail(`Track "${track.object_id}" has no positions.`, 'TRACK_POINTS');
    if (track.occluded !== undefined && !Array.isArray(track.occluded))
      throw fail(`Track "${track.object_id}" has malformed occlusion windows.`, 'TRACK_OCCLUSION');
  }
  return true;
}

/* Scene validation mirrors the ENGINE's accepted request shapes
   (services/api/server.py dispatches on scenario / scene / tracks):
     - a fixture scenario payload: {id (or scenario): "...", tracks: [...]};
     - a user-authored scene:     {stage_metres, objects};
     - raw sampled tracks:        {tracks: [...]}.
   The wizard only accepts what the deterministic pipeline accepts.
   Note the live /api/scenarios?name= payload identifies the fixture
   with `id`, while the counterfactual request body uses `scenario` —
   both keys are accepted here, with objects taking precedence. */
function validateScene(scene) {
  if (!scene || typeof scene !== 'object' || Array.isArray(scene))
    throw fail('A scene is required.', 'SCENE_REQUIRED');
  const scenarioId = typeof scene.scenario === 'string' ? scene.scenario
    : typeof scene.id === 'string' ? scene.id : null;
  if (Array.isArray(scene.objects)) {
    const stage = scene.stage_metres;
    if (!Array.isArray(stage) || stage.length !== 2 || !stage.every(v => Number.isFinite(v) && v >= 6 && v <= 60))
      throw fail('Scene stage must be two floor dimensions between 6 and 60 metres.', 'SCENE_STAGE');
    if (!scene.objects.length || scene.objects.length > MAX_OBJECTS)
      throw fail(`A scene needs 1–${MAX_OBJECTS} components.`, 'SCENE_OBJECTS');
    const seen = new Set();
    for (const object of scene.objects) {
      if (!object || typeof object !== 'object') throw fail('Each component must be an object.', 'SCENE_OBJECT');
      if (!CATEGORIES.includes(object.category)) throw fail(`Unsupported component category "${object.category}".`, 'SCENE_CATEGORY');
      const id = object.id ?? object.object_id;
      if (typeof id !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(id)) throw fail('Components require a stable alphanumeric id.', 'SCENE_ID');
      if (seen.has(id)) throw fail(`Duplicate component id "${id}".`, 'SCENE_ID_DUPLICATE');
      seen.add(id);
      const radius = object.radius ?? 0.5, speed = object.speed ?? 0, delay = object.delay ?? 0;
      if (![radius, speed, delay].every(Number.isFinite) || radius < 0 || speed < 0 || speed > 8 || delay < 0 || delay > 10)
        throw fail(`Component "${id}" has invalid radius/speed/delay settings.`, 'SCENE_MOTION');
      if (!Array.isArray(object.waypoints) || object.waypoints.length > 24)
        throw fail(`Component "${id}" needs at most 24 waypoints.`, 'SCENE_PATH');
    }
    return true;
  }
  if (scenarioId !== null) {
    if (!scenarioId.trim()) throw fail('The fixture scenario id is empty.', 'SCENE_ID');
    if (!Array.isArray(scene.tracks) || !scene.tracks.length)
      throw fail('A fixture scenario must carry the tracks it will analyse.', 'TRACKS_REQUIRED');
    validateTracks(scene.tracks);
    return true;
  }
  if (Array.isArray(scene.tracks)) { validateTracks(scene.tracks); return true; }
  throw fail('A scene needs a fixture id, components, or tracks.', 'SCENE_SHAPE');
}

function validateIntervention(intervention) {
  if (!intervention || typeof intervention !== 'object') throw fail('An intervention is required.', 'INTERVENTION_REQUIRED');
  if (typeof intervention.agent_id !== 'string' || !intervention.agent_id)
    throw fail('Pick which component receives the intervention.', 'INTERVENTION_AGENT');
  const speedRatio = Number(intervention.speed_ratio);
  if (!Number.isFinite(speedRatio) || speedRatio <= 0 || speedRatio > 1)
    throw fail('Speed reduction must be a ratio in (0, 1].', 'INTERVENTION_SPEED');
  const interventionTime = Number(intervention.intervention_time);
  if (!Number.isFinite(interventionTime) || interventionTime < 0)
    throw fail('Intervention time must be zero or later.', 'INTERVENTION_TIME');
  const deceleration = Number(intervention.deceleration);
  if (!Number.isFinite(deceleration) || deceleration < 0 || deceleration > 15)
    throw fail('Braking deceleration must be 0–15 m/s².', 'INTERVENTION_DECEL');
  return true;
}

function sceneShapeOf(scene) {
  if (Array.isArray(scene.objects)) return 'objects';
  if (typeof scene.scenario === 'string' || typeof scene.id === 'string') return 'scenario';
  return 'tracks';
}

function scenarioIdOf(scene) {
  return typeof scene.scenario === 'string' ? scene.scenario : scene.id;
}

function sceneTracksOf(scene) {
  if (Array.isArray(scene.tracks)) return scene.tracks;
  return [];
}

function createWizard(now) {
  const clock = typeof now === 'function' ? now : () => new Date().toISOString();
  let state = {
    step: STEPS[0],
    scene: null,
    sceneShape: null,
    sceneLabel: 'FIXTURE',
    tracks: null,
    occlusionSeconds: 0,
    intervention: null,
    run: null,
    approval: null,
    exported: false,
  };
  let log = [];

  function note(kind, message) { log.push({ kind, message, at: clock() }); }

  function stepIndex(step) { return STEPS.indexOf(step); }
  function requireStep(step, code, message) {
    if (state.step !== step) throw fail(message, code);
  }

  return {
    get step() { return state.step; },
    get steps() { return STEPS.slice(); },
    get progress() {
      return { index: stepIndex(state.step), total: STEPS.length, title: STEP_TITLES[state.step] };
    },
    get state() { return JSON.parse(JSON.stringify(state)); },
    get log() { return log.slice(); },

    /* Step 1 — Upload Scene. Accepts the same scene shapes the
       deterministic pipeline accepts; the source decides the badge. */
    submitScene(scene, options) {
      requireStep('upload', 'WRONG_STEP', 'Finish or restart the current step before uploading a scene.');
      validateScene(scene);
      const source = options && options.source ? options.source : 'fixture';
      if (!SOURCE_LABELS[source]) throw fail(`Unknown scene source "${source}".`, 'SCENE_SOURCE');
      state.scene = JSON.parse(JSON.stringify(scene));
      state.sceneShape = sceneShapeOf(scene);
      state.sceneLabel = SOURCE_LABELS[source];
      const described = state.sceneShape === 'scenario' ? `fixture "${scenarioIdOf(scene)}"`
        : state.sceneShape === 'objects' ? `${scene.objects.length} component(s) on a ${scene.stage_metres[0]} × ${scene.stage_metres[1]} m floor`
        : `${scene.tracks.length} sampled track(s)`;
      note('scene', `Scene accepted (${state.sceneShape}: ${described}), labelled ${state.sceneLabel}.`);
      return state.sceneLabel;
    },

    /* Step 2 — Inspect Tracks. Real sampled tracks only; occlusion
       windows are recorded as missing evidence, never as precision. */
    inspectTracks(tracks) {
      requireStep('inspect', 'WRONG_STEP', 'Upload a scene before inspecting tracks.');
      validateTracks(tracks);
      state.tracks = JSON.parse(JSON.stringify(tracks));
      state.occlusionSeconds = tracks.reduce((total, track) =>
        total + (track.occluded || []).reduce((sum, span) => sum + Math.max(0, (span[1] ?? 0) - (span[0] ?? 0)), 0), 0);
      note('tracks', `${tracks.length} track(s) inspected; ${state.occlusionSeconds.toFixed(2)} s of occlusion recorded as missing evidence.`);
      return { tracks: tracks.length, occlusionSeconds: state.occlusionSeconds };
    },

    /* Step 3 — Change an Intervention. User-declared hypothesis:
       labelled ASSUMPTION until the deterministic engine answers. */
    setIntervention(intervention) {
      requireStep('intervene', 'WRONG_STEP', 'Inspect tracks before changing an intervention.');
      validateIntervention(intervention);
      state.intervention = {
        agent_id: String(intervention.agent_id),
        speed_ratio: Number(intervention.speed_ratio),
        intervention_time: Number(intervention.intervention_time),
        deceleration: Number(intervention.deceleration),
        provenance: 'ASSUMPTION',
      };
      note('intervention', `Intervention declared for ${state.intervention.agent_id} (labelled ASSUMPTION until the deterministic run).`);
      return state.intervention;
    },

    /* Records the REAL deterministic engine response. The manifest
       hash is the replayable identity of this exact computation. A run
       cannot exist without a declared intervention — you cannot measure
       a change you never declared. */
    recordRun(run) {
      requireStep('intervene', 'WRONG_STEP', 'Declare an intervention before recording a run.');
      if (!state.intervention) throw fail('Declare an intervention before recording a run.', 'INTERVENTION_REQUIRED');
      if (!run || typeof run.manifest_hash !== 'string' || !run.manifest_hash)
        throw fail('A run must carry its deterministic manifest hash.', 'RUN_HASH');
      if (run.results === undefined || run.results === null || typeof run.results !== 'object')
        throw fail('A run must carry its results.', 'RUN_RESULTS');
      state.run = {
        run_id: typeof run.run_id === 'string' ? run.run_id : null,
        manifest_hash: run.manifest_hash,
        results: run.results,
        provenance: 'DETERMINISTIC',
      };
      note('run', `Deterministic run recorded (manifest ${run.manifest_hash.slice(0, 16)}…).`);
      return state.run;
    },

    /* Step 4 — human approval. Attributable: a name is mandatory and
       the approval timestamp comes from the caller (real clock). */
    approve(name, at) {
      requireStep('proof', 'WRONG_STEP', 'Record a run before approving evidence.');
      if (typeof name !== 'string' || !name.trim()) throw fail('Approval needs an attributable name.', 'APPROVAL_NAME');
      if (typeof at !== 'string' || !at) throw fail('Approval needs a timestamp.', 'APPROVAL_TIME');
      state.approval = { by: name.trim(), at };
      note('approval', `Evidence approved by ${state.approval.by} at ${state.approval.at}.`);
      return state.approval;
    },

    canAdvance() {
      if (state.step === 'upload') return Boolean(state.scene);
      if (state.step === 'inspect') return Boolean(state.tracks);
      if (state.step === 'intervene') return Boolean(state.intervention && state.run);
      return false;
    },

    advance() {
      if (!this.canAdvance()) throw fail('This step is not complete yet.', 'STEP_INCOMPLETE');
      if (state.step === STEPS[STEPS.length - 1]) throw fail('The wizard is already complete.', 'WIZARD_DONE');
      state.step = STEPS[stepIndex(state.step) + 1];
      note('wizard', `Advanced to ${STEP_TITLES[state.step]}.`);
      return state.step;
    },

    back() {
      const index = stepIndex(state.step);
      if (index <= 0) throw fail('Already at the first step.', 'WIZARD_START');
      state.step = STEPS[index - 1];
      note('wizard', `Returned to ${STEP_TITLES[state.step]}.`);
      return state.step;
    },

    /* Export stays LOCKED without a named approval — the same rule the
       studio applies to evidence packets. */
    exportProof() {
      requireStep('proof', 'WRONG_STEP', 'Complete the wizard before exporting proof.');
      if (!state.run) throw fail('No deterministic run recorded — nothing to export.', 'EXPORT_NO_RUN');
      if (!state.approval) throw fail('Export is locked until a named human approves the evidence.', 'EXPORT_LOCKED');
      if (state.exported) throw fail('This proof packet was already exported; restart for a new one.', 'EXPORT_ONCE');
      state.exported = true;
      const scene = state.scene;
      const packet = {
        schema: 'frontiersight.guided-proof/1',
        generated_at: clock(),
        scene: {
          provenance: state.sceneLabel,
          shape: state.sceneShape,
          ...(state.sceneShape === 'scenario' ? {scenario: scenarioIdOf(scene)} : {}),
          ...(state.sceneShape === 'objects' ? {stage_metres: scene.stage_metres, components: scene.objects.length} : {}),
          ...(state.sceneShape === 'tracks' ? {tracks: scene.tracks.length} : {}),
        },
        tracks: {
          inspected: state.tracks.length,
          occlusion_seconds: Number(state.occlusionSeconds.toFixed(3)),
          occlusion_label: 'missing evidence — separate from numerical uncertainty',
        },
        intervention: { ...state.intervention },
        run: { run_id: state.run.run_id, manifest_hash: state.run.manifest_hash, provenance: state.run.provenance },
        approval: { by: state.approval.by, at: state.approval.at },
        disclaimers: [NOT_A_CERTIFICATION],
      };
      note('export', 'Proof packet exported (approval-bound).');
      return packet;
    },

    reset() {
      state = {
        step: STEPS[0], scene: null, sceneShape: null, sceneLabel: 'FIXTURE', tracks: null, occlusionSeconds: 0,
        intervention: null, run: null, approval: null, exported: false,
      };
      log = [];
      note('wizard', 'Wizard reset.');
      return state.step;
    },
  };
}

export { STEPS, STEP_TITLES, createWizard, validateScene, validateTracks, validateIntervention, NOT_A_CERTIFICATION };
