/* Trend Research Lab — 시세·체크포인트·피드·성향 테스트 */
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const KST = (d = new Date()) => new Date(d.getTime() + (d.getTimezoneOffset() + 540) * 60000);
const hhmm = (d) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const DOW = ["일", "월", "화", "수", "목", "금", "토"];

/* ───────── 1. 실시간 시세 (Hyperliquid) ───────── */
const TICKS = [
  { g: "한국 프록시" },
  { k: "KR200", n: "코스피200", d: 2 },
  { k: "SMSN", n: "삼성전자", d: 2, u: "$", won: true },
  { k: "SKHX", n: "SK하이닉스", d: 2, u: "$", won: true },
  { k: "EWY", n: "EWY (한국 ETF)", d: 2, u: "$" },
  { k: "KORU", n: "KORU (한국 3배)", d: 2, u: "$" },
  { k: "KRW", n: "원/달러", d: 1, suf: "원" },
  { g: "미국 지수·반도체" },
  { k: "SP500", n: "S&P500", d: 1 },
  { k: "XYZ100", n: "나스닥100", d: 0 },
  { k: "DOW", n: "다우존스", d: 0, srv: true },
  { k: "SOXL", n: "SOXL (반도체 3배)", d: 2, u: "$" },
  { g: "원자재·채권" },
  { k: "CL", n: "WTI 원유", d: 2, u: "$" },
  { k: "BRENTOIL", n: "브렌트유", d: 2, u: "$" },
  { k: "GOLD", n: "금", d: 1, u: "$" },
  { k: "NATGAS", n: "천연가스", d: 3, u: "$" },
  { k: "UST2Y", n: "미 2년물 금리", srv: "tnx", t: "2Y" },
  { k: "US10Y", n: "미 10년물 금리", srv: "tnx", t: "10Y" },
  { k: "UST30Y", n: "미 30년물 금리", srv: "tnx", t: "30Y" },
];
let lastPx = {};

async function loadTicks() {
  try {
    const r = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "metaAndAssetCtxs", dex: "xyz" }),
    });
    const [meta, ctx] = await r.json();
    const map = {};
    meta.universe.forEach((a, i) => { map[a.name.replace("xyz:", "")] = ctx[i]; });
    const krw = map.KRW ? +map.KRW.markPx : null;
    const html = TICKS.map((t) => {
      if (t.g) return `<p class="tick-group">${t.g}</p>`;
      if (t.srv === "tnx") {                              // 미 국채 2·10·30년 금리(CNBC, 없으면 야후): 수준은 %, 변화는 bp
        const U = window.trlUst || {};
        const r = U[t.t] || (t.t === "10Y" ? window.trlTnx || {} : {});
        const sp = t.t === "10Y" && U["2Y"] && r.px ? ` · 2년물과 차 ${Math.round((r.px - U["2Y"].px) * 100)}bp` : "";
        if (!r.px) return `<div class="tick"><p class="t-name">${t.n}</p><p class="t-px">-</p><p class="fine">불러오는 중</p></div>`;
        const c3 = r.bp > 0.05 ? "c-up" : r.bp < -0.05 ? "c-dn" : "c-fl";
        const old = Date.now() - r.at > 60 * 60000;
        return `<div class="tick" data-k="${t.k}"><p class="t-name">${t.n}</p><p class="t-px">${r.px.toFixed(3)}%</p><p class="t-ch ${c3}">${r.bp > 0 ? "▲" : r.bp < 0 ? "▼" : ""} ${r.bp > 0 ? "+" : ""}${r.bp.toFixed(1)}bp</p><p class="fine" style="margin:2px 0 0">전일 ${r.prev}%${sp}${old ? " · 장 마감" : ""}</p></div>`;
      }
      if (t.srv) {                                        // 다우존스: 사이트 속보 데이터(야후)에서 — 미국장엔 지수, 그 외엔 선물
        const dw = window.trlDow || {};
        const now = Date.now(), live = dw.idx && now - dw.idx.at < 20 * 60000;
        const main = live ? dw.idx : (dw.fut || dw.idx);
        if (!main) return `<div class="tick"><p class="t-name">${t.n}</p><p class="t-px">-</p><p class="fine">불러오는 중</p></div>`;
        const c2 = main.chg > 0.005 ? "c-up" : main.chg < -0.005 ? "c-dn" : "c-fl";
        const sub = live ? (dw.fut ? `선물 ${Math.round(dw.fut.px).toLocaleString("ko-KR")} (${dw.fut.chg > 0 ? "+" : ""}${dw.fut.chg}%)` : "지수")
          : "미니 다우 선물 · 장외";
        return `<div class="tick" data-k="DOW"><p class="t-name">${t.n}${live ? "" : " (선물)"}</p><p class="t-px">${Math.round(main.px).toLocaleString("ko-KR")}</p><p class="t-ch ${c2}">${main.chg > 0 ? "▲" : main.chg < 0 ? "▼" : ""} ${main.chg > 0 ? "+" : ""}${main.chg.toFixed(2)}%</p><p class="fine" style="margin:2px 0 0">${sub}</p></div>`;
      }
      const x = map[t.k];
      const kr = (window.trlKr || {})[t.k];
      const sg = (v) => `<b class="${v > 0.005 ? "c-up" : v < -0.005 ? "c-dn" : "c-fl"}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</b>`;
      const h24 = x && +x.prevDayPx ? (+x.markPx / +x.prevDayPx - 1) * 100 : null;
      const meta = x && +x.dayNtlVlm > 0 ? `<p class="t-meta">24h 거래대금 $${fmtVol(+x.dayNtlVlm)}${x.oraclePx && +x.oraclePx ? ` · 기초가격 대비 ${sg((+x.markPx / +x.oraclePx - 1) * 100)}` : ""}</p>` : "";
      if (kr && kr.px && (kr.open || !x)) {               // 한국 정규장: 한국거래소 실시간 가격 · 전일 종가 대비(네이버)
        const ck = kr.chg > 0.005 ? "c-up" : kr.chg < -0.005 ? "c-dn" : "c-fl";
        const v = t.k === "KR200" ? kr.px.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : Math.round(kr.px).toLocaleString("ko-KR") + "원";
        const age = Date.now() - kr.at > 10 * 60000 ? ` · <b class="h-warn">${Math.round((Date.now() - kr.at) / 60000)}분 전 값</b>` : "";
        return `<div class="tick" data-k="${t.k}"><p class="t-name">${t.n}</p><p class="t-px">${v}</p><p class="t-ch ${ck}">${kr.chg > 0 ? "▲" : kr.chg < 0 ? "▼" : ""} ${kr.chg > 0 ? "+" : ""}${kr.chg.toFixed(2)}% <small>정규장</small></p>
          <p class="t-meta">한국거래소 ${hhmm(KSTof(kr.at))}${age}${h24 != null ? ` · 24h 프록시 ${sg(h24)}` : ""}</p>${meta}</div>`;
      }
      if (!x) return "";
      const px = +x.markPx, prev = +x.prevDayPx, ch = prev ? (px / prev - 1) * 100 : 0;
      const cls = ch > 0.005 ? "c-up" : ch < -0.005 ? "c-dn" : "c-fl";
      const flash = lastPx[t.k] && lastPx[t.k] !== px ? " flash" : "";
      lastPx[t.k] = px;
      const val = (t.u || "") + px.toLocaleString("ko-KR", { minimumFractionDigits: t.d, maximumFractionDigits: t.d }) + (t.suf || "");
      const won = t.won && krw ? `<p class="fine" style="margin:2px 0 0">원화 환산 약 ${(Math.round(px * krw / 100) * 100).toLocaleString("ko-KR")}원</p>` : "";
      // 정규장 기준(한국: 네이버 마감값, 미국: 야후) — 24시간 대비와 따로 표시
      const rg = kr && kr.px ? { chg: kr.chg, at: kr.at, open: kr.open, src: "한국거래소" } : (window.trlReg || {})[t.k] ? { ...(window.trlReg || {})[t.k], src: "정규장" } : null;
      const reg = rg ? `<p class="t-meta">정규장 ${sg(rg.chg)} ${rg.open ? "장중" : `마감 ${mdhm(rg.at)}`}</p>` : "";
      return `<div class="tick${flash}" data-k="${t.k}"><p class="t-name">${t.n}</p><p class="t-px">${val}</p><p class="t-ch ${cls}">${ch > 0 ? "▲" : ch < 0 ? "▼" : ""} ${ch > 0 ? "+" : ""}${ch.toFixed(2)}% <small>24시간</small></p>${won}${reg}${meta}</div>`;
    }).join("");
    $("#tickGrid").innerHTML = html;
    setTimeout(() => document.querySelectorAll(".tick.flash").forEach((e) => e.classList.remove("flash")), 900);
    const k = KST();
    $("#tickStamp").textContent = `${k.getMonth() + 1}/${k.getDate()}(${DOW[k.getDay()]}) ${hhmm(k)}:${String(k.getSeconds()).padStart(2, "0")} KST 수신 · 하이퍼리퀴드 24시간 선물 실시간`;
  } catch (e) {
    $("#tickStamp").textContent = "시세를 불러오지 못했습니다. 잠시 후 다시 시도합니다.";
  }
}

