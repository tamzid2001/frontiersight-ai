const $=id=>document.getElementById(id);
const state={scenario:null,data:null,t:0,playing:false,run:null,cf:null};
const COL={forklift:"#38c6d9",pedestrian:"#f2b04a",robot:"#2dd4a8"};

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

const WORLD={x:15,y:14};
function px(x,y,W,H){return [x/WORLD.x*W, H-(y/WORLD.y*H)];}
function posAt(track,t){const p=track.points;if(t<=p[0][0])return p[0];if(t>=p[p.length-1][0])return p[p.length-1];
 for(let i=1;i<p.length;i++){if(p[i][0]>=t){const[t0,a]=[p[i-1][0],p[i-1]],[t1,b]=[p[i][0],p[i]];const k=(t-t0)/(t1-t0||1);return[0,a[1]+(b[1]-a[1])*k,a[2]+(b[2]-a[2])*k];}}return p[p.length-1];}
function draw(){const c=$("stage");if(!c||!state.data)return;const x=c.getContext("2d"),W=c.width,H=c.height;
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

async function runCf(){const r=await(await fetch("/api/counterfactual",{method:"POST",headers:{"Content-Type":"application/json"},
 body:JSON.stringify({scenario:state.scenario,speed_reduction_pct:+$("sr").value,intervention_t:+$("it").value})})).json();
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
