/* 실시간 속보 · 변곡점 — 뉴스(live 브랜치 news.json)와 가격 변화를 시각으로 연결
   - 빨간 점(🔴)은 '변곡점(평소보다 크게 움직이기 시작한 구간) 직전 뉴스'에만 붙는다.
   - 해석은 사람이 쓴 '💡 해석' 노트(data/notes.json)로만 싣고 블로그 분석 글로 잇는다. */
"use strict";
(() => {
  const NEWS_URL = "https://raw.githubusercontent.com/ingforme82-commits/trend-lab/live/news.json";
  const API_URL = "https://api.github.com/repos/ingforme82-commits/trend-lab/contents/news.json?ref=live";
  // 작은 차트 카드: 하이퍼리퀴드 5분봉(xyz:) 또는 서버가 넣어 준 시계열(srv: 금리·달러)
  const CARDS = [
    { code: "NQ", k: "xyz:XYZ100", n: "나스닥100", d: 0 },
    { code: "K200", k: "xyz:KR200", n: "코스피200", d: 2 },
    { code: "WTI", k: "xyz:CL", n: "WTI", d: 2, u: "$" },
    { code: "US10Y", k: "srv:US10Y", n: "미 10년물 금리", d: 3, suf: "%", bp: true },
    { code: "DXY", k: "srv:DXY", n: "달러인덱스", d: 2 },
  ];
  const COIN = { NQ: "xyz:XYZ100", K200: "xyz:KR200", WTI: "xyz:CL", BRENT: "xyz:BRENTOIL", GOLD: "xyz:GOLD", US10Y: "srv:US10Y", DXY: "srv:DXY" };
  const REACT = CARDS.slice(0, 3);   // 목록의 '이후' 변화: 나스닥100·코스피200·WTI
  const H = 24;
  const q = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const kst = (ms) => new Date(ms + (new Date().getTimezoneOffset() + 540) * 60000);
  const hm = (ms) => { const d = kst(ms); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const ago = (ms) => { const m = Math.round((Date.now() - ms) / 60000); return m < 1 ? "방금" : m < 60 ? `${m}분 전` : m < 1440 ? `${Math.floor(m / 60)}시간 전` : `${Math.floor(m / 1440)}일 전`; };
  const setText = (s, t) => { const e = q(s); if (e) e.textContent = t; };
  const fmtMove = (m) => `${m.move > 0 ? "+" : ""}${m.move}${m.unit === "bp" ? "bp" : "%"}`;
  const eok = (v) => v >= 1e12 ? `${(v / 1e12).toFixed(1)}조` : `${Math.round(v / 1e8).toLocaleString("ko-KR")}억`;
  const cls = (v) => (v > 0.005 ? "c-up" : v < -0.005 ? "c-dn" : "c-fl");
  const pct = (v) => v == null ? "-" : `<b class="${cls(v)}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</b>`;

  let news = [], moves = [], series = {}, notes = [], candles = {}, candles1 = {}, sel = null, tag = "전체", shown = 15, health = null;
  // 속보 필터: 중요도·시간·검증·정렬(분류는 tag 칩)
  const flt = { imp: "all", hrs: 0, ver: "all", sort: "new" };
  let world = [], spot = [], trend = [], sectors = [], brief = null, briefs = [], kwFilter = null, momentum = null, flows = null, flowSort = "val", flowOpen = null;   // kwFilter: {label, rx}

  /* ── 데이터 ── */
  let apiBlockedUntil = 0;
  async function fetchNews() {
    if (Date.now() > apiBlockedUntil) {
      try {
        const r = await fetch(API_URL, { headers: { Accept: "application/vnd.github.raw+json" }, cache: "no-cache" });
        if (r.ok) return await r.json();
        if (r.status === 403 || r.status === 429) apiBlockedUntil = Date.now() + 20 * 60000;
      } catch { /* raw로 */ }
    }
    return (await fetch(`${NEWS_URL}?t=${Math.floor(Date.now() / 60000)}`)).json();
  }
  async function loadNews() {
    try {
      const j = await fetchNews();
      news = j.items || []; moves = j.moves || []; series = j.series || {}; health = j.health || null;
      world = j.world || []; spot = j.spot || []; trend = j.trending || []; sectors = j.sectors || []; brief = j.brief || null;
      window.trlDow = j.dow || {}; window.trlTnx = j.us10y || {}; window.trlUst = j.ust || {}; window.trlKr = j.kr || {}; window.trlReg = j.reg || {}; momentum = j.momentum || null; flows = j.flows || null; if (typeof window.loadTicks === "function" && !window.__tickRefreshed) { window.__tickRefreshed = true; window.loadTicks(); } window.trlSectors = sectors; window.trlWorld = world; window.trlSpot = spot; window.trlTrend = trend; window.trlNotesReady = true;
      window.trlMoves = moves; window.trlSeries = series; window.trlNews = news;
      drawHealth(j.updated);
      drawTicker();
    } catch { setText("#newsStamp", "속보를 불러오지 못했습니다."); }
  }
  async function loadNotes() {
    try { notes = await (await fetch(`data/notes.json?t=${Math.floor(Date.now() / 600000)}`)).json(); window.trlNotes = notes; } catch { /* 없음 */ }
  }
  async function loadCandles() {
    const end = Date.now(), start = end - H * 3600e3;
    await Promise.all(CARDS.filter((c) => c.k.startsWith("xyz:")).map(async (s) => {
      try {
        const r = await fetch("https://api.hyperliquid.xyz/info", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: "candleSnapshot", req: { coin: s.k, interval: "5m", startTime: start, endTime: end } }) });
        candles[s.k] = (await r.json()).map((c) => [c.t, +c.c]);
      } catch { /* 이전 값 유지 */ }
    }));
    // 속보 반응(보도 5분 전 기준 +5/+15/+30/+60분)은 1분봉으로
    await Promise.all(REACT.map(async (s) => {
      try {
        const r = await fetch("https://api.hyperliquid.xyz/info", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: "candleSnapshot", req: { coin: s.k, interval: "1m", startTime: start - 10 * 60000, endTime: end } }) });
        candles1[s.k] = (await r.json()).map((c) => [c.t, +c.c]);
      } catch { /* 이전 값 유지 */ }
    }));
  }
  // 시각 t 에 이미 마감된 마지막 1분봉 종가(없으면 null)
  const pxAt = (rows, t) => { let v = null; for (const [ot, c] of rows) { if (ot + 60000 <= t) v = c; else break; } return v; };
  const WIN = [5, 15, 30, 60];
  function windows(k, ts) {
    const rows = candles1[k] || [];
    if (rows.length < 2 || ts - 5 * 60000 < rows[0][0] + 60000) return null;      // 기준 가격(보도 5분 전)이 범위 밖
    const base = pxAt(rows, ts - 5 * 60000);
    if (!base) return null;
    const lastOpen = rows[rows.length - 1][0];                                    // 진행 중인 마지막 봉의 시작 시각
    return WIN.map((n) => { const t = ts + n * 60000; if (t > lastOpen) return { n, v: null }; const p = pxAt(rows, t); return { n, v: p ? (p / base - 1) * 100 : null }; });
  }
  window.trlWindows = windows;
  const reactKey = (n) => (n.tags || []).includes("중동·유가") ? REACT[2] : (n.tags || []).some((t) => ["한국", "반도체", "환율", "2차전지", "조선", "방산", "원전"].includes(t)) ? REACT[1] : REACT[0];
  const rowsOf = (k) => (k.startsWith("srv:") ? series[k.slice(4)] || [] : candles[k] || []);

  // 노트: 같은 자산 + 시간이 겹치는 변곡점에 붙는다
  const noteFor = (m) => notes.find((n) => n.assets.includes(m.asset) && Date.parse(n.from) <= m.end + 5 * 60000 && Date.parse(n.to) >= m.start - 5 * 60000);
  const movesOfNews = (ts) => moves.filter((m) => (m.news || []).includes(ts));

  /* ── 맨 위 띠: 변곡점 뉴스 먼저, 그다음 최신 속보 ── */
  let tickerKey = "";
  function drawTicker() {
    const box = q("#ticker"); if (!box) return;
    // 최근 1시간 안의 주요 뉴스 위주(중요도 순으로 고른 뒤 시간 순으로 흘림). 1시간 안에 5건이 안 되면 3시간까지 넓힌다
    const score = (n) => (n.pivot ? 8 : 0) + (n.hot ? 4 : 0) + (n.kind === "섹터 시세" ? 3 : 0)
      + ((n.tags || []).some((t) => ["중동·유가", "연준·금리", "반도체", "AI·빅테크", "한국", "지수"].includes(t)) ? 1 : 0)
      - (n.kind === "증권사 시황" || n.kind === "시황 분석" ? 2 : 0) - (/입찰|낙찰|응찰|Bid-to-Cover|\$거시경제/.test(n.text) ? 2 : 0);
    let span = 1;
    let recent = news.filter((n) => Date.now() - n.ts < 3600e3);
    if (recent.length < 5) { span = 3; recent = news.filter((n) => Date.now() - n.ts < 3 * 3600e3); }
    const pick = recent.map((n) => [score(n), n]).sort((a, b) => b[0] - a[0] || b[1].ts - a[1].ts).slice(0, 12).map((x) => x[1]).sort((a, b) => b.ts - a.ts);
    const key = span + ":" + pick.map((n) => n.ts + (n.pivot ? "p" : "")).join(",");
    if (!pick.length || key === tickerKey) return;
    tickerKey = key;
    const row = pick.map((n) => `<a class="tk-i${n.pivot ? " hot" : ""}" href="${q("#news") ? "#news" : "index.html#news"}" data-ts="${n.ts}"><b>${hm(n.ts)}</b>${n.pivot ? "🔴 " : ""}${n.lang === "en" ? "🌐 " : ""}${esc(n.text)}</a>`).join("");
    box.innerHTML = `<span class="tk-label">📡 주요 시황 <small>${span === 1 ? "최근 1시간" : "최근 3시간"}</small></span><div class="tk-view"><div class="tk-track" style="animation-duration:${Math.max(40, pick.length * 9)}s">${row}${row}</div></div>`;
    box.hidden = false;
  }

  /* ── '이후' 변화(5분봉) ── */
  function reaction(k, ts) {
    const c = rowsOf(k); if (!c || c.length < 2 || ts < c[0][0]) return null;
    let i = c.findIndex((x) => x[0] > ts); i = i === -1 ? c.length - 1 : Math.max(0, i - 1);
    const p0 = c[i][1], p1 = c[c.length - 1][1];
    return p0 ? (p1 / p0 - 1) * 100 : null;
  }

  /* ── 작은 차트 카드: 변곡점 구간 색칠 + 그 직전 뉴스에만 빨간 점 ── */
  function drawCharts() {
    q("#newsCharts").innerHTML = CARDS.map((s) => {
      const c = rowsOf(s.k);
      if (c.length < 2) return `<div class="nc"><p class="nc-n">${s.n}</p><p class="fine">${s.k.startsWith("srv:") ? "미국장 시간에 갱신" : "불러오는 중…"}</p></div>`;
      const W = 300, Hh = 76, t0 = c[0][0], t1 = c[c.length - 1][0];
      const vs = c.map((x) => x[1]), lo = Math.min(...vs), hi = Math.max(...vs), rg = hi - lo || 1;
      const X = (t) => Math.max(0, Math.min(W, ((t - t0) / (t1 - t0 || 1)) * W)), Y = (v) => Hh - 6 - ((v - lo) / rg) * (Hh - 12);
      const path = c.map((x, i) => `${i ? "L" : "M"}${X(x[0]).toFixed(1)},${Y(x[1]).toFixed(1)}`).join("");
      const last = vs[vs.length - 1], chg = s.bp ? (last - vs[0]) * 100 : (last / vs[0] - 1) * 100;
      const my = moves.filter((m) => m.asset === s.code && m.end >= t0);
      const zones = my.map((m) => `<rect x="${X(m.start).toFixed(1)}" y="0" width="${Math.max(2, X(m.end) - X(m.start)).toFixed(1)}" height="${Hh}" class="nc-zone ${m.move > 0 ? "up" : "dn"}"/>`).join("");
      const dots = my.flatMap((m) => m.news || []).filter((ts) => ts >= t0).map((ts) => {
        let i = c.findIndex((x) => x[0] > ts); i = i === -1 ? c.length - 1 : Math.max(0, i - 1);
        return `<circle cx="${X(ts).toFixed(1)}" cy="${Y(c[i][1]).toFixed(1)}" r="3.2" class="nc-dot"/>`;
      }).join("");
      const line = sel && sel >= t0 && sel <= t1 ? `<line x1="${X(sel).toFixed(1)}" x2="${X(sel).toFixed(1)}" y1="0" y2="${Hh}" class="nc-sel"/>` : "";
      const val = (s.u || "") + last.toLocaleString("ko-KR", { maximumFractionDigits: s.d, minimumFractionDigits: s.d }) + (s.suf || "");
      const chTxt = s.bp ? `<b class="${cls(chg)}">${chg > 0 ? "+" : ""}${chg.toFixed(1)}bp</b>` : pct(chg);
      return `<div class="nc" data-coin="${s.k}" role="button" tabindex="0"><div class="nc-h"><span class="nc-n">${s.n}</span><span class="nc-v">${val}</span>${chTxt}</div>
        <svg viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none" class="nc-svg">${zones}<path d="${path}" class="nc-line ${chg >= 0 ? "up" : "down"}"/>${dots}${line}</svg>
        <p class="nc-f">${my.length ? `변곡점 ${my.length}회 · ` : ""}최근 ${H}시간 · 누르면 1분봉</p></div>`;
    }).join("");
  }

  /* ── 시장을 움직인 순간(변곡점 카드) ── */
  function drawMoves() {
    const box = q("#moveList"); if (!box) return;
    const list = moves.filter((m) => Date.now() - m.start < 24 * 3600e3).slice(0, 8);
    if (!list.length) { box.innerHTML = `<p class="empty">최근 24시간 동안 평소보다 크게 움직인 구간이 없습니다.</p>`; return; }
    box.innerHTML = list.map((m) => {
      const nt = noteFor(m);
      const ns = m.items || (m.news || []).map((ts) => news.find((n) => n.ts === ts)).filter(Boolean);
      const others = Object.entries(m.others || {}).slice(0, 4).map(([k, v]) => `${esc(k)} <b class="${cls(v)}">${v > 0 ? "+" : ""}${v}${k.includes("금리") ? "bp" : "%"}</b>`).join(" · ");
      return `<article class="mv" data-asset="${m.asset}" data-start="${m.start}">
        <div class="mv-h"><span class="mv-a ${m.move > 0 ? "pos" : "neg"}">${esc(m.name)} ${m.move > 0 ? "▲" : "▼"} ${fmtMove(m)}</span>
          <span class="mv-t">${hm(m.start)}–${hm(m.end)} · 평소 변동폭의 ${m.ratio}배</span></div>
        ${others ? `<p class="mv-o">같은 구간 ${others}</p>` : ""}
        ${ns.length ? `<ul class="mv-n">${ns.map((n) => `<li><span class="mv-dot"></span><b>${hm(n.ts)}</b> ${n.lang === "en" ? "🌐 " : ""}${esc(n.text)} <small>${n.osrc ? `${esc(n.osrc)} · ${esc(n.src)} 경유` : esc(n.src)}</small></li>`).join("")}</ul>`
          : `<p class="mv-none">직전 15분 안에 관련 분야 뉴스가 없습니다(수급·기술적 움직임일 수 있음).</p>`}
        ${nt ? `<div class="mv-note"><b>💡 ${esc(nt.title)}</b><p>${esc(nt.text)}</p>${nt.post ? `<a href="posts/${encodeURIComponent(nt.post)}.html" target="_blank" rel="noopener">블로그 분석 글 보기 →</a>` : ""}</div>` : ""}
      </article>`;
    }).join("");
  }

  /* ── 해외 지수 ── */
  function drawWorld() {
    const box = q("#worldGrid"); if (!box) return;
    box.innerHTML = world.map((w) => {
      const old = Date.now() - w.at > 3 * 3600e3;
      return `<div class="tick"><p class="t-name">${esc(w.region)} · ${esc(w.name)}</p><p class="t-px">${w.px.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}</p>
        <p class="t-ch ${cls(w.chg)}">${w.chg > 0 ? "▲" : w.chg < 0 ? "▼" : ""} ${w.chg > 0 ? "+" : ""}${w.chg.toFixed(2)}%</p>
        <p class="fine" style="margin:2px 0 0">${w.live ? "24시간 거래" : old ? `${kst(w.at).getMonth() + 1}/${kst(w.at).getDate()} ${hm(w.at)} 마감` : `${hm(w.at)} 기준`}</p></div>`;
    }).join("");
  }

  /* ── 🔥 화제 종목(종목군): 한 칸에서 번갈아 보이기 ── */
  let spotIdx = 0, spotHold = false, spotTimer = null, memOpen = null;   // memOpen: "종목군id:심볼"
  // 하이퍼리퀴드에서 1분봉을 볼 수 있는 종목(그 외는 차트 버튼 대신 정규장 수치만)
  const HL_SYMS = new Set(["LITE", "CRWV", "NBIS", "IREN", "AAOI", "GLW", "INTC", "NVDA", "AMD", "MU", "TSM", "TSLA", "SPCX", "META", "MSFT", "GOOGL", "AMZN", "AAPL", "ORCL", "PLTR", "AVGO", "ARM", "MRVL", "QCOM", "LRCX", "AMAT", "ASML", "SMH", "SOXL", "COIN", "HOOD", "NFLX", "NET", "CRWD", "DELL", "IBM", "WDC", "SNDK", "GEV", "BE", "MAGS", "URNM", "XLE", "LLY", "RKLB", "MSTR", "CRCL", "BMNR", "RIVN", "HIMS", "MRNA", "CVX", "NOW", "SKHX", "SMSN"]);
  function spotCard(s) {
    let rx; try { rx = new RegExp(s.kw || s.name, "i"); } catch { rx = /$^/; }
    const rel = news.filter((n) => rx.test(n.text + " " + (n.orig || "") + " " + (n.sub || "")));
    const today = rel.filter((n) => Date.now() - n.ts < 24 * 3600e3).length;
    const mem = s.members || [];
    const head = s.avg ? `<span class="spot-px">평균</span><b class="${cls(s.chg)}">${s.chg > 0 ? "+" : ""}${(+s.chg).toFixed(2)}%</b>`
      : s.px ? `<span class="spot-px">$${(+s.px).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}</span><b class="${cls(s.chg)}">${s.chg > 0 ? "+" : ""}${(+s.chg).toFixed(2)}%</b>` : "";
    return `<article class="spot">
      <div class="spot-top"><b class="spot-n">${esc(s.name)}</b><span class="spot-m">${esc(s.market || "")} · ${esc(s.since || "")}부터</span>${head}</div>
      ${s.reason ? `<p class="spot-r">${esc(s.reason)}</p>` : ""}
      ${mem.length ? memBlock(s, mem) : ""}
      <p class="spot-c">최근 24시간 관련 속보 <b>${today}건</b></p>
      ${rel.length ? `<ul class="spot-news">${rel.slice(0, 3).map((n) => `<li><b>${hm(n.ts)}</b> ${n.pivot ? "🔴 " : ""}${esc(n.text)}</li>`).join("")}</ul>` : ""}
      <div class="spot-btns">${s.hl ? `<button class="btn btn-gold btn-sm" data-spot-chart="${esc(s.hl)}" data-spot-name="${esc(mem.length ? mem.find((m) => "xyz:" + m.sym === s.hl)?.name || s.name : s.name)}">1분봉 차트</button>` : ""}
        <button class="btn btn-ghost-dark btn-sm" data-spot-kw="${esc(s.kw || s.name)}" data-spot-name="${esc(s.name)}">관련 속보 보기</button></div>
    </article>`;
  }
  // 통화별 가격 표시(지수는 숫자만)
  const money = (m) => {
    const v = (+m.px).toLocaleString("ko-KR", { maximumFractionDigits: m.cur === "KRW" ? 0 : 2 });
    if ((m.sym || "").startsWith("^")) return v;
    return m.cur === "KRW" ? v + "원" : m.cur === "JPY" ? "¥" + v : "$" + v;
  };
  // 종목군 구성 종목: 이름 버튼만 → 누르면 그 종목 상세
  function memBlock(s, mem) {
    const key = (m) => `${s.id}:${m.sym}`;
    const open = mem.find((m) => memOpen === key(m));
    const btns = mem.map((m) => `<button class="mem-b${open === m ? " on" : ""}" data-mem="${esc(key(m))}">${esc(m.name)}</button>`).join("");
    let detail = "";
    if (open) {
      let rx; try { rx = new RegExp(`${open.name}|\\b${open.sym}\\b`, "i"); } catch { rx = /$^/; }
      const rel = news.filter((n) => rx.test(n.text + " " + (n.orig || "") + " " + (n.sub || ""))).slice(0, 4);
      detail = `<div class="mem-d">
        <div class="mem-h"><b>${esc(open.name)}</b> <small>${esc(open.sym)}</small>
          <span class="mem-px">${money(open)}</span>
          <b class="${cls(open.chg)}">${open.chg > 0 ? "+" : ""}${open.chg.toFixed(2)}%</b>${open.stale ? `<em class="stale">전일 종가 기준</em>` : ""}
          ${open.to3m != null ? `<span class="dim">3개월 고점 대비 ${open.to3m > 0 ? "+" : ""}${open.to3m}%</span>` : ""}</div>
        ${rel.length ? `<ul class="spot-news">${rel.map((n) => `<li><b>${hm(n.ts)}</b> ${n.pivot ? "🔴 " : ""}${esc(n.text)} <small class="dim">${esc(n.osrc ? n.osrc + " · " + n.src + " 경유" : n.src)}</small></li>`).join("")}</ul>` : `<p class="dim" style="margin:4px 0">최근 관련 속보가 없습니다.</p>`}
        <div class="spot-btns">${HL_SYMS.has(open.sym) ? `<button class="btn btn-gold btn-sm" data-spot-chart="xyz:${esc(open.sym)}" data-spot-name="${esc(open.name)}">${esc(open.name)} 1분봉</button>` : ""}
          <button class="btn btn-ghost-dark btn-sm" data-mem="${esc(key(open))}">접기</button></div>
      </div>`;
    }
    return `<div class="mem-bar"><span class="mem-l">구성 종목</span>${btns}</div>${detail}`;
  }

  function drawSpot() {
    const box = q("#spotBox"); if (!box) return;
    if (!spot.length) { box.hidden = true; return; }
    box.hidden = false;
    spotIdx = ((spotIdx % spot.length) + spot.length) % spot.length;
    const nav = spot.length > 1 ? `<div class="spot-nav"><button class="spot-arrow" data-spot-step="-1" aria-label="이전">‹</button>${spot.map((x, i) =>
      `<button class="spot-dot${i === spotIdx ? " on" : ""}" data-spot-go="${i}" title="${esc(x.name)}">${esc(x.name)}</button>`).join("")}<button class="spot-arrow" data-spot-step="1" aria-label="다음">›</button></div>` : "";
    box.innerHTML = `<p class="spot-h">🔥 오늘의 주요 종목군 <small>미국 개장 30분 뒤 가격·뉴스 움직임으로 매일 자동 선정 · 추천 아님 · ${spot.length}개가 번갈아 보입니다</small></p>${nav}${spotCard(spot[spotIdx])}`;
    if (!spotTimer && spot.length > 1) {
      spotTimer = setInterval(() => { if (!spotHold && !memOpen) { spotIdx++; drawSpot(); } }, 8000);
      box.addEventListener("mouseenter", () => { spotHold = true; });
      box.addEventListener("mouseleave", () => { spotHold = false; });
      box.addEventListener("touchstart", () => { spotHold = true; setTimeout(() => { spotHold = false; }, 15000); }, { passive: true });
      box.addEventListener("click", (e) => {
        const st = e.target.closest("[data-spot-step]"), go = e.target.closest("[data-spot-go]");
        if (st) { spotIdx += +st.dataset.spotStep; memOpen = null; drawSpot(); }
        if (go) { spotIdx = +go.dataset.spotGo; memOpen = null; drawSpot(); }
        const mb = e.target.closest("[data-mem]");
        if (mb) { memOpen = memOpen === mb.dataset.mem ? null : mb.dataset.mem; drawSpot(); }
      });
    }
  }

  /* ── 섹터: 처음엔 '섹터 이름 + 평균'만 한 줄로, 누르면 그 섹터 종목 등락이 펼쳐진다 ── */
  let openSector = null;
  // 📈 섹터 모멘텀(국내): 4개 지표 순위 기반, 수급 미반영 — 섹터 단위만 공개
  function momHtml(m, compact) {
    const list = (m && m.sectors) || [];
    if (!list.length) return "";
    const bar = (v) => `<span class="mm-bar"><i style="width:${Math.max(2, Math.min(100, v))}%"></i></span>`;
    const rows = list.map((s, i) => `<li><b class="mm-rk">${i + 1}</b><span class="mm-n">${esc(s.name)}</span>${bar(s.momentum)}<b class="mm-v">${s.momentum.toFixed(0)}</b>
      ${compact ? "" : `<small class="dim">종목 중앙값 ${s.median.toFixed(0)} · 확산도 ${s.breadth.toFixed(0)} · 상승 ${s.up.toFixed(0)}%${s.share_shift != null ? ` · 거래대금 점유율 ×${s.share_shift.toFixed(2)}` : ""}</small>`}</li>`).join("");
    const st = m.at ? `${hm(m.at)} 기준${m.open ? "" : " · 장 마감·개장 전(전일 값 포함)"}${m.late ? ` · <b class="h-warn">지연 ${m.late}/${m.n}종목</b>` : ""}` : "";
    return `<div class="mm"><p class="mm-h">📈 섹터 모멘텀 <small>국내 · ${st}</small></p><ol class="mm-l">${rows}</ol>
      ${compact ? "" : `<p class="mm-f">거래대금 가속도·상대강도·5일선·신고가 근접 4개 지표의 종목 간 순위(0~100)로 계산 · 수급 미반영 · 매수·매도 권유 아님</p>`}</div>`;
  }
  function drawSectors() {
    const box = q("#sectorBox"); if (!box) return;
    if (!sectors.length) { box.hidden = true; return; }
    box.hidden = false;
    const won = (r) => r.cur === "KRW";
    const chips = sectors.map((c) => {
      const flags = c.rows.filter((r) => r.flags.length).length;
      return `<button class="sc-chip${openSector === c.name ? " on" : ""}" data-sec-toggle="${esc(c.name)}" aria-expanded="${openSector === c.name}">
        ${c.icon} ${esc(c.name)} <b class="${cls(c.avg)}">${c.avg > 0 ? "+" : ""}${c.avg.toFixed(2)}%</b>${flags ? '<i class="sc-dot" title="신호 종목 있음"></i>' : ""}</button>`;
    }).join("");
    const c = sectors.find((x) => x.name === openSector);
    const panel = c ? `<div class="sc-panel">
        <div class="sc-ph"><b>${c.icon} ${esc(c.name)}</b> 평균 <b class="${cls(c.avg)}">${c.avg > 0 ? "+" : ""}${c.avg.toFixed(2)}%</b>
          ${c.rows.length && Date.now() - Math.max(...c.rows.map((r) => r.at)) > 3 * 3600e3 ? '<span class="dim">· 장 마감 기준</span>' : ""}
          <button class="btn btn-ghost-dark btn-sm" data-sec-tag="${esc(c.tag)}">${esc(c.tag)} 관련 속보</button></div>
        <div class="sec-rows">${c.rows.map((r) => `<div class="sec-r${r.flags.length ? " flag" : ""}"><span class="sec-n">${esc(r.name)}</span>
          <b class="${cls(r.chg)}">${r.chg > 0 ? "+" : ""}${r.chg.toFixed(2)}%</b>${r.stale ? `<em class="stale">전일</em>` : ""}
          <small>${won(r) ? `${Math.round(r.px).toLocaleString("ko-KR")}원${r.val ? ` · 거래대금(통합) ${eok(r.val)}` : ""}` : `$${r.px}`}${r.to3m != null && r.to3m > 0 ? " · 3개월 고점 돌파" : r.to52 != null ? ` · 52주 고가 ${r.to52 > 0 ? "+" : ""}${r.to52}%` : ""}</small>
          ${r.flags.length ? `<span class="sec-f">${r.flags.map(esc).join(" · ")}</span>` : ""}</div>`).join("")}</div>
      </div>` : "";
    box.innerHTML = momHtml(momentum) + `<p class="spot-h">📊 섹터 시세 <small>섹터를 누르면 종목별 등락이 보입니다 · 주황 점은 신호(±3%·고점 돌파) 종목이 있는 섹터</small></p>
      <div class="sc-bar">${chips}</div>${panel}`;
  }

  /* ── 💰 주도주 수급: 반도체·국내 보안 상위 종목 거래대금·수급(사실 집계) ── */
  const eokS = (v) => v == null ? "-" : `<b class="${cls(v / 1e8)}">${v > 0 ? "+" : v < 0 ? "−" : ""}${eok(Math.abs(v))}</b>`;
  const md = (d) => d ? `${+d.slice(5, 7)}/${+d.slice(8, 10)}` : "";
  function flowTable(g, n, compact) {
    const rows = [...g.rows].sort((a, b) => flowSort === "chg" && !compact ? b.chg - a.chg : (b.val || 0) - (a.val || 0)).slice(0, n);
    const invDay = (rows.find((r) => r.inv) || {}).inv;
    const head = compact ? "<tr><th>종목</th><th>등락</th><th>거래대금</th></tr>"
      : `<tr><th>종목</th><th>등락</th><th>거래대금<small>통합</small></th><th>외국계 창구<small>오늘</small></th><th>외국인<small>${invDay ? md(invDay.day) : ""}</small></th><th>기관<small>${invDay ? md(invDay.day) : ""}</small></th><th>외국인·기관<small>5일 합계</small></th><th>프로그램</th></tr>`;
    const body = rows.map((r) => `<tr><td class="fl-n">${esc(r.name)}</td><td>${pct(r.chg)}</td><td>${r.val ? eok(r.val) : "-"}${!compact && r.val_krx && r.val - r.val_krx > 1e8 ? `<small class="fl-k">KRX ${eok(r.val_krx)}</small>` : ""}</td>${compact ? "" : `
      <td>${r.win ? eokS(r.win.amt) : "-"}</td><td>${r.inv ? eokS(r.inv.frgn) : "-"}</td><td>${r.inv ? eokS(r.inv.org) : "-"}</td>
      <td class="fl-5">${r.inv ? `${eokS(r.inv.frgn5)} / ${eokS(r.inv.org5)}` : "-"}</td><td class="dim">준비 중</td>`}</tr>`).join("");
    return `<div class="fl-g"><p class="fl-gh">${g.icon || ""} ${esc(g.name)}${g.n ? ` <small>상승 ${g.up}/${g.n}종목</small>` : ""}</p>
      <div class="fl-scroll"><table class="fl-t">${head}${body}</table></div></div>`;
  }
  function drawFlows() {
    const box = q("#flowBox"); if (!box) return;
    const gs = (flows && flows.groups) || [];
    if (!gs.length) { box.hidden = true; return; }
    box.hidden = false;
    const st = `${hm(flows.at)} 기준${flows.open ? " · 1분마다 갱신" : " · 장 마감(시간외 포함 시세)"}`;
    const btn = (k, l) => `<button class="sc-chip${flowSort === k ? " on" : ""}" data-flow-sort="${k}">${l}</button>`;
    const sum = (rows, f) => rows.reduce((a, r) => a + (f(r) || 0), 0);
    const chips = gs.map((g) => { const v = g.val || sum(g.rows, (r) => r.val), w = sum(g.rows, (r) => r.win && r.win.amt);
      return `<button class="sc-chip fl-chip${flowOpen === g.name ? " on" : ""}" data-flow-open="${esc(g.name)}" aria-expanded="${flowOpen === g.name}">
        ${g.icon || ""} ${esc(g.name)} <small>상승 ${g.up}/${g.n}</small> <small>대금 ${eok(v)}</small> <small>외국계 창구 ${eokS(w)}</small></button>`; }).join("");
    const g = gs.find((x) => x.name === flowOpen);
    box.innerHTML = `<p class="spot-h">💰 주도주 수급 <small>${st} · 종목군을 누르면 종목별 거래대금·수급이 보입니다</small></p>
      <div class="sc-bar">${chips}</div>
      ${g ? `<div class="sc-panel"><div class="fl-sort">${btn("val", "거래대금순")}${btn("chg", "등락률순")}</div>${flowTable(g, 8)}
      <p class="mm-f">종목군 안에서 거래대금 상위·등락률 상위 종목 · 거래대금은 통합(KRX + 넥스트레이드 프리·애프터마켓), 작은 글씨는 KRX만 · 금액은 순매수 수량 × 종가(장중 현재가)로 계산한 추정치(억 원)<br>
      외국계 창구 = 외국계 증권사 창구 합계(장중, 다음 금융) — 외국인 투자자 수급과 다름 · 외국인·기관 = 거래소 확정치(네이버, 장 마감 후 확정되며 그 전에는 직전 거래일 값)<br>
      종목별 프로그램 매매는 무료 공개 출처가 없어 준비 중 · 사실 집계이며 매수·매도 권유가 아닙니다</p></div>` : ""}`;
  }

  /* ── 📋 시장 브리핑(실시간 + 매일 12시 기록) ── */
  async function loadBriefs() {
    try { briefs = await (await fetch(`data/briefs.json?t=${Math.floor(Date.now() / 600000)}`)).json(); } catch { briefs = []; }
  }
  const sg = (v, u = "%") => `<b class="${cls(v)}">${v > 0 ? "+" : ""}${(+v).toFixed(2)}${u}</b>`;
  // 🌙 저녁 점검(20:05·22:15): 선물·유가를 한국장 마감(15:30)·넥장 마감(20:00)·1시간 전 대비로
  function eveHtml(e) {
    const p = (v) => v == null ? '<span class="dim">-</span>' : sg(v);
    const fv = (r, v) => v == null ? "-" : (r.u === "$" ? "$" : "") + v.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + (r.u === "원" ? "원" : "");
    const tbl = (rows, reg) => `<div class="fl-scroll"><table class="fl-t"><tr><th>종목</th><th>현재</th>${reg ? "<th>미국 종가<small>대비</small></th>" : ""}<th>15:30<small>한국 마감 후</small></th><th>20:00<small>넥장 마감 후</small></th><th>1시간</th><th>24시간</th><th>15:30 이후<small>저가~고가</small></th></tr>
      ${rows.map((r) => `<tr><td class="fl-n">${esc(r.name)}</td><td>${fv(r, r.px)}</td>${reg ? `<td>${p(r.reg)}</td>` : ""}<td>${p(r.kr)}</td><td>${p(r.nx)}</td><td>${p(r.h1)}</td><td>${p(r.d24)}</td><td class="fl-5">${r.lo != null ? `${fv(r, r.lo)}~${fv(r, r.hi)}` : "-"}</td></tr>`).join("")}</table></div>`;
    const li = (n) => `<li><b>${hm(n.ts)}</b> ${esc(n.text)} <small class="dim">${esc(n.src)}${n.verify === "multi" ? " · 복수 출처" : n.verify === "unconfirmed" ? " · 미확인" : ""}</small></li>`;
    return `<div class="bwide"><h4>🌙 선물·유가 점검 <small class="dim">${hm(e.at)} 기준 · 하이퍼리퀴드 24시간 선물 · 미국 개장 ${esc(e.us_open || "")} KST</small></h4>
        <p class="fl-gh">📈 지수·반도체 선물</p>${tbl(e.fut || [], true)}
        <p class="fl-gh" style="margin-top:10px">🛢️ 유가·금·달러</p>${tbl(e.oil || [], false)}
        <p class="mm-f">미국 종가 대비 = 현물 지수 종가와 24시간 선물 비교(기초 차이 포함) · 삼성전자·SK하이닉스 선물은 달러 표시</p></div>
      ${(e.nxt || []).length ? `<div class="bcol"><h4>🌆 넥스트레이드 애프터마켓</h4><ul class="bn">${e.nxt.map((r) => `<li>${esc(r.name)} ${Math.round(r.px).toLocaleString("ko-KR")}원 ${sg(r.chg)} <small class="dim">KRX 종가 대비 ${r.vs_krx != null ? `${r.vs_krx > 0 ? "+" : ""}${r.vs_krx.toFixed(2)}%` : "-"}${r.val ? ` · NXT 거래대금 ${eok(r.val)}` : ""}${r.status === "CLOSE" ? " · 마감" : ""}</small></li>`).join("")}</ul></div>` : ""}
      ${(e.oil_heads || []).length ? `<div class="bcol"><h4>🛢️ 유가·중동 속보 <small class="dim">최근 12시간</small></h4><ul class="bn">${e.oil_heads.map(li).join("")}</ul></div>` : ""}
      ${(e.tonight || []).length ? `<div class="bcol"><h4>🗓️ 오늘 밤 일정</h4><ul class="bn">${e.tonight.map((c) => `<li><b>${esc(c.time)}</b> ${esc(c.title)}</li>`).join("")}</ul></div>` : ""}`;
  }
  function briefHtml(b, hist) {
    if (!b) return "";
    // 후속 확인: 지난 기록에서 같은 종목이 며칠 연속 화제였는지, 섹터 평균이 어떻게 바뀌었는지
    const streak = (name) => { let n = 1; for (const h of hist) { if ((h.trending || []).some((t) => t.name === name)) n++; else break; } return n; };
    const prevSec = (name) => { const h = hist[0]; const x = h && (h.sectors || []).find((s) => s.name === name); return x ? x.avg : null; };
    const mv = (b.moves || []).map((m) => `<li><b class="${m.move > 0 ? "c-up" : "c-dn"}">${esc(m.name)} ${m.move > 0 ? "▲" : "▼"}${m.move > 0 ? "+" : ""}${m.move}${m.unit === "bp" ? "bp" : "%"}</b>
      <small>${hm(m.start)}–${hm(m.end)} · 평소의 ${m.ratio}배</small>${m.news && m.news[0] ? `<span>🔴 ${esc(m.news[0])}</span>` : `<span class="dim">직전 관련 뉴스 없음</span>`}</li>`).join("");
    const sec = (b.sectors || []).map((s) => { const p = prevSec(s.name);
      return `<li><b>${s.icon} ${esc(s.name)}</b> 평균 ${sg(s.avg)}${p != null ? ` <small>(전 기록 ${p > 0 ? "+" : ""}${p.toFixed(2)}%)</small>` : ""}
        <span>강 ${esc(s.best.name)} ${sg(s.best.chg)} · 약 ${esc(s.worst.name)} ${sg(s.worst.chg)}${s.flags ? ` · 신호 ${s.flags}종목` : ""}</span></li>`; }).join("");
    const tr = (b.trending || []).map((t) => { const k = hist.length ? streak(t.name) : 1;
      return `<span class="bt">${esc(t.name)} <b>${t.n}</b>${k > 1 ? `<em>${k}일 연속</em>` : ""}</span>`; }).join("");
    const w = b.world || {};
    const fx = (f) => f.u === "$" ? "$" + f.px.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) : f.px.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + (f.u === "원" || f.u === "엔" ? f.u : "");
    const fut = (b.futures || []).map((f) => `<span class="bf"><small>${esc(f.name)}</small> ${fx(f)} ${sg(f.chg)}</span>`).join("")
      + (() => { const u = b.ust && b.ust["10Y"] ? b.ust : b.us10y ? { "10Y": b.us10y } : {};
        return ["2Y", "10Y", "30Y"].filter((k) => u[k]).map((k) => `<span class="bf"><small>미 ${k.replace("Y", "년물")}</small> ${u[k].px.toFixed(3)}% <b class="${cls(u[k].bp)}">${u[k].bp > 0 ? "+" : ""}${u[k].bp.toFixed(1)}bp</b></span>`).join("")
          + (u["2Y"] && u["10Y"] ? `<span class="bf"><small>10년−2년</small> ${Math.round((u["10Y"].px - u["2Y"].px) * 100)}bp</span>` : ""); })();
    const krRow = (k) => { const L = [["KOSPI", "코스피"], ["KOSDAQ", "코스닥"], ["KR200", "코스피200"], ["SMSN", "삼성전자"], ["SKHX", "SK하이닉스"]].filter(([c]) => k && k[c] && k[c].px);
      if (!L.length) return "";
      const fv = (c, v) => c === "SMSN" || c === "SKHX" ? Math.round(v).toLocaleString("ko-KR") + "원" : v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      return `<h4>🇰🇷 한국 증시 <small class="dim">(한국거래소 · 전일 종가 대비${L.some(([c]) => k[c].open) ? " · 장중" : " · 마감"})</small></h4><div class="bfs" style="margin-bottom:10px">${L.map(([c, n]) => `<span class="bf"><small>${n}</small> ${fv(c, k[c].px)} ${sg(k[c].chg)}</span>`).join("")}</div>`; };
    const li = (n) => `<li><b>${hm(n.ts)}</b> ${n.pivot ? "🔴 " : ""}${esc(n.text)} <small class="dim">${esc(n.src)}</small></li>`;
    const top = (b.session || fut) ? `<div class="bwide">${b.session ? `<p class="bsess">🕘 지금: <b>${esc(b.session)}</b></p>` : ""}
        ${krRow(b.kr)}
        ${fut ? `<h4>⏱️ 24시간 선물·환율 <small class="dim">(24시간 전 대비)</small></h4><div class="bfs">${fut}</div>` : ""}</div>
      ${(b.macro || []).length ? `<div class="bcol"><h4>🧾 경제지표 발표 <small class="dim">최근 12시간</small></h4><ul class="bn">${b.macro.map(li).join("")}</ul></div>` : ""}
      ${(b.heads || []).length ? `<div class="bcol"><h4>📰 주요 속보 <small class="dim">최근 3시간</small></h4><ul class="bn">${b.heads.map(li).join("")}</ul></div>` : ""}` : "";
    const cps = (b.checkpoints || []).length ? `<div class="bcol"><h4>🗓️ 오늘 체크포인트</h4><ul class="bn">${b.checkpoints.map((c) => `<li>${c.time ? `<b>${esc(c.time)}</b> ` : ""}${esc(c.title)}</li>`).join("")}</ul></div>` : "";
    const ktop = (b.kr_top || []).length ? `<div class="bcol"><h4>🇰🇷 국내 감시 종목 상승 상위</h4><ul class="bn">${b.kr_top.map((r) => `<li>${esc(r.name)} ${sg(r.chg)} <small class="dim">${esc(r.sector)}${r.val ? ` · 거래대금 ${eok(r.val)}` : ""}</small></li>`).join("")}</ul></div>` : "";
    const rg = b.reg && b.reg.SP500 ? `<div class="bcol"><h4>🇺🇸 미국 정규장 마감</h4><div class="bfs">${[["SP500", "S&P500"], ["XYZ100", "나스닥100"], ["SOXL", "SOXL"], ["EWY", "EWY"]].filter(([k]) => b.reg[k]).map(([k, n]) => `<span class="bf"><small>${n}</small> ${sg(b.reg[k].chg)}</span>`).join("")}</div></div>` : "";
    const fl = (b.flows || []).length ? `<div class="bcol">${b.flows.map((g) => flowTable(g, 5, true)).join("")}</div>` : "";
    const mom = (b.momentum || []).length ? `<div class="bcol">${momHtml({ sectors: b.momentum }, true)}</div>` : "";
    const ev = b.eve && (b.eve.fut || []).length ? eveHtml(b.eve) : "";
    return ev + top + cps + rg + mom + fl + ktop + `<div class="bcol"><h4>📍 가장 크게 움직인 순간</h4><ul>${mv || '<li class="dim">최근 24시간 변곡점 없음</li>'}</ul></div>
      <div class="bcol"><h4>📊 섹터 강약</h4><ul>${sec || '<li class="dim">-</li>'}</ul></div>
      <div class="bcol"><h4>📈 뉴스에 많이 나온 종목</h4><div class="bts">${tr || '<span class="dim">-</span>'}</div>
        <h4 style="margin-top:12px">🌏 해외 지수</h4><p>상승 ${w.up || 0} · 하락 ${w.down || 0}${w.best ? ` · 최강 ${esc(w.best.name)} ${sg(w.best.chg)} · 최약 ${esc(w.worst.name)} ${sg(w.worst.chg)}` : ""}</p>
        ${(b.spot || []).length ? `<h4 style="margin-top:12px">🔥 화제 종목</h4><p>${b.spot.map((s) => `${esc(s.name)} ${s.chg != null ? sg(s.chg) : ""}`).join(" · ")}</p>` : ""}</div>`;
  }
  function drawBrief() {
    const box = q("#briefNow"); if (!box) return;
    const today = briefs.filter((h) => h.day !== kstDay(Date.now()) || true);
    box.innerHTML = brief ? briefHtml(brief, briefs.filter((h) => h.day !== kstDay(Date.now()))) : `<p class="empty">브리핑을 불러오는 중…</p>`;
    if (brief) setText("#briefStamp", `실시간 · ${hm(brief.at)} KST 기준`);
    const hb = q("#briefHist"); if (!hb) return;
    hb.innerHTML = briefs.length ? briefs.slice(0, 21).map((h, i) => `<details class="bh"${i === 0 ? "" : ""}><summary><b>${h.day.slice(5).replace("-", "/")}</b> ${h.slot ? `<b class="bslot">${esc(h.slot)}</b>${h.title ? ` ${esc(h.title)}` : ""}` : `${hm(h.at)} 기록`}
        <span>${(h.moves || [])[0] ? `${esc(h.moves[0].name)} ${h.moves[0].move > 0 ? "+" : ""}${h.moves[0].move}${h.moves[0].unit === "bp" ? "bp" : "%"}` : ""}${(h.trending || [])[0] ? ` · 화제 ${esc(h.trending[0].name)}` : ""}</span></summary>
        <div class="brief">${briefHtml(h, briefs.slice(i + 1))}</div></details>`).join("") : `<p class="dim">첫 기록은 오늘 12시에 저장됩니다.</p>`;
  }
  const kstDay = (ms) => { const d = kst(ms); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

  /* ── 최근 24시간 뉴스에 많이 나온 종목 ── */
  function drawTrend() {
    const box = q("#trendBox"); if (!box) return;
    box.innerHTML = trend.length ? `<span class="trend-h">📈 최근 24시간 뉴스에 많이 나온 종목</span>` + trend.map((t) =>
      `<button class="trend-i${kwFilter && kwFilter.label === t.name ? " on" : ""}" data-kw="${esc(t.kw)}" data-name="${esc(t.name)}">${esc(t.name)} <b>${t.n}</b></button>`).join("") : "";
  }

  /* ── 첫 화면 '지금 시장' 한 줄 ── */
  function drawHeroLive() {
    const box = q("#heroLive"); if (!box) return;
    const parts = [];
    const m = moves.find((x) => Date.now() - x.end < 6 * 3600e3);
    if (m) parts.push(`📍 최근 변곡점 <b>${esc(m.name)} ${m.move > 0 ? "▲" : "▼"}${fmtMove(m)}</b> (${hm(m.start)}–${hm(m.end)})`);
    const hot = news.find((n) => n.pivot);
    if (hot) parts.push(`🔴 ${hm(hot.ts)} ${esc(hot.text.length > 44 ? hot.text.slice(0, 44) + "…" : hot.text)}`);
    if (spot[0] && spot[0].chg != null) parts.push(`🔥 ${esc(spot[0].name)} ${spot[0].chg > 0 ? "+" : ""}${(+spot[0].chg).toFixed(2)}%`);
    if (trend[0]) parts.push(`📈 화제 ${esc(trend[0].name)} ${trend[0].n}건`);
    if (!parts.length) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `<span class="hl-dot"></span><b>지금 시장</b> ${parts.map((x) => `<span>${x}</span>`).join("")}<a href="#news">속보 보기 →</a>`;
  }

  /* ── 속보 목록 ── */
  const VER = { official: ["🏛 공식 발표", "v-ok"], multi: ["✔ 복수 출처", "v-ok"], single: ["단일 출처", "v-one"], unconfirmed: ["⚠ 미확인·보도 인용", "v-warn"] };
  const isStrat = (n) => n.kind === "증권사 시황" || n.kind === "시황 분석";
  const isMajor = (n) => n.pivot || n.hot || n.verify === "multi" || n.verify === "official" || n.kind === "섹터 시세";
  const impScore = (n) => (n.pivot ? 8 : 0) + (n.hot ? 4 : 0) + (n.verify === "multi" ? 2 : 0) + (n.verify === "official" ? 3 : 0) + (n.nsrc || 1) - (isStrat(n) ? 2 : 0);
  const mktScore = (n) => { const w = windows(reactKey(n).k, n.ts); if (!w) return -1; const d = w.slice().reverse().find((x) => x.v != null); return d ? Math.abs(d.v) : -1; };
  function drawFilters() {
    const box = q("#newsFilt"); if (!box || box.dataset.ready) return;
    const sel = (k, label, opts) => `<label>${label}<select data-f="${k}">${opts.map(([v, t]) => `<option value="${v}"${String(flt[k]) === String(v) ? " selected" : ""}>${t}</option>`).join("")}</select></label>`;
    box.innerHTML = sel("imp", "중요도", [["all", "전체"], ["major", "주요만"]])
      + sel("hrs", "시간", [[0, "전체"], [1, "1시간"], [3, "3시간"], [12, "12시간"]])
      + sel("ver", "검증", [["all", "전체"], ["ok", "공식·복수 출처만"], ["noun", "미확인 제외"], ["un", "미확인만"]])
      + sel("sort", "정렬", [["new", "최신순"], ["imp", "중요도순"], ["mkt", "시장 반응순"]]);
    box.dataset.ready = "1";
    box.addEventListener("change", (e) => { const f = e.target.dataset.f; if (!f) return; flt[f] = f === "hrs" ? +e.target.value : e.target.value; shown = 15; drawList(); });
  }
  function drawHealth(updated) {
    const el = q("#newsStamp"); if (!el) return;
    const now = Date.now(), parts = [`속보 갱신 ${hm(updated)} KST · ${ago(updated)}`];
    const warn = (t) => `<b class="h-warn">${t}</b>`;
    if (now - updated > 10 * 60000) parts.push(warn("갱신 지연"));
    const h = health;
    if (h) {
      if (h.tg) { const late = h.tg.last && now - h.tg.last > 60 * 60000; parts.push(`텔레 최신 ${h.tg.last ? hm(h.tg.last) : "-"}${h.tg.refresh === false ? " " + warn("수집 실패") : late ? " " + warn("1시간 넘게 새 글 없음") : ""}`); }
      if (h.rss && h.rss.total) parts.push(`RSS ${h.rss.ok}/${h.rss.total}${h.rss.fail && h.rss.fail.length ? " " + warn(`누락: ${h.rss.fail.map(esc).join("·")}`) : ""}`);
      if (h.tr && (h.tr.auto || h.tr.fail)) parts.push(`해외 기사 자동 번역 ${h.tr.auto}건${h.tr.fail ? " " + warn(`번역 실패 ${h.tr.fail}건(원문 표시)`) : ""}`);
    }
    el.innerHTML = parts.join(" · ");
  }
  function drawList() {
    drawFilters();
    const PIV = "🔴 변곡점 뉴스", STRAT = "📊 시황·전략";
    const tags = ["전체", PIV, STRAT, ...new Set(news.flatMap((n) => n.tags).filter((t) => t !== "시황"))];
    q("#newsChips").innerHTML = tags.map((t) => `<button class="chip${t === tag ? " on" : ""}" data-t="${esc(t)}">${esc(t)}</button>`).join("");
    const byTag = (n) => tag === "전체" || (tag === PIV ? n.pivot : tag === STRAT ? isStrat(n) : n.tags.includes(tag));
    const byKw = (n) => !kwFilter || kwFilter.rx.test(n.text + " " + (n.orig || "") + " " + (n.sub || ""));
    const now = Date.now();
    const byF = (n) => (flt.imp === "all" || isMajor(n)) && (!flt.hrs || now - n.ts < flt.hrs * 3600e3)
      && (flt.ver === "all" || (flt.ver === "ok" ? ["multi", "official"].includes(n.verify) : flt.ver === "noun" ? n.verify !== "unconfirmed" : n.verify === "unconfirmed"));
    let list = news.filter((n) => byTag(n) && byKw(n) && byF(n));
    if (flt.sort === "imp") list = list.slice().sort((a, b) => impScore(b) - impScore(a) || b.ts - a.ts);
    if (flt.sort === "mkt") list = list.slice().sort((a, b) => mktScore(b) - mktScore(a) || b.ts - a.ts);
    if (kwFilter) q("#newsChips").insertAdjacentHTML("afterbegin", `<button class="chip on kw-chip" data-clear-kw="1">🔎 ${esc(kwFilter.label)} ✕</button>`);
    q("#newsList").innerHTML = list.slice(0, shown).map((n) => {
      const R = reactKey(n), w = n.kind === "섹터 시세" ? null : windows(R.k, n.ts);
      const rs = w ? `<span class="nw-r">${esc(R.n)} <small>보도 5분 전 대비</small> ${w.map((x) => `<span class="rw">+${x.n}분 ${x.v == null ? `<i class="dim">계산 중</i>` : pct(x.v)}</span>`).join("")}</span>` : "";
      const pv = n.pivot ? `<p class="nw-pv">🔴 변곡점 직전 뉴스 — ${movesOfNews(n.ts).map((m) => `${esc(m.name)} ${fmtMove(m)} (${hm(m.start)}–${hm(m.end)})`).join(", ") || (n.pv || []).map(esc).join(", ")}</p>` : "";
      const lag = n.got && n.got - n.ts >= 2 * 60000 ? ` · 수집 ${hm(n.got)}<small>(+${Math.round((n.got - n.ts) / 60000)}분)</small>` : "";
      const v = VER[n.verify] ? `<span class="nw-v ${VER[n.verify][1]}">${VER[n.verify][0]}${n.nsrc > 1 ? ` ${n.nsrc}곳` : ""}</span>` : "";
      const tr = n.tr === "auto" ? `<span class="nw-v v-tr" title="${esc(n.orig || "")}">🌐 자동 번역</span>` : n.tr === "fail" ? `<span class="nw-v v-warn">🌐 번역 실패·원문</span>` : "";
      const XC = { ok: ["🌐 외신 확인", "v-ok"], ref: ["🌐 해외 보도", "v-one"], diff: ["⚠ 외신과 수치 다름", "v-warn"] };
      const xc = n.xc && XC[n.xc.st] ? `<span class="nw-v ${XC[n.xc.st][1]}">${XC[n.xc.st][0]} · ${n.xc.src.map(esc).join("·")}</span>` : "";
      const xcl = n.xc && XC[n.xc.st] ? `<p class="nw-xc"><b>원문</b> ${esc(n.xc.en)} <small class="dim">— ${esc(n.xc.src[0])}${n.xc.ko ? ` · 번역: ${esc(n.xc.ko)}` : ""}</small></p>` : "";
      const also = (n.also || []).length ? `<span class="nw-also">후속: ${n.also.map((a) => `${esc(a.osrc ? a.osrc + "·" + a.src : a.src)} ${hm(a.ts)}`).join(", ")}</span>` : "";
      return `<li class="nw${n.pivot ? " piv" : ""}${sel === n.ts ? " sel" : ""}${n.verify === "unconfirmed" ? " unv" : ""}" data-ts="${n.ts}">
        <div class="nw-t"><b>${hm(n.ts)}</b><span>${ago(n.ts)}</span></div>
        <div class="nw-b"><p class="nw-txt${n.kind === "섹터 시세" ? " sector" : ""}">${n.pivot ? "🔴 " : ""}${esc(n.text)}</p>${n.sub ? `<p class="nw-sub">${esc(n.sub)}</p>` : ""}${pv}
          <p class="nw-m">${n.tags.map((t) => `<span class="nw-tag">${esc(t)}</span>`).join("")}${isStrat(n) ? `<span class="nw-tag strat">${esc(n.kind)}</span>` : ""}${v}${xc}${tr}
          <span class="nw-src">${n.verify ? "최초 " : ""}${n.osrc ? `${esc(n.osrc)} · ${esc(n.src)} 경유` : esc(n.src)} ${hm(n.ts)}${lag}</span></p>
          ${xcl}${also ? `<p class="nw-m">${also}</p>` : ""}${rs ? `<p class="nw-m">${rs}</p>` : ""}</div></li>`;
    }).join("") || `<li class="empty">조건에 맞는 속보가 없습니다.</li>`;
    q("#newsMore").hidden = list.length <= shown;
  }

  const open = (coin, ts) => window.trlChart && window.trlChart.open({ coin, sel: ts, news });
  const full = !!q("#newsList");
  if (full) {
    q("#newsChips").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (!b) return; tag = b.dataset.t; shown = 15; drawList(); });
    q("#newsList").addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      const li = e.target.closest(".nw"); if (!li) return;
      const ts = +li.dataset.ts; sel = ts; if (window.trlCount) window.trlCount("news");
      drawCharts(); drawList();
      const m = movesOfNews(ts)[0], n = news.find((x) => x.ts === ts) || { tags: [] };
      const coin = m ? COIN[m.asset] : n.tags.includes("중동·유가") ? "xyz:CL" : (n.tags.includes("한국") || n.tags.includes("반도체")) ? "xyz:KR200" : n.tags.includes("연준·금리") ? "srv:US10Y" : "xyz:XYZ100";
      open(coin, ts);
    });
    q("#newsMore").addEventListener("click", () => { shown += 15; drawList(); });
    const openCard = (e) => { const c = e.target.closest(".nc[data-coin]"); if (c) open(c.dataset.coin, sel); };
    q("#newsCharts").addEventListener("click", openCard);
    q("#newsCharts").addEventListener("keydown", (e) => { if (e.key === "Enter") openCard(e); });
    const ml = q("#moveList");
    if (ml) ml.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      const c = e.target.closest(".mv"); if (!c) return;
      const m = moves.find((x) => x.asset === c.dataset.asset && x.start === +c.dataset.start);
      if (window.trlCount) window.trlCount("move");
      open(COIN[c.dataset.asset], (m && m.news && m.news[0]) || +c.dataset.start);
    });
    document.addEventListener("click", (e) => {
      const a = e.target.closest(".tk-i"); if (!a) return;
      e.preventDefault(); sel = +a.dataset.ts; tag = "전체"; shown = Math.max(shown, 40);
      drawCharts(); drawList(); q("#news").scrollIntoView({ behavior: "smooth" });
    });
  }

  const redraw = () => { drawHeroLive(); drawWorld(); drawSpot(); drawSectors(); drawFlows(); drawBrief(); if (full) { drawCharts(); drawMoves(); drawTrend(); drawList(); } };
  const setKw = (label, pat) => {
    try { kwFilter = { label, rx: new RegExp(pat, "i") }; } catch { kwFilter = null; }
    tag = "전체"; shown = 30; drawTrend(); drawList(); q("#news").scrollIntoView({ behavior: "smooth" });
  };
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-kw]");
    if (t && q("#trendBox") && q("#trendBox").contains(t)) {
      if (kwFilter && kwFilter.label === t.dataset.name) { kwFilter = null; drawTrend(); drawList(); } else setKw(t.dataset.name, t.dataset.kw);
      return;
    }
    if (e.target.closest("[data-clear-kw]")) { kwFilter = null; drawTrend(); drawList(); return; }
    const fs = e.target.closest("[data-flow-sort]"); if (fs) { flowSort = fs.dataset.flowSort; drawFlows(); return; }
    const fo = e.target.closest("[data-flow-open]"); if (fo) { const n = fo.dataset.flowOpen; flowOpen = flowOpen === n ? null : n; drawFlows(); return; }
    const tg = e.target.closest("[data-sec-toggle]");
    if (tg) { const n = tg.dataset.secToggle; openSector = openSector === n ? null : n; drawSectors(); return; }
    const st = e.target.closest("[data-sec-tag]"); if (st && q("#news")) { kwFilter = null; tag = st.dataset.secTag; shown = 30; drawTrend(); drawList(); q("#news").scrollIntoView({ behavior: "smooth" }); return; }
    const sk = e.target.closest("[data-spot-kw]"); if (sk && q("#news")) { setKw(sk.dataset.spotName, sk.dataset.spotKw); return; }
    const sc = e.target.closest("[data-spot-chart]"); if (sc && window.trlChart) window.trlChart.open({ coin: sc.dataset.spotChart, name: sc.dataset.spotName, sel: null, news });
  });
  (async () => { await Promise.all([loadNews(), loadNotes(), loadBriefs(), full ? loadCandles() : null]); redraw(); })();
  setInterval(loadBriefs, 600000);
  setInterval(async () => { await loadNews(); redraw(); }, 60000);                 // 속보·변곡점 1분마다
  setInterval(loadNotes, 600000);
  if (full) setInterval(async () => { await loadCandles(); redraw(); }, 120000);  // 지수 2분마다
})();