const fmtVol = (v) => (v >= 1e9 ? (v / 1e9).toFixed(1) + "B" : v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : Math.round(v || 0) + "");
const KSTof = (ms) => new Date(ms + (new Date().getTimezoneOffset() + 540) * 60000);
const mdhm = (ms) => { const d = KSTof(ms); return `${d.getMonth() + 1}/${d.getDate()} ${hhmm(d)}`; };

/* ───────── 2. 체크포인트 ───────── */
async function loadChecks() {
  try {
    const list = await (await fetch(`data/checkpoints.json?t=${Date.now()}`)).json();
    const today = ymd(KST());
    const items = list.filter((c) => c.date >= today).sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || ""))).slice(0, 8);
    $("#checkList").innerHTML = items.length ? items.map((c) => {
      const d = new Date(c.date + "T00:00:00");
      return `<li class="${c.date === today ? "today" : ""}"><span class="c-date">${d.getMonth() + 1}/${d.getDate()}(${DOW[d.getDay()]})${c.time ? " " + esc(c.time) : ""}</span><p class="c-title">${esc(c.title)}</p>${c.note ? `<p class="c-note">${esc(c.note)}</p>` : ""}</li>`;
    }).join("") : `<li><p class="c-title">다음 일정은 곧 업데이트됩니다.</p></li>`;
  } catch { /* 체크포인트 없으면 섹션만 비움 */ }
}

/* ───────── 2-1. 📌 주요 이슈(data/headline.json, 운영자가 올림 · 사실·수치만 · 외부 링크 없음) ───────── */
async function loadHeadline() {
  try {
    const h = await (await fetch(`data/headline.json?t=${Date.now()}`)).json();
    const today = ymd(KST());
    const items = (h.items || []).filter((x) => !x.until || x.until >= today);
    if (!items.length) return;
    $("#hlList").innerHTML = items.map((x) => `<article class="hl-card">
      <p class="hl-tag">${esc(x.tag || "")}${x.when ? ` <small>${esc(x.when)}</small>` : ""}</p>
      <h3 class="hl-title">${esc(x.title)}</h3>
      <ul class="hl-pts">${(x.points || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
      ${x.source ? `<p class="hl-src">출처: ${esc(x.source)}</p>` : ""}
    </article>`).join("");
    $("#hlStamp").textContent = h.updated ? `${h.updated} 정리` : "";
    $("#headline").hidden = false;
  } catch { /* 주요 이슈 없으면 칸 숨김 */ }
}

