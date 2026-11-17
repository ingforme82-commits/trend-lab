const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "news.js"), "utf8");
const start = source.indexOf("const CH_FLAG");
const end = source.indexOf("function drawS7()", start);
assert.ok(start >= 0 && end > start);
const elements = new Map();
const q = (id) => { if (!elements.has(id)) elements.set(id, {}); return elements.get(id); };
const rows = Array.from({length: 25}, (_, i) => ["11/" + String(i + 1).padStart(2, "0"), 100.25, 102.5, 99.1, 101.75]);
const item = (code, name) => ({code, name, px: 101.75, chg: 1.5, rows, day: "11/17", rank: 1, live: false,
  candle: {name: "양봉"}, state: "채널 안", up_now: 105.5, lo_now: 95.25, up_next: 105, lo_next: 95,
  su: -0.5, sl: -0.25, ma5: 101.25, gap_next: 3.2, gap_low: -6.4, hi: [2, 16], lo: [0, 14],
  instrument_type: "index", source: "합성 지수 출처", daily_source: "합성 일봉", source_at: 1000,
  quality_note: "장 종료·마지막 제공 지수"});
const context = {q, CH_ST: {}, esc: (s) => String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;"),
  hm: () => "15:30", window: {trlChan: {at: 1000, rule: "합성 검사", groups: [
    {cc: "kr_index", country: "한국", sector: "코스피 지수", items: [item("KOSPI", "코스피")]},
    {cc: "kr_index", country: "한국", sector: "코스닥 지수", items: [item("KOSDAQ", "코스닥")]}
  ]}}};
vm.createContext(context);
vm.runInContext(source.slice(start, end) + "\nglobalThis.fmt = chFmt; globalThis.render = drawChan;", context);
assert.equal(context.fmt("kr_index", 4968.48), "4,968.48pt");
assert.equal(context.fmt("kr", 195000), "195,000원");
assert.equal(context.fmt("us", 159.16), "$159.16");
context.render();
const html = elements.get("#chanBoard").innerHTML;
assert.equal((html.match(/class="ch-card"/g) || []).length, 2);
assert.equal((html.match(/class="ch-chart"/g) || []).length, 2);
assert.ok(html.includes("코스피") && html.includes("코스닥"));
assert.ok(html.includes("101.75pt") && html.includes("합성 지수 출처"));
assert.ok(!html.includes("NaN") && !html.includes("Infinity") && !html.includes("101.75원"));
console.log("지수 차트 2개 렌더·소수점·포인트 단위·출처 표시: PASS");
