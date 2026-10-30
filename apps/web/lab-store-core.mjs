/** Transactional editor document. Renderers and analysis are caches, never owners. */
const copy=value=>structuredClone(value);
const bytes=value=>new TextEncoder().encode(JSON.stringify(value)).length;
const MAX_DOCUMENT_BYTES=512*1024,MAX_HISTORY_BYTES=8*1024*1024;
function jsonData(value,depth=0,budget={nodes:0}){
 if(++budget.nodes>30000||depth>48)throw Error('Editor document exceeds its structural budget');
 if(value===null||typeof value==='string'||typeof value==='boolean')return;
 if(typeof value==='number'&&Number.isFinite(value))return;
 if(typeof value!=='object'||Object.getPrototypeOf(value)!==Object.prototype&&!Array.isArray(value))throw Error('Editor documents require finite JSON data');
 for(const [key,item] of Object.entries(value)){
  if(['__proto__','prototype','constructor','operator_token','secret_key','api_key','authorization'].includes(key.toLowerCase()))throw Error('Credentials and executable object keys cannot enter a scene document');
  jsonData(item,depth+1,budget);
 }
}
export function validateEditorDocument(value){
 jsonData(value);
 if(bytes(value)>MAX_DOCUMENT_BYTES)throw Error('Scene document exceeds 512 KiB; store media bytes separately');
 if(value.schema_version!=='frontiersight.editor/1.0'||typeof value.id!=='string'||!value.id||value.id.length>100)throw Error('Invalid editor document identity or version');
 if(value.scene!==null&&(value.scene?.schema_version!=='2.0'||!Array.isArray(value.scene.objects)))throw Error('Expected the canonical v2 scene');
 for(const field of ['media','robot_models','observations','interventions'])if(!Array.isArray(value[field])||value[field].length>64)throw Error('Invalid bounded editor collection: '+field);
 const ids=value.scene?.objects.map(object=>object.id)||[];
 if(new Set(ids).size!==ids.length)throw Error('Scene object identities must be unique');
 return copy(value);
}
export function newEditorDocument(id='untitled'){
 return {schema_version:'frontiersight.editor/1.0',id,scene:null,media:[],robot_models:[],observations:[],interventions:[]};
}
export function createEditorStore(initial=newEditorDocument()){
 let document=validateEditorDocument(initial),revision=0,epoch=0,undo=[],redo=[],historyBytes=0;
 let derived=null,baseline=null,selection=null,time=0,timelineScale=1,viewportMode='perspective';
 const listeners=new Set();
 const notify=type=>{for(const listener of [...listeners])listener({type,revision,epoch});};
 const invalidate=()=>{derived=null;if(selection&&!document.scene?.objects.some(o=>o.id===selection))selection=null;revision++;};
 const read=()=>copy(document);
 function commit(next,{label='Edit scene',expectedRevision=revision,provenance='ASSUMPTION'}={}){
  if(expectedRevision!==revision)throw Error('Scene changed; review the current revision before applying this edit');
  next=validateEditorDocument(next);
  if(JSON.stringify(next)===JSON.stringify(document))return false;
  const size=bytes(document)+bytes(next);
  historyBytes-=redo.reduce((total,item)=>total+item.bytes,0);
  undo.push({before:document,after:next,label:String(label).slice(0,120),provenance,bytes:size});historyBytes+=size;redo=[];
  while(undo.length>100||historyBytes>MAX_HISTORY_BYTES){historyBytes-=undo.shift().bytes;}
  document=next;invalidate();notify('document');return true;
 }
 function restore(direction){
  const source=direction==='undo'?undo:redo,target=direction==='undo'?redo:undo;
  if(!source.length)return false;
  const command=source.pop();target.push(command);document=copy(direction==='undo'?command.before:command.after);
  invalidate();notify('document');return true;
 }
 return {
  read,commit,
  get revision(){return revision;},
  get epoch(){return epoch;},
  get canUndo(){return undo.length>0;},get canRedo(){return redo.length>0;},
  get selection(){return selection;},get time(){return time;},get timelineScale(){return timelineScale;},get viewportMode(){return viewportMode;},
  get result(){return derived?copy(derived):null;},get baseline(){return baseline?copy(baseline):null;},
  get history(){return undo.map(({label,provenance})=>({label,provenance}));},
  ticket:()=>({revision,epoch}),current:ticket=>ticket?.revision===revision&&ticket?.epoch===epoch,
  edit(mutator,options){const next=read();mutator(next);return commit(next,options);},
  replaceScene(scene,options){return this.edit(next=>{next.scene=copy(scene);},options);},
  undo:()=>restore('undo'),redo:()=>restore('redo'),
  publish(result,ticket){if(!this.current(ticket))return false;derived=copy(result);notify('result');return true;},
  lockBaseline(){if(!document.scene)throw Error('Load a scene first');baseline={scene:copy(document.scene),revision};notify('baseline');},
  select(id){if(id!==null&&!document.scene?.objects.some(object=>object.id===id))throw Error('Unknown scene object');selection=id;notify('selection');},
  setTime(value){const duration=document.scene?.duration_s||0;if(!Number.isFinite(value))throw Error('Time must be finite');time=Math.max(0,Math.min(duration,value));notify('time');},
  setTimelineScale(value){if(!Number.isFinite(value)||value<.25||value>32)throw Error('Timeline zoom must be .25..32');timelineScale=value;notify('view');},
  setViewportMode(value){if(!['perspective','top','front','side','orthographic'].includes(value))throw Error('Unsupported camera mode');viewportMode=value;notify('view');},
  subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);},
  reset(id='untitled'){epoch++;revision++;document=newEditorDocument(id);undo=[];redo=[];historyBytes=0;derived=null;baseline=null;selection=null;time=0;notify('reset');},
  checkpoint(maxBytes=64000){
   const value={undo:[],redo:[]};
   for(const key of ['undo','redo'])for(const entry of (key==='undo'?undo:redo).slice(-5).reverse()){
    const next=copy(entry);value[key].unshift(next);if(bytes(value)>maxBytes){value[key].shift();break;}
   }
   return value;
  },
  export(){return JSON.stringify({document:read(),revision,checkpoint:{undo:copy(undo),redo:copy(redo)}},null,2);},
  recover(serialized){
   if(typeof serialized!=='string'||serialized.length>MAX_HISTORY_BYTES)throw Error('Recovery exceeds its resource budget');
   const value=JSON.parse(serialized),next=validateEditorDocument(value.document),checkpoint=value.checkpoint||{undo:[],redo:[]};
   let size=0;const stacks={undo:[],redo:[]};
   for(const key of ['undo','redo']){
    if(!Array.isArray(checkpoint[key])||checkpoint[key].length>100)throw Error('Invalid history checkpoint');
    for(const command of checkpoint[key]){
     const before=validateEditorDocument(command.before),after=validateEditorDocument(command.after),count=bytes(before)+bytes(after);size+=count;
     if(size>MAX_HISTORY_BYTES||typeof command.label!=='string')throw Error('Invalid history budget or command');
     stacks[key].push({before,after,label:command.label.slice(0,120),provenance:String(command.provenance||'ASSUMPTION'),bytes:count});
    }
   }
   if(stacks.undo.length&&JSON.stringify(stacks.undo.at(-1).after)!==JSON.stringify(next))throw Error('Undo checkpoint does not match document');
   if(stacks.redo.length&&JSON.stringify(stacks.redo.at(-1).before)!==JSON.stringify(next))throw Error('Redo checkpoint does not match document');
   document=next;undo=stacks.undo;redo=stacks.redo;historyBytes=size;invalidate();notify('document');return true;
  },
 };
}
export const editor=createEditorStore();
