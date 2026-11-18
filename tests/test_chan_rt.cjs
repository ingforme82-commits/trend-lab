const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const source = fs.readFileSync(path.join(__dirname, "..", "news.js"), "utf8");
const start = source.indexOf("const CH_RT");
const end = source.indexOf("let chanRtSig", start);
const ctx = {Date, Math, Number, window: {}};
vm.createContext(ctx);
vm.runInContext(source.slice(start, end) + "\nglobalThis.live = chLive;", ctx);
const rows = Array.from({length: 10}, (_, i) => ["11/" + String(i + 1).padStart(2, "0"), 100, 102, 98, 100]);
const it = {code: "005930", live: true, rows, px: 100, chg: 0, up_now: 103, lo_now: 90, up_next: 102.5, ma5: 100, gap_next: 2.5, channel_valid: true, state: "상단 근접"};
// 실시간 값 없음 → 그대로
assert.equal(ctx.live(it), it);
// 신선한 실시간 체결 → 마지막 봉·5일선·상태 갱신
ctx.window.trlRt = {q: {SMSN: {px: 110, chg: 10, at: Date.now()}}};
const o = ctx.live(it);
assert.deepEqual(o.rows[9].slice(1), [100, 110, 98, 110]);
assert.equal(o.px, 110);
assert.equal(o.ma5, 102);
assert.equal(o.state, "돌파 시도(장중)");
assert.deepEqual(it.rows[9].slice(1), [100, 102, 98, 100]);   // 원본은 그대로
// 오래된 값(15초 넘음)·진행 중 봉 아님 → 쓰지 않음
ctx.window.trlRt = {q: {SMSN: {px: 110, chg: 10, at: Date.now() - 20000}}};
assert.equal(ctx.live(it), it);
ctx.window.trlRt = {q: {SMSN: {px: 110, chg: 10, at: Date.now()}}};
assert.equal(ctx.live({...it, live: false}).px, 100);
console.log("chan rt ok");
