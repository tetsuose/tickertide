import React, { useState, useRef, useLayoutEffect, useEffect, useMemo } from "react";

/* ======================================================================
   TickerTide — UX REFERENCE (v2). NOT the implementation.
   Synthetic data (mulberry32 seed), US-listed only, no real pipeline.
   This file locks LAYOUT / INTERACTION / HIERARCHY / COLOR only.
   Real data contract + algorithms live in BUILD-PLAN.md (§1–§5).
   Do NOT copy the data-gen logic here; copy the UX.

   Spine: one per-stock composite engine -> 5 surfaces, 2 scales
          (wide explore / bounded decide), zero persistent backend.
   Surfaces: Ocean · Discovery · Rotation · Valuation · Stock

   Invariants the build MUST preserve:
   - evidence-first: raw facts by default; composite is an expandable
     badge only; never buy / target / star verdicts.
   - Ocean axes FIXED x=RS pctile, y=Valuation pctile (no RRG-axes mode).
   - Rotation = RS-Ratio multi-line (not RRG scatter); row/line click
     -> set scope + drill (N=1 solo line + member evidence-cards).
   - global scope {all|sector|theme|pinned}: single source, sticky across
     tabs, visible + one-click dismissable; Discovery/Valuation/Rotation/
     Ocean ALL respond to it.
   - pctile = common-vintage only (rank within current cohort; stale
     rows show "vint", not ranked against fresh).
   - composite weights are an OPINION (early<->reliable knob), not fitted;
     always exposed via knob + component bars + expandable badge.
   ====================================================================== */

// ---------- deterministic RNG ----------
function mulberry32(a){return function(){a|=0;a=(a+0x6d2b79f5)|0;let t=Math.imul(a^(a>>>15),1|a);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296;};}
const rng = mulberry32(20260604);
const rnd=(lo,hi)=>lo+(hi-lo)*rng();
const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
const pick=(arr)=>arr[Math.floor(rng()*arr.length)];

const N=1800, WEEKS=14;

// ---------- taxonomies ----------
const SECTORS=[
 {k:"TECH",n:"Info Tech",c:"#4d9bff"},{k:"COMM",n:"Comm Svcs",c:"#7c6bff"},
 {k:"DISC",n:"Cons Disc",c:"#ff8f3f"},{k:"HLTH",n:"Health Care",c:"#2ec0a0"},
 {k:"FIN",n:"Financials",c:"#3fb950"},{k:"INDU",n:"Industrials",c:"#c9a227"},
 {k:"NRG",n:"Energy",c:"#e0612e"},{k:"STPL",n:"Cons Staples",c:"#9aa7b5"},
 {k:"MATL",n:"Materials",c:"#b06fd0"},{k:"UTIL",n:"Utilities",c:"#5f8fa8"},
 {k:"RE",n:"Real Estate",c:"#d08fae"},
];
const SECI=Object.fromEntries(SECTORS.map((s,i)=>[s.k,i]));
const THEMES=[
 {k:"AI",n:"AI",c:"#2ec07a"},{k:"ROBO",n:"Robotics 智能机器人",c:"#ff5d57"},
 {k:"SPACE",n:"Space Compute 太空算力",c:"#5197ff"},{k:"OPTIC",n:"Optical 光模块",c:"#e0a02e"},
 {k:"SEMI",n:"Semis",c:"#7c6bff"},{k:"NUKE",n:"Nuclear",c:"#2ec0a0"},
 {k:"CYBR",n:"Cybersecurity",c:"#ff8f3f"},{k:"CLOUD",n:"Cloud",c:"#9aa7b5"},
];
const THEMEC=Object.fromEntries(THEMES.map(t=>[t.k,t.c]));
const techThemes=["AI","ROBO","SPACE","OPTIC","SEMI","CLOUD","CYBR"];

// ---------- ticker gen ----------
const L="ABCDEFGHIKLMNOPRSTUVXYZ".split(""); const used=new Set();
function mkTicker(){for(;;){let n=rng()<.5?3:4,t="";for(let i=0;i<n;i++)t+=L[Math.floor(rng()*L.length)];if(!used.has(t)){used.add(t);return t;}}}

// ---------- archetypes ----------
const archMix=[...Array(140).fill("leader"),...Array(230).fill("early"),...Array(180).fill("fader"),
 ...Array(230).fill("improving"),...Array(440).fill("neutral"),...Array(580).fill("laggard")];
function genMetrics(a){
 const M={
  leader:{rs:[.82,.97],high:[.92,1],trend:[.8,1],vol:[.6,.95],accel:[.45,.7]},
  early:{rs:[.6,.85],high:[.7,.88],trend:[.45,.8],vol:[.5,.85],accel:[.8,.98]},
  fader:{rs:[.7,.9],high:[.78,.9],trend:[.55,.85],vol:[.25,.5],accel:[.1,.38]},
  improving:{rs:[.42,.62],high:[.6,.8],trend:[.35,.6],vol:[.5,.8],accel:[.75,.95]},
  neutral:{rs:[.4,.65],high:[.65,.85],trend:[.4,.7],vol:[.35,.6],accel:[.4,.6]},
  laggard:{rs:[.08,.4],high:[.5,.72],trend:[.05,.4],vol:[.2,.55],accel:[.2,.55]},
 }[a];
 return {rs:rnd(...M.rs),high:rnd(...M.high),trend:rnd(...M.trend),vol:rnd(...M.vol),accel:rnd(...M.accel)};
}
function jit(m,d){return{rs:clamp(m.rs+rnd(-d,d),0,1),high:clamp(m.high+rnd(-d*.6,d*.6),.5,1),trend:clamp(m.trend+rnd(-d,d),0,1),vol:clamp(m.vol+rnd(-d,d),0,1),accel:clamp(m.accel+rnd(-d,d),0,1)};}

// growthy archetypes -> expensive valuations
const GROWTHY=new Set(["leader","early","improving"]);
function genVal(a,growthy){
 if(growthy){
  const g=rnd(.22,.66), m=rnd(-.12,.2);
  return {pe: rng()<.4?null:rnd(35,95), ps:rnd(6,30), evs:rnd(6,32), evebitda:rnd(24,62), peg:rnd(.8,2.6), growth:g, margin:m, rule40:clamp(g*100+m*100,5,110)};
 }
 if(a==="laggard"){
  const g=rnd(-.08,.08), m=rnd(.02,.16);
  return {pe: rng()<.3?null:rnd(6,16), ps:rnd(.6,3), evs:rnd(.8,3.4), evebitda:rnd(5,12), peg:rnd(1.5,4), growth:g, margin:m, rule40:clamp(g*100+m*100,-10,40)};
 }
 const g=rnd(.03,.16), m=rnd(.08,.3);
 return {pe:rnd(11,26), ps:rnd(1.4,5.5), evs:rnd(1.8,6), evebitda:rnd(8,18), peg:rnd(.7,2.2), growth:g, margin:m, rule40:clamp(g*100+m*100,5,55)};
}

function assignThemes(sec){
 const out=[]; const r=rng();
 if(["TECH","COMM"].includes(sec)){ if(r<.85){const t=pick(techThemes); out.push({k:t,w:rnd(.3,1)}); if(rng()<.4){const t2=pick(techThemes.filter(x=>x!==t)); out.push({k:t2,w:rnd(.2,.6)});}} }
 else if(["DISC","INDU"].includes(sec)){ if(r<.4) out.push({k:pick(["ROBO","SPACE","SEMI"]),w:rnd(.2,.7)}); }
 else if(["NRG","UTIL"].includes(sec)){ if(r<.45) out.push({k:"NUKE",w:rnd(.3,1)}); }
 else if(sec==="HLTH"){ if(r<.2) out.push({k:"AI",w:rnd(.2,.5)}); }
 return out;
}

const UNIVERSE=archMix.map((a,i)=>{
 const sec=pick(SECTORS).k;
 const growthy=GROWTHY.has(a) && (["TECH","COMM","HLTH","DISC"].includes(sec) ? true : rng()<.3);
 const today=jit(genMetrics(a),.05);
 const yest=jit({rs:(today.rs+genMetrics(a).rs)/2,high:today.high,trend:today.trend,vol:today.vol,accel:clamp(today.accel+rnd(-.18,.18),0,1)},.04);
 const rsNow=today.rs*100;
 const valNow=clamp((growthy? rnd(60,96): a==="laggard"? rnd(15,45): rnd(35,65)),2,98);
 const mktcap=Math.exp(rnd(Math.log(.3),Math.log(growthy?2600:900)));
 // weekly path drifting into (rsNow,valNow)
 const r0=clamp(rsNow+rnd(-26,26),2,98), v0=clamp(valNow+rnd(-20,20),2,98);
 const series=[];
 for(let w=0;w<WEEKS;w++){
  const t=w/(WEEKS-1);
  const rs=clamp(r0+(rsNow-r0)*t+rnd(-4,4),0,100);
  const val=clamp(v0+(valNow-v0)*t+rnd(-3.5,3.5),0,100);
  series.push({rs,val});
 }
 return {id:i,ticker:mkTicker(),sec,arch:a,growthy,today,yest,val:genVal(a,growthy),mktcap,themes:assignThemes(sec),series};
});

// ---------- RRG bucket paths (sectors + themes) ----------
function bucketPaths(keys,colorOf,spread){
 return keys.map((kk,idx)=>{
  // intentional quadrant spread
  const ang=(idx/keys.length)*Math.PI*2; const rad=rnd(1.2,3.4);
  let hx=100+Math.cos(ang)*rad+rnd(-.6,.6), hy=100+Math.sin(ang)*rad+rnd(-.6,.6);
  const pts=[[hx,hy]]; let x=hx,y=hy;
  for(let i=0;i<5;i++){ x=x-rnd(.15,.5)+rnd(-.18,.18); y=y+rnd(.05,.45)*(i%2?-1:1)+rnd(-.15,.15); pts.push([clamp(x,96.5,104),clamp(y,96.5,104)]);}
  pts.reverse();
  return {key:kk.k,name:kk.n,color:colorOf(kk),pts};
 });
}
const RRG_SEC=bucketPaths(SECTORS,(s)=>s.c);
const RRG_THEME=bucketPaths(THEMES,(t)=>t.c);
const quadOf=(x,y)=>x>=100?(y>=100?"lead":"weak"):(y>=100?"impr":"lag");
// ---------- sector/theme RS-Ratio weekly time series (multi-line rotation chart) ----------
function bucketRSLines(keys,colorOf){
 const W=40;
 return keys.map((kk,idx)=>{
  const r=lcg((((idx+1)*2246822519)^0x9e3779b9)>>>0);
  const phase=(idx/keys.length)*Math.PI*2, amp=2.5+r()*5, driftEnd=(r()-0.5)*9;
  let v=100+Math.cos(phase)*amp*0.5; const series=[];
  for(let i=0;i<W;i++){const t=i/(W-1); const target=100+Math.sin(phase+t*Math.PI*1.3)*amp+driftEnd*t; v=v+(target-v)*0.4+(r()-0.5)*1.1; series.push(clamp(+v.toFixed(2),88,112));}
  return {key:kk.k,name:kk.n,color:colorOf(kk),series};
 });
}
const RS_SEC_LINES=bucketRSLines(SECTORS,(s)=>s.c);
const RS_THEME_LINES=bucketRSLines(THEMES,(t)=>t.c);
const QUAD={lead:{c:"var(--grn)",label:"LEADING"},weak:{c:"var(--amb)",label:"WEAKENING"},lag:{c:"var(--red)",label:"LAGGING"},impr:{c:"var(--blu)",label:"IMPROVING"}};

