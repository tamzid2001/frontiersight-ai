/** Original illustrative meshes. Collision geometry remains authoritative in Python. */
import * as THREE from 'three';
const material = color => new THREE.MeshStandardMaterial({color, roughness: .8});
function block(group, size, position, color) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), material(color));
  mesh.position.set(...position); group.add(mesh); return mesh;
}
function ball(group, radius, position, color) {
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 16, 10), material(color));
  mesh.position.set(...position); group.add(mesh); return mesh;
}
export function illustrativeBody(object) {
  const group = new THREE.Group(), label = (object.label || object.id).toLowerCase();
  if (object.geometry.kind === 'capsule' || /person|pedestrian|human/.test(label)) {
    // A person-shaped illustration, normalized to the declared capsule bounds.
    ball(group, .18, [0, .72, 0], '#d3a37f');
    block(group, [.48, .66, .25], [0, .18, 0], '#d7a82d');
    for (const side of [-1, 1]) {
      block(group, [.14, .6, .16], [side * .13, -.45, 0], '#293e5f');
      block(group, [.14, .58, .14], [side * .33, .15, 0], '#d7a82d');
      block(group, [.19, .12, .3], [side * .13, -.8, .06], '#202b3c');
    }
    ball(group, .195, [0, .8, 0], '#f0c035');
  } else if (/forklift|chassis/.test(label)) {
    block(group, [1.2, .6, .9], [0, -.12, 0], '#dba326');
    block(group, [.78, .48, .62], [-.1, .34, 0], '#52677c');
    block(group, [.82, .07, .68], [-.1, .62, 0], '#e7b942');
    for (const side of [-1, 1]) for (const x of [-.4, .4]) {
      const wheel = new THREE.Mesh(new THREE.CylinderGeometry(.22, .22, .13, 16), material('#25303c'));
      wheel.rotation.x = Math.PI / 2; wheel.position.set(x, -.35, side * .49); group.add(wheel);
    }
  } else if (/forks/.test(label)) {
    block(group, [.12, .14, .9], [-.4, 0, 0], '#7d8d9c');
    for (const side of [-1, 1]) block(group, [1.1, .08, .16], [.08, -.03, side * .35], '#a6b4bf');
  } else if (/payload|pallet|box/.test(label)) {
    block(group, [1, 1, 1], [0, 0, 0], '#b88c5c');
    block(group, [.07, 1.005, 1.005], [0, 0, 0], '#dcc395');
    for (const y of [-.32, .32]) block(group, [1.005, .035, 1.005], [0, y, 0], '#967244');
  } else if (/vehicle/.test(label)) {
    block(group, [1.5, .45, .9], [0, -.1, 0], '#318fb1');
    block(group, [.8, .38, .78], [-.1, .3, 0], '#91bbc4');
  } else {
    const color = /shelf|beam|mast/.test(label) ? '#7791a7' : '#83a3aa';
    block(group, [1, 1, 1], [0, 0, 0], color);
  }
  const box = new THREE.Box3().setFromObject(group), size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  for (const child of group.children) child.position.sub(center);
  const geometry = object.geometry;
  const extent = geometry.kind === 'box'
    ? [2 * geometry.half_extents_m[0], 2 * geometry.half_extents_m[2], 2 * geometry.half_extents_m[1]]
    : [2 * geometry.radius_m, 2 * (geometry.radius_m + (geometry.half_length_m || 0)), 2 * geometry.radius_m];
  group.scale.set(extent[0] / size.x, extent[1] / size.y, extent[2] / size.z);
  group.userData.visualOnly = true; return group;
}
export function disposeObject(root) {
  const geometries = new Set(), materials = new Set();
  root.traverse(node => {
    if (node.geometry) geometries.add(node.geometry);
    for (const value of Array.isArray(node.material) ? node.material : node.material ? [node.material] : []) materials.add(value);
  });
  for (const geometry of geometries) geometry.dispose();
  for (const value of materials) value.dispose();
}