/* ───────── 3. (블로그 분석 글 피드 — 2026-10-28 운영자 결정으로 사이트에서 뺌) ───────── */

/* ───────── 4. 투자 스타일 테스트 ───────── */
// 점수 축: T 추세추종 · C 역발상 · S 단기매매 · L 장기보유 · N 뉴스·테마 / r 위험(1~4) / h 습관 플래그 / g 좋은 습관
const Q = [
  { q: "한 종목을 보통 얼마나 들고 있나요?", o: [
    { t: "하루 안에 사고판다", s: { S: 3 } },
    { t: "며칠에서 몇 주", s: { T: 2, S: 1 } },
    { t: "몇 달 정도", s: { T: 1, L: 1, C: 1 } },
    { t: "1년 이상", s: { L: 3 } } ] },
  { q: "어떤 종목에 먼저 눈이 가나요?", o: [
    { t: "신고가를 내며 강하게 오르는 종목", s: { T: 3 } },
    { t: "많이 떨어져서 싸 보이는 종목", s: { C: 3 } },
    { t: "오늘 뉴스·테마로 움직이는 종목", s: { N: 3, S: 1 } },
    { t: "실적과 사업이 좋은 회사", s: { L: 3 } } ] },
  { q: "판단할 때 가장 먼저 보는 것은?", o: [
    { t: "차트와 이동평균선", s: { T: 3 } },
    { t: "재무제표·밸류에이션", s: { L: 2, C: 1 } },
    { t: "뉴스·텔레그램·커뮤니티 의견", s: { N: 3 }, h: ["confirm"] },
    { t: "호가·수급(외국인·기관)", s: { S: 3 } } ] },
  { q: "급등하는 종목을 보면?", o: [
    { t: "내 기준(돌파·거래량)에 맞으면 들어간다", s: { T: 2 }, g: ["rule"] },
    { t: "눌림이 올 때까지 기다린다", s: { C: 1, T: 1 } },
    { t: "놓칠까 봐 일단 산다", s: { N: 2, S: 1 }, h: ["chase"] },
    { t: "별 관심 없다", s: { L: 2 } } ] },
  { q: "산 종목이 -10% 빠졌습니다. 보통 어떻게 하나요?", o: [
    { t: "미리 정한 기준대로 정리한다", s: { T: 2 }, g: ["cut"] },
    { t: "평단을 낮추려고 더 산다", s: { C: 2 }, h: ["avgdown"] },
    { t: "회복될 때까지 기다린다", s: { L: 2 }, h: ["hold"] },
    { t: "그때그때 상황을 보고 정한다", s: { S: 1, N: 1 }, h: ["norule"] } ] },
  { q: "산 종목이 +15% 올랐습니다. 보통 어떻게 하나요?", o: [
    { t: "추세가 꺾일 때까지 들고 간다", s: { T: 3 } },
    { t: "수익 날 때 바로 판다", s: { S: 2 }, h: ["early"] },
    { t: "처음 정한 목표가까지 기다린다", s: { L: 2 } },
    { t: "절반만 팔고 나머지는 둔다", s: { T: 1, L: 1 }, g: ["split"] } ] },
  { q: "평균적으로 매매는 얼마나 자주 하나요?", o: [
    { t: "한 달에 몇 번 이하", s: { L: 2 } },
    { t: "일주일에 몇 번", s: { T: 2 } },
    { t: "하루 1~3번", s: { S: 2 } },
    { t: "하루 4번 이상", s: { S: 3 }, h: ["overtrade"] } ] },
  { q: "지수가 5일선 아래로 밀리며 약세일 때는?", o: [
    { t: "비중을 줄이고 회복을 확인한다", s: { T: 3 }, g: ["regime"] },
    { t: "싸게 모을 기회로 본다", s: { C: 2, L: 1 } },
    { t: "짧은 반등을 노린다", s: { S: 2 } },
    { t: "특별히 바꾸지 않는다", s: { L: 2 } } ] },
  { q: "투자금이 어느 정도 손실 나면 견디기 힘든가요?", o: [
    { t: "-5%만 돼도 불안하다", r: 1 },
    { t: "-10~20%까지는 버틸 수 있다", r: 2 },
    { t: "-30%까지도 버틸 수 있다", r: 3 },
    { t: "손실은 크게 신경 쓰지 않는다", r: 4 } ] },
  { q: "주식에 들어간 돈은 전체 자산에서 어느 정도인가요?", o: [
    { t: "여유자금 일부", r: 1 },
    { t: "자산의 절반 정도", r: 2 },
    { t: "자산의 대부분", r: 3 },
    { t: "신용·대출까지 쓴다", r: 4, h: ["leverage"] } ] },
  { q: "매매 기록을 남기고 다시 보나요?", o: [
    { t: "매번 기록하고 복기한다", g: ["journal"] },
    { t: "큰 손익이 났을 때만 본다" },
    { t: "기록하지 않는다", h: ["nojournal"] },
    { t: "증권사 앱 손익만 가끔 본다" } ] },
];

