/** Illustrative height and physical collision clearance are independent. */
export function entityScale(category, radius, footprint, height) {
  if (![radius, footprint, height].every(Number.isFinite) || radius < 0 || footprint <= 0 || height <= 0)
    throw new RangeError('Invalid entity dimensions');
  const fit = radius / footprint;
  const cap = category === 'pedestrian' ? 1.85 : category === 'cyclist' ? 1.8 : Infinity;
  return Math.min(fit, cap / height);
}