// ---------- scoring ----------
function weights(k){return {rs:.20+.03*k,high:.34-.24*k,trend:.22-.10*k,vol:.14-.04*k,accel:.10+.35*k};}
const WLABEL={rs:"RS",high:"52WH",trend:"Trend",vol:"Vol",accel:"Accel"};
const WORDER=["rs","high","trend","vol","accel"];
function score(m,w){const h=clamp((m.high-.5)/.5,0,1);return 100*(w.rs*m.rs+w.high*h+w.trend*m.trend+w.vol*m.vol+w.accel*m.accel);}
const templatePass=(m)=>m.trend>.7&&m.high>.9;
const scoreColor=(s)=>s>=62?"var(--grn)":s>=47?"var(--amb)":"var(--dim2)";
const pInt=(v)=>Math.round(v*100);

// ---------- FLIP ----------
function useFlip(orderKey){
 const refs=useRef(new Map()),prev=useRef(new Map());
 useLayoutEffect(()=>{const next=new Map();refs.current.forEach((el,k)=>{if(el)next.set(k,el.getBoundingClientRect().top);});
  refs.current.forEach((el,k)=>{if(!el)return;const p=prev.current.get(k),n=next.get(k);
   if(p!=null&&n!=null&&Math.abs(p-n)>.5){const dy=p-n;el.style.transition="none";el.style.transform=`translateY(${dy}px)`;
    requestAnimationFrame(()=>{el.style.transition="transform 460ms cubic-bezier(.2,.8,.2,1)";el.style.transform="";});}});
  prev.current=next;},[orderKey]);
 return (k)=>(el)=>{if(el)refs.current.set(k,el);else refs.current.delete(k);};
}

// ---------- small bits ----------
function Bar({v,color,w=56}){return <span style={{display:"inline-flex",alignItems:"center"}}><span style={{width:w,height:5,background:"var(--line2)",borderRadius:3,overflow:"hidden"}}><span style={{display:"block",width:`${clamp(v,0,100)}%`,height:"100%",background:color,borderRadius:3,transition:"width .3s"}}/></span></span>;}
function Cell({v}){const c=v>=.7?"var(--grn)":v>=.45?"var(--txt)":"var(--dim)";return <span style={{color:c,fontVariantNumeric:"tabular-nums"}}>{pInt(v)}</span>;}
function Spark({vals,color,w=120,h=30,base}){
 if(!vals||!vals.length)return null;const mn=Math.min(...vals),mx=Math.max(...vals),rg=mx-mn||1;
 const pts=vals.map((v,i)=>`${(i/(vals.length-1))*w},${h-((v-mn)/rg)*(h-4)-2}`).join(" ");
 return <svg width={w} height={h} style={{display:"block"}}>{base!=null&&<line x1={0} y1={h-((base-mn)/rg)*(h-4)-2} x2={w} y2={h-((base-mn)/rg)*(h-4)-2} stroke="var(--line2)" strokeDasharray="2 3"/>}<polyline points={pts} fill="none" stroke={color} strokeWidth="1.6"/></svg>;
}

// ====================================================================
//  OCEAN  (canvas)
// ====================================================================
const OW=880, OH=470, PL=46, PR=18, PT=16, PB=40;
function Ocean({week,colorBy,pinned,setPinned,activeTheme,scope}){
 const cv=useRef(null), pos=useRef([]), [hover,setHover]=useRef? useState(null): [null];
 const plotW=OW-PL-PR, plotH=OH-PT-PB;
 const dom = {xmin:0,xmax:100,ymin:0,ymax:100};
 const sx=(v)=>PL+((v-dom.xmin)/(dom.xmax-dom.xmin))*plotW;
 const sy=(v)=>PT+plotH-((v-dom.ymin)/(dom.ymax-dom.ymin))*plotH;
 const getXY=(s,w)=>{const p=s.series[w]; return [p.rs,p.val];};
 const colorFor=(s)=>{
  if(colorBy==="quadrant"){const p=s.series[week];const strong=p.rs>=50,cheap=p.val<50;return strong?(cheap?"#2ec07a":"#e0a02e"):(cheap?"#5197ff":"#56616f");}
  if(colorBy==="theme"){const t=s.themes.find(x=>x.k===activeTheme);return t?THEMEC[activeTheme]:"rgba(120,130,145,.18)";}
  return SECTORS[SECI[s.sec]].c;
 };
 const rFor=(s)=>clamp(2.0+Math.sqrt(s.mktcap)*0.34,1.6,11);

 useEffect(()=>{
  const c=cv.current; if(!c)return; const ctx=c.getContext("2d");
  c.width=OW*2; c.height=OH*2; ctx.setTransform(2,0,0,2,0,0); ctx.clearRect(0,0,OW,OH);
  // quadrant tints
  const cx=sx(50), cy=sy(50);
  ctx.fillStyle="rgba(46,192,122,.07)";ctx.fillRect(cx,cy,OW-PR-cx,PT+plotH-cy); // strong+cheap (bottom-right)
  // crosshair
  ctx.strokeStyle="rgba(120,135,150,.35)";ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(cx,PT);ctx.lineTo(cx,PT+plotH);ctx.moveTo(PL,cy);ctx.lineTo(PL+plotW,cy);ctx.stroke();
  // points (current week)
  const arr=[]; const inScope=(s)=>scope.kind==="all"||(scope.kind==="theme"?s.themes.some(t=>t.k===scope.key):s.sec===scope.key);
  for(const s of UNIVERSE){const [vx,vy]=getXY(s,week);const px=sx(vx),py=sy(vy),r=rFor(s);
   const faded=!inScope(s)||(colorBy==="theme"&&!s.themes.find(x=>x.k===activeTheme));
   ctx.globalAlpha=faded?0.06:(colorBy==="theme"?1:.72);
   ctx.beginPath();ctx.fillStyle=colorFor(s);ctx.arc(px,py,faded?1.2:r,0,7);ctx.fill();
   if(!faded)arr.push({id:s.id,px,py,r});
  }
  ctx.globalAlpha=1;
  // hover ring
  if(hover){const [vx,vy]=getXY(hover,week);ctx.beginPath();ctx.strokeStyle="#fff";ctx.lineWidth=1.5;ctx.arc(sx(vx),sy(vy),rFor(hover)+3,0,7);ctx.stroke();}
  // pinned trails + arrows
  for(const id of pinned){const s=UNIVERSE[id];if(!s)continue;const col=SECTORS[SECI[s.sec]].c;
   ctx.strokeStyle=col;ctx.lineWidth=2;ctx.beginPath();
   for(let w=0;w<=week;w++){const [vx,vy]=getXY(s,w);const px=sx(vx),py=sy(vy);w===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
   ctx.stroke();
   // arrowhead at current week
   if(week>0){const [ax,ay]=getXY(s,week-1),[bx,by]=getXY(s,week);const x1=sx(ax),y1=sy(ay),x2=sx(bx),y2=sy(by);
    const ang=Math.atan2(y2-y1,x2-x1);ctx.fillStyle=col;ctx.beginPath();ctx.moveTo(x2,y2);
    ctx.lineTo(x2-8*Math.cos(ang-.4),y2-8*Math.sin(ang-.4));ctx.lineTo(x2-8*Math.cos(ang+.4),y2-8*Math.sin(ang+.4));ctx.closePath();ctx.fill();}
   const [hx,hy]=getXY(s,week);ctx.fillStyle="#e9eef5";ctx.font="600 11px IBM Plex Mono,monospace";ctx.fillText(s.ticker,sx(hx)+8,sy(hy)-7);
   ctx.beginPath();ctx.fillStyle=col;ctx.arc(sx(hx),sy(hy),rFor(s)+1,0,7);ctx.fill();ctx.strokeStyle="#0a0e14";ctx.lineWidth=1.5;ctx.stroke();
  }
  pos.current=arr;
 },[week,colorBy,activeTheme,pinned,hover,scope]);

 const toLogical=(e)=>{const r=cv.current.getBoundingClientRect();return [(e.clientX-r.left)*(OW/r.width),(e.clientY-r.top)*(OH/r.height)];};
 const nearest=(lx,ly)=>{let best=null,bd=1e9;for(const p of pos.current){const d=(p.px-lx)**2+(p.py-ly)**2;if(d<bd){bd=d;best=p;}}return best&&bd<(best.r+5)**2?best.id:null;};
 const onMove=(e)=>{const [lx,ly]=toLogical(e);const id=nearest(lx,ly);setHover(id!=null?UNIVERSE[id]:null);};
 const onClick=(e)=>{const [lx,ly]=toLogical(e);const id=nearest(lx,ly);if(id==null)return;setPinned(p=>p.includes(id)?p.filter(x=>x!==id):[...p,id]);};

 return (
  <div style={{position:"relative"}}>
   <canvas ref={cv} onMouseMove={onMove} onMouseLeave={()=>setHover(null)} onClick={onClick}
    style={{width:"100%",height:"auto",aspectRatio:`${OW}/${OH}`,cursor:"pointer",display:"block",background:"var(--bg2)",border:"1px solid var(--line)",borderRadius:9}}/>
   {/* axis labels overlay */}
   <div className="oax-x">RS percentile → (weak · strong)</div>
   <div className="oax-y">Valuation ↑ (cheap · expensive)</div>
   <div className="oquad">cheap &amp; strengthening</div>
   {hover && <Tip s={hover} week={week}/>}
  </div>
 );
}
function Tip({s,week}){
 const p=s.series[week];
 return <div className="otip">
  <b>{s.ticker}</b> <span className="dim">{SECTORS[SECI[s.sec]].n}</span>
  <div className="otrow"><span>RS pct</span><b>{p.rs.toFixed(0)}</b></div>
  <div className="otrow"><span>Valuation pct</span><b>{p.val.toFixed(0)}</b></div>
  <div className="otrow"><span>P/S</span><b>{s.val.ps.toFixed(1)}</b></div>
  <div className="otrow"><span>Mkt cap</span><b>${s.mktcap.toFixed(1)}B</b></div>
  {s.themes.length>0&&<div className="otags">{s.themes.map(t=>(<span key={t.k} style={{color:THEMEC[t.k]}}>{t.k}</span>))}</div>}
  <div className="ohint">click to pin / track</div>
 </div>;
}

// ====================================================================
//  RRG chart (shared by rotation tab)
// ====================================================================
function RRGChart({data}){
 const W=520,H=420,pad=38,dmin=96.5,dmax=103.8;
 const sx=(v)=>pad+((v-dmin)/(dmax-dmin))*(W-2*pad), sy=(v)=>H-pad-((v-dmin)/(dmax-dmin))*(H-2*pad);
 const cx=sx(100),cy=sy(100),ticks=[98,100,102];
 const qf={lead:"rgba(46,192,122,.07)",weak:"rgba(224,160,46,.07)",lag:"rgba(255,93,87,.06)",impr:"rgba(81,151,255,.07)"};
 return <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{background:"var(--bg2)",border:"1px solid var(--line)",borderRadius:9}}>
  <rect x={cx} y={pad} width={W-pad-cx} height={cy-pad} fill={qf.lead}/><rect x={cx} y={cy} width={W-pad-cx} height={H-pad-cy} fill={qf.weak}/>
  <rect x={pad} y={cy} width={cx-pad} height={H-pad-cy} fill={qf.lag}/><rect x={pad} y={pad} width={cx-pad} height={cy-pad} fill={qf.impr}/>
  {ticks.map(t=>(<g key={"x"+t}><line x1={sx(t)} y1={pad} x2={sx(t)} y2={H-pad} stroke="var(--line)" strokeDasharray="2 4"/><text x={sx(t)} y={H-pad+15} className="axt" textAnchor="middle">{t}</text></g>))}
  {ticks.map(t=>(<g key={"y"+t}><line x1={pad} y1={sy(t)} x2={W-pad} y2={sy(t)} stroke="var(--line)" strokeDasharray="2 4"/><text x={pad-7} y={sy(t)+3} className="axt" textAnchor="end">{t}</text></g>))}
  <line x1={cx} y1={pad} x2={cx} y2={H-pad} stroke="var(--line2)"/><line x1={pad} y1={cy} x2={W-pad} y2={cy} stroke="var(--line2)"/>
  <text x={W-pad-4} y={pad+13} className="qlab" fill="var(--grn)" textAnchor="end">LEADING</text>
  <text x={W-pad-4} y={H-pad-6} className="qlab" fill="var(--amb)" textAnchor="end">WEAKENING</text>
  <text x={pad+4} y={H-pad-6} className="qlab" fill="var(--red)">LAGGING</text>
  <text x={pad+4} y={pad+13} className="qlab" fill="var(--blu)">IMPROVING</text>
  {data.map(s=>{const head=s.pts[s.pts.length-1];const col=s.color;const segs=[];
   for(let i=1;i<s.pts.length;i++){const a=s.pts[i-1],b=s.pts[i];segs.push(<line key={i} x1={sx(a[0])} y1={sy(a[1])} x2={sx(b[0])} y2={sy(b[1])} stroke={col} strokeWidth={1.4} strokeOpacity={.18+.16*i} strokeLinecap="round"/>);}
   return <g key={s.key}>{segs}<circle cx={sx(head[0])} cy={sy(head[1])} r={5} fill={col} stroke="var(--bg)" strokeWidth={1.5}/><text x={sx(head[0])+8} y={sy(head[1])+3} className="rlab" fill={col}>{s.key}</text></g>;
  })}
 </svg>;
}

