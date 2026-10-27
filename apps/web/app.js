const $=id=>document.getElementById(id);
const state={scenario:null,data:null,t:0,playing:false,run:null,cf:null};

// ---- Real entity rendering (top-down vector silhouettes, heading-oriented) ----
// Each kind is drawn in local space pointing +x, scaled by footprint radius px.
// Colours are realistic object colours (not theme accents) so a forklift reads
// as a forklift in either theme; trails/labels keep the category accent colour.
const REAL={forklift:{body:"#e9a13b",dark:"#8a5a16",metal:"#9aa7b8",tyre:"#20262e"},
 pedestrian:{vest:"#ff7847",skin:"#f0bd93",dark:"#7a2d12"},
 robot:{body:"#aebfd2",dark:"#5d7186",dome:"#38c6d9",tyre:"#20262e"},
 vehicle:{body:"#4d8dff",dark:"#2f5fb3",glass:"#bcd7ff",tyre:"#20262e"},
 cyclist:{frame:"#b07fe8",skin:"#f0bd93",tyre:"#20262e"},
 shelf:{body:"#8a6f4d",box:"#b08d5f",dark:"#5d4630"}, object:{body:"#9aa7b8",dark:"#5d7186"}};
function rr(x,a,b,w,h,r){x.beginPath();x.roundRect(a,b,w,h,r);}
function drawEntity(x,kind,cx,cy,s,heading,phase){
 const C=REAL[kind]||REAL.object; if(s<3)s=3;
 x.save(); x.translate(cx,cy); if(kind!=="shelf")x.rotate(heading||0);
 if(kind==="forklift"){
   x.fillStyle=C.tyre;[[-.62,-.52],[.42,-.52],[-.62,.52],[.42,.52]].forEach(w=>{x.beginPath();x.arc(w[0]*s,w[1]*s,s*.17,0,7);x.fill();});
   x.fillStyle=C.body; rr(x,-1.05*s,-.55*s,1.85*s,1.1*s,s*.22); x.fill();
   x.fillStyle=C.dark; rr(x,-1.05*s,-.55*s,.42*s,1.1*s,s*.18); x.fill();
   x.fillStyle="#374151"; x.fillRect(.62*s,-.6*s,.17*s,1.2*s);
   x.strokeStyle=C.metal; x.lineWidth=Math.max(1.4,s*.09);
   [-.3,.3].forEach(o=>{x.beginPath();x.moveTo(.79*s,o*s);x.lineTo(1.42*s,o*s);x.stroke();});
   x.fillStyle="#f6c453"; x.beginPath(); x.arc(-.25*s,0,s*.16,0,7); x.fill();
 } else if(kind==="pedestrian"){
   const sw=Math.sin(phase||0)*.45;
   x.strokeStyle=C.dark; x.lineWidth=Math.max(1.6,s*.16); x.lineCap="round";
   x.beginPath(); x.moveTo(0,0); x.lineTo(-.55*s,(0.5+sw)*s*.62); x.moveTo(0,0); x.lineTo(-.55*s,(-.5+sw)*s*.62); x.stroke();
   x.beginPath(); x.moveTo(.1*s,0); x.lineTo(.75*s,.62*s); x.moveTo(.1*s,0); x.lineTo(.75*s,-.62*s); x.stroke();
   x.fillStyle=C.vest; x.beginPath(); x.ellipse(.05*s,0,.62*s,.5*s,0,0,7); x.fill();
   x.fillStyle=C.skin; x.beginPath(); x.arc(.18*s,0,.3*s,0,7); x.fill();
 } else if(kind==="robot"){
   x.fillStyle=C.tyre;[[-.6,-.55],[.6,-.55],[-.6,.55],[.6,.55]].forEach(w=>{x.beginPath();x.arc(w[0]*s,w[1]*s,s*.15,0,7);x.fill();});
   x.fillStyle=C.body; rr(x,-.85*s,-.6*s,1.7*s,1.2*s,s*.3); x.fill();
   x.fillStyle=C.dark; x.fillRect(.55*s,-.6*s,.3*s,1.2*s);
   x.fillStyle=C.dome; x.beginPath(); x.arc(0,0,s*.34,0,7); x.fill();
   x.fillStyle="#0b2b33"; x.beginPath(); x.arc(.12*s,0,s*.1,0,7); x.fill();
 } else if(kind==="vehicle"){
   x.fillStyle=C.tyre;[[-.75,-.58],[.75,-.58],[-.75,.58],[.75,.58]].forEach(w=>{x.beginPath();x.arc(w[0]*s,w[1]*s,s*.16,0,7);x.fill();});
   x.fillStyle=C.body; rr(x,-1.25*s,-.55*s,2.5*s,1.1*s,s*.3); x.fill();
   x.fillStyle=C.glass; rr(x,.15*s,-.45*s,.62*s,.9*s,s*.12); x.fill();
   x.fillStyle=C.dark; rr(x,-.95*s,-.45*s,.5*s,.9*s,s*.12); x.fill();
 } else if(kind==="cyclist"){
   x.strokeStyle=C.tyre; x.lineWidth=Math.max(1.3,s*.08);
   [-.62,.62].forEach(o=>{x.beginPath();x.arc(o*s,0,s*.34,0,7);x.stroke();});
   x.strokeStyle=C.frame; x.lineWidth=Math.max(1.5,s*.11); x.beginPath();
   x.moveTo(-.62*s,0); x.lineTo(0,-.1*s); x.lineTo(.62*s,0); x.moveTo(0,-.1*s); x.lineTo(.25*s,-.5*s); x.stroke();
   x.fillStyle=C.skin; x.beginPath(); x.arc(.18*s,-.42*s,.24*s,0,7); x.fill();
 } else if(kind==="shelf"){
   x.fillStyle=C.body; x.fillRect(-1.1*s,-.8*s,2.2*s,1.6*s);
   x.fillStyle=C.box; const bw=2.2*s/3,bh=1.6*s/2;
   for(let i=0;i<3;i++)for(let k=0;k<2;k++)x.fillRect(-1.1*s+3+i*bw,-.8*s+3+k*bh,bw-6,bh-6);
   x.strokeStyle=C.dark; x.lineWidth=2; x.strokeRect(-1.1*s,-.8*s,2.2*s,1.6*s);
 } else { x.fillStyle=C.body; rr(x,-.8*s,-.55*s,1.6*s,1.1*s,s*.25); x.fill(); }
 x.restore();}
function labelPill(x,text,cx,cy,accent){
 x.save(); x.font="600 11.5px system-ui"; const w=x.measureText(text).width+14;
 const cs=getComputedStyle(document.documentElement);
 x.globalAlpha=.9; x.fillStyle=cs.getPropertyValue("--panel2"); rr(x,cx,cy-9,w,18,9); x.fill();
 x.globalAlpha=1; x.strokeStyle=accent||"#888"; x.lineWidth=1; rr(x,cx,cy-9,w,18,9); x.stroke();
 x.fillStyle=cs.getPropertyValue("--ink"); x.fillText(text,cx+7,cy+4); x.restore();}
function headingAt(track,t){const p0=posAt(track,t),p1=posAt(track,Math.min(t+0.35, track.points[track.points.length-1][0]));
 const dx=p1[1]-p0[1],dy=p1[2]-p0[2]; if(Math.hypot(dx,dy)<1e-6)return null; return Math.atan2(-dy,dx);}

const COL={forklift:"#38c6d9",pedestrian:"#f2b04a",robot:"#2dd4a8",vehicle:"#4dc9ff",cyclist:"#c792ff",shelf:"#5b6b9f",person:"#f2b04a",object:"#e8edf6"};

// tabs
function showView(v){
 document.querySelectorAll("#tabs button").forEach(x=>{const on=x.dataset.view===v;x.classList.toggle("on",on);
  if(on)x.setAttribute("aria-current","page");else x.removeAttribute("aria-current");});
 document.querySelectorAll(".view").forEach(s=>s.classList.toggle("on",s.id==="view-"+v));
 if(v==="create"){if(typeof labDraw==="function")labDraw();
   if(localStorage.getItem("fs-view-lab")==="3d"&&state.labView!=="3d")setLabView("3d");}
 if(v==="studio"&&localStorage.getItem("fs-view-studio")==="3d"&&state.studioView!=="3d")setStudioView("3d");
 if(v==="counterfactual"&&localStorage.getItem("fs-view-cf")==="3d"&&state.cfView!=="3d")setCfView("3d");
 if(v==="counterfactual"){syncLabToCfIfNewer().then(changed=>{syncCounterfactual();
   if(!changed&&state.cfData){drawCfMap();drawCfChart();}});}}
document.querySelectorAll("#tabs button").forEach(b=>b.onclick=()=>showView(b.dataset.view));
function goto(v){showView(v);}

async function diag(){try{const d=await(await fetch("/api/diagnostics")).json();
 $("mode").textContent=d.meta_configured?"● LIVE META":"● FIXTURE REPLAY";
 $("mode").className="pill "+(d.meta_configured?"ok":"warn");
 $("hero-diag").textContent=`Meta: ${d.meta_configured?"configured":"not configured"} · Spark ${d.spark_model} · SAM ${d.sam_model} · mode ${d.mode}`;
 $("diag").textContent=JSON.stringify(d,null,2);}catch(e){$("mode").textContent="● API OFFLINE";}}

async function loadScenarios(){let d;try{d=await(await fetch("/api/scenarios")).json();}
 catch(e){$("scenario-list").innerHTML='<div class="card wide"><h3>Could not load scenarios</h3><p class="dim">The API is unreachable. Check <code>/api/health</code>, then reload. Nothing has been simulated or hidden.</p><button onclick="location.reload()">Reload</button></div>';return;}
 state.scenarioList=d.scenarios; populateCfScene(); populateStudioWorkspaces();
 $("scenario-list").innerHTML=d.scenarios.map(s=>`<div class="card scenario-card" data-search="${(s.id+" "+s.description).toLowerCase()}" data-card="${s.id}"><h3>${s.id}</h3><p class="dim">${s.description}</p><p class="dim counts" data-counts="${s.id}">loading counts…</p><button onclick="pick('${s.id}')">Open in Studio →</button></div>`).join("");
 d.scenarios.forEach(async s=>{try{const f=await(await fetch("/api/scenarios?name="+s.id)).json();
  const el=document.querySelector(`[data-counts="${s.id}"]`);const n=f.tracks.length;
  if(el){const smooth=Object.values(f.ground_truth||{}).filter(g=>g.curve==="smooth").length;
   el.textContent=`${n} objects · ${n*(n-1)/2} analysed pairs · ${f.calibration.metres_per_pixel?"calibrated (m)":"pixel space"}${smooth?` · ${smooth} curved path${smooth>1?"s":""}`:""}`;}}catch(e){}});
 const v=await(await fetch("/api/validate")).json();
 $("validation-list").innerHTML=v.cases.map(c=>`<li>${c.passed?"✓":"✗"} <b>${c.case}</b> — <span class="dim">${c.detail}</span></li>`).join("");
 renderMyScenes();
 state.data=await(await fetch("/api/scenarios?name="+d.scenarios[0].id)).json();state.scenario=d.scenarios[0].id;
 renderObjects();draw();populateCfScene();   // silent preload: user stays on Overview
}
function renderMyScenes(){const host=$("scenario-list");if(!host)return;
 const old=$("my-scenes-card");if(old)old.remove();const oldRuns=$("runs-card");if(oldRuns)oldRuns.remove();
 loadWorkspaces(); renderRuns();
 let mine=[];
 if(true){return;}const div=document.createElement("div");div.className="card wide";div.id="my-scenes-card";
 div.innerHTML=`<h3>My scenes (this browser)</h3>`+mine.map((s,i)=>`<p><b>${s.id}</b> <span class="dim">${new Date(s.when).toLocaleString()} · ${s.tracks.length} objects</span>
  <button data-mine="${i}" class="ghostbtn">Re-analyse</button> <button data-del="${i}" class="ghostbtn">Delete</button></p>`).join("");
 host.appendChild(div);
 div.querySelectorAll("[data-mine]").forEach(b=>b.onclick=()=>analyzeCustom(mine[+b.dataset.mine].tracks,mine[+b.dataset.mine].id));
 div.querySelectorAll("[data-del]").forEach(b=>b.onclick=()=>{mine.splice(+b.dataset.del,1);localStorage.setItem(sceneStoreKey(),JSON.stringify(mine));div.remove();renderMyScenes();});}
function resetRunState(){state.run=null;state.cfData=null;state.highlight=null;state.cfAgentId=null;
 state.approvals={};const ev=$("events");if(ev)ev.innerHTML='<li class="dim">Run analysis to detect events.</li>';
 const tr=$("trace");if(tr)tr.innerHTML='<li class="dim">Run analysis to populate the trace.</li>';
 if(typeof syncApprovalUI==="function")syncApprovalUI();}
window.pick=async id=>{let d;try{d=await(await fetch("/api/scenarios?name="+id)).json();}
 catch(e){toast("Could not load scenario "+id+" — check the API and try again.","err");return;}
 resetRunState();state.data=d;state.scenario=id;state.t=0;state.dataUpdatedAt=Date.now();
 $("scenario-select").value=id;renderObjects();draw();populateCfScene();goto("studio");};
function populateStudioWorkspaces(){const sel=$("scenario-select");if(!sel)return;
 const cur=sel.value;
 const builtins=(state.scenarioList||[]).map(s=>`<option value="${s.id}">${s.id}</option>`).join("");
 const mine=(state.workspaces||[]).filter(w=>w.objects||w.tracks);
 sel.innerHTML=`<optgroup label="Built-in examples">${builtins}</optgroup>`+
  (mine.length?`<optgroup label="My workspaces">${mine.map(w=>`<option value="ws:${w.key}">${w.name} (${w.kind==="frames"?"SAM frames":"Lab scene"})</option>`).join("")}</optgroup>`:"");
 if([...sel.options].some(o=>o.value===cur))sel.value=cur;
 else if(state.scenario&&[...sel.options].some(o=>o.value===state.scenario))sel.value=state.scenario;}
async function objectsToTracks(objects){
 try{const r=await fetch("/api/tracks/from-paths",{method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({objects:objects.map(o=>({object_id:o.id||o.object_id,category:o.category,waypoints:o.waypoints,
    speed:o.speed,radius:o.radius,delay:o.delay,curve:o.curve,mode:o.mode}))})});
  const out=await r.json();if(r.ok&&out.tracks)return out.tracks;}catch(e){}
 // offline fallback: identical browser sampler
 return objects.map(o=>{const T=Math.max(4,Math.min(20,o.delay+pathDur(o)));const pts=[];
  for(let t=0;t<=T+1e-9;t=Math.round((t+0.1)*100)/100){const p=posOnPath(o,t);pts.push([t,p[0],p[1]]);}
  return {object_id:o.id||o.object_id,category:o.category,space:"world",radius:o.radius,source:"USER_CREATED",occluded:[],points:pts};});}
async function loadWorkspaceIntoStudio(w){
 let tracks=w.tracks;
 if(!tracks&&w.objects)tracks=await objectsToTracks(w.objects);
 if(!tracks||!tracks.length){toast("That workspace has no analysable tracks yet.","warn");return;}
 resetRunState();
 state.dataUpdatedAt=Date.now();
 state.data={id:"ws-"+w.id,description:`Your workspace "${w.name}"`,kind:"USER_UPLOADED",
  calibration:{metres_per_pixel:null,frame:tracks[0].space==="world"?"Create Lab stage (metres)":"image (pixels)"},
  disclaimer:"User workspace. Metric claims only when tracks are in world space.",
  tracks,ground_truth:{}};
 state.scenario=state.data.id;state.t=0;
 const sel=$("scenario-select");if(sel)sel.value="ws:"+w.key;
 renderObjects();draw();populateCfScene();goto("studio");
 toast(`Workspace "${w.name}" loaded in the Studio — press Run analysis.`);}
state.studioView="2d";
async function setStudioView(v){state.studioView=v;localStorage.setItem("fs-view-studio",v);
 $("studio-view-2d").setAttribute("aria-pressed",String(v==="2d"));
 $("studio-view-3d").setAttribute("aria-pressed",String(v==="3d"));
 $("stage").classList.toggle("hidden",v==="3d");
 $("studio-3d").classList.toggle("hidden",v!=="3d");
 if(v==="3d"){
  try{
   if(!window.__lab3dMod){window.__lab3dMod=await import("/three-view.js");}
   const mod=window.__lab3dMod;
   const hooks={extent:()=>{if(!state.data)return [16,14];
     let mx=16,my=14;state.data.tracks.forEach(tr=>tr.points.forEach(p=>{mx=Math.max(mx,p[1]);my=Math.max(my,p[2]);}));
     return [Math.ceil(mx*1.08),Math.ceil(my*1.08)];},
    pos:(item,t)=>{const p=posAt(item._tr,t);return p?[p[1],p[2]]:null;}};
   hooks.onContextLost=()=>{toast("3D context was lost (GPU) — returned to 2D playback; nothing was lost.","warn");setStudioView("2d");};
   mod.showStudio3D($("studio-3d"),hooks);
   window.__studio3dSync=(tracks,t)=>mod.syncStudio3D(tracks,t);
   mod.syncStudio3D(state.data?state.data.tracks:[],state.t,true);
  }catch(e){toast("3D view unavailable (WebGL): "+e.message+" — 2D playback is unaffected.","err");setStudioView("2d");}
 } else if(window.__lab3dMod){window.__lab3dMod.hideStudio3D();window.__studio3dSync=null;}
}
$("studio-view-2d").onclick=()=>setStudioView("2d");
$("studio-view-3d").onclick=()=>setStudioView("3d");
$("scenario-select").onchange=e=>{const v=e.target.value;
 if(v.startsWith("ws:")){const w=(state.workspaces||[]).find(x=>x.key===v.slice(3));
  if(w){loadWorkspaceIntoStudio(w);return;}}
 pick(v);};

