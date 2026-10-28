import test from 'node:test';
import assert from 'node:assert/strict';
import { imageScene, projectedObject } from '../apps/web/image-scene-core.mjs';
import { sceneryKind, sceneryPlan, stagePoint } from '../apps/web/scenery-core.mjs';

const record = (overrides = {}) => ({object_id:7,box:{x1:20,y1:10,x2:39,y2:29,frame_w:100,frame_h:50},confidence:.8,...overrides});
const capture = (records = [record()], overrides = {}) => ({t:0,concept:'forklift',records,...overrides});

test('image coordinates use inclusive box maxima and remain uncalibrated', () => {
 const scene = imageScene([capture()],1000,500);
 assert.deepEqual(scene.objects[0].bounds,[200,100,200,200]);
 assert.equal(scene.metricReconstruction,false); assert.equal(scene.physicalCalibration,null);
 assert.equal(scene.coordinateSpace,'image_pixels'); assert.equal(scene.objects[0].depthSource,'ASSUMPTION');
 assert.equal(scene.objects[0].geometry,'bounding_box_region');
 assert.deepEqual(projectedObject(scene.objects[0],1000,500),{x:-2.4,y:3.6,width:2.4,height:2.4,depth:.12,z:.29});
});

test('only latest frame contributes and response-local IDs are namespaced by concept', () => {
 const scene=imageScene([capture(),capture(undefined,{t:1}),capture(undefined,{t:1,concept:'pallet'}),capture(undefined,{t:1})],100,50);
 assert.equal(scene.objects.length,2); assert.deepEqual(scene.objects.map(o=>o.label),['forklift','pallet']);
 assert.equal(scene.at,1);
});

test('actual decoded masks distinguished from opaque payloads', () => {
 const mask={decoded:true,png_data_url:'data:image/png;base64,AAAA'};
 const valid=imageScene([capture([record({mask})])],100,50).objects[0];
 assert.equal(valid.mask,mask.png_data_url); assert.equal(valid.geometry,'segmented_mask_extrusion');
 for (const bad of [{decoded:false,...{png_data_url:mask.png_data_url}},{decoded:true,png_data_url:'javascript:bad'}])
  assert.equal(imageScene([capture([record({mask:bad})])],100,50).objects[0].mask,null);
});

test('invalid source boxes, non-finite values and IDs are excluded', () => {
 for(const patch of [{x1:-1},{x2:101},{frame_w:0},{frame_h:Infinity},{x1:50}]){
  const r=record();Object.assign(r.box,patch);assert.equal(imageScene([capture([r])],100,50).objects.length,0);
 }
 assert.equal(imageScene([capture([record({object_id:-1})])],100,50).objects.length,0);
});

test('image and object budgets prevent oversized scene allocation', () => {
 for(const [w,h] of [[0,10],[1601,10],[2.5,2],[Infinity,4]])assert.throws(()=>imageScene([],w,h));
 assert.throws(()=>imageScene(Array.from({length:97},()=>capture()),100,50));
 assert.equal(imageScene([capture(Array.from({length:60},(_,id)=>record({object_id:id})))],100,50).objects.length,24);
});

test('edge boxes clip to the actual photograph rather than adding pixels', () => {
 const r=record();Object.assign(r.box,{x1:99,y1:49,x2:100,y2:50});
 assert.deepEqual(imageScene([capture([r])],100,50).objects[0].bounds,[99,49,1,1]);
 assert.throws(()=>projectedObject({bounds:[1,0,500,2]},100,50));
 assert.throws(()=>projectedObject({bounds:[0,0,1,1]},0,50));
});

test('scenery selects physical AI context from the scene, with explicit overrides', () => {
 assert.equal(sceneryKind([{category:'cyclist'}]),'road');
 assert.equal(sceneryKind([{category:'robot'}]),'robotics');
 assert.equal(sceneryKind([{category:'robot'},{category:'forklift'}]),'warehouse');
 assert.equal(sceneryKind([], 'road'),'road');assert.equal(sceneryKind([], 'invalid'),'warehouse');
});

test('all solid scenery stays outside the analyzed rectangle and has no collider', () => {
 for(const extent of [[16,14],[640,480],[3,5]])for(const kind of ['warehouse','road','robotics']){
  const plan=sceneryPlan([],extent,kind);assert.equal(plan.physics,'VISUAL_ONLY');
  assert.ok(plan.props.length>=7);
  for(const p of plan.props){assert.equal(p.collider,false);assert.equal(p.decorative,true);
   assert.ok(Math.abs(p.x)-p.width/2>=extent[0]/2 || Math.abs(p.z)-p.depth/2>=extent[1]/2,JSON.stringify(p));}
 }
});

test('each viewer has independent coordinate extents', () => {
 assert.deepEqual(stagePoint(2,3,[16,14]),[-6,4]);
 assert.deepEqual(stagePoint(2,3,[640,480]),[-318,237]);
 assert.deepEqual(stagePoint(2,3,[16,14]),[-6,4]);
 for(const extent of [[0,2],[NaN,2],[],[2,3,4]])assert.throws(()=>stagePoint(0,0,extent));
});

test('2D contexts paint all three environments and restore caller drawing state', async () => {
 const {paintScenery2D}=await import('../apps/web/scenery-core.mjs');
 for(const kind of ['warehouse','road','robotics']){
  let saves=0,restores=0,fills=0;
  const context={save(){saves++;},restore(){restores++;},createLinearGradient(){return {addColorStop(){}};},
   fillRect(){fills++;},setLineDash(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},strokeRect(){}};
  assert.equal(paintScenery2D(context,800,600,[],kind),kind);
  assert.ok(fills>=3);assert.equal(saves,1);assert.equal(restores,1);
 }
});
