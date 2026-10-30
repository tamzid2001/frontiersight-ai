import test from 'node:test';
import assert from 'node:assert/strict';
import {createEditorStore,newEditorDocument,validateEditorDocument} from '../apps/web/lab-store-core.mjs';
const scene=()=>({schema_version:'2.0',duration_s:10,objects:[{id:'box',pose:{position_m:[0,0,0]}}]});
test('transactional history restores actual scene, invalidates derived results and branches redo',()=>{
 const store=createEditorStore();store.replaceScene(scene());store.lockBaseline();const first=store.ticket();assert(store.publish({value:1},first));
 store.edit(d=>d.scene.objects[0].pose.position_m[2]=3,{label:'Lift box'});assert.equal(store.result,null);assert(!store.publish({value:'stale'},first));
 const edited=store.revision;assert(store.undo());assert.equal(store.read().scene.objects[0].pose.position_m[2],0);assert(store.revision>edited);assert(store.redo());
 assert.equal(store.read().scene.objects[0].pose.position_m[2],3);assert.equal(store.baseline.scene.objects[0].pose.position_m[2],0);
 store.undo();store.edit(d=>d.scene.name='Alternative');assert(!store.canRedo);assert(!store.redo());
});
test('document copies, revision preconditions and tenant epochs prevent stale private scene resurrection',()=>{
 const store=createEditorStore();store.replaceScene(scene());const ticket=store.ticket(),read=store.read();read.scene.objects[0].id='changed';assert.equal(store.read().scene.objects[0].id,'box');
 assert.throws(()=>store.edit(d=>d.scene.name='stale',{expectedRevision:0}),/changed/);store.reset();assert(!store.current(ticket));assert(!store.publish({secret:true},ticket));assert.equal(store.result,null);assert(!store.undo());
});
test('selection, one timeline and view preferences never mutate geometry or create edit history',()=>{
 const store=createEditorStore();store.replaceScene(scene());const revision=store.revision,before=store.read();let calls=0;const unsubscribe=store.subscribe(()=>calls++);
 store.select('box');assert.throws(()=>store.select('missing'));store.select(null);store.setTime(20);assert.equal(store.time,10);store.setTime(-1);assert.equal(store.time,0);assert.throws(()=>store.setTime(NaN));
 store.setTimelineScale(4);assert.throws(()=>store.setTimelineScale(100));store.setViewportMode('front');assert.throws(()=>store.setViewportMode('bad'));assert.deepEqual(store.read(),before);assert.equal(store.revision,revision);assert(calls>0);unsubscribe();
});
test('bounded finite data, safe collections and recoverable history reject unsafe document payloads',()=>{
 const store=createEditorStore();assert(!store.undo());assert(!store.commit(store.read()));assert.throws(()=>store.lockBaseline());
 for(const value of [NaN,Infinity,()=>{},new Date()]){const d=newEditorDocument();d.extra=value;assert.throws(()=>validateEditorDocument(d));}
 for(const key of ['api_key','operator_token','constructor']){const d=newEditorDocument();d[key]='unsafe';assert.throws(()=>validateEditorDocument(d));}
 for(const mutate of [d=>d.schema_version='bad',d=>d.id='',d=>d.media={},d=>d.scene={schema_version:'old'},d=>d.scene={schema_version:'2.0',objects:[{id:'a'},{id:'a'}]},d=>d.extra='x'.repeat(600000),d=>d.media=Array(65).fill('x')]){const d=newEditorDocument();mutate(d);assert.throws(()=>validateEditorDocument(d));}
 store.replaceScene(scene());const serialized=store.export();store.reset();store.recover(serialized);assert.equal(store.read().scene.objects[0].id,'box');
 for(let i=0;i<110;i++)store.edit(d=>d.scene.name=String(i));assert.equal(store.history.length,100);assert(store.undo());assert(store.canRedo);assert.throws(()=>store.recover('invalid'));
});
test('exported transactions survive recovery, with bounded cloud checkpoints and coherent undo',()=>{
 const store=createEditorStore();store.replaceScene(scene());store.edit(d=>d.scene.name='A');store.edit(d=>d.scene.name='B');store.undo();
 const recovered=createEditorStore();recovered.recover(store.export());assert(recovered.canUndo);assert(recovered.canRedo);recovered.redo();assert.equal(recovered.read().scene.name,'B');recovered.undo();assert.equal(recovered.read().scene.name,'A');
 assert.equal(store.checkpoint(1).undo.length,0);assert(store.checkpoint().undo.length>0);
 const bad=JSON.parse(store.export());bad.checkpoint.undo.at(-1).after.scene.name='tampered';assert.throws(()=>recovered.recover(JSON.stringify(bad)),/does not match/);
 bad.checkpoint={undo:{},redo:[]};assert.throws(()=>recovered.recover(JSON.stringify(bad)),/checkpoint/);
 bad.checkpoint={undo:[],redo:[{before:newEditorDocument('different'),after:newEditorDocument(),label:'x'}]};assert.throws(()=>recovered.recover(JSON.stringify(bad)),/Redo checkpoint/);
 const deep=newEditorDocument();let node=deep;for(let i=0;i<50;i++){node.child={};node=node.child;}assert.throws(()=>validateEditorDocument(deep),/structural/);
 const many=newEditorDocument();many.extra=Array(30001).fill(0);assert.throws(()=>validateEditorDocument(many),/structural/);
});