function renderObjects(){if(!state.data)return;
 const tEnd=Math.max(1,...state.data.tracks.map(t=>t.points.length?t.points[t.points.length-1][0]:0));
 const sc=$("scrub");if(sc)sc.max=tEnd.toFixed(2);state.duration=tEnd;
 $("objects").innerHTML=state.data.tracks.map(t=>`<li class="objrow" data-id="${t.object_id}" title="Click to highlight this track"><b style="color:${COL[t.category]||"#fff"}">●</b> ${t.object_id} · ${t.category} · <span class="dim">${t.source}, ${t.points.length} obs${t.occluded.length?", occluded "+t.occluded.map(o=>o.join("–")+"s").join(","):""}</span></li>`).join("");
 document.querySelectorAll(".objrow").forEach(el=>el.onclick=()=>{state.highlight=state.highlight===el.dataset.id?null:el.dataset.id;draw();});
 populateCfAgents();}

let WORLD={x:15,y:14};
function computeWorld(){if(!state.data)return WORLD;let mx=1,my=1;
 state.data.tracks.forEach(t=>t.points.forEach(p=>{mx=Math.max(mx,p[1]);my=Math.max(my,p[2]);}));
 WORLD={x:mx*1.12,y:my*1.12};return WORLD;}
function px(x,y,W,H){return [x/WORLD.x*W, H-(y/WORLD.y*H)];}
function posAt(track,t){const p=track.points;if(t<=p[0][0])return p[0];if(t>=p[p.length-1][0])return p[p.length-1];
 for(let i=1;i<p.length;i++){if(p[i][0]>=t){const[t0,a]=[p[i-1][0],p[i-1]],[t1,b]=[p[i][0],p[i]];const k=(t-t0)/(t1-t0||1);return[0,a[1]+(b[1]-a[1])*k,a[2]+(b[2]-a[2])*k];}}return p[p.length-1];}
function draw(){if(window.__studio3dSync)window.__studio3dSync(state.data?state.data.tracks:[],state.t);
 const c=$("stage");if(!c||!state.data)return;computeWorld();const x=c.getContext("2d"),W=c.width,H=c.height;
 x.clearRect(0,0,W,H);x.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue("--line");for(let gx=0;gx<=WORLD.x;gx+=2){const[a]=px(gx,0,W,H);x.beginPath();x.moveTo(a,0);x.lineTo(a,H);x.stroke();}
 const _labels=[];
 for(const tr of state.data.tracks){const col=COL[tr.category]||"#fff";const hl=!state.highlight||state.highlight===tr.object_id;
  x.strokeStyle=col+(hl?"aa":"2a");x.lineWidth=hl?2:1;x.beginPath();tr.points.forEach(p=>{const[a,b]=px(p[1],p[2],W,H);p===tr.points[0]?x.moveTo(a,b):x.lineTo(a,b);});x.stroke();
  const occ=tr.occluded.some(o=>state.t>=o[0]&&state.t<=o[1]);
  const cur=posAt(tr,state.t);const[a,b]=px(cur[1],cur[2],W,H);const r=tr.radius/WORLD.x*W;
  x.globalAlpha=hl?1:0.35;
  if(occ){x.strokeStyle="#f26d7d";x.lineWidth=2.5;x.setLineDash([5,4]);x.beginPath();x.arc(a,b,r+7,0,7);x.stroke();x.setLineDash([]);}
  const hd=headingAt(tr,state.t); if(hd!==null)state["hd_"+tr.object_id]=hd;
  drawEntity(x,tr.category,a,b,Math.max(9,r),state["hd_"+tr.object_id]||0,state.t*7);
  _labels.push([`${tr.object_id}${occ?" · OCCLUDED":""}`,a+r+8,b-9,col,hl]);
  x.globalAlpha=1;x.lineWidth=1;}
 _labels.forEach(L=>{x.globalAlpha=L[4]?1:0.4;labelPill(x,L[0],L[1],L[2],L[3]);});x.globalAlpha=1;
 $("clock").textContent="t = "+state.t.toFixed(2)+"s";$("scrub").value=state.t;}
$("scrub").oninput=e=>{state.t=+e.target.value;draw();};
// (play handler replaced by the speed-aware version below)