const TYPES = {
  T: { n: "추세추종형", e: "📈", d: "이미 시작된 흐름에 올라타고, 흐름이 꺾이면 내리는 스타일입니다. 바닥과 꼭지를 맞히기보다 '지금 추세 안에 있는가'를 확인합니다.",
       s: "큰 흐름을 길게 가져갈 수 있고, 손실을 기준대로 끊기 쉽습니다.", w: "횡보장에서는 잦은 진입·이탈로 작은 손실이 쌓일 수 있습니다(휩쏘).",
       c: ["진입·이탈 기준(예: 5일선·20일선, Envelope 상·하단)을 숫자로 적어 두었나요?", "횡보 구간을 걸러낼 조건(거래량, 기울기)이 있나요?"] },
  C: { n: "역발상 저가매수형", e: "🪂", d: "많이 빠져 싸 보일 때 모으는 스타일입니다. 남들이 두려워할 때 들어가는 용기가 장점입니다.",
       s: "공포 국면에서 좋은 가격을 얻을 수 있습니다.", w: "'싸다'가 '더 싸질 수 있다'로 이어지는 하락 추세에서는 물타기로 손실이 커지기 쉽습니다.",
       c: ["추가 매수 횟수와 총 한도를 미리 정했나요?", "하락 추세가 멈췄다는 확인 신호(예: 5일선 회복)를 기다리나요?"] },
  S: { n: "단기 트레이더형", e: "⚡", d: "호가·수급·당일 흐름에 빠르게 반응하는 스타일입니다. 짧은 시간 안에 결과를 확인합니다.",
       s: "시장 변화에 빠르게 대응하고 오래 물려 있지 않습니다.", w: "매매 횟수가 늘수록 수수료·세금·실수가 누적되고, 감정 매매로 이어지기 쉽습니다.",
       c: ["하루 최대 매매 횟수와 하루 최대 손실 한도가 있나요?", "수수료·세금을 뺀 실제 손익을 확인하나요?"] },
  L: { n: "장기 보유형", e: "🌳", d: "회사의 사업과 실적을 믿고 오래 들고 가는 스타일입니다. 단기 흔들림에 덜 반응합니다.",
       s: "매매 비용이 적고, 좋은 기업의 성장을 오래 누릴 수 있습니다.", w: "'언젠가 오르겠지'가 매도 기준이 없는 보유로 바뀌면 손실 종목을 너무 오래 들고 있게 됩니다.",
       c: ["처음 산 이유가 깨지면 판다는 기준을 적어 두었나요?", "전체 자산에서 한 종목 비중 한도가 있나요?"] },
  N: { n: "뉴스·테마 반응형", e: "📰", d: "새 소식과 테마의 움직임에 민감하게 반응하는 스타일입니다. 시장의 관심이 어디로 가는지 빨리 압니다.",
       s: "새로운 흐름을 빨리 발견합니다.", w: "뉴스가 나왔을 때는 이미 가격에 반영된 경우가 많아 고점에서 따라 사기 쉽습니다.",
       c: ["뉴스가 나오기 전후 가격이 얼마나 움직였는지 확인하나요?", "보고 싶은 정보만 찾고 있지는 않은지 반대 의견도 확인하나요?"] },
};
const RISK = ["안정 추구", "중립", "적극", "공격"];
const HABITS = {
  chase: ["추격 매수", "급등을 보고 놓칠까 봐 사는 습관입니다. '진입 전 체크리스트 3가지'를 만들어 통과할 때만 사도록 해 보세요."],
  avgdown: ["물타기", "손실 종목에 돈을 더 넣는 습관입니다. 추가 매수 횟수(예: 최대 1회)와 총 비중 한도를 미리 적어 두세요."],
  hold: ["손절 지연", "회복을 기다리며 손실 종목을 오래 들고 있는 습관(처분효과)입니다. '산 이유가 깨지면 정리'라는 문장 기준을 정해 두세요."],
  norule: ["기준 없는 대응", "상황마다 판단이 바뀌면 같은 실수가 반복됩니다. 손실 한도를 숫자로 한 줄만 정해도 달라집니다."],
  early: ["이익 조기 실현", "수익은 빨리, 손실은 늦게 정리하면 손익비가 나빠집니다. 일부만 팔고 나머지는 추세로 판단하는 방법도 있습니다."],
  overtrade: ["과매매", "매매가 잦을수록 비용과 감정 매매가 늘어납니다. 하루 최대 매매 횟수를 정해 보세요."],
  confirm: ["확증 편향", "커뮤니티·텔레그램 의견에 기대면 보고 싶은 정보만 보게 됩니다. 반대 근거를 한 가지씩 적어 보세요."],
  leverage: ["레버리지 위험", "신용·대출은 하락장에서 반대매매로 원치 않는 가격에 정리될 수 있습니다. 담보 비율과 최악의 경우를 먼저 계산해 보세요."],
  nojournal: ["복기 없음", "기록이 없으면 무엇이 통했고 무엇이 실패했는지 알 수 없습니다. 매매 이유를 한 줄씩만 남겨도 패턴이 보입니다."],
};
const GOODS = {
  rule: "진입 기준을 갖고 있습니다", cut: "손실을 기준대로 끊습니다", split: "분할 매도로 감정을 줄입니다",
  regime: "시장 상태에 따라 비중을 조절합니다", journal: "매매를 기록하고 복기합니다",
};

