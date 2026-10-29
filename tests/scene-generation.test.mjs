import test from 'node:test';
import assert from 'node:assert/strict';
import requestCore from '../apps/web/scene-request-core.js';
import {entityScale} from '../apps/web/entity-scale.mjs';

test('human height stays human-sized at every accepted collision radius',()=>{
 for(const radius of [.1,.45,1,3]){
  const scale=entityScale('pedestrian',radius,.297,1.735);
  assert.ok(scale*1.735<=1.85000001);
  assert.ok(scale*.297<=radius+.000001);
 }
 assert.equal(entityScale('forklift',.9,1,2),.9);
 assert.ok(entityScale('cyclist',3,.6,1.64)*1.64<=1.800001);
 for(const args of [[NaN,1,1],[-1,1,1],[1,0,1],[1,1,0]])assert.throws(()=>entityScale('pedestrian',...args));
});

test('repeated clicks cannot create duplicate in-flight batches',async()=>{
 const core=requestCore.create(1000);let finish,calls=0;
 const pending=core.run(()=>{calls++;return new Promise(resolve=>finish=resolve);});
 assert.equal(core.busy,true);
 await assert.rejects(core.run(()=>{calls++;}),/already running/);
 finish('one scene');assert.equal(await pending,'one scene');
 assert.equal(calls,1);assert.equal(core.busy,false);
});

test('timeout stops waiting even if provider ignores abort; late result is discarded',async()=>{
 const core=requestCore.create(10);let finish;
 const pending=core.run(()=>new Promise(resolve=>finish=resolve));
 await assert.rejects(pending,{name:'TimeoutError'});
 assert.equal(core.busy,false);
 assert.equal(await core.run(()=>Promise.resolve('new scene')),'new scene');
 finish('old scene');
});

test('cancel aborts request and releases UI for a new explicit click',async()=>{
 const core=requestCore.create(1000);let signal;
 const pending=core.run(s=>{signal=s;return new Promise(()=>{});});
 await Promise.resolve();core.cancel();
 await assert.rejects(pending,{name:'AbortError'});assert.equal(signal.aborted,true);
 assert.equal(await core.run(()=>42),42);
});

test('synchronous errors release the request lock without retry',async()=>{
 const core=requestCore.create(100);let calls=0;
 await assert.rejects(core.run(()=>{calls++;throw new Error('offline');}),/offline/);
 assert.equal(calls,1);assert.equal(core.busy,false);
 for(const deadline of [0,-1,NaN])assert.throws(()=>requestCore.create(deadline));
});

import stageEdit from '../apps/web/stage-edit-core.js';
test('generated paths fit the current floor before replacing any scene',()=>{
 const original={name:'Example',objects:[{category:'pedestrian',radius:.45,waypoints:[[8,7],[12,10]]}]};
 const copy=structuredClone(original),fitted=requestCore.fitScene(original,[9,8],stageEdit.resizePath);
 assert.deepEqual(fitted.stage_metres,[9,8]);assert.deepEqual(fitted.objects[0].waypoints[0],[4.5,4]);
 assert.equal(fitted.objects[0].radius,.45);assert.deepEqual(original,copy);
 for(const bad of [null,{objects:[]},{objects:Array(25).fill(original.objects[0])}])assert.throws(()=>requestCore.fitScene(bad,[9,8],stageEdit.resizePath));
 assert.throws(()=>requestCore.fitScene({...original,stage_metres:[0,8]},[9,8],stageEdit.resizePath));
});

test('editable scenes preserve identities and reject duplicate or unsafe IDs atomically',()=>{
 const source={stage_metres:[8,6],objects:[{id:'robot-7',category:'robot',waypoints:[[2,2],[5,3]],radius:.4,speed:1,path_source:'PREDICTED',custom:{spec:{name:'Robot'}}}]};
 const fit=(o,points)=>points.map(p=>[...p]);
 const result=requestCore.editableScene(source,[16,14],fit);
 assert.equal(result.objects[0].id,'robot-7');assert.equal(result.objects[0].path_source,'PREDICTED');
 assert.deepEqual(result.stage_metres,[8,6]);result.objects[0].waypoints[0][0]=3;assert.equal(source.objects[0].waypoints[0][0],2);
 for(const change of [{id:'<img>'},{id:'x',object_id:'y'},{speed:9},{radius:-1},{mode:'warp'},{curve:'unknown'},{waypoints:null}]){
  assert.throws(()=>requestCore.editableScene({...source,objects:[{...source.objects[0],...change}]},[8,6],fit));
 }
 assert.throws(()=>requestCore.editableScene({...source,objects:[source.objects[0],source.objects[0]]},[8,6],fit));
 assert.throws(()=>requestCore.editableScene({...source,stage_metres:[0,6]},[8,6],fit));
 assert.throws(()=>requestCore.editableScene(null,[8,6],fit));
 const legacy=requestCore.editableScene({objects:[{category:'robot',waypoints:[[1,1]]}]},[8,6],fit);assert.equal(legacy.objects[0].id,'robot-1');
});