// ====================================================================
//  MAIN
// ====================================================================
// ---------- synthetic OHLC bars per stock (for evidence-card charts) ----------
function lcg(seed){let s=(seed>>>0)||1;return function(){s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296;};}
const barCache={};
function genBars(stock){
 if(barCache[stock.id])return barCache[stock.id];
 var r=lcg((stock.id*2654435761>>>0)^0x9e3779b9), a=stock.arch, N=520, DISP=90;
 var brk = a==="early"?Math.round(N*0.78) : a==="leader"?Math.round(N*0.5) : a==="improving"?Math.round(N*0.84) : a==="fader"?Math.round(N*0.34) : 1e9;
 var rollEnd = brk+Math.round(N*0.32);
 var px=20+r()*30, bars=[];
 for(var i=0;i<N;i++){
   var drift;
   if(a==="laggard") drift=-0.0006+(r()-0.5)*0.018;
   else if(a==="fader") drift = i<brk? (r()-0.5)*0.014 : (i<rollEnd? 0.007+(r()-0.42)*0.02 : (r()-0.57)*0.02);
   else if(a==="neutral") drift=(r()-0.5)*0.015;
   else { drift = i<brk? (r()-0.5)*0.015 : 0.0045+(r()-0.46)*0.018; if(i>=brk&&r()<0.1) drift-=0.028; }
   var o=px, c=Math.max(1,px*(1+drift)), hh=Math.max(o,c)*(1+r()*0.008), ll=Math.min(o,c)*(1-r()*0.008);
   var inBrk=i>=brk&&i<brk+12, v=inBrk?1.7+r()*1.3:(i>=brk&&i<rollEnd?1.0+r()*0.7:0.8+r()*0.4);
   bars.push({o:o,c:c,h:hh,l:ll,v:v}); px=c;
 }
 function ma(n,idx){var s=0,k=0;for(var j=idx;j>idx-n&&j>=0;j--){s+=bars[j].c;k++;}return s/k;}
 var ma50=[],ma150=[],ma200=[];
 for(var i=0;i<N;i++){ma50.push(ma(50,i));ma150.push(ma(150,i));ma200.push(ma(200,i));}
 var st=N-DISP, hw=bars.slice(Math.max(0,N-252)), hi252=hw[0].h;
 for(var i=0;i<hw.length;i++) if(hw[i].h>hi252) hi252=hw[i].h;
 var last=bars[N-1].c;
 function ret(n){return (N-1-n)>=0? last/bars[N-1-n].c-1 : 0;}
 var vol50=0;for(var j=N-50;j<N;j++)vol50+=bars[j].v;vol50/=50;
 var cross=N-1;for(var i=N-1;i>0;i--){if(bars[i].c>ma50[i]&&bars[i-1].c<=ma50[i-1]){cross=i;break;}}
 var out={bars:bars,ma50:ma50,ma150:ma150,ma200:ma200,disp:bars.slice(st),d50:ma50.slice(st),d150:ma150.slice(st),d200:ma200.slice(st),hi252:hi252,
   fields:{ret1m:ret(21),ret3m:ret(63),ret6m:ret(126),pctFromHigh:last/hi252-1,weeksSince:Math.max(1,Math.round((N-1-cross)/5)),volX:bars[N-1].v/vol50}};
 barCache[stock.id]=out;return out;
}

function MiniChart({ev}){
 var W=440,H=148,PL=4,PR=4,PT=4,priceH=104,gap=8,volH=30;
 var n=ev.disp.length,bw=(W-PL-PR)/n,cw=Math.max(1,bw*0.62);
 var pmin=1e9,pmax=-1e9,vmax=0;
 for(var i=0;i<n;i++){pmin=Math.min(pmin,ev.disp[i].l,ev.d200[i]);pmax=Math.max(pmax,ev.disp[i].h,ev.d50[i]);vmax=Math.max(vmax,ev.disp[i].v);}
 var pd=(pmax-pmin)*0.06;pmin-=pd;pmax+=pd;
 var X=function(i){return PL+i*bw+bw/2;}, PY=function(p){return PT+priceH-((p-pmin)/(pmax-pmin))*priceH;};
 var volBase=PT+priceH+gap+volH, VY=function(v){return volBase-(v/vmax)*volH;};
 var path=function(arr,col){var d="";for(var i=0;i<n;i++){d+=(i?"L":"M")+X(i).toFixed(1)+" "+PY(arr[i]).toFixed(1);}return <path d={d} fill="none" stroke={col} strokeWidth="1.3"/>;};
 var yh=PY(ev.hi252);
 return <svg viewBox={"0 0 "+W+" "+H} width="100%" style={{display:"block"}}>
   <line x1={PL} y1={yh} x2={W-PR} y2={yh} stroke="var(--dim2)" strokeDasharray="3 3" strokeWidth="1"/>
   {ev.disp.map(function(b,i){var up=b.c>=b.o,col=up?"var(--grn)":"var(--red)",y1=PY(b.o),y2=PY(b.c),top=Math.min(y1,y2),h=Math.max(0.8,Math.abs(y1-y2));
     return <g key={i}><line x1={X(i)} y1={PY(b.h)} x2={X(i)} y2={PY(b.l)} stroke={col} strokeWidth="0.7"/><rect x={X(i)-cw/2} y={top} width={cw} height={h} fill={col}/></g>;})}
   {path(ev.d200,"#888780")}{path(ev.d150,"#BA7517")}{path(ev.d50,"#378ADD")}
   {ev.disp.map(function(b,i){var up=b.c>=b.o;return <rect key={"v"+i} x={X(i)-cw/2} y={VY(b.v)} width={cw} height={volBase-VY(b.v)} fill={up?"rgba(46,192,122,.5)":"rgba(255,93,87,.5)"}/>;})}
 </svg>;
}