let qi = 0, answers = [];
function showQ() {
  const q = Q[qi];
  $("#qbarFill").style.width = `${(qi / Q.length) * 100}%`;
  $("#qCount").textContent = `질문 ${qi + 1} / ${Q.length}`;
  $("#qText").textContent = q.q;
  $("#qOpts").innerHTML = q.o.map((o, i) => `<button class="qopt${answers[qi] === i ? " sel" : ""}" data-i="${i}">${esc(o.t)}</button>`).join("");
  $("#qBack").disabled = qi === 0;
}
$("#quizStart").addEventListener("click", () => {
  qi = 0; answers = []; $("#quizIntro").hidden = true; $("#result").hidden = true; $("#quizBox").hidden = false; showQ();
});
$("#qOpts").addEventListener("click", (e) => {
  const b = e.target.closest(".qopt"); if (!b) return;
  answers[qi] = +b.dataset.i; b.classList.add("sel");
  setTimeout(() => { if (++qi < Q.length) showQ(); else showResult(); }, 160);
});
$("#qBack").addEventListener("click", () => { if (qi > 0) { qi--; showQ(); } });

function showResult() {
  if (window.trlCount) window.trlCount("quiz");
  const sc = { T: 0, C: 0, S: 0, L: 0, N: 0 }, h = [], g = [], rs = [];
  answers.forEach((a, i) => {
    const o = Q[i].o[a];
    Object.entries(o.s || {}).forEach(([k, v]) => { sc[k] += v; });
    if (o.r) rs.push(o.r);
    (o.h || []).forEach((x) => h.push(x)); (o.g || []).forEach((x) => g.push(x));
  });
  const order = Object.entries(sc).sort((a, b) => b[1] - a[1]);
  const total = order.reduce((s, [, v]) => s + v, 0) || 1;
  const main = TYPES[order[0][0]], sub = order[1][1] > 0 ? TYPES[order[1][0]] : null;
  const risk = Math.max(1, Math.min(4, Math.round(rs.reduce((a, b) => a + b, 0) / (rs.length || 1))));
  const pct = (v) => Math.round((v / total) * 100);

  $("#quizBox").hidden = true;
  const r = $("#result"); r.hidden = false;
  r.innerHTML = `
    <div class="r-top"><div class="r-emoji">${main.e}</div><div><p class="r-label">나의 투자 스타일</p><p class="r-type">${main.n}</p>${sub ? `<p class="r-label" style="color:#5b6474;font-weight:500">보조 성향: ${sub.e} ${sub.n}</p>` : ""}</div></div>
    <p class="r-desc">${main.d}</p>
    <p class="r-h">스타일 구성</p>
    <div class="bars">${order.map(([k, v], i) => `<div class="bar${i === 0 ? " main" : ""}"><span>${TYPES[k].e} ${TYPES[k].n}</span><div class="bar-t"><div class="bar-f" style="width:${pct(v)}%"></div></div><span>${pct(v)}%</span></div>`).join("")}</div>
    <p class="r-h">위험 감수 수준: ${RISK[risk - 1]}</p>
    <div class="risk">${[1, 2, 3, 4].map((n) => `<div class="${n <= risk ? "on" : ""}"></div>`).join("")}</div>
    <div class="risk-l">${RISK.map((x) => `<span>${x}</span>`).join("")}</div>
    <p class="r-h">이 스타일의 강점과 주의점</p>
    <div class="r-box good"><b>강점</b><p>${main.s}</p></div>
    <div class="r-box warn"><b>주의점</b><p>${main.w}</p></div>
    ${h.length ? `<p class="r-h">조심하면 좋은 습관 ${h.length}가지</p>${[...new Set(h)].map((x) => `<div class="r-box warn"><b>${HABITS[x][0]}</b><p>${HABITS[x][1]}</p></div>`).join("")}` : ""}
    ${g.length ? `<p class="r-h">이미 갖고 있는 좋은 습관</p>${[...new Set(g)].map((x) => `<div class="r-box good"><b>✓ ${GOODS[x]}</b></div>`).join("")}` : ""}
    <p class="r-h">스스로 점검해 볼 질문</p>
    <ul class="r-rules">${main.c.map((x) => `<li>${x}</li>`).join("")}</ul>
    <div class="r-btns">
      <button class="btn btn-kakao" id="rShare">💬 카톡으로 결과 공유</button>
      <button class="btn btn-gold" id="rStudy">📋 복사하고 오픈채팅 열기</button>
      <button class="btn btn-ghost-dark" id="rCopy">결과만 복사</button>
      <button class="btn btn-ghost-dark" id="rAgain">다시 하기</button>
    </div>
    <p class="r-toast" id="rToast" hidden></p>
    <p class="r-fine">이 결과는 답변을 바탕으로 한 교육용 자기 점검이며, 투자 자문이나 특정 종목·상품의 추천이 아닙니다. 답변은 저장·전송되지 않습니다.</p>`;
  r.scrollIntoView({ behavior: "smooth", block: "start" });

  $("#rAgain").addEventListener("click", () => $("#quizStart").click());
  const quizUrl = `${location.origin}${location.pathname}#quiz`;
  const habitTxt = h.length ? `조심할 습관: ${[...new Set(h)].map((x) => HABITS[x][0]).join(", ")}
` : "";
  const txt = `[나의 투자 스타일] ${main.e} ${main.n}${sub ? ` (보조: ${sub.n})` : ""}
위험 감수: ${RISK[risk - 1]}
${habitTxt}` +
    `
나도 해보기 👉 ${quizUrl}`;
  const toast = (m) => { const t = $("#rToast"); t.textContent = m; t.hidden = false; };
  const copy = async () => { try { await navigator.clipboard.writeText(txt); return true; } catch { return false; } };
  // 휴대폰: 공유 창(카톡 선택) / PC: 복사 후 안내
  $("#rShare").addEventListener("click", async () => {
    if (navigator.share) {
      try { await navigator.share({ title: "나의 투자 스타일", text: txt }); if (window.trlCount) window.trlCount("share"); return; }
      catch (err) { if (err && err.name === "AbortError") return; }
    }
    toast((await copy()) ? "결과가 복사됐어요. 카톡 대화방에 붙여넣기(Ctrl+V 또는 길게 눌러 붙여넣기) 하세요." : "복사하지 못했어요. 화면을 캡처해서 공유해 주세요.");
  });
  // 스터디 오픈채팅: 결과를 먼저 복사해 두고 방을 연다(카톡은 외부에서 메시지를 대신 보내 줄 수 없음)
  $("#rStudy").addEventListener("click", async () => {
    const ok = await copy();
    toast(ok ? "결과가 복사됐어요. 열린 오픈채팅방 입력창을 길게 눌러 '붙여넣기' 하면 그대로 올라갑니다." : "복사하지 못했어요. 결과 화면을 캡처해서 올려 주세요.");
    if (window.trlCount) window.trlCount("kakao");
    window.open("https://invite.kakao.com/tc/p7OX5rMjd0", "_blank", "noopener");
  });
  $("#rCopy").addEventListener("click", async (e) => { e.target.textContent = (await copy()) ? "복사됐어요 ✓" : "복사 실패"; });
}

