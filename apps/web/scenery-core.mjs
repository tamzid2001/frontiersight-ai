/** Decorative scenery. These props never enter the planar collision engine. */
export function sceneryKind(items = [], requested = 'auto') {
  if (['warehouse', 'road', 'robotics'].includes(requested)) return requested;
  const categories = new Set(items.map(item => item.category));
  if (categories.has('vehicle') || categories.has('cyclist')) return 'road';
  if (categories.has('robot') && !categories.has('forklift') && !categories.has('shelf')) return 'robotics';
  return 'warehouse';
}

export function stagePoint(x, y, extent) {
  if (!Array.isArray(extent) || extent.length !== 2 || !extent.every(v => Number.isFinite(v) && v > 0)
      || !Number.isFinite(x) || !Number.isFinite(y)) throw Error('Invalid stage coordinates');
  return [x - extent[0] / 2, extent[1] / 2 - y];
}

export function sceneryPlan(items, extent, requested = 'auto') {
  stagePoint(0, 0, extent);
  const kind = sceneryKind(items, requested), [w, h] = extent;
  // Heights and prop locations are illustrative. Every solid prop is outside
  // the bounded analysis stage, so scenery cannot suggest a tested collision.
  const scale = Math.min(w, h) / 14, props = [];
  const add = (type, x, z, color, width = 1, height = 1, depth = 1) =>
    props.push({ type, x, z, color, width: width * scale, height: height * scale,
      depth: depth * scale, decorative: true, collider: false });
  if (kind === 'road') {
    for (let i = -2; i <= 2; i++) {
      add('tree', i * w / 5, -h / 2 - 1.5 * scale, '#4b8059', 1.1, 2.1, 1.1);
      add('building', i * w / 5, h / 2 + 2 * scale, i % 2 ? '#c6ac8c' : '#88a7b8', 2.2, 2.6 + (i + 2) % 3, 1.5);
    }
  } else {
    for (let i = -2; i <= 2; i++) {
      add(kind === 'warehouse' ? 'rack' : 'workcell', i * w / 5, -h / 2 - 1.7 * scale,
        kind === 'warehouse' ? '#326e89' : '#3e8190', 2.1, kind === 'warehouse' ? 2.8 : 1.7, 1.3);
    }
    add('wall', -w / 2 - 1.5 * scale, 0, '#bfd0cc', .16, 2.6, h / scale + 3);
    add('wall', 0, -h / 2 - 3.2 * scale, '#d4dfdc', w / scale + 3, 2.6, .16);
  }
  return { kind, extent: [...extent], props, physics: 'VISUAL_ONLY',
    ground: kind === 'road' ? '#647480' : kind === 'robotics' ? '#b1c7c9' : '#c6c7ab',
    sky: kind === 'road' ? '#c8e4ed' : '#dce9e4' };
}

export function paintScenery2D(context, width, height, items, requested = 'auto') {
  const kind = sceneryKind(items, requested);
  context.save();
  const gradient = context.createLinearGradient(0, 0, width, height);
  gradient.addColorStop(0, kind === 'road' ? '#516979' : '#cbd7ca');
  gradient.addColorStop(1, kind === 'road' ? '#8a9a9c' : '#9eafb0');
  context.fillStyle = gradient; context.fillRect(0, 0, width, height);
  if (kind === 'road') {
    context.fillStyle = '#bbc9be'; context.fillRect(0, 0, width, height * .075);
    context.fillRect(0, height * .925, width, height * .075);
    context.strokeStyle = '#f9edc2'; context.lineWidth = Math.max(2, width / 300);
    context.setLineDash([width / 20, width / 30]); context.beginPath();
    context.moveTo(0, height / 2); context.lineTo(width, height / 2); context.stroke(); context.setLineDash([]);
    context.fillStyle = '#edf1df';
    for (let y = height * .12; y < height * .9; y += height * .1) context.fillRect(width * .83, y, width * .08, height * .045);
  } else {
    context.fillStyle = kind === 'warehouse' ? '#7f9e9b' : '#819fba';
    context.fillRect(width * .08, 0, width * .22, height);
    context.fillStyle = '#e8bd55'; context.fillRect(width * .07, 0, 3, height);
    context.fillRect(width * .31, 0, 3, height);
    context.strokeStyle = '#f0e3a1'; context.lineWidth = 2;
    context.setLineDash([12, 9]); context.strokeRect(width * .58, height * .15, width * .32, height * .7);
  }
  context.restore();
  return kind;
}
