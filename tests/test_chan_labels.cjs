// dev-20261122-2300 추세 판단(채널) 문구 정리 — 신호 앞 시점 표시·띠 문구·운영자 원칙 라벨 유지
// 실행: node tests/test_chan_labels.cjs
//  · 신호 종류·순서·색은 그대로, 글자 앞에 시점 P 만 붙는다("P · 신호")
//  · 11/23 운영자(decisions/trading.md): 국내 장중 = 평일 08:00~20:00(NXT 프리·KRX 정규장·NXT 애프터), 정규장은 따로 구분 표시
//  · 미국·일본: '장중'은 live 정규장일 때만. 마감·지연에는 어디서도 '장중'이 붙지 않는다
//  · 하단 3% 근접 신호·'채널 상단 도달 후 상단 아래'(외부 패치)는 넣지 않는다
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const ROOT = path.join(__dirname, "..");
const news = fs.readFileSync(path.join(ROOT, "news.js"), "utf8");
const app = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const cut = (src, a, b) => { const i = src.indexOf(a), j = src.indexOf(b, i); assert.ok(i >= 0 && j > i, a); return src.slice(i, j); };
const at = (s) => Date.parse(s);

const ctx = {Date, Math, Number, String, window: {}};
vm.createContext(ctx);
vm.runInContext(cut(news, "const CH_RT", "let chanRtSig") + "\nglobalThis.T = {chSigNow, chPhase};", ctx);
const {chSigNow, chPhase} = ctx.T;

// 시각(KST): 2026-11-23 월요일
const T = {
  krReg: at("2026-11-23T10:00:00+09:00"),   // KRX 정규장
  krPre: at("2026-11-23T08:20:00+09:00"),   // NXT 프리
  krAft: at("2026-11-23T17:00:00+09:00"),   // NXT 애프터
  krNight: at("2026-11-23T21:00:00+09:00"), // 20시 뒤
  krEarly: at("2026-11-23T07:30:00+09:00"), // 08시 전
  sat: at("2026-11-21T11:00:00+09:00"),     // 토요일
};

// ── 1) 시점 P ──
// 국내(kr·kr_index)
for (const cc of ["kr", "kr_index"]) {
  assert.equal(chPhase({live: true}, cc, T.krReg), "장중(정규장)");
  assert.equal(chPhase({live: true, session: "정규장"}, cc, T.krReg), "장중(정규장)");
  assert.equal(chPhase({live: true, session: "NXT 프리"}, cc, T.krPre), "장중(NXT 프리)");
  assert.equal(chPhase({live: true, session: "NXT 애프터"}, cc, T.krAft), "장중(NXT 애프터)");
  assert.equal(chPhase({live: false}, cc, T.krAft), "종가");
  assert.equal(chPhase({live: false}, cc, T.krNight), "종가");
  assert.equal(chPhase({live: false, session: "NXT 애프터"}, cc, T.krNight), "NXT 애프터 마지막 체결");
  // 08~20시 밖·주말에는 live 표시가 남아 있어도 '장중' 금지
  for (const t of [T.krNight, T.krEarly, T.sat]) {
    assert.equal(chPhase({live: true}, cc, t), "종가");
    assert.equal(chPhase({live: true, session: "NXT 애프터"}, cc, t), "NXT 애프터 마지막 체결");
  }
}
// 미국·일본(지금 규칙 그대로)
for (const cc of ["us", "jp"]) {
  assert.equal(chPhase({live: true}, cc), "장중");
  assert.equal(chPhase({live: true, session: "정규장"}, cc), "장중");
  assert.equal(chPhase({live: true, session: "프리마켓"}, cc), "프리");
  assert.equal(chPhase({live: true, session: "애프터마켓"}, cc), "애프터");
  assert.equal(chPhase({live: true, session: "선물 24시간"}, cc), "선물");
  assert.equal(chPhase({live: false}, cc), "종가");
  assert.equal(chPhase({live: false, session: "정규장"}, cc), "종가");
  assert.equal(chPhase({live: false, session: "애프터마켓"}, cc), "애프터 마지막 체결");
  assert.equal(chPhase({live: false, session: "프리마켓"}, cc), "프리 마지막 체결");
  assert.equal(chPhase({live: false, session: "선물 24시간"}, cc), "선물 마지막 체결");
}

