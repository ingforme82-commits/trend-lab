// node tests/windows.test.js — news.js 의 pxAt·windows 코드를 그대로 꺼내 시험한다
const fs = require("fs"), assert = require("assert");
const src = fs.readFileSync(__dirname + "/../news.js", "utf8").split("\r\n").join("\n");
const grab = (re) => { const m = src.match(re); assert(m, "코드를 찾지 못함: " + re); return m[0]; };
const code = grab(/const pxAt = [^\n]+\n/) + grab(/const WIN = [^\n]+\n/) + grab(/function windows\(k, ts\) \{[\s\S]*?\n  \}\n/);
const M = 60000, T0 = 1_000_000 * M;
// 1분봉: i번째 봉은 T0+i분에 시작, T0+(i+1)분에 마감, 종가 100+i. 마지막 봉(i=40)은 진행 중
const rows = []; for (let i = 0; i <= 40; i++) rows.push([T0 + i * M, 100 + i]);
const windows = new Function("candles1", code + "return windows;")({ K: rows });
const near = (a, b) => assert(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

// 보도 T0+10분 → 기준은 보도 5분 전(T0+5분)에 마감된 봉 종가 104
let w = windows("K", T0 + 10 * M);
assert.deepStrictEqual(w.map((x) => x.n), [5, 15, 30, 60]);
near(w[0].v, (114 / 104 - 1) * 100);   // +5분  → T0+15분 마감 봉 114
near(w[1].v, (124 / 104 - 1) * 100);   // +15분 → 124
near(w[2].v, (139 / 104 - 1) * 100);   // +30분 → T0+40분 마감 봉 139
assert.strictEqual(w[3].v, null);      // +60분 → 아직 안 지남 = 계산 중
// 기준 가격이 데이터 범위 밖이면 계산하지 않음
assert.strictEqual(windows("K", T0 + 5 * M), null);
assert.notStrictEqual(windows("K", T0 + 6 * M), null);
// 데이터 없음
assert.strictEqual(windows("X", T0 + 10 * M), null);
// 하락도 음수로
const down = []; for (let i = 0; i <= 80; i++) down.push([T0 + i * M, 200 - i]);
w = new Function("candles1", code + "return windows;")({ D: down })("D", T0 + 10 * M);
assert(w.every((x) => x.v < 0), "하락은 모두 음수");
console.log("windows.test.js OK");
