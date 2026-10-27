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
 if(v==="create"&&typeof labDraw==="function")labDraw();
 if(v==="counterfactual"&&state.data){populateCfScene();populateCfAgents();if(state.cfData){drawCfMap();drawCfChart();}}}
document.querySelectorAll("#tabs button").forEach(b=>b.onclick=()=>showView(b.dataset.view));
function goto(v){showView(v);}

async function diag(){try{const d=await(await fetch("/api/diagnostics")).json();
 $("mode").textContent=d.meta_configured?"● LIVE META":"● FIXTURE REPLAY";
 $("mode").className="pill "+(d.meta_configured?"ok":"warn");
 $("hero-diag").textContent=`Meta: ${d.meta_configured?"configured":"not configured"} · Spark ${d.spark_model} · SAM ${d.sam_model} · mode ${d.mode}`;
 $("diag").textContent=JSON.stringify(d,null,2);}catch(e){$("mode").textContent="● API OFFLINE";}}

async function loadScenarios(){let d;try{d=await(await fetch("/api/scenarios")).json();}
 catch(e){$("scenario-list").innerHTML='<div class="card wide"><h3>Could not load scenarios</h3><p class="dim">The API is unreachable. Check <code>/api/health</code>, then reload. Nothing has been simulated or hidden.</p><button onclick="location.reload()">Reload</button></div>';return;}
 state.scenarioList=d.scenarios; populateCfScene();
 $("scenario-select").innerHTML=d.scenarios.map(s=>`<option value="${s.id}">${s.id}</option>`).join("");
 $("scenario-list").innerHTML=d.scenarios.map(s=>`<div class="card scenario-card" data-search="${(s.id+" "+s.description).toLowerCase()}" data-card="${s.id}"><h3>${s.id}</h3><p class="dim">${s.description}</p><p class="dim counts" data-counts="${s.id}">loading counts…</p><button onclick="pick('${s.id}')">Open in Studio →</button></div>`).join("");
 d.scenarios.forEach(async s=>{try{const f=await(await fetch("/api/scenarios?name="+s.id)).json();
  const el=document.querySelector(`[data-counts="${s.id}"]`);const n=f.tracks.length;
  if(el)el.textContent=`${n} objects · ${n*(n-1)/2} analysed pairs · ${f.calibration.metres_per_pixel?"calibrated (m)":"pixel space"}`;}catch(e){}});
 const v=await(await fetch("/api/validate")).json();
 $("validation-list").innerHTML=v.cases.map(c=>`<li>${c.passed?"✓":"✗"} <b>${c.case}</b> — <span class="dim">${c.detail}</span></li>`).join("");
 renderMyScenes();
 state.data=await(await fetch("/api/scenarios?name="+d.scenarios[0].id)).json();state.scenario=d.scenarios[0].id;
 renderObjects();draw();populateCfScene();   // silent preload: user stays on Overview
}
function renderMyScenes(){const host=$("scenario-list");if(!host)return;
 const old=$("my-scenes-card");if(old)old.remove();const oldRuns=$("runs-card");if(oldRuns)oldRuns.remove();
 let mine=[];
 try{mine=JSON.parse(localStorage.getItem(sceneStoreKey())||localStorage.getItem("fs-my-scenes")||"[]");}catch(e){}
 renderRuns();
 if(!mine.length){renderRuns();return;}const div=document.createElement("div");div.className="card wide";div.id="my-scenes-card";
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
 resetRunState();state.data=d;state.scenario=id;state.t=0;
 $("scenario-select").value=id;renderObjects();draw();populateCfScene();goto("studio");};
