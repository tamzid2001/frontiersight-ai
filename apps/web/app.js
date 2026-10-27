const $=id=>document.getElementById(id);
const state={scenario:null,data:null,t:0,playing:false,run:null,cf:null};
const COL={forklift:"#38c6d9",pedestrian:"#f2b04a",robot:"#2dd4a8",vehicle:"#4dc9ff",cyclist:"#c792ff",shelf:"#5b6b9f",person:"#f2b04a",object:"#e8edf6"};

// tabs
document.querySelectorAll("#tabs button").forEach(b=>b.onclick=()=>{
 document.querySelectorAll("#tabs button").forEach(x=>x.classList.toggle("on",x===b));
 document.querySelectorAll(".view").forEach(v=>v.classList.toggle("on",v.id==="view-"+b.dataset.view));});
function goto(v){document.querySelector(`#tabs button[data-view="${v}"]`).click();}

async function diag(){try{const d=await(await fetch("/api/diagnostics")).json();
 $("mode").textContent=d.meta_configured?"● LIVE META":"● FIXTURE REPLAY";
 $("mode").className="pill "+(d.meta_configured?"ok":"warn");
 $("hero-diag").textContent=`Meta: ${d.meta_configured?"configured":"not configured"} · Spark ${d.spark_model} · SAM ${d.sam_model} · mode ${d.mode}`;
 $("diag").textContent=JSON.stringify(d,null,2);}catch(e){$("mode").textContent="● API OFFLINE";}}

async function loadScenarios(){let d;try{d=await(await fetch("/api/scenarios")).json();}
 catch(e){$("scenario-list").innerHTML='<div class="card wide"><h3>Could not load scenarios</h3><p class="dim">The API is unreachable. Check <code>/api/health</code>, then reload. Nothing has been simulated or hidden.</p><button onclick="location.reload()">Reload</button></div>';return;}
 $("scenario-select").innerHTML=d.scenarios.map(s=>`<option value="${s.id}">${s.id}</option>`).join("");
 $("scenario-list").innerHTML=d.scenarios.map(s=>`<div class="card"><h3>${s.id}</h3><p class="dim">${s.description}</p><button onclick="pick('${s.id}')">Open in Studio →</button></div>`).join("");
 const v=await(await fetch("/api/validate")).json();
 $("validation-list").innerHTML=v.cases.map(c=>`<li>${c.passed?"✓":"✗"} <b>${c.case}</b> — <span class="dim">${c.detail}</span></li>`).join("");
 await pick(d.scenarios[0].id);}
window.pick=async id=>{state.data=await(await fetch("/api/scenarios?name="+id)).json();state.scenario=id;state.t=0;
 $("scenario-select").value=id;renderObjects();draw();goto("studio");};
$("scenario-select").onchange=e=>pick(e.target.value);

function renderObjects(){if(!state.data)return;
 $("objects").innerHTML=state.data.tracks.map(t=>`<li><b style="color:${COL[t.category]||"#fff"}">●</b> ${t.object_id} · ${t.category} · <span class="dim">${t.source}, ${t.points.length} obs${t.occluded.length?", occluded "+t.occluded.map(o=>o.join("–")+"s").join(","):""}</span></li>`).join("");}

let WORLD={x:15,y:14};
function computeWorld(){if(!state.data)return WORLD;let mx=1,my=1;
 state.data.tracks.forEach(t=>t.points.forEach(p=>{mx=Math.max(mx,p[1]);my=Math.max(my,p[2]);}));
 WORLD={x:mx*1.12,y:my*1.12};return WORLD;}
function px(x,y,W,H){return [x/WORLD.x*W, H-(y/WORLD.y*H)];}
function posAt(track,t){const p=track.points;if(t<=p[0][0])return p[0];if(t>=p[p.length-1][0])return p[p.length-1];
 for(let i=1;i<p.length;i++){if(p[i][0]>=t){const[t0,a]=[p[i-1][0],p[i-1]],[t1,b]=[p[i][0],p[i]];const k=(t-t0)/(t1-t0||1);return[0,a[1]+(b[1]-a[1])*k,a[2]+(b[2]-a[2])*k];}}return p[p.length-1];}