// ── 2) 신호 라벨 표 (순서·조건·색은 지금 그대로) ──
// 일봉 10개: 앞 8개 종가 100, 어제 종가 prev, 오늘 [시가, 고가, 저가, 종가=px]
function mk({prev = 100, o = 100, h, l = 95, px, ...rest}) {
  const rows = Array.from({length: 9}, (_, i) => ["11/" + String(i + 10), 100, 101, 99, i === 8 ? prev : 100]);
  rows.push(["11/19", o, h ?? Math.max(o, px), l, px]);
  return {rows, px, up_now: 130, lo_now: 80, channel_valid: true, state: "채널 안", live: false, ...rest};
}
const CASES = [
  // [이름, 항목, 기대 base 글자, 색]
  ["돌파 확인", mk({px: 120, ma5: 104, state: "돌파 확인"}), "돌파 확정", "up"],
  ["돌파 시도(장중)", mk({px: 120, ma5: 104, state: "돌파 시도(장중)"}), "돌파 시도(종가 확인 전)", "up"],
  ["하단 이탈", mk({px: 78, ma5: 96, state: "하단 이탈"}), "하락 시그널 · 채널 하단 이탈", "dn"],
  // 고가 ≥ 상단×1.01 뒤 상단 아래 — 5일선(고가 때)·상단 0.5% 밖/안
  ["상단 돌파 실패", mk({px: 108, h: 112, ma5: 101, up_now: 110}), "채널 상단 돌파 실패", "dn"],
  ["5일선 돌파 실패(겹침)", mk({px: 108, h: 112, ma5: 109.2, up_now: 110}), "5일선 돌파 실패(채널 상단과 겹침)", "dn"],
  ["겹침 0.5% 안(0.45%)", mk({px: 108, h: 112, ma5: 109.7, up_now: 110}), "5일선 돌파 실패(채널 상단과 겹침)", "dn"],
  ["겹침 0.5% 밖(0.55%)", mk({px: 108, h: 112, ma5: 109.8, up_now: 110}), "채널 상단 돌파 실패", "dn"],
  // 고가 ≥ 상단, 현재가 < 상단×0.997
  ["상단 저항", mk({px: 109, h: 110.5, ma5: 101, up_now: 110}), "채널 상단 저항", "dn"],
  ["5일선 저항(겹침)", mk({px: 109, h: 110.5, ma5: 109.7, up_now: 110}), "5일선 저항(채널 상단과 겹침)", "dn"],
  // 어제 5일선 아래 → 오늘 고가 5일선 닿고 0.3% 넘게 아래
  ["5일선 저항", mk({px: 104, h: 106, ma5: 105}), "5일선 저항", "dn"],
  // 어제 5일선 위 → 오늘 아래: 시가가 5일선(시가 때) 위였으면 '5일선 이탈', 시가부터 아래면 '시가부터 5일선 아래'(정규장만)
  ["5일선 이탈", mk({prev: 102, o: 101.5, h: 101.6, px: 100, ma5: 101}), "하락 시그널 · 5일선 이탈", "dn"],
  ["시가부터 5일선 아래", mk({prev: 102, o: 99, h: 100.2, px: 100, ma5: 101}), "시가부터 5일선 아래", "dn"],
  ["시가부터 아래 — 시간외는 구분 안 함", mk({prev: 102, o: 99, h: 100.2, px: 100, ma5: 101, session: "애프터마켓"}), "하락 시그널 · 5일선 이탈", "dn"],
  // 어제 5일선 아래 → 오늘 위: 색은 wk(빨강은 진짜 돌파만)
  ["5일선 위로", mk({o: 100, h: 102.5, px: 102, ma5: 100.5}), "5일선 위로(돌파 전)", "wk"],
  ["시가부터 5일선 위", mk({o: 101, h: 102.5, px: 102, ma5: 100.5}), "시가부터 5일선 위(돌파 전)", "wk"],
  ["시가부터 위 — 시간외는 구분 안 함", mk({o: 101, h: 102.5, px: 102, ma5: 100.5, session: "NXT 애프터"}), "5일선 위로(돌파 전)", "wk"],
];
const PHASES = [   // [이름, 덮어쓸 값, cc, 시각, 기대 P]
  ["국내 장중(정규장)", {live: true}, "kr", T.krReg, "장중(정규장)"],
  ["국내 장중(NXT 애프터)", {live: true, session: "NXT 애프터"}, "kr", T.krAft, "장중(NXT 애프터)"],
  ["국내 종가", {live: false}, "kr", T.krNight, "종가"],
  ["국내 시간외 마지막 체결", {live: false, session: "NXT 애프터"}, "kr", T.krNight, "NXT 애프터 마지막 체결"],
  ["미국 장중", {live: true}, "us", T.krNight, "장중"],
  ["미국 시간외 live", {live: true, session: "애프터마켓"}, "us", T.krNight, "애프터"],
  ["미국 종가", {live: false}, "us", T.krReg, "종가"],
  ["미국 시간외 마지막 체결", {live: false, session: "애프터마켓"}, "us", T.krReg, "애프터 마지막 체결"],
];
let n = 0;
for (const [name, base, want, tone] of CASES) {
  for (const [pn, over, cc, t, P] of PHASES) {
    const it = {...base, ...over, session: over.session ?? base.session};
    const s = chSigNow(it, cc, t);
    // 시간외 값에서는 '시가부터' 구분을 하지 않는다 — 기대 글자도 그에 맞춘다
    const ext = it.session && it.session !== "정규장";
    const w = ext ? want.replace("시가부터 5일선 아래", "하락 시그널 · 5일선 이탈").replace("시가부터 5일선 위(돌파 전)", "5일선 위로(돌파 전)") : want;
    assert.ok(s, `${name} / ${pn}: 신호 없음`);
    assert.equal(s.base, w, `${name} / ${pn}`);
    assert.equal(s.tone, tone, `${name} / ${pn}: 색`);
    const wantP = base.session ? chPhase(it, cc, t) : P;      // 케이스 자체가 시간외 값이면 그 세션 기준 시점(1번에서 따로 확인)
    assert.equal(s.phase, wantP, `${name} / ${pn}: 시점`);
    assert.equal(s.label, wantP + " · " + w, `${name} / ${pn}: 글자`);
    if (tone === "up") assert.ok(/^돌파 (확정|시도)/.test(s.base), "빨강(up)은 돌파 확정·시도만");
    n++;
  }
}
// 돌파 시도와 확정은 합치지 않는다(서로 다른 글자)
assert.notEqual(chSigNow(CASES[0][1], "kr", T.krNight).label, chSigNow(CASES[1][1], "kr", T.krNight).label);