$("analyze").onclick=async()=>{
 if(state.data&&state.data.kind==="USER_UPLOADED"){try{await analyzeCustom(state.data.tracks,state.scenario);}catch(e){}return;}
 $("analyze-status").textContent="Running bounded agent workflow…";
 let r;try{r=await(await fetch("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({scenario:state.scenario,speed_reduction_pct:+$("sr").value,intervention_t:+$("it").value,human_approved:$("approve").checked})})).json();}
 catch(e){$("analyze-status").textContent="Analysis failed: API unreachable. No results were fabricated.";return;}
 if(!r.run){$("analyze-status").textContent="Analysis failed: "+(r.error||r.detail||"unknown error");return;}
 state.run=r.run;const pairs=r.run.findings.pairs||[];
 const evs=[];pairs.forEach(p=>{if(p.event)evs.push({...p.event,pair:p.pair});});
 $("events").innerHTML=evs.length?evs.map((e,i)=>`<li class="ev" data-t="${e.at_time_s||e.t_star_s||0}">⚠ <b>${e.type}</b> ${e.pair.join(" ↔ ")}<br><span class="dim">${e.ttc_s!=null?"TTC "+e.ttc_s+"s":e.d_min!=null?"d_min "+e.d_min+" "+(e.units||""):""} · click to seek</span></li>`).join(""):'<li class="dim">No proximity events above threshold in this scenario.</li>';
 document.querySelectorAll(".ev").forEach(el=>{el.tabIndex=0;el.setAttribute("role","button");
  const seek=()=>{state.t=+el.dataset.t;draw();};el.onclick=seek;
  el.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();seek();}};});
 $("analyze-status").textContent=`Run ${r.run.run_id} · ${r.run.mode} · ${r.run.stages.filter(s=>s.status==="completed").length}/${r.run.stages.length} stages completed`;
 recordRun({scenario:state.scenario,mode:r.run.mode,run:r.run.run_id,events:(r.run.findings.pairs||[]).filter(p=>p.event).length,pairs:(r.run.findings.pairs||[]).length}); obDone("demo");
 renderTrace(r.run);renderInspector(r);drawCfFromRun(r.run);};
function renderTrace(run){$("trace").innerHTML=run.stages.map(s=>`<li class="${s.status}"><b>${s.name}</b> · ${s.status} · <span class="dim">${s.attribution}${s.artifact?" · artifact "+s.artifact:""}${s.retries?" · retries "+s.retries:""}</span><br><span class="dim mono">${JSON.stringify(s.detail).slice(0,320)}</span></li>`).join("");}
function renderInspector(r){const sc=r.scenario;const mpp=sc.calibration.metres_per_pixel;
 const unitsLine=(sc.tracks[0]&&sc.tracks[0].space==="world")
  ? `<b>Units:</b> metres (world space${mpp?`, declared scale ${mpp} m/px`:", 1 unit = 1 m by construction"})`
  : `<b>Units:</b> pixels (uncalibrated) — <b>no metric claims</b>; declare a scale to convert`;
 $("inspector-body").innerHTML=
 `<p><b>Coordinate frame:</b> ${sc.calibration.frame} · ${unitsLine} · <b>Space:</b> ${sc.tracks[0]?sc.tracks[0].space:"—"}</p>`+
 sc.tracks.map(t=>`<p><b>${t.object_id}</b> (${t.category}) — ${t.points.length} observations, radius ${t.radius} m, source <code>${t.source}</code>${t.occluded.length?`, occluded ${t.occluded.map(o=>o.join("–"))}s (missing evidence, not numerical uncertainty)`:""}</p>`).join("")+
 `<p class="dim">Assumption register: constant-velocity extrapolation for CPA/TTC; finite-difference velocities; smoothing (if applied) biases peaks downward and never overwrites ground truth, which is held separately in the evidence packet.</p>`+
 (r.run&&r.run.findings.pairs?`<h3>All pairs (${r.run.findings.pairs.length})</h3><table class="pairtable"><tr><th>Pair</th><th>Measured d_min (along paths)</th><th>CPA d_min (predicted)</th><th>Units</th><th>TTC</th><th>Event</th><th>Metric claims</th></tr>${r.run.findings.pairs.map(p=>`<tr><td>${p.pair.join(" ↔ ")}</td><td>${p.measured?p.measured.d_min:"—"}${p.measured&&p.measured.contact?" · contact":""}</td><td>${p.d_min??"—"}</td><td>${p.units}</td><td>${p.ttc_s??"—"}</td><td>${p.event?p.event.type:"—"}</td><td>${p.metric_claims?"yes":"no (pixel space)"}</td></tr>`).join("")}</table>`:"");}

// ---- Counterfactual simulator ----
state.cfT=0; state.cfPlaying=false; state.cfData=null;
function populateCfScene(){const sel=$("cf-scene");if(!sel)return;const cur=sel.value;
 const opts=(state.scenarioList||[]).map(s=>`<option value="${s.id}">${s.id}</option>`).join("");
 sel.innerHTML=opts; if(state.data&&state.data.kind==="USER_UPLOADED")sel.innerHTML+=`<option value="__current">Current created/custom scene</option>`;
 sel.value=(state.data&&state.data.kind==="USER_UPLOADED")?"__current":(state.scenario||sel.value);}
function populateCfAgents(){const sel=$("cf-agent"),tg=$("cf-target");if(!sel||!state.data)return;
 const prevA=sel.value,prevT=tg?tg.value:"";
 sel.innerHTML=state.data.tracks.map(t=>`<option value="${t.object_id}">${t.object_id}</option>`).join("");
 if(prevA&&state.data.tracks.some(t=>t.object_id===prevA))sel.value=prevA;
 if(state.cfAgentId)sel.value=state.cfAgentId;
 if(tg){const agent=sel.value;tg.innerHTML=`<option value="">All actors (worst case)</option>`+
  state.data.tracks.filter(t=>t.object_id!==agent).map(t=>`<option value="${t.object_id}">${t.object_id}</option>`).join("");
  if(prevT)tg.value=prevT;}}
$("cf-agent").onchange=()=>{state.cfAgentId=$("cf-agent").value;populateCfAgents();runCf();};
$("cf-target").onchange=()=>runCf();
$("cf-scene").onchange=async()=>{const v=$("cf-scene").value;if(!v||v==="__current"||v===state.scenario){runCf();return;}
 let d;try{d=await(await fetch("/api/scenarios?name="+v)).json();}
 catch(e){$("cf-results").textContent="Could not load scene "+v+" — simulation not run.";return;}
 resetRunState();state.data=d;state.scenario=v;state.t=0;
 const ss=$("scenario-select");if(ss)ss.value=v;
 renderObjects();draw();populateCfAgents();runCf();};
document.querySelectorAll(".cf-preset").forEach(b=>b.onclick=()=>{$("sr").value=b.dataset.sr;$("it").value=b.dataset.it;$("cf-decel").value=b.dataset.dec;
 $("sr-val").textContent=b.dataset.sr+"%";$("it-val").textContent=(+b.dataset.it).toFixed(2)+"s";$("dec-val").textContent=b.dataset.dec+" m/s²";runCf();});
function normalizeCf(r){if(r.results)return r;
 const out={agent_id:r.agent_id||$("cf-agent").value,focus_other:null,results:{},monte_carlo:r.monte_carlo,manifest_hash:r.manifest_hash};
 const radii={};(state.data?state.data.tracks:[]).forEach(t=>radii[t.object_id]=t.radius);
 for(const [oid,v] of Object.entries(r.per_actor||{})){
  out.results[oid]={original:{d_min:v.original_d_min,contact:v.contact_original},
   counterfactual:{d_min:v.counterfactual_d_min,contact:v.contact_counterfactual},
   delta_d_min:+(v.counterfactual_d_min-v.original_d_min).toFixed(4),
   trajectories:(r.trajectories_by_actor||{})[oid]||r.trajectories,
   radius_sum:(radii[out.agent_id]||0)+(radii[oid]||0)};
  if(!out.focus_other||v.original_d_min<out.results[out.focus_other].original.d_min)out.focus_other=oid;}
 return out;}
function currentSceneKey(){if(!state.data)return "none";
 return (state.scenario||state.data.id||"")+"|"+state.data.tracks.map(t=>t.object_id+":"+t.points.length).join(",");}
function cfParamKey(){return currentSceneKey()+"|sr="+$("sr").value+"|it="+$("it").value+"|dec="+$("cf-decel").value
 +"|agent="+($("cf-agent").value||"")+"|target="+($("cf-target").value||"");}
let _cfSyncTimer=null;
function syncCounterfactual(){populateCfScene();populateCfAgents();
 clearTimeout(_cfSyncTimer);
 _cfSyncTimer=setTimeout(()=>{const key=cfParamKey();
  if(state.cfDataKey===key)return;         // already showing exactly this scene+params
  runCf();},220);}
async function syncLabToCfIfNewer(){
 if(!(state.labUpdatedAt> (state.dataUpdatedAt||0)) || state.lab.objects.length<2) return false;
 const tracks=await objectsToTracks(state.lab.objects);
 if(!tracks.length) return false;
 resetRunState();
 state.data={id:"lab-current",description:"Current Create Lab scene",kind:"USER_UPLOADED",
  calibration:{metres_per_pixel:null,frame:"Create Lab stage (metres)"},
  disclaimer:"Current Create Lab scene, sampled server-side.",tracks,ground_truth:{}};
 state.scenario="lab-current";state.dataUpdatedAt=Date.now();
 renderObjects();draw();
 return true;}
async function runCf(){if(!state.data){$("cf-results").textContent="Load or create a scene first.";return;}
 const _keyAtStart=cfParamKey();
 const custom=state.data.kind==="USER_UPLOADED";
 const body=custom?{tracks:state.data.tracks,agent_id:$("cf-agent").value||state.data.tracks[0].object_id,
   speed_reduction_pct:+$("sr").value,intervention_t:+$("it").value,braking_decel:+$("cf-decel").value}
  :{scenario:state.scenario,agent_id:$("cf-agent").value,target_id:$("cf-target").value||null,
   speed_reduction_pct:+$("sr").value,intervention_t:+$("it").value,braking_decel:+$("cf-decel").value};
 $("cf-results").textContent="Simulating on the server…";
 let r;try{r=await(await fetch(custom?"/api/counterfactual-custom":"/api/counterfactual",
  {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})).json();}
 catch(e){$("cf-results").textContent="Simulation failed: API unreachable.";return;}
 if(r.error){$("cf-results").textContent="Simulation failed: "+r.error;return;}
 r=normalizeCf(r);state.cfData=r;state.cfDataKey=_keyAtStart;state.cfT=0;
 const focus=r.focus_other,fr=r.results[focus];
 $("cf-results").innerHTML=`agent <b>${r.agent_id}</b> · focus pair vs <b>${focus}</b><br>`+
  Object.entries(r.results).map(([oid,v])=>`${oid}: d_min ${v.original.d_min} m → <b>${v.counterfactual.d_min} m</b> (Δ ${v.delta_d_min>=0?"+":""}${v.delta_d_min}) ${v.counterfactual.contact?"· ⚠ still contact":"· contact avoided"}`).join("<br>")+
  (r.monte_carlo?`<br>Monte Carlo (focus pair, ${r.monte_carlo.runs} runs, seed ${r.monte_carlo.seed}): p05/p50/p95 ${r.monte_carlo.d_min_p05} / ${r.monte_carlo.d_min_p50} / ${r.monte_carlo.d_min_p95} m`:"")+
  `<br><span class="dim">manifest ${(r.manifest_hash||"").slice(0,16)}… · conditional prediction under declared assumptions, not a guarantee</span>`;
 drawCfMap();drawCfChart();}
function cfBounds(r){let xs=[],ys=[];for(const v of Object.values(r.results)){
 for(const s of ["original","counterfactual"])v.trajectories[s].forEach(p=>{xs.push(p[1],p[3]);ys.push(p[2],p[4]);});}
 return {x0:Math.min(...xs),x1:Math.max(...xs),y0:Math.min(...ys),y1:Math.max(...ys)};}
function cfXY(b,W,H){const dx=(b.x1-b.x0)||1,dy=(b.y1-b.y0)||1,s=Math.min(W/dx,H/dy)*0.92;
 return (x,y)=>[W/2-(b.x0+b.x1)/2*s+x*s, H/2+(b.y0+b.y1)/2*s-y*s];}
function trajAt(traj,t){let best=traj[0];for(const p of traj){if(Math.abs(p[0]-t)<Math.abs(best[0]-t))best=p;}return best;}
function drawCfMap(){if(window.__cf3dSync)window.__cf3dSync(state.cfData,state.cfT);
 const r=state.cfData,c=$("cf-map");if(!r||!c)return;const x=c.getContext("2d"),W=c.width,H=c.height;
 const line=getComputedStyle(document.documentElement).getPropertyValue("--line");
 x.clearRect(0,0,W,H);x.strokeStyle=line;for(let gx=0;gx<W;gx+=44){x.beginPath();x.moveTo(gx,0);x.lineTo(gx,H);x.stroke();}
 const b=cfBounds(r),xy=cfXY(b,W,H),focus=r.focus_other;
 for(const [oid,v] of Object.entries(r.results)){
  x.strokeStyle="#8fa0b8";x.lineWidth=1.2;x.beginPath();v.trajectories.original.forEach((p,i)=>{const[a,bb]=xy(p[3],p[4]);i?x.lineTo(a,bb):x.moveTo(a,bb);});x.stroke();
  const o=trajAt(v.trajectories.counterfactual,state.cfT);const[ox,oy]=xy(o[3],o[4]);
  const oc=(state.data.tracks.find(t=>t.object_id===oid)||{}).category||"object";
  const onx=trajAt(v.trajectories.counterfactual,Math.min(6,state.cfT+0.3));
  drawEntity(x,oc,ox,oy,12,Math.atan2(-(onx[4]-o[4]),onx[3]-o[3]),0);
  x.fillStyle=getComputedStyle(document.documentElement).getPropertyValue("--ink");
  x.font="12px system-ui";x.fillText(oid,ox+10,oy-8);}
 const fv=r.results[focus];
 x.strokeStyle="#8fa0b8";x.setLineDash([6,5]);x.lineWidth=2;x.beginPath();fv.trajectories.original.forEach((p,i)=>{const[a,bb]=xy(p[1],p[2]);i?x.lineTo(a,bb):x.moveTo(a,bb);});x.stroke();x.setLineDash([]);
 x.strokeStyle="#2dd4a8";x.lineWidth=3;x.beginPath();fv.trajectories.counterfactual.forEach((p,i)=>{const[a,bb]=xy(p[1],p[2]);i?x.lineTo(a,bb):x.moveTo(a,bb);});x.stroke();x.lineWidth=1;
 let cpa=fv.trajectories.counterfactual[0];fv.trajectories.counterfactual.forEach(p=>{if(p[5]<cpa[5])cpa=p;});
 const[cx,cy]=xy(cpa[1],cpa[2]);x.strokeStyle="#f2b04a";x.beginPath();x.moveTo(cx-8,cy);x.lineTo(cx,cy-8);x.lineTo(cx+8,cy);x.lineTo(cx,cy+8);x.closePath();x.stroke();
 const go=trajAt(fv.trajectories.original,state.cfT),gc=trajAt(fv.trajectories.counterfactual,state.cfT);
 const gcNext=trajAt(fv.trajectories.counterfactual,Math.min(6,state.cfT+0.3));
 const hd=Math.atan2(-(gcNext[2]-gc[2]),gcNext[1]-gc[1]);
 const agentCat=(state.data.tracks.find(t=>t.object_id===r.agent_id)||{}).category||"object";
 let[a1,b1]=xy(go[1],go[2]);x.globalAlpha=.4;drawEntity(x,agentCat,a1,b1,15,hd,0);x.globalAlpha=1;
 let[a2,b2]=xy(gc[1],gc[2]);drawEntity(x,agentCat,a2,b2,17,hd,state.cfT*7);
 x.fillStyle=getComputedStyle(document.documentElement).getPropertyValue("--ink");x.font="13px system-ui";
 x.fillText(r.agent_id+" (counterfactual)",a2+13,b2+4);x.fillText("◇ closest approach "+cpa[5].toFixed(2)+" m",cx+12,cy-10);
 $("cf-clock").textContent="t = "+state.cfT.toFixed(2)+"s";$("cf-scrub").value=state.cfT;}
function drawCfFromRun(run){ if(state.data&&$("cf-scene")) syncCounterfactual(); }
function drawCfChart(){const r=state.cfData,c=$("cf-chart");if(!r||!c)return;const x=c.getContext("2d"),W=c.width,H=c.height;
 const line=getComputedStyle(document.documentElement).getPropertyValue("--line");
 x.clearRect(0,0,W,H);const f=r.results[r.focus_other];if(!f)return;
 const all=[...f.trajectories.original.map(p=>p[5]),...f.trajectories.counterfactual.map(p=>p[5])];
 const mx=Math.max(...all,f.radius_sum)*1.15||1;
 x.strokeStyle=line;x.beginPath();x.moveTo(44,10);x.lineTo(44,H-30);x.lineTo(W-10,H-30);x.stroke();
 const y0=H-30-f.radius_sum/mx*(H-50);x.fillStyle="#f26d7d33";x.fillRect(44,y0,W-54,H-30-y0);
 x.strokeStyle="#f26d7d";x.setLineDash([4,4]);x.beginPath();x.moveTo(44,y0);x.lineTo(W-10,y0);x.stroke();x.setLineDash([]);
 const plot=(traj,col,width)=>{x.strokeStyle=col;x.lineWidth=width;x.beginPath();traj.forEach((p,i)=>{const X=44+p[0]/6*(W-60),Y=H-30-p[5]/mx*(H-50);i?x.lineTo(X,Y):x.moveTo(X,Y);});x.stroke();x.lineWidth=1;};
 plot(f.trajectories.original,"#8fa0b8",2);plot(f.trajectories.counterfactual,"#2dd4a8",2.5);
 const tx=44+state.cfT/6*(W-60);x.strokeStyle=line;x.beginPath();x.moveTo(tx,10);x.lineTo(tx,H-30);x.stroke();
 x.fillStyle=getComputedStyle(document.documentElement).getPropertyValue("--ink");x.font="13px system-ui";
 x.fillText("— original",52,24);x.fillStyle="#2dd4a8";x.fillText("— counterfactual",150,24);
 x.fillStyle="#f26d7d";x.fillText("contact ≤ "+f.radius_sum.toFixed(2)+" m",W-170,y0-6);
 const ink=getComputedStyle(document.documentElement).getPropertyValue("--dim");x.fillStyle=ink;x.fillText("focus pair: "+r.agent_id+" ↔ "+r.focus_other,52,H-8);}
$("cf-run").onclick=()=>runCf();
[["sr","sr-val",v=>v+"%"],["it","it-val",v=>(+v).toFixed(2)+"s"],["cf-decel","dec-val",v=>v+" m/s\u00b2"]].forEach(([id,lbl,f])=>{
 const el=$(id);if(!el)return;el.addEventListener("input",()=>{$(lbl).textContent=f(el.value);clearTimeout(window._cfDeb);window._cfDeb=setTimeout(runCf,300);});});
state.cfView="2d";
async function setCfView(v){state.cfView=v;localStorage.setItem("fs-view-cf",v);
 $("cf-view-2d").setAttribute("aria-pressed",String(v==="2d"));
 $("cf-view-3d").setAttribute("aria-pressed",String(v==="3d"));
 $("cf-map").classList.toggle("hidden",v==="3d");
 $("cf-3d").classList.toggle("hidden",v!=="3d");
 if(v==="3d"){
  try{
   if(!window.__lab3dMod){window.__lab3dMod=await import("/three-view.js");}
   const mod=window.__lab3dMod;
   const meta={};(state.data?state.data.tracks:[]).forEach(tr=>meta[tr.object_id]={category:tr.category,radius:tr.radius});
   const hooks={extent:()=>{if(!state.cfData)return [16,14];
     let mx=1,my=1;Object.values(state.cfData.results).forEach(r=>{
      r.trajectories.counterfactual.forEach(p=>{mx=Math.max(mx,p[1],p[3]);my=Math.max(my,p[2],p[4]);});});
     return [Math.max(8,Math.ceil(mx*1.15)),Math.max(8,Math.ceil(my*1.15))];}};
   hooks.onContextLost=()=>{toast("3D context was lost (GPU) — returned to the 2D map; the simulation is unchanged.","warn");setCfView("2d");};
   mod.showCf3D($("cf-3d"),hooks);
   window.__cf3dSync=(cf,t)=>{const m2={};(state.data?state.data.tracks:[]).forEach(tr=>m2[tr.object_id]={category:tr.category,radius:tr.radius});
    mod.syncCf3D(cf,m2,t);};
   if(state.cfData)mod.syncCf3D(state.cfData,meta,state.cfT,true);
  }catch(e){toast("3D view unavailable (WebGL): "+e.message+" — the 2D map is unaffected.","err");setCfView("2d");}
 } else if(window.__lab3dMod){window.__lab3dMod.hideCf3D();window.__cf3dSync=null;}
}
$("cf-view-2d").onclick=()=>setCfView("2d");
$("cf-view-3d").onclick=()=>setCfView("3d");
$("cf-scrub").oninput=e=>{state.cfT=+e.target.value;drawCfMap();drawCfChart();};
$("cf-play").onclick=()=>{state.cfPlaying=!state.cfPlaying;$("cf-play").textContent=state.cfPlaying?"⏸ Pause":"▶ Play comparison";
 state._cfLast=null;
 if(state.cfPlaying){const step=(ts)=>{if(!state.cfPlaying)return;
   if(state._cfLast==null)state._cfLast=ts;
   const dt=Math.min(0.1,(ts-state._cfLast)/1000);state._cfLast=ts;
   state.cfT+=dt;if(state.cfT>6)state.cfT=0;drawCfMap();drawCfChart();requestAnimationFrame(step);};
  requestAnimationFrame(step);}};

// ---- human approval gate (Evidence) ----
state.approvals=state.approvals||{};
function runApproved(){return !!(state.run&&state.approvals[state.run.run_id]);}
function syncApprovalUI(){const ok=runApproved(),has=!!state.run;
 const note=$("gate-note"),aj=$("export-json"),ah=$("export-html"),es=$("export-status");
 if(note)note.textContent=!has?"Export is locked: run an analysis first, review its trace, then approve that run here."
  :ok?`Approved for run ${state.run.run_id} by ${state.approvals[state.run.run_id].by} — recorded in the exported packet.`
  :`Export is locked until a named human approves run ${state.run.run_id}. Approval is recorded in the exported packet.`;
 if(aj)aj.disabled=!ok;if(ah)ah.disabled=!ok;
 if(es)es.textContent=has?(ok?"approved · export unlocked":"not approved · export locked"):"no run yet";
 const cb=$("approve-evidence");if(cb)cb.checked=ok;
 const cf=$("approve");if(cf)cf.checked=ok;}
function applyApproval(){const name=($("approver-name").value||"").trim()||((typeof profile==="function"&&profile())?profile().name:"");
 if(!state.run)return;
 if($("approve-evidence").checked){ if(!name){toast("Enter the approver's name — approval must be attributable.","warn");$("approve-evidence").checked=false;return;}
  state.approvals[state.run.run_id]={by:name,at:new Date().toISOString()}; }
 else delete state.approvals[state.run.run_id];
 const cf=$("approve");if(cf)cf.checked=$("approve-evidence").checked;
 syncApprovalUI();}
$("approve-evidence").onchange=applyApproval;
$("approve").onchange=()=>{const ev=$("approve-evidence");if(ev){ev.checked=$("approve").checked;applyApproval();}};
async function fetchReport(){const name=state.scenario||"warehouse-near-miss";
 const rep=await(await fetch("/api/report?name="+encodeURIComponent(name))).json();
 if(state.run){ if(rep.experiment_id!==`fs-${state.run.scenario_id||name}`&&state.data&&state.data.kind!=="USER_UPLOADED"){}
  rep.run=state.run; rep.human_approval=state.approvals[state.run.run_id]||null; }
 $("evidence-preview").textContent=JSON.stringify(
  {experiment_id:rep.experiment_id, human_approval:rep.human_approval,
   run:rep.run?{run_id:rep.run.run_id, mode:rep.run.mode, stages:rep.run.stages.map(s=>s.name+":"+s.status)}:null,
   labels:rep.labels, note:"full packet downloaded as JSON"},null,2); return rep;}
$("export-json").onclick=async()=>{if(!runApproved()){toast("Export locked — review the trace and approve this run first.","warn");return;}
 const rep=await fetchReport();
 download(new Blob([JSON.stringify(rep,null,2)],{type:"application/json"}),`frontiersight-${state.scenario}-evidence.json`);
 toast("Evidence packet exported with recorded human approval.");};
$("export-html").onclick=async()=>{if(!runApproved()){toast("Export locked — review the trace and approve this run first.","warn");return;}
 const rep=await fetchReport();
 download(new Blob([`<!doctype html><title>FrontierSight evidence — ${state.scenario}</title><h1>FrontierSight AI evidence report</h1><p>${rep.disclaimer||""}</p><p>Human approval: ${rep.human_approval?rep.human_approval.by+" at "+rep.human_approval.at:"none"}</p><pre>${JSON.stringify(rep,null,2).replace(/</g,"&lt;")}</pre>`],{type:"text/html"}),`frontiersight-${state.scenario}-report.html`);};
$("cta-demo").onclick=async()=>{await pick("warehouse-near-miss");goto("studio");$("analyze").click();};
$("cta-create").onclick=()=>goto("create");
$("cta-video").onclick=()=>{showView("home");document.getElementById("demo-video").scrollIntoView({behavior:"smooth",block:"center"});};
$("demo-play").onclick=()=>{const f=$("demo-frame");
 f.innerHTML='<iframe src="https://www.youtube-nocookie.com/embed/mYTkPqigoz8?autoplay=1&rel=0" title="FrontierSight AI demo video" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>';};
$("live-test").onclick=async()=>{$("live-out").textContent="Calling Muse Spark…";
 const r=await fetch("/api/meta/hypothesis",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({scenario:state.scenario||"warehouse-near-miss"})});
 $("live-out").textContent=JSON.stringify(await r.json(),null,2).slice(0,1600);};

diag();loadScenarios().then(()=>runCf());

// ---- Create Lab ----
state.lab={objects:[],selected:null,playing:false,t:0,nextId:{}};
const LAB={w:16,h:14};
function labStatus(m){const e=$("lab-status");if(e)e.textContent=m;}
function labId(cat){state.lab.nextId[cat]=(state.lab.nextId[cat]||0)+1;return cat+"-"+state.lab.nextId[cat];}
function labObj(id){return state.lab.objects.find(o=>o.id===id);}
const LAB_SLOTS=[[3,3],[13,3],[3,11],[13,11],[8,7],[5,5],[11,9],[7,12]];
function touchLab(){state.labUpdatedAt=Date.now();}
function labAdd(cat,waypoints,speed,radius,delay,mode,curve){touchLab();
 const o={id:labId(cat),category:cat,radius:radius??(cat==="shelf"?1.1:cat==="forklift"||cat==="vehicle"?0.9:0.5),
  speed:speed??(cat==="shelf"?0:1.4),delay:delay??0,mode:mode||"stop",curve:curve||"straight",waypoints:waypoints||[]};
 if(!o.waypoints.length){const s=LAB_SLOTS[state.lab.objects.length%LAB_SLOTS.length];o.waypoints=[[s[0],s[1]]];o.spawned=true;}
 state.lab.objects.push(o);state.lab.selected=o.id;labRenderList();labDraw();return o;}
function labClear(){$("lab-canvas").getContext("2d").clearRect(0,0,880,620);}
function labXY(x,y,W,H){return [x/LAB.w*W, H-(y/LAB.h*H)];}
function labInv(px,py,W,H){return [Math.round(px/W*LAB.w*10)/10, Math.round((H-py)/H*LAB.h*10)/10];}

// ---- curved paths: Catmull-Rom with arc-length parameterisation (mirror of engine/curves.py) ----
const CR_PER=24;
function crPoint(p0,p1,p2,p3,t){ // centripetal Catmull-Rom (Barry-Goldman) — mirror of engine/curves.py
 const knot=(pa,pb,t0)=>t0+Math.pow(Math.max(Math.hypot(pb[0]-pa[0],pb[1]-pa[1]),1e-4),0.5);
 const t1=knot(p0,p1,0),t2=knot(p1,p2,t1),t3=knot(p2,p3,t2),tt=t1+t*(t2-t1);
 const L=(pa,pb,ta,tb,x)=>{const k=tb===ta?0:(x-ta)/(tb-ta);return [pa[0]+(pb[0]-pa[0])*k,pa[1]+(pb[1]-pa[1])*k];};
 const a1=L(p0,p1,0,t1,tt),a2=L(p1,p2,t1,t2,tt),a3=L(p2,p3,t2,t3,tt);
 const b1=L(a1,a2,0,t2,tt),b2=L(a2,a3,t1,t3,tt);
 return L(b1,b2,t1,t2,tt);}