function draw(){const c=$("stage");if(!c||!state.data)return;computeWorld();const x=c.getContext("2d"),W=c.width,H=c.height;
 x.clearRect(0,0,W,H);x.strokeStyle="#1b2434";for(let gx=0;gx<=WORLD.x;gx+=2){const[a]=px(gx,0,W,H);x.beginPath();x.moveTo(a,0);x.lineTo(a,H);x.stroke();}
 for(const tr of state.data.tracks){const col=COL[tr.category]||"#fff";
  x.strokeStyle=col+"55";x.beginPath();tr.points.forEach(p=>{const[a,b]=px(p[1],p[2],W,H);p===tr.points[0]?x.moveTo(a,b):x.lineTo(a,b);});x.stroke();
  const occ=tr.occluded.some(o=>state.t>=o[0]&&state.t<=o[1]);
  const cur=posAt(tr,state.t);const[a,b]=px(cur[1],cur[2],W,H);const r=tr.radius/WORLD.x*W;
  x.strokeStyle=occ?"#f26d7d":col;x.lineWidth=occ?3:2;x.setLineDash(occ?[5,4]:[]);x.beginPath();x.arc(a,b,r,0,7);x.stroke();x.setLineDash([]);x.lineWidth=1;
  x.fillStyle="#e8edf6";x.font="13px system-ui";x.fillText(`${tr.object_id}${occ?" · OCCLUDED":""}`,a+r+6,b-6);}
 $("clock").textContent="t = "+state.t.toFixed(2)+"s";$("scrub").value=state.t;}
$("scrub").oninput=e=>{state.t=+e.target.value;draw();};
$("play").onclick=()=>{state.playing=!state.playing;$("play").textContent=state.playing?"⏸ Pause":"▶ Play";
 if(state.playing){const step=()=>{if(!state.playing)return;state.t+=0.05;if(state.t>8)state.t=0;draw();requestAnimationFrame(step);};step();}};

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
 renderTrace(r.run);renderInspector(r);drawCfFromRun(r.run);};
function renderTrace(run){$("trace").innerHTML=run.stages.map(s=>`<li class="${s.status}"><b>${s.name}</b> · ${s.status} · <span class="dim">${s.attribution}${s.artifact?" · artifact "+s.artifact:""}${s.retries?" · retries "+s.retries:""}</span><br><span class="dim mono">${JSON.stringify(s.detail).slice(0,320)}</span></li>`).join("");}
function renderInspector(r){const sc=r.scenario;$("inspector-body").innerHTML=
 `<p><b>Coordinate frame:</b> ${sc.calibration.frame} · <b>Scale:</b> ${sc.calibration.metres_per_pixel} m/px (declared, synthetic) · <b>Units:</b> metres (calibrated) · <b>Space:</b> world</p>`+
 sc.tracks.map(t=>`<p><b>${t.object_id}</b> (${t.category}) — ${t.points.length} observations, radius ${t.radius} m, source <code>${t.source}</code>${t.occluded.length?`, occluded ${t.occluded.map(o=>o.join("–"))}s (missing evidence, not numerical uncertainty)`:""}</p>`).join("")+
 `<p class="dim">Assumption register: constant-velocity extrapolation for CPA/TTC; finite-difference velocities; smoothing (if applied) biases peaks downward and never overwrites ground truth, which is held separately in the evidence packet.</p>`;}