// ── 3) 신호 없음 ──
// 지연(stale) → null (마감 뒤 '장중' 원천 차단)
assert.equal(chSigNow({...CASES[1][1], stale: true, live: true}, "kr", T.krReg), null);
assert.equal(chSigNow({...CASES[1][1], stale: true, live: true}, "us"), null);
// 하단 3% 근접은 신호가 아니다(외부 패치 '채널 하단 근접' 넣지 않음)
const nearFloor = mk({px: 81, h: 81.5, o: 81, ma5: 82, lo_now: 80});   // 하단 +1.25%, 5일선 아래로 유지(어제도 아래)
nearFloor.rows[8][4] = 82; nearFloor.rows.forEach((r, i) => { if (i < 8) r[4] = 83; });
assert.equal(chSigNow({...nearFloor, live: true}, "kr", T.krReg), null);
assert.equal(chSigNow({...nearFloor, live: false}, "us"), null);
// 채널 안 조용한 날 → null
assert.equal(chSigNow(mk({px: 100, h: 100.5, ma5: 100.2}), "kr", T.krReg), null);

// ── 4) 전체 탐색: 마감·지연·장외 시간에는 어떤 신호에도 '장중'이 없다, 금지 문구 없음 ──
const ALLOWED = new Set(["돌파 확정", "돌파 시도(종가 확인 전)", "하락 시그널 · 채널 하단 이탈", "채널 상단 돌파 실패", "5일선 돌파 실패(채널 상단과 겹침)",
  "채널 상단 저항", "5일선 저항(채널 상단과 겹침)", "5일선 저항", "하락 시그널 · 5일선 이탈", "시가부터 5일선 아래", "5일선 위로(돌파 전)", "시가부터 5일선 위(돌파 전)"]);
const SESS = [undefined, "정규장", "NXT 프리", "NXT 애프터", "프리마켓", "애프터마켓", "선물 24시간"];
let swept = 0;
for (const [, base] of CASES) for (const cc of ["kr", "kr_index", "us", "jp"]) for (const session of SESS) for (const live of [true, false]) for (const t of Object.values(T)) {
  const s = chSigNow({...base, session, live}, cc, t);
  if (!s) continue; swept++;
  assert.ok(ALLOWED.has(s.base), s.base);
  assert.ok(!/근접|도달 후/.test(s.label), s.label);
  const krOpen = (cc === "kr" || cc === "kr_index") && (t === T.krReg || t === T.krPre || t === T.krAft);
  if (!live) assert.ok(!s.label.includes("장중"), `마감 값에 장중: ${s.label}`);
  if ((cc === "kr" || cc === "kr_index") && !krOpen) assert.ok(!s.label.includes("장중"), `국내 장외 시간에 장중: ${s.label}`);
  if (cc === "us" || cc === "jp") assert.equal(s.label.startsWith("장중"), live && (!session || session === "정규장"), s.label);
}

