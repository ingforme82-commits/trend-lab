/* Trend Research Lab — 시세·체크포인트·피드·성향 테스트 */
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const KST = (d = new Date()) => new Date(d.getTime() + (d.getTimezoneOffset() + 540) * 60000);
const hhmm = (d) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const DOW = ["일", "월", "화", "수", "목", "금", "토"];

/* ───────── 1. 실시간 시세 (Hyperliquid) ───────── */
// SKHY(SK하이닉스 ADR) 10주 = 원주 1주(SEC F-6). 원주 환산가 = 한국 종가 ÷ 10 ÷ 원/달러 → ADR 프리미엄(11/16 운영자)
function skhyMeta(px) {
  const k = (window.trlKr || {}).SKHX, fx = ((window.trlBrief || {}).futures || []).find((y) => y.name === "원/달러" && y.src !== "하이퍼리퀴드");
  if (!k || !k.px || !fx || !fx.px || !px) return "";
  const par = k.px / 10 / fx.px, prem = (px / par - 1) * 100;
  return `<p class="t-meta">원주 환산 $${par.toFixed(2)} (한국 ${Math.round(k.px).toLocaleString("ko-KR")}원 ÷10 ÷${(+fx.px).toFixed(1)}) · 프리미엄 <b>${prem > 0 ? "+" : ""}${prem.toFixed(1)}%</b></p>`;
}

const TICKS = [
  { g: "🇰🇷 한국", sub: "코스피·대형주" },
  { k: "KOSPI", n: "코스피", d: 2, krOnly: true },
  { k: "KOSDAQ", n: "KOSDAQ", d: 2, krOnly: true },
  { k: "KR200", n: "코스피200", d: 2 },
  { k: "SMSN", n: "삼성전자", d: 2, u: "$", won: true },
  { k: "EWY", n: "EWY (한국 ETF)", d: 2, u: "$" },  { g: "🇺🇸 미국", sub: "지수·반도체" },
  { k: "SP500", n: "S&P500", d: 1 },
  { k: "XYZ100", n: "나스닥100", d: 0 },
  { k: "DOW", n: "다우존스", d: 0, srv: true },
  { k: "SOXL", n: "SOXL (반도체 3배)", d: 2, u: "$" },
  { k: "DRAM", n: "DRAM (메모리 ETF)", d: 2, u: "$", lev: true },
  { k: "SKHY", n: "SKHY (SK하이닉스 ADR)", d: 2, u: "$", lev: true },
  { k: "MU", n: "MU (마이크론)", d: 2, u: "$", lev: true },
  { g: "🌐 Macro", sub: "환율·원자재·금리" },
  { k: "KRW", n: "원/달러", d: 1, suf: "원", fx: "원/달러" },
  { k: "CL", n: "WTI 무기한", d: 2, u: "$" },
  { k: "BRENTOIL", n: "브렌트유", d: 2, u: "$" },
  { k: "GC", n: "금 선물 (COMEX GC)", d: 2 },
  { k: "GOLD", n: "금 무기한 선물", d: 1, u: "$" },
  { k: "NATGAS", n: "천연가스", d: 3, u: "$" },
  { k: "DXY", n: "달러인덱스", d: 2, fx: "달러인덱스" },
  { k: "UST2Y", n: "미 2년물 금리", srv: "tnx", t: "2Y" },
  { k: "US10Y", n: "미 10년물 금리", srv: "tnx", t: "10Y" },
  { k: "UST30Y", n: "미 30년물 금리", srv: "tnx", t: "30Y" },
];
let lastPx = {};