function EvidenceCard({s,onOpen,w}){
 var ev=genBars(s), sc=score(s.today,w), f=ev.fields;
 const [open,setOpen]=useState(false);
 var pc=function(v){return (v>=0?"+":"")+(v*100).toFixed(0)+"%";};
 return <div className="ecard">
   <div className="ec-head">
     <div className="ec-tk">{s.ticker} <span className="ec-sec">{SECTORS[SECI[s.sec]].n} · ${s.mktcap.toFixed(0)}B</span></div>
     <button className="ec-badge" style={{color:scoreColor(sc)}} onClick={function(e){e.stopPropagation();setOpen(!open);}}>{sc.toFixed(0)} <i>▾</i></button>
   </div>
   {s.themes.length>0 && <div className="ec-themes">{s.themes.map(function(t){return <span key={t.k} style={{color:THEMEC[t.k]}}>{t.k}</span>;})}</div>}
   {open && <div className="ec-comp">{WORDER.map(function(key){var v=key==="high"?(s.today.high-.5)/.5:s.today[key];return <div key={key} className="ec-crow"><span>{WLABEL[key]}</span><Bar v={v*100} color="var(--blu)" w={90}/><b>{pInt(v)}</b></div>;})}<div className="ec-note">composite = 这些原始分的加权和,无黑箱</div></div>}
   <div className="ec-chart" onClick={onOpen}><MiniChart ev={ev}/></div>
   <div className="ec-fields" onClick={onOpen}>
     <div className="ec-f"><span>1M</span><b style={{color:f.ret1m>=0?"var(--grn)":"var(--red)"}}>{pc(f.ret1m)}</b></div>
     <div className="ec-f"><span>3M</span><b style={{color:f.ret3m>=0?"var(--grn)":"var(--red)"}}>{pc(f.ret3m)}</b></div>
     <div className="ec-f"><span>6M</span><b style={{color:f.ret6m>=0?"var(--grn)":"var(--red)"}}>{pc(f.ret6m)}</b></div>
     <div className="ec-f"><span>from high</span><b>{pc(f.pctFromHigh)}</b></div>
     <div className="ec-f"><span>week</span><b>{f.weeksSince}</b></div>
     <div className="ec-f"><span>vol</span><b style={{color:f.volX>=1.5?"var(--grn)":"var(--txt)"}}>{f.volX.toFixed(1)}×</b></div>
   </div>
   <div className="ec-why" onClick={onOpen}><span className="ec-wl">why moving</span> <span className="dim">— AI enrichment placeholder</span></div>
 </div>;
}

// ---------- synthetic quarterly financials + P/S-over-time (for Stock stack) ----------
const finCache={};
function genFinancials(stock){
 if(finCache[stock.id])return finCache[stock.id];
 var ev=genBars(stock), bars=ev.bars, N=bars.length, closeNow=bars[N-1].c, mc=stock.mktcap, ps=stock.val.ps;
 var revTTMnow=mc/ps, g=Math.max(-0.05,Math.min(0.7,stock.val.growth)), gq=Math.pow(1+g,0.25);
 var Q=12, r=lcg((stock.id*40503>>>0)^0x85ebca6b);
 var denom=0; for(var k=Q-4;k<Q;k++)denom+=Math.pow(gq,k);
 var base=revTTMnow/(denom||1), rev=[];
 for(var k=0;k<Q;k++) rev.push(base*Math.pow(gq,k)*(1+(r()-0.5)*0.05));
 var quarters=[];
 for(var k=0;k<Q;k++){var ttm=k>=3?rev[k]+rev[k-1]+rev[k-2]+rev[k-3]:null, yoy=k>=4?rev[k]/rev[k-4]-1:null; quarters.push({rev:rev[k],ttm:ttm,yoy:yoy});}
 var qLen=Math.max(1,Math.floor(N/8)), psDaily=[];
 for(var i=0;i<N;i++){var dk=Math.min(7,Math.floor(i/qLen)), ri=4+dk, ttm=quarters[ri].ttm, mcD=mc*bars[i].c/closeNow; psDaily.push(ttm?mcD/ttm:null);}
 var out={quarters:quarters,psDaily:psDaily,qLen:qLen,revTTMnow:revTTMnow,psNow:ps};
 finCache[stock.id]=out;return out;
}

function StockChartStack({stock}){
 var ev=genBars(stock), fin=genFinancials(stock), bars=ev.bars, M=bars.length;
 var W=860, padL=50, padR=64, padT=12;
 var hP=186, g1=8, hV=26, g2=18, hR=74, g3=8, hPS=48, padB=18;
 var yP=padT, yV=yP+hP+g1, yR=yV+hV+g2, yPS=yR+hR+g3, H=yPS+hPS+padB;
 var bw=(W-padL-padR)/M, cw=Math.max(0.8,bw*0.62);
 var X=function(i){return padL+i*bw+bw/2;};
 var pmin=1e9,pmax=-1e9,vmax=0;
 for(var i=0;i<M;i++){pmin=Math.min(pmin,bars[i].l,ev.ma200[i]);pmax=Math.max(pmax,bars[i].h,ev.ma50[i]);vmax=Math.max(vmax,bars[i].v);}
 var pd=(pmax-pmin)*0.05||1;pmin-=pd;pmax+=pd;
 var PY=function(p){return yP+hP-((p-pmin)/(pmax-pmin))*hP;};
 var VY=function(v){return yV+hV-(v/(vmax||1))*hV;};
 var qd=fin.quarters.slice(4), rmax=0; for(var i=0;i<qd.length;i++) rmax=Math.max(rmax,qd[i].rev); rmax=rmax||1;
 var RY=function(v){return yR+hR-(v/rmax)*(hR-8);};
 var psv=[]; for(var i=0;i<fin.psDaily.length;i++) if(fin.psDaily[i]!=null) psv.push(fin.psDaily[i]);
 var psmin=Math.min.apply(null,psv), psmax=Math.max.apply(null,psv), psr=(psmax-psmin)*0.12||1; psmin-=psr; psmax+=psr;
 var SY=function(v){return yPS+hPS-((v-psmin)/(psmax-psmin))*hPS;};
 var qLen=fin.qLen;
 var line=function(arr,col,yfn){var d="",on=false;for(var i=0;i<M;i++){var v=arr[i];if(v==null){on=false;continue;}d+=(on?"L":"M")+X(i).toFixed(1)+" "+yfn(v).toFixed(1);on=true;}return <path d={d} fill="none" stroke={col} strokeWidth="1.4"/>;};
 var labels=function(yfn,vmn,vmx,fmt){var o=[];for(var t=0;t<=2;t++){var v=vmn+(vmx-vmn)*t/2;o.push(<text key={t} x={padL-6} y={yfn(v)+3} className="axt" textAnchor="end">{fmt(v)}</text>);}return o;};
 var yh=PY(ev.hi252), glines=[]; for(var k=0;k<=8;k++) glines.push(Math.min(M-1,k*qLen));
 return <svg viewBox={"0 0 "+W+" "+H} width="100%" style={{display:"block"}}>
   {glines.map(function(gi,k){var x=X(gi);return <line key={"g"+k} x1={x} y1={yP} x2={x} y2={yPS+hPS} stroke="var(--line)" strokeDasharray="2 5"/>;})}
   <text x={padL} y={yP-2} className="axl" textAnchor="start">PRICE · daily K + MA50/150/200</text>
   <text x={padL} y={yR-4} className="axl" textAnchor="start">REVENUE · quarterly</text>
   <text x={padL} y={yPS-3} className="axl" textAnchor="start">P/S · price ÷ TTM revenue</text>
   <line x1={padL} y1={yh} x2={W-padR} y2={yh} stroke="var(--dim2)" strokeDasharray="3 3"/>
   {bars.map(function(b,i){var up=b.c>=b.o,col=up?"var(--grn)":"var(--red)",y1=PY(b.o),y2=PY(b.c),top=Math.min(y1,y2),h=Math.max(0.6,Math.abs(y1-y2));
     return <g key={i}><line x1={X(i)} y1={PY(b.h)} x2={X(i)} y2={PY(b.l)} stroke={col} strokeWidth="0.6"/><rect x={X(i)-cw/2} y={top} width={cw} height={h} fill={col}/></g>;})}
   {line(ev.ma200,"#888780",PY)}{line(ev.ma150,"#BA7517",PY)}{line(ev.ma50,"#378ADD",PY)}
   {labels(PY,pmin,pmax,function(v){return v.toFixed(0);})}
   {bars.map(function(b,i){var up=b.c>=b.o;return <rect key={"v"+i} x={X(i)-cw/2} y={VY(b.v)} width={cw} height={(yV+hV)-VY(b.v)} fill={up?"rgba(46,192,122,.45)":"rgba(255,93,87,.45)"}/>;})}
   {qd.map(function(q,k){var cx=X(Math.min(M-1,k*qLen+Math.floor(qLen/2))), wq=qLen*bw*0.6, up=(q.yoy==null||q.yoy>=0); return <rect key={"r"+k} x={cx-wq/2} y={RY(q.rev)} width={wq} height={(yR+hR)-RY(q.rev)} fill={up?"rgba(46,192,122,.55)":"rgba(255,93,87,.55)"}/>;})}
   {labels(RY,0,rmax,function(v){return "$"+v.toFixed(0)+"B";})}
   <text x={W-padR+5} y={RY(qd[qd.length-1].rev)+3} className="axt" textAnchor="start">${qd[qd.length-1].rev.toFixed(1)}B{qd[qd.length-1].yoy!=null?" "+(qd[qd.length-1].yoy>=0?"+":"")+(qd[qd.length-1].yoy*100).toFixed(0)+"%y/y":""}</text>
   {line(fin.psDaily,"#e0a02e",SY)}
   {labels(SY,psmin,psmax,function(v){return v.toFixed(1)+"×";})}
   <text x={W-padR+5} y={SY(fin.psNow)+3} className="axt" textAnchor="start">{fin.psNow.toFixed(1)}× now</text>
 </svg>;
}