function resolvePath(o){const key=JSON.stringify([o.waypoints,o.curve,o.mode]);
 if(o._res&&o._res.key===key)return o._res;
 const wps=o.waypoints, closed=o.mode==="loop"; let pts=[];
 if(wps.length<2){pts=wps.slice();}
 else if(o.curve==="smooth"){
  const ext=closed?[wps[wps.length-1],...wps,wps[0],wps[1]]:[wps[0],...wps,wps[wps.length-1]];
  for(let i=1;i<ext.length-2;i++){for(let k=0;k<CR_PER;k++)pts.push(crPoint(ext[i-1],ext[i],ext[i+1],ext[i+2],k/CR_PER));}
  pts.push(closed?wps[0]:wps[wps.length-1]);
 } else {
  const seq=closed?[...wps,wps[0]]:wps;
  for(let i=1;i<seq.length;i++){const[a,b]=[seq[i-1],seq[i]];
   for(let k=0;k<CR_PER;k++){const t=k/CR_PER;pts.push([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]);}}
  pts.push(seq[seq.length-1]);
 }
 const cum=[0];for(let i=1;i<pts.length;i++)cum.push(cum[i-1]+Math.hypot(pts[i][0]-pts[i-1][0],pts[i][1]-pts[i-1][1]));
 const res={key,pts,cum,total:cum[cum.length-1]||0};o._res=res;return res;}

const DYN={forklift:{a:0.7,lat:0.6,turn:1.3},vehicle:{a:1.6,lat:1.1,turn:3.2},cyclist:{a:1.2,lat:1.4,turn:1.2},
 pedestrian:{a:1.3,lat:1.6,turn:0.25},robot:{a:1.0,lat:1.0,turn:0.5},shelf:{a:0,lat:0,turn:0},object:{a:1.0,lat:1.0,turn:0.8}};
function pathCurvatures(pts){const out=new Array(pts.length).fill(0);
 for(let i=1;i<pts.length-1;i++){const[a,b,c]=[pts[i-1],pts[i],pts[i+1]];
  const ab=Math.hypot(b[0]-a[0],b[1]-a[1]),bc=Math.hypot(c[0]-b[0],c[1]-b[1]),ca=Math.hypot(a[0]-c[0],a[1]-c[1]);
  const area2=Math.abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]));
  if(ab*bc*ca<1e-12||area2<1e-12)continue;const r=(ab*bc*ca)/(2*area2);out[i]=r>0?1/r:0;}
 if(out.length>2){out[0]=out[1];out[out.length-1]=out[out.length-2];}return out;}
function getProfile(o){const r=resolvePath(o);
 const key=r.key+"|"+o.speed+"|"+o.category+"|"+o.mode;
 if(o._prof&&o._prof.key===key)return o._prof;
 const dyn=DYN[o.category]||DYN.object,a=Math.max(dyn.a,1e-3),pts=r.pts,cum=r.cum,n=pts.length;
 const ks=pathCurvatures(pts);
 let v=ks.map(k=>k>1e-6?Math.min(o.speed,Math.sqrt(dyn.lat/k)):o.speed);
 if(n>=2&&r.total>0){
  if(o.mode==="loop"){
   for(let pass=0;pass<2;pass++){
    for(let i=0;i<n;i++){const jj=(i+1)%n;const ds=jj>i?cum[jj]-cum[i]:r.total-cum[i]+cum[jj];
     if(ds>0)v[jj]=Math.min(v[jj],Math.sqrt(v[i]*v[i]+2*a*ds));}
    for(let i=n-1;i>=0;i--){const jj=(i+1)%n;const ds=jj>i?cum[jj]-cum[i]:r.total-cum[i]+cum[jj];
     if(ds>0)v[i]=Math.min(v[i],Math.sqrt(v[jj]*v[jj]+2*a*ds));}}
  }else{
   v[0]=0;if(o.mode==="stop"||o.mode==="pingpong")v[n-1]=0;
   for(let i=n-2;i>=0;i--){const ds=cum[i+1]-cum[i];if(ds>0)v[i]=Math.min(v[i],Math.sqrt(v[i+1]*v[i+1]+2*a*ds));}
   for(let i=0;i<n-1;i++){const ds=cum[i+1]-cum[i];if(ds>0)v[i+1]=Math.min(v[i+1],Math.sqrt(v[i]*v[i]+2*a*ds));}
  }}
 const times=[0];
 for(let i=0;i<n-1;i++){const ds=cum[i+1]-cum[i],avg=(v[i]+v[i+1])/2;
  times.push(times[i]+(avg>1e-6?ds/avg:0));}
 const prof={key,times,speeds:v,total:times.length?times[times.length-1]:(o.speed?r.total/o.speed:0)};
 o._prof=prof;return prof;}
function profPosition(o,lt){const r=resolvePath(o),P=getProfile(o);
 if(!P.times.length||P.total<=0)return o.waypoints[0];
 if(o.mode==="loop")lt=lt%P.total;
 else if(o.mode==="pingpong"){const m=lt%(2*P.total);lt=m>P.total?2*P.total-m:m;}
 else lt=Math.min(lt,P.total);
 let lo=0,hi=P.times.length-1;while(lo<hi){const mid=(lo+hi)>>1;if(P.times[mid]<lt)lo=mid+1;else hi=mid;}
 const i=Math.min(Math.max(lo-1,0),P.times.length-2),span=P.times[i+1]-P.times[i];
 const k=span>0?(lt-P.times[i])/span:0,s=r.cum[i]+(r.cum[i+1]-r.cum[i])*k;
 return pathPosAtDistance(o,s);}
function minTurnRadius(o){const ks=pathCurvatures(resolvePath(o).pts);
 const kmax=Math.max(0,...ks);return kmax>1e-9?1/kmax:Infinity;}
function realismWarnings(o){const out=[];if(!o.waypoints.length)return out;
 const dyn=DYN[o.category]||DYN.object,r=minTurnRadius(o);
 if(dyn.turn&&isFinite(r)&&r<dyn.turn)out.push(`${o.id}: tightest turn ${r.toFixed(2)} m is below the ${o.category} limit ${dyn.turn} m — widen the curve`);
 const pts=resolvePath(o).pts;
 if(pts.some(q=>q[0]<-0.05||q[0]>16.05||q[1]<-0.05||q[1]>14.05))out.push(`${o.id}: path leaves the stage bounds`);
 for(const s of state.lab.objects){if(s.category!=="shelf"||!s.waypoints.length)continue;
  const sp=s.waypoints[0];
  if(pts.some(q=>Math.hypot(q[0]-sp[0],q[1]-sp[1])<s.radius+(o.radius||0)*0.6))
   out.push(`${o.id}: path passes through the footprint of ${s.id}`);}
 return out;}

function pathPosAtDistance(o,d){const r=resolvePath(o);if(r.pts.length<2||r.total===0)return r.pts[0]||null;
 d=Math.min(Math.max(d,0),r.total);let lo=0,hi=r.cum.length-1;
 while(lo<hi){const mid=(lo+hi)>>1;if(r.cum[mid]<d)lo=mid+1;else hi=mid;}
 const i=Math.max(1,lo),seg=r.cum[i]-r.cum[i-1],k=seg>0?(d-r.cum[i-1])/seg:0;
 return [r.pts[i-1][0]+(r.pts[i][0]-r.pts[i-1][0])*k, r.pts[i-1][1]+(r.pts[i][1]-r.pts[i-1][1])*k];}

function pathLen(o){return resolvePath(o).total;}
function pathDur(o){return o.speed>0?getProfile(o).total:0;}
function labDuration(){return Math.min(20,Math.max(4,...state.lab.objects.map(o=>o.delay+pathDur(o))));}
function posOnPath(o,t){if(!o.waypoints.length)return null;
 if(o.waypoints.length===1||o.speed<=0)return o.waypoints[0];
 const lt=Math.max(0,t-o.delay);
 return profPosition(o,lt);}
function labDraw(){if(window.__lab3dSync)window.__lab3dSync(state.lab.objects,state.lab.t);
 const c=$("lab-canvas");if(!c)return;computeLabDuration();const x=c.getContext("2d"),W=c.width,H=c.height;
 x.clearRect(0,0,W,H);x.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue("--line");for(let gx=0;gx<=LAB.w;gx+=2){const[a]=labXY(gx,0,W,H);x.beginPath();x.moveTo(a,0);x.lineTo(a,H);x.stroke();}
 for(let gy=0;gy<=LAB.h;gy+=2){const[,b]=labXY(0,gy,W,H);x.beginPath();x.moveTo(0,b);x.lineTo(W,b);x.stroke();}
 const _labLabels=[];
 for(const o of state.lab.objects){const col=COL[o.category]||"#fff",sel=o.id===state.lab.selected;
  if(o.waypoints.length>1){const hov=o.id===state.labHover;
   x.strokeStyle=col+(sel||hov?"":"88");x.lineWidth=sel?2.5:hov?2.2:1.5;x.beginPath();
   resolvePath(o).pts.forEach((w,i)=>{const[a,b]=labXY(w[0],w[1],W,H);i?x.lineTo(a,b):x.moveTo(a,b);});x.stroke();x.lineWidth=1;}
  o.waypoints.forEach((w,i)=>{const[a,b]=labXY(w[0],w[1],W,H);x.fillStyle=sel?col:"#41506e";
   x.beginPath();x.arc(a,b,sel?6:4.5,0,7);x.fill();x.fillStyle="#dfe7f5";x.font="10px system-ui";x.fillText(String(i+1),a-3,b+3);});
  const pos=posOnPath(o,state.lab.t);if(pos){const[a,b]=labXY(pos[0],pos[1],W,H);const r=o.radius/LAB.w*W;
   if(sel){x.strokeStyle=col;x.lineWidth=1.6;x.setLineDash([4,4]);x.beginPath();x.arc(a,b,r+8,0,7);x.stroke();x.setLineDash([]);}
   const ahead=posOnPath(o,state.lab.t+0.35);let hd=state["lhd_"+o.id]||0;
   if(ahead&&(ahead[0]!==pos[0]||ahead[1]!==pos[1])){hd=Math.atan2(-(ahead[1]-pos[1]),ahead[0]-pos[0]);state["lhd_"+o.id]=hd;}
   drawEntity(x,o.category,a,b,Math.max(10,r),hd,state.lab.t*7);
   _labLabels.push([`${o.id}${o.speed?` · ${o.speed} m/s`:" · static"}`,a+r+9,b-9,col]);}}
 _labLabels.forEach(L=>labelPill(x,L[0],L[1],L[2],L[3]));
 const live=$("lab-live");if(live){let best=null;
  const placed=state.lab.objects.map(o=>({o,p:posOnPath(o,state.lab.t)})).filter(q=>q.p);
  for(let i=0;i<placed.length;i++)for(let k=i+1;k<placed.length;k++){
   const d=Math.hypot(placed[i].p[0]-placed[k].p[0],placed[i].p[1]-placed[k].p[1])-placed[i].o.radius-placed[k].o.radius;
   if(!best||d<best.d)best={d,a:placed[i].o.id,b:placed[k].o.id};}
  live.textContent=best?`Closest pair at preview: ${best.a} ↔ ${best.b} — surface gap ${best.d.toFixed(2)} m ${best.d<0.5?"⚠ proximity":best.d<0?"⚠ OVERLAP":""}`:"Closest pair: —";
  live.style.color=best&&best.d<0.5?"var(--amber)":"";}
 const clk=$("lab-clock");if(clk)clk.textContent="t = "+state.lab.t.toFixed(2)+"s";const sc=$("lab-scrub");if(sc)sc.value=state.lab.t;}
function computeLabDuration(){const sc=$("lab-scrub");if(sc)sc.max=labDuration();}
function labReady(){const el=$("lab-ready");if(!el)return;const os=state.lab.objects;
 const moving=os.filter(o=>o.speed>0&&o.waypoints.length>1).length, placed=os.filter(o=>o.waypoints.length).length;
 el.innerHTML=os.length<2?`Add at least <b>2 components</b> to run analysis (${os.length} so far).`
  :`Ready check: <b>${os.length} components</b> · ${placed} placed · ${moving} moving · stage 16×14 m — ${moving?"press Run analysis.":"give a selected component a path (click the stage) to create motion."}`;
 el.style.color=os.length>=2&&moving?"var(--teal)":"var(--amber)";
 const warns=os.flatMap(o=>o.speed>0||o.waypoints.length>1?realismWarnings(o):[]);
 if(warns.length)el.innerHTML+=warns.map(w=>`<br><span style="color:var(--amber)">⚠ ${w}</span>`).join("");}
document.addEventListener("keydown",e=>{if((e.key==="Delete"||e.key==="Backspace")&&$("view-create").classList.contains("on")
 &&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)){const o=labObj(state.lab.selected);
 if(o&&o.waypoints.length){o.waypoints.pop();labRenderList();labDraw();}}});
function labRenderList(){const el=$("lab-list");if(!el)return;labReady();
 if(state.labTitle)labSetTitle(state.labTitle,false);
 el.innerHTML=state.lab.objects.length?state.lab.objects.map(o=>`<div class="labobj ${o.id===state.lab.selected?"sel":""}" data-id="${o.id}">
  <b style="color:${COL[o.category]||"#fff"}">●</b> <b>${o.id}</b> <span class="dim">${o.waypoints.length} waypoint(s) · ${pathLen(o).toFixed(1)} m${o.speed?` · ${(pathDur(o)).toFixed(1)}s`:""}</span>
  <div class="row labctl">
   <label>Speed m/s<input type="number" step="0.1" min="0" max="8" value="${o.speed}" data-f="speed"></label>
   <label>Radius m<input type="number" step="0.1" min="0.1" max="3" value="${o.radius}" data-f="radius"></label>
   <label>Delay s<input type="number" step="0.25" min="0" max="10" value="${o.delay}" data-f="delay"></label>
   <label>Path mode<select data-f="mode"><option ${o.mode==="stop"?"selected":""}>stop</option><option ${o.mode==="loop"?"selected":""}>loop</option><option ${o.mode==="pingpong"?"selected":""}>pingpong</option></select></label>
   <label>Path shape<select data-f="curve"><option value="straight" ${o.curve!=="smooth"?"selected":""}>straight lines</option><option value="smooth" ${o.curve==="smooth"?"selected":""}>smooth curve</option></select></label>
  </div>
  <div class="row"><button data-act="select">${o.id===state.lab.selected?"Selected ✓":"Select & edit path"}</button>
   <button class="ghostbtn" data-act="undo">Undo point</button>
   <button class="ghostbtn" data-act="clear">Clear path</button>
   <button class="ghostbtn" data-act="dup">Duplicate</button>
   <button class="ghostbtn" data-act="del">Delete</button></div></div>`).join("")
  :'<p class="dim">No components yet. Add one, select it, then click the stage to lay its path.</p>';
 el.querySelectorAll(".labobj").forEach(card=>{const o=labObj(card.dataset.id);
  card.querySelectorAll("input,select").forEach(inp=>inp.onchange=()=>{o[inp.dataset.f]=(inp.dataset.f==="mode"||inp.dataset.f==="curve")?inp.value:Math.max(0,+inp.value||0);delete o._res;labRenderList();labDraw();});
  card.querySelectorAll("button").forEach(b=>b.onclick=()=>{const a=b.dataset.act;
   if(a==="select"){state.lab.selected=o.id;}
   if(a==="undo"){o.waypoints.pop();}
   if(a==="clear"){o.waypoints=[];}
   if(a==="dup"){const c=labAdd(o.category,o.waypoints.map(w=>[w[0]+0.5,w[1]+0.5]),o.speed,o.radius,o.delay,o.mode,o.curve);labStatus(c.id+" duplicated — drag its waypoints apart.");}
   if(a==="del"){state.lab.objects=state.lab.objects.filter(q=>q.id!==o.id);if(state.lab.selected===o.id)state.lab.selected=null;}
   labRenderList();labDraw();});});}
