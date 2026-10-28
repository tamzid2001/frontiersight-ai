/* FrontierSight 3D view — a visualisation of the SAME 2D scene model.
   Heights are illustrative; physics, sampling and analysis stay planar.
   Lazy-initialised on first open; renders only while visible. */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';
import { sceneryPlan, stagePoint } from './scenery-core.mjs';
import { buildScenery } from './scenery-three.mjs';

const REALC = { forklift: 0xe9a13b, pedestrian: 0xff7847, robot: 0xaebfd2,
  vehicle: 0x4d8dff, cyclist: 0xb07fe8, shelf: 0x8a6f4d, object: 0x9aa7b8 };
const BASER = { forklift: 0.9, pedestrian: 0.45, robot: 0.55, vehicle: 1.1, cyclist: 0.5, shelf: 1.1, object: 0.6 };
let C = null;
const INSTANCES = new Set();
function disposeObject(root){root.traverse(m=>{
 if(m.isInstancedMesh)m.dispose();
 if(m.geometry)m.geometry.dispose();
 if(m.material){(Array.isArray(m.material)?m.material:[m.material]).forEach(mm=>{mm.map?.dispose();mm.dispose();});}});}


function mat(color, rough = 0.65) {
  return new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: 0.08 });
}
function box(w, h, d, color, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color));
  m.position.set(x, y, z); return m;
}
function wheel(r, x, z) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, r * 0.55, 20), mat(0x20262e, 0.9));
  m.rotation.x = Math.PI / 2; m.position.set(x, r, z); return m;
}

function buildCustom(spec) {
  const g = new THREE.Group();
  const pal = spec.palette || {};
  for (const part of spec.parts || []) {
    const color = new THREE.Color(pal[part.color] || part.color || pal.body || "#9aa7b8");
    const [sx, sy, sz] = part.size, [px, py, pz] = part.pos;
    let m;
    if (part.shape === "cylinder") m = new THREE.Mesh(new THREE.CylinderGeometry(sx / 2, sx / 2, sy, 20), mat(color.getHex(), 0.6));
    else if (part.shape === "sphere") m = new THREE.Mesh(new THREE.SphereGeometry(sx / 2, 20, 14), mat(color.getHex(), 0.55));
    else if (part.shape === "capsule") m = new THREE.Mesh(new THREE.CapsuleGeometry(sx / 2, Math.max(0.05, sy - sx), 6, 14), mat(color.getHex(), 0.6));
    else if (part.shape === "cone") m = new THREE.Mesh(new THREE.ConeGeometry(sx / 2, sy, 20), mat(color.getHex(), 0.6));
    else m = box(sx, sy, sz, color.getHex());
    m.position.set(px, py, pz);
    g.add(m);
  }
  g.userData.noScale = true;
  return g;
}

