import test from 'node:test';
import assert from 'node:assert/strict';
import {guideState,importDocument} from '../apps/web/guided-lab-core.mjs';
import {createEditorStore} from '../apps/web/lab-store-core.mjs';

test('guide distinguishes actual computed results, calibration and source authority',()=>{
 assert.equal(guideState({},null,null).loaded,false);
 const document={scene:{objects:[{provenance:'FIXTURE'}],calibration:{status:'ASSUMPTION_3D'}}};
 const fixture=guideState(document,null,null);
 assert.equal(fixture.source,'Synthetic fixture');assert.match(fixture.coordinates,/no measured depth/);
 document.scene.calibration.status='CALIBRATED_METRIC_3D';
 document.scene.objects[0].provenance='MODEL_DERIVED';document.observations=[{id:'video'}];
 const modeled=guideState(document,{frames:[]},{baseline_digest:'fixture'});
 assert.match(modeled.source,/Model-derived/);assert.match(modeled.coordinates,/Caller-supplied/);
 assert.equal(modeled.computed,true);assert.equal(modeled.compared,true);assert.equal(modeled.observationReferences,1);
 document.scene.objects[0].provenance='HARDWARE_OBSERVATION';document.scene.calibration.status='ESTIMATED_3D';
 assert.match(guideState(document).source,/Caller-declared/);assert.match(guideState(document).coordinates,/uncertainty/);
 document.scene.objects[0].provenance='ASSUMPTION';delete document.scene.calibration;
 assert.match(guideState(document).source,/User-declared/);
});
test('supported imports retain source bytes and reject unrelated JSON',()=>{
 const scene={schema_version:'2.0',objects:[]};assert.equal(importDocument(scene).scene,scene);
 const project={schema_version:'frontiersight.project/1.0',document:{schema_version:'frontiersight.editor/1.0',scene},checkpoint:{undo:[],redo:[]}};
 assert.equal(importDocument(project).kind,'project');assert.deepEqual(JSON.parse(importDocument(project).recovery).document,project.document);
 assert.equal(importDocument({document:project.document}).scene,scene);
 for(const invalid of [null,{},[],{schema_version:'old'}])assert.throws(()=>importDocument(invalid),/canonical/);
});
test('scene edits, baseline replacement and workspace changes invalidate comparison evidence',()=>{
 const store=createEditorStore();store.replaceScene({schema_version:'2.0',duration_s:5,objects:[{id:'box'}]});store.lockBaseline();
 const ticket={...store.ticket(),baselineRevision:store.baseline.revision};
 const comparison={baseline_digest:'base',alternative_digest:'altered',counterfactual:{frames:[]}};
 assert(store.publishComparison(comparison,ticket));assert(store.comparison);assert(store.result);
 store.edit(document=>document.scene.name='Edited');assert.equal(store.comparison,null);
 assert(!store.publishComparison(comparison,ticket));
 const newTicket={...store.ticket(),baselineRevision:store.baseline.revision};store.lockBaseline();
 assert(!store.publishComparison(comparison,newTicket));
 const current={...store.ticket(),baselineRevision:store.baseline.revision};
 assert(store.publishComparison(comparison,current));const read=store.comparison;read.baseline_digest='mutated';assert.equal(store.comparison.baseline_digest,'base');
 store.reset();assert.equal(store.comparison,null);assert(!store.publishComparison(comparison,current));
});