function RSRatioLines({data}){
 const [hov,setHov]=useState(null);
 const W=860,H=350,padL=38,padR=120,padT=14,padB=26;
 const n=data[0].series.length;
 let lo=1e9,hi=-1e9; data.forEach(d=>d.series.forEach(v=>{if(v<lo)lo=v;if(v>hi)hi=v;}));
 lo=Math.min(lo,98.5);hi=Math.max(hi,101.5);const pdv=(hi-lo)*0.08;lo-=pdv;hi+=pdv;
 const X=i=>padL+(i/(n-1))*(W-padL-padR);
 const Y=v=>padT+(H-padT-padB)*(1-(v-lo)/(hi-lo));
 const y100=Y(100);
 const ends=data.map(d=>({key:d.key,name:d.name,color:d.color,v:d.series[n-1],y:Y(d.series[n-1])})).sort((a,b)=>a.y-b.y);
 const gap=13; for(let i=1;i<ends.length;i++) if(ends[i].y-ends[i-1].y<gap) ends[i].y=ends[i-1].y+gap;
 const ticks=[94,96,98,100,102,104,106].filter(t=>t>=lo&&t<=hi);
 const pathOf=s=>{let d="";for(let i=0;i<n;i++)d+=(i?"L":"M")+X(i).toFixed(1)+" "+Y(s[i]).toFixed(1);return d;};
 return <svg viewBox={"0 0 "+W+" "+H} width="100%" style={{background:"var(--bg2)",border:"1px solid var(--line)",borderRadius:9,display:"block"}}>
   {ticks.map(t=>(<g key={t}><line x1={padL} y1={Y(t)} x2={W-padR} y2={Y(t)} stroke={t===100?"var(--line2)":"var(--line)"} strokeDasharray={t===100?"none":"2 4"}/><text x={padL-6} y={Y(t)+3} className="axt" textAnchor="end">{t}</text></g>))}
   <text x={W-padR-3} y={y100-4} className="axt" textAnchor="end" style={{fill:"var(--dim)"}}>= SPY (100)</text>
   {data.map(d=>{const on=hov===null||hov===d.key;return <path key={d.key} d={pathOf(d.series)} fill="none" stroke={d.color} strokeWidth={hov===d.key?2.6:1.5} strokeOpacity={on?1:0.1} onMouseEnter={()=>setHov(d.key)} onMouseLeave={()=>setHov(null)} style={{cursor:"pointer"}}/>;})}
   {ends.map(e=>{const on=hov===null||hov===e.key;return <g key={e.key} opacity={on?1:0.18} onMouseEnter={()=>setHov(e.key)} onMouseLeave={()=>setHov(null)} style={{cursor:"pointer"}}>
     <line x1={X(n-1)} y1={Y(e.v)} x2={W-padR+7} y2={e.y} stroke={e.color} strokeWidth={0.7} strokeOpacity={0.5}/>
     <text x={W-padR+10} y={e.y+3} fill={e.color} style={{fontSize:"9.5px",fontFamily:"var(--mono)"}}>{e.name} {e.v.toFixed(1)}</text>
   </g>;})}
   <text x={padL} y={H-7} className="axt" textAnchor="start">← {n} weeks</text>
   <text x={W-padR} y={H-7} className="axt" textAnchor="end">now</text>
 </svg>;
}

// ---------- synthetic as-of dates (staggered reporting + off-calendar fiscals) ----------
const QENDS=[
 {d:"2026-04-30",days:35},  // off-cal, freshest
 {d:"2026-03-31",days:65},  // calendar Q1 — the bulk
 {d:"2026-02-28",days:96},  // off-cal
 {d:"2026-01-31",days:124}, // off-cal / slow
 {d:"2025-12-31",days:155}, // a quarter behind (calendar Q4, hasn't reported Q1)
 {d:"2025-09-30",days:247}, // stale tail
];
function genAsof(stock){
 const r=lcg(((stock.id*0x9e3779b1)^0x51ed270b)>>>0), u=r(), big=stock.mktcap>40;
 let idx; if(big){idx=u<0.62?1:u<0.80?0:u<0.92?2:3;} else {idx=u<0.40?1:u<0.52?0:u<0.64?2:u<0.80?4:u<0.92?3:5;}
 return QENDS[idx];
}
function freshness(days){
 if(days<=95) return {c:"var(--grn)"};
 if(days<=160) return {c:"var(--amb)"};
 return {c:"var(--red)"};
}
function shortDate(s){const p=s.split("-");const mo=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+p[1]-1];return mo+" '"+p[0].slice(2);}

function bucketMeta(kind,key){if(kind==="sector"){const s=SECTORS[SECI[key]];return s?{name:s.n,color:s.c}:null;}if(kind==="theme"){const t=THEMES.find(x=>x.k===key);return t?{name:t.n,color:t.c}:null;}return null;}

function SoloRSLine({bucket}){
 const s=bucket.series, n=s.length;
 const W=860,H=300,padL=44,padR=66,padT=18,padB=28;
 let lo=Math.min.apply(null,s),hi=Math.max.apply(null,s); lo=Math.min(lo,99);hi=Math.max(hi,101); const pdv=(hi-lo)*0.14; lo-=pdv;hi+=pdv;
 const X=i=>padL+(i/(n-1))*(W-padL-padR);
 const Y=v=>padT+(H-padT-padB)*(1-(v-lo)/(hi-lo));
 const y100=Y(100), K=3;
 const lvl=s[n-1], slope4=lvl-s[Math.max(0,n-5)];
 const ticks=[]; for(let t=Math.ceil(lo);t<=Math.floor(hi);t++) if(t%2===0) ticks.push(t);
 return <svg viewBox={"0 0 "+W+" "+H} width="100%" style={{background:"var(--bg2)",border:"1px solid var(--line)",borderRadius:9,display:"block"}}>
   {ticks.map(t=>(<g key={t}><line x1={padL} y1={Y(t)} x2={W-padR} y2={Y(t)} stroke={t===100?"var(--line2)":"var(--line)"} strokeDasharray={t===100?"none":"2 4"}/><text x={padL-7} y={Y(t)+3} className="axt" textAnchor="end">{t}</text></g>))}
   <text x={W-padR-3} y={y100-4} className="axt" textAnchor="end" style={{fill:"var(--dim)"}}>= SPY (100)</text>
   <text x={padL} y={padT-4} className="axl" textAnchor="start">RS-RATIO vs SPY · 线色 = 斜率(↑绿/↓红)= momentum</text>
   {s.slice(1).map((v,j)=>{const i=j+1;const a=s[Math.max(0,i-K)];const up=v>=a;return <line key={i} x1={X(i-1)} y1={Y(s[i-1])} x2={X(i)} y2={Y(v)} stroke={up?"var(--grn)":"var(--red)"} strokeWidth={2.6} strokeLinecap="round"/>;})}
   <circle cx={X(n-1)} cy={Y(lvl)} r={4} fill={slope4>=0?"var(--grn)":"var(--red)"}/>
   <text x={W-padR+4} y={Y(lvl)+3} className="mono" style={{fill:bucket.color,fontSize:"11px"}}>{lvl.toFixed(1)}</text>
   <text x={padL} y={H-8} className="axt" textAnchor="start">← {n} weeks</text>
   <text x={W-padR} y={H-8} className="axt" textAnchor="end">now</text>
 </svg>;
}

