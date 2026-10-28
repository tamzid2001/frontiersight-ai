/* Small dependency-free geometry shared by mouse, touch and numeric editing. */
(function (root) {
  'use strict';
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  function extent(stage) {
    if (!Array.isArray(stage) || stage.length !== 2 || !stage.every(v => Number.isFinite(v) && v > 0))
      throw new Error('Scene dimensions must be positive finite numbers.');
    return stage;
  }
  function points(rows) {
    if (!Array.isArray(rows) || rows.length > 10000 || !rows.every(p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite)))
      throw new Error('Path coordinates must be finite X/Y pairs.');
    return rows;
  }
  function limits(stage, radius) {
    extent(stage);
    if (!Number.isFinite(radius) || radius < 0 || stage.some(size => size < 2 * radius))
      throw new Error('This component is too large for that floor. Increase the floor size or reduce its radius.');
    return [[radius, stage[0] - radius], [radius, stage[1] - radius]];
  }
  function bounds(rows) {
    const low = [Infinity, Infinity], high = [-Infinity, -Infinity];
    for (const p of rows) for (let axis = 0; axis < 2; axis++) {
      low[axis] = Math.min(low[axis], p[axis]); high[axis] = Math.max(high[axis], p[axis]);
    }
    return {low, high};
  }
  function fitPath(rows, stage, radius = 0, envelope = rows) {
    points(rows); points(envelope); const range = limits(stage, radius);
    if (!rows.length) return [];
    const box = bounds(rows.concat(envelope));
    // One uniform correction preserves the sampled curve's shape when fitting
    // it after an anisotropic floor resize. Physical radius is never scaled.
    let scale = 1;
    for (let axis = 0; axis < 2; axis++) {
      const span = box.high[axis] - box.low[axis];
      if (span) scale = Math.min(scale, (range[axis][1] - range[axis][0]) / span);
    }
    const scaled = rows.map(p => p.map((v, axis) => box.low[axis] + (v - box.low[axis]) * scale));
    const offsets = range.map(([low, high], axis) => clamp(0,
      low - box.low[axis], high - (box.low[axis] + (box.high[axis] - box.low[axis]) * scale)));
    return scaled.map(p => p.map((v, axis) => v + offsets[axis]));
  }
  function resizePath(rows, from, to, radius = 0) {
    extent(from); extent(to); points(rows);
    return fitPath(rows.map(p => p.map((v, axis) => v * to[axis] / from[axis])), to, radius);
  }
  function translatePath(rows, dx, dy, stage, radius = 0, envelope = rows) {
    points(rows); points(envelope); const range = limits(stage, radius);
    if (![dx, dy].every(Number.isFinite)) throw new Error('Movement must be finite.');
    if (!rows.length) return {points: [], dx: 0, dy: 0, clamped: false};
    const box = bounds(rows.concat(envelope));
    const delta = [dx, dy].map((value, axis) => {
      const low = range[axis][0] - box.low[axis], high = range[axis][1] - box.high[axis];
      if (low > high + 1e-8) throw new Error('The path does not fit this floor. Resize it or edit its waypoints first.');
      return clamp(value, low, Math.max(low, high));
    });
    return {points: rows.map(p => p.map((v, axis) => v + delta[axis])), dx: delta[0], dy: delta[1],
      clamped: Math.abs(delta[0] - dx) > 1e-8 || Math.abs(delta[1] - dy) > 1e-8};
  }
  function pointerPoint(clientX, clientY, rect, stage) {
    extent(stage);
    if (![clientX, clientY, rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0)
      throw new Error('Preview size is unavailable.');
    return [clamp((clientX - rect.left) / rect.width, 0, 1) * stage[0],
      (1 - clamp((clientY - rect.top) / rect.height, 0, 1)) * stage[1]];
  }
  const api = {fitPath, resizePath, translatePath, pointerPoint};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.FrontierStageEdit = api;
})(typeof globalThis === 'undefined' ? window : globalThis);