function buildEntity(o) {
  if (o._lab && o._lab.custom && o._lab.custom.spec) return buildCustom(o._lab.custom.spec);
  const g = new THREE.Group();
  const c = REALC[o.category] || REALC.object;
  if (o.category === "forklift") {
    g.add(box(1.5, 0.62, 0.92, c, 0, 0.52, 0));
    g.add(box(0.14, 1.35, 0.92, 0x374151, 0.82, 0.85, 0));
    g.add(box(0.72, 0.07, 0.13, 0x9aa7b8, 1.22, 0.1, -0.28), box(0.72, 0.07, 0.13, 0x9aa7b8, 1.22, 0.1, 0.28));
    [[-0.55, -0.5], [0.5, -0.5], [-0.55, 0.5], [0.5, 0.5]].forEach(([x, z]) => g.add(wheel(0.21, x, z)));
    const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 10), mat(0xf6c453, 0.3));
    beacon.position.set(-0.3, 1.0, 0); g.add(beacon);
  } else if (o.category === "pedestrian") {
    const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.21, 0.62, 6, 14), mat(c, 0.8));
    torso.position.y = 0.95; g.add(torso);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.155, 18, 14), mat(0xf0bd93, 0.7));
    head.position.y = 1.58; g.add(head);
    [-0.09, 0.09].forEach(z => {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.05, 0.62, 8), mat(0x2c3444, 0.9));
      leg.position.set(0, 0.31, z); g.add(leg);
    });
  } else if (o.category === "robot") {
    g.add(box(1.1, 0.5, 0.82, c, 0, 0.42, 0));
    const dome = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.26, 0.2, 20), mat(0x38c6d9, 0.35));
    dome.position.y = 0.78; g.add(dome);
    [[-0.42, -0.44], [0.42, -0.44], [-0.42, 0.44], [0.42, 0.44]].forEach(([x, z]) => g.add(wheel(0.17, x, z)));
  } else if (o.category === "vehicle") {
    g.add(box(2.1, 0.55, 0.98, c, 0, 0.52, 0));
    g.add(box(0.95, 0.48, 0.88, 0x2f5fb3, -0.15, 1.02, 0));
    [[-0.78, -0.55], [0.78, -0.55], [-0.78, 0.55], [0.78, 0.55]].forEach(([x, z]) => g.add(wheel(0.24, x, z)));
  } else if (o.category === "cyclist") {
    [-0.45, 0.45].forEach(x => {
      const w = new THREE.Mesh(new THREE.TorusGeometry(0.31, 0.035, 10, 28), mat(0x20262e, 0.8));
      w.position.set(x, 0.31, 0); g.add(w);
    });
    const frame = box(0.95, 0.06, 0.06, c, 0, 0.55, 0); frame.rotation.z = 0.35; g.add(frame);
    const rider = new THREE.Mesh(new THREE.CapsuleGeometry(0.17, 0.5, 6, 12), mat(0x35424f, 0.85));
    rider.position.set(0.05, 1.05, 0); rider.rotation.z = -0.25; g.add(rider);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.14, 16, 12), mat(0xf0bd93, 0.7));
    head.position.set(0.22, 1.5, 0); g.add(head);
  } else if (o.category === "shelf") {
    g.add(box(2.3, 2.1, 1.0, c, 0, 1.05, 0));
    for (let i = 0; i < 3; i++) for (let k = 0; k < 2; k++)
      g.add(box(0.62, 0.8, 0.06, 0xb08d5f, -0.72 + i * 0.72, 0.65 + k * 0.95, 0.52));
  } else {
    g.add(box(1.2, 0.7, 0.8, c, 0, 0.45, 0));
  }
  const s = THREE.MathUtils.clamp((o.radius || BASER[o.category] || 0.6) / (BASER[o.category] || 0.6), 0.6, 1.8);
  if (!g.userData.noScale && o.category !== "pedestrian" && o.category !== "cyclist") g.scale.setScalar(s);
  return g;
}

