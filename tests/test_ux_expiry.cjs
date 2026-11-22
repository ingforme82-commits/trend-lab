// 11/22 UX 티켓(기한 지난 문구 자동 내림): '장중' 카드 마감 뒤 내림 · 발표 시각 지난 실적 대기 항목 내림 · 전부 지나면 칸 숨김
// 실행: node tests/test_ux_expiry.cjs
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const src = fs.readFileSync("app.js", "utf8");
const cut = (a, b) => { const i = src.indexOf(a), j = src.indexOf(b, i); assert.ok(i >= 0 && j > i, a); return src.slice(i, j); };
const KST = (d = new Date()) => new Date(d.getTime() + (d.getTimezoneOffset() + 540) * 60000);
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const at = (s) => Date.parse(s);

// ── 1) 장중 카드 ──
const ctx = { window: {}, KST, Intl, Date, Math, String, Object, Number };
vm.createContext(ctx);
vm.runInContext(cut("function marketSessions(", "function pulseItems(") + cut("const HL_US =", "function hlOrder(") + "\nglobalThis.T={hlWhenAt,hlStale,sessCloseAfter,hlMkt};", ctx);
const { hlWhenAt, hlStale, sessCloseAfter } = ctx.T;

// when 읽기(KST) — 실제 headline.json 형식들
const now = at("2026-11-22T12:00:00+09:00");
assert.equal(hlWhenAt("11/19 23:35 KST (미 동부 09:35) · 정규장 개장 초반", now), at("2026-11-19T23:35:00+09:00"));
assert.equal(hlWhenAt("11/10(화) 10시 42분 기준 · 장중 잠정", now), at("2026-11-10T10:42:00+09:00"));
assert.equal(hlWhenAt("11월 21일 22:10 KST 정리", now), at("2026-11-21T22:10:00+09:00"));
assert.equal(hlWhenAt("11/14 15시 기준", now), at("2026-11-14T15:00:00+09:00"));
assert.equal(hlWhenAt("10/30(금) 정리", now), null);        // 시각 없음
assert.equal(hlWhenAt("11/16~20 주간 확인 계획", now), null);
assert.equal(hlWhenAt("12/31 09:00", at("2027-01-02T09:00:00+09:00")), at("2026-12-31T09:00:00+09:00")); // 해 넘김

// 마감 시각: 한국 20:00 KST(11/23 운영자: 국내 장중 08:00~20:00, NXT 애프터 마감), 미국 뉴욕 16:00(겨울 = KST 다음 날 06:00, 여름 = 05:00)
assert.equal(sessCloseAfter("kr", at("2026-11-10T10:42:00+09:00")), at("2026-11-10T20:00:00+09:00"));
assert.equal(sessCloseAfter("kr", at("2026-11-10T17:10:00+09:00")), at("2026-11-10T20:00:00+09:00"));   // 애프터 중 작성
assert.equal(sessCloseAfter("kr", at("2026-11-10T20:30:00+09:00")), at("2026-11-10T20:30:00+09:00"));   // 20시 뒤 작성 → 바로 지남
assert.equal(sessCloseAfter("us", at("2026-11-19T23:35:00+09:00")), at("2026-11-20T06:00:00+09:00"));
assert.equal(sessCloseAfter("us", at("2026-07-15T23:00:00+09:00")), at("2026-07-16T05:00:00+09:00"));

// 미국 장중 카드(11/19 23:35 작성): 마감 06:00 전엔 둔다, 뒤엔 내린다
const us = { tag: "🇺🇸 미국장 장중", when: "11/19 23:35 KST (미 동부 09:35) · 정규장 개장 초반", until: "2026-11-21" };
assert.equal(hlStale(us, at("2026-11-20T05:59:00+09:00")), false);
assert.equal(hlStale(us, at("2026-11-20T06:00:00+09:00")), true);
// 한국 장중(when 에 '장중', 시장 mkt=kr): 정규장 마감 15:30 에는 아직 둠, 20:00(NXT 마감) 전/후
const kr = { tag: "🏁 주도 섹터·종목", when: "11/10(화) 10시 42분 기준 · 장중 잠정", mkt: "kr", until: "2026-11-11" };
assert.equal(hlStale(kr, at("2026-11-10T15:30:00+09:00")), false);
assert.equal(hlStale(kr, at("2026-11-10T19:59:00+09:00")), false);
assert.equal(hlStale(kr, at("2026-11-10T20:00:00+09:00")), true);
// 시각을 못 읽으면 지금 국내 장중(평일 08:00~20:00)일 때만: 07:59 내림 · 08:00 둠 · 11시 둠 · 16시(애프터) 둠 · 20시 내림 · 주말 내림
const krNoTime = { tag: "🇰🇷 한국장 장중", when: "장중 정리", mkt: "kr" };
assert.equal(hlStale(krNoTime, at("2026-11-20T07:59:00+09:00")), true);
assert.equal(hlStale(krNoTime, at("2026-11-20T08:00:00+09:00")), false);
assert.equal(hlStale(krNoTime, at("2026-11-20T11:00:00+09:00")), false);
assert.equal(hlStale(krNoTime, at("2026-11-20T16:00:00+09:00")), false);
assert.equal(hlStale(krNoTime, at("2026-11-20T20:00:00+09:00")), true);
assert.equal(hlStale(krNoTime, at("2026-11-21T11:00:00+09:00")), true);
// 미국은 그대로: 시각 없는 미국 장중 카드는 정규장 중에만(뉴욕 11시 = KST 다음 날 01시 둠, 뉴욕 17시 애프터 = 내림)
const usNoTime = { tag: "🇺🇸 미국장 장중", when: "장중 정리", mkt: "us" };
assert.equal(hlStale(usNoTime, at("2026-11-20T01:00:00+09:00")), false);
assert.equal(hlStale(usNoTime, at("2026-11-20T07:00:00+09:00")), true);
// '장중'이 없는 카드·시장 미상(g) 카드는 건드리지 않는다(until 만)
assert.equal(hlStale({ tag: "📊 오늘 시황(자동)", title: "마감 — 장중 고점 대비 -2.0%", when: "11/20 15시 35분 자동 갱신 · 마감" }, now), false);
assert.equal(hlStale({ tag: "🗞️ 오늘 주목", when: "11/10 10시 장중", mkt: "g" }, now), false);