async function runCf(){const custom=state.data&&state.data.kind==="USER_UPLOADED";
 const r=await(await fetch(custom?"/api/counterfactual-custom":"/api/counterfactual",{method:"POST",headers:{"Content-Type":"application/json"},
 body:JSON.stringify(custom?{tracks:state.data.tracks,agent_id:state.data.tracks[0].object_id,speed_reduction_pct:+$("sr").value,intervention_t:+$("it").value}
  :{scenario:state.scenario,speed_reduction_pct:+$("sr").value,intervention_t:+$("it").value})})).json();
 if(r.error){$("cf-results").textContent="Simulation failed: "+r.error;return;}
 if(custom){$("cf-results").innerHTML=`agent <b>${state.data.tracks[0].object_id}</b> vs ${Object.keys(r.per_actor).length} other actor(s)<br>worst original d_min <b>${r.worst_original_d_min}</b> → counterfactual <b>${r.worst_counterfactual_d_min}</b> (Δ ${r.delta_worst_d_min>=0?"+":""}${r.delta_worst_d_min})<br>`+
  Object.entries(r.per_actor).map(([k,v])=>`${k}: ${v.original_d_min} → ${v.counterfactual_d_min}`).join("<br>");
  state.cf={trajectories:r.trajectories,original:{d_min:r.worst_original_d_min},counterfactual:{d_min:r.worst_counterfactual_d_min},delta_d_min:r.delta_worst_d_min,monte_carlo:null,manifest_hash:"custom"};drawCf(state.cf);return;}
 state.cf=r;drawCf(r);
 $("cf-results").innerHTML=`original d_min <b>${r.original.d_min} m</b> (contact: ${r.original.contact})<br>counterfactual d_min <b>${r.counterfactual.d_min} m</b> (contact: ${r.counterfactual.contact})<br>Δ d_min <b>${r.delta_d_min>=0?"+":""}${r.delta_d_min} m</b><br>Monte Carlo d_min p05/p50/p95: ${r.monte_carlo?`${r.monte_carlo.d_min_p05} / ${r.monte_carlo.d_min_p50} / ${r.monte_carlo.d_min_p95} (${r.monte_carlo.runs} runs, seed ${r.monte_carlo.seed})`:"—"}<br>manifest ${r.manifest_hash.slice(0,16)}…`;
}
function drawCfFromRun(run){const s=run.findings.simulation_summary;if(s&&state.cf)drawCf(state.cf);}
function drawCf(r){const c=$("cf-chart"),x=c.getContext("2d"),W=c.width,H=c.height;x.clearRect(0,0,W,H);
 const series=(traj,key)=>traj.map(p=>p[key]);const all=[...series(r.trajectories.original,5),...series(r.trajectories.counterfactual,5)];
 const mx=Math.max(...all)*1.15||1;x.strokeStyle="#232b3a";x.beginPath();x.moveTo(44,10);x.lineTo(44,H-30);x.lineTo(W-10,H-30);x.stroke();
 const plot=(traj,col)=>{x.strokeStyle=col;x.lineWidth=2;x.beginPath();traj.forEach((p,i)=>{const X=44+p[0]/6*(W-60),Y=H-30-p[5]/mx*(H-50);i?x.lineTo(X,Y):x.moveTo(X,Y);});x.stroke();x.lineWidth=1;};
 plot(r.trajectories.original,"#8fa0b8");plot(r.trajectories.counterfactual,"#2dd4a8");
 x.fillStyle="#e8edf6";x.font="13px system-ui";x.fillText("— original",52,24);x.fillStyle="#2dd4a8";x.fillText("— counterfactual",150,24);
 x.fillStyle="#8fa0b8";x.fillText("time → 6s",W-90,H-8);x.fillText("distance (m)",6,20);}
let deb;$("sr").oninput=e=>{$("sr-val").textContent=e.target.value+"%";clearTimeout(deb);deb=setTimeout(runCf,350);};
$("it").oninput=e=>{$("it-val").textContent=(+e.target.value).toFixed(2)+"s";clearTimeout(deb);deb=setTimeout(runCf,350);};
$("cf-run").onclick=runCf;

$("export-json").onclick=async()=>{const name=state.scenario||"warehouse-near-miss";
 const rep=await(await fetch("/api/report?name="+name)).json();if(state.run)rep.run=state.run;
 download(new Blob([JSON.stringify(rep,null,2)],{type:"application/json"}),`frontiersight-${name}-evidence.json`);};