// canvas editing: click a path to select & edit it; click near its line to
// insert a point there; drag points to reshape; shift-drag moves the whole
// path; right-click a point deletes it. Clicking empty stage appends.
(()=>{const c=$("lab-canvas");if(!c)return;c.style.cursor="crosshair";
 let drag=null,moved=false,pathDrag=null;
 const evPos=e=>{const r=c.getBoundingClientRect();return [(e.clientX-r.left)*c.width/r.width,(e.clientY-r.top)*c.height/r.height];};
 const stagePos=e=>{const[px,py]=evPos(e);return labInv(px,py,c.width,c.height);};
 function hitWaypoint(px,py){let best=null;
  for(const o of state.lab.objects)o.waypoints.forEach((w,i)=>{
   const[a,b]=labXY(w[0],w[1],c.width,c.height);const d=Math.hypot(a-px,b-py);
   if(d<13&&(!best||d<best.d))best={o,i,d};});
  return best;}
 function hitPath(sx,sy){let best=null;
  for(const o of state.lab.objects){if(o.waypoints.length<2)continue;
   const pts=resolvePath(o).pts;
   for(let i=1;i<pts.length;i++){const[a,b]=[pts[i-1],pts[i]];
    const vx=b[0]-a[0],vy=b[1]-a[1],L2=vx*vx+vy*vy||1e-9;
    const k=Math.min(1,Math.max(0,((sx-a[0])*vx+(sy-a[1])*vy)/L2));
    const d=Math.hypot(sx-(a[0]+vx*k),sy-(a[1]+vy*k));
    if(!best||d<best.d)best={o,d};}}
  return best;}
 function nearestWpSegment(o,sx,sy){let best={i:0,d:Infinity};
  for(let i=1;i<o.waypoints.length;i++){const[a,b]=[o.waypoints[i-1],o.waypoints[i]];
   const vx=b[0]-a[0],vy=b[1]-a[1],L2=vx*vx+vy*vy||1e-9;
   const k=Math.min(1,Math.max(0,((sx-a[0])*vx+(sy-a[1])*vy)/L2));
   const d=Math.hypot(sx-(a[0]+vx*k),sy-(a[1]+vy*k));
   if(d<best.d)best={i:i-1,d};}
  return best;}
 function select(o){if(state.lab.selected!==o.id){state.lab.selected=o.id;labRenderList();labDraw();}}
 c.addEventListener("pointerdown",e=>{if(e.button!==0)return;
  try{c.setPointerCapture(e.pointerId);}catch(_){}
  moved=false;c._suppressAdd=false;const[px,py]=evPos(e),[sx,sy]=stagePos(e);
  const wh=hitWaypoint(px,py);
  if(wh){select(wh.o);drag=wh;return;}
  const ph=hitPath(sx,sy);
  if(ph&&ph.d<0.45){select(ph.o);c._suppressAdd=true;
   if(e.shiftKey){pathDrag={o:ph.o,sx,sy,orig:ph.o.waypoints.map(w=>[...w])};}
   else labStatus(`${ph.o.id} selected — click near its path to insert a point, click empty stage to append, drag points to reshape, Shift-drag to move the whole path.`);
   return;}});
 c.addEventListener("pointermove",e=>{const[px,py]=evPos(e),[sx,sy]=stagePos(e);
  if(drag){moved=true;drag.o.waypoints[drag.i]=labInv(px,py,c.width,c.height);delete drag.o._res;labDraw();return;}
  if(pathDrag){moved=true;const dx=sx-pathDrag.sx,dy=sy-pathDrag.sy;
   pathDrag.o.waypoints=pathDrag.orig.map(w=>[Math.round((w[0]+dx)*10)/10,Math.round((w[1]+dy)*10)/10]);
   delete pathDrag.o._res;labDraw();return;}
  const hov=hitPath(sx,sy);const hovId=hov&&hov.d<0.45?hov.o.id:null;
  c.style.cursor=hovId?"pointer":"crosshair";
  if(hovId!==state.labHover){state.labHover=hovId;labDraw();}});
 c.addEventListener("pointercancel",()=>{drag=null;pathDrag=null;});
 c.addEventListener("pointerup",e=>{if(e.button!==0)return;const wasDrag=!!drag||!!pathDrag;
  if(drag&&moved){drag=null;touchLab();labRenderList();labDraw();return;}
  if(pathDrag){pathDrag=null;touchLab();labRenderList();labDraw();return;}
  drag=null;
  if(c._suppressAdd){c._suppressAdd=false;labRenderList();labDraw();return;}
  const o=labObj(state.lab.selected);if(!o){labStatus("Add and select a component first.");return;}
  const[sx,sy]=stagePos(e);
  const seg=o.waypoints.length>1?nearestWpSegment(o,sx,sy):{i:0,d:Infinity};
  const pt=[sx,sy];
  if(o.waypoints.length>1&&seg.d<0.4){o.waypoints.splice(seg.i+1,0,pt);
   labStatus(`Point inserted into ${o.id}'s path (position ${seg.i+2} of ${o.waypoints.length}). Drag it to shape the curve.`);}
  else o.waypoints.push(pt);
  delete o._res;touchLab();labRenderList();labDraw();});
 c.addEventListener("dblclick",e=>{const[px,py]=evPos(e);const wh=hitWaypoint(px,py);
  if(wh){wh.o.waypoints.splice(wh.i,1);delete wh.o._res;touchLab();labRenderList();labDraw();
   labStatus(`Waypoint removed from ${wh.o.id}.`);}});
 c.addEventListener("contextmenu",e=>{e.preventDefault();const[px,py]=evPos(e);
  const wh=hitWaypoint(px,py);
  if(wh){select(wh.o);wh.o.waypoints.splice(wh.i,1);delete wh.o._res;touchLab();labRenderList();labDraw();
   labStatus(`Waypoint removed from ${wh.o.id}.`);}
  else{const[sx,sy]=stagePos(e);const ph=hitPath(sx,sy);if(ph)select(ph.o);}});
})();
$("lab-add").onclick=()=>{const cat=$("lab-new-cat").value;const o=labAdd(cat);
 labStatus(`${o.id} added and selected — click the stage to lay its path (shelf = static, one point is enough).`);};
document.querySelectorAll("[data-tpl]").forEach(b=>b.onclick=()=>{state.lab.objects=[];state.lab.selected=null;state.lab.nextId={};
 if(b.dataset.tpl==="near-miss"){labAdd("forklift",[[1,7],[7.5,7],[13,7]],1.6,0.9,0);labAdd("pedestrian",[[8.6,13],[8.0,9],[8.5,5.5],[9.2,1]],1.55,0.45,0,"stop","smooth");}
 if(b.dataset.tpl==="crossing"){labAdd("vehicle",[[0.5,7],[6,6.8],[10,8],[15,11]],2.4,1.1,0,"stop","smooth");labAdd("cyclist",[[9,13.5],[8.6,8],[9.2,3],[9.5,0.5]],1.9,0.5,0.5,"stop","smooth");labAdd("pedestrian",[[14,2],[8,6.2],[3,11]],1.3,0.45,1,"stop","smooth");}
 if(b.dataset.tpl==="cell"){labAdd("robot",[[2,2],[13,2],[13,11],[2,11]],1.2,0.55,0,"loop","smooth");labAdd("forklift",[[1,12],[14,12]],0.9,0.9,1);labAdd("shelf",[[8,7]],0,1.4,0);labAdd("pedestrian",[[15,1],[10,6],[15,12]],1.1,0.45,2,"stop","smooth");}
 labSetTitle(b.dataset.tpl.replace("-"," ").replace(/\b\w/g,c=>c.toUpperCase())+" template",false);
 if(!$("lab-ws-name").value)$("lab-ws-name").value=suggestedName(labTitleSafe());
 labStatus(`Template "${b.dataset.tpl}" loaded — edit any path, then Run analysis.`);labDraw();});
function labTitleSafe(){return (state.labTitle||"").replace(/ template$/,"")||"";}
state.labView="2d";
async function setLabView(v){state.labView=v;localStorage.setItem("fs-view-lab",v);
 $("lab-view-2d").setAttribute("aria-pressed",String(v==="2d"));
 $("lab-view-3d").setAttribute("aria-pressed",String(v==="3d"));
 $("lab-canvas").classList.toggle("hidden",v==="3d");
 $("lab-3d").classList.toggle("hidden",v!=="3d");
 if(v==="3d"){
  try{
   if(!window.__lab3dMod){window.__lab3dMod=await import("/three-view.js");}
   const mod=window.__lab3dMod;
   mod.showLab3D($("lab-3d"),{resolve:o=>resolvePath(o),pos:(o,t)=>posOnPath(o,t),
    onContextLost:()=>{toast("3D context was lost (GPU) — returned to the 2D editor; your scene is untouched.","warn");setLabView("2d");},
    onGroundClick:(x,y)=>{const o=labObj(state.lab.selected);
     if(!o){labStatus("Select a component first, then click the ground to add waypoints.");return;}
     o.waypoints.push([Math.round(x*10)/10,Math.round(y*10)/10]);delete o._res;
     labRenderList();labDraw();}});
   window.__lab3dSync=(objs,t)=>mod.syncLab3D(objs,t);
   mod.syncLab3D(state.lab.objects,state.lab.t,true);
  }catch(e){toast("3D view unavailable (WebGL): "+e.message+" — the 2D editor is unaffected.","err");setLabView("2d");}
 } else if(window.__lab3dMod){window.__lab3dMod.hideLab3D();}
}
$("lab-view-2d").onclick=()=>setLabView("2d");
$("lab-view-3d").onclick=()=>setLabView("3d");
$("lab-play").onclick=()=>{state.lab.playing=!state.lab.playing;$("lab-play").textContent=state.lab.playing?"⏸ Pause preview":"▶ Preview motion";
 state._labLast=null;
 if(state.lab.playing){const step=(ts)=>{if(!state.lab.playing)return;
   if(state._labLast==null)state._labLast=ts;
   const dt=Math.min(0.1,(ts-state._labLast)/1000);state._labLast=ts;
   state.lab.t+=dt;if(state.lab.t>labDuration())state.lab.t=0;labDraw();requestAnimationFrame(step);};
  requestAnimationFrame(step);}};
$("lab-scrub").oninput=e=>{state.lab.t=+e.target.value;labDraw();};
function labSampleTracks(){const T=labDuration(),dt=0.1;const tracks=[];
 for(const o of state.lab.objects){if(!o.waypoints.length)throw new Error(`${o.id} has no path — click the stage to add waypoints.`);
  if(o.category!=="shelf"&&o.speed<=0&&o.waypoints.length>1)throw new Error(`${o.id} has a path but speed 0 — set a speed or make it a shelf.`);
  if(o.category!=="shelf"&&o.speed>0&&o.waypoints.length<2)throw new Error(`${o.id} is placed but has no path yet — select it and click the stage to add waypoints, or set its speed to 0 to keep it parked.`);
  const pts=[];for(let t=0;t<=T+1e-9;t=Math.round((t+dt)*100)/100){const p=posOnPath(o,t);pts.push([t,p[0],p[1]]);}
  tracks.push({object_id:o.id,category:o.category,space:"world",radius:o.radius,source:"USER_CREATED",points:pts});}
 if(tracks.length<2)throw new Error("Create at least two components to analyse interactions.");
 return tracks;}
async function analyzeCustom(tracks,label){
 const ctrl=new AbortController(); const killer=setTimeout(()=>ctrl.abort(),95000);
 let r;
 try{
  const res=await fetch("/api/analyze-custom",{method:"POST",headers:{"Content-Type":"application/json"},signal:ctrl.signal,
   body:JSON.stringify({id:label||"created-scene",tracks,metres_per_pixel:null,
    speed_reduction_pct:+$("sr").value,intervention_t:+$("it").value,human_approved:$("approve").checked})});
  const text=await res.text();
  try{ r=JSON.parse(text); }catch(e){ throw new Error(`server returned HTTP ${res.status} (non-JSON). The analysis likely timed out — press Run analysis again.`); }
  if(!res.ok||r.error) throw new Error(r.error||r.detail||("HTTP "+res.status));
  if(!r.run||!r.scenario) throw new Error("server response is missing the analysis run — please retry.");
 }catch(e){
  if(e.name==="AbortError") e=new Error("analysis timed out after 95s in the browser — press Run analysis again.");
  labStatus("Analysis failed: "+e.message); const as=$("analyze-status"); if(as)as.textContent="Custom analysis failed: "+e.message;
  throw e;
 }finally{ clearTimeout(killer); }
 state.data=r.scenario;state.scenario=r.scenario.id;state.run=r.run;state.t=0;state.dataUpdatedAt=Date.now(); syncCounterfactual();
 try{const mine=JSON.parse(localStorage.getItem("fs-my-scenes")||"[]");mine.push({id:r.scenario.id,when:Date.now(),tracks});localStorage.setItem("fs-my-scenes",JSON.stringify(mine.slice(-10)));}catch(e){}
 renderObjects();draw();renderTrace(r.run);renderInspector(r);goto("studio");
 $("analyze-status").textContent=`Custom run ${r.run.run_id} · ${r.run.mode} · ${r.scenario.tracks.length} objects · ${r.run.findings.pairs.length} pairs analysed`;
 const evs=[];(r.run.findings.pairs||[]).forEach(p=>{if(p.event)evs.push({...p.event,pair:p.pair});});
 $("events").innerHTML=evs.length?evs.map(e=>`<li class="ev" data-t="${e.at_time_s||e.t_star_s||0}">⚠ <b>${e.type}</b> ${e.pair.join(" ↔ ")}<br><span class="dim">${e.ttc_s!=null?"TTC "+e.ttc_s+"s":e.d_min!=null?"d_min "+e.d_min+" "+(e.units||""):""}</span></li>`).join(""):'<li class="dim">No proximity events above threshold.</li>';
 document.querySelectorAll(".ev").forEach(el=>el.onclick=()=>{state.t=+el.dataset.t;draw();});
 window.scrollTo({top:0,behavior:"smooth"});
 return r;}
$("lab-run").onclick=async()=>{let localTracks;
 try{localTracks=labSampleTracks();}catch(e){labStatus(e.message);return;}
 const btn=$("lab-run"),old=btn.textContent,t0=Date.now();btn.disabled=true;btn.textContent="Sampling paths… 0s";
 const timer=setInterval(()=>{btn.textContent=`Analysing… ${Math.round((Date.now()-t0)/1000)}s`;},500);
 try{
  let tracks=localTracks, sampledBy="browser sampler";
  try{const r=await fetch("/api/tracks/from-paths",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({objects:state.lab.objects.map(o=>({object_id:o.id,category:o.category,waypoints:o.waypoints,
     speed:o.speed,radius:o.radius,delay:o.delay,curve:o.curve,mode:o.mode}))})});
   const out=await r.json();
   if(r.ok&&out.tracks){tracks=out.tracks;sampledBy="server engine (engine/curves)";}
   else if(out.error)throw new Error(out.error);
  }catch(e){labStatus("Server sampling unavailable ("+e.message+") — using the identical browser sampler.");}
  labStatus("Tracks sampled by "+sampledBy+". Running analysis…");
  await analyzeCustom(tracks,"created-"+Date.now());
  labStatus("Analysis complete — showing Studio. Events are in the right-hand list; click one to seek.");
 }catch(e){/* analyzeCustom already surfaced the error */}
 finally{clearInterval(timer);btn.disabled=false;btn.textContent=old;}};
$("lab-export").onclick=()=>{download(new Blob([JSON.stringify({kind:"frontiersight-created-scene",stage_metres:[LAB.w,LAB.h],objects:state.lab.objects},null,2)],{type:"application/json"}),"frontiersight-scene.json");};
$("lab-import").onchange=e=>{const f=e.target.files[0];if(!f)return;f.text().then(txt=>{try{
 const d=JSON.parse(txt);const objs=d.objects||d;if(!Array.isArray(objs))throw new Error("expected {objects:[...]} ");
 state.lab.objects=[];state.lab.nextId={};objs.forEach(o=>labAdd(o.category||"object",(o.waypoints||o.points||[]).map(p=>[+p[0],+p[1]]),+o.speed||0,+o.radius||0.5,+o.delay||0,o.mode||"stop",o.curve||"straight"));
 labStatus(`Imported ${state.lab.objects.length} component(s).`);labDraw();}catch(err){labStatus("Import failed: "+err.message);}});};
function labSetTitle(name,saved){state.labTitle=name||"Untitled scene";
 const t=$("lab-scene-title");if(t)t.textContent=state.labTitle;
 const b=$("lab-saved-badge");if(b){b.textContent=saved?"saved":"unsaved";
  b.className="pill "+(saved?"ok":"warn");}}
function suggestedName(base){if(base)return base;
 const cats=[...new Set(state.lab.objects.map(o=>o.category))].join(" + ")||"scene";
 return `${cats} · ${state.lab.objects.length} components · ${new Date().toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})}`;}
function labLoadScene(scene,label){state.lab.objects=[];state.lab.selected=null;state.lab.nextId={};state.lab.t=0;state.labUpdatedAt=Date.now();
 labSetTitle(scene.name||"",false);
 (scene.objects||[]).forEach(o=>labAdd(o.category,(o.waypoints||[]).map(w=>[+w[0],+w[1]]),+o.speed||0,+o.radius||0.5,+o.delay||0,o.mode||"stop",o.curve||"straight"));
 labStatus(label);labDraw();}
