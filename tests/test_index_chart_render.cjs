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
  upper_start: 2, lower_start: 0, hi: [2, 16], lo: [0, 14], upper_touch_count: 2, lower_touch_count: 2,
  upper_verified: true, lower_verified: true, channel_valid: true, touch_tolerance_pct: .75, touch_min_spacing: 3, touch_lookback_bars: 25,
  instrument_type: "index", source: "합성 지수 출처", daily_source: "합성 일봉", source_at: 1000,
  quality_note: "장 종료·마지막 제공 지수"});
const context = {q, CH_ST: {}, esc: (s) => String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;"),
  hm: () => "15:30", window: {trlChan: {at: 1000, rule: "합성 검사", groups: [
    {cc: "kr_index", country: "한국", sector: "코스피·코스닥 지수", items: [item("KOSPI", "코스피"), {...item("KOSDAQ", "코스닥"), hi: [2, 8, 16], lo: [0, 6, 14], upper_touch_count: 3, lower_touch_count: 3, lower_verified: true, channel_valid: true, state: "채널 안"}]}
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
assert.equal((html.match(/class="ch-grid2"/g) || []).length, 1);
assert.ok(html.indexOf("코스피</b>") < html.indexOf("코스닥</b>"));
assert.ok(html.includes("상단 3회 접촉 보강"));
assert.ok(html.includes("하단 2점 기준선"));
assert.ok(html.includes("추가 접촉 오차 0.75%"));
assert.ok(!html.includes("ch-unverified"));
context.window.trlChan.groups[0].items[1].lower_verified = false;
context.window.trlChan.groups[0].items[1].lower_touch_count = 1;
context.window.trlChan.groups[0].items[1].channel_valid = false;
context.render();
assert.ok(elements.get("#chanBoard").innerHTML.includes("하단 1점 재확인"));
assert.ok(elements.get("#chanBoard").innerHTML.includes("ch-unverified"));
assert.ok(!html.includes("10월 말 고점 대비 덜 빠진 순") && !html.includes("ch-md m"));
const css = fs.readFileSync(path.join(root, "style.css"), "utf8");
assert.ok(css.includes("grid-template-columns:repeat(2,minmax(0,1fr))"));
assert.ok(css.includes("@media (max-width:860px){.ch-grid2{grid-template-columns:1fr}}"));
console.log("두 기준점 실선·추가 접촉 보강·지수 순서·PC 2열/모바일 1열: PASS");

const regular = {...item("NVDA", "엔비디아"), instrument_type: "stock", px: 150, state: "채널 안", ma5: 160};
regular.rows = rows.map(r => r.slice());
regular.rows[regular.rows.length - 1] = ["11/17",150,151,149,150];
regular.display = {...item("NVDA", "엔비디아"), instrument_type: "stock", px: 175, ma5: 155,
  reference_only: true, signal_eligible: false, source_at: 1000, checked_at: 2000,
  source: "확장세션 공급자", scope: "미국 확장세션", session: "애프터마켓",
  quality_note: "진행 중", time_kind: "5분봉 시작", history_note: "과거 정규장 · 오늘 확장세션",
  state: "돌파 시도(세션 참고)", live: true};
context.window.trlChan.groups = [{cc: "us", country: "미국", sector: "합성 검사", items: [regular]}];
context.render();
const extended = elements.get("#chanBoard").innerHTML;
assert.ok(extended.includes("$175.00"));
assert.ok(extended.includes("정규장 종가 <b class=\"mn\">$150.00"));
assert.ok(extended.includes("시간외 · 애프터마켓"));
assert.ok(!extended.includes("과거 정규장") && !extended.includes("참고값") && !extended.includes("시간외 값으로"));
assert.ok(!extended.includes("NaN") && !extended.includes("Infinity"));
assert.equal(regular.px, 150);
assert.equal(regular.state, "채널 안");
console.log("확장세션 표시 가격·원천시각·정규장 판정 분리: PASS");

regular.code = "MU"; regular.name = "마이크론"; regular.px = 712.42; regular.day = "11/17";
regular.rows[regular.rows.length - 1] = ["11/17",726.22,726.75,666.88,712.42];
regular.display = {...regular.display, code:"MU",name:"마이크론", day:"11/18", px:726.48,
  session:"프리마켓", chg:-2.59, base:745.8, rows:regular.rows.concat([["11/18",734.04,741.64,720.65,726.48]])};
function renderMU() {
  context.render();
  return elements.get("#chanBoard").innerHTML;
}
let text = renderMU();
assert.ok(text.includes('class="up">+1.97%</b>'));
assert.ok(text.includes('정규장 종가 <b class="mn">$712.42'));
assert.ok(!text.includes("-2.59%"));
const summary = elements.get("#chanNow").innerHTML;
assert.ok(summary.includes("마이크론") && summary.includes('+1.97%') && summary.includes("프리마켓"));
assert.ok(!summary.includes("-2.59%"));
regular.display.px = 705.2958;
text = renderMU();
assert.ok(text.includes('class="down">-1.00%</b>'));
regular.display.px = 712.42;
text = renderMU();
assert.ok(text.includes('class="dim">0.00%</b>'));
assert.ok(!text.includes("-0.00%"));
console.log("정규장 대비 등락률·양음보합 부호와 색상·국가별 현재 추세 일치: PASS");