$("export-html").onclick=async()=>{const name=state.scenario||"warehouse-near-miss";
 const rep=await(await fetch("/api/report?name="+name)).json();if(state.run)rep.run=state.run;
 $("evidence-preview").textContent=JSON.stringify(rep,null,2).slice(0,2600);
 download(new Blob([`<!doctype html><title>FrontierSight evidence — ${name}</title><h1>FrontierSight AI evidence report</h1><p>${rep.disclaimer}</p><pre>${JSON.stringify(rep,null,2).replace(/</g,"&lt;")}</pre>`],{type:"text/html"}),`frontiersight-${name}-report.html`);};
function download(blob,name){const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=name;a.click();}
$("cta-demo").onclick=()=>{goto("studio");$("analyze").click();};
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
function labAdd(cat,waypoints,speed,radius,delay,mode){
 const o={id:labId(cat),category:cat,radius:radius??(cat==="shelf"?1.1:cat==="forklift"||cat==="vehicle"?0.9:0.5),
  speed:speed??(cat==="shelf"?0:1.4),delay:delay??0,mode:mode||"stop",waypoints:waypoints||[]};
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
 x.clearRect(0,0,W,H);x.strokeStyle="#1b2434";for(let gx=0;gx<=LAB.w;gx+=2){const[a]=labXY(gx,0,W,H);x.beginPath();x.moveTo(a,0);x.lineTo(a,H);x.stroke();}
 for(let gy=0;gy<=LAB.h;gy+=2){const[,b]=labXY(0,gy,W,H);x.beginPath();x.moveTo(0,b);x.lineTo(W,b);x.stroke();}
 for(const o of state.lab.objects){const col=COL[o.category]||"#fff",sel=o.id===state.lab.selected;
  if(o.waypoints.length>1){x.strokeStyle=col+(sel?"":"88");x.lineWidth=sel?2.5:1.5;x.beginPath();
   o.waypoints.forEach((w,i)=>{const[a,b]=labXY(w[0],w[1],W,H);i?x.lineTo(a,b):x.moveTo(a,b);});x.stroke();x.lineWidth=1;}
  o.waypoints.forEach((w,i)=>{const[a,b]=labXY(w[0],w[1],W,H);x.fillStyle=sel?col:"#41506e";
   x.beginPath();x.arc(a,b,sel?6:4.5,0,7);x.fill();x.fillStyle="#dfe7f5";x.font="10px system-ui";x.fillText(String(i+1),a-3,b+3);});
  const pos=posOnPath(o,state.lab.t);if(pos){const[a,b]=labXY(pos[0],pos[1],W,H);const r=o.radius/LAB.w*W;
   x.strokeStyle=col;x.lineWidth=2.5;x.beginPath();x.arc(a,b,r,0,7);x.stroke();
   x.fillStyle=col+"2e";x.beginPath();x.arc(a,b,r,0,7);x.fill();
   x.fillStyle="#e8edf6";x.font="12.5px system-ui";x.fillText(`${o.id}${o.speed?` · ${o.speed} m/s`:" · static"}`,a+r+5,b-5);}}
 const live=$("lab-live");if(live){let best=null;
  const placed=state.lab.objects.map(o=>({o,p:posOnPath(o,state.lab.t)})).filter(q=>q.p);
  for(let i=0;i<placed.length;i++)for(let k=i+1;k<placed.length;k++){
   const d=Math.hypot(placed[i].p[0]-placed[k].p[0],placed[i].p[1]-placed[k].p[1])-placed[i].o.radius-placed[k].o.radius;
   if(!best||d<best.d)best={d,a:placed[i].o.id,b:placed[k].o.id};}
  live.textContent=best?`Closest pair at preview: ${best.a} ↔ ${best.b} — surface gap ${best.d.toFixed(2)} m ${best.d<0.5?"⚠ proximity":best.d<0?"⚠ OVERLAP":""}`:"Closest pair: —";
  live.style.color=best&&best.d<0.5?"var(--amber)":"";}
 const clk=$("lab-clock");if(clk)clk.textContent="t = "+state.lab.t.toFixed(2)+"s";const sc=$("lab-scrub");if(sc)sc.value=state.lab.t;}