function create(container, hooks) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.setSize(container.clientWidth, 560);
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const cs = getComputedStyle(document.documentElement);
  scene.background = new THREE.Color(cs.getPropertyValue("--canvas").trim() || "#0a0e1a");
  const camera = new THREE.PerspectiveCamera(46, container.clientWidth / 560, 0.1, 200);
  camera.position.set(0, 17, 15);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0); controls.maxPolarAngle = Math.PI * 0.47; controls.update();
  scene.add(new THREE.HemisphereLight(0xdfeaff, 0x1a2233, 1.15));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(8, 18, 6); scene.add(sun);

  const _ext = hooks.extent ? hooks.extent() : [16, 14];
  const span = Math.max(..._ext);
  camera.far = Math.max(200, span * 10); camera.position.set(0, span * 1.05, span * .95); camera.updateProjectionMatrix();
  const toThree = (x, y) => stagePoint(x, y, _ext);
  let decoration = null, decorationKind = null;
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(_ext[0], _ext[1]),
    new THREE.MeshStandardMaterial({ color: new THREE.Color(cs.getPropertyValue("--panel2").trim() || "#10141c"), roughness: 1 }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = -.04; scene.add(ground);
  const grid = new THREE.GridHelper(_ext[0], Math.round(_ext[0]), 0x2a3650, 0x232c44);
  grid.scale.z = _ext[1] / _ext[0]; grid.position.y = 0.01;
  grid.material.transparent = true; grid.material.opacity = .12; scene.add(grid);
  const border = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(_ext[0], _ext[1])),
    new THREE.LineBasicMaterial({ color: 0x38c6d9 }));
  border.rotation.x = -Math.PI / 2; border.position.y = 0.02; scene.add(border);

  const world = new THREE.Group(); scene.add(world);
  const state = { renderer, scene, camera, controls, world, entities: new Map(), sig: "", visible: true, raf: 0, ground };
  INSTANCES.add(state);
  renderer.domElement.addEventListener("webglcontextlost", e=>{e.preventDefault(); state.stop();
   if(hooks.onContextLost)hooks.onContextLost();});
  renderer.domElement.tabIndex = 0;
  renderer.domElement.setAttribute("aria-label", "3D scene. Drag to orbit, scroll to zoom; focus this canvas to pan with arrow keys.");
  controls.listenToKeyEvents(renderer.domElement);

  function updateScenery(items) {
    const plan = sceneryPlan(items, _ext, globalThis.frontierSceneryChoice || "auto");
    if (plan.kind === decorationKind) return;
    if (decoration) { disposeObject(decoration); scene.remove(decoration); }
    decoration = buildScenery(plan); decorationKind = plan.kind; scene.add(decoration);
    scene.background = new THREE.Color(plan.sky);
  }

  function rebuild(items) {
    updateScenery(items);
    world.children.slice().forEach(ch=>{disposeObject(ch); world.remove(ch);});
    state.entities.clear();
    for (const o of items) {
      if (o.lines) for (const ln of o.lines) {
        const pts = ln.pts.map(([x, y]) => { const [tx, tz] = toThree(x, y); return new THREE.Vector3(tx, 0.06, tz); });
        world.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
          new THREE.LineBasicMaterial({ color: ln.color, transparent: true, opacity: ln.opacity ?? 0.8 })));
      }
      if (o.pathPts && o.pathPts.length > 1) {
        const pts = o.pathPts.map(([x, y]) => { const [tx, tz] = toThree(x, y); return new THREE.Vector3(tx, 0.06, tz); });
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
          new THREE.LineBasicMaterial({ color: REALC[o.category] || 0xffffff, transparent: true, opacity: 0.75 }));
        world.add(line);
        if (o.dots) for (const [x, y] of o.dots) {
          const dot = new THREE.Mesh(new THREE.SphereGeometry(0.09, 10, 8),
            new THREE.MeshBasicMaterial({ color: REALC[o.category] || 0xffffff }));
          const [tx, tz] = toThree(x, y); dot.position.set(tx, 0.07, tz); world.add(dot);
        }
      }
      const ent = buildEntity(o);
      if (o.opacity !== undefined) ent.traverse(m => { if (m.material) { m.material = m.material.clone(); m.material.transparent = true; m.material.opacity = o.opacity; } });
      world.add(ent); state.entities.set(o.id, ent);
    }
    state.sig = hooks.sig ? hooks.sig() : "";
  }

  function setTime(items, t) {
    updateScenery(items);
    for (const o of items) {
      const ent = state.entities.get(o.id); if (!ent) continue;
      const pos = hooks.pos(o, t); if (!pos) { ent.visible = false; continue; }
      ent.visible = true;
      const [tx, tz] = toThree(pos[0], pos[1]); ent.position.set(tx, 0, tz);
      const ahead = hooks.pos(o, t + 0.35);
      if (ahead && (ahead[0] !== pos[0] || ahead[1] !== pos[1])) {
        // local +X after rotY maps to (cos, 0, -sin); three z = extent/2 - stage y
        const dx = ahead[0] - pos[0], dz = -(ahead[1] - pos[1]);
        ent.rotation.y = Math.atan2(-dz, dx);
      }
    }
  }

  // ground click -> add waypoint (click vs orbit-drag disambiguated)
  const ray = new THREE.Raycaster(), plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  let downAt = null;
  renderer.domElement.addEventListener("pointerdown", e => { downAt = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", e => {
    if (!downAt) return;
    const moved = Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]); downAt = null;
    if (moved > 6) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1,
                                  -((e.clientY - rect.top) / rect.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = new THREE.Vector3();
    if (ray.ray.intersectPlane(plane, hit) && hooks.onGroundClick)
      hooks.onGroundClick(hit.x + _ext[0] / 2, _ext[1] / 2 - hit.z);
  });

  const resize = new ResizeObserver(() => {
    const w = container.clientWidth; if (!w) return;
    renderer.setSize(w, 560); camera.aspect = w / 560; camera.updateProjectionMatrix();
  }); resize.observe(container);

  function loop() {
    if (!state.visible) return;
    controls.update(); renderer.render(scene, camera);
    state.raf = requestAnimationFrame(loop);
  }
  state.rebuild = rebuild; state.setTime = setTime; state.hooks = hooks;
  state.start = () => { state.visible = true; cancelAnimationFrame(state.raf); loop(); };
  state.stop = () => { state.visible = false; cancelAnimationFrame(state.raf); };
  state.dispose = () => { state.stop(); resize.disconnect(); controls.dispose();
    disposeObject(scene); renderer.dispose(); renderer.domElement.remove(); INSTANCES.delete(state); };
  return state;
}