/* ───────── 5. 오프라인 모임 · 아카이브 · 커리큘럼 · 도서 ───────── */
const fmtD = (d, withYear) => { const x = new Date(d + "T00:00:00"); return `${withYear ? x.getFullYear() + "년 " : ""}${x.getMonth() + 1}월 ${x.getDate()}일(${DOW[x.getDay()]})`; };
const ampm = (t) => { if (!t) return ""; const [h, m] = t.split(":").map(Number); return `${h < 12 ? "오전" : "오후"} ${h % 12 || 12}시${m ? " " + m + "분" : ""}`; };
const dday = (d) => { const n = Math.round((new Date(d + "T00:00:00") - new Date(ymd(KST()) + "T00:00:00")) / 864e5); return n === 0 ? "오늘" : n > 0 ? `D-${n}` : ""; };
let archCat = "all";

async function loadStudies() {
  try {
    const [site, list, cur, books] = await Promise.all(["site", "studies", "curriculum", "books"].map((f) => fetch(`data/${f}.json?t=${Date.now()}`).then((r) => r.json())));
    const today = ymd(KST());
    // 오늘 열리는 모임은 사진이 올라오기 전까지 '다가오는 모임'으로 둔다
    const upcoming = list.filter((s) => s.date > today || (s.date === today && !(s.photos || []).length)).sort((a, b) => a.date.localeCompare(b.date));
    const nextOf = (k) => upcoming.find((s) => s.series === k);
    const ups = ["regular", "book"].map(nextOf).filter(Boolean).sort((a, b) => a.date.localeCompare(b.date));
    const label = (s) => { const se = site.series[s.series] || {}; return `${se.emoji || ""} ${se.short || ""}${s.no ? ` ${s.no}회` : ""}`; };

    const nt = site.notice || {};
    window.__pinNotice = !!(nt.pin && nt.text && (!nt.until || nt.until >= today));
    if (window.__pinNotice) { $("#notice").innerHTML = `<div class="wrap">📢 ${esc(nt.text)}</div>`; $("#notice").hidden = false; }
    else loadBand();                                       // 고정 공지(pin)가 없으면 맨 위 띠 = 최근 정시 브리핑 요약

    $("#heroStudy").innerHTML = `<p class="hc-tag">다음 그룹 스터디</p>` + ups.map((s, i) => `
      <a class="hc-item${i ? " sub" : ""}" href="study.html?id=${encodeURIComponent(s.id)}">
        <span class="hc-kind">${label(s)} <em>${dday(s.date)}</em></span>
        <span class="hc-title">「${esc(s.title)}」</span>
        <span class="hc-when">${fmtD(s.date)} ${ampm(s.time)} · 베델회관 7층</span>${s.date_note ? `<span class="hc-note">※ ${esc(s.date_note)}</span>` : ""}
      </a>`).join("") + `<a class="btn btn-kakao btn-block" href="${esc(site.kakao)}" target="_blank" rel="noopener">💬 카카오톡으로 참여하기</a>`;

    $("#upList").innerHTML = ups.map((s) => {
      const se = site.series[s.series] || {};
      return `<article class="up">
        <div class="up-top"><span class="up-kind">${label(s)}</span><span class="up-dday">${dday(s.date)}</span></div>
        <h3 class="up-title">${esc(s.title)}</h3>
        ${s.theme ? `<p class="up-theme">${esc(s.theme)}</p>` : ""}
        <ul class="up-meta">
          <li>🗓️ ${fmtD(s.date, true)} ${ampm(s.time)}${s.date_note ? `<br><span class="date-note">※ ${esc(s.date_note)}</span>` : ""}</li>
          <li>📍 ${esc(s.place || site.place)}</li>
          ${s.book ? `<li>📖 ${esc(s.book)}</li>` : ""}
        </ul>
        ${s.summary ? `<p class="up-sum">${esc(s.summary)}</p>` : ""}
        <p class="up-rule">${esc(se.name || "")} · ${esc(se.rule || "")}</p>
        <div class="up-btns"><a class="btn btn-kakao" href="${esc(site.kakao)}" target="_blank" rel="noopener">💬 참여 신청</a><a class="btn btn-ghost-dark" href="study.html?id=${encodeURIComponent(s.id)}">자세히</a></div>
      </article>`;
    }).join("") || `<p class="empty">다음 그룹 스터디 일정은 곧 안내합니다.</p>`;
    $("#studyInfo").innerHTML = `<ul><li>📍 ${esc(site.place)}</li><li>🅿️ ${esc(site.parking)}</li><li>☕ ${esc(site.free)}</li><li>👥 카카오톡 오픈채팅 ${esc(site.members)} · 참가비 무료 · 교육 목적 그룹 스터디</li></ul>`;

    const past = list.filter((s) => !upcoming.includes(s)).sort((a, b) => b.date.localeCompare(a.date));
    const nPhoto = past.reduce((n, s) => n + (s.photos || []).length, 0);
    const first = past[past.length - 1];
    const fd = first ? new Date(first.date + "T00:00:00") : null;
    $("#archStats").innerHTML = [
      [past.filter((s) => s.series === "regular").length + "회", "정기 스터디"],
      [past.filter((s) => s.series === "book").length + "회", "독서 토론"],
      [nPhoto + "장", "현장 사진"],
      [fd ? `${fd.getFullYear() % 100}.${fd.getMonth() + 1}~` : "-", "함께한 기간"],
    ].map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join("");
    let growth = null;                                    // 📒 가치 투자 성장 스토리(운영자 개인 공부 기록, 운영자 외 얼굴 모자이크)
    try { growth = await fetch(`data/growth.json?t=${Date.now()}`).then((r) => (r.ok ? r.json() : null)); } catch { growth = null; }
    const hasG = growth && (growth.photos || []).length;
    $("#archChips").innerHTML = [["all", "전체"], ["regular", "📈 정기 스터디"], ["book", "📚 독서 토론"], ...(hasG ? [["growth", "📒 " + growth.title]] : [])].map(([k, l]) => `<button class="chip${k === archCat ? " on" : ""}" data-k="${k}">${l}</button>`).join("");
    const draw = () => {
      if (archCat === "growth" && hasG) {
        $("#archList").innerHTML = `<p class="arc-intro">${esc(growth.intro || "")}</p>` + growth.photos.map((p, i) => {
          const d = new Date(p.date + "T00:00:00");
          return `<a class="arc" href="study.html?id=growth&p=${i}">
            <div class="arc-img"><img src="${esc(p.thumb)}" alt="${esc(growth.title)} ${esc(p.date)} 사진" loading="lazy"><span class="arc-month">${d.getFullYear() % 100}년 ${d.getMonth() + 1}월</span></div>
            <div class="arc-body"><p class="arc-date">📒 ${d.getMonth() + 1}/${d.getDate()}(${DOW[d.getDay()]})</p><h3 class="arc-title">${esc(growth.title)}</h3></div></a>`;
        }).join("");
        return;
      }
      const pick = (s) => archCat === "all" || s.series === archCat;
      $("#archList").innerHTML = ups.filter(pick).map((s) => archCard(s, true, label)).join("") + past.filter(pick).map((s) => archCard(s, false, label)).join("");
    };
    $("#archChips").onclick = (e) => { const b = e.target.closest(".chip"); if (!b) return; archCat = b.dataset.k; $("#archChips").querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c === b)); draw(); };
    draw();
    $("#archStamp").textContent = past[0] ? `마지막 기록 ${fmtD(past[0].date)}` : "";

    $("#curSub").textContent = `${cur.rule} · ${cur.flow}`;
    $("#curNote").textContent = `${cur.why} ${cur.note}`;
    const byDate = Object.fromEntries(list.filter((s) => s.series === "regular").map((s) => [s.date, s]));
    const nextReg = nextOf("regular");
    $("#curList").innerHTML = cur.parts.map((p) => `<div class="cur-part"><h3>${esc(p.name)}</h3><p>${esc(p.desc)}</p><ol>${p.items.map((it) => {
      const full = it.date.length === 10, done = full && it.date < today, st = byDate[it.date], isNext = !!(nextReg && nextReg.date === it.date);
      const tag = isNext ? `<em class="cur-next">다음 회차</em>` : done ? `<em class="cur-done">완료</em>` : "";
      const d = full ? fmtD(it.date) : it.date.replace("-", "년 ") + "월~";
      const inner = `<span class="cur-no">${it.no ? it.no + "회" : "2년차"}</span><span class="cur-d">${d}</span><span class="cur-t">${esc(it.topic)}</span>${tag}`;
      return `<li class="${done ? "done" : ""}${isNext ? " next" : ""}">${st ? `<a href="study.html?id=${encodeURIComponent(st.id)}">${inner}</a>` : `<div>${inner}</div>`}</li>`;
    }).join("")}</ol></div>`).join("");

    $("#bookSub").textContent = `${site.series.book.name} · ${books.rule}`;
    const sById = Object.fromEntries(list.map((s) => [s.id, s]));
    $("#bookList").innerHTML = books.books.map((b, i) => {
      const st = b.study && sById[b.study];
      const tag = st ? (upcoming.includes(st) ? `<em class="cur-next">${fmtD(st.date)} 예정</em>` : `<em class="cur-done">${fmtD(st.date)} 완료</em>`) : `<em class="bk-sel">선정 도서</em>`;
      const body = `<span class="bk-n">${i + 1}</span><span class="bk-t"><b>${esc(b.title)}</b><small>${esc(b.author)}</small></span>${tag}`;
      return `<li>${st ? `<a href="study.html?id=${encodeURIComponent(st.id)}">${body}</a>` : `<div>${body}</div>`}</li>`;
    }).join("");
  } catch (e) { console.error(e); }
}

