"use strict";
const report = JSON.parse(document.getElementById("report-data").textContent);
const el = (id) => document.getElementById(id);
const names = Object.keys(report.summary);
const money = (n) => n === null || n === undefined ? "Unavailable" : new Intl.NumberFormat("en-US",{style:"currency",currency:"USD"}).format(n);
const text = (tag, value, parent, cls) => {const n=document.createElement(tag); n.textContent=String(value); if(cls)n.className=cls; if(parent)parent.append(n); return n;};
const option = (value,label,parent) => {const n=text("option",label,parent);n.value=value;};
let cursor=0, timer=null;
const position = () => report.positions[Number(el("position").value)];
const arm = () => position().variants[el("variant").value];
function pause(){if(timer!==null)clearTimeout(timer);timer=null;el("play").textContent="Play";}
function svgNode(tag,attrs,parent){const n=document.createElementNS("http://www.w3.org/2000/svg",tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(parent)parent.append(n);return n;}
function plot(target, series, {baseline=null, title="", dollars=false}={}){
  target.replaceChildren();
  if(!series.length){text("p","No usable marks to plot.",target);return;}
  series=series.map(s=>({...s,points:s.points.length<=1000?s.points:Array.from({length:1000},(_,i)=>s.points[Math.round(i*(s.points.length-1)/999)])}));
  const points=series.flatMap(s=>s.points);
  let min=Math.min(...points.map(p=>p.y),baseline===null?Infinity:baseline),max=Math.max(...points.map(p=>p.y),baseline===null?-Infinity:baseline);
  const pad=Math.max(.05,(max-min)*.12);min-=pad;max+=pad;
  const xmin=Math.min(...points.map(p=>p.x)),xmax=Math.max(xmin+1,...points.map(p=>p.x));
  const x=(v)=>72+(v-xmin)/(xmax-xmin)*940,y=(v)=>220-(v-min)/(max-min)*175;
  const svg=svgNode("svg",{viewBox:"0 0 1080 280",role:"img","aria-label":title},target);
  svgNode("title",{},svg).textContent=title;
  for(let i=0;i<5;i++){const value=min+(max-min)*i/4;svgNode("line",{x1:72,x2:1012,y1:y(value),y2:y(value),stroke:"#243845"},svg);const t=svgNode("text",{x:8,y:y(value)+4},svg);t.textContent=dollars?money(value):value.toFixed(2);}
  if(baseline!==null){svgNode("line",{x1:72,x2:1012,y1:y(baseline),y2:y(baseline),stroke:"#ffcd87","stroke-dasharray":"6 6"},svg);svgNode("text",{x:76,y:26},svg).textContent=dollars ? "Zero realized P&L" : "Entry ask "+baseline.toFixed(2);}
  for(const s of series){svgNode("polyline",{points:s.points.map(p=>x(p.x)+","+y(p.y)).join(" "),fill:"none",stroke:s.color,"stroke-width":3},svg);
    for(const p of (s.points.length<=200?s.points:[])){const dot=svgNode("circle",{cx:x(p.x),cy:y(p.y),r:5,fill:s.color},svg);svgNode("title",{},dot).textContent=p.label;}
  }
  svgNode("text",{x:72,y:252},svg).textContent=points[0].label.split(" | ")[0];
  svgNode("text",{x:840,y:252},svg).textContent=points[points.length-1].label.split(" | ")[0];
  svgNode("text",{x:350,y:275},svg).textContent=title;
}
function draw(){
  const p=position(),v=arm(),trace=v.trace;
  cursor=Math.min(cursor,Math.max(0,trace.length-1));
  el("scrub").max=String(Math.max(0,trace.length-1));el("scrub").value=String(cursor);el("scrub").disabled=!trace.length;
  el("previous").disabled=!cursor;el("next").disabled=cursor>=trace.length-1;el("play").disabled=trace.length<2;
  el("position-status").textContent=p.occ+" / "+p.contracts+" contract(s) / "+v.status+" / "+p.quotes_available+" recorded quotes / "+p.bare_quotes+" missing context";
  if(!trace.length){el("action").textContent="Unreplayable";el("rule").textContent="No recorded engine context";
    el("explanation").textContent="There is no decision trace. This path is excluded from realized and paired dollar comparisons.";
    el("fill").textContent="Realized P&L: unavailable";el("clock").textContent="No usable marks";el("trace").textContent="[]";plot(el("chart"),[]);return;}
  const mark=trace[cursor],d=mark.decision;
  el("clock").textContent=mark.time_et.replace("T"," ")+" ET / mark "+(cursor+1)+" of "+trace.length;
  el("action").textContent=d.action;el("rule").textContent=d.rule;
  el("explanation").textContent=d.rule==="engine_error" ? "The engine raised "+d.error_type+". The replay retains a HOLD and records the error; it does not invent an exit." :
    "The "+el("variant").value+" engine returned "+d.action+" at this mark. The rule label and full computed state below come from the actual decision. "+(v.v3_context_from_entry?"Probability and horizon context use the entry snapshot where absent from stored marks.":"");
  el("fill").textContent=d.action==="SELL" ? "First exit bid "+mark.inputs.bid.toFixed(4)+" / buy ask "+p.entry_ask.toFixed(4)+" / net after fees "+money(v.net_after_fees):
    "No exit at this mark. Realized P&L remains unavailable until the first SELL.";
  el("trace").textContent=JSON.stringify(mark,null,2);
  plot(el("chart"),[{color:"#5ce1ba",points:trace.slice(0,cursor+1).map(m=>({x:m.ts_epoch,y:m.inputs.bid,label:m.time_et.slice(11,16)+" ET | bid "+m.inputs.bid+" | "+m.decision.action+" "+m.decision.rule}))},
    {color:"#85a7ff",points:trace.slice(0,cursor+1).map(m=>({x:m.ts_epoch,y:m.inputs.ask,label:m.time_et.slice(11,16)+" ET | ask "+m.inputs.ask}))}],
    {baseline:p.entry_ask,title:"Stored bid (green) / ask (blue) through selected mark"});
}
function reset(){pause();cursor=0;draw();drawEquity();}
function tick(){if(cursor>=arm().trace.length-1){pause();return;}cursor++;draw();timer=setTimeout(tick,Number(el("speed").value));}
el("play").addEventListener("click",()=>{if(timer!==null){pause();return;}if(cursor>=arm().trace.length-1)cursor=0;el("play").textContent="Pause";timer=setTimeout(tick,Number(el("speed").value));draw();});
el("speed").addEventListener("change",()=>{if(timer!==null){clearTimeout(timer);timer=setTimeout(tick,Number(el("speed").value));}});
el("previous").addEventListener("click",()=>{pause();cursor=Math.max(0,cursor-1);draw();});
el("next").addEventListener("click",()=>{pause();cursor=Math.min(arm().trace.length-1,cursor+1);draw();});
el("scrub").addEventListener("input",()=>{pause();cursor=Number(el("scrub").value);draw();});
el("position").addEventListener("change",reset);el("variant").addEventListener("change",reset);
el("dataset").textContent=report.dataset.label+(report.dataset.fictional?" / FICTIONAL DATA":" / supplied history");
for(const name of names){option(name,name,el("variant"));const a=report.summary[name],card=text("article","",el("summary"),"card");
  text("h3",name,card);text("p",money(a.realized_net_sum),card,"metric");text("p","Closed-only net after fees",card);
  text("p",a.closed+" closed / "+a.open+" open / "+a.unreplayable+" unreplayable / "+a.engine_errors+" errors",card,"small");
  text("p","Mean of "+a.closed+" closed: "+money(a.realized_net_mean),card,"small");}
for(const [i,p] of report.positions.entries()){option(String(i),p.position_id+" / "+p.occ,el("position"));
  for(const [name,v] of Object.entries(p.variants)){const tr=document.createElement("tr");el("positions").append(tr);
    const td=text("td","",tr),button=text("button",p.position_id,td);button.addEventListener("click",()=>{el("position").value=String(i);el("variant").value=name;reset();el("replay").scrollIntoView({behavior:"smooth",block:"start"});el("replay").focus({preventScroll:true});});
    text("td",name,tr);text("td",v.status,tr,v.status);text("td",v.status==="closed"?v.trace[v.trace.length-1].time_et.replace("T"," ")+" ET":"Unavailable",tr);
    text("td",v.result?v.result.rule:"No context",tr);text("td",money(v.net_after_fees),tr);text("td",(v.result?v.result.marks_replayed:0)+" / "+p.bare_quotes+" / "+(v.result?v.result.engine_errors:0),tr);}}
el("paired").textContent=report.paired_closed_comparisons.length+" position(s) closed in both engines. Net deltas and timing differences are retained in the full JSON report.";
for(const row of report.paired_closed_comparisons){const tr=text("tr","",el("comparisons"));for(const value of [row.position_id,row.baseline,row.variant,money(row.net_delta),row.exit_delay_minutes])text("td",value,tr);}
if(!report.paired_closed_comparisons.length){const td=text("td","No positions closed in both engines.",text("tr","",el("comparisons")));td.colSpan=5;}
for(const [k,v] of Object.entries(report.assumptions)){text("dt",k.replaceAll("_"," "),el("assumptions"));text("dd",v,el("assumptions"));}
el("hashes").textContent=JSON.stringify({report_sha256:report.report_sha256,dataset:report.dataset,source_sha256:report.source_sha256,configuration_sha256:report.configuration_sha256,environment:report.environment,parameters:Object.fromEntries(names.map(n=>[n,report.summary[n].parameters]))},null,2);
function drawEquity(){const name=el("variant").value;let total=0;const rows=report.positions.filter(p=>p.variants[name].status==="closed").sort((a,b)=>a.variants[name].exit_ts-b.variants[name].exit_ts||a.position_id.localeCompare(b.position_id));
 const points=rows.map(p=>{total+=p.variants[name].net_after_fees;return {x:p.variants[name].exit_ts,y:total,label:p.variants[name].trace.slice(-1)[0].time_et.replace("T"," ")+" ET | "+p.position_id+" | "+money(total)};});
 plot(el("equity"),points.length?[{color:"#5ce1ba",points}]:[],{baseline:0,title:name+" / closed exits only",dollars:true});}
function download(name,type,data){const url=URL.createObjectURL(new Blob([data],{type}));const a=document.createElement("a");a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
el("export-json").addEventListener("click",()=>download("shadow-replay-report.json","application/json",JSON.stringify(report,null,2)));
const csvCell=(value)=>{if(value===null||value===undefined)return "";let s=String(value);if(typeof value==="string"&&/^[\s]*[=+\-@]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
el("export-csv").addEventListener("click",()=>{const rows=[["position_id","day","occ","variant","status","entry_ask","contracts","exit_ts","exit_minute","rule","net_before_fees","net_after_fees","marks_replayed","skipped_no_ext","engine_errors","entry_sha256","quotes_sha256"]];
 for(const p of report.positions)for(const [name,v] of Object.entries(p.variants)){const r=v.result||{};rows.push([p.position_id,p.day,p.occ,name,v.status,p.entry_ask,p.contracts,v.exit_ts,r.exit_minute,r.rule,r.net_worst,v.net_after_fees,r.marks_replayed,p.bare_quotes,r.engine_errors,p.entry_sha256,p.quotes_sha256]);}
 download("shadow-replay-positions.csv","text/csv",rows.map(r=>r.map(csvCell).join(",")).join("\r\n")+"\r\n");});
el("print").addEventListener("click",()=>window.print());
const tours=[["coverage","Read coverage first.","Closed-only dollars omit open and unreplayable paths. The fictional flag makes demonstration data explicit."],
 ["replay","Replay the actual decision.","Choose a position and engine, then play or scrub the recorded marks. The trace stops at the first SELL."],
 ["results","Compare on identical paths.","Compare rule, timing, fees and errors. The cumulative sequence sorts actual exits; it never assigns zero P&L to open positions."],
 ["provenance","Export the evidence.","The full JSON contains input, code and configuration hashes plus every consumed decision. Keep the source ledgers to reproduce it."]];
let tourIndex=0;
function showTour(){const step=tours[tourIndex];el(step[0]).scrollIntoView({block:"center"});el("tour-progress").textContent="Step "+(tourIndex+1)+" / "+tours.length;el("tour-title").textContent=step[1];el("tour-body").textContent=step[2];el("tour-back").disabled=tourIndex===0;el("tour-next").textContent=tourIndex===tours.length-1?"Finish tour":"Next";}
el("tour").addEventListener("click",()=>{pause();tourIndex=0;showTour();el("tour-dialog").showModal();});
el("tour-back").addEventListener("click",()=>{tourIndex=Math.max(0,tourIndex-1);showTour();});
el("tour-next").addEventListener("click",()=>{if(tourIndex===tours.length-1){el("tour-dialog").close();el("tour").textContent="Tour complete / replay tour";el("tour").focus();return;}tourIndex++;showTour();});
el("tour-close").addEventListener("click",()=>el("tour-dialog").close());
document.addEventListener("visibilitychange",()=>{if(document.hidden)pause();});
const preferred=report.positions.findIndex(p=>p.position_id==="winner");
if(preferred>=0)el("position").value=String(preferred);reset();
