const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const source=fs.readFileSync("news.js","utf8");
const start=source.indexOf("const REACT_COLS");
const end=source.indexOf("/* ── 해외 지수",start);
assert.ok(start>0&&end>start);
const elements=new Map();
const q=id=>{if(!elements.has(id))elements.set(id,{});return elements.get(id);};
const now=Date.now();
const moves=Array.from({length:6},(_,i)=>({id:"m"+i,grp:"g"+i,start:now-(i+1)*60000,end:now-i*60000,
 name:"나스닥100",asset:"NQ",move:-1-i,unit:"pct",ratio:6-i,from:100,to:99-i,items:[]}));
moves.reverse(); // Input order must not determine the newest three.
const context={q,moves,news:[],esc:String,hm:v=>String(v),cls:()=>"down",fmtMove:m=>String(m.move),noteFor:()=>null};
vm.createContext(context);
vm.runInContext(source.slice(start,end)+"\nglobalThis.draw=drawMoves;",context);
context.draw();
const html=elements.get("#moveList").innerHTML;
assert.equal((html.match(/<article class="mv"/g)||[]).length,3);
assert.ok(html.includes('data-start="'+(now-60000)+'"'));
assert.ok(!html.includes('data-start="'+(now-240000)+'"'));
const table=elements.get("#moveReact").innerHTML;
assert.equal((table.match(/<tr>/g)||[]).length,4); // header plus three groups
assert.ok(table.includes("最新")===false && table.includes("최신 3개"));
assert.equal(moves.length,6);
console.log("변곡점 카드·지수 반응표 최신 3개, 원본 기록 보존: PASS");