/* ── 맨 위 띠: 하루 4번(07:20 오전 · 14:00 오후 · 20:05 저녁 · 22:15 밤·새벽) 정시 브리핑 기록에서 수치만 뽑아 고정 ── */
const BAND = { "07:20": ["🌅", "오전장 핵심 뉴스"], "14:00": ["🕑", "오후"], "20:05": ["🌆", "저녁"], "22:15": ["🌙", "밤·새벽"] };
const pc = (v) => v == null ? "" : `${v > 0 ? "+" : ""}${(+v).toFixed(2)}%`;
function bandText(h) {
  const P = [];
  const fut = (n) => ((h.eve || {}).fut || []).find((f) => f.name === n) || {};
  const oil = (n) => ((h.eve || {}).oil || []).find((f) => f.name === n) || {};
  const reg = h.reg || {}, kr = h.kr || {}, u = h.ust || {};
  const w = (h.watch || {}).items || [];
  const wt = w.filter((x) => x.px != null).map((x) => `${x.sym} ${pc(x.chg)}${x.three ? (x.open ? " 적삼병 조건 충족 중" : " 적삼병 조건 충족 마감") : x.bull === false ? " 음봉" : ""}`);
  if (h.slot === "07:20") {
    if (h.headline) return h.headline;
    if (reg.SP500) P.push(`미국 마감 S&P500 ${pc(reg.SP500.chg)} · 나스닥100 ${pc((reg.XYZ100 || {}).chg)}`);
    if (reg.SOXL) P.push(`SOXL ${pc(reg.SOXL.chg)}`);
    if (u["10Y"]) P.push(`미 10년물 ${u["10Y"].px.toFixed(3)}%`);
    P.push(...wt);
    if ((h.checkpoints || []).length) P.push(`오늘: ${h.checkpoints.slice(0, 2).map((c) => (c.time ? c.time + " " : "") + c.title).join(", ")}`);
  } else if (h.slot === "14:00") {
    if (kr.KOSPI) P.push(`코스피 ${pc(kr.KOSPI.chg)} · 코스닥 ${pc((kr.KOSDAQ || {}).chg)}`);
    if (kr.SMSN) P.push(`삼성전자 ${pc(kr.SMSN.chg)} · SK하이닉스 ${pc((kr.SKHX || {}).chg)}`);
    const m = (h.momentum || []).slice().sort((a, b) => b.momentum - a.momentum)[0];
    if (m) P.push(`섹터 모멘텀 1위 ${m.name}`);
  } else if (h.slot === "20:05") {
    const nx = ((h.eve || {}).nxt || []).slice(0, 2);
    if (nx.length) P.push(`넥장 마감 ${nx.map((r) => `${r.name} ${pc(r.chg)}`).join(" · ")}`);
    if (fut("S&P500").kr != null) P.push(`15:30 이후 S&P500 선물 ${pc(fut("S&P500").kr)} · 나스닥100 ${pc(fut("나스닥100").kr)}`);
    if (oil("WTI").kr != null) P.push(`WTI ${pc(oil("WTI").kr)}`);
    if (((h.eve || {}).tonight || [])[0]) P.push(`오늘 밤: ${h.eve.tonight[0].time} ${h.eve.tonight[0].title}`);
  } else {
    if (fut("S&P500").reg != null) P.push(`미국 개장 전 S&P500 선물 ${pc(fut("S&P500").reg)} · 나스닥100 ${pc(fut("나스닥100").reg)}(전일 종가 대비)`);
    if (oil("WTI").kr != null) P.push(`WTI ${pc(oil("WTI").kr)}(15:30 이후)`);
    P.push(...wt);
  }
  return P.join(" · ");
}
async function loadBand() {
  try {
    const b = await fetch(`data/briefs.json?t=${Math.floor(Date.now() / 60000)}`).then((r) => r.json());
    const h = b.find((x) => BAND[x.slot]);
    if (!h) return;
    const t = bandText(h);
    if (!t) return;
    const [ic, nm] = BAND[h.slot], d = h.day.slice(5).replace("-", "/").replace(/^0/, "");
    const slotLabel = h.headline ? `${hhmm(KST(new Date(h.at)))} KST 기준` : `(${h.slot} 정리)`;
    $("#notice").innerHTML = `<div class="wrap"><a href="#brief" class="band-a">${ic} <b>${d} ${nm}</b> <small>${slotLabel}</small> · ${esc(t)}</a></div>`;
    $("#notice").hidden = false;
  } catch { /* 띠 없이 */ }
}
setInterval(() => { const nt = window.__pinNotice; if (!nt) loadBand(); }, 60000);

