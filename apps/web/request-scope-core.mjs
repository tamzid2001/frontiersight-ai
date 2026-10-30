/* Freshness guard only; authentication remains a server responsibility. */
export function createRequestScope() {
  let revision = 0;
  return {
    capture: () => revision,
    current: ticket => ticket === revision,
    invalidate: () => { revision += 1; }
  };
}