document.querySelectorAll(".lab-chip").forEach(b=>b.onclick=()=>{$("lab-prompt").value=b.textContent;$("lab-generate").click();});
$("lab-prompt").addEventListener("input",()=>{$("lab-prompt-count").textContent=$("lab-prompt").value.length;});
$("lab-generate").onclick=async()=>{const desc=$("lab-prompt").value.trim();
 if(desc.length<8){$("lab-gen-status").textContent="Describe the scene in a sentence or two first (at least a few words).";return;}
 if(desc.length>4000){$("lab-gen-status").textContent=`Your description is ${desc.length} characters — the limit is 4000. Shorten it a little and try again.`;return;}
 $("lab-gen-status").textContent="Asking Muse Spark to design the scene…";
 let r;try{const res=await fetch("/api/meta/scene",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt:desc})});
  r=await res.json();r.status=res.status===200?"OK":res.status;}
 catch(e){$("lab-gen-status").textContent="Generation failed: API unreachable.";return;}
 if(r.status==="BLOCKED_CREDENTIALS"){$("lab-gen-status").textContent=r.detail;return;}
 if(r.error||r.status==="MODEL_ERROR"){
  $("lab-gen-status").textContent=(r.status===400||/characters|required/.test(r.error||""))
   ? "Check your description: "+(r.error||r.detail)
   : "Muse could not produce a valid scene: "+(r.error||r.detail)+" — try a clearer description.";return;}
 labLoadScene(r.scene,`Generated "${r.scene.name}" — edit any waypoint, then Run analysis.`); obDone("muse");
 $("lab-ws-name").value=r.scene.name||"";
 const sv=$("lab-save-ws");sv.classList.add("pulse");sv.textContent="Save this scene →";
 const q=r.scene.quality;
 $("lab-gen-status").innerHTML+=`<br><b>Auto-labelled:</b> “${r.scene.name}” — it is prefilled below the stage. Press <b>Save workspace</b> to keep it (it will also appear in the Video Studio dropdown under <i>My workspaces</i>).`+
  (q?`<br><b>Path quality (engine-scored):</b> closest surface separation ${q.min_separation_m} m`+
   (q.has_close_interaction?" — a real interaction to analyse.":" — no close interaction; edit paths closer together.")+
   (q.issues&&q.issues.length?` Issues: ${q.issues.join("; ")}`:"")+
   (q.warnings&&q.warnings.length?` Warnings: ${q.warnings.join("; ")}`:""):"");
 toast("Scene generated — name prefilled under the stage. Save it to keep it in your workspaces.");
 $("lab-gen-status").innerHTML=`Source: <b>${r.source==="MODEL_DERIVED"?"MODEL_DERIVED · Muse Spark "+(r.model_call?`(${r.model_call.model}, ${r.model_call.latency_ms} ms)`:""):"OFFLINE_HEURISTIC (no model call)"}</b><br>${r.scene.explanation||""}`;};
// starter template so the Lab is never an empty, unexplained canvas
if(!state.lab.objects.length){$("lab-add")&&document.querySelector('[data-tpl="near-miss"]').click();}

// ---- theme: light / dark / system (persisted, OS-aware, pre-paint handled in <head>) ----
const _mq=matchMedia("(prefers-color-scheme: light)");
function applyTheme(){const mode=localStorage.getItem("fs-theme")||"system";
 const resolved=mode==="system"?(_mq.matches?"light":"dark"):mode;
 document.documentElement.dataset.theme=resolved;
 document.querySelectorAll("[data-theme-mode]").forEach(b=>b.classList.toggle("on",b.dataset.themeMode===mode));
 if(state&&state.data)draw(); if(state&&state.lab&&state.lab.objects.length&&$("lab-canvas"))labDraw();
 if(window.__lab3dMod&&window.__lab3dMod.refreshAll3DThemes)window.__lab3dMod.refreshAll3DThemes();
 else if(localStorage.getItem("fs-view-lab")==="3d"){import("/three-view.js").then(m=>{window.__lab3dMod=m;}).catch(()=>{});}}
document.querySelectorAll("[data-theme-mode]").forEach(b=>b.onclick=()=>{localStorage.setItem("fs-theme",b.dataset.themeMode);applyTheme();});
if(_mq.addEventListener)_mq.addEventListener("change",()=>{if((localStorage.getItem("fs-theme")||"system")==="system")applyTheme();});
applyTheme();

function download(blob,name){const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),4000);}

// ---- toasts ----
function toast(msg, kind="ok"){const host=$("toasts");if(!host)return;const d=document.createElement("div");
 d.className="toast "+(kind==="ok"?"":kind);d.textContent=msg;host.appendChild(d);
 setTimeout(()=>{d.style.opacity="0";d.style.transition="opacity .4s";setTimeout(()=>d.remove(),420);},4200);}

// ---- server accounts (first-party auth; Clerk/OIDC can replace the provider) ----
function sessionToken(){return localStorage.getItem("fs-session")||"";}
function serverUser(){try{return JSON.parse(localStorage.getItem("fs-user")||"null");}catch(e){return null;}}
function profile(){return serverUser();}
function sceneStoreKey(){const p=serverUser();return "fs-my-scenes:"+(p?("u"+p.id):"guest");}
function runsKey(){const p=serverUser();return "fs-runs:"+(p?("u"+p.id):"guest");}
async function api(path, opts={}){const tok=sessionToken();
 const r=await fetch(path,{...opts,headers:{"Content-Type":"application/json",...(tok?{"Authorization":"Bearer "+tok}:{}),...(opts.headers||{})}});
 let body={};try{body=await r.json();}catch(e){}
 return {status:r.status, body};}
state.me=null;
async function refreshMe(){const {body}=await api("/api/me");state.me=body;
 const btn=$("auth-btn"),badge=$("plan-badge");
 const so=$("auth-signedout"),si=$("auth-signedin");
 if(body.authenticated){const u=body.user;
  if(btn)btn.textContent="● "+u.name.split(" ")[0];
  if(badge){badge.textContent=body.plan==="explorer"?"Explorer":body.plan==="researcher"?"Researcher":"Team";badge.classList.remove("hidden");}
  if(so)so.classList.add("hidden");if(si)si.classList.remove("hidden");
  const who=$("auth-who");if(who)who.textContent=u.name;
  const meta=$("auth-meta");if(meta)meta.textContent=`· ${u.email} · plan: ${body.plan}${body.subscription?` · subscription ${body.subscription.status}`:""}`;
 }else{
  if(btn)btn.textContent="Sign in";
  if(badge)badge.classList.add("hidden");
  if(so)so.classList.remove("hidden");if(si)si.classList.add("hidden");
 }
 if(body.authenticated)loadOrg();else{const oc=$("org-card");if(oc)oc.textContent="Sign in to see your organisation.";}
 const card=$("me-card");
 if(card)card.innerHTML=body.authenticated
  ? `Signed in as <b>${body.user.email}</b> · plan <b>${body.plan}</b>${body.subscription?` · subscription: ${body.subscription.status}${body.subscription.cancel_at_period_end?" (cancels at period end)":""}`:" · no subscription"}<br>Entitlements: SAM video ${body.entitlements.sam_video?"✓":"—"} · server scenes ${body.entitlements.server_scenes===null?"unlimited":body.entitlements.server_scenes} · Monte-Carlo ≤ ${body.entitlements.mc_runs===null?"unlimited":body.entitlements.mc_runs} · your Meta key ${body.meta_key.configured?("saved (…"+body.meta_key.last4+")"):"not saved"}<br>Billing (Stripe): ${body.billing_configured?"configured":"not configured on this deployment"}`
  : `Not signed in (guest / Explorer). Billing (Stripe): ${body.billing_configured?"configured":"not configured on this deployment — subscriptions are disabled, waitlist is open."}`;
 return body;}
function refreshAuthUI(){refreshMe();}
$("auth-btn").onclick=()=>goto("auth");
$("tab-signup").onclick=()=>{$("form-signup").classList.remove("hidden");$("form-signin").classList.add("hidden");};
$("tab-signin").onclick=()=>{$("form-signin").classList.remove("hidden");$("form-signup").classList.add("hidden");};
async function afterAuth(out, msg){localStorage.setItem("fs-session",out.body.token);
 localStorage.setItem("fs-user",JSON.stringify(out.body.user));
 await refreshMe();renderMyScenes();toast(msg);goto("workspace");}
$("auth-signup").onclick=async()=>{const out=await api("/api/auth/signup",{method:"POST",
 body:JSON.stringify({name:$("su-name").value.trim(),email:$("su-email").value.trim(),password:$("su-password").value})});
 if(out.status!==201){$("auth-status").textContent=out.body.error||"Sign-up failed.";return;}
 afterAuth(out,`Welcome, ${out.body.user.name.split(" ")[0]} — free Explorer account created.`);};
$("auth-signin").onclick=async()=>{const out=await api("/api/auth/login",{method:"POST",
 body:JSON.stringify({email:$("si-email").value.trim(),password:$("si-password").value})});
 if(out.status!==200){$("auth-status").textContent=out.body.error||"Sign-in failed.";return;}
 afterAuth(out,`Welcome back, ${out.body.user.name.split(" ")[0]}.`);};
$("auth-guest").onclick=()=>{toast("Continuing as guest — device-local scenes only, Explorer limits.","warn");goto("home");};
$("auth-signout").onclick=async()=>{await api("/api/auth/logout",{method:"POST"});
 localStorage.removeItem("fs-session");localStorage.removeItem("fs-user");
 await refreshMe();renderMyScenes();toast("Signed out.","warn");goto("home");};
$("auth-goto-app").onclick=()=>goto("workspace");
async function manageBilling(){const out=await api("/api/billing/portal",{method:"POST"});
 if(out.status===200&&out.body.url){location.href=out.body.url;return;}
 const el=$("auth-billing-status")||$("byok-status");
 if(el)el.textContent=out.body.error||"Billing portal unavailable.";
 toast(out.body.error||"Billing portal unavailable.","warn");}
$("auth-billing").onclick=manageBilling;
$("manage-billing").onclick=manageBilling;
$("byok-save").onclick=async()=>{const key=$("byok-key").value.trim();
 if(!key){$("byok-status").textContent="Paste your Meta API key first.";return;}
 const out=await api("/api/keys/meta",{method:"PUT",body:JSON.stringify({key})});
 $("byok-status").textContent=out.status===200?`Saved (…${out.body.last4}). It will never be shown again.`
  :out.status===402?out.body.error+" — see Pricing.":(out.body.error||"Could not save the key.");
 if(out.status===200)$("byok-key").value="";refreshMe();};
$("byok-delete").onclick=async()=>{const out=await api("/api/keys/meta",{method:"PUT",body:JSON.stringify({delete:true})});
 $("byok-status").textContent=out.status===200?"Your key was removed.":(out.body.error||"Could not remove the key.");refreshMe();};

// ---- run history ----
function recordRun(rec){try{const k=runsKey();const arr=JSON.parse(localStorage.getItem(k)||"[]");
 arr.unshift({when:Date.now(),...rec});localStorage.setItem(k,JSON.stringify(arr.slice(0,20)));}catch(e){} renderRuns();}
function renderRuns(){const host=$("scenario-list");if(!host||$("runs-card"))return;let runs=[];
 try{runs=JSON.parse(localStorage.getItem(runsKey())||"[]");}catch(e){}
 if(!runs.length)return;const div=document.createElement("div");div.className="card wide";div.id="runs-card";
 div.innerHTML=`<h3>Recent runs</h3>`+runs.slice(0,8).map(r=>`<p><b>${r.scenario}</b> <span class="dim">${new Date(r.when).toLocaleString()} · ${r.mode} · ${r.pairs} pairs · ${r.events} event(s) · run ${r.run}</span></p>`).join("");
 host.appendChild(div);}

// ---- onboarding checklist ----
function obDone(k){try{const o=JSON.parse(localStorage.getItem("fs-onboard")||"{}");o[k]=true;localStorage.setItem("fs-onboard",JSON.stringify(o));}catch(e){}renderOnboard();}
function renderOnboard(){let o={};try{o=JSON.parse(localStorage.getItem("fs-onboard")||"{}");}catch(e){}
 document.querySelectorAll(".ob-row").forEach(r=>{const done=!!o[r.dataset.ob];r.classList.toggle("done",done);
  const mark=r.querySelector(".ob-mark");if(mark)mark.textContent=done?"✓":"○";});
 const card=$("onboarding");if(card&&o.demo&&o.created&&o.muse)$("ob-note").innerHTML="All three done — you have used the full loop. <a href='#' id='ob-hide'>Dismiss</a>";
 const hide=$("ob-hide");if(hide)hide.onclick=e=>{e.preventDefault();card.style.display="none";localStorage.setItem("fs-onboard-hide","1");};
 if(card&&localStorage.getItem("fs-onboard-hide")==="1")card.style.display="none";}
renderOnboard();

// ---- pricing toggle + waitlist (no billing exists; see docs/AUTH_AND_BILLING.md) ----
$("bill-toggle").onclick=()=>{const annual=$("bill-toggle").getAttribute("aria-pressed")==="true";
 $("bill-toggle").setAttribute("aria-pressed",String(!annual));
 document.querySelectorAll(".amt").forEach(a=>{a.textContent=annual?a.dataset.m:a.dataset.a;});
 document.querySelectorAll(".per").forEach(a=>{a.textContent=annual?"/mo":"/yr";});
 $("bill-toggle").firstChild.textContent=annual?"Switch to annual ":"Switch to monthly ";};
$("sub-btn").onclick=async()=>{const me=state.me||await refreshMe();
 if(!me.authenticated){toast("Create a free account first, then subscribe.","warn");goto("auth");return;}
 const annual=$("bill-toggle").getAttribute("aria-pressed")==="true";
 const out=await api("/api/billing/checkout",{method:"POST",body:JSON.stringify({period:annual?"annual":"monthly"})});
 if(out.status===200&&out.body.url){location.href=out.body.url;return;}
 if(out.body.code==="BILLING_NOT_CONFIGURED"){
  toast("Billing isn't enabled on this deployment yet — joining the waitlist instead (no payment).","warn");
  await api("/api/waitlist",{method:"POST",body:JSON.stringify({email:me.user.email,plan:"Researcher"})});
  return;}
 toast(out.body.error||"Checkout could not be started.","err");};
document.querySelectorAll(".waitlist-btn").forEach(b=>b.onclick=async()=>{
 const me=state.me||await refreshMe();
 const email=me.authenticated?me.user.email:"";
 if(!email){toast("Sign in (or create a free account) so the waitlist has an email to reach.","warn");goto("auth");return;}
 const out=await api("/api/waitlist",{method:"POST",body:JSON.stringify({email,plan:b.dataset.plan})});
 toast(out.status===201?`Waitlist joined for ${b.dataset.plan} as ${email}. No payment taken — billing is not enabled on this deployment.`
   :"Waitlist failed: "+(out.body.error||"unknown"),"warn");});
$("quote-open").onclick=()=>{$("quote-card").classList.remove("hidden");$("quote-card").scrollIntoView({behavior:"smooth"});};
$("quote-send").onclick=async()=>{const out=await api("/api/sales/quote",{method:"POST",
 body:JSON.stringify({company:$("q-company").value.trim(),email:$("q-email").value.trim(),
  seats:$("q-seats").value.trim(),needs:$("q-needs").value.trim()})});
 $("quote-status").textContent=out.status===201?"Recorded — in production this also emails the sales contact. Custom pricing is manual."
  :(out.body.error||"Could not send.");};
$("bill-toggle").addEventListener("click",()=>{const annual=$("bill-toggle").getAttribute("aria-pressed")==="true";
 const sa=$("sub-amt");if(sa)sa.textContent=annual?"$19/mo":"$190/yr";});
document.querySelectorAll("[data-goto]").forEach(b=>b.onclick=()=>goto(b.dataset.goto));

// ---- shareable Create Lab links ----
$("lab-share").onclick=async()=>{const payload={objects:state.lab.objects};
 const enc=btoa(unescape(encodeURIComponent(JSON.stringify(payload)))).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
 const url=location.origin+location.pathname+"#view=create&s="+enc;
 try{await navigator.clipboard.writeText(url);toast("Share link copied — it encodes your scene (components + paths), nothing is uploaded.");}
 catch(e){labStatus("Copy this link: "+url);}};
function loadShared(){if(!location.hash.includes("s="))return;
 try{const enc=new URLSearchParams(location.hash.slice(1)).get("s");
  const payload=JSON.parse(decodeURIComponent(escape(atob(enc.replace(/-/g,"+").replace(/_/g,"/")))));
  labLoadScene({objects:payload.objects},"Shared scene loaded from link — press Run analysis.");
  goto("create");toast("Shared scene loaded from link.");}
 catch(e){toast("That share link could not be decoded — starting with the template instead.","err");}}
loadShared();
window.addEventListener("hashchange", loadShared);

refreshMe();

document.querySelectorAll("[data-foot]").forEach(a=>a.onclick=()=>{showView(a.dataset.foot);window.scrollTo({top:0});});
document.querySelectorAll(".quick-scn").forEach(b=>b.onclick=()=>pick(b.dataset.id));

// ---- SAM Vision panel (Studio) ----
state.samCaptures=[];
function samStatus(m){const e=$("sam-status");if(e)e.textContent=m;}
$("sam-file").onchange=e=>{const f=e.target.files[0];if(!f)return;state.samSource="upload";state.samCaptures=[];$("sam-count").textContent="0";
 if(f.size>60*1024*1024){samStatus("File exceeds the 60 MB browser-preview bound.");e.target.value="";return;}
 const url=URL.createObjectURL(f),v=$("sam-video"),im=$("sam-img");
 if(f.type.startsWith("video/")){im.style.display="none";v.style.display="block";v.src=url;samStatus("Video loaded locally — pause on a moment, then Segment. Loading it uploads nothing.");}
 else if(f.type.startsWith("image/")){v.style.display="none";im.style.display="block";im.src=url;samStatus("Image loaded locally. Segment it with SAM 3.1.");}
 else samStatus("Unsupported type — use a video or image, or build the scene in Create Lab.");};