// ── 5) 화면 코드: 카드 상태 칸은 state 글자 그대로, #chanRule 그대로, 시그널 칸 꼬리 ' · 마지막' 중복 없음 ──
assert.ok(news.includes('<span class="ch-st s-${CH_ST[it.state] || "in"}">${esc(it.state)}</span>'), "카드 상태 칸 = state 그대로");
assert.ok(news.includes('const CH_ST = {"돌파 확인": "ok", "돌파 시도(장중)": "try", "돌파 관찰·상단 근접": "near", "채널 위·5일선 아래": "warn", "채널 돌파·전고점 아래": "warn", "상단 근접": "near", "채널 안": "in", "하단 이탈": "bad"};'), "CH_ST 그대로");
assert.ok(news.includes('q("#chanRule").textContent = "돌파 관찰: 5일선 위·채널 상단 3% 이내 · 종가와 이후 지지 확인";'), "#chanRule 그대로");
assert.ok(!news.includes('${esc(now.label)}${it.live ? "" : " · 마지막"}'), "시그널 칸 ' · 마지막' 꼬리는 P 가 대신");
assert.ok(news.includes("돌파 시도·확정") && !news.includes("돌파 시그널·확정"), "시그널 칸 머리 범례");
assert.ok(!/경계선까지|채널 하단 근접/.test(news), "외부 패치 문구 없음");
assert.equal((news.match(/chSigNow\(it, g\.cc\)/g) || []).length, 2, "카드·시그널 칸 모두 시장(cc)을 넘김");

// ── 6) 띠(app.js) ──
const actx = {Date: class extends Date { static now() { return actx.NOW; } }, Math, String, Number, window: {}, NOW: 0};
vm.createContext(actx);
vm.runInContext(cut(app, "function bandSignal(", "async function loadBand") + "\nglobalThis.B = {bandSignal, bandPhase, bandSigText};", actx);
const RAW = "📐 5일선 돌파 시그널 — 삼성전자 100,000원이 5일선 99,000원 위로 (어제 98,000원은 5일선 아래) · 채널 상단선 105,000원까지 +5.0%";
const TAIL = RAW.slice("📐 5일선 돌파 시그널".length);
function band(cc, it, now) {
  actx.NOW = now;
  actx.window.trlChan = {groups: [{cc, items: [{code: "X", ma5: 99, px: 100, ...it}]}], signals: [{code: "X", ts: now - 600e3, text: RAW}]};
  const s = actx.B.bandSignal(now);
  return s ? s.text : null;
}
assert.equal(band("kr", {live: true}, T.krReg), "📐 장중(정규장) 5일선 상향 관측" + TAIL);
assert.equal(band("kr", {live: true, display: {session: "NXT 애프터", live: true, px: 100, ma5: 99}}, T.krAft), "📐 장중(NXT 애프터) 5일선 상향 관측" + TAIL);
assert.equal(band("kr", {live: true}, T.krNight), null);                 // 20시 뒤: 띠에 안 나옴(장중 금지)
assert.equal(band("kr", {live: false}, T.krReg), null);                  // live 아님 → 띠 없음(지금과 같음)
assert.equal(band("us", {live: true}, T.krNight), "📐 장중 5일선 상향 관측" + TAIL);
assert.equal(band("us", {live: true, session: "애프터마켓"}, T.krReg), "📐 애프터마켓 5일선 상향 관측" + TAIL);
assert.equal(band("us", {live: true, stale: true}, T.krNight), null);
assert.equal(band("us", {live: true, px: 98}, T.krNight), null);         // 5일선 아래로 밀림 → 내림(11/20 운영자)
assert.equal(actx.B.bandSigText("다른 문장", "장중"), "다른 문장");         // 원문 형식이 다르면 그대로

// ── 7) 번역표: 화면에 나올 수 있는 P·신호 조각이 모두 i18n-ui.js 에 6개 언어로 ──
const ictx = {window: {}};
vm.createContext(ictx);
vm.runInContext(fs.readFileSync(path.join(ROOT, "i18n-ui.js"), "utf8"), ictx);
const UI = ictx.window.TRL_UI;
const tpl = (s) => s.replace(/\d+(?:[.,:]\d+)*/g, ((i) => () => `{${i++}}`)(0));
const parts = new Set(["돌파 시도·확정"]);
for (const b of ALLOWED) b.split(" · ").forEach((p) => parts.add(tpl(p)));
const SESS_OF = {kr: [undefined, "정규장", "NXT 프리", "NXT 애프터"], us: [undefined, "정규장", "프리마켓", "애프터마켓", "선물 24시간"], jp: [undefined]};   // session_chan.py 가 내는 값
for (const cc of ["kr", "us", "jp"]) for (const session of SESS_OF[cc]) for (const live of [true, false]) for (const t of [T.krReg, T.krPre, T.krAft, T.krNight]) parts.add(chPhase({live, session}, cc, t));
for (const p of parts) for (const l of ["en", "ja", "zh-hans", "zh-hant", "fr"]) assert.ok(UI[p] && UI[p][l] && !/[가-힣]/.test(UI[p][l]), `번역 없음: ${p} (${l})`);

console.log(`test_chan_labels ok — 라벨 표 ${n}칸, 전체 탐색 ${swept}건, 번역 조각 ${parts.size}개`);