async function loadTicks() {
  const putHTML = globalThis.trlViewport?.html || ((el, html) => { el.innerHTML = html; });
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
      if (t.g) return `<p class="tick-group" role="heading" aria-level="3">${t.g}${t.sub ? ` <small>${t.sub}</small>` : ""}</p>`;
      if (t.k === "GC") {
        const quote = (window.trlWorld || []).find((item) => item.sym === "GC=F");
        const valid = quote && Number.isFinite(quote.px) && quote.px > 0 && Number.isFinite(quote.chg) && Number.isFinite(quote.at) && quote.at > 0;
        if (!valid) return `<div class="tick" data-k="GC"><p class="t-name">${t.n}</p><p class="t-px">-</p><p class="fine">시세 확인 중</p></div>`;
        const c = quote.chg > 0.005 ? "c-up" : quote.chg < -0.005 ? "c-dn" : "c-fl";
        const stamp = new Date(quote.at).toLocaleString("en-GB", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
        const status = Date.now() - quote.at > 15 * 60000 ? "마지막 시세" : "지연 가능";
        return `<div class="tick" data-k="GC"><p class="t-name">${t.n}</p><p class="t-px">$${quote.px.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p><p class="t-ch ${c}">${quote.chg > 0 ? "+" : ""}${quote.chg.toFixed(2)}%</p><p class="fine">Yahoo Finance · ${stamp} KST · ${status}</p></div>`;
      }
      if (t.srv === "tnx") {                              // 미 국채 2·10·30년 금리(CNBC, 없으면 야후): 수준은 %, 변화는 bp
        const U = window.trlUst || {};
        const r = U[t.t] || (t.t === "10Y" ? window.trlTnx || {} : {});
        const sp = t.t === "10Y" && U["2Y"] && r.px ? ` · 2년물과 차 ${Math.round((r.px - U["2Y"].px) * 100)}bp` : "";
        if (!r.px) return `<div class="tick"><p class="t-name">${t.n}</p><p class="t-px">-</p><p class="fine">불러오는 중</p></div>`;
        const c3 = r.bp > 0.05 ? "c-up" : r.bp < -0.05 ? "c-dn" : "c-fl";
        const old = r.stale || !r.at || Date.now() - r.at > 30 * 60000;
        const status = r.market_note || (old ? "시세 지연 · 마지막 값" : "최근 시세");
        const stamp = r.at ? new Date(r.at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) + " KST" : "시각 미확인";
        return `<div class="tick" data-k="${t.k}"><p class="t-name">${t.n}</p><p class="t-px">${r.px.toFixed(3)}%</p><p class="t-ch ${c3}">${r.bp > 0 ? "▲" : r.bp < 0 ? "▼" : ""} ${r.bp > 0 ? "+" : ""}${r.bp.toFixed(1)}bp</p><p class="fine" style="margin:2px 0 0">전일 ${r.prev}%${sp}${" · " + esc(status)}</p><p class="fine">${esc(r.src || "출처 미확인")} · ${esc(stamp)}</p></div>`;
      }
      if (t.fx) {                                         // 달러: CNBC(실패 시 야후) 24시간 환율 — 하이퍼리퀴드 환율 상품은 거래가 멈춰 쓰지 않음(11/16)
        const f = ((window.trlBrief || {}).futures || []).find((y) => y.name === t.fx && y.src !== "하이퍼리퀴드");
        if (!f) return `<div class="tick"><p class="t-name">${t.n}</p><p class="t-px">-</p><p class="fine">불러오는 중</p></div>`;
        const cf = f.chg > 0.005 ? "c-up" : f.chg < -0.005 ? "c-dn" : "c-fl";
        const nf = (v) => (+v).toLocaleString("ko-KR", { minimumFractionDigits: t.d, maximumFractionDigits: t.d }) + (t.suf || "");
        const stamp = f.at ? new Date(f.at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) + " KST" : "";
        return `<div class="tick" data-k="${t.k}"><p class="t-name">${t.n}</p><p class="t-px">${nf(f.px)}</p><p class="t-ch ${cf}">${f.chg > 0 ? "▲" : f.chg < 0 ? "▼" : ""} ${f.chg > 0 ? "+" : ""}${(+f.chg).toFixed(2)}% <small>24시간 시장</small></p><p class="fine" style="margin:2px 0 0">기준 ${esc(f.base || "전일 종가")} ${f.ref != null ? nf(f.ref) : "-"}</p><p class="fine">${esc(f.src || "")}${stamp ? " · " + stamp : ""}</p></div>`;
      }
      if (t.lev) {                                        // DRAM 등: 하이퍼리퀴드에 없음 → 1분 시세(levetf, 야후) · 실시간은 loadRt 가 덮어씀
        const x = ((window.trlLev || {}).items || []).find((y) => y.sym === t.k);
        if (!x || x.px == null) return `<div class="tick" data-k="${t.k}"><p class="t-name">${t.n}</p><p class="t-px">-</p><p class="fine">불러오는 중</p></div>`;
        const cl = x.chg > 0.005 ? "c-up" : x.chg < -0.005 ? "c-dn" : "c-fl";
        const ref = x.chg != null ? x.px / (1 + x.chg / 100) : null;
        return `<div class="tick" data-k="${t.k}"><p class="t-name">${t.n}</p><p class="t-px">$${(+x.px).toFixed(2)}</p><p class="t-ch ${cl}">${x.chg > 0 ? "▲" : x.chg < 0 ? "▼" : ""} ${x.chg > 0 ? "+" : ""}${(+x.chg).toFixed(2)}% <small>정규장</small></p><p class="fine" style="margin:2px 0 0">기준 전일 종가 ${ref ? "$" + ref.toFixed(2) : "-"}</p>${t.k === "DRAM" ? `<p class="t-meta">SK하이닉스·마이크론·삼성전자 비중 큼</p>` : ""}${t.k === "MU" ? `<p class="t-meta">미국 메모리 대장 — 삼성·하이닉스 업황 선행</p>` : ""}${t.k === "SKHY" ? skhyMeta(x.px) : ""}</div>`;
      }
      if (t.rt) {                                         // 실시간 체결 전용 칸(SK스퀘어): 마지막 체결이 15초 안이면 값, 아니면 안내
        const r = ((window.trlRt || {}).q || {})[t.k];
        if (r && r.px > 0 && r.ref > 0 && Date.now() - r.at < 15000) {
          const c = r.chg > 0.005 ? "c-up" : r.chg < -0.005 ? "c-dn" : "c-fl";
          return `<div class="tick" data-k="${t.k}" data-rt-at="${r.at}"><p class="t-name">${t.n}</p><p class="t-px">${Math.round(r.px).toLocaleString("ko-KR")}원</p><p class="t-ch ${c}">${r.chg > 0 ? "▲" : r.chg < 0 ? "▼" : ""} ${r.chg > 0 ? "+" : ""}${(+r.chg).toFixed(2)}% <small>${r.mk === "NXT" ? "넥스트레이드 체결" : "실시간 체결"}</small></p><p class="fine" style="margin:2px 0 0">기준 전일 종가 ${Math.round(r.ref).toLocaleString("ko-KR")}원</p></div>`;
        }
        const item = (window.trlChan?.groups || []).flatMap((group) => group.items || []).find((row) => row.code === "402340");
        const nx = item?.nxt;
        const age = Date.now() - nx?.at;
        const hasNxt = Number.isFinite(nx?.px) && nx.px > 0 && age >= -60000 && age < 7 * 86400e3;
        const stamp = hasNxt ? `${mdhm(nx.at)} KST` : "";
        const basis = hasNxt && nx.session === "애프터" && Number.isFinite(item.krx_close) && item.krx_close > 0 && mdhm(nx.at).split(" ")[0] === String(item.krx_close_day || "").replace(/\b0(?=\d)/g, "") ? item.krx_close : null;
        const chg = basis ? 100 * (nx.px / basis - 1) : null;
        const tone = chg > 0.005 ? "c-up" : chg < -0.005 ? "c-dn" : "c-fl";
        const label = hasNxt ? "NXT 마지막 체결" : "NXT 시세 없음";
        return `<div class="tick" data-k="${t.k}"><p class="t-name">${t.n}</p><p class="t-px">${hasNxt ? Math.round(nx.px).toLocaleString("ko-KR") + "원" : "—"}</p>${chg === null ? "" : `<p class="t-ch ${tone}">${chg > 0 ? "+" : ""}${chg.toFixed(2)}% <small>KRX 종가 대비</small></p>`}<p class="fine">${label}${stamp ? " · " + stamp : ""}</p></div>`;

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
      const x = t.krOnly ? null : map[t.k];
      const kr = (window.trlKr || {})[t.k];
      if (t.krOnly && !(kr && kr.px)) return `<div class="tick" data-k="${t.k}"><p class="t-name">${t.n}</p><p class="t-px">-</p><p class="fine">시세 확인 중</p></div>`;
      const sg = (v) => `<b class="${v > 0.005 ? "c-up" : v < -0.005 ? "c-dn" : "c-fl"}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</b>`;
      const h24 = x && +x.prevDayPx ? (+x.markPx / +x.prevDayPx - 1) * 100 : null;
      const meta = x && +x.dayNtlVlm > 0 ? `<p class="t-meta">24h 거래대금 $${fmtVol(+x.dayNtlVlm)}${x.oraclePx && +x.oraclePx ? ` · 기초가격 대비 ${sg((+x.markPx / +x.oraclePx - 1) * 100)}` : ""}</p>` : "";
      if (kr && kr.px && (kr.open || !x)) {               // 한국 정규장: 한국거래소 실시간 가격 · 전일 종가 대비(네이버)
        const ck = kr.chg > 0.005 ? "c-up" : kr.chg < -0.005 ? "c-dn" : "c-fl";
        const v = ["KR200", "KOSPI", "KOSDAQ"].includes(t.k) ? kr.px.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : Math.round(kr.px).toLocaleString("ko-KR") + "원";
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
      return `<div class="tick${flash}" data-k="${t.k}"><p class="t-name">${t.n}</p><p class="t-px">${val}</p><p class="t-ch ${cls}">${ch > 0 ? "▲" : ch < 0 ? "▼" : ""} ${ch > 0 ? "+" : ""}${ch.toFixed(2)}% <small>24시간</small></p><p class="fine" style="margin:2px 0 0">기준 24시간 전 ${(t.u || "") + prev.toLocaleString("ko-KR", { minimumFractionDigits: t.d, maximumFractionDigits: t.d }) + (t.suf || "")}</p>${won}${reg}${meta}</div>`;
    }).join("");
    putHTML($("#tickGrid"), html);
    setTimeout(() => document.querySelectorAll(".tick.flash").forEach((e) => e.classList.remove("flash")), 900);
    const k = KST();
    window.trlTickAt = Date.now();
    $("#tickStamp").innerHTML = `<span class="ts-dot" aria-hidden="true"></span>마지막 업데이트 <b>${k.getMonth() + 1}/${k.getDate()}(${DOW[k.getDay()]}) ${hhmm(k)}:${String(k.getSeconds()).padStart(2, "0")} KST</b> <span data-tick-ago></span> · 출처별 시세 기준 시각 확인`;
    renderPulse();
  } catch (e) {
    $("#tickStamp").innerHTML = window.trlTickAt
      ? `<span class="ts-dot is-stale" aria-hidden="true"></span><span class="is-stale">시세를 새로 받지 못했습니다</span> · 마지막 업데이트 <span data-tick-ago></span> 값 표시 중`
      : "시세를 불러오지 못했습니다. 잠시 후 다시 시도합니다.";
    renderPulse();
  }
  tickAgo();
}

/* ── Market Pulse · 현재 시장(2026-11-21 UX) ──
 * 숫자는 아래 시세 칸(#tickGrid)에 이미 그려진 값을 그대로 옮긴다 — 같은 출처·같은 기준, 새 계산·추정 없음.
 * 칸이 아직 없으면 '-'(불러오는 중)로 둔다. 장 상태는 한국 시간·뉴욕 시간 기준 시간표(휴장일은 한국거래소 응답이 있으면 그 값). */