function archCard(s, isNext, label) {
  const d = new Date(s.date + "T00:00:00");
  const ph = s.photos || [];
  const img = ph.length ? `<img src="${esc(ph[s.cover || 0].thumb)}" alt="${esc(s.title || "")} 현장 사진" loading="lazy"><span class="arc-cnt">📷 ${ph.length}</span>`
    : s.poster ? `<img src="${esc(s.poster.thumb)}" alt="${esc(s.title || "")} 안내 포스터" loading="lazy">`
    : `<div class="arc-ph"><span>${isNext ? "🗓️" : "📚"}</span>${isNext ? `${dday(s.date)} · 다음 스터디` : "사진 정리 중"}</div>`;
  return `<a class="arc${isNext ? " next" : ""}" href="study.html?id=${encodeURIComponent(s.id)}">
    <div class="arc-img">${img}<span class="arc-month">${isNext ? "예정" : `${d.getFullYear() % 100}년 ${d.getMonth() + 1}월`}</span></div>
    <div class="arc-body"><p class="arc-date">${label(s)} · ${d.getMonth() + 1}/${d.getDate()}(${DOW[d.getDay()]})</p>
    <h3 class="arc-title">${esc(s.title)}</h3><p class="arc-sub">${esc(s.book || s.theme || "")}</p></div></a>`;
}

/* ───────── 시작 ───────── */
loadHeadline(); loadTicks(); loadChecks(); loadStudies();   // 블로그 분석 글 피드는 2026-10-28 운영자 결정으로 뺌
setInterval(loadTicks, 30000);