export default function App(){
 const [tab,setTab]=useState("ocean");
 const [k,setK]=useState(0);
 const w=useMemo(()=>weights(k),[k]);
 // ocean state
 const [week,setWeek]=useState(WEEKS-1);
 const [colorBy,setColorBy]=useState("sector"); // sector | theme | quadrant
 const [activeTheme,setActiveTheme]=useState("AI");
 const [pinned,setPinned]=useState([]);
 // rotation state
 const [rotMode,setRotMode]=useState("sector");
 // valuation state
 const [valMetric,setValMetric]=useState("ps");
 const [valFilter,setValFilter]=useState("ALL");
 const [scope,setScope]=useState({kind:"all",key:null});
 // stock state
 const [stk,setStk]=useState(null);

 // leaders ranking
 const ranked=useMemo(()=>{
  const today=UNIVERSE.map(u=>({...u,sc:score(u.today,w)})).sort((a,b)=>b.sc-a.sc);
  const yest=UNIVERSE.map(u=>({id:u.id,sc:score(u.yest,w)})).sort((a,b)=>b.sc-a.sc);
  const yR=new Map(yest.map((x,i)=>[x.id,i+1]));
  return today.map((u,i)=>({...u,rank:i+1,yrank:yR.get(u.id),delta:yR.get(u.id)-(i+1)}));
 },[w]);
 const top20=ranked.slice(0,20);
 const yTop=useMemo(()=>new Set(ranked.filter(r=>r.yrank<=20).map(r=>r.id)),[ranked]);
 const orderKey=top20.map(r=>r.ticker).join();
 const setRow=useFlip(orderKey);

 // valuation table
 const valRows=useMemo(()=>{
  let rows=UNIVERSE.filter(u=>scope.kind==="all"?true:scope.kind==="theme"?u.themes.some(t=>t.k===scope.key):u.sec===scope.key);
  const get=(u)=>valMetric==="rule40"?u.val.rule40:valMetric==="growth"?u.val.growth*100:valMetric==="margin"?u.val.margin*100:u.val[valMetric];
  // pctile = common-vintage only: rank within the current-vintage cohort (as-of ≤95d); stale rows not ranked (§4.5)
  const vals=rows.filter(u=>genAsof(u).days<=95).map(get).filter(v=>v!=null).sort((a,b)=>a-b);
  const pct=(v)=>(v==null||!vals.length)?null:Math.round((vals.filter(x=>x<=v).length/vals.length)*100);
  rows=rows.map(u=>{const az=genAsof(u);const fresh=az.days<=95;return {...u,m:get(u),pctile:fresh?pct(get(u)):null,_stale:!fresh,sc:score(u.today,w)};});
  const asc=["pe","ps","evs","evebitda","peg"].includes(valMetric);
  rows.sort((a,b)=>{if(a.m==null)return 1;if(b.m==null)return -1;return asc?a.m-b.m:b.m-a.m;});
  return rows;
 },[valMetric,scope,w]);

 const stock=stk!=null?UNIVERSE[stk]:null;
 const stockList=useMemo(()=>[...UNIVERSE].sort((a,b)=>b.mktcap-a.mktcap).slice(0,120),[]);

 const flips=0;
 return (
  <div className="tt"><Style/><div className="grid-overlay"/>
   <div className="wrap">
    {/* header */}
    <header className="hdr">
     <div className="brand"><div className="logo">▚</div><div>
      <div className="title">US EQUITY MOMENTUM MONITOR</div>
      <div className="sub">one composite · five lenses · two scales · <span className="mock">MOCK / SYNTHETIC · US-LISTED ONLY</span></div>
     </div></div>
     <div className="asof"><span className="dot"/> EOD · AS OF <b>2026-05-29</b><div className="asof2">universe {N.toLocaleString()} · pinned {pinned.length}</div></div>
    </header>

    {/* controls */}
    <div className="ctrl">
     <div className="tabs">
      {[["ocean","Ocean"],["leaders","Discovery"],["rotation","Rotation"],["valuation","Valuation"],["stock","Stock"]].map(([id,l])=>(
       <button key={id} className={"tab"+(tab===id?" on":"")} onClick={()=>setTab(id)}>{l}</button>))}
     </div>
     <div className="knobwrap">
      <div className="knoblabels"><span className={k<.5?"kactive":""}>RELIABLE</span><span className="khint">confirmation ⟷ acceleration</span><span className={k>=.5?"kactive":""}>EARLY</span></div>
      <input className="knob" type="range" min={0} max={1} step={.01} value={k} onChange={e=>setK(parseFloat(e.target.value))}/>
      <div className="wbars">{WORDER.map(key=>(<div className="wb" key={key} title={WLABEL[key]}><div className="wbtrack"><div className="wbfill" style={{height:`${(w[key]/.45)*100}%`}}/></div><div className="wbl">{WLABEL[key]}</div></div>))}</div>
     </div>
    </div>

    {scope.kind!=="all" && (()=>{const m=bucketMeta(scope.kind,scope.key)||{name:scope.key,color:"var(--txt)"};return (
     <div className="scopebar"><span className="scopechip" style={{borderColor:m.color}}><span style={{width:9,height:9,borderRadius:"50%",background:m.color,display:"inline-block"}}/>Scope: <b style={{color:m.color}}>{m.name}</b><button className="scopex" onClick={()=>setScope({kind:"all",key:null})}>✕</button></span><span className="scopehint">filtering Discovery · Valuation · Rotation · Ocean</span></div>
    );})()}

    {/* ============ OCEAN ============ */}
    {tab==="ocean" && (
     <section className="panel">
      <div className="ptitle"><span>OCEAN — {N.toLocaleString()} US-listed names · explore wide</span>
       <span className="orow">
        <select value={colorBy} onChange={e=>setColorBy(e.target.value)} className="sel"><option value="sector">Color: Sector</option><option value="theme">Color: Theme</option><option value="quadrant">Color: Quadrant</option></select>
        {colorBy==="theme"&&<select value={activeTheme} onChange={e=>setActiveTheme(e.target.value)} className="sel">{THEMES.map(t=>(<option key={t.k} value={t.k}>{t.k}</option>))}</select>}
       </span>
      </div>
      <div style={{padding:"14px 16px 4px"}}>
       <Ocean week={week} colorBy={colorBy} pinned={pinned} setPinned={setPinned} activeTheme={activeTheme} scope={scope}/>
       <div className="scrub">
        <span className="sclab">WEEK {week+1}/{WEEKS}</span>
        <input className="knob scr" type="range" min={0} max={WEEKS-1} step={1} value={week} onChange={e=>setWeek(parseInt(e.target.value))}/>
        <span className="sclab dim">scrub time · no autoplay</span>
       </div>
       {pinned.length>0 && <div className="pinrow">tracking: {pinned.map(id=>(<span key={id} className="pinchip" onClick={()=>setPinned(p=>p.filter(x=>x!==id))}>{UNIVERSE[id].ticker} ✕</span>))}<span className="pinclear" onClick={()=>setPinned([])}>clear</span></div>}
      </div>
      <div className="foot">Static per snapshot — drag the scrubber to move through weeks. Click any point to <b>pin</b> it: pinned names draw an <b>arrow trail</b> through time. A trail moving <b>right + staying low</b> (into the green quadrant) = cheap and strengthening = the emerging leader you'd otherwise miss. This is the <b>explore</b> surface — act in Leaders.</div>
     </section>
    )}

    {/* ============ LEADERS ============ */}
    {tab==="leaders" && (
     <section className="panel">
      <div className="ptitle"><span>DISCOVERY — evidence cards · {N.toLocaleString()} universe → composite-triaged candidates</span><span className="ptags"><em className="tag">evidence-first · raw facts, not a score board</em></span></div>
      <div style={{padding:"14px 16px"}}>
       <div className="ecgrid">
        {ranked.filter(s=>scope.kind==="all"||(scope.kind==="theme"?s.themes.some(t=>t.k===scope.key):s.sec===scope.key)).slice(0,18).map(s=>(<EvidenceCard key={s.ticker} s={s} w={w} onOpen={()=>{setStk(s.id);setTab("stock");}}/>))}
       </div>
      </div>
      <div className="foot">每张卡 = 一只票的原始证据(price+volume+MA 图 + 摊开的硬数字),<b>不是</b>分数榜。composite 缩成角标(点 ▾ 看 5 个 component 原始值,无黑箱)。点卡片任意处 → 展开成 Stock 详情(collapsed→expanded)。旋钮调候选池排序;AI「why moving」待接入。</div>
     </section>
    )}

    {/* ============ ROTATION ============ */}
    {tab==="rotation" && (
     <section className="panel">
      <div className="ptitle"><span>{scope.kind==="all"?"ROTATION — sector RS-Ratio vs SPY · 高度=level,斜率=momentum":"ROTATION — "+((bucketMeta(scope.kind,scope.key)||{}).name||scope.key)+" · 单条放大 + 成员"}</span>
       {scope.kind==="all"
        ? <span className="orow"><button className={"seg"+(rotMode==="sector"?" on":"")} onClick={()=>setRotMode("sector")}>GICS Sectors</button><button className={"seg"+(rotMode==="theme"?" on":"")} onClick={()=>setRotMode("theme")}>Themes</button></span>
        : <span className="orow"><button className="seg" onClick={()=>setScope({kind:"all",key:null})}>← all {scope.kind==="theme"?"themes":"sectors"}</button></span>}
      </div>
      {scope.kind==="all" ? (
       <div>
        <RSRatioLines data={rotMode==="sector"?RS_SEC_LINES:RS_THEME_LINES}/>
        <div className="stbl2">
         <div className="sthead2"><div className="r">#</div><div>{rotMode==="sector"?"Sector":"Theme"}</div><div className="r">RS-Ratio</div><div className="r">Δ4w</div><div>state</div></div>
         {(rotMode==="sector"?RS_SEC_LINES:RS_THEME_LINES).map(s=>{const m=s.series.length;const lvl=s.series[m-1];const slope=lvl-s.series[Math.max(0,m-5)];return{s,lvl,slope};}).sort((a,b)=>b.lvl-a.lvl).map((o,i)=>{const q=o.lvl>=100?(o.slope>=0?"lead":"weak"):(o.slope>=0?"impr":"lag");return(
          <div key={o.s.key} className="srow2" onClick={()=>setScope({kind:rotMode==="sector"?"sector":"theme",key:o.s.key})} style={{cursor:"pointer"}}><div className="r mono dim">{i+1}</div><div className="tk" style={{color:o.s.color}}>{o.s.name}</div><div className="r mono">{o.lvl.toFixed(1)}</div><div className="r mono" style={{color:o.slope>=0?"var(--grn)":"var(--red)"}}>{o.slope>=0?"▲":"▼"}{Math.abs(o.slope).toFixed(1)}</div><div><span className="qchip" style={{color:QUAD[q].c,borderColor:QUAD[q].c}}>{QUAD[q].label}</span></div></div>);})}
        </div>
        <div className="foot">所有 sector 的 RS-Ratio(相对 SPY)叠一张图:<b>高度 = level</b>(&gt;100 跑赢)、<b>斜率 = momentum</b>(走平=中性)、线交叉 = leadership 换手。hover 高亮、<b>点一行 → 钻进该 bucket</b>。下表按 level 排序,<b>Δ4w = 斜率</b>。{rotMode==="theme"&&<span> Themes 多对多 &amp; point-in-time。</span>}相对图 —— 配 absolute regime 读。</div>
       </div>
      ) : (
       <div>
        {(()=>{const dl=(scope.kind==="theme"?RS_THEME_LINES:RS_SEC_LINES).find(b=>b.key===scope.key);return dl?<SoloRSLine bucket={dl}/>:null;})()}
        <div className="ptitle" style={{marginTop:14}}><span>成员 · top by composite</span><span className="ptags"><em className="tag">scope 收窄到该 bucket</em></span></div>
        <div className="ecgrid" style={{marginTop:10}}>
         {UNIVERSE.filter(u=>scope.kind==="theme"?u.themes.some(t=>t.k===scope.key):u.sec===scope.key).sort((a,b)=>score(b.today,w)-score(a.today,w)).slice(0,6).map(s=>(<EvidenceCard key={s.ticker} s={s} w={w} onOpen={()=>{setStk(s.id);setTab("stock");}}/>))}
        </div>
        <div className="foot">单条 RS-Ratio 放大:<b>高度=level、线色=斜率(↑绿/↓红)=momentum</b>(N=1 时 color 空出来给斜率)。下面是该 bucket 成员证据卡。点 ✕ 或「← all」清 scope 回总览。</div>
       </div>
      )}
     </section>
    )}

    {/* ============ VALUATION ============ */}
    {tab==="valuation" && (
     <section className="panel">
      <div className="ptitle"><span>VALUATION — cross-sectional · {N.toLocaleString()} names</span>
       <span className="orow">
        <select value={valMetric} onChange={e=>setValMetric(e.target.value)} className="sel"><option value="ps">sort: P/S</option><option value="pe">sort: P/E</option><option value="evs">sort: EV/S</option><option value="evebitda">sort: EV/EBITDA</option><option value="peg">sort: PEG</option><option value="rule40">sort: Rule of 40</option><option value="growth">sort: Growth %</option><option value="margin">sort: Margin %</option></select>
        <select value={scope.kind==="all"?"ALL":scope.kind==="theme"?("T:"+scope.key):scope.key} onChange={e=>{const v=e.target.value;v==="ALL"?setScope({kind:"all",key:null}):v.startsWith("T:")?setScope({kind:"theme",key:v.slice(2)}):setScope({kind:"sector",key:v});}} className="sel"><option value="ALL">all</option>{SECTORS.map(s=>(<option key={s.k} value={s.k}>{s.n}</option>))}{THEMES.map(t=>(<option key={t.k} value={"T:"+t.k}>◆ {t.k}</option>))}</select>
       </span></div>
      <div className="tbl">
       <div className="thead v-cols"><div>Ticker</div><div>Sector</div><div>As-of</div><div className="r">P/E</div><div className="r">P/S</div><div className="r">EV/S</div><div className="r">EV/EBITDA</div><div className="r">PEG</div><div className="r">Grw%</div><div className="r">Mgn%</div><div className="r">R40</div><div className="r">pctile</div></div>
       <div style={{maxHeight:340,overflowY:"auto"}}>{valRows.slice(0,50).map(r=>{const az=genAsof(r),fr=freshness(az.days);return(
        <div key={r.ticker} className="trow v-cols" onClick={()=>{setStk(r.id);setTab("stock");}} style={{cursor:"pointer",borderLeft:"3px solid "+fr.c,opacity:az.days>160?0.6:1}}>
         <div className="tk">{r.ticker}</div><div className="dim">{SECTORS[SECI[r.sec]].n}</div>
         <div><span style={{color:fr.c}}>●</span> <span className="mono" style={{fontSize:"10.5px"}}>{shortDate(az.d)}</span></div>
         <div className="r mono">{r.val.pe==null?"—":r.val.pe.toFixed(0)}</div><div className="r mono">{r.val.ps.toFixed(1)}</div>
         <div className="r mono">{r.val.evs.toFixed(1)}</div><div className="r mono">{r.val.evebitda.toFixed(0)}</div><div className="r mono">{r.val.peg.toFixed(1)}</div>
         <div className="r mono" style={{color:r.val.growth>.25?"var(--grn)":"var(--dim)"}}>{(r.val.growth*100).toFixed(0)}</div>
         <div className="r mono" style={{color:r.val.margin<0?"var(--red)":"var(--txt)"}}>{(r.val.margin*100).toFixed(0)}</div>
         <div className="r mono" style={{color:r.val.rule40>=40?"var(--grn)":"var(--dim)"}}>{r.val.rule40.toFixed(0)}</div>
         <div className="r mono">{r._stale?<span className="dim" style={{fontSize:"9.5px"}} title="stale vintage — not ranked">vint</span>:<b>{r.pctile==null?"—":r.pctile}</b>}</div>
        </div>);})}</div>
      </div>
      <div className="foot">Showing 50 of {valRows.length} filtered. <b>As-of</b> = 该票最新 trailing-4Q 的季末日(合成,模拟报告错开 + off-calendar 财年)。●<span style={{color:"var(--grn)"}}>绿</span>=已报当期 / <span style={{color:"var(--amb)"}}>黄</span>=落后一季 / <span style={{color:"var(--red)"}}>红</span>=落后逾一季(行变暗)——黄/红与绿<b>不在同一 as-of 日</b>,横比 P/S 等要打折;即便绿类也固有滞后 ~40–90 天(全体如此)。<b>pctile</b> = 只在 <b>current-vintage cohort</b>(as-of ≤~95 天)内排名;stale 行(黄/红)显示 <b>vint</b> = 未进排名(不拿陈旧 vintage 和新鲜的比)。点行 → Stock。</div>
     </section>
    )}

    {/* ============ STOCK ============ */}
    {tab==="stock" && (
     <section className="panel">
      <div className="ptitle"><span>STOCK DETAIL</span>
       <select value={stk??""} onChange={e=>setStk(e.target.value===""?null:parseInt(e.target.value))} className="sel">
        <option value="">select ticker…</option>{stockList.map(s=>(<option key={s.id} value={s.id}>{s.ticker} · {SECTORS[SECI[s.sec]].n}</option>))}</select>
      </div>
      {!stock ? <div className="foot" style={{padding:"40px 16px",textAlign:"center"}}>Pick a ticker — or click any row in Leaders / Valuation / pin in Ocean.</div> : (
       <div className="sd">
        <div className="sd-head">
         <div><div className="sd-tk">{stock.ticker}</div><div className="dim">{SECTORS[SECI[stock.sec]].n} · ${stock.mktcap.toFixed(1)}B mkt cap</div>
          <div className="sd-themes">{stock.themes.length?stock.themes.map(t=>(<span key={t.k} className="tchip" style={{borderColor:THEMEC[t.k],color:THEMEC[t.k]}}>{THEMES.find(x=>x.k===t.k).n} · {(t.w*100).toFixed(0)}%</span>)):<span className="dim">no theme membership</span>}</div>
         </div>
         <div className="sd-score"><div className="dim" style={{fontSize:9,letterSpacing:".08em"}}>COMPOSITE</div><div style={{fontSize:30,fontWeight:700,color:scoreColor(score(stock.today,w))}}>{score(stock.today,w).toFixed(0)}</div></div>
        </div>
        <div className="sd-chart"><StockChartStack stock={stock}/></div>
        <div className="sd-grid">
         <div className="sd-card"><div className="sd-cl">P/S</div><div className="sd-big">{stock.val.ps.toFixed(1)}</div></div>
         <div className="sd-card"><div className="sd-cl">EV/S</div><div className="sd-big">{stock.val.evs.toFixed(1)}</div></div>
         <div className="sd-card"><div className="sd-cl">EV/EBITDA</div><div className="sd-big">{stock.val.evebitda.toFixed(0)}</div></div>
         <div className="sd-card"><div className="sd-cl">P/E</div><div className="sd-big">{stock.val.pe==null?"—":stock.val.pe.toFixed(0)}</div></div>
         <div className="sd-card"><div className="sd-cl">Rev growth</div><div className="sd-big" style={{color:stock.val.growth>.25?"var(--grn)":"var(--txt)"}}>{(stock.val.growth*100).toFixed(0)}%</div></div>
         <div className="sd-card"><div className="sd-cl">Rule of 40</div><div className="sd-big" style={{color:stock.val.rule40>=40?"var(--grn)":"var(--txt)"}}>{stock.val.rule40.toFixed(0)}</div></div>
        </div>
        <div className="sd-comp">
         <div className="sd-cl">composite components (current)</div>
         <div className="sd-bars">{WORDER.map(key=>{const v=key==="high"?(stock.today.high-.5)/.5:stock.today[key];return(
          <div key={key} className="sd-bar"><div className="sd-bn">{WLABEL[key]}</div><Bar v={v*100} color="var(--blu)" w={120}/><div className="sd-bv">{pInt(v)}</div></div>);})}</div>
        </div>
       </div>)}
      <div className="foot">Per-name drill-down(= evidence-card 的 expanded 态)。K 线 + 成交量 + <b>季度营收</b> + <b>P/S over time</b> 共用同一时间轴对齐(季度网格贯穿):价格涨而营收平 → P/S 在扩(变贵无基本面);价↑且营收↑ → 赚到这波。合成数据。</div>
     </section>
    )}

    <div className="legaloot">Prototype for layout/interaction only. Deterministic synthetic data — no live feed, no signal, US-listed scope. Real pipeline (GitHub Actions cron · Stooq + Nasdaq screener + SEC EDGAR · DuckDB · Cloudflare Pages static) is built in code mode.</div>
   </div>
  </div>
 );
}