const PULSE = [["KOSPI", "코스피", "KR200"], ["KOSDAQ", "KOSDAQ"], ["XYZ100", "나스닥100"], ["SP500", "S&P500"], ["KRW", "원/달러"], ["CL", "WTI 원유"], ["GC", "COMEX GC"], ["US10Y", "미 10년물"]];
function marketSessions(now = Date.now()) {
  const k = KST(new Date(now)), kd = k.getDay(), km = k.getHours() * 60 + k.getMinutes();
  const kr = (window.trlKr || {}).KOSPI || (window.trlKr || {}).KR200;
  let krS, krOn = false;
  if (kd === 0 || kd === 6) krS = "주말 휴장";
  else if (km >= 540 && km < 930) { krOn = kr && kr.open === false ? false : true; krS = krOn ? "정규장 장중" : "휴장"; }
  else if (km >= 480 && km < 530) { krS = "NXT 프리마켓"; krOn = true; }
  else if (km >= 930 && km < 1200) { krS = "정규장 마감 · NXT 애프터"; krOn = true; }
  else krS = km < 480 ? "장 시작 전" : "장 마감";
  const ny = new Date(new Date(now).toLocaleString("en-US", { timeZone: "America/New_York" })), nd = ny.getDay(), nm = ny.getHours() * 60 + ny.getMinutes();
  let usS, usOn = false;
  if (nd === 0 || nd === 6) usS = "주말 휴장";
  else if (nm >= 240 && nm < 570) { usS = "프리마켓"; usOn = true; }
  else if (nm >= 570 && nm < 960) { usS = "정규장 장중"; usOn = true; }
  else if (nm >= 960 && nm < 1200) { usS = "애프터마켓"; usOn = true; }
  else usS = "장 마감";
  return [["🇰🇷 한국", krS, krOn], ["🇺🇸 미국", usS, usOn]];
}
function pulseItems() {
  const grid = $("#tickGrid");
  const tile = (k) => grid && grid.querySelector(`.tick[data-k="${k}"]`);
  return PULSE.map(([k, n, alt]) => {
    const el = tile(k) || (alt && tile(alt));
    const name = el && alt && !tile(k) ? (el.querySelector(".t-name")?.textContent || n) : n;
    const v = el?.querySelector(".t-px")?.textContent.trim();
    const chEl = el?.querySelector(".t-ch");
    const cls = chEl ? (chEl.classList.contains("c-up") ? "c-up" : chEl.classList.contains("c-dn") ? "c-dn" : "c-fl") : "c-fl";
    const ch = chEl ? (chEl.childNodes[0]?.textContent || chEl.textContent).replace(/\s+/g, " ").trim() : "";
    const basis = chEl?.querySelector("small")?.textContent || "";
    return { name, v: v && v !== "-" ? v : null, ch, cls, basis };
  });
}
function renderPulse() {
  const items = pulseItems(), sess = marketSessions();
  const sessHtml = sess.map(([m, t, on]) => `<li class="${on ? "on" : ""}"><b>${m}</b> ${t}</li>`).join("");
  const li = (x) => `<li><span class="pg-n">${esc(x.name)}</span><span class="pg-v">${x.v ? esc(x.v) : "-"}</span><span class="pg-c ${x.v ? x.cls : "c-fl"}">${x.v ? esc(x.ch) + (x.basis ? ` <small>${esc(x.basis)}</small>` : "") : "불러오는 중"}</span></li>`;
  for (const [s, g] of [["#heroPulseSess", "#heroPulseGrid"], ["#mktNowSess", "#mktNowGrid"]]) {
    const se = $(s), ge = $(g); if (!se || !ge) continue;
    if (se.innerHTML !== sessHtml) se.innerHTML = sessHtml;
    const html = items.map(li).join("");
    if (ge.innerHTML !== html) ge.innerHTML = html;
  }
}
function tickAgo() {
  const at = window.trlTickAt;
  const old = at && Date.now() - at > 120000;
  const txt = at ? (() => { const s = Math.max(0, Math.round((Date.now() - at) / 1000)); return s < 60 ? `${s}초 전` : `${Math.floor(s / 60)}분 전`; })() : "";
  document.querySelectorAll("[data-tick-ago]").forEach((e) => { e.textContent = txt ? `(${txt})` : ""; e.classList.toggle("is-stale", !!old); });
  const dot = document.querySelector("#tickStamp .ts-dot"); if (dot) dot.classList.toggle("is-stale", !!old);
  const pa = $("#heroPulseAt");
  if (pa) { const k = at ? KST(new Date(at)) : null; pa.textContent = k ? `${hhmm(k)} KST 기준 · ${txt}` : "시세 불러오는 중"; pa.classList.toggle("is-stale", !!old); }
}
setInterval(tickAgo, 1000);
setInterval(() => { const s = marketSessions(); const h = s.map(([m, t, on]) => `<li class="${on ? "on" : ""}"><b>${m}</b> ${t}</li>`).join(""); for (const id of ["#heroPulseSess", "#mktNowSess"]) { const e = $(id); if (e && e.innerHTML !== h) e.innerHTML = h; } }, 60000);

const fmtVol = (v) => (v >= 1e9 ? (v / 1e9).toFixed(1) + "B" : v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : Math.round(v || 0) + "");
const KSTof = (ms) => new Date(ms + (new Date().getTimezoneOffset() + 540) * 60000);
const mdhm = (ms) => { const d = KSTof(ms); return `${d.getMonth() + 1}/${d.getDate()} ${hhmm(d)}`; };

/* ───────── 2. 체크포인트 ───────── */
async function fetchCheckpoints() {
  const validate = async (response) => {
    if (!response.ok) throw Error("Checkpoint feed unavailable");
    const rows = await response.json();
    if (!Array.isArray(rows) || !rows.length || rows.some((row) =>
      !row || !/^\d{4}-\d{2}-\d{2}$/.test(row.date) || typeof row.title !== "string")) {
      throw Error("Invalid checkpoint feed");
    }
    return rows;
  };
  const query = "?t=" + Math.floor(Date.now() / 60000);
  try {
    const live = "https://raw.githubusercontent.com/ingforme82-commits/trend-lab/main/data/checkpoints.json";
    return await validate(await fetch(live + query, { signal: AbortSignal.timeout(3500) }));
  } catch {
    return validate(await fetch("data/checkpoints.json" + query));
  }
}

async function loadChecks() {
  const putHTML = globalThis.trlViewport?.html || ((el, html) => { el.innerHTML = html; });
  try {
    const list = await fetchCheckpoints();
    const today = ymd(KST());
    // 오늘 일정 중 시각이 지난 것은 내린다(11/18 운영자 "시간 지난 건 지나고 최신화로") — 시각 없는 오늘 일정은 하루 동안 둔다
    const k = KST(), nowHM = String(k.getHours()).padStart(2, "0") + ":" + String(k.getMinutes()).padStart(2, "0");
    const hmOf = (t) => { const m = String(t || "").match(/(\d{1,2}):(\d{2})/); return m ? m[1].padStart(2, "0") + ":" + m[2] : ""; };
    const items = list.filter((c) => c.date > today || (c.date === today && (!hmOf(c.time) || hmOf(c.time) >= nowHM))).sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || ""))).slice(0, 8);
    const html = items.length ? items.map((c) => {
      const d = new Date(c.date + "T00:00:00");
      return `<li class="${c.date === today ? "today" : ""}"><span class="c-date">${d.getMonth() + 1}/${d.getDate()}(${DOW[d.getDay()]})${c.time ? " " + esc(c.time) : ""}</span><p class="c-title">${esc(c.title)}</p>${c.note ? `<p class="c-note">${esc(c.note)}</p>` : ""}</li>`;
    }).join("") : `<li><p class="c-title">다음 일정은 곧 업데이트됩니다.</p></li>`;
    putHTML($("#checkList"), html);
  } catch { /* 체크포인트 없으면 섹션만 비움 */ }
}

