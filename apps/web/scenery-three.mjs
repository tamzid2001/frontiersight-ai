import * as THREE from 'three';

const cube = (w, h, d, color, x, y, z) => {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), new THREE.MeshStandardMaterial({ color, roughness: .85 }));
  mesh.position.set(x, y, z); return mesh;
};

export function buildScenery(plan) {
  const group = new THREE.Group(), [w, h] = plan.extent, unit = Math.min(w, h) / 14;
  group.userData.decorative = true;
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(w + 9 * unit, h + 9 * unit),
    new THREE.MeshStandardMaterial({ color: plan.ground, roughness: 1 }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = -.025; group.add(ground);
  // Painted lanes and work zones are scenery, not a replacement for modeled obstacles.
  const stripe = (x, z, width, depth, color) => group.add(cube(width, .012 * unit, depth, color, x, .005 * unit, z));
  if (plan.kind === 'road') {
    stripe(0, -h / 2 - .7 * unit, w + 5 * unit, 1.2 * unit, '#bdc9bb');
    stripe(0, h / 2 + .7 * unit, w + 5 * unit, 1.2 * unit, '#bdc9bb');
    for (let x = -w / 2; x < w / 2; x += 2 * unit) stripe(x, 0, unit, .07 * unit, '#fff0b9');
    for (let z = -h / 2; z < h / 2; z += 1.1 * unit) stripe(w * .35, z, 1.3 * unit, .45 * unit, '#f1f3df');
  } else {
    stripe(-w * .28, 0, w * .22, h, '#7f9f9a');
    for (const x of [-w * .4, -w * .16]) stripe(x, 0, .055 * unit, h, '#f5ce61');
    for (const z of [-h * .35, h * .35]) stripe(w * .25, z, w * .32, .055 * unit, '#f5ce61');
  }
  for (const prop of plan.props) {
    const { x, z, width: pw, height: ph, depth: pd, color, type } = prop;
    if (type === 'wall' || type === 'building') {
      group.add(cube(pw, ph, pd, color, x, ph / 2, z));
      if (type === 'building') for (let row = 0; row < 3; row++)
        group.add(cube(pw * .7, .25 * unit, .03 * unit, '#d5edf0', x, (.6 + row * .65) * unit, z - pd / 2 - .02 * unit));
    } else if (type === 'tree') {
      const trunk = new THREE.Mesh(new THREE.CylinderGeometry(.1 * unit, .15 * unit, ph * .55, 8), new THREE.MeshStandardMaterial({ color: '#7b654a' }));
      trunk.position.set(x, ph * .275, z); group.add(trunk);
      const leaves = new THREE.Mesh(new THREE.SphereGeometry(pw * .65, 12, 8), new THREE.MeshStandardMaterial({ color, roughness: 1 }));
      leaves.position.set(x, ph * .8, z); group.add(leaves);
    } else {
      for (const dx of [-pw * .46, pw * .46]) for (const dz of [-pd * .43, pd * .43])
        group.add(cube(.09 * unit, ph, .09 * unit, color, x + dx, ph / 2, z + dz));
      const levels = type === 'rack' ? 3 : 1;
      for (let level = 0; level < levels; level++) {
        const y = ph * (level + 1) / (levels + .3);
        group.add(cube(pw, .12 * unit, pd, color, x, y, z));
        for (let i = -1; i <= 1; i++) group.add(cube(pw * .25, .4 * unit, pd * .7, i % 2 ? '#b88b54' : '#c7a77a', x + i * pw * .3, y + .25 * unit, z));
      }
      if (type === 'workcell') {
        group.add(cube(.3 * unit, .65 * unit, .4 * unit, '#deaa43', x, ph + .3 * unit, z));
        const arm = cube(.85 * unit, .18 * unit, .22 * unit, '#d9902a', x + .25 * unit, ph + .65 * unit, z);
        arm.rotation.z = -.4; group.add(arm);
      }
    }
  }
  return group;
}