state.samSource="default";
const _samDefaultImg=new Image();
_samDefaultImg.onload=()=>{if(state.samSource!=="default")return;
 const c=$("sam-canvas");if(!c)return;const x=c.getContext("2d");
 const s=Math.min(c.width/_samDefaultImg.naturalWidth,c.height/_samDefaultImg.naturalHeight);
 const w=_samDefaultImg.naturalWidth*s,hh=_samDefaultImg.naturalHeight*s;
 x.clearRect(0,0,c.width,c.height);x.drawImage(_samDefaultImg,(c.width-w)/2,(c.height-hh)/2,w,hh);
 samStatus("Default example frame loaded — press “Segment current frame” to run SAM 3.1 on it, or load your own image/video. Expect labelled boxes with confidences; zero matches is a valid result.");};
_samDefaultImg.src="/sam-default.jpg";
$("sam-restore").onclick=()=>{state.samSource="default";state.samCaptures=[];$("sam-count").textContent="0";
 $("sam-video").style.display="none";$("sam-img").style.display="none";
 if(_samDefaultImg.complete)_samDefaultImg.onload();
 samStatus("Default example frame restored. Press Segment to run SAM 3.1 on it.");};
function samFrame(){if(state.samSource==="default"){
 const c=document.createElement("canvas");c.width=_samDefaultImg.naturalWidth;c.height=_samDefaultImg.naturalHeight;
 c.getContext("2d").drawImage(_samDefaultImg,0,0);return c;}
 const v=$("sam-video"),im=$("sam-img");
 const src=v.style.display!=="none"?(v.videoWidth&&v):(im.naturalWidth&&im);
 if(!src){samStatus("Load an image or video frame first.");return null;}
 const c=document.createElement("canvas");c.width=src.videoWidth||src.naturalWidth;c.height=src.videoHeight||src.naturalHeight;
 c.getContext("2d").drawImage(src,0,0);return c;}
$("sam-run").onclick=async()=>{const c=samFrame();if(!c)return;
 const dataUrl=c.toDataURL("image/jpeg",0.85);
 if(dataUrl.length>11*1024*1024){samStatus("Encoded frame exceeds the ingest bound — use a lower-resolution source.");return;}
 const t=$("sam-video").style.display!=="none"?+$("sam-video").currentTime.toFixed(2):0;
 const concepts=[$("sam-concept").value.trim(),$("sam-concept2").value.trim()].filter(Boolean);
 const x=$("sam-canvas").getContext("2d");x.drawImage(c,0,0,$("sam-canvas").width,$("sam-canvas").height);
 samStatus("Calling SAM 3.1…");
 for(const concept of concepts){
  let r;try{r=await(await fetch("/api/meta/segment",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image_data_url:dataUrl,concept})})).json();}
  catch(e){samStatus("Segmentation failed: API unreachable.");return;}
  if(r.status==="BLOCKED_CREDENTIALS"){samStatus("Meta API is not configured on this server (BLOCKED_CREDENTIALS). Nothing was segmented or claimed.");return;}
  if(r.error||r.status==="MODEL_ERROR"){samStatus("SAM error: "+(r.error||r.detail));return;}
  const recs=(r.frames&&r.frames[0])?r.frames[0].records:[];
  state.samCaptures.push({t,concept,records:recs});
  const sx=$("sam-canvas").width/c.width,sy=$("sam-canvas").height/c.height;
  x.strokeStyle=COL[concept]||"#38c6d9";x.lineWidth=2;
  recs.forEach(rec=>{const b=rec.box;x.strokeRect(b.x1*sx,b.y1*sy,(b.x2-b.x1)*sx,(b.y2-b.y1)*sy);});
  recs.forEach(rec=>{labelPill(x,`${concept} #${rec.object_id}${rec.confidence!=null?" "+rec.confidence.toFixed(2):""}`,rec.box.x1*sx+4,Math.max(14,rec.box.y1*sy-8),COL[concept]);});
  $("sam-records").innerHTML=recs.length?recs.map(rec=>`<li><b>${concept} #${rec.object_id}</b> · box [${rec.box.x1},${rec.box.y1}]–[${rec.box.x2},${rec.box.y2}] · confidence ${rec.confidence!=null?rec.confidence.toFixed(3):"n/a"} · source <code>MODEL_DERIVED</code></li>`).join(""):'<li class="dim">SAM returned zero matches for this concept on this frame — a valid result, recorded as-is.</li>';
  samStatus(`SAM 3.1 (${r.model||"sam-3.1"}): ${recs.length} "${concept}" object(s) at t=${t}s · ${r.latency_ms||"?"} ms · captures so far: ${state.samCaptures.length}.`);
  obDone("muse");}
 $("sam-count").textContent=state.samCaptures.length;};
$("sam-build").onclick=async()=>{if(state.samCaptures.length<2){samStatus("Segment at least two moments of a video first — one frame cannot produce motion.");return;}
 const byConcept={};state.samCaptures.forEach(f=>{(byConcept[f.concept]=byConcept[f.concept]||[]).push({t:f.t,records:f.records});});
 let all=[];for(const [concept,frames] of Object.entries(byConcept)){
  const r=await(await fetch("/api/tracks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({frames,category:concept})})).json();
  if(r.error){samStatus("Track build failed: "+r.error);return;}
  all=all.concat(r.tracks.map(t=>({...t,object_id:concept+"-"+t.object_id.split("-").pop(),category:concept})));}
 if(all.filter(t=>t.points.length>1).length<2){samStatus("Built tracks are too short to analyse (need 2+ moving tracks with 2+ points). Capture more moments with visible motion.");return;}
 samStatus(`Built ${all.length} track(s) — running full analysis…`);
 try{await analyzeCustom(all,"sam-"+Date.now());}catch(e){samStatus("Analysis failed: "+e.message);}};

// ---- playback: true delta-time (timer accuracy is refresh-rate independent) ----
state.playSpeed=1; state._playLast=null;
document.querySelectorAll(".speedseg button").forEach(b=>b.onclick=()=>{
 state.playSpeed=+b.dataset.speed;
 document.querySelectorAll(".speedseg button").forEach(x=>x.classList.toggle("on",x===b));});
$("play").onclick=()=>{state.playing=!state.playing;$("play").textContent=state.playing?"⏸ Pause":"▶ Play";
 state._playLast=null;
 if(state.playing){const step=(ts)=>{if(!state.playing)return;
   if(state._playLast==null)state._playLast=ts;
   const dt=Math.min(0.1,(ts-state._playLast)/1000);state._playLast=ts;
   state.t+=dt*(state.playSpeed||1);
   if(state.t>(state.duration||8))state.t=0;
   draw();requestAnimationFrame(step);};
  requestAnimationFrame(step);}};

// ---- counterfactual export ----
$("cf-export").onclick=()=>{if(!state.cfData){$("cf-results").textContent="Run a simulation first, then export.";return;}
 download(new Blob([JSON.stringify(state.cfData,null,2)],{type:"application/json"}),"frontiersight-counterfactual.json");
 toast("Counterfactual result exported (JSON).");};

// ---- workspace search + live counts ----
function applyUnifiedFilter(){const q=($("ws-search").value||"").toLowerCase();
 const kind=$("ws-lib-kind").value;
 document.querySelectorAll(".scenario-card").forEach(c=>{
  c.style.display=(!kind||kind==="scenario")&&c.dataset.search.includes(q)?"":"none";});
 document.querySelectorAll(".ws-card").forEach(c=>{
  c.style.display=(!kind||c.dataset.kind===kind)&&c.dataset.search.includes(q)?"":"none";});
 const sc=$("scenario-list");if(sc)sc.style.display=(!kind||kind==="scenario")?"":"none";}
$("ws-search").addEventListener("input",applyUnifiedFilter);
$("ws-lib-kind").addEventListener("change",applyUnifiedFilter);

// ---- settings: version + clear local data ----
(async()=>{try{const h=await(await fetch("/api/health")).json();
 const fv=$("foot-version");if(fv)fv.textContent="v"+h.version;const sv=$("set-version");if(sv)sv.textContent=h.version;}catch(e){}})();
$("clear-data").onclick=()=>{const keys=Object.keys(localStorage).filter(k=>k.startsWith("fs-"));
 keys.forEach(k=>localStorage.removeItem(k));
 $("clear-status").textContent=`Removed ${keys.length} local item(s). Reloading…`;
 toast("Local data cleared — profiles, scenes, runs and preferences on this device are gone.","warn");
 setTimeout(()=>location.reload(),900);};
$("lab-clear-all").onclick=()=>{state.lab.objects=[];state.lab.selected=null;labRenderList();labDraw();
 labStatus("All components cleared. Add components or load a template to start again.");};

// ---- global error surface (throttled; errors become visible, never silent) ----
let _lastErr=0;
window.addEventListener("unhandledrejection",e=>{const now=Date.now();if(now-_lastErr<5000)return;_lastErr=now;
 toast("Something went wrong in the interface: "+((e.reason&&e.reason.message)||"async error")+" — reload if it persists.","err");});
window.addEventListener("error",e=>{const now=Date.now();if(now-_lastErr<5000)return;_lastErr=now;
 toast("Something went wrong in the interface: "+(e.message||"unknown error")+" — the deterministic API is unaffected; reload if it persists.","err");});

const _skipEl=$("skip-link");
if(_skipEl)_skipEl.onclick=()=>{showView("home");
 const el=document.querySelector("#view-home h1");
 if(el){el.setAttribute("tabindex","-1");el.focus();el.scrollIntoView({behavior:"smooth",block:"start"});}};

// ---- support + organisation (Settings) ----
$("sup-send").onclick=async()=>{const out=await api("/api/support",{method:"POST",
 body:JSON.stringify({subject:$("sup-subject").value.trim(),message:$("sup-message").value.trim()})});
 $("sup-status").textContent=out.status===201?("Opened — "+out.body.note):(out.body.error||"Could not open the request.");
 if(out.status===201){$("sup-subject").value="";$("sup-message").value="";toast("Support request opened ("+(out.body.priority?"priority":"standard")+" queue).");}};
async function loadOrg(){const card=$("org-card");if(!card)return;
 const out=await api("/api/org");
 if(out.status===401){card.textContent="Sign in to see your organisation.";return;}
 if(!out.body.org){card.textContent=out.body.note||"No organisation.";return;}
 card.innerHTML=`<b>${out.body.org}</b> · your role: ${out.body.role} · ${out.body.members.length} member(s)<br>`+
  out.body.members.map(m=>`${m.email} (${m.role})`).join("<br>")+
  (out.body.shared_scenes.length?`<br>Shared org scenes: ${out.body.shared_scenes.map(s=>s.name).join(", ")}`:"")+
  (out.body.audit_log&&out.body.audit_log.length?`<br>Audit log (latest): ${out.body.audit_log.slice(0,5).map(a=>a.action).join(", ")}`:"");}

// ---- form system behaviours: password toggles, range fill, invalid states ----
document.querySelectorAll('input[type="password"]').forEach(inp=>{
 const wrap=document.createElement("span");wrap.className="passwrap";
 inp.parentNode.insertBefore(wrap,inp);wrap.appendChild(inp);
 const b=document.createElement("button");b.type="button";b.className="pass-toggle";
 b.textContent="Show";b.setAttribute("aria-label","Show password");
 b.onclick=()=>{const show=inp.type==="password";inp.type=show?"text":"password";
  b.textContent=show?"Hide":"Show";b.setAttribute("aria-label",show?"Hide password":"Show password");};
 wrap.appendChild(b);});
function paintRange(r){const min=+r.min||0,max=+r.max||100,v=+r.value||0;
 r.style.setProperty("--fill",((v-min)/(max-min)*100)+"%");}
document.querySelectorAll('input[type="range"]').forEach(r=>{paintRange(r);
 r.addEventListener("input",()=>paintRange(r));});
function markInvalid(ids,invalid){ids.forEach(id=>{const el=$(id);if(el)el.classList.toggle("invalid",invalid);});}
["su-name","su-email","su-password","si-email","si-password","byok-key"].forEach(id=>{
 const el=$(id);if(el)el.addEventListener("input",()=>el.classList.remove("invalid"));});
const _suBtn=$("auth-signup");if(_suBtn){const _su=_suBtn.onclick;
 _suBtn.onclick=async()=>{await _su();if($("auth-status").textContent)markInvalid(["su-name","su-email","su-password"],true);};}
const _siBtn=$("auth-signin");if(_siBtn){const _si=_siBtn.onclick;
 _siBtn.onclick=async()=>{await _si();if($("auth-status").textContent)markInvalid(["si-email","si-password"],true);};}

// ---- Workspaces: saved labs + SAM frame sets (search · open · update · delete) ----
function wsKey(){const u=(typeof serverUser==="function")?serverUser():null;return "fs-workspaces:"+(u?("u"+u.id):"guest");}
function wsLocalList(){try{return JSON.parse(localStorage.getItem(wsKey())||"[]");}catch(e){return[];}}
function wsLocalSave(list){try{localStorage.setItem(wsKey(),JSON.stringify(list.slice(0,40)));return true;}
 catch(e){toast("Browser storage is full — delete a workspace or sign in to save on the server.","err");return false;}}
state.workspaces=[]; state.openWorkspace=null;
function wsNormalizeLocal(w){return {...w, server:false, key:"local:"+w.id};}
function wsNormalizeServer(s){const w=(s.payload&&s.payload.workspace)||{};
 return {key:"server:"+s.id, server:true, id:s.id, name:s.name||w.name||"workspace",
  kind:w.kind||(s.payload&&s.payload.tracks?"frames":"lab"), updated:(s.created_at||0)*1000,
  objects:w.objects||(s.payload&&s.payload.objects)||null, tracks:w.tracks||(s.payload&&s.payload.tracks)||null,
  captures:w.captures||null, image:w.image||null};}
async function loadWorkspaces(){
 let list=wsLocalList().map(wsNormalizeLocal);
 // legacy analysed scenes become workspaces (read-compat, deduped by id)
 try{const legacy=JSON.parse(localStorage.getItem((typeof sceneStoreKey==="function"?sceneStoreKey():"fs-my-scenes"))||"[]");
  for(const m of legacy) if(!list.some(w=>w.id===m.id))
   list.push({key:"legacy:"+m.id, server:false, legacy:true, id:m.id, name:m.id, kind:"lab", updated:m.when, tracks:m.tracks, objects:null});}catch(e){}
 if(sessionToken()){try{const out=await api("/api/scenes");
   if(out.status===200){const srv=out.body.scenes.map(wsNormalizeServer);
    const note=$("ws-storage-note");if(note)note.textContent="Synced with your account on the server (plus anything kept only in this browser).";
    list=srv.concat(list.filter(w=>!srv.some(s=>s.name===w.name)));}}catch(e){}}
 state.workspaces=list.sort((a,b)=>(b.updated||0)-(a.updated||0));
 renderWorkspaces(); populateStudioWorkspaces();}
function renderWorkspaces(){const host=$("workspace-list");if(!host)return;
 if(!state.workspaces.length){host.innerHTML='<p class="dim">Nothing saved yet — build a scene in Create Lab, or segment frames in the Studio, then save.</p>';return;}
 host.innerHTML=state.workspaces.map(w=>`<article class="card ws-card" data-key="${w.key}" data-kind="${w.kind}"
   data-search="${(w.name+" "+w.kind+" "+(w.objects?w.objects.map(o=>o.category).join(" "):"")).toLowerCase()}">
  <button class="kebab" data-kebab aria-label="Workspace actions" title="Actions">\u22ef</button>
  <div class="ws-menu hidden" role="menu">
   <button data-ws="open">Open</button>
   ${(w.objects||w.tracks)?'<button data-ws="studio">Open in Studio</button>':""}
   ${w.kind==="lab"?'<button data-ws="update">Update from current Lab</button>':""}
   ${w.tracks?'<button data-ws="analyse">Analyse tracks</button>':""}
   <button data-ws="rename">Rename</button>
   <div class="sep"></div>
   <button data-ws="del" class="danger">Delete</button>
  </div>
  <div class="ws-head"><h4>${w.kind==="frames"?"\u25a3":"\u2726"} ${w.name}</h4></div>
  <div>
   <span class="pill ghost">${w.kind==="frames"?"SAM frame set":"Create Lab scene"}</span>
   <span class="pill ghost">${w.server?"server":"this browser"}</span>
  </div>
  <p class="ws-meta">${new Date(w.updated||Date.now()).toLocaleString()}${w.objects?` · ${w.objects.length} components`:""}${w.captures?` · ${w.captures.length} captured frame(s)`:""}${w.tracks?` · ${w.tracks.length} tracks`:""}</p>
  <div class="ws-foot"><button data-ws="open">Open</button>
   <span class="dim">${w.kind==="frames"?"Reopen in the Studio SAM panel":"Reopen in Create Lab"}</span></div>
 </article>`).join("");
 host.querySelectorAll(".ws-card").forEach(card=>{const w=state.workspaces.find(x=>x.key===card.dataset.key);
  const menu=card.querySelector(".ws-menu");
  card.querySelector("[data-kebab]").onclick=e=>{e.stopPropagation();
   document.querySelectorAll(".ws-menu").forEach(m=>{if(m!==menu)m.classList.add("hidden");});
   menu.classList.toggle("hidden");};
  card.querySelectorAll("button[data-ws]").forEach(b=>b.onclick=async()=>{const a=b.dataset.ws;
   menu.classList.add("hidden");
   if(a==="open")openWorkspace(w);
   if(a==="studio")loadWorkspaceIntoStudio(w);
   if(a==="analyse"&&w.tracks){analyzeCustom(w.tracks,"workspace-"+w.id).catch(()=>{});}
   if(a==="update"){w.objects=JSON.parse(JSON.stringify(state.lab.objects));w.updated=Date.now();
    await persistWorkspace(w);labSetTitle(w.name,true);toast(`Workspace "${w.name}" updated from the current Lab scene.`);loadWorkspaces();}
   if(a==="rename"){wsRenameInline(card,w);}
   if(a==="del"){await deleteWorkspace(w);loadWorkspaces();}
  });});
 applyUnifiedFilter();}
function wsRenameInline(card,w){const h4=card.querySelector("h4");if(!h4||card.querySelector(".ws-rename"))return;
 const input=document.createElement("input");input.type="text";input.className="ws-rename";
 input.value=w.name;input.setAttribute("aria-label","Rename workspace");
 h4.replaceWith(input);input.focus();input.select();
 const commit=async()=>{const name=input.value.trim().slice(0,120)||w.name;
  w.name=name;w.updated=Date.now();await persistWorkspace(w);loadWorkspaces();};
 input.addEventListener("keydown",e=>{if(e.key==="Enter")commit();if(e.key==="Escape")loadWorkspaces();});
 input.addEventListener("blur",commit);}
document.addEventListener("click",e=>{if(!e.target.closest(".ws-card"))
 document.querySelectorAll(".ws-menu").forEach(m=>m.classList.add("hidden"));});
document.addEventListener("keydown",e=>{if(e.key==="Escape")
 document.querySelectorAll(".ws-menu").forEach(m=>m.classList.add("hidden"));});
async function persistWorkspace(w){
 if(sessionToken()&&!w.legacy){
  const payload={workspace:{kind:w.kind,objects:w.objects||null,tracks:w.tracks||null,captures:w.captures||null,image:w.image||null}};
  if(w.server&&w.id){const out=await api("/api/scenes/update",{method:"POST",body:JSON.stringify({id:w.id,name:w.name,payload})});
   if(out.status===200)return true;}
  const out=await api("/api/scenes",{method:"POST",body:JSON.stringify({name:w.name,payload})});
  if(out.status===201){w.server=true;w.id=out.body.id;return true;}
  if(out.status===402){toast(out.body.error+" — saving in this browser instead.","warn");}
 }
 const list=wsLocalList().filter(x=>x.id!==w.id);
 list.unshift({id:w.id||("ws-"+Date.now()),name:w.name,kind:w.kind,updated:w.updated||Date.now(),
  objects:w.objects||null,tracks:w.tracks||null,captures:w.captures||null,image:w.image||null});
 return wsLocalSave(list);}
async function deleteWorkspace(w){
 if(w.server&&sessionToken()){await api("/api/scenes/delete",{method:"POST",body:JSON.stringify({id:w.id})});}
 wsLocalSave(wsLocalList().filter(x=>x.id!==w.id));
 if(state.openWorkspace&&state.openWorkspace.key===w.key)state.openWorkspace=null;
 toast(`Workspace "${w.name}" deleted.`);}
function openWorkspace(w){state.openWorkspace=w;
 if(w.kind==="frames"){
  state.samCaptures=w.captures||[];
  const cnt=$("sam-count");if(cnt)cnt.textContent=state.samCaptures.length;
  goto("studio");
  if(w.image){const img=new Image();img.onload=()=>{const c=$("sam-canvas");c.getContext("2d").drawImage(img,0,0,c.width,c.height);};img.src=w.image;}
  else if(w.tracks){toast(`Workspace "${w.name}" has ${w.tracks.length} built track(s) — use "Analyse tracks" on its card, or segment new frames.`);}
  else toast(`Workspace "${w.name}" reopened with ${state.samCaptures.length} captured frame(s) — Build tracks when ready.`);
  const st=$("sam-status");if(st)st.textContent=`Workspace "${w.name}" loaded: ${state.samCaptures.length} captured frame(s). Segment more moments or Build tracks.`;
  document.getElementById("sam-panel").scrollIntoView({behavior:"smooth"});
 }else{
  if(w.objects){labLoadScene({objects:w.objects},`Workspace "${w.name}" opened — edit anything, then Run analysis or Update.`);}
  else if(w.tracks){analyzeCustom(w.tracks,"workspace-"+w.id).catch(()=>{});return;}
  goto("create");
  const uw=$("lab-update-ws");if(uw)uw.classList.remove("hidden");
 }}

$("lab-save-ws").onclick=async()=>{if(!state.lab.objects.length){labStatus("Nothing to save yet — add a component first.");return;}
 const name=($("lab-ws-name").value||"").trim()||suggestedName(state.labTitle);
 const w={id:"ws-"+Date.now(),name,kind:"lab",updated:Date.now(),
  objects:JSON.parse(JSON.stringify(state.lab.objects))};
 state.openWorkspace=w;
 if(await persistWorkspace(w)){state.openWorkspace=w;const uw=$("lab-update-ws");if(uw)uw.classList.remove("hidden");
  labSetTitle(name,true);const sv=$("lab-save-ws");sv.classList.remove("pulse");sv.textContent="Save workspace";
  toast(`Workspace "${name}" saved${w.server?" on the server":" in this browser"} — now in Workspace and the Studio dropdown.`);loadWorkspaces();}};
$("lab-update-ws").onclick=async()=>{const w=state.openWorkspace;
 if(!w){toast("Open a workspace first, or use Save workspace.","warn");return;}
 w.objects=JSON.parse(JSON.stringify(state.lab.objects));w.updated=Date.now();
 if(await persistWorkspace(w)){labSetTitle(w.name,true);toast(`Workspace "${w.name}" updated.`);loadWorkspaces();}};
$("sam-save-ws").onclick=async()=>{if(!state.samCaptures.length){samStatus("Capture at least one frame first.");return;}
 let image=null;try{const c=$("sam-canvas");image=c.toDataURL("image/jpeg",0.62);if(image.length>600000)image=null;}catch(e){}
 const w={id:"ws-"+Date.now(),name:"SAM frames "+new Date().toLocaleTimeString(),kind:"frames",
  updated:Date.now(),captures:state.samCaptures,image,
  tracks:null};
 if(await persistWorkspace(w)){toast(`Frame workspace saved${w.server?" on the server":" in this browser"}${image?"":" (frame image too large to store — captures kept)"}.`);loadWorkspaces();}};

// ---- MCP server card (Settings) ----
(async()=>{const el=$("mcp-tools");if(!el)return;
 try{const r=await fetch("/api/mcp");const d=await r.json();
  $("mcp-endpoint").textContent=location.origin+"/api/mcp";
  el.innerHTML=`<b>${d.name} v${d.version}</b> · protocol ${d.protocol} · ${(d.tools||[]).length} tools<br>`+
   (d.tools||[]).map(t=>`<code>${t.name}</code>`).join(" · ");
 }catch(e){el.textContent="MCP endpoint unreachable from this browser.";}})();


// ---- Clerk (identity + billing) — config-gated, first-party auth stays the fallback ----
let ClerkApp = null;
async function syncClerkSession() {
  if (!ClerkApp || !ClerkApp.user) return;
  try {
    const token = await ClerkApp.session.getToken();
    if (!token) return;
    const out = await api("/api/auth/clerk-sync", { method: "POST",
      headers: { "Authorization": "Bearer " + token },
      body: JSON.stringify({ email: (ClerkApp.user.primaryEmailAddress || {}).emailAddress || "",
                             name: ClerkApp.user.fullName || "" }) });
    if (out.status === 200) {
      localStorage.setItem("fs-session", out.body.token);
      localStorage.setItem("fs-user", JSON.stringify(out.body.user));
      await refreshMe(); renderMyScenes();
    }
  } catch (e) { /* server sync is best-effort; entitlements refresh on next load */ }
}
async function initClerk() {
  const note = $("clerk-note");
  let cfg = state.authConfig;
  try { if (!cfg) { cfg = await (await fetch("/api/auth/config")).json(); state.authConfig = cfg; } }
  catch (e) { if (note) note.textContent = "Sign-in providers unavailable right now; email/password below still works."; return; }
  if (!cfg.clerk_enabled) {
    if (note) note.textContent = "Clerk single sign-on is not configured on this deployment (CLERK_PUBLISHABLE_KEY missing). Email/password accounts below are fully functional.";
    return;
  }
  try {
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js";
      s.async = true; s.crossOrigin = "anonymous";
      s.setAttribute("data-clerk-publishable-key", cfg.clerk_publishable_key);
      s.onload = resolve; s.onerror = reject;
      document.head.appendChild(s);
    });
    ClerkApp = window.Clerk;
    try { await ClerkApp.load({ publishableKey: cfg.clerk_publishable_key }); }
    catch (e) { await ClerkApp.load(); }
    if (note) note.innerHTML = `Signed in with <b>Clerk</b> (${cfg.clerk_instance} instance). ` +
      (ClerkApp.user ? "Manage your account from the avatar menu." : "Use the Clerk form below, or email/password further down.");
    const btnSlot = $("clerk-userbtn");
    if (ClerkApp.user && btnSlot && ClerkApp.mountUserButton) {
      ClerkApp.mountUserButton(btnSlot, {});
      const ab = $("auth-btn"); if (ab) ab.classList.add("hidden");
    }
    const si = $("clerk-signin");
    if (si && !ClerkApp.user && ClerkApp.mountSignIn) ClerkApp.mountSignIn(si, {});
    if (ClerkApp.user) await syncClerkSession();
    if (ClerkApp.addListener) ClerkApp.addListener(({ user }) => {
      if (user) syncClerkSession();
      else { localStorage.removeItem("fs-session"); localStorage.removeItem("fs-user"); refreshMe(); }
    });
    // Clerk Billing pricing table (plans live in Clerk Dashboard)
    const tableHost = $("clerk-pricing");
    if (tableHost && typeof ClerkApp.mountPricingTable === "function") {
      try {
        ClerkApp.mountPricingTable(tableHost, {});
        tableHost.classList.remove("hidden");
        const cards = $("plan-cards"); if (cards) cards.style.display = "none";
        const det = document.createElement("p"); det.className = "dim";
        det.textContent = "Checkout and plan management run through Clerk (development instance). Feature comparison below still applies.";
        tableHost.appendChild(det);
      } catch (e) {
        tableHost.innerHTML = `<p class="dim">Clerk Billing could not render here (${(e && e.message) || "billing not enabled"}). ` +
          `Enable Billing in the Clerk Dashboard and create the plans described in docs/CLERK_SETUP.md — the plans below remain available via Stripe/waitlist.</p>`;
        tableHost.classList.remove("hidden");
      }
    }
  } catch (e) {
    if (note) note.textContent = "Clerk could not be loaded (network/CDN). Email/password accounts below remain fully functional.";
  }
}
initClerk();

