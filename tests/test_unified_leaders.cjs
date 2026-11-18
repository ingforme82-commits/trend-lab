const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const source=fs.readFileSync("news.js","utf8"),start=source.indexOf("const risingLeader"),end=source.indexOf("function drawSectors()",start);
assert.ok(start>0 && end>start);
const row=(sym)=>({sym,name:sym,px:10,chg:2});
const ctx={spot:[
 {id:"SEMI",name:"반도체 종목군",market:"미국",chg:3,members:[row("A"),row("B")],kw:"칩"},
 {id:"QUANTUM",name:"양자컴퓨팅",market:"미국",chg:-8,members:[{...row("Q"),chg:-8}]},
 {id:"SOLAR",name:"태양광",market:"미국",chg:4,members:[row("S"),row("T")]},
 {id:"A",name:"대형주A",market:"미국",chg:2,px:10},
 {id:"ASIA",name:"한국·일본",pin:true,market:"한국·일본",chg:5,members:[]}],
 leaders:{us:{at:1000,open:false,industry:[
  {name:"반도체",chg:2,n:4,up:3,score:80,rows:[row("A"),row("B"),row("C"),row("D")]},
  {name:"하락 업종",chg:-3,n:4,up:0,score:90,rows:[row("Q")]},
  {name:"대형주 편중",chg:1,n:10,up:2,score:100,rows:[row("X")]}]}},
 news:[{text:"칩 상승 관련 보도",ts:1000}],mode:()=>"us",ldTab:null,ldOpen:"반도체",
 sortRows:x=>x,usd:()=>"-",esc:x=>String(x),sg2:x=>x,pct:x=>x,hm:()=>"12:00",sth:()=>"",sortChips:()=>""};
vm.createContext(ctx);
vm.runInContext(source.slice(start,end)+"\nglobalThis.groups=leaderGroups;globalThis.render=leadersHtml;",ctx);
const original=JSON.stringify(ctx.leaders);
const groups=ctx.groups(ctx.leaders.us,"industry","us");
assert.deepEqual(Array.from(groups,g=>g.name),["반도체","태양광"]);
assert.equal(groups[0].relatedPatterns.length,1);
assert.equal(JSON.stringify(ctx.leaders),original);
const html=ctx.render();
assert.equal((html.match(/오늘의 주도 섹터·종목/g)||[]).length,1);
assert.ok(!html.includes("오늘의 주요 종목군")&&!html.includes("양자컴퓨팅")&&!html.includes("하락 업종")&&!html.includes("대형주 편중"));
assert.ok(html.includes("칩 상승 관련 보도"));
ctx.spot=[];ctx.leaders.us.industry=[{name:"모두하락",chg:-10,n:4,up:0,rows:[]}];
assert.ok(ctx.render().includes("현재 기준을 충족하는 상승 주도 섹터가 없습니다"));
console.log("상승/확산 기준·음수 제외·종목군 중복 통합·관련 뉴스·빈 후보: PASS");