function labItems(objects) {
  return objects.map(o => ({ id: o.id, category: o.category, radius: o.radius,
    pathPts: o.waypoints && o.waypoints.length > 1 ? C0.resolve(o).pts : null, dots: o.waypoints, _lab: o }));
}
let C0 = null; // lab hooks (resolve) captured at show time for item building
export function showLab3D(container, hooks) {
  C0 = hooks;
  const wrapped = { ...hooks,
    sig: () => JSON.stringify((C0._objs || []).map(o => [o.id, o.category, o.waypoints, o.curve, o.mode, o.radius])),
    pos: (item, t) => hooks.pos(item._lab, t) };
  if (!C) C = create(container, wrapped);
  C.hooks = wrapped; C.start();
  return C;
}
export function hideLab3D() { if (C) C.stop(); }
export function syncLab3D(objects, t, force = false) {
  if (!C || !C.visible || !C0) return;
  C0._objs = objects;
  const items = labItems(objects);
  const sig = JSON.stringify(objects.map(o => [o.id, o.category, o.waypoints, o.curve, o.mode, o.radius]));
  if (force || sig !== C.sig) { C.rebuild(items); C.sig = sig; }
  C.setTime(items, t);
}

// ---- Studio 3D: same stage tech, read-only playback of scenario tracks ----
let S = null;
export function showStudio3D(container, hooks) {
  const key = hooks.extent ? hooks.extent().join("x") : "16x14";
  if (S && S._extentKey !== key) { S.dispose(); S = null; }
  if (!S) { S = create(container, hooks); S._extentKey = key; }
  S.start();
  return S;
}
export function hideStudio3D() { if (S) S.stop(); }
export function syncStudio3D(tracks, t, force = false) {
  if (!S || !S.visible) return;
  const items = tracks.map(tr => ({ id: tr.object_id, category: tr.category, radius: tr.radius,
    pathPts: tr.points.map(p => [p[1], p[2]]), dots: null, _tr: tr }));
  const sig = "studio:" + tracks.map(tr => tr.object_id + ":" + tr.points.length).join(",");
  if (force || sig !== S.sig) { S.rebuild(items); S.sig = sig; }
  S.setTime(items, t);
}
export function refreshAll3DThemes() {
  const cs = getComputedStyle(document.documentElement);
  const bg = cs.getPropertyValue("--canvas").trim() || "#0a0e1a";
  const panel = cs.getPropertyValue("--panel2").trim() || "#10141c";
  for (const s of INSTANCES) {
    // Scenery keeps its physically legible daylight palette across UI themes.
    if (s.ground) s.ground.material.color = new THREE.Color(panel);
  }
}


// ---- Counterfactual 3D: agent (cf), ghost (original), other actors ----
let F = null;
function cfPos(item, t) {
  const rows = item._rows; if (!rows || !rows.length) return null;
  let best = rows[0];
  for (const r of rows) if (Math.abs(r[0] - t) < Math.abs(best[0] - t)) best = r;
  return item._at === "agent" ? [best[1], best[2]] : [best[3], best[4]];
}
export function showCf3D(container, hooks) {
  const key = hooks.extent ? hooks.extent().join("x") : "16x14";
  if (F && F._extentKey !== key) { F.dispose(); F = null; }
  if (!F) { F = create(container, { ...hooks, pos: cfPos }); F._extentKey = key; }
  F.start();
  return F;
}
export function hideCf3D() { if (F) F.stop(); }
export function syncCf3D(cf, meta, t, force = false) {
  if (!F || !F.visible || !cf) return;
  const focus = cf.focus_other, fr = cf.results[focus]; if (!fr) return;
  const agentMeta = meta[cf.agent_id] || { category: "object", radius: 0.6 };
  const items = [
    { id: cf.agent_id, category: agentMeta.category, radius: agentMeta.radius, _at: "agent",
      _rows: fr.trajectories.counterfactual,
      lines: [{ pts: fr.trajectories.counterfactual.map(r => [r[1], r[2]]), color: 0x2dd4a8, opacity: 0.95 },
              { pts: fr.trajectories.original.map(r => [r[1], r[2]]), color: 0x8fa0b8, opacity: 0.55 }] },
    { id: cf.agent_id + "-ghost", category: agentMeta.category, radius: agentMeta.radius, _at: "agent",
      _rows: fr.trajectories.original, opacity: 0.35, lines: [] },
  ];
  for (const [oid, r] of Object.entries(cf.results)) {
    const m = meta[oid] || { category: "object", radius: 0.5 };
    items.push({ id: oid, category: m.category, radius: m.radius, _at: "other",
      _rows: r.trajectories.counterfactual,
      lines: [{ pts: r.trajectories.counterfactual.map(p => [p[3], p[4]]), color: 0x8fa0b8, opacity: 0.6 }] });
  }
  const sig = "cf:" + cf.agent_id + ":" + focus + ":" + Object.keys(cf.results).join(",");
  if (force || sig !== F.sig) { F.rebuild(items); F.sig = sig; }
  F.setTime(items, t);
}