// ---- help search + jump navigation ----
$("help-search").addEventListener("input",e=>{const q=e.target.value.toLowerCase();
 document.querySelectorAll(".help-block").forEach(b=>{
  b.style.display=!q||b.textContent.toLowerCase().includes(q)?"":"none";});});
document.querySelectorAll("[data-help-jump]").forEach(b=>b.onclick=()=>{
 const el=document.getElementById(b.dataset.helpJump);
 if(el){el.style.display="";el.scrollIntoView({behavior:"smooth",block:"start"});}});


// ---- voice dictation: mic -> browser WAV encode -> Muse Voice Transcribe ----
const voice = { rec: null, chunks: [], stream: null, started: 0, timer: null };
function micStatus(m) { const e = $("mic-status"); if (e) e.textContent = m; }
function encodeWavPcm16(samples, sampleRate) {
  const buf = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buf);
  const wstr = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  wstr(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); wstr(8, "WAVE");
  wstr(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true); v.setUint16(32, 2, true);
  v.setUint16(34, 16, true); wstr(36, "data"); v.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => v.setInt16(44 + i * 2, Math.max(-32768, Math.min(32767, Math.round(s * 32767))), true));
  return new Blob([buf], { type: "audio/wav" });
}
async function blobToWav24k(blob) {
  const AC = window.AudioContext || window.webkitAudioContext;
  const ac = new AC();
  const decoded = await ac.decodeAudioData(await blob.arrayBuffer());
  const off = new OfflineAudioContext(1, Math.ceil(decoded.duration * 24000), 24000);
  const src = off.createBufferSource(); src.buffer = decoded; src.connect(off.destination); src.start();
  const rendered = await off.startRendering();
  ac.close();
  return encodeWavPcm16(rendered.getChannelData(0), 24000);
}
function setTranscript(text, label) {
  const ta = $("lab-prompt");
  const cur = ta.value.trim();
  ta.value = cur ? (cur + (/\s$/.test(ta.value) ? "" : " ") + text) : text;
  ta.dispatchEvent(new Event("input"));
  const chip = $("voice-src");
  chip.textContent = label; chip.classList.remove("hidden");
  ta.focus();
}
async function stopRecording() {
  if (!voice.rec) return;
  const rec = voice.rec; voice.rec = null;
  clearInterval(voice.timer);
  $("mic-btn").classList.remove("recording"); $("mic-btn").textContent = "🎙 Speak instead";
  rec.stop();
}
$("mic-btn").onclick = async () => {
  if (voice.rec) { stopRecording(); return; }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === "undefined") {
    micStatus("This browser cannot record audio. You can still type the scene above.");
    return;
  }
  micStatus("Requesting microphone access…");
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch (e) { micStatus("Microphone access was denied. Allow the mic in your browser's site settings, or type the scene above."); return; }
  voice.stream = stream; voice.chunks = [];
  const rec = new MediaRecorder(stream);
  voice.rec = rec; voice.started = Date.now();
  rec.ondataavailable = e => { if (e.data.size) voice.chunks.push(e.data); };
  rec.onstop = async () => {
    stream.getTracks().forEach(t => t.stop());
    const secs = (Date.now() - voice.started) / 1000;
    micStatus("Transcribing with Muse Voice Transcribe…");
    try {
      const raw = new Blob(voice.chunks, { type: rec.mimeType || "audio/webm" });
      const wav = await blobToWav24k(raw);
      if (wav.size > 9 * 1024 * 1024) { micStatus("That take is too long for one transcription — keep it under about 2 minutes."); return; }
      const dataUrl = await new Promise(res => { const fr = new FileReader();
        fr.onload = () => res(fr.result); fr.readAsDataURL(wav); });
      const lang = $("voice-lang").value;
      const resp = await fetch("/api/meta/transcribe", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ audio_data_url: dataUrl, language_bias: lang ? [lang] : null }) });
      const out = await resp.json();
      if (resp.status === 200 && !out.transcript) {
        micStatus("Meta heard no speech in that take — try again a little closer to the microphone, or type the scene.");
      } else if (resp.status === 200 && out.transcript) {
        setTranscript(out.transcript, `Heard via Muse Voice Transcribe · ${secs.toFixed(1)}s of audio`);
        micStatus(`Transcribed by ${out.model} in ${(out.latency_ms / 1000).toFixed(1)}s — edit the text above, then Generate scene.`);
      } else {
        micStatus("Transcription did not complete: " + (out.error || out.detail || ("HTTP " + resp.status)) +
          ("webkitSpeechRecognition" in window || "SpeechRecognition" in window
            ? " You can try your browser's built-in speech recognition instead (different provider, labelled as such)."
            : " You can still type the scene above."));
        if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window)
          $("voice-fallback").classList.remove("hidden");
      }
    } catch (e) { micStatus("Transcription failed in the browser: " + e.message + " — the typed flow still works."); }
  };
  rec.start(250);
  $("mic-btn").classList.add("recording");
  const tick = () => { const s = Math.floor((Date.now() - voice.started) / 1000);
    $("mic-btn").textContent = `■ Stop · ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    if (s >= 120) { micStatus("Two-minute cap reached — transcribing what we have."); stopRecording(); } };
  tick(); voice.timer = setInterval(tick, 500);
  micStatus("Recording… speak your scene now (for example: “a forklift crosses an aisle while a pedestrian walks the other way”), then press Stop.");
};
$("voice-fallback").onclick = () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { micStatus("This browser has no built-in speech recognition either — typing is the way."); return; }
  const langMap = { "": navigator.language || "en-US", English: "en-US", Spanish: "es-ES", Hindi: "hi-IN",
    French: "fr-FR", German: "de-DE", Portuguese: "pt-PT", Japanese: "ja-JP", Korean: "ko-KR", "Mandarin Chinese": "zh-CN" };
  const rec = new SR();
  rec.lang = langMap[$("voice-lang").value] || "en-US";
  rec.interimResults = false;
  micStatus("Listening with your browser's speech recognition (not Meta)…");
  rec.onresult = e => { const text = e.results[0][0].transcript;
    setTranscript(text, "Heard via your browser's speech recognition (not Meta)");
    micStatus("Browser transcription added above — edit it, then Generate scene."); };
  rec.onerror = e => micStatus("Browser speech recognition error: " + e.error);
  rec.start();
};
