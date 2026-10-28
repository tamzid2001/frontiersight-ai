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

// The browser and Python API use these same metre-space edit semantics.
const {default: editor}=await import('../apps/web/stage-edit-core.js');
test('resizing rescales every waypoint and does not mutate the source path',()=>{
 const original=[[2,2],[8,7],[14,12]],copy=structuredClone(original);
 assert.deepEqual(editor.resizePath(original,[16,14],[8,7],.5),[[1,1],[4,3.5],[7,6]]);
 assert.deepEqual(original,copy);
 assert.deepEqual(editor.resizePath([[8,7]],[16,14],[32,28],.5),[[16,14]]);
});
test('floor fitting uses the physical footprint and preserves relative path shape',()=>{
 const fitted=editor.resizePath([[0,0],[16,14]],[16,14],[6,6],1);
 assert.deepEqual(fitted,[[1,1],[5,5]]);
 assert.deepEqual(editor.fitPath([], [6,6],1),[]);
 assert.deepEqual(editor.fitPath([[10,20]],[8,8],1),[[7,7]]);
 assert.deepEqual(editor.fitPath([[3,3],[3,3]],[6,6],3),[[3,3],[3,3]]);
});
test('whole-path translation clamps at boundaries without deforming the path',()=>{
 const points=[[2,2],[5,4]],moved=editor.translatePath(points,100,-100,[10,8],1);
 assert.deepEqual(moved.points,[[6,1],[9,3]]);assert.equal(moved.clamped,true);
 assert.equal(moved.points[1][0]-moved.points[0][0],3);
 assert.deepEqual(editor.translatePath(points,1,1,[10,8],1),{points:[[3,3],[6,5]],dx:1,dy:1,clamped:false});
 assert.deepEqual(editor.translatePath([],1,1,[10,8],1).points,[]);
});
test('sampled smooth-curve envelopes also constrain dragging and resize fitting',()=>{
 const points=[[2,2],[4,4]],envelope=[[1,1],[5,5]];
 assert.equal(editor.translatePath(points,100,0,[6,6],1,envelope).dx,0);
 const fitted=editor.fitPath(points,[6,6],1,[[0,0],[6,6]]);
 assert.deepEqual(fitted,[[1+4/3,1+4/3],[1+8/3,1+8/3]]);
});
test('pointer coordinates respect CSS canvas sizing, vertical inversion and captured pointers outside the canvas',()=>{
 const rect={left:100,top:200,width:800,height:400};
 assert.deepEqual(editor.pointerPoint(500,400,rect,[16,14]),[8,7]);
 assert.deepEqual(editor.pointerPoint(-500,1000,rect,[16,14]),[0,0]);
 assert.deepEqual(editor.pointerPoint(1000,0,rect,[16,14]),[16,14]);
});
test('non-finite input, impossible footprints and unfittable rigid paths fail explicitly',()=>{
 for(const stage of [[0,2],[1,NaN],[],[3,4,5]])assert.throws(()=>editor.fitPath([[1,1]],stage));
 for(const points of [null,[[1]],[[NaN,2]],Array(10001).fill([1,2])])assert.throws(()=>editor.fitPath(points,[6,6]));
 assert.throws(()=>editor.fitPath([[1,1]],[6,6],4));assert.throws(()=>editor.fitPath([[1,1]],[6,6],-1));
 assert.throws(()=>editor.translatePath([[0,0],[10,10]],0,0,[6,6],1));
 assert.throws(()=>editor.translatePath([[1,1]],Infinity,0,[6,6],1));
 assert.throws(()=>editor.pointerPoint(1,1,{left:0,top:0,width:0,height:2},[6,6]));
});
test('the browser bundle exposes the same implementation without Node globals',async()=>{
 const {readFile}=await import('node:fs/promises');const vm=await import('node:vm');const context={};
 vm.runInNewContext(await readFile(new URL('../apps/web/stage-edit-core.js',import.meta.url),'utf8'),context);
 assert.equal(typeof context.FrontierStageEdit.resizePath,'function');
 assert.equal(context.FrontierStageEdit.resizePath([[8,7]],[16,14],[8,7])[0][0],4);
});