$("scenario-select").onchange=e=>pick(e.target.value);

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
function draw(){const c=$("stage");if(!c||!state.data)return;computeWorld();const x=c.getContext("2d"),W=c.width,H=c.height;
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

$("analyze").onclick=async()=>{$("analyze-status").textContent="Running bounded agent workflow…";
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
 (r.run&&r.run.findings.pairs?`<h3>All pairs (${r.run.findings.pairs.length})</h3><table class="pairtable"><tr><th>Pair</th><th>d_min</th><th>Units</th><th>TTC</th><th>Event</th><th>Metric claims</th></tr>${r.run.findings.pairs.map(p=>`<tr><td>${p.pair.join(" ↔ ")}</td><td>${p.d_min}</td><td>${p.units}</td><td>${p.ttc_s??"—"}</td><td>${p.event?p.event.type:"—"}</td><td>${p.metric_claims?"yes":"no (pixel space)"}</td></tr>`).join("")}</table>`:"");}

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
async function runCf(){if(!state.data){$("cf-results").textContent="Load or create a scene first.";return;}
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
 r=normalizeCf(r);state.cfData=r;state.cfT=0;
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
function drawCfMap(){const r=state.cfData,c=$("cf-map");if(!r||!c)return;const x=c.getContext("2d"),W=c.width,H=c.height;
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
function drawCfFromRun(run){ if(state.data&&$("cf-scene")){ populateCfScene(); if(state.cfData)runCf(); } }
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
$("cf-scrub").oninput=e=>{state.cfT=+e.target.value;drawCfMap();drawCfChart();};
$("cf-play").onclick=()=>{state.cfPlaying=!state.cfPlaying;$("cf-play").textContent=state.cfPlaying?"⏸ Pause":"▶ Play comparison";
 if(state.cfPlaying){const step=()=>{if(!state.cfPlaying)return;state.cfT+=0.05;if(state.cfT>6)state.cfT=0;drawCfMap();drawCfChart();requestAnimationFrame(step);};step();}};

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
function labAdd(cat,waypoints,speed,radius,delay,mode){
 const o={id:labId(cat),category:cat,radius:radius??(cat==="shelf"?1.1:cat==="forklift"||cat==="vehicle"?0.9:0.5),
  speed:speed??(cat==="shelf"?0:1.4),delay:delay??0,mode:mode||"stop",waypoints:waypoints||[]};
 if(!o.waypoints.length){const s=LAB_SLOTS[state.lab.objects.length%LAB_SLOTS.length];o.waypoints=[[s[0],s[1]]];o.spawned=true;}
 state.lab.objects.push(o);state.lab.selected=o.id;labRenderList();labDraw();return o;}
function labClear(){$("lab-canvas").getContext("2d").clearRect(0,0,880,620);}
function labXY(x,y,W,H){return [x/LAB.w*W, H-(y/LAB.h*H)];}
function labInv(px,py,W,H){return [Math.round(px/W*LAB.w*10)/10, Math.round((H-py)/H*LAB.h*10)/10];}
function pathLen(o){let L=0;for(let i=1;i<o.waypoints.length;i++){const[a,b]=[o.waypoints[i-1],o.waypoints[i]];L+=Math.hypot(b[0]-a[0],b[1]-a[1]);}return L;}
function pathDur(o){return o.speed>0?pathLen(o)/o.speed:0;}
function labDuration(){return Math.min(20,Math.max(4,...state.lab.objects.map(o=>o.delay+pathDur(o))));}
function posOnPath(o,t){if(!o.waypoints.length)return null;
 let lt=Math.max(0,t-o.delay);if(o.waypoints.length===1||o.speed<=0||lt===0)return o.waypoints[0];
 const D=pathDur(o);if(D>0&&lt>D){if(o.mode==="loop")lt=lt%D;else if(o.mode==="pingpong"){const m=lt%(2*D);lt=m>D?2*D-m:m;}else lt=D;}
 let d=o.speed*lt;for(let i=1;i<o.waypoints.length;i++){const[a,b]=[o.waypoints[i-1],o.waypoints[i]];
  const seg=Math.hypot(b[0]-a[0],b[1]-a[1]);if(d<=seg){const k=seg?d/seg:0;return [a[0]+(b[0]-a[0])*k,a[1]+(b[1]-a[1])*k];}d-=seg;}
 return o.waypoints[o.waypoints.length-1];}
function labDraw(){const c=$("lab-canvas");if(!c)return;computeLabDuration();const x=c.getContext("2d"),W=c.width,H=c.height;
 x.clearRect(0,0,W,H);x.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue("--line");for(let gx=0;gx<=LAB.w;gx+=2){const[a]=labXY(gx,0,W,H);x.beginPath();x.moveTo(a,0);x.lineTo(a,H);x.stroke();}
 for(let gy=0;gy<=LAB.h;gy+=2){const[,b]=labXY(0,gy,W,H);x.beginPath();x.moveTo(0,b);x.lineTo(W,b);x.stroke();}
 const _labLabels=[];
 for(const o of state.lab.objects){const col=COL[o.category]||"#fff",sel=o.id===state.lab.selected;
  if(o.waypoints.length>1){x.strokeStyle=col+(sel?"":"88");x.lineWidth=sel?2.5:1.5;x.beginPath();
   o.waypoints.forEach((w,i)=>{const[a,b]=labXY(w[0],w[1],W,H);i?x.lineTo(a,b):x.moveTo(a,b);});x.stroke();x.lineWidth=1;}
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
 el.style.color=os.length>=2&&moving?"var(--teal)":"var(--amber)";}
document.addEventListener("keydown",e=>{if((e.key==="Delete"||e.key==="Backspace")&&$("view-create").classList.contains("on")
 &&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)){const o=labObj(state.lab.selected);
 if(o&&o.waypoints.length){o.waypoints.pop();labRenderList();labDraw();}}});
function labRenderList(){const el=$("lab-list");if(!el)return;labReady();
 el.innerHTML=state.lab.objects.length?state.lab.objects.map(o=>`<div class="labobj ${o.id===state.lab.selected?"sel":""}" data-id="${o.id}">
  <b style="color:${COL[o.category]||"#fff"}">●</b> <b>${o.id}</b> <span class="dim">${o.waypoints.length} waypoint(s) · ${pathLen(o).toFixed(1)} m${o.speed?` · ${(pathDur(o)).toFixed(1)}s`:""}</span>
  <div class="row labctl">
   <label>Speed m/s<input type="number" step="0.1" min="0" max="8" value="${o.speed}" data-f="speed"></label>
   <label>Radius m<input type="number" step="0.1" min="0.1" max="3" value="${o.radius}" data-f="radius"></label>
   <label>Delay s<input type="number" step="0.25" min="0" max="10" value="${o.delay}" data-f="delay"></label>
   <label>Path mode<select data-f="mode"><option ${o.mode==="stop"?"selected":""}>stop</option><option ${o.mode==="loop"?"selected":""}>loop</option><option ${o.mode==="pingpong"?"selected":""}>pingpong</option></select></label>
  </div>
  <div class="row"><button data-act="select">${o.id===state.lab.selected?"Selected ✓":"Select & edit path"}</button>
   <button class="ghostbtn" data-act="undo">Undo point</button>
   <button class="ghostbtn" data-act="clear">Clear path</button>
   <button class="ghostbtn" data-act="dup">Duplicate</button>
   <button class="ghostbtn" data-act="del">Delete</button></div></div>`).join("")
  :'<p class="dim">No components yet. Add one, select it, then click the stage to lay its path.</p>';
 el.querySelectorAll(".labobj").forEach(card=>{const o=labObj(card.dataset.id);
  card.querySelectorAll("input,select").forEach(inp=>inp.onchange=()=>{o[inp.dataset.f]=inp.dataset.f==="mode"?inp.value:Math.max(0,+inp.value||0);labRenderList();labDraw();});
  card.querySelectorAll("button").forEach(b=>b.onclick=()=>{const a=b.dataset.act;
   if(a==="select"){state.lab.selected=o.id;}
   if(a==="undo"){o.waypoints.pop();}
   if(a==="clear"){o.waypoints=[];}
   if(a==="dup"){const c=labAdd(o.category,o.waypoints.map(w=>[w[0]+0.5,w[1]+0.5]),o.speed,o.radius,o.delay,o.mode);labStatus(c.id+" duplicated — drag its waypoints apart.");}
   if(a==="del"){state.lab.objects=state.lab.objects.filter(q=>q.id!==o.id);if(state.lab.selected===o.id)state.lab.selected=null;}
   labRenderList();labDraw();});});}
// canvas editing: click adds a waypoint to the selected component; drag moves one
(()=>{const c=$("lab-canvas");if(!c)return;let drag=null,moved=false;
 const evPos=e=>{const r=c.getBoundingClientRect();return [(e.clientX-r.left)*c.width/r.width,(e.clientY-r.top)*c.height/r.height];};
 c.addEventListener("pointerdown",e=>{try{c.setPointerCapture(e.pointerId);}catch(_){} const[px,py]=evPos(e);moved=false;c._suppressAdd=false;
  // click any component's live marker to select it (drawn footprint, min 14px)
  for(const o of state.lab.objects){const pos=posOnPath(o,state.lab.t);if(!pos)continue;
   const[a,b]=labXY(pos[0],pos[1],c.width,c.height);const r=Math.max(14,o.radius/LAB.w*c.width);
   if(Math.hypot(a-px,b-py)<r){if(state.lab.selected!==o.id){state.lab.selected=o.id;labRenderList();labDraw();}c._suppressAdd=true;break;}}
  const o=labObj(state.lab.selected);if(!o)return;
  o.waypoints.forEach((w,i)=>{const[a,b]=labXY(w[0],w[1],c.width,c.height);if(Math.hypot(a-px,b-py)<12)drag={o,i};});});
 c.addEventListener("dblclick",e=>{const[px,py]=evPos(e);const o=labObj(state.lab.selected);if(!o)return;
  let best=-1,bd=14;o.waypoints.forEach((w,i)=>{const[a,b]=labXY(w[0],w[1],c.width,c.height);const d=Math.hypot(a-px,b-py);if(d<bd){bd=d;best=i;}});
  if(best>=0){o.waypoints.splice(best,1);labRenderList();labDraw();labStatus(`Waypoint ${best+1} removed from ${o.id}.`);}});
 c.addEventListener("pointermove",e=>{if(!drag)return;moved=true;const[px,py]=evPos(e);
  drag.o.waypoints[drag.i]=labInv(px,py,c.width,c.height);labDraw();});
 c.addEventListener("pointercancel",()=>{drag=null;});
 c.addEventListener("pointerup",e=>{const wasDrag=!!drag;if(drag&&moved){drag=null;labRenderList();labDraw();return;}drag=null;
  if(wasDrag){labRenderList();labDraw();return;}
  if(c._suppressAdd){c._suppressAdd=false;return;}
  const o=labObj(state.lab.selected);if(!o){labStatus("Add and select a component first.");return;}
  const[px,py]=evPos(e);o.waypoints.push(labInv(px,py,c.width,c.height));labRenderList();labDraw();});})();
$("lab-add").onclick=()=>{const cat=$("lab-new-cat").value;const o=labAdd(cat);
 labStatus(`${o.id} added and selected — click the stage to lay its path (shelf = static, one point is enough).`);};
document.querySelectorAll("[data-tpl]").forEach(b=>b.onclick=()=>{state.lab.objects=[];state.lab.selected=null;state.lab.nextId={};
 if(b.dataset.tpl==="near-miss"){labAdd("forklift",[[1,7],[7.5,7],[13,7]],1.6,0.9,0);labAdd("pedestrian",[[8.6,13],[8.6,6],[8.6,1]],1.55,0.45,0);}
 if(b.dataset.tpl==="crossing"){labAdd("vehicle",[[0.5,7],[8,7],[15,7]],2.4,1.1,0);labAdd("cyclist",[[9,13.5],[9,7],[9,1]],1.9,0.5,0.5);labAdd("pedestrian",[[14,2],[8,6.2],[3,11]],1.3,0.45,1);}
 if(b.dataset.tpl==="cell"){labAdd("robot",[[2,2],[13,2],[13,11],[2,11],[2,2]],1.2,0.55,0);labAdd("forklift",[[1,12],[14,12]],0.9,0.9,1);labAdd("shelf",[[8,7]],0,1.4,0);labAdd("pedestrian",[[15,1],[10,6],[15,12]],1.1,0.45,2);}
 labStatus(`Template "${b.dataset.tpl}" loaded — edit any path, then Run analysis.`);labDraw();});
$("lab-play").onclick=()=>{state.lab.playing=!state.lab.playing;$("lab-play").textContent=state.lab.playing?"⏸ Pause preview":"▶ Preview motion";
 if(state.lab.playing){const step=()=>{if(!state.lab.playing)return;state.lab.t+=0.05;if(state.lab.t>labDuration())state.lab.t=0;labDraw();requestAnimationFrame(step);};step();}};
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
 state.data=r.scenario;state.scenario=r.scenario.id;state.run=r.run;state.t=0;
 try{const mine=JSON.parse(localStorage.getItem("fs-my-scenes")||"[]");mine.push({id:r.scenario.id,when:Date.now(),tracks});localStorage.setItem("fs-my-scenes",JSON.stringify(mine.slice(-10)));}catch(e){}
 renderObjects();draw();renderTrace(r.run);renderInspector(r);goto("studio");
 $("analyze-status").textContent=`Custom run ${r.run.run_id} · ${r.run.mode} · ${r.scenario.tracks.length} objects · ${r.run.findings.pairs.length} pairs analysed`;
 const evs=[];(r.run.findings.pairs||[]).forEach(p=>{if(p.event)evs.push({...p.event,pair:p.pair});});
 $("events").innerHTML=evs.length?evs.map(e=>`<li class="ev" data-t="${e.at_time_s||e.t_star_s||0}">⚠ <b>${e.type}</b> ${e.pair.join(" ↔ ")}<br><span class="dim">${e.ttc_s!=null?"TTC "+e.ttc_s+"s":e.d_min!=null?"d_min "+e.d_min+" "+(e.units||""):""}</span></li>`).join(""):'<li class="dim">No proximity events above threshold.</li>';
 document.querySelectorAll(".ev").forEach(el=>el.onclick=()=>{state.t=+el.dataset.t;draw();});
 window.scrollTo({top:0,behavior:"smooth"});
 return r;}
$("lab-run").onclick=async()=>{let tracks;try{tracks=labSampleTracks();}catch(e){labStatus(e.message);return;}
 const btn=$("lab-run"),old=btn.textContent,t0=Date.now();btn.disabled=true;btn.textContent="Analysing… 0s";
 labStatus("Running: deterministic engine + Muse Spark hypothesis (typically 5–25s). Do not press again.");
 const timer=setInterval(()=>{btn.textContent=`Analysing… ${Math.round((Date.now()-t0)/1000)}s`;},500);
 try{await analyzeCustom(tracks,"created-"+Date.now());labStatus("Analysis complete — showing Studio. Events are in the right-hand list; click one to seek.");}
 catch(e){/* analyzeCustom already surfaced the error */}
 finally{clearInterval(timer);btn.disabled=false;btn.textContent=old;}};
$("lab-export").onclick=()=>{download(new Blob([JSON.stringify({kind:"frontiersight-created-scene",stage_metres:[LAB.w,LAB.h],objects:state.lab.objects},null,2)],{type:"application/json"}),"frontiersight-scene.json");};
$("lab-import").onchange=e=>{const f=e.target.files[0];if(!f)return;f.text().then(txt=>{try{
 const d=JSON.parse(txt);const objs=d.objects||d;if(!Array.isArray(objs))throw new Error("expected {objects:[...]} ");
 state.lab.objects=[];state.lab.nextId={};objs.forEach(o=>labAdd(o.category||"object",(o.waypoints||o.points||[]).map(p=>[+p[0],+p[1]]),+o.speed||0,+o.radius||0.5,+o.delay||0,o.mode||"stop"));
 labStatus(`Imported ${state.lab.objects.length} component(s).`);labDraw();}catch(err){labStatus("Import failed: "+err.message);}});};
function labLoadScene(scene,label){state.lab.objects=[];state.lab.selected=null;state.lab.nextId={};state.lab.t=0;
 (scene.objects||[]).forEach(o=>labAdd(o.category,(o.waypoints||[]).map(w=>[+w[0],+w[1]]),+o.speed||0,+o.radius||0.5,+o.delay||0,o.mode||"stop"));
 labStatus(label);labDraw();}
document.querySelectorAll(".lab-chip").forEach(b=>b.onclick=()=>{$("lab-prompt").value=b.textContent;$("lab-generate").click();});
$("lab-generate").onclick=async()=>{const desc=$("lab-prompt").value.trim();
 if(desc.length<8){$("lab-gen-status").textContent="Describe the scene in a sentence or two first.";return;}
 $("lab-gen-status").textContent="Asking Muse Spark to design the scene…";
 let r;try{r=await(await fetch("/api/meta/scene",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt:desc})})).json();}
 catch(e){$("lab-gen-status").textContent="Generation failed: API unreachable.";return;}
 if(r.status==="BLOCKED_CREDENTIALS"){$("lab-gen-status").textContent=r.detail;return;}
 if(r.error||r.status==="MODEL_ERROR"){$("lab-gen-status").textContent="Muse could not produce a valid scene: "+(r.error||r.detail)+" — try a clearer description.";return;}
 labLoadScene(r.scene,`Generated "${r.scene.name}" — edit any waypoint, then Run analysis.`); obDone("muse"); toast("Scene generated by Muse Spark — edit any waypoint, then Run analysis.");
 $("lab-gen-status").innerHTML=`Source: <b>${r.source==="MODEL_DERIVED"?"MODEL_DERIVED · Muse Spark "+(r.model_call?`(${r.model_call.model}, ${r.model_call.latency_ms} ms)`:""):"OFFLINE_HEURISTIC (no model call)"}</b><br>${r.scene.explanation||""}`;};
