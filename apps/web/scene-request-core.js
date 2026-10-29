/* One explicit generation batch at a time, with no automatic retries. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SceneRequest = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function create(timeoutMs = 35000) {
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new RangeError('Invalid deadline');
    let active = null;
    return {
      get busy() { return active !== null; },
      cancel() { active?.abort(new DOMException('Generation cancelled', 'AbortError')); },
      async run(request) {
        if (active) throw new Error('Scene generation is already running');
        const controller = new AbortController(); active = controller;
        let listener;
        const aborted = new Promise((_, reject) => {
          listener = () => reject(controller.signal.reason);
          controller.signal.addEventListener('abort', listener, {once:true});
        });
        const timer = setTimeout(() => controller.abort(new DOMException('Generation deadline reached', 'TimeoutError')), timeoutMs);
        try {
          return await Promise.race([Promise.resolve().then(() => {
            controller.signal.throwIfAborted(); return request(controller.signal);
          }), aborted]);
        } finally {
          clearTimeout(timer); controller.signal.removeEventListener('abort', listener);
          if (active === controller) active = null;
        }
      }
    };
  }
  function fitScene(scene, stage, resizePath) {
    if (!scene || !Array.isArray(scene.objects) || !scene.objects.length || scene.objects.length > 24)
      throw new RangeError('Invalid generated scene');
    const from = scene.stage_metres ?? [16, 14];
    const objects = scene.objects.map(object => ({...object,
      waypoints: resizePath(object.waypoints, from, stage, object.radius ?? .5)}));
    return {...scene, stage_metres: [...stage], objects};
  }
  function editableScene(scene, currentStage, fitPath) {
    if (!scene || !Array.isArray(scene.objects) || scene.objects.length > 24) throw Error('Scene requires 0–24 objects.');
    const stage = scene.stage_metres ?? currentStage;
    if (!Array.isArray(stage) || stage.length !== 2 || !stage.every(v=>Number.isFinite(v)&&v>=6&&v<=60)) throw Error('Floor dimensions must be 6–60 metres.');
    const seen = new Set(), counts = {};
    const objects = scene.objects.map(raw=>{
      const o = JSON.parse(JSON.stringify(raw));
      if (!['forklift','pedestrian','robot','vehicle','cyclist','shelf','object'].includes(o.category)) throw Error('Unsupported component category.');
      counts[o.category] = (counts[o.category]||0)+1;
      o.id = o.id ?? o.object_id ?? (o.category+'-'+counts[o.category]);
      if (!/^[A-Za-z0-9_-]{1,100}$/.test(o.id) || seen.has(o.id) || (o.object_id && o.object_id!==o.id)) throw Error('Objects require unique stable IDs.');
      seen.add(o.id);
      o.radius ??= .5; o.speed ??= 0; o.delay ??= 0; o.curve ??= 'straight'; o.mode ??= 'stop';
      if (![o.radius,o.speed,o.delay].every(Number.isFinite) || o.radius<0 || o.speed<0 || o.speed>8 || o.delay<0 || o.delay>10 ||
          !['straight','smooth'].includes(o.curve) || !['stop','loop','pingpong'].includes(o.mode) || !Array.isArray(o.waypoints) || o.waypoints.length>24) throw Error('Invalid component motion settings.');
      delete o._res;delete o._prof;
      o.waypoints = fitPath(o, o.waypoints, stage);
      return o;
    });
    return {...scene, stage_metres:[...stage], objects};
  }
  return {create, fitScene, editableScene};
});
