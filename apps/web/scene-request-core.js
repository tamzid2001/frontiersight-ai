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
  return {create, fitScene};
});