function Style(){return <style>{`
@import url('https://fonts.googleapis.com/css2?family=Saira+Semi+Condensed:wght@500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
.tt{--bg:#080b11;--bg2:#0c1117;--panel:#0e141d;--line:#1b232e;--line2:#2a3441;--txt:#e9eef5;--dim:#8593a3;--dim2:#56616f;--grn:#2ec07a;--red:#ff5d57;--amb:#e0a02e;--blu:#5197ff;--accent:#2ec07a;--mono:'IBM Plex Mono',ui-monospace,monospace;--disp:'Saira Semi Condensed',system-ui,sans-serif;position:relative;color:var(--txt);font-family:var(--mono);background:radial-gradient(1100px 560px at 82% -12%,rgba(46,192,122,.07),transparent 60%),radial-gradient(820px 460px at -8% 112%,rgba(81,151,255,.06),transparent 60%),var(--bg);border-radius:12px;overflow:hidden;font-size:12.5px;line-height:1.45;-webkit-font-smoothing:antialiased;}
.tt *{box-sizing:border-box;}
.grid-overlay{position:absolute;inset:0;pointer-events:none;background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);background-size:34px 34px;-webkit-mask-image:radial-gradient(120% 90% at 50% 0%,#000 30%,transparent 80%);mask-image:radial-gradient(120% 90% at 50% 0%,#000 30%,transparent 80%);opacity:.16;}
.wrap{position:relative;padding:18px 20px 16px;}
.hdr{display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:14px;border-bottom:1px solid var(--line);}
.brand{display:flex;gap:12px;align-items:center;}
.logo{width:34px;height:34px;display:grid;place-items:center;border:1px solid var(--line2);border-radius:7px;color:var(--accent);font-size:18px;background:linear-gradient(180deg,rgba(46,192,122,.12),transparent);}
.title{font-family:var(--disp);font-weight:800;font-size:20px;letter-spacing:.07em;line-height:1;}
.sub{color:var(--dim);font-size:10.5px;letter-spacing:.04em;margin-top:5px;}
.mock{color:var(--amb);font-weight:600;letter-spacing:.05em;}
.asof{text-align:right;font-size:10.5px;color:var(--dim);letter-spacing:.06em;}.asof b{color:var(--txt);}.asof2{color:var(--dim2);margin-top:4px;font-size:10px;}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--grn);margin-right:6px;animation:pulse 2.2s infinite;vertical-align:middle;}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(46,192,122,.5)}70%{box-shadow:0 0 0 6px rgba(46,192,122,0)}100%{box-shadow:0 0 0 0 rgba(46,192,122,0)}}
.ctrl{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:14px 0;flex-wrap:wrap;}
.tabs{display:flex;gap:4px;background:var(--bg2);border:1px solid var(--line);border-radius:9px;padding:4px;}
.tab{font-family:var(--disp);font-weight:600;letter-spacing:.05em;font-size:12.5px;color:var(--dim);background:none;border:0;padding:7px 13px;border-radius:6px;cursor:pointer;transition:.15s;}
.tab:hover{color:var(--txt);}.tab.on{color:var(--bg);background:var(--accent);}
.knobwrap{display:flex;flex-direction:column;gap:7px;min-width:320px;flex:1;max-width:420px;}
.knoblabels{display:flex;justify-content:space-between;align-items:center;font-family:var(--disp);font-weight:600;letter-spacing:.08em;font-size:10.5px;color:var(--dim2);}
.kactive{color:var(--accent);}.khint{color:var(--dim2);font-family:var(--mono);font-size:9px;}
.knob{-webkit-appearance:none;appearance:none;height:4px;border-radius:3px;background:linear-gradient(90deg,var(--blu),var(--grn));outline:none;cursor:pointer;}
.knob::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;background:var(--txt);border:3px solid var(--bg);box-shadow:0 0 0 1px var(--line2);cursor:grab;}
.knob::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:var(--txt);border:3px solid var(--bg);cursor:grab;}
.wbars{display:flex;gap:10px;align-items:flex-end;}
.wb{display:flex;flex-direction:column;align-items:center;gap:4px;flex:1;}
.wbtrack{width:100%;height:24px;background:var(--bg2);border:1px solid var(--line);border-radius:4px;display:flex;align-items:flex-end;overflow:hidden;}
.wbfill{width:100%;background:linear-gradient(180deg,var(--accent),var(--grn));transition:height .25s;}
.wbl{font-size:8.5px;color:var(--dim2);}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:11px;overflow:hidden;}
.ptitle{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:11px 16px;border-bottom:1px solid var(--line);font-family:var(--disp);font-weight:600;letter-spacing:.05em;font-size:12.5px;color:var(--dim);flex-wrap:wrap;}
.orow{display:flex;gap:7px;align-items:center;}
.sel{font-family:var(--mono);font-size:10.5px;color:var(--txt);background:var(--bg2);border:1px solid var(--line2);border-radius:6px;padding:5px 8px;cursor:pointer;}
.seg{font-family:var(--disp);font-weight:600;font-size:11px;letter-spacing:.04em;color:var(--dim);background:var(--bg2);border:1px solid var(--line2);border-radius:6px;padding:5px 11px;cursor:pointer;}
.seg.on{color:var(--bg);background:var(--accent);border-color:var(--accent);}
.ptags{display:flex;gap:7px;}.tag{font-style:normal;font-size:9.5px;color:var(--dim);border:1px solid var(--line2);padding:3px 8px;border-radius:20px;}
.tbl{width:100%;}
.thead{display:grid;gap:8px;padding:8px 16px;color:var(--dim2);font-size:9.5px;letter-spacing:.07em;text-transform:uppercase;border-bottom:1px solid var(--line);}
.trow{display:grid;gap:8px;padding:9px 16px;border-bottom:1px solid rgba(27,35,46,.6);align-items:center;transition:background .2s;}
.trow:hover{background:var(--bg2);}
.l-cols{grid-template-columns:.4fr .55fr 1.1fr 1.3fr 1fr .5fr .5fr .5fr .5fr .5fr;}
.v-cols{grid-template-columns:1fr 1.1fr .95fr .55fr .55fr .55fr .8fr .5fr .5fr .5fr .5fr .6fr;}
.r{text-align:right;justify-self:end;}.mono{font-variant-numeric:tabular-nums;}.dim{color:var(--dim);}
.tk{font-weight:600;letter-spacing:.03em;display:flex;align-items:center;gap:6px;}.rank{font-weight:700;}
.pill{font-size:8px;font-weight:700;letter-spacing:.05em;padding:1px 5px;border-radius:4px;}
.pill.grn{background:rgba(46,192,122,.16);color:var(--grn);}.pill.blu{background:rgba(81,151,255,.16);color:var(--blu);}
.mv{font-size:10px;}.mv.up{color:var(--grn);}.mv.dn{color:var(--red);}.mv.flat{color:var(--dim2);}
.foot{padding:10px 16px;font-size:10px;color:var(--dim);border-top:1px solid var(--line);background:var(--bg2);}.foot b{color:var(--txt);}
.legaloot{margin-top:12px;font-size:9.5px;color:var(--dim2);text-align:center;}
/* ocean */
.oax-x{position:absolute;right:18px;bottom:6px;font-family:var(--disp);font-size:10px;letter-spacing:.04em;color:var(--dim);}
.oax-y{position:absolute;left:8px;top:50%;transform:rotate(-90deg);transform-origin:left;font-family:var(--disp);font-size:10px;letter-spacing:.04em;color:var(--dim);white-space:nowrap;}
.oquad{position:absolute;right:30px;bottom:48px;font-size:9px;letter-spacing:.05em;color:var(--grn);opacity:.7;}
.otip{position:absolute;top:14px;left:14px;background:rgba(8,11,17,.95);border:1px solid var(--line2);border-radius:8px;padding:9px 11px;font-size:11px;pointer-events:none;min-width:150px;box-shadow:0 6px 20px rgba(0,0,0,.5);}
.otip b{font-size:13px;}.otrow{display:flex;justify-content:space-between;gap:14px;color:var(--dim);margin-top:3px;}.otrow b{color:var(--txt);}
.otags{display:flex;gap:6px;margin-top:6px;font-size:9px;font-weight:700;}.ohint{margin-top:6px;color:var(--dim2);font-size:8.5px;}
.scrub{display:flex;align-items:center;gap:12px;margin-top:10px;}
.scr{flex:1;background:var(--line2);}.scr::-webkit-slider-thumb{background:var(--accent);}
.sclab{font-family:var(--disp);font-weight:600;font-size:10px;letter-spacing:.06em;color:var(--txt);white-space:nowrap;}
.pinrow{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:10px;font-size:10px;color:var(--dim);}
.pinchip{font-size:10px;color:var(--txt);background:var(--bg2);border:1px solid var(--line2);border-radius:20px;padding:2px 9px;cursor:pointer;}
.pinclear{color:var(--dim2);cursor:pointer;text-decoration:underline;}
/* rrg */
.rrg-layout{display:grid;grid-template-columns:1.3fr .9fr;gap:14px;padding:14px 16px;}
.axt{fill:var(--dim2);font-size:9px;font-family:var(--mono);}.qlab{font-family:var(--disp);font-weight:700;font-size:10px;letter-spacing:.1em;opacity:.7;}.rlab{font-family:var(--mono);font-weight:600;font-size:10px;}
.rrg-side{display:flex;flex-direction:column;gap:12px;}
.legend{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;padding:10px 12px;background:var(--bg2);border:1px solid var(--line);border-radius:8px;}
.lg{display:flex;align-items:center;gap:7px;font-size:9.5px;letter-spacing:.05em;color:var(--dim);}.sw{width:9px;height:9px;border-radius:2px;}
.stbl{border:1px solid var(--line);border-radius:8px;overflow:hidden;}
.sthead{display:grid;grid-template-columns:1.6fr .7fr .7fr 1.1fr;gap:6px;padding:7px 11px;background:var(--bg2);color:var(--dim2);font-size:9px;letter-spacing:.06em;text-transform:uppercase;border-bottom:1px solid var(--line);}
.srow{display:grid;grid-template-columns:1.6fr .7fr .7fr 1.1fr;gap:6px;padding:7px 11px;align-items:center;border-bottom:1px solid rgba(27,35,46,.6);font-size:10.5px;}.srow:last-child{border-bottom:0;}
.qchip{font-size:8px;font-weight:600;letter-spacing:.04em;border:1px solid;padding:1px 6px;border-radius:20px;}
/* stock detail */
.sd{padding:16px;}
.sd-head{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:14px;}
.sd-tk{font-family:var(--disp);font-weight:800;font-size:26px;letter-spacing:.04em;}
.sd-themes{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;}.tchip{font-size:9.5px;border:1px solid;border-radius:20px;padding:2px 8px;}
.sd-score{text-align:right;}
.sd-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;}
.sd-card{background:var(--bg2);border:1px solid var(--line);border-radius:8px;padding:11px 13px;}
.sd-cl{font-size:9px;letter-spacing:.07em;text-transform:uppercase;color:var(--dim2);margin-bottom:7px;}
.sd-big{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;}
.sd-comp{background:var(--bg2);border:1px solid var(--line);border-radius:8px;padding:12px 14px;}
.sd-chart{background:var(--bg2);border:1px solid var(--line);border-radius:8px;padding:10px 12px 4px;margin-bottom:12px;}
.axl{fill:var(--dim);font-size:8.5px;letter-spacing:.06em;font-family:var(--disp);}
.stbl2{margin-top:12px;border:1px solid var(--line);border-radius:8px;overflow:hidden;}
.sthead2,.srow2{display:grid;grid-template-columns:34px 1.5fr .8fr .8fr 1fr;gap:8px;padding:7px 13px;align-items:center;}
.sthead2{background:var(--panel);font-family:var(--disp);font-size:10px;letter-spacing:.05em;color:var(--dim);text-transform:uppercase;}
.srow2{border-top:1px solid var(--line);font-size:12px;}
.srow2 .tk{font-family:var(--disp);font-weight:600;}
.srow2:hover{background:var(--panel);}
.scopebar{display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap;}
.scopechip{display:inline-flex;align-items:center;gap:7px;background:var(--bg2);border:1px solid var(--line2);border-radius:20px;padding:5px 6px 5px 13px;font-size:12px;font-family:var(--disp);letter-spacing:.03em;}
.scopex{margin-left:3px;width:20px;height:20px;border-radius:50%;border:none;background:var(--panel);color:var(--dim);cursor:pointer;font-size:11px;line-height:1;}
.scopex:hover{background:var(--red);color:#fff;}
.scopehint{font-size:10px;color:var(--dim2);letter-spacing:.04em;}
.sd-bars{display:flex;flex-direction:column;gap:8px;margin-top:8px;}
.sd-bar{display:grid;grid-template-columns:60px 1fr 36px;gap:10px;align-items:center;}
.sd-bn{font-size:10px;color:var(--dim);}.sd-bv{font-size:11px;text-align:right;font-variant-numeric:tabular-nums;}
.reveal{animation:fadeUp .5s both;}@keyframes fadeUp{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:none;}}
.ecgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;}
.ecard{background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:12px 13px;cursor:pointer;transition:border-color .15s;}
.ecard:hover{border-color:var(--line2);}
.ec-head{display:flex;justify-content:space-between;align-items:center;}
.ec-tk{font-family:var(--disp);font-weight:700;font-size:17px;letter-spacing:.03em;}
.ec-sec{font-family:var(--mono);font-weight:400;font-size:10px;color:var(--dim);letter-spacing:0;}
.ec-badge{font-family:var(--mono);font-size:13px;font-weight:700;background:var(--panel);border:1px solid var(--line2);border-radius:6px;padding:2px 8px;cursor:pointer;}
.ec-badge i{font-style:normal;font-size:9px;color:var(--dim2);}
.ec-themes{display:flex;gap:6px;margin-top:5px;font-size:9px;font-weight:700;}
.ec-comp{margin-top:8px;padding:8px 10px;background:var(--panel);border:1px solid var(--line);border-radius:7px;}
.ec-crow{display:grid;grid-template-columns:46px 1fr 28px;gap:8px;align-items:center;font-size:10px;color:var(--dim);margin:3px 0;}
.ec-crow b{color:var(--txt);text-align:right;font-variant-numeric:tabular-nums;}
.ec-note{font-size:8.5px;color:var(--dim2);margin-top:5px;}
.ec-chart{margin:8px 0 6px;}
.ec-fields{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;padding-top:8px;border-top:1px solid var(--line);}
.ec-f{display:flex;flex-direction:column;gap:2px;}
.ec-f span{font-size:8.5px;color:var(--dim2);letter-spacing:.03em;}
.ec-f b{font-size:12px;font-variant-numeric:tabular-nums;}
.ec-why{margin-top:8px;font-size:9.5px;}
.ec-wl{font-family:var(--disp);font-weight:600;letter-spacing:.05em;color:var(--dim);}
@media (max-width:900px){.ecgrid{grid-template-columns:1fr;}}
@media (max-width:760px){.rrg-layout{grid-template-columns:1fr;}.knobwrap{min-width:100%;max-width:100%;}.sd-grid{grid-template-columns:repeat(2,1fr);}.v-cols{grid-template-columns:1fr .8fr .5fr .5fr .5fr .5fr;}.v-cols>div:nth-child(n+7){display:none;}}
`}</style>;}