/* ───────── 2-0. 📅 미국 주요 실적 일정(data/earnings.json — tools/earnings_cal.py, Finnhub·야후 교차 확인, 11/18) ───────── */
async function loadEarnings() {
  const putHTML = globalThis.trlViewport?.html || ((el, html) => { el.innerHTML = html; });
  try {
    const read = (url, fallback) => fetch(url).then((r) => { if (!r.ok) throw new Error("calendar unavailable"); return r.json(); }).catch(() => fallback);
    const [j, checkpoints] = await Promise.all([
      read(`data/earnings.json?t=${Math.floor(Date.now() / 600000)}`, {}),
      read(`data/checkpoints.json?t=${Math.floor(Date.now() / 600000)}`, [])
    ]);
    const today = ymd(KST());
    const until = ymd(new Date(KST().getTime() + 21 * 864e5)), from = ymd(new Date(KST().getTime() - 2 * 864e5));
    const ipos = (Array.isArray(checkpoints) ? checkpoints : []).filter((x) => x.kind === "ipo" && x.date >= today && x.date <= until)
      .map((x) => ({...x, event_type: "ipo", priority: x.priority || 0}));
    // 11/22 UX: 발표 시각(kst_date + kst 의 마지막 'n시', 시각 미정이면 그날 끝)이 지났는데 실제치가 없으면
    //  '예상'만 남은 대기 항목이므로 내린다. 실제치가 있는 항목은 지난 2일 창 그대로 결과를 보여 준다.
    const relAt = (x) => {
      const d = x.kst_date || x.date; if (!d) return Infinity;
      const hs = String(x.kst || "").match(/(\d{1,2})시/g);
      return hs ? Date.parse(`${d}T${hs[hs.length - 1].replace("시", "").padStart(2, "0")}:00:00+09:00`) : Date.parse(`${d}T00:00:00+09:00`) + 864e5;
    };
    const waiting = (x) => x.eps_act == null && x.rev_act == null && Date.now() >= relAt(x);
    const items = [...ipos, ...(j.items || []).filter((x) => x.date >= from && x.date <= until && !waiting(x))]
      .sort((a, b) => (b.priority || 0) - (a.priority || 0) || a.date.localeCompare(b.date)).slice(0, 24);
    if (!items.length) { $("#earnings").hidden = true; return; }
    const bn = (v) => v == null ? "" : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`;
    const pct = (v) => v == null ? "" : ` <b class="${v >= 0 ? "eu" : "ed"}">${v > 0 ? "+" : ""}${v}%</b>`;
    const html = items.map((x) => {
      if (x.event_type === "ipo") return `<li class="${x.date === today ? "today" : ""}"><span class="c-date">미국 ${esc(x.market_date || x.date)} · ${esc(x.timing || "정확한 한국 시각 미정")}</span><p class="c-title">${esc(x.title)} <small>${esc(x.sym || "")} · IPO</small></p><p class="c-note">${esc(x.note || "")}</p><p class="c-note">출처: ${esc(x.source || "확인 중")}</p></li>`;
      const d = new Date(x.date + "T00:00:00"), done = x.eps_act != null || x.rev_act != null;
      const est = x.eps_est != null ? `예상 EPS $${(+x.eps_est).toFixed(2)}${x.rev_est ? ` · 매출 ${bn(x.rev_est)}` : ""}` : "";
      const act = done ? `<br>실제 EPS ${x.eps_act != null ? "$" + (+x.eps_act).toFixed(2) + pct(x.eps_sur) : "-"}${x.rev_act != null ? ` · 매출 ${bn(x.rev_act)}${pct(x.rev_sur)}` : ""}` : "";
      const warn = x.check === "확정" ? "" : `<p class="c-note">⚠ ${esc(x.check)}</p>`;
      return `<li class="${(x.kst_date || x.date) === today ? "today" : ""}"><span class="c-date">${d.getMonth() + 1}/${d.getDate()}(${DOW[d.getDay()]}) ${x.kst === "시각 미정" ? "미국 · 발표 시각 미정" : `미국 ${esc(x.hour)} · 한국 ${esc(x.kst)}`}</span>`
        + `<p class="c-title">${esc(x.name)} <small>${esc(x.sym)} · ${esc(x.sector)}</small></p><p class="c-note">${est}${act}</p>${warn}</li>`;
    }).join("");
    putHTML($("#earnList"), html);
    $("#earnStamp").textContent = j.updated ? `${j.updated} 기준` : "";
    $("#earnings").hidden = false;
  } catch { /* 개별 출처 실패는 다른 일정까지 숨기지 않는다 */ }
}

/* ───────── 2-1. 📌 주요 이슈(data/headline.json, 운영자가 올림 · 사실·수치만 · 외부 링크 없음) ───────── */
// 자동 카드(⚡ 지수 급변 · 📈 금리·유가·환율)는 news.json 'auto_issues'(1분)로 받아 맨 위에 — news.js 가 window.trlAuto 를 채우고 다시 그린다(11/13)
let hlData = { items: [], updated: "" };
async function loadHeadline() {
  try { hlData = await (await fetch(`data/headline.json?t=${Date.now()}`)).json(); } catch { /* 없음 */ }
  renderHeadline();
}
// 11/19 운영자 "오늘 주요 이슈도 실시간 업데이트": 카드에 watch(정규식)가 있으면 사이트 속보(1분)에서 관련 소식 최신 5건을 카드 아래에 붙인다.
// 정리 본문은 운영자 확인분 그대로 두고, 새 소식은 출처·시각과 함께 따로 — 한 곳 보도는 '1곳' 표시(교차 확인 원칙)
function hlLive(x) {
  if (!x.watch) return "";
  let re; try { re = new RegExp(x.watch, "i"); } catch { return ""; }
  const since = Date.now() - 12 * 3600e3, seen = new Set();
  const rows = (window.trlNews || []).filter((n) => n.ts >= since && re.test(`${n.text || ""} ${n.orig || ""}`))
    .sort((a, b) => b.ts - a.ts).filter((n) => { const k = String(n.text).replace(/[^0-9A-Za-z가-힣]/g, "").slice(0, 24); if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 5);
  if (!rows.length) return "";
  const t = (ms) => { const d = KSTof(ms); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  return `<div class="hl-live"><p class="hl-live-h">관련 속보</p><ul>${rows.map((n) =>
    `<li><time>${t(n.ts)}</time> <span class="hl-live-src">${esc(n.src)}${(n.nsrc || 1) > 1 ? ` 외 ${n.nsrc - 1}곳` : " · 1곳"}</span> ${esc(n.text)}</li>`).join("")}</ul></div>`;
}
// 11/20 운영자: 주요 이슈도 추세 판단과 같은 시간대 순서 — 08~16시 한국 먼저, 16~20시 한국·미국, 20~08시 미국 먼저.
// 카드 시장은 mkt(us·kr·g) 값이 있으면 그것, 없으면 태그·제목으로 추정. 같은 시장 안에서는 메인 카드 먼저, 그다음 원래 순서.
const HL_US = /🇺🇸|🌙|미국|뉴욕|나스닥|S&P|다우|앤트로픽|\bANT\b|엔비디아|SOXL|FOMC|연준/;
const HL_KR = /🇰🇷|한국|코스피|코스닥|국내|조선|외국인·기관/;
function hlMkt(x) {
  if (x.mkt) return x.mkt;
  const t = `${x.tag || ""} ${x.title || ""}`;
  return HL_US.test(x.tag || "") ? "us" : HL_KR.test(x.tag || "") ? "kr" : HL_US.test(t) && !HL_KR.test(t) ? "us" : HL_KR.test(t) && !HL_US.test(t) ? "kr" : "g";
}
// 11/22 UX(기한 지난 문구 자동 내림): '장중' 카드(태그·when 에 '장중')는 그 장이 끝나면 내린다.
//  11/23 운영자(decisions/trading.md): 국내 장중 = 08:00~20:00(NXT 프리·KRX 정규장·NXT 애프터) → 국내 카드는 20:00(NXT 마감)에 내림.
//  미국은 그대로 정규장 마감(뉴욕 16:00). marketSessions 와 같은 시간표 — 새 수치 없음.
//  작성 시각은 카드 when(예: "11/19 23:35 KST", "11/10(화) 10시 42분 기준")에서 읽고, 못 읽으면 지금 그 장이 장중일 때만 둔다
//  (국내 = 평일 08:00~20:00·휴장 아님, 미국 = 정규장 중).
//  시장을 정할 수 없는 카드(g)는 until 날짜만 따른다.
function hlWhenAt(when, now = Date.now()) {
  const m = String(when || "").match(/(\d{1,2})(?:\/|월\s*)(\d{1,2})일?\s*(?:\([^)]*\))?\s*(\d{1,2})(?::|시\s*)(\d{2})?/);
  if (!m) return null;
  const k = KST(new Date(now)), mo = +m[1], d = +m[2], hh = +m[3], mi = +(m[4] || 0);
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || hh > 23 || mi > 59) return null;
  const y = k.getFullYear() - (mo > k.getMonth() + 1 ? 1 : 0);
  return Date.UTC(y, mo - 1, d, hh, mi) - 9 * 3600e3;
}
function sessCloseAfter(mkt, t) {
  if (mkt === "kr") { const k = KST(new Date(t)); return Math.max(t, Date.UTC(k.getFullYear(), k.getMonth(), k.getDate(), 20, 0) - 9 * 3600e3); }
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(new Date(t)).map((x) => [x.type, x.value]));
  const off = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute) - Math.floor(t / 60000) * 60000;   // 뉴욕 − UTC
  return Math.max(t, Date.UTC(+p.year, +p.month - 1, +p.day, 16, 0) - off);
}
function hlStale(x, now = Date.now()) {
  if (!x || !/장중/.test(`${x.tag || ""} ${x.when || ""}`)) return false;
  const mk = hlMkt(x); if (mk !== "kr" && mk !== "us") return false;
  const t = hlWhenAt(x.when, now);
  if (t != null) return now >= sessCloseAfter(mk, t);
  if (mk === "us") return marketSessions(now)[1][1] !== "정규장 장중";
  const k = KST(new Date(now)), km = k.getHours() * 60 + k.getMinutes(), d = k.getDay();
  return d === 0 || d === 6 || km < 480 || km >= 1200 || marketSessions(now)[0][1] === "휴장";
}
window.trlHlStale = hlStale;
function hlOrder(items) {
  const hr = KST().getHours();
  const slot = hr >= 8 && hr < 16 ? ["kr", "g", "us"] : hr >= 16 && hr < 20 ? ["kr", "us", "g"] : ["us", "g", "kr"];
  return items.map((x, i) => ({x, i, r: slot.indexOf(hlMkt(x))})).sort((a, b) => a.r - b.r || (b.x.main ? 1 : 0) - (a.x.main ? 1 : 0) || a.i - b.i).map((o) => o.x);
}
// 추세 판단에 표시된 시장별 최신 거래일 일봉의 시가·종가를 비교한다.
function hlTone(market) {
  const groups = window.trlChan?.groups || [];
  const now = KST(), kstHour = now.getHours();
  const region = market === "g" ? (kstHour >= 8 && kstHour < 20 ? "kr" : "us") : market;
  const rows = new Map();
  for (const group of groups) {
    if ((group.cc === "kr_index" ? "kr" : group.cc) !== region) continue;
    for (const item of group.items) {
      if (region === "us" && item.code.endsWith("=F")) continue;
      const bar = item.rows?.at(-1);
      if (typeof bar?.[0] === "string" && bar[1] > 0 && bar[4] > 0) rows.set(item.code, bar);
    }
  }
  const dated = [...rows.values()].map(([day, open, , , close]) => {
    const [month, date] = day.split("/").map(Number);
    const year = now.getFullYear() - (month > now.getMonth() + 1 ? 1 : 0);
    return [Date.UTC(year, month - 1, date), Math.sign(close - open)];
  });
  const latest = Math.max(...dated.map(([day]) => day));
  const score = dated.reduce((sum, [day, direction]) => sum + (day === latest ? direction : 0), 0);
  return score > 0 ? "hl-up" : score < 0 ? "hl-down" : "";
}
// 11/21: 카드에 i18n.{en,…} 이 있으면 그 언어 화면에서 사람이 쓴 번역을 그대로 쓰고 자동 번역은 건너뛴다(translate="no").
//  숫자가 한국어 단위에 붙은 문장(87.79달러입니다·16시~20시)은 자동 번역이 자주 깨져서 중요 카드만 직접 번역해 둔다.
const pageLang = (() => { try { const q = new URL(location.href).searchParams.get("lang"); return (q || document.documentElement.lang || "ko").toLowerCase(); } catch { return "ko"; } })();
function hlLang(x) {
  const t = x && x.i18n && (x.i18n[pageLang] || x.i18n[pageLang.split("-")[0]]);
  return t ? { ...x, ...t, _fixed: true } : x;
}
window.trlHlLang = hlLang;
function renderHeadlineRaw() {
  try {
    const h = hlData || {};
    const today = ymd(KST());
    const auto = (window.trlAuto || []).filter((x) => (!x.until || x.until >= today) && !hlStale(x));
    const tags = new Set(auto.map((x) => x.tag));
    const items = hlOrder([...auto, ...(h.items || []).filter((x) => (!x.until || x.until >= today) && !hlStale(x) && !tags.has(x.tag))]);
    if (!items.length) { $("#headline").hidden = true; return; }   // 11/22: 전부 기한이 지나면 지난 카드를 남기지 않고 칸을 내린다
    $("#hlList").innerHTML = items.map((x0) => { const x = hlLang(x0), nt = x._fixed ? ' translate="no"' : ""; return `<article class="hl-card${x.main ? ` hl-main ${hlTone(hlMkt(x))}` : ""}" data-viewport-key="headline:${esc(x0.tag || x0.title)}">
      <p class="hl-tag">${x.main ? '<span class="hl-badge">메인</span>' : ""}<span${nt}>${esc(x.tag || "")}${x.when ? ` <small>${esc(x.when)}</small>` : ""}</span></p>
      <h3 class="hl-title"${nt}>${esc(x.title)}</h3>
      <ul class="hl-pts"${nt}>${(x.points || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
      ${hlLive(x)}
      ${x.source ? (x._fixed ? `<p class="hl-src" translate="no">${esc(x.src_label || "Source")}: ${esc(x.source)}</p>` : `<p class="hl-src">출처: ${esc(x.source)}</p>`) : ""}
    </article>`; }).join("");
    $("#hlStamp").textContent = h.updated ? `${h.updated} 정리` : "";
    $("#headline").hidden = false;
  } catch { /* 주요 이슈 없으면 칸 숨김 */ }
}
function renderHeadline() {
  return globalThis.trlViewport ? globalThis.trlViewport.update(renderHeadlineRaw) : renderHeadlineRaw();
}
window.renderHeadline = renderHeadline;

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
        <div class="up-btns"><a class="btn btn-kakao" href="${esc(site.kakao)}" target="_blank" rel="noopener">💬 참여 신청</a></div>
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
    const growthPhotos = (growth?.photos || []).map((photo, originalIndex) => ({ ...photo, originalIndex }))
      .sort((a, b) => b.date.localeCompare(a.date));
    const hasG = growthPhotos.length > 0;
    const growthCard = (p) => {
      return `<a class="arc" href="study.html?id=growth&p=${p.originalIndex}">
        <div class="arc-img"><img src="${esc(p.thumb)}" alt="${esc(growth.title)} ${esc(p.date)} 사진" loading="lazy"></div>
        <div class="arc-body"><p class="arc-date">📒 ${fmtD(p.date, true)}</p><h3 class="arc-title">${esc(growth.title)}</h3></div></a>`;
    };
    $("#archChips").innerHTML = [["all", "전체"], ["regular", "📈 정기 스터디"], ["book", "📚 독서 토론"], ...(hasG ? [["growth", "📒 " + growth.title]] : [])].map(([k, l]) => `<button class="chip${k === archCat ? " on" : ""}" data-k="${k}">${l}</button>`).join("");
    const latestRecord = [past[0]?.date, growthPhotos[0]?.date].filter(Boolean).sort().at(-1);
    $("#archStamp").textContent = latestRecord ? `마지막 기록 ${fmtD(latestRecord, true)}` : "";
    const draw = () => {
      if (archCat === "growth" && hasG) {
        $("#archList").innerHTML = `<p class="arc-intro">${esc(growth.intro || "")}</p>` + growthPhotos.map(growthCard).join("");
        return;
      }
      const pick = (s) => archCat === "all" || s.series === archCat;
      const history = past.filter(pick).map((s) => ({ date: s.date, render: () => archCard(s, false, label) }));
      if (archCat === "all") {
        history.push(...growthPhotos.map((p) => ({ date: p.date, render: () => growthCard(p) })));
        history.sort((a, b) => b.date.localeCompare(a.date));
      }
      $("#archList").innerHTML = ups.filter(pick).map((s) => archCard(s, true, label)).join("") + history.map((row) => row.render()).join("");
    };
    $("#archChips").onclick = (e) => { const b = e.target.closest(".chip"); if (!b) return; archCat = b.dataset.k; $("#archChips").querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c === b)); draw(); };
    draw();

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
      const tag = st ? (upcoming.includes(st) ? `<em class="cur-next">${fmtD(st.date)}${st.confirmed ? "" : " 예정"}</em>` : `<em class="cur-done">${fmtD(st.date)} 완료</em>`) : `<em class="bk-sel">선정 도서</em>`;
      const body = `<span class="bk-n">${i + 1}</span><span class="bk-t"><b>${esc(b.title)}</b><small>${esc(b.author)}</small></span>${tag}`;
      return `<li>${st ? `<a href="study.html?id=${encodeURIComponent(st.id)}">${body}</a>` : `<div>${body}</div>`}</li>`;
    }).join("");
  } catch (e) { console.error(e); }
}

/* ── 맨 위 띠: 하루 6번(06:10 새벽 · 07:20 오전 · 14:00 오후 · 15:30 국내 마감 · 20:05 저녁 · 22:15 밤·새벽) 정시 브리핑 기록에서 수치만 뽑아 고정 ── */
const BAND = { "06:10": ["🌄", "새벽 미국 마감·이슈"], "07:20": ["🌅", "오전장 핵심 뉴스"], "14:00": ["🕑", "오후"], "15:30": ["🔔", "국내 마감(종가)"], "20:05": ["🌆", "저녁"], "22:15": ["🌙", "밤·새벽"] };
const pc = (v) => v == null ? "" : `${v > 0 ? "+" : ""}${(+v).toFixed(2)}%`;
function bandText(h) {
  const P = [];
  const fut = (n) => ((h.eve || {}).fut || []).find((f) => f.name === n) || {};
  const oil = (n) => ((h.eve || {}).oil || []).find((f) => f.name === n) || {};
  const reg = h.reg || {}, kr = h.kr || {}, u = h.ust || {};
  const w = (h.watch || {}).items || [];
  const wt = w.filter((x) => x.px != null).map((x) => `${x.sym} ${pc(x.chg)}${x.three ? (x.open ? " 적삼병 조건 충족 중" : " 적삼병 조건 충족 마감") : x.bull === false ? " 음봉" : ""}`);
  if (h.slot === "07:20" || h.slot === "06:10") {
    if (h.headline) return h.headline;
    if (reg.SP500) P.push(`미국 마감 S&P500 ${pc(reg.SP500.chg)} · 나스닥100 ${pc((reg.XYZ100 || {}).chg)}`);
    if (reg.SOXL) P.push(`SOXL ${pc(reg.SOXL.chg)}`);
    if (u["10Y"]) P.push(`미 10년물 ${u["10Y"].px.toFixed(3)}%`);
    P.push(...wt);
    if ((h.checkpoints || []).length) P.push(`오늘: ${h.checkpoints.slice(0, 2).map((c) => (c.time ? c.time + " " : "") + c.title).join(", ")}`);
  } else if (h.slot === "14:00" || h.slot === "15:30") {
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

function liveBand() {
  const now = new Date(), k = KST(now), minute = k.getHours() * 60 + k.getMinutes();
  const weekday = k.getDay() > 0 && k.getDay() < 6;
  const etParts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(now);
  const part = (name) => (etParts.find((x) => x.type === name) || {}).value || "";
  const etMinute = (+part("hour")) * 60 + (+part("minute"));
  const etWeekday = !["Sat", "Sun"].includes(part("weekday"));
  const usRegular = etWeekday && etMinute >= 570 && etMinute < 960;
  const usAfter = etWeekday && etMinute >= 960 && etMinute < 1200;
  const kr = window.trlKr || {}, idx = kr.KOSPI || {}, kosdaq = kr.KOSDAQ || {};
  const s7 = window.trlS7 || {}, flows = window.trlFlows || {}, brief = window.trlBrief || {};
  const reg = window.trlReg || {}, lev = (window.trlLev || {}).items || [];
  const out = [], pcLive = (v) => v == null ? "" : (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%";
  const cash = (v) => v == null ? "" : "$" + Number(v).toFixed(2);
  const money = (v) => v >= 1e12 ? (v / 1e12).toFixed(1) + "조" : Math.round(v / 1e8).toLocaleString("ko-KR") + "억";
  const latest = () => {
    const hs = brief.heads || [];
    const h = hs.find((x) => /코스피|코스닥|삼성|하이닉스|반도체|미국|연준|나스닥|S&P|PCE|금리|일본|중국|실적|선물|트럼프|이란|호르무즈|협상|전쟁|원유|유가/.test(x.text || ""));
    return h ? "속보 " + String(h.text).replace(/\s+/g, " ").slice(0, 74) + (h.src ? " · " + h.src : "") : "";
  };
  const stockEt = () => {
    const rows = new Map();
    for (const g of (flows.groups || [])) for (const r of (g.rows || [])) if (r.code) rows.set(r.code, r);
    let total = 0;
    for (const r of rows.values()) if (r.val != null && r.val_krx != null) total += Math.max(0, r.val - r.val_krx);
    return total;
  };
  const etfExt = () => lev.filter((x) => x.ext && x.ext.px != null && ["SOXL", "KORU"].includes(x.sym)).map((x) => {
    const e = x.ext, stamp = hhmm(KST(new Date(e.checked_at || e.at || 0)));
    const sn = e.sess === "day" ? "주간거래" : e.sess === "pre" ? "프리장" : "애프터";
    return e.live && Date.now() - (e.checked_at || e.at || 0) < 5 * 60000
      ? x.sym + " " + sn + " " + cash(e.px) + " (" + pcLive(e.chg) + " · " + stamp + " 한국 시간 조회" + (e.stale ? " · 마지막 체결 " + hhmm(KST(new Date(e.at))) : "") + ")"
      : x.sym + " " + sn + " 마지막 체결 " + cash(e.px) + " (" + pcLive(e.chg) + " · " + hhmm(KST(new Date(e.at || e.checked_at || 0))) + ")";
  });
  const future = (name) => (brief.futures || []).find((x) => x.name === name);
  // 한국은 거래소 마지막 종가가 기준, 24시간 시세는 '야간·24시간 · 종가 이후 변화'로 따로(11/15 운영자 승인)
  const krClose = () => [["KOSPI", "코스피"], ["KOSDAQ", "코스닥"]].filter(([c]) => kr[c] && kr[c].px != null && !kr[c].open)
    .map(([c, n]) => n + " " + Number(kr[c].px).toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + " (" + pcLive(kr[c].chg) + ")")
    .join(" · ") + (idx.at && !idx.open ? " · " + (KST(new Date(idx.at)).getMonth() + 1) + "/" + KST(new Date(idx.at)).getDate() + " 마감" : "");
  const live24 = () => [["코스피200", ""], ["나스닥100", ""], ["S&P500", ""], ["WTI", "$"], ["브렌트", "$"], ["금", "$"], ["원/달러", ""]]
    .map(([n, u]) => { const f = future(n); if (!f) return "";
      const v = u + Number(f.px).toLocaleString("en-US", { maximumFractionDigits: 2 });
      const rv = (x) => u + Number(x).toLocaleString("en-US", { maximumFractionDigits: 3 });
      return f.since_close != null ? n + " 야간·24시간 " + v + " (종가 이후 " + pcLive(f.since_close) + (f.close_ref != null ? ", 종가 시각 " + rv(f.close_ref) : "") + ")"
        : n + " " + v + " (" + pcLive(f.chg) + (f.ref != null ? ", 기준 " + (f.base || "") + " " + rv(f.ref) : "") + ")"; })
    .filter(Boolean).join(" · ");
  let icon = "", title = "", at = window.trlUpdated || Date.now();
  if (!weekday) {
    // 주말: 정시 브리핑 대신 지금 시각 24시간 시세 하나로(운영자 지시 — 기준을 나누지 않음)
    icon = "🛰️"; title = "주말 · 한국 종가 + 24시간 시세";
    if (krClose()) out.push(krClose());
    const kf = future("코스피200 야간선물") || future("코스피200 주간선물");
    if (kf) out.push(kf.name + " " + Number(kf.px).toLocaleString("en-US", { maximumFractionDigits: 2 }) + " (" + (kf.base || "") + (kf.ref != null ? " " + Number(kf.ref).toLocaleString("en-US", { maximumFractionDigits: 2 }) : "") + " 대비 " + pcLive(kf.chg) + ", NH)");
    out.push(live24());
    if (latest()) out.push(latest());
    at = brief.at || at;
  } else if (minute >= 930 && minute < 1200) {
    icon = "🏁"; title = "KRX 마감";
    if (idx.px != null) out.push("코스피 " + Number(idx.px).toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + " (" + pcLive(idx.chg) + ")");
    if (kosdaq.px != null) out.push("코스닥 " + Number(kosdaq.px).toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + " (" + pcLive(kosdaq.chg) + ")");
    if (s7.reconcile) out.push("S7 시세 확인 중");
    else if (s7.s7) out.push("S7 기여 " + Number(s7.s7.pts).toFixed(1) + "p (" + s7.s7.share + "%)");
    const breadth = s7.kospi || {};
    if (breadth.up != null && breadth.dn != null) out.push("상승/하락 " + breadth.up + "/" + breadth.dn);
    if (breadth.frgn != null && breadth.org != null) out.push("외국인 " + Math.round(breadth.frgn).toLocaleString("ko-KR") + "억 · 기관 " + Math.round(breadth.org).toLocaleString("ko-KR") + "억");
    if (latest()) out.push(latest());
    at = idx.at || s7.at || at;
  } else if (usRegular) {
    icon = "🇺🇸"; title = "미국 정규장";
    if (reg.SP500) out.push("S&P500 " + pcLive(reg.SP500.chg));
    if (reg.XYZ100) out.push("나스닥100 " + pcLive(reg.XYZ100.chg));
    for (const x of lev) if (["SOXL", "KORU"].includes(x.sym) && x.px != null) out.push(x.sym + " " + cash(x.px) + " (" + pcLive(x.chg) + ")");
    const wti = future("WTI"), brent = future("브렌트");
    if (wti || brent) out.push([wti && "WTI " + cash(wti.px), brent && "브렌트 " + cash(brent.px)].filter(Boolean).join(" · "));
    if (latest()) out.push(latest());
    at = Math.max(reg.SP500 && reg.SP500.at || 0, reg.XYZ100 && reg.XYZ100.at || 0, window.trlLev && window.trlLev.at || 0) || at;
  } else if (minute >= 300 && minute < 930) {
    icon = minute < 540 ? "🌅" : "📊";
    title = minute < 540 ? "미국 마감 · 한국 장전" : (minute < 720 ? "한국 오전장" : "한국 오후장") + " · 미국 마감";   // 오전장 09:00~12:00, 오후장 12:00~15:30
    if (idx.px != null) out.push("코스피 " + Number(idx.px).toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + " (" + pcLive(idx.chg) + ")");
    if (kosdaq.px != null) out.push("코스닥 " + Number(kosdaq.px).toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + " (" + pcLive(kosdaq.chg) + ")");
    const names = [["삼성전자", kr.SMSN], ["SK하이닉스", kr.SKHX]];
    const stockText = names.filter(([, q]) => q && q.chg != null).map(([n, q]) => n + " " + pcLive(q.chg));
    if (stockText.length) out.push(stockText.join(" · "));
    const us = [reg.SP500 && "S&P500 " + pcLive(reg.SP500.chg), reg.XYZ100 && "나스닥100 " + pcLive(reg.XYZ100.chg)].filter(Boolean);
    if (us.length) out.push("미국 정규장 마감 " + us.join(" · "));
    const ext = etfExt();
    if (ext.length) out.push(ext.join(" · "));
    const wti = future("WTI"), brent = future("브렌트");
    if (wti || brent) out.push([wti && "WTI " + cash(wti.px) + " (" + pcLive(wti.chg) + ")", brent && "브렌트 " + cash(brent.px) + " (" + pcLive(brent.chg) + ")"].filter(Boolean).join(" · "));
    if (latest()) out.push(latest());
    at = Math.max(idx.at || 0, kr.SMSN && kr.SMSN.at || 0, kr.SKHX && kr.SKHX.at || 0, brief.at || 0) || at;
  } else if (minute >= 1200) {
    icon = "🌆"; title = usAfter ? "미국 마감·애프터장" : "넥스트레이드 마감 · 미국 프리장";
    if (idx.px != null) out.push("코스피 종가 " + Number(idx.px).toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + " (" + pcLive(idx.chg) + ")");
    const nxt = stockEt();
    if (nxt > 0) out.push("관심 종목 NXT 거래대금 " + money(nxt));
    out.push(...etfExt());
    const sp = future("S&P500"), nq = future("나스닥100");
    if (sp || nq) out.push("24시간 지수 참고 " + (sp ? "S&P500 " + pcLive(sp.chg) : "") + (sp && nq ? " · " : "") + (nq ? "나스닥100 " + pcLive(nq.chg) : ""));
    if (latest()) out.push(latest());
    at = Math.max(idx.at || 0, window.trlLev && window.trlLev.at || 0, brief.at || 0) || at;
  } else {
    icon = "🛰️"; title = "24시간 시세";
    out.push(live24());
    if (latest()) out.push(latest());
    at = brief.at || at;
  }
  const time = hhmm(KST(new Date(at))) + " 기준";
  return { icon, title, text: out.filter(Boolean).join(" · "), date: (k.getMonth() + 1) + "/" + k.getDate(), time };
}
// 11/20 운영자(TSMC): 띠에는 '지금도 유효한' 5일선 돌파만 — 그 종목 장이 열려 있고 현재가가 아직 5일선(정규장 종가 기준) 위일 때.
// 장중 잠깐 넘었다가 다시 밀렸거나 장이 끝난 시그널은 띠에서 내린다(추세 판단 기록에는 남음).
function bandSignal(now = Date.now()) {
  const c = window.trlChan || {}, by = {};
  (c.groups || []).forEach((g) => (g.items || []).forEach((it) => { by[it.code] = {...it, ...(it.display || {}), cc: g.cc}; }));
  const s = (c.signals || []).find((s) => {
    const it = by[s.code];
    if (!it || !it.live || it.stale || !(it.ma5 > 0) || !(it.px > 0)) return false;
    if (!bandPhase(it, now)) return false;                         // 국내 20시 뒤 등 장중이 아니면 띠에 안 올림
    return it.px > it.ma5 && now - s.ts < 8 * 3600e3;
  });
  return s && {...s, text: bandSigText(s.text, bandPhase(by[s.code], now))};
}
// dev-20261122-2300: 띠 시점 — 국내 = '장중(정규장)'·'장중(NXT 프리·애프터)'(11/23 운영자: 평일 08:00~20:00 장중),
//  미국·일본 = 정규장 '장중', 시간외 = 세션명(프리마켓·애프터마켓·선물 24시간). live 가 아니면 null(띠에 안 나옴).
function bandPhase(it, now = Date.now()) {
  if (!it || !it.live) return null;
  const ses = it.session && it.session !== "정규장" ? String(it.session) : "";
  if (it.cc === "kr" || it.cc === "kr_index") {
    const k = new Date(now + 9 * 3600e3), d = k.getUTCDay(), m = k.getUTCHours() * 60 + k.getUTCMinutes();
    return d > 0 && d < 6 && m >= 480 && m < 1200 ? `장중(${ses || "정규장"})` : null;
  }
  return ses || "장중";
}
// chan.py 기록 원문 '📐 5일선 돌파 시그널 — …' 은 그대로 두고 화면 띠에서만 '📐 <시점> 5일선 상향 관측 — …' 으로 바꾼다.
function bandSigText(text, phase) {
  return String(text || "").replace(/^📐 5일선 돌파 시그널/, "📐 " + phase + " 5일선 상향 관측");
}
async function loadBand() {
  const putHTML = globalThis.trlViewport?.html || ((el, html) => { el.innerHTML = html; });
  if (window.__pinNotice) return;
  try {
    const live = liveBand();
    const sig = bandSignal();                                        // 📐 5일선 돌파 시그널이 있으면 띠 맨 앞(11/17)
    const sigHtml = sig ? '<a href="#chan" class="bi band-sig">' + esc(sig.text) + '</a>' : '';
    if (live) {
      const node = $("#notice");
      if (!node) return;
      putHTML(node, bandHtml(live.icon + ' <b>' + live.date + ' ' + live.title + '</b> <small>' + live.time + '</small>', live.text, sigHtml));
      node.hidden = false;
      bandFit();
      return;
    }
    const b = await fetch('data/briefs.json?t=' + Math.floor(Date.now() / 60000)).then((r) => r.json());
    const h = b.find((x) => BAND[x.slot]);
    if (!h) return;
    const t = bandText(h);
    if (!t) return;
    const parts = BAND[h.slot], d = h.day.slice(5).replace("-", "/").replace(/^0/, "");
    const slotLabel = h.headline ? hhmm(KST(new Date(h.at))) + " KST 기준" : "(" + h.slot + " 정리)";
    putHTML($("#notice"), bandHtml(parts[0] + ' <b>' + d + " " + parts[1] + '</b> <small>' + slotLabel + '</small>', t, sigHtml));
    $("#notice").hidden = false;
    bandFit();
  } catch { /* 띠 없이 */ }
}
// 11/17 운영자: 띠는 스크롤해도 늘 보이게(메뉴 막대 안) · 흐르지 않고 고정 — 표식(날짜·장)은 왼쪽 고정,
// 항목은 ' · ' 단위로 끊어 단어가 잘리지 않게(PC 최대 2줄, 모바일 1줄은 손가락으로 밀어 보기)
function bandSplit(s) {
  const out = []; let depth = 0, cur = "";
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === "(") depth++; else if (ch === ")") depth = Math.max(0, depth - 1);
    if (depth === 0 && s.startsWith(" · ", i)) { out.push(cur); cur = ""; i += 2; continue; }
    cur += ch;
  }
  out.push(cur);
  return out.map((x) => x.trim()).filter(Boolean);
}
function bandHtml(label, text, sigHtml) {
  const items = bandSplit(text || "").map((x) => '<a href="#news" class="bi">' + esc(x) + '</a>').join("");
  return '<div class="wrap band-w" title="' + esc(text || "") + '"><a href="#news" class="band-lab">' + label + '</a><div class="band-items">' + (sigHtml || "") + items + '</div></div>';
}
function bandFit() { /* 11/17: 흐르는 띠 없앰(고정 표시) — 예전 호출 자리 유지 */ }
window.addEventListener("resize", () => bandFit());
window.loadBand = loadBand;
setInterval(() => { if (!window.__pinNotice) loadBand(); }, 60000);

function archCard(s, isNext, label) {
  const d = new Date(s.date + "T00:00:00");
  const ph = s.photos || [];
  const img = ph.length ? `<img src="${esc(ph[s.cover || 0].thumb)}" alt="${esc(s.title || "")} 현장 사진" loading="lazy"><span class="arc-cnt">📷 ${ph.length}</span>`
    : s.poster ? `<img src="${esc(s.poster.thumb)}" alt="${esc(s.title || "")} 안내 포스터" loading="lazy">`
    : `<div class="arc-ph"><span>${isNext ? "🗓️" : "📚"}</span>${isNext ? `${dday(s.date)} · 다음 스터디` : "사진 정리 중"}</div>`;
  return `<a class="arc${isNext ? " next" : ""}" href="study.html?id=${encodeURIComponent(s.id)}">
    <div class="arc-img">${img}<span class="arc-month">${isNext && !s.confirmed ? "예정" : `${d.getFullYear() % 100}년 ${d.getMonth() + 1}월`}</span></div>
    <div class="arc-body"><p class="arc-date">${label(s)} · ${d.getMonth() + 1}/${d.getDate()}(${DOW[d.getDay()]})</p>
    <h3 class="arc-title">${esc(s.title)}</h3><p class="arc-sub">${esc(s.book || s.theme || "")}</p></div></a>`;
}

/* ───────── 시작 ───────── */
/* ───────── 1-1. 실시간 체결(Oracle 서버 KIS 웹소켓 → Cloudflare 터널, 2초마다) — 11/16 운영자 ───────── */
// news.json 'rt_url' 이 있을 때만. 받은 종목 칸은 '실시간 체결' 값으로 바꾸고 기준(전일 종가)을 숫자로 적는다.
const RT_NAMES = { KOSPI: "코스피", KR200: "코스피200", KOSDAQ: "코스닥", SOXL: "SOXL (반도체 3배)", DRAM: "DRAM (메모리 ETF)", SKHY: "SKHY (SK하이닉스 ADR)", MU: "MU (마이크론)", NVDA: "NVDA", KORU: "KORU (한국 3배)", SMSN: "삼성전자", SKHX: "SK하이닉스", SKSQ: "SK스퀘어" };
let rtBusy = false;
function expireRtRaw() {
  document.querySelectorAll('.tick[data-rt-at]').forEach(el => {
    if (Date.now() - Number(el.dataset.rtAt) > 15000) {
      const label = el.querySelector('.t-ch small');
      if (label) label.textContent = '수신 지연 · 마지막 값';
    }
  });
}
function expireRt() {
  return globalThis.trlViewport ? globalThis.trlViewport.update(expireRtRaw) : expireRtRaw();
}
async function loadRt() {
  const putHTML = globalThis.trlViewport?.html || ((el, html) => { el.innerHTML = html; });
  expireRt();
  const u = window.trlRtUrl;
  if (!u || document.hidden || rtBusy) return;
  rtBusy = true;
  const started = performance.now();
  try {
    const response = await fetch(u + "/rt", { cache: "no-store", signal: AbortSignal.timeout(4000) });
    if (!response.ok) throw Error('Quote connection failed');
    const j = await response.json();
    window.trlRt = j;
    window.trlRtHealth = { checked: Date.now(), roundTripMs: performance.now() - started, ok: true };
    const now = Date.now();
    Object.entries(j.q || {}).forEach(([k, r]) => {
      if (!Object.hasOwn(RT_NAMES, k) || !r || !Number.isFinite(r.px) || r.px <= 0 || !Number.isFinite(r.ref) || r.ref <= 0 || !Number.isFinite(r.chg) || !Number.isFinite(r.at) || r.at <= 0 || r.at > now + 1000 || now - r.at > 15000) return;
      const el = document.querySelector(`.tick[data-k="${k}"]`);
      if (!el) return;
      const c = r.chg > 0.005 ? "c-up" : r.chg < -0.005 ? "c-dn" : "c-fl";
      const won = k === "SMSN" || k === "SKHX" || k === "SKSQ";
      const nf = (v) => won ? Math.round(v).toLocaleString("ko-KR") + "원" : (["SOXL", "DRAM", "SKHY", "MU", "NVDA", "KORU"].includes(k) ? "$" : "") + (+v).toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const flash = el.dataset.rt && el.dataset.rt !== String(r.px) ? " flash" : "";
      el.dataset.rt = String(r.px);
      el.dataset.rtAt = String(r.at);
      el.className = "tick" + flash;
      putHTML(el, `<p class="t-name">${RT_NAMES[k] || k}</p><p class="t-px">${nf(r.px)}</p><p class="t-ch ${c}">${r.chg > 0 ? "▲" : r.chg < 0 ? "▼" : ""} ${r.chg > 0 ? "+" : ""}${(+r.chg).toFixed(2)}% <small>${r.mk === "NXT" ? "넥스트레이드 체결" : "실시간 체결"}</small></p><p class="fine" style="margin:2px 0 0">기준 전일 종가 ${nf(r.ref)}${r.mk ? ` · ${r.mk === "NXT" ? "넥스트레이드(NXT)" : "통합(KRX+NXT)"}` : ""}</p>${k === "SKHY" ? skhyMeta(r.px) : ""}<p class="t-meta">KIS 웹소켓 · ${hhmm(KSTof(r.at))}:${String(KSTof(r.at).getSeconds()).padStart(2, "0")}</p>`);
    });
  } catch { window.trlRtHealth = { checked: Date.now(), ok: false }; }
  finally { rtBusy = false; if (typeof renderPulse === "function") renderPulse(); window.dispatchEvent(new Event('trl:quotes')); }
}
setInterval(loadRt, 2000);

loadHeadline(); loadTicks(); loadChecks(); loadEarnings(); loadStudies();
setInterval(loadHeadline, 60000);   // 11/19 운영자: 주요 이슈도 1분마다(새 카드·관련 속보)
setInterval(loadChecks, 60000);   // 체크포인트: 시각이 지나면 1분 안에 내림   // 블로그 분석 글 피드는 2026-10-28 운영자 결정으로 뺌
setInterval(loadTicks, 30000);

/* ── 모바일 하단 메뉴: 지금 보고 있는 칸 표시(2026-11-21 UX) ── */
(() => {
  const nav = document.getElementById("bnav"); if (!nav) return;
  const links = [...nav.querySelectorAll("a[data-sec]")];
  let raf = 0;
  const pick = () => {
    raf = 0;
    const y = innerHeight * 0.35;
    const top = (id) => { const e = document.getElementById(id); return e ? e.getBoundingClientRect().top : Infinity; };
    const mk = document.getElementById("market"), mr = mk && mk.getBoundingClientRect();
    let cur = "today";
    if (top("research") <= y) cur = "research";
    if (top("lab") <= y) cur = "lab";
    if (cur === "today" && mr && mr.top <= y && mr.bottom > y) cur = "market";
    if (top("today") > innerHeight) cur = "";                         // 맨 위(첫 화면)에서는 표시 없음
    links.forEach((a) => a.dataset.sec === cur ? a.setAttribute("aria-current", "true") : a.removeAttribute("aria-current"));
  };
  addEventListener("scroll", () => { if (!raf) raf = requestAnimationFrame(pick); }, { passive: true });
  addEventListener("resize", () => { if (!raf) raf = requestAnimationFrame(pick); });
  pick();
})();
