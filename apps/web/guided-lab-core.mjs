/** Pure presentation of evidence already owned by the canonical editor. */
export function guideState(document, result, comparison) {
  const scene = document?.scene;
  if (!scene) return {loaded: false, computed: false, compared: false, objects: 0,
    source: 'No scene', coordinates: 'Depth unavailable', observationReferences: 0};
  const sources = new Set(scene.objects.map(object => object.provenance));
  const source = sources.size === 1 && sources.has('FIXTURE') ? 'Synthetic fixture'
    : sources.has('MODEL_DERIVED') ? 'Model-derived / declared geometry'
    : sources.has('HARDWARE_OBSERVATION') ? 'Caller-declared sensor observations'
    : 'User-declared geometry';
  const status = scene.calibration?.status;
  const coordinates = status === 'CALIBRATED_METRIC_3D' ? 'Caller-supplied metric calibration'
    : status === 'ESTIMATED_3D' ? 'Estimated metres · uncertainty declared'
    : 'Assumed metres · no measured depth';
  return {loaded: true, computed: Boolean(result), compared: Boolean(comparison),
    objects: scene.objects.length, source, coordinates,
    observationReferences: document.observations?.length || 0};
}

export function importDocument(value) {
  if (value?.schema_version === '2.0') return {kind: 'scene', scene: value};
  if (value?.schema_version === 'frontiersight.project/1.0')
    return {kind: 'project', scene: value.document?.scene,
      recovery: JSON.stringify({document: value.document, checkpoint: value.checkpoint})};
  if (value?.document?.schema_version === 'frontiersight.editor/1.0')
    return {kind: 'project', scene: value.document.scene, recovery: JSON.stringify(value)};
  throw Error('Choose a canonical v2 scene or a FrontierSight editor recovery JSON file.');
}