// ── 2) 렌더: 전부 지나면 #headline 숨김, 장중 카드만 빠짐 ──
const els = new Map(), $ = (k) => { if (!els.has(k)) els.set(k, { hidden: false, innerHTML: "", textContent: "" }); return els.get(k); };
const rctx = { window: { trlAuto: [] }, KST: () => KST(new Date(at("2026-11-20T07:00:00+09:00"))), ymd, $, esc: (s) => String(s ?? ""), Intl, Date: class extends Date { static now() { return at("2026-11-20T07:00:00+09:00"); } }, Math, String, Object, Number, RegExp };
vm.createContext(rctx);
vm.runInContext(cut("function marketSessions(", "function pulseItems(") + cut("const HL_US =", "// 추세 판단에 표시된") + cut("function hlLang(", "window.trlHlLang") + cut("function renderHeadlineRaw(", "function renderHeadline()")
  + "\nfunction hlLive(){return ''}\nfunction hlTone(){return ''}\nconst pageLang='ko';\nglobalThis.go=(h)=>{hlData=h;renderHeadlineRaw();};let hlData;", rctx);
$("#headline").hidden = false;
rctx.go({ updated: "x", items: [us, { tag: "📐 기준", title: "남는 카드", when: "11/15 기준", until: "2027-11-15" }] });
assert.ok(!$("#hlList").innerHTML.includes("미국장 장중") && $("#hlList").innerHTML.includes("남는 카드"));
assert.equal($("#headline").hidden, false);
$("#hlList").innerHTML = "옛 카드";
rctx.go({ updated: "x", items: [us, { tag: "지난 것", title: "t", until: "2026-11-19" }] });
assert.equal($("#headline").hidden, true);                    // 전부 지남 → 칸 내림(예전엔 옛 카드가 남았음)

// ── 3) 실적: 발표 시각 지난 대기 항목 내림 ──
async function earn(nowIso, items) {
  const e = new Map(), q = (k) => { if (!e.has(k)) e.set(k, { hidden: true, innerHTML: "", textContent: "" }); return e.get(k); };
  const N = at(nowIso);
  const c = { console, Promise, Date: class extends Date { static now() { return N; } }, DOW: ["일", "월", "화", "수", "목", "금", "토"],
    KST: () => KST(new Date(N)), ymd, $: q, esc: (s) => String(s ?? ""),
    fetch: async (u) => ({ ok: true, json: async () => u.includes("checkpoints") ? [] : { updated: "fx", items } }) };
  vm.createContext(c);
  vm.runInContext(cut("async function loadEarnings()", "/* ───────── 2-1.") + "\nglobalThis.run=loadEarnings;", c);
  await c.run(); return e;
}
(async () => {
  const items = [
    { date: "2026-11-19", kst_date: "2026-11-20", name: "대기A", sym: "AAA", sector: "s", hour: "장마감 뒤", kst: "11/20 06시 이후", check: "확정", eps_est: 1 },
    { date: "2026-11-20", kst_date: "2026-11-20", name: "대기B", sym: "BBB", sector: "s", hour: "장전", kst: "11/20 밤 21~22시", check: "확정", eps_est: 1 },
    { date: "2026-11-19", kst_date: "2026-11-20", name: "결과C", sym: "CCC", sector: "s", hour: "장마감 뒤", kst: "11/20 06시 이후", check: "확정", eps_est: 1, eps_act: 1.2, eps_sur: 20 },
    { date: "2026-11-20", kst_date: "2026-11-20", name: "미정D", sym: "DDD", sector: "s", hour: "", kst: "시각 미정", check: "확정", eps_est: 1 },
  ];
  let e = await earn("2026-11-20T05:59:00+09:00", items), h = e.get("#earnList").innerHTML;
  assert.ok(["대기A", "대기B", "결과C", "미정D"].every((n) => h.includes(n)));
  e = await earn("2026-11-20T06:00:00+09:00", items); h = e.get("#earnList").innerHTML;
  assert.ok(!h.includes("대기A") && h.includes("대기B") && h.includes("결과C") && h.includes("미정D"));
  e = await earn("2026-11-20T22:00:00+09:00", items); h = e.get("#earnList").innerHTML;
  assert.ok(!h.includes("대기B") && h.includes("결과C") && h.includes("미정D"));   // 21~22시 → 22시 지나면
  e = await earn("2026-11-21T00:00:00+09:00", items); h = e.get("#earnList").innerHTML;
  assert.ok(!h.includes("미정D") && h.includes("결과C"));                          // 시각 미정 → 그날이 끝나면
  e = await earn("2026-11-21T00:00:00+09:00", items.filter((x) => x.eps_act == null));
  assert.equal(e.get("#earnings").hidden, true);                                    // 남은 게 없으면 칸 숨김
  console.log("test_ux_expiry ok");
})().catch((err) => { console.error(err); process.exit(1); });
