const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const start = source.indexOf('const RT_NAMES =');
const end = source.indexOf('// 📊 출처 점수판',start);
test('old quote loses live label even when connection fails', async () => {
  const label = {textContent:'실시간 체결'};
  const element = {dataset:{rtAt:'1'}, querySelector:()=>label};
  const context = {Date,Number,Object,String,Event,performance,AbortSignal,
    window:{trlRtUrl:'https://sample.trycloudflare.com',dispatchEvent(){}},
    document:{hidden:false,querySelectorAll:()=>[element]},
    fetch:async()=>{throw Error('offline');},setInterval(){}};
  vm.runInNewContext(source.slice(start,end)+';globalThis.loadForTest=loadRt;',context);
  await context.loadForTest();
  assert.equal(label.textContent,'수신 지연 · 마지막 값');
  assert.equal(context.window.trlRtHealth.ok,false);
});
