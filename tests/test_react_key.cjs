// dev-20261128-0200 1c 뉴스 반응 지표(reactKey) — 실행: node tests/test_react_key.cjs
const fs=require("fs"),vm=require("vm"),assert=require("assert/strict");
const src=fs.readFileSync(require("path").join(__dirname, "..", "news.js"),"utf8");
const a=src.indexOf("  // 11/28 운영자 \"추천대로\": 엔비디아"), b=src.indexOf("  const H = 24;");
const c=src.indexOf("  // 11/28 운영자 \"추천대로\": 뉴스 분야별"), d=src.indexOf("  window.trlReactKey = reactKey;");
const ctx={window:{},Date,Object}; vm.createContext(ctx);
vm.runInContext(src.slice(a,b)+src.slice(c,d)+";globalThis.rk=reactKey;",ctx);
const us=Date.parse("2026-11-27T23:30:00+09:00"), kr=Date.parse("2026-11-27T10:30:00+09:00");
const k=(tags,text,ts)=>ctx.rk({tags,text,ts}).code;
assert.equal(k(["중동·유가","연준·금리"],"",us),"WTI");
assert.equal(k(["연준·금리"],"파월",us),"US10Y");
assert.equal(k(["환율"],"원/달러 1,400원",kr),"USDKRW");
assert.equal(k(["반도체"],"엔비디아 실적 발표",us),"NVDA");
assert.equal(k(["반도체"],"SK하이닉스 HBM 공급",us),"SKHX");
assert.equal(k(["반도체"],"마이크론 실적 호조",us),"NVDA");
assert.equal(k(["AI·빅테크"],"엔비디아 급등",kr),"SKHX");
assert.equal(k(["한국"],"코스피 외국인 순매수",kr),"K200");
assert.equal(k(["지수"],"뉴욕증시",us),"NQ");
console.log("reactKey ok");