// starter template so the Lab is never an empty, unexplained canvas
if(!state.lab.objects.length){$("lab-add")&&document.querySelector('[data-tpl="near-miss"]').click();}

// ---- theme: light / dark / system (persisted, OS-aware, pre-paint handled in <head>) ----
const _mq=matchMedia("(prefers-color-scheme: light)");
function applyTheme(){const mode=localStorage.getItem("fs-theme")||"system";
 const resolved=mode==="system"?(_mq.matches?"light":"dark"):mode;
 document.documentElement.dataset.theme=resolved;
 document.querySelectorAll("[data-theme-mode]").forEach(b=>b.classList.toggle("on",b.dataset.themeMode===mode));
 if(state&&state.data)draw(); if(state&&state.lab&&state.lab.objects.length&&$("lab-canvas"))labDraw();}
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
$("sam-file").onchange=e=>{const f=e.target.files[0];if(!f)return;
 if(f.size>60*1024*1024){samStatus("File exceeds the 60 MB browser-preview bound.");e.target.value="";return;}
 const url=URL.createObjectURL(f),v=$("sam-video"),im=$("sam-img");
 if(f.type.startsWith("video/")){im.style.display="none";v.style.display="block";v.src=url;samStatus("Video loaded locally — pause on a moment, then Segment. Loading it uploads nothing.");}
 else if(f.type.startsWith("image/")){v.style.display="none";im.style.display="block";im.src=url;samStatus("Image loaded locally. Segment it with SAM 3.1.");}
 else samStatus("Unsupported type — use a video or image, or build the scene in Create Lab.");};
function samFrame(){const v=$("sam-video"),im=$("sam-img");
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

// ---- playback speed ----
$("play").onclick=()=>{state.playing=!state.playing;$("play").textContent=state.playing?"⏸ Pause":"▶ Play";
 if(state.playing){const step=()=>{if(!state.playing)return;state.t+=0.05*(+$("play-speed").value||1);if(state.t>8)state.t=0;draw();requestAnimationFrame(step);};step();}};

// ---- counterfactual export ----
$("cf-export").onclick=()=>{if(!state.cfData){$("cf-results").textContent="Run a simulation first, then export.";return;}
 download(new Blob([JSON.stringify(state.cfData,null,2)],{type:"application/json"}),"frontiersight-counterfactual.json");
 toast("Counterfactual result exported (JSON).");};

// ---- workspace search + live counts ----
$("ws-search").oninput=e=>{const q=e.target.value.toLowerCase();
 document.querySelectorAll(".scenario-card").forEach(c=>{c.style.display=c.dataset.search.includes(q)?"":"none";});};

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
