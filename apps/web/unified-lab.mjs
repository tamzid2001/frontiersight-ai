/** Unified editor orchestration. Physics remains in services.api.physical. */
import {editor} from './lab-store-core.mjs';
const $=id=>document.getElementById(id),host=$('ul-panel-host');
const panes={world:$('view-physical'),video:$('view-studio'),planar:$('view-planar'),counterfactual:$('view-counterfactual')};
for(const pane of Object.values(panes))host.append(pane);
const analysis=document.createElement('details');analysis.className='card ul-analysis-drawer';const summary=document.createElement('summary');summary.textContent='Physics, clearance & evidence';analysis.append(summary);$('ul-tracks').parentElement.after(analysis);for(const node of [...panes.world.querySelector('.pi-main').children])if(!node.classList.contains('pi-stage-card')&&node.id!=='pi-status')analysis.append(node);
const stylesheet=document.createElement('link');stylesheet.rel='stylesheet';stylesheet.href='/unified-lab.css';document.head.append(stylesheet);
$('ul-worker-connection').append($('edge-connection-controls'),$('edge-status'));
$('ul-worker-live').append($('edge-live-panel'));
const workerLink=document.createElement('button');workerLink.type='button';workerLink.textContent='Configure worker in Results';workerLink.onclick=()=>window.goto('devices');$('edge-studio-panel').querySelector('summary').after(workerLink);
const legacyVideo=document.createElement('details');legacyVideo.className='card';const legacySummary=document.createElement('summary');legacySummary.textContent='Archived 2D track fixtures and analysis';legacyVideo.append(legacySummary);while(panes.video.firstElementChild&&panes.video.firstElementChild.id!=='edge-studio-panel')legacyVideo.append(panes.video.firstElementChild);panes.video.append(legacyVideo);$('edge-studio-panel').open=true;
const migrate=document.createElement('button');migrate.type='button';migrate.textContent='Use this 2D input as an assumed 3D initial state';migrate.title='Preserve the source document; metric height is an explicit assumption';panes.planar.prepend(migrate);
migrate.onclick=async()=>{try{await window.ensurePhysical();await window.frontierPhysical.upgrade(window.frontierPlanar.scene());await openPanel('world');}catch(error){message(error.message,true);}};
let panel='world',playing=false,rafTime=0,cloudId=null,cloudVersion=null,saveTimer,saving=false,saveAgain=false,snap=false;
function message(value,error=false){$('ul-message').textContent=value;$('ul-message').classList.toggle('error',error);}
let cachedResult=null,trackWindow={start:0,visible:30};
function result(){return cachedResult;}
export async function openPanel(value='world'){
 if(!['world','planar','video','counterfactual','legacy2d','legacy-counterfactual'].includes(value))value='world';panel=value;
 for(const pane of Object.values(panes))pane.classList.remove('on');
 host.classList.toggle('ul-video-mode',value==='video');
 if(value==='legacy2d'){panes.planar.classList.add('on');window.frontierPlanar.start();}
 else if(value==='legacy-counterfactual'){panes.counterfactual.classList.add('on');window.frontierPlanar.counterfactual();}
 else{panes.world.classList.add('on');await window.ensurePhysical();await window.frontierPhysical.ready;if(value==='planar')window.frontierPhysical.control('top');if(value==='video'){panes.video.classList.add('on');await import('./edge-studio.mjs');}if(value==='counterfactual'&&editor.read().scene)$('pi-compare').click();}
 document.querySelectorAll('[data-lab-panel]').forEach(button=>button.setAttribute('aria-selected',String(button.dataset.labPanel===value)));
 const uri=new URL(location.href);if(uri.pathname==='/create'){if(value==='world')uri.searchParams.delete('panel');else uri.searchParams.set('panel',value);history.replaceState(history.state,'',uri);}
 if(value.startsWith('legacy'))message('Archived planar migration input. Import explicitly assumed initial states into the canonical scene; source data stays unchanged.');
 else message('Simulation only · one canonical document and shared timeline.');
}
export async function openDevices(){
 await window.ensurePhysical();await import('./edge-studio.mjs');
 $('ul-worker-capabilities').textContent='Disconnected. Connect to read actual worker capabilities; no online devices are fabricated.';
}
for(const button of document.querySelectorAll('[data-legacy-panel]'))button.onclick=()=>openPanel(button.dataset.legacyPanel==='planar'?'legacy2d':'legacy-counterfactual');
for(const button of document.querySelectorAll('[data-lab-panel]'))button.onclick=()=>openPanel(button.dataset.labPanel).catch(error=>message(error.message,true));
$('ul-copy-worker').onclick=async()=>{try{const url=new URL($('edge-url').value);if(!['localhost','127.0.0.1'].includes(url.hostname)||!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash||url.pathname!=='/')throw Error('Enter a loopback worker origin');await navigator.clipboard.writeText(url.origin);$('ul-worker-copy-status').textContent='Worker URL copied. Operator credentials were not copied.';}catch(error){$('ul-worker-copy-status').textContent=error.message;}};
function download(value,name){const url=URL.createObjectURL(new Blob([value],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function save(){
 if(!editor.read().scene)throw Error('Load a scene first');
 if(saving){saveAgain=true;return;}saving=true;const ticket=editor.ticket();$('ul-save-status').textContent='Saving…';
 try{const document=editor.read(),body={name:document.scene.name,scene:{schema_version:'frontiersight.project/1.0',document,checkpoint:editor.checkpoint()}};
 if(cloudId){body.id=cloudId;body.expectedVersion=cloudVersion;}
 const response=await window.api('/api/v1/scenes/'+(cloudId?'update':'create'),{method:'POST',body:JSON.stringify(body)});
 if(ticket.epoch!==editor.epoch)return;
 if(response.status>=300)throw Error(response.body.error||'Cloud storage unavailable');
 cloudId=response.body.id||cloudId;cloudVersion=response.body.version;if(!editor.current(ticket)){saveAgain=true;return;}$('ul-save-status').textContent='Saved · revision '+editor.revision;
 }finally{saving=false;if(saveAgain){saveAgain=false;clearTimeout(saveTimer);saveTimer=setTimeout(()=>save().catch(error=>{$('ul-save-status').textContent='Not saved';message(error.message,true);}),1500);}}
}
async function applyScene(next,label){await window.ensurePhysical();return window.frontierPhysical.apply(next,label);}
async function objectCommand(command){const document=editor.read();if(!document.scene)throw Error('Load a scene');const next=document.scene;const id=editor.selection||$('pi-object').value;const selected=next.objects.find(o=>o.id===id);if(!selected)throw Error('Select a component');
 if(command==='delete'){if(next.objects.some(o=>o.parent_id===id))throw Error('Delete or detach child components before their parent');if(next.objects.length===1)throw Error('Keep at least one object');next.objects=next.objects.filter(o=>o.id!==id);next.excluded_pairs=(next.excluded_pairs||[]).filter(pair=>!pair.includes(id));}
 else{const item=structuredClone(selected);let n=1;while(next.objects.some(o=>o.id===id.slice(0,55)+'_copy'+n))n++;item.id=id.slice(0,55)+'_copy'+n;item.label=(item.label||id)+' copy';item.pose.position_m[0]+=.5;if(item.waypoints)for(const point of item.waypoints)point.position_m[0]+=.5;next.objects.push(item);}
 await applyScene(next,command==='delete'?'Delete component':'Duplicate component');
}
async function command(name){
 if(['frame-back','frame-next'].includes(name)){editor.setTime(editor.time+(name==='frame-back'?-1:1)*(editor.read().scene?.step_s||.1));return;}
 if(name==='play'){playing=!playing;return;}if(name==='pause'){playing=false;return;}
 if(name==='timeline-fit'){editor.setTimelineScale(1);return;}
 if(name==='timeline-in'||name==='timeline-out'){editor.setTimelineScale(Math.max(.25,Math.min(32,editor.timelineScale*(name==='timeline-in'?2:.5))));return;}
 if(name==='save'){await save();return;}
 if(name==='export'||name==='download-draft'){download(editor.export(),'frontiersight-editor.json');return;}
 if(name==='duplicate'||name==='delete'){await objectCommand(name);return;}
 await window.ensurePhysical();
 if(name==='undo'||name==='redo'){await window.frontierPhysical[name]();return;}
 if(name==='run'){await window.frontierPhysical.run();return;}
 if(name==='compare'){$('pi-compare').click();await openPanel('world');return;}
 if(name==='snap'){snap=!snap;document.querySelector('[data-ul="snap"]').setAttribute('aria-pressed',String(snap));window.frontierPhysical.control('snap',snap);return;}
 window.frontierPhysical.control(name);if(['grid','axes'].includes(name)){const button=document.querySelector('[data-ul="'+name+'"]');button.setAttribute('aria-pressed',String(button.getAttribute('aria-pressed')!=='true'));}
 if(['select','move','rotate','scale'].includes(name))for(const button of document.querySelectorAll('[data-ul="select"],[data-ul="move"],[data-ul="rotate"],[data-ul="scale"]'))button.setAttribute('aria-pressed',String(button.dataset.ul===name));
}
for(const button of document.querySelectorAll('[data-ul]'))button.onclick=()=>command(button.dataset.ul).catch(error=>message(error.message,true));
$('ul-time').oninput=()=>{playing=false;editor.setTime(Number($('ul-time').value));};
$('ul-document-file').onchange=async event=>{try{const file=event.target.files[0];if(!file)return;if(file.size>8*1024*1024)throw Error('Editor recovery file exceeds 8 MiB');const ticket=editor.ticket(),raw=await file.text(),value=JSON.parse(raw);if(!editor.current(ticket))throw Error('Workspace changed during import');await window.ensurePhysical();await window.frontierPhysical.validate(value.document.scene);if(!editor.current(ticket))throw Error('Workspace changed during validation');editor.recover(raw);await window.frontierPhysical.run();message('Document and bounded undo history recovered. Media references need their original local files.');}catch(error){message(error.message,true);}};
function renderTracks(){
 const scene=editor.read().scene,record=result(),host=$('ul-tracks');host.replaceChildren();if(!scene)return;
 const duration=scene.duration_s,visible=duration/editor.timelineScale,start=Math.max(0,Math.min(Math.max(0,duration-visible),editor.time-visible/2));trackWindow={start,visible};
 for(const object of scene.objects){const row=document.createElement('div');row.className='ul-track';const label=document.createElement('button');label.textContent=object.label||object.id;label.onclick=()=>editor.select(object.id);const canvas=document.createElement('canvas');canvas.width=900;canvas.height=34;canvas.setAttribute('aria-label',(object.label||object.id)+' modeled altitude timeline');row.append(label,canvas);const playhead=document.createElement('span');playhead.className='ul-playhead';row.append(playhead);host.append(row);const ctx=canvas.getContext('2d');ctx.strokeStyle='#27516b';ctx.beginPath();ctx.moveTo(0,17);ctx.lineTo(900,17);ctx.stroke();
 const samples=record?.frames.map(f=>[f.t_s,f.objects.find(o=>o.id===object.id)?.position_m[2]]).filter(p=>Number.isFinite(p[1]))||[];const max=Math.max(1,...samples.map(p=>p[1])),min=Math.min(0,...samples.map(p=>p[1]));ctx.strokeStyle='#37bada';ctx.beginPath();samples.forEach(([t,z],i)=>{const x=(t-start)/visible*900,y=29-(z-min)/Math.max(.001,max-min)*24;if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();ctx.fillStyle='#8c6bff';for(const point of object.waypoints||[])ctx.fillRect((point.t_s-start)/visible*900-3,3,6,28);ctx.fillStyle='#61d1ff';ctx.fillRect((editor.time-start)/visible*900,0,1,34);
 canvas.onclick=event=>{const rect=canvas.getBoundingClientRect();editor.setTime(start+(event.clientX-rect.left)/rect.width*visible);editor.select(object.id);};
 canvas.onpointerdown=event=>{const rect=canvas.getBoundingClientRect(),t=start+(event.clientX-rect.left)/rect.width*visible;const point=object.waypoints?.find(p=>Math.abs(p.t_s-t)<visible*8/rect.width);if(!point)return;event.preventDefault();canvas.setPointerCapture(event.pointerId);const ticket=editor.ticket();canvas.onpointerup=async up=>{canvas.onpointerup=null;try{if(!editor.current(ticket))throw Error('Scene changed during keyframe edit');const next=editor.read().scene,entry=next.objects.find(o=>o.id===object.id).waypoints.find(p=>p.t_s===point.t_s);entry.t_s=Math.max(0,Math.min(duration,start+(up.clientX-rect.left)/rect.width*visible));if(snap)entry.t_s=Math.round(entry.t_s/scene.step_s)*scene.step_s;await applyScene(next,'Move timed waypoint');}catch(error){message(error.message,true);}};};
 }
 const events=document.createElement('p');events.className='ul-event-track';events.textContent=record?record.events.length+' computed contact/possible-contact events · '+record.frames.length+' samples · no measured confidence interval':'Run the declared model to compute trajectories and events';host.append(events);
}
function refresh(event){
 const scene=editor.read().scene;$('ul-revision').textContent=scene?(scene.name+' · r'+editor.revision):'No scene loaded';$('ul-clock').textContent=editor.time.toFixed(2)+' s';$('ul-time').max=scene?.duration_s||30;$('ul-time').value=editor.time;
 const working=$('view-physical').getAttribute('aria-busy')==='true';document.querySelector('[data-ul="undo"]').disabled=working||!editor.canUndo;document.querySelector('[data-ul="redo"]').disabled=working||!editor.canRedo;
 if(event?.type==='document'){$('ul-save-status').textContent='Unsaved changes';clearTimeout(saveTimer);if(window.hasSceneSession?.())saveTimer=setTimeout(()=>save().catch(error=>{message(error.message,true);$('ul-save-status').textContent='Not saved';}),1500);}
 if(event?.type==='reset'){clearTimeout(saveTimer);cloudId=null;cloudVersion=null;playing=false;$('ul-save-status').textContent='Workspace cleared';}
 if(event?.type==='result')cachedResult=editor.result;
 if(event?.type==='document'||event?.type==='reset')cachedResult=null;
 if(event?.type!=='time'||editor.time<trackWindow.start||editor.time>trackWindow.start+trackWindow.visible)renderTracks();
 const video=$('edge-video');if(event?.type==='time'&&video?.getAttribute('src')&&Number.isFinite(video.duration)&&Math.abs(video.currentTime-editor.time)>.1)video.currentTime=Math.min(video.duration,editor.time);
 $('ul-tracks').style.setProperty('--ul-progress',Math.max(0,Math.min(1,(editor.time-trackWindow.start)/trackWindow.visible)));
}
editor.subscribe(refresh);refresh();
function tick(now){if(playing&&editor.read().scene){editor.setTime(editor.time+Math.min(.1,(now-rafTime)/1000));if(editor.time>=editor.read().scene.duration_s)playing=false;}rafTime=now;requestAnimationFrame(tick);}requestAnimationFrame(tick);
document.addEventListener('keydown',event=>{if(!$('view-create').classList.contains('on')||event.target.closest('input,textarea,select,[contenteditable=true]'))return;let name;if(event.metaKey||event.ctrlKey){if(event.key.toLowerCase()==='z')name=event.shiftKey?'redo':'undo';if(event.key.toLowerCase()==='y')name='redo';if(event.key.toLowerCase()==='s')name='save';}else name={' ':'play',Delete:'delete',Backspace:'delete',f:'fit','1':'select','2':'move','3':'rotate','4':'scale',Escape:'select'}[event.key];if(name){event.preventDefault();command(name).catch(error=>message(error.message,true));}});
window.frontierLab={editor,refresh,openPanel,save,openProject:async record=>{await window.ensurePhysical();const value=record.scene||record.payload;if(value.schema_version==='frontiersight.project/1.0'){editor.recover(JSON.stringify({document:value.document,checkpoint:value.checkpoint}));cloudId=record.id;cloudVersion=record.version;await window.frontierPhysical.run();await openPanel('world');}}};
