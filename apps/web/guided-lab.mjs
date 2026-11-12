import {editor} from './lab-store-core.mjs';
import {guideState, importDocument} from './guided-lab-core.mjs';

const $ = id => document.getElementById(id);
let phase = 'input', exporting = false;
const labels = {input: 'Choose an input', inspect: 'Inspect and compare', proof: 'Review proof'};

function announce(message, error = false) {
  $('guide-status').textContent = message;
  $('guide-status').classList.toggle('error', error);
}
function showPhase(next, focus = true) {
  phase = next;
  for (const node of document.querySelectorAll('[data-guide-step]')) {
    const selected = node.dataset.guideStep === phase;
    if (selected) node.setAttribute('aria-current', 'step');
    else node.removeAttribute('aria-current');
  }
  for (const node of document.querySelectorAll('[data-guide-pane]'))
    node.hidden = node.dataset.guidePane !== phase;
  $('guide-phase-title').textContent = labels[phase];
  if (focus) $('guide-phase-title').focus({preventScroll: true});
  refresh();
}
function refresh() {
  const state = guideState(editor.read(), editor.result, editor.comparison);
  $('guide-source').textContent = state.source;
  $('guide-coordinates').textContent = state.coordinates;
  $('guide-observations').textContent = state.observationReferences
    ? `${state.observationReferences} observation references · pixel depth remains unavailable without calibration`
    : 'No measured video observations in this scene';
  $('guide-object-count').textContent = `${state.objects} modeled components`;
  $('guide-inspect').disabled = !state.loaded;
  $('guide-review').disabled = !state.computed;
  $('guide-evidence').disabled = !state.computed || exporting;
  $('guide-earlier').disabled = !editor.read().scene?.objects.some(object => object.joint?.type === 'prismatic_z');
  $('guide-proof-state').textContent = state.compared
    ? 'Baseline and alternative recomputed from this revision.'
    : state.computed ? 'Current scene computed. No counterfactual comparison has been computed for this revision.'
    : 'Run the current scene to compute evidence. Previous results are invalid after an edit.';
  const list = $('guide-history');
  list.replaceChildren(...editor.history.slice(-6).map(entry => {
    const item = document.createElement('li');
    item.textContent = `${entry.label} · ${entry.provenance}`; return item;
  }));
  if (!list.children.length) {
    const item = document.createElement('li'); item.textContent = 'No scene edits recorded.'; list.append(item);
  }
}
async function task(work) {
  const controls = [...document.querySelectorAll('[data-guide-action]')];
  controls.forEach(control => control.disabled = true);
  $('guide-content').setAttribute('aria-busy', 'true');
  try { await work(); }
  catch (error) { announce(error.message, true); }
  finally {
    controls.forEach(control => control.disabled = false);
    $('guide-content').removeAttribute('aria-busy'); refresh();
  }
}
function download(value, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function installGuidedLab() {
  for (const button of document.querySelectorAll('[data-guide-step]'))
    button.onclick = () => showPhase(button.dataset.guideStep);
  $('guide-inspect').onclick = () => showPhase('inspect');
  $('guide-review').onclick = () => showPhase('proof');
  $('guide-sample').onclick = () => task(async () => {
    await window.ensurePhysical();
    const ticket = editor.ticket();
    const response = await fetch('/api/v2/scenes/demo', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({demo: 'warehouse'}),
      signal: AbortSignal.timeout(10000)});
    if (!response.ok) throw Error('Sample unavailable. Retry when the local API is running.');
    const {scene} = await response.json();
    if (!editor.current(ticket)) throw Error('Workspace changed while loading the sample. Select it again.');
    await window.frontierPhysical.load(scene);
    if (!editor.result) throw Error('The sample could not be computed; inspect the simulation status.');
    announce('Synthetic warehouse loaded. No video, model or hardware call occurred.'); showPhase('inspect');
  });
  $('guide-file').onchange = () => task(async () => {
    const file = $('guide-file').files[0]; if (!file) return;
    if (file.size > 512 * 1024) throw Error('Scene imports are limited to 512 KiB. Video belongs in Video & observations.');
    const ticket = editor.ticket();
    const input = importDocument(JSON.parse(await file.text()));
    await window.ensurePhysical(); await window.frontierPhysical.validate(input.scene);
    if (!editor.current(ticket)) throw Error('Scene changed during import; choose the file again to replace it.');
    if (input.kind === 'project') {
      editor.recover(input.recovery); editor.lockBaseline(); await window.frontierPhysical.run();
    } else await window.frontierPhysical.load(input.scene);
    if (!editor.result) throw Error('Imported scene was not computed; inspect the simulation status.');
    announce('Validated scene loaded. Source provenance and assumptions are preserved.'); showPhase('inspect');
  });
  $('guide-earlier').onclick = () => task(async () => {
    const scene = editor.read().scene;
    const forks = scene.objects.find(object => object.joint?.type === 'prismatic_z');
    if (!forks) throw Error('This example requires a declared prismatic lift joint. Use the inspector for other scenes.');
    if (!editor.baseline) editor.lockBaseline();
    forks.joint.start_s = Math.max(0, forks.joint.start_s - 2);
    forks.provenance = 'ASSUMPTION';
    await window.frontierPhysical.apply(scene, 'Start the declared lift two seconds earlier');
    await window.frontierPhysical.compare();
    if (!editor.comparison) throw Error('Comparison unavailable for the current revision.');
    announce('Lift timing changed and both scenes recomputed. Review actual contacts and clearance below.');
    showPhase('proof');
  });
  $('guide-evidence').onclick = () => task(async () => {
    exporting = true; refresh();
    const ticket = editor.ticket(), baselineRevision = editor.baseline?.revision;
    const request = {scene: editor.read().scene, document_id: editor.read().id,
      scene_revision: ticket.revision};
    if (editor.comparison && editor.baseline) request.baseline = editor.baseline.scene;
    try {
      const response = await fetch('/api/v2/evidence/project', {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request),
        signal: AbortSignal.timeout(30000)});
      const packet = await response.json();
      if (!response.ok) throw Error(packet.detail || packet.error || 'Evidence export failed.');
      if (!editor.current(ticket) || (request.baseline && editor.baseline?.revision !== baselineRevision)) throw Error('Scene changed during export. Recompute and export the new revision.');
      download(packet, 'frontiersight-project-evidence.json');
      $('guide-proof-digest').textContent = packet.packet_sha256;
      announce('Evidence exported with its computed SHA-256. The packet is unsigned and is not a safety certificate.');
    } finally { exporting = false; }
  });
  editor.subscribe(event => {
    if (['document', 'reset', 'baseline'].includes(event.type)) $('guide-proof-digest').textContent = 'Not exported for this revision';
    if (event.type !== 'time' && event.type !== 'selection' && event.type !== 'view') refresh();
  });
  showPhase('input', false);
}