function computeLabDuration(){const sc=$("lab-scrub");if(sc)sc.max=labDuration();}
function labRenderList(){const el=$("lab-list");if(!el)return;
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
 c.addEventListener("pointerdown",e=>{const[px,py]=evPos(e);moved=false;
  const o=labObj(state.lab.selected);if(!o)return;
  o.waypoints.forEach((w,i)=>{const[a,b]=labXY(w[0],w[1],c.width,c.height);if(Math.hypot(a-px,b-py)<12)drag={o,i};});});
 c.addEventListener("pointermove",e=>{if(!drag)return;moved=true;const[px,py]=evPos(e);
  drag.o.waypoints[drag.i]=labInv(px,py,c.width,c.height);labDraw();});
 c.addEventListener("pointerup",e=>{if(drag&&moved){drag=null;labRenderList();labDraw();return;}drag=null;
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
  const pts=[];for(let t=0;t<=T+1e-9;t=Math.round((t+dt)*100)/100){const p=posOnPath(o,t);pts.push([t,p[0],p[1]]);}
  tracks.push({object_id:o.id,category:o.category,space:"world",radius:o.radius,source:"USER_CREATED",points:pts});}
 if(tracks.length<2)throw new Error("Create at least two components to analyse interactions.");
 return tracks;}
async function analyzeCustom(tracks,label){labStatus("Analysing "+label+"…");$("analyze-status").textContent="Running custom analysis…";
 const r=await(await fetch("/api/analyze-custom",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({id:label||"created-scene",tracks,metres_per_pixel:null,
   speed_reduction_pct:+$("sr").value,intervention_t:+$("it").value,human_approved:$("approve").checked})})).json();
 if(r.error){labStatus("Analysis failed: "+r.error);$("analyze-status").textContent="Custom analysis failed: "+r.error;return;}
 state.data=r.scenario;state.scenario=r.scenario.id;state.run=r.run;state.t=0;
 try{const mine=JSON.parse(localStorage.getItem("fs-my-scenes")||"[]");mine.push({id:r.scenario.id,when:Date.now(),tracks});localStorage.setItem("fs-my-scenes",JSON.stringify(mine.slice(-10)));}catch(e){}
 renderObjects();draw();renderTrace(r.run);renderInspector(r);goto("studio");
 $("analyze-status").textContent=`Custom run ${r.run.run_id} · ${r.run.mode} · ${r.scenario.tracks.length} objects · ${r.run.findings.pairs.length} pairs analysed`;
 const evs=[];(r.run.findings.pairs||[]).forEach(p=>{if(p.event)evs.push({...p.event,pair:p.pair});});
 $("events").innerHTML=evs.length?evs.map(e=>`<li class="ev" data-t="${e.at_time_s||e.t_star_s||0}">⚠ <b>${e.type}</b> ${e.pair.join(" ↔ ")}<br><span class="dim">${e.ttc_s!=null?"TTC "+e.ttc_s+"s":e.d_min!=null?"d_min "+e.d_min+" "+(e.units||""):""}</span></li>`).join(""):'<li class="dim">No proximity events above threshold.</li>';
 document.querySelectorAll(".ev").forEach(el=>el.onclick=()=>{state.t=+el.dataset.t;draw();});}
$("lab-run").onclick=()=>{try{analyzeCustom(labSampleTracks(),"created-"+Date.now());}catch(e){labStatus(e.message);}};
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
 labLoadScene(r.scene,`Generated "${r.scene.name}" — edit any waypoint, then Run analysis.`);
 $("lab-gen-status").innerHTML=`Source: <b>${r.source==="MODEL_DERIVED"?"MODEL_DERIVED · Muse Spark "+(r.model_call?`(${r.model_call.model}, ${r.model_call.latency_ms} ms)`:""):"OFFLINE_HEURISTIC (no model call)"}</b><br>${r.scene.explanation||""}`;};
// starter template so the Lab is never an empty, unexplained canvas
if(!state.lab.objects.length){$("lab-add")&&document.querySelector('[data-tpl="near-miss"]').click();}
