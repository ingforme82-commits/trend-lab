const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const source=fs.readFileSync("app.js","utf8");
const start=source.indexOf("async function loadEarnings()");
const end=source.indexOf("/* ───────── 2-1.",start);
assert.ok(start>0&&end>start);
const cps=JSON.parse(fs.readFileSync("data/checkpoints.json","utf8"));
assert.equal(cps.filter(x=>x.kind==="ipo"&&x.sym==="ANT").length,2);
const h=JSON.parse(fs.readFileSync("data/headline.json","utf8"));
const ant=h.items.find(x=>x.tag==="🤖 앤트로픽 IPO");
assert.ok(ant);
assert.equal(ant.main,true);
assert.ok(ant.points.some(p=>p.includes("83달러")&&p.includes("확정"))); // 11/18 공모가 확정 반영
assert.ok(ant.points.some(p=>p.includes("첫 체결")||(p.includes("선물 계약")&&p.includes("시초가와 다를 수")))); // 상장 전: 선물 ≠ 주식 / 11/19 상장 뒤: 실제 첫 체결가
async function check(fail){
 const els=new Map();const q=k=>{if(!els.has(k))els.set(k,{});return els.get(k);};
 const context={console,Promise,Date,DOW:["일","월","화","수","목","금","토"],
  KST:()=>new Date("2026-11-18T20:00:00Z"),ymd:d=>d.toISOString().slice(0,10),$:q,
  esc:s=>String(s??"").replaceAll("&","&amp;").replaceAll("<","&lt;"),
  fetch:async url=>({ok:!(fail&&url.includes(fail)),json:async()=>url.includes("checkpoints")?cps:
    {updated:"fixture",items:[{date:"2026-11-17",kst_date:"2026-11-18",name:"엔비디아",sym:"NVDA",sector:"반도체",hour:"장마감 뒤",kst:"11/18 06시 이후",check:"확정"}]}})};
 vm.createContext(context);
 vm.runInContext(source.slice(start,end)+"\nglobalThis.run=loadEarnings;",context);
 await context.run();return els;
}
(async()=>{
 let els=await check();let html=els.get("#earnList").innerHTML;
 assert.ok(html.includes("앤트로픽")&&html.includes("NVDA"));
 assert.ok(html.indexOf("앤트로픽")<html.indexOf("NVDA"));
 assert.ok(html.includes("첫 체결 시각")||html.includes("첫 거래"));
 assert.ok(!html.includes("예상 EPS $70")); // IPO price is not earnings.
 els=await check("earnings.json");
 assert.ok(els.get("#earnList").innerHTML.includes("앤트로픽"));
 assert.equal(els.get("#earnings").hidden,false);
 els=await check("checkpoints.json");
 assert.ok(els.get("#earnList").innerHTML.includes("NVDA"));
 console.log("실적·IPO 병합, IPO 우선 표시, 원천 실패 격리: PASS");
})().catch(e=>{console.error(e);process.exitCode=1;});
