/* 실시간 속보 · 변곡점 — 뉴스(live 브랜치 news.json)와 가격 변화를 시각으로 연결
   - 빨간 점(🔴)은 '변곡점(평소보다 크게 움직이기 시작한 구간) 직전 뉴스'에만 붙는다.
   - 해석은 사람이 쓴 '💡 해석' 노트(data/notes.json)로만 싣는다(블로그 글 연결은 2026-10-28 뺌). */
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
  const COIN = { NQ: "xyz:XYZ100", SP: "xyz:SP500", K200: "xyz:KR200", WTI: "xyz:CL", BRENT: "xyz:BRENTOIL", GOLD: "xyz:GOLD", US10Y: "srv:US10Y", DXY: "srv:DXY" };
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
  let world = [], spot = [], trend = [], sectors = [], brief = null, briefs = [], kwFilter = null, momentum = null, watch = null, lev = null, flows = null, flowOpen = null;   // kwFilter: {label, rx}

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
      window.trlDow = j.dow || {}; window.trlTnx = j.us10y || {}; window.trlUst = j.ust || {}; window.trlKr = j.kr || {}; window.trlReg = j.reg || {}; momentum = j.momentum || null; flows = j.flows || null; s7 = j.s7 || null; leaders = j.leaders || null; watch = j.watch || null; lev = j.lev || null; if (typeof window.loadTicks === "function" && !window.__tickRefreshed) { window.__tickRefreshed = true; window.loadTicks(); } window.trlSectors = sectors; window.trlWorld = world; window.trlSpot = spot; window.trlTrend = trend; window.trlNotesReady = true;
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
  // 중복 거르기: 같은 분(hh:mm)은 하나, 내용이 비슷하면(글자 2개씩 묶음 겹침 45% 이상) 하나 — 앞(중요한 것)이 남는다
  const bigr = (t) => { const x = String(t || "").replace(/^\s*(\[[^\]]{1,14}\]|[^\p{L}\p{N}]+)\s*/u, "").replace(/[^\p{L}\p{N}]/gu, "").toLowerCase(); const b = new Set(); for (let i = 0; i < x.length - 1; i++) b.add(x.slice(i, i + 2)); return b; };
  const simTxt = (a, b) => { if (!a.size || !b.size) return 0; let n = 0; for (const x of a) if (b.has(x)) n++; return n / Math.min(a.size, b.size); };
  function dedupe(list, sameMinute = true) {
    const out = [], mins = new Set();
    for (const n of list) {
      const m = hm(n.ts), g = bigr(n.text);
      if (sameMinute && mins.has(m)) continue;
      if (out.some((o) => simTxt(o._g, g) >= 0.45)) continue;
      mins.add(m); out.push(Object.assign(Object.create(null), n, { _g: g }));
    }
    return out;
  }
  // 📡 주요 시황: 끊김 없이 계속 흐른다. 목록은 한 번만 넣고(같은 소식이 한 화면에 두 번 안 보임), 새 소식은 한 바퀴가 끝날 때 바꿔 넣는다
  let tickPick = [], tickPending = null;
  const tickRow = (pick) => pick.map((n) => `<a class="tk-i${n.pivot ? " hot" : ""}" href="${q("#news") ? "#news" : "index.html#news"}" data-ts="${n.ts}"><b>${hm(n.ts)}</b>${n.pivot ? "🔴 " : ""}${n.lang === "en" ? "🌐 " : ""}${esc(gist(n.text, 110))}${n.series_n > 1 ? ` <small>· 같은 발언 외 ${n.series_n - 1}건</small>` : ""}</a>`).join("");
  function tickShow(pick) {
    const box = q("#ticker"); if (!box) return;
    const tr = box.querySelector(".tk-track");
    if (!tr) return;
    tickPick = pick;
    tr.innerHTML = tickRow(pick);
    tr.style.animationDuration = `${Math.max(30, pick.reduce((a, n) => a + Math.min(110, n.text.length), 0) * 0.28)}s`;   // 글 길이에 맞춘 일정한 속도
  }
  function drawTicker() {
    const box = q("#ticker"); if (!box) return;
    // 최근 1시간 안의 주요 뉴스 위주(중요도 순으로 고른 뒤 시간 순으로 흘림). 1시간 안에 5건이 안 되면 3시간까지 넓힌다
    const score = (n) => (n.pivot ? 8 : 0) + (n.hot ? 4 : 0) + (n.kind === "섹터 시세" ? 3 : 0)
      + ((n.tags || []).some((t) => ["중동·유가", "연준·금리", "반도체", "AI·빅테크", "한국", "지수"].includes(t)) ? 1 : 0)
      - (n.kind === "증권사 시황" || n.kind === "시황 분석" ? 2 : 0) - (/입찰|낙찰|응찰|Bid-to-Cover|\$거시경제/.test(n.text) ? 2 : 0);
    let span = 1;
    let recent = news.filter((n) => Date.now() - n.ts < 3600e3);
    if (recent.length < 5) { span = 3; recent = news.filter((n) => Date.now() - n.ts < 3 * 3600e3); }
    const pick = dedupe(recent.map((n) => [score(n), n]).sort((a, b) => b[0] - a[0] || b[1].ts - a[1].ts).map((x) => x[1])).slice(0, 12).sort((a, b) => b.ts - a.ts);
    const key = span + ":" + pick.map((n) => n.ts + (n.pivot ? "p" : "")).join(",");
    if (!pick.length || key === tickerKey) return;
    tickerKey = key;
    const lab = `📡 주요 시황 <small>${span === 1 ? "최근 1시간" : "최근 3시간"} · ${pick.length}건 · 중복 없이</small>`;
    const tr = box.querySelector(".tk-track");
    if (!tr) {                                             // 처음: 바로 흘리기 시작
      box.innerHTML = `<span class="tk-label">${lab}</span><div class="tk-view"><div class="tk-track tk-flow"></div></div>`;
      box.hidden = false;
      tickShow(pick);
      const t2 = box.querySelector(".tk-track");
      if (t2) t2.addEventListener("animationiteration", () => {   // 한 바퀴 끝 → 기다리던 새 목록으로
        if (tickPending) { const p = tickPending; tickPending = null; tickShow(p); const l = box.querySelector(".tk-label"); if (l) l.innerHTML = p.lab; }
      });
    } else {
      pick.lab = lab;
      tickPending = pick;                                  // 흐르는 중에는 끊지 않고 다음 바퀴부터
    }
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
    const recent = moves.filter((m) => Date.now() - m.start < 24 * 3600e3);
    // 같은 순간(시작 6분 안)은 카드 하나로: 평소 대비 배수가 가장 큰 자산이 제목, 나머지는 '함께 움직임'
    const groups = [];
    for (const m of recent) {
      const g = groups.find((x) => x.grp && x.grp === m.grp);
      if (g) g.list.push(m); else groups.push({ grp: m.grp, list: [m] });
    }
    const list = groups.slice(0, 8);
    if (!list.length) { box.innerHTML = `<p class="empty">최근 24시간 동안 평소보다 크게 움직인 구간이 없습니다.</p>`; return; }
    const px = (m) => m.unit === "bp" ? `${(+m.from).toFixed(3)}% → ${(+m.to).toFixed(3)}%` : `${(+m.from).toLocaleString("ko-KR", { maximumFractionDigits: 2 })} → ${(+m.to).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}`;
    box.innerHTML = list.map(({ list: ms }) => {
      ms.sort((a, b) => b.ratio - a.ratio);
      const m = ms[0], co = ms.slice(1);
      const nt = noteFor(m);
      const seenTs = new Set(), ns = [];
      for (const x of ms) for (const n of (x.items || (x.news || []).map((ts) => news.find((y) => y.ts === ts)).filter(Boolean))) {
        if (!seenTs.has(n.ts + n.text)) { seenTs.add(n.ts + n.text); ns.push({ ...n, _a: x.name }); }
      }
      ns.sort((a, b) => a.ts - b.ts);
      const inGrp = new Set(ms.map((x) => x.name));
      const others = Object.entries(m.others || {}).filter(([k]) => !inGrp.has(k)).slice(0, 4).map(([k, v]) => `${esc(k)} <b class="${cls(v)}">${v > 0 ? "+" : ""}${v}${k.includes("금리") ? "bp" : "%"}</b>`).join(" · ");
      return `<article class="mv" data-asset="${m.asset}" data-start="${m.start}">
        <div class="mv-h"><span class="mv-a ${m.move > 0 ? "pos" : "neg"}">${m.kind === "level" ? `🎯 ${esc(m.name)} ${m.unit === "bp" ? (+m.level).toFixed(2) + "%" : (m.asset === "WTI" || m.asset === "BRENT" || m.asset === "GOLD" ? "$" : "") + (+m.level).toLocaleString("ko-KR")} ${m.move > 0 ? "위로" : "아래로"}` : `${esc(m.name)} ${m.move > 0 ? "▲" : "▼"} ${fmtMove(m)}`}</span>
          <span class="mv-t">${hm(m.start)}–${hm(m.end)}${m.session ? ` · ${esc(m.session)}` : ""}</span></div>
        <p class="mv-o">${px(m)}${co.length ? ` · <b>함께 움직임</b> ${co.map((x) => `${x.kind === "level" ? "🎯 " : ""}${esc(x.name)}${x.kind === "level" ? ` ${(+x.level).toLocaleString("ko-KR")} ${x.move > 0 ? "위로" : "아래로"}` : ` <b class="${cls(x.move)}">${fmtMove(x)}</b>`} <small>(${hm(x.start)}–${hm(x.end)}${x.session ? ", " + esc(x.session) : ""})</small>`).join(" · ")}` : ""}</p>
        ${others ? `<p class="mv-o">같은 구간 ${others}</p>` : ""}
        ${ns.length ? `<ul class="mv-n">${ns.slice(0, 4).map((n) => `<li><span class="mv-dot"></span><b>${hm(n.ts)}</b> ${n.lang === "en" ? "🌐 " : ""}${esc(n.text)} <small>${n.osrc ? `${esc(n.osrc)} · ${esc(n.src)} 경유` : esc(n.src)}${co.length ? ` · ${esc(n._a)} 쪽` : ""}${n.lag != null ? ` · <b class="mv-lag">${n.lag < 0 ? `움직임 ${-n.lag}분 전` : n.lag === 0 ? "움직임과 같은 분" : `가격이 먼저 움직이고 ${n.lag}분 뒤`}</b>` : ""}</small></li>`).join("")}</ul>`
          : `<p class="mv-none">직전 15분 안에 관련 분야 뉴스가 없습니다(수급·기술적 움직임일 수 있음).</p>`}
        ${nt ? `<div class="mv-note"><b>💡 ${esc(nt.title)}</b><p>${esc(nt.text)}</p></div>` : ""}
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
    const rows = list.map((s, i) => `<li><b class="mm-rk" title="점수 순위">${s.rank ? s.rank + "위" : i + 1}</b><span class="mm-n">${s.us ? "🇺🇸 " : ""}${esc(s.name)}</span>${bar(s.momentum)}<b class="mm-v">${s.momentum.toFixed(0)}</b>
      ${compact ? "" : `<small class="dim">종목 중앙값 ${s.median.toFixed(0)} · 확산도 ${s.breadth.toFixed(0)} · 상승 ${s.up.toFixed(0)}%${s.share_shift != null ? ` · ${s.us ? "거래대금 가속도(QQQ 대비)" : "거래대금 점유율"} ×${s.share_shift.toFixed(2)}` : ""}${s.us ? " · 나스닥100 대비 상대강도 · 마지막 정규장 기준" : ""}</small>`}</li>`).join("");
    const st = m.at ? `${hm(m.at)} 기준${m.open ? "" : " · 장 마감·개장 전(전일 값 포함)"}${m.late ? ` · <b class="h-warn">지연 ${m.late}/${m.n}종목</b>` : ""}` : "";
    const usd = m.us_day ? ` · 🇺🇸 미국 ${+m.us_day.slice(5, 7)}/${+m.us_day.slice(8, 10)} 정규장` : "";
    return `<div class="mm"><p class="mm-h">📈 섹터 모멘텀 <small>${st}${usd}</small></p><ol class="mm-l">${rows}</ol>
      ${compact ? "" : `<p class="mm-f">순서는 고정(미국 반도체·한국 반도체·2차전지·방산·원전·조선), 왼쪽 'n위'는 점수 순위 · 거래대금 가속도·상대강도·5일선·신고가 근접 4개 지표의 종목 간 순위(0~100)로 계산 · 수급 미반영 · 매수·매도 권유 아님</p>`}</div>`;
  }
  // 🔬 SOXL · KORU 점검(레버리지 3배 ETF): 갭·5일선·20일선·연속 양봉·20일 고저·거래량·기초지수 ×3·24시간 시세
  const md2 = (ms) => { const d = kst(ms); return `${d.getMonth() + 1}/${d.getDate()}`; };
  function levHtml(L, compact) {
    const its = (L && L.items) || [];
    if (!its.length) return "";
    const $$ = (v) => v == null ? "-" : "$" + (+v).toFixed(2);
    const sgn = (v) => v == null ? "-" : `<b class="${cls(v)}">${v > 0 ? "+" : ""}${(+v).toFixed(2)}%</b>`;
    const one = (x) => {
      if (x.err || x.px == null) return `<div class="lv"><b>${esc(x.sym)}</b> <span class="dim">시세를 받지 못함</span></div>`;
      const st = x.open ? "진행 중" : "마감";
      const L2 = [
        `캔들: 시가 ${$$(x.o)} (갭 ${sgn(x.gap)}${x.gap_over_high ? " · 전일 고가 위" : ""}) · 고가 ${$$(x.h)} 저가 ${$$(x.l)} · 오늘 ${x.px > x.o ? "양봉" : x.px < x.o ? "음봉" : "보합"} ${st}`,
        `연속 양봉: 전일까지 ${x.streak_prev}일 → ${x.bull ? `${x.streak}일째` : "끊김(오늘 양봉 아님)"}${x.three ? ` · <b>적삼병 조건 ${x.open ? "충족 중(마감 전)" : "충족 마감"}</b>` : ""}`,
        `이동평균: 5일선 ${$$(x.ma5)} ${x.over_ma5 ? "위" : "아래"} ${sgn(x.vs_ma5)} · 20일선 ${$$(x.ma20)} ${x.over_ma20 ? "위" : "아래"} ${sgn(x.vs_ma20)}`,
        `20일 범위: 고가 ${$$(x.hi20)} 대비 ${sgn(x.from_hi20)} · 저가 ${$$(x.lo20)} 대비 ${sgn(x.from_lo20)}${x.vol_ratio != null ? ` · 거래량 20일 평균의 ×${x.vol_ratio}${x.open ? "(장중 누적)" : ""}` : ""}`,
        `기초: ${esc(x.base)} ${sgn(x.base_chg)}${x.base_over_ma5 != null ? ` (5일선 ${x.base_over_ma5 ? "위" : "아래"})` : ""}${x.x3 != null ? ` · ×3 = ${sgn(x.x3)} → 실제와 차이 ${x.x3_gap > 0 ? "+" : ""}${x.x3_gap}%p` : ""}${x.kr200 != null ? ` · 코스피200 야간(24시간) ${sgn(x.kr200)}` : ""}`,
      ];
      const ex = (e, nm) => {
        if (!e) return "";
        const ss = e.sess === "pre" ? "프리마켓" : "애프터마켓";
        return `🌙 ${nm ? esc(nm) + " " : ""}${ss} ${$$(e.px)} · 정규장 종가 ${$$(e.base)} 대비 ${sgn(e.chg)} <small class="dim">${e.stale ? `마지막 체결 ${md2(e.at)} ${hm(e.at)}${e.live ? " · 15분 넘게 체결 없음" : " · 지금은 시간외 거래 시간 아님"}` : `${hm(e.at)} 체결`} · 야후 1분봉</small>`;
      };
      if (x.ext) L2.unshift(ex(x.ext));
      if (x.base_ext) L2.splice(1, 0, ex(x.base_ext, "EWY"));
      if (x.h24) L2.push(`24시간 시세(하이퍼리퀴드): ${$$(x.h24.px)} · 정규장 가격 대비 ${sgn(x.h24.vs_reg)}`);
      if (x.members) L2.push(`구성 대형주 ${x.members.n}종목 중 ${x.members.n_up}종목 상승 · 강 ${x.members.up.map((m) => `${esc(m.name)} ${sgn(m.chg)}`).join(", ")} · 약 ${x.members.down.map((m) => `${esc(m.name)} ${sgn(m.chg)}`).join(", ")}`);
      return `<div class="lv"><p class="wt-n"><b>${esc(x.sym)}</b> <small class="dim">${esc(x.name)}</small> ${$$(x.px)} ${sgn(x.chg)} <small class="dim">${+x.day.slice(5, 7)}/${+x.day.slice(8, 10)} 정규장 ${st}</small></p>
        <ul>${(compact ? L2.slice(0, 3) : L2).map((t) => `<li>${t}</li>`).join("")}</ul></div>`;
    };
    return `<div class="lvbox"><p class="mm-h">🔬 SOXL · KORU 점검 <small>${hm(L.at)} 기준 · 2분마다 갱신</small></p>${its.map(one).join("")}
      ${compact ? "" : `<p class="mm-f">야후 정규장 시세 기준(시가는 5분봉 첫 봉) · 🌙 시간외 = 프리·애프터마켓 마지막 1분봉 체결, 정규장 종가 대비(하이퍼리퀴드 24시간 가격과 다른 상품) · 적삼병 조건 = 3일 연속 양봉(시가보다 높게, 전일보다 높게 마감)으로 단순 판정 · 3배 ETF는 하루 단위로 3배를 따라가 여러 날 누적 수익률은 3배와 다름 · 사실 집계이며 매수·매도 권유가 아닙니다</p>`}</div>`;
  }
  /* ── ⏱ 시간대별 강세: 매시(KST) '이번 시간 상승률' 상위 종목·업종 — 한국·미국 구분 ── */
  function hourlyHtml() {
    const H = leaders && leaders.hourly; if (!H || (!H.kr && !H.us)) return "";
    const order = mode() === "us" ? ["us", "kr"] : ["kr", "us"];
    const tab = hrTab && H[hrTab] ? hrTab : order.find((k) => H[k]);
    const blk = H[tab] || {}, slots = blk.slots || [];
    const cur = slots.find((x) => x.h === hrSlot) || slots[0];
    if (!cur) return "";
    const lab = (x) => `${x.h}시${x.live ? " 진행 중" : ""}`;
    const money = (v) => tab === "us" ? usd(v) : v ? eok(v) : "-";
    const rows = sortRows(cur.stocks || [], "hr").map((r) => `<tr><td class="fl-n">${esc(r.name)}</td><td>${pct(r.slot)}</td><td>${pct(r.chg)}</td><td>${money(r.val)}</td><td class="fl-5">${esc(r.sec || "")}</td></tr>`).join("");
    return `<div class="hr"><p class="spot-h">⏱ 시간대별 강세 종목·업종 <small>${hm(H.at)} 기준 · 매시(한국시간) 첫 값부터 지금까지 · ${blk.open ? "장중 3분마다" : "장 마감 기준"}</small></p>
      <div class="fl-sort">${order.filter((k) => H[k]).map((k) => `<button class="sc-chip${tab === k ? " on" : ""}" data-hr-tab="${k}">${k === "kr" ? "🇰🇷 한국" : "🇺🇸 미국"}</button>`).join("")}
        <span class="dim">시간대</span>${slots.map((x) => `<button class="sc-chip${x === cur ? " on" : ""}" data-hr-slot="${x.h}">${lab(x)}</button>`).join("")}</div>
      <p class="hr-sec"><b>${lab(cur)} 강한 업종</b> ${(cur.sectors || []).map((g) => `${esc(g.name)} ${pct(g.slot)} <small class="dim">상승 ${g.up}/${g.n} · ${g.top.map(esc).join(", ")}</small>`).join(" · ") || '<span class="dim">-</span>'}
        <small class="dim">· 전체 ${cur.up}/${cur.n}종목 상승</small></p>
      <div class="fl-scroll"><table class="fl-t"><tr>${sth("hr", "name", "종목")}${sth("hr", "slot", "이번 시간", cur.gap ? "전일 종가부터" : `${cur.h}시부터`)}${sth("hr", "chg", "오늘")}${sth("hr", "val", "거래대금")}<th>업종</th></tr>${rows}</table></div>
      <p class="mm-f">${tab === "kr" ? "코스피·코스닥 전 종목 중 오늘 거래대금 30억 원 이상(ETF·우선주 제외)" : "나스닥·뉴욕거래소 시가총액 상위 600종목"} · 업종은 네이버 분류, 걸러진 종목 3개 이상인 업종만 평균 · 첫 시간대는 전일 종가부터라 시가 갭 포함 · 사실 집계이며 매수·매도 권유가 아닙니다</p></div>`;
  }
  function leadersHtml() {
    if (!leaders || (!leaders.kr && !leaders.us)) return "";
    const tabs = [["kr.industry", "🇰🇷 한국 업종"], ["kr.theme", "🇰🇷 한국 테마"], ["us.industry", "🇺🇸 미국 업종"]];
    if (mode() === "us") tabs.unshift(tabs.pop());
    const tab = ldTab || tabs[0][0];
    const [mk, kd] = tab.split("."), blk = leaders[mk] || {}, isUs = mk === "us";
    const money = (v) => isUs ? usd(v) : v ? eok(v) : "-";
    const gs = sortRows(blk[kd] || [], "ld");
    const chips = gs.map((g) => `<button class="sc-chip ld-chip${ldOpen === g.name ? " on" : ""}" data-ld-open="${esc(g.name)}" aria-expanded="${ldOpen === g.name}">
      ${esc(g.name)} ${sg2(g.chg)} <small>상승 ${g.up}/${g.n} · 대금 ${money(g.val)} · 점수 ${g.score}</small></button>`).join("");
    const g = gs.find((x) => x.name === ldOpen);
    const mem = g ? `<div class="sc-panel"><div class="fl-scroll"><table class="fl-t"><tr>${sth("ldm", "name", "종목")}${sth("ldm", "chg", "등락")}${sth("ldm", "val", "거래대금")}${sth("ldm", "mcap", "시가총액")}</tr>
      ${sortRows(g.rows || [], "ldm").map((r) => `<tr><td class="fl-n">${esc(r.name)}</td><td>${pct(r.chg)}</td><td>${money(r.val)}</td><td>${money(r.mcap)}</td></tr>`).join("")}</table></div>
      <p class="mm-f">${esc(g.name)} 구성 ${g.n}종목 중 거래대금 상위 ${(g.rows || []).length}종목 · 머리글을 누르면 정렬</p></div>` : "";
    return `<div class="ld"><p class="spot-h">🏁 오늘의 주도 섹터 <small>자동 · ${hm(blk.at || leaders.at)} 기준 · ${blk.open ? "장중 3분마다 갱신" : "장 마감 기준"} · 섹터를 누르면 종목이 보입니다</small></p>
      <div class="fl-sort">${tabs.map(([k, l]) => `<button class="sc-chip${tab === k ? " on" : ""}" data-ld-tab="${k}">${l}</button>`).join("")}</div>
      ${sortChips("ld", [["score", "주도 점수순"], ["chg", "등락률순"], ["val", "거래대금순"], ["mcap", "시가총액순"], ["breadth", "상승 비율순"]])}
      <div class="sc-bar">${chips || '<span class="dim">자료를 불러오는 중</span>'}</div>${mem}
      <p class="mm-f">네이버 금융 ${isUs ? "해외(나스닥·뉴욕거래소 시가총액 상위 각 300종목, 업종별 시가총액 가중 등락률)" : kd === "theme" ? "국내 테마(등락률 상위 후보 16개 중)" : "국내 업종(등락률 상위 후보 12개 중)"} · 주도 점수 = 등락률 순위 50 + 거래대금 순위 30 + 상승 종목 비율 20(후보끼리 비교) · 순위일 뿐 매수·매도 권유가 아닙니다</p></div>`;
  }
  function drawSectors() {
    const box = q("#sectorBox"); if (!box) return;
    if (!sectors.length && !leaders) { box.hidden = true; return; }
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
        ${sortChips("sec", [["chg", "등락률순"], ["val", "거래대금순"], ["mcap", "시가총액순"], ["name", "이름순"]])}
        <div class="sec-rows">${sortRows(c.rows, "sec").map((r) => `<div class="sec-r${r.flags.length ? " flag" : ""}"><span class="sec-n">${esc(r.name)}</span>
          <b class="${cls(r.chg)}">${r.chg > 0 ? "+" : ""}${r.chg.toFixed(2)}%</b>${r.stale ? `<em class="stale">전일</em>` : ""}
          <small>${won(r) ? `${Math.round(r.px).toLocaleString("ko-KR")}원${r.val ? ` · 거래대금(통합) ${eok(r.val)}` : ""}${r.mcap ? ` · 시총 ${eok(r.mcap)}` : ""}` : `$${r.px}`}${r.to3m != null && r.to3m > 0 ? " · 3개월 고점 돌파" : r.to52 != null ? ` · 52주 고가 ${r.to52 > 0 ? "+" : ""}${r.to52}%` : ""}</small>
          ${r.flags.length ? `<span class="sec-f">${r.flags.map(esc).join(" · ")}</span>` : ""}</div>`).join("")}</div>
      </div>` : "";
    box.innerHTML = leadersHtml() + hourlyHtml() + momHtml(momentum) + levHtml(lev) + `<p class="fl-sort"><button class="sc-chip${fixSecOpen ? " on" : ""}" data-fixsec="1">📌 관심 섹터(고정) 시세 ${fixSecOpen ? "접기" : "보기"}</button></p>
      ${fixSecOpen ? `<p class="spot-h">📊 관심 섹터 시세 <small>섹터를 누르면 종목별 등락이 보입니다 · 주황 점은 신호(±3%·고점 돌파) 종목이 있는 섹터</small></p>
      <div class="sc-bar">${chips}</div>${panel}` : ""}`;
  }

  /* ── 👀 운영자 관전 포인트(data/watch.json): 운영자 메모 + 장중 수치(갭·5일선·연속 양봉·가격대) ── */
  function watchHtml(w, compact) {
    const its = (w && w.items) || [];
    if (!its.length) return "";
    const $$ = (v) => v == null ? "-" : "$" + (+v).toFixed(2);
    const sgn = (v) => `<b class="${cls(v)}">${v > 0 ? "+" : ""}${(+v).toFixed(2)}%</b>`;
    const md = (d) => `${+d.slice(5, 7)}/${+d.slice(8, 10)}`;
    const row = (x) => {
      if (x.err || x.px == null) return `<div class="wt-i"><b>${esc(x.name)}</b> <span class="dim">${x.px == null && !x.err ? "개장 전 · 전일 종가 " + $$(x.prev) + " · 5일선 " + $$(x.ma5_prev) : "시세를 받지 못함"}</span></div>`;
      const st = x.open ? "진행 중" : "마감";
      const L = [];
      if (x.focus.includes("gap")) L.push(`갭: 시가 ${$$(x.o)} — 전일 종가 대비 ${sgn(x.gap)} · 전일 고가 ${$$(x.prev_h)} ${x.gap_over_high ? "위" : "아래"}에서 시작`);
      if (x.focus.includes("ma5")) L.push(`5일선 ${$$(x.ma5)}: 현재 ${x.over_ma5 ? "위" : "아래"} ${sgn(x.vs_ma5)}${x.focus.includes("gap") ? ` · 시가도 5일선(${$$(x.ma5_prev)}) ${x.open_over_ma5 ? "위" : "아래"}` : ""}`);
      if (x.focus.includes("three")) L.push(`연속 양봉: 전일까지 ${x.streak_prev}일 → 오늘 ${x.bull ? `양봉 ${st} = ${x.streak}일째` : `양봉 아님(${st})`}${x.three ? ` · <b>적삼병 조건 ${x.open ? "충족 중(마감 전)" : "충족 마감"}</b>` : ""}`);
      if (x.level) L.push(`${$$(x.level)} 구간: ${(() => { const d = (x.px / x.level - 1) * 100; return Math.abs(d) < 0.15 ? "현재가가 그 부근" : `현재가가 ${sgn(d)} ${d > 0 ? "위" : "아래"}`; })()}${x.level_touched ? " · 오늘 고가가 도달" : ""}${(x.level_hits || []).length ? ` · 최근 10거래일 중 ${$$(x.level)} 이상 올랐다 아래에서 마감: ${x.level_hits.map((h) => `${md(h.d)}(고가 ${$$(h.h)}, 종가 ${$$(h.c)})`).join(", ")}` : ""}`);
      return `<div class="wt-i"><p class="wt-n"><b>${esc(x.name)}</b> ${$$(x.px)} ${sgn(x.chg)} <small class="dim">${md(x.day)} 정규장 ${st} · 고가 ${$$(x.h)} 저가 ${$$(x.l)}</small></p><ul>${L.map((t) => `<li>${t}</li>`).join("")}</ul></div>`;
    };
    return `<div class="wt"><p class="spot-h">👀 ${compact ? esc(w.title || "운영자 관전 포인트") : "운영자 메모·가격대"} <small>${esc(its.map((x) => x.sym).join("·"))} · ${hm(w.at)} 기준 · 1분마다 갱신</small></p>
      ${w.memo ? `<blockquote class="wt-memo">${esc(w.memo)}<cite>— 운영자 관전 포인트</cite></blockquote>` : ""}
      ${its.map(row).join("")}
      ${(w.events || []).length ? `<p class="wt-n" style="margin-top:8px"><b>⏱ 지금 상태(마지막 전환)</b> <small class="dim">기준선(5일선·시가·전일 종가·가격대)을 0.15% 넘게 넘을 때 · 조건마다 가장 최근 것만(되돌려진 옛 기록은 지움)</small></p><ul class="wt-ev">${w.events.slice(0, compact ? 6 : 15).map((e) => `<li><b>${hm(e.ts)}</b> <span class="${e.up ? "c-up" : "c-dn"}">${e.up ? "▲" : "▼"}</span> ${esc(e.text)}${e.n > 1 ? ` <small class="dim">· 오늘 ${e.n}번째 전환</small>` : ""}</li>`).join("")}</ul>` : ""}
      ${compact ? "" : `<p class="mm-f">자동 수치는 야후 정규장 시세 기준 · 적삼병 조건 = 3일 연속 양봉(시가보다 높게, 전일보다 높게 마감)으로 단순 판정 · 사실 집계이며 매수·매도 권유가 아닙니다</p>`}</div>`;
  }
  /* ── 🕗 시간대 관전 포인트(자동): 한국장 08~18시 / 미국장 18~08시(KST) — 1분마다 지금 수치로 다시 쓴다 ── */
  let leaders = null, ldTab = null, ldOpen = null, fixSecOpen = false, hrTab = null, hrSlot = null;
  const mode = () => { const h = kst(Date.now()).getHours(); return h >= 8 && h < 18 ? "kr" : "us"; };
  const sg2 = (v) => v == null ? "-" : `<b class="${cls(v)}">${v > 0 ? "+" : ""}${(+v).toFixed(2)}%</b>`;
  const usd = (v) => v == null ? "-" : `${(v / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: v >= 1e10 ? 0 : 1 })}억 달러`;
  function sessionHtml() {
    const md_ = mode(), now = kst(Date.now());
    const today = kstDay(Date.now()), tmr = kstDay(Date.now() + 86400e3);
    const fut = {}; ((brief && brief.futures) || []).forEach((f) => { fut[f.name] = f; });
    const fv = (n) => { const f = fut[n]; return f ? `${esc(n)} ${f.u === "$" ? "$" : ""}${(+f.px).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}${f.u === "원" ? "원" : ""} ${sg2(f.chg)}` : ""; };
    const top3 = (gs) => (gs || []).slice(0, 3).map((g) => `${esc(g.name)} ${sg2(g.chg)} <small class="dim">상승 ${g.up}/${g.n}</small>`).join(" · ");
    const reg = window.trlReg || {}, kr = window.trlKr || {};
    const L = [];
    const lvl = () => ((watch && watch.items) || []).filter((x) => x.px != null).map((x) => {
      const e = ((lev && lev.items) || []).find((y) => y.sym === x.sym);
      const ext = e && e.ext && !e.ext.stale ? ` · ${e.ext.sess === "pre" ? "프리" : "애프터"} $${e.ext.px} ${sg2(e.ext.chg)}` : "";
      return `${esc(x.sym)} $${(+x.px).toFixed(2)} ${sg2(x.chg)}${x.level ? (() => { const d = (x.px / x.level - 1) * 100; return ` (운영자 가격대 $${x.level} ${Math.abs(d) < 0.15 ? "부근" : `대비 ${sg2(d)} ${d > 0 ? "위" : "아래"}`})`; })() : ""}${ext}`;
    }).join(" · ");
    if (md_ === "us") {
      const u = leaders && leaders.us;
      if (u && (u.industry || []).length) L.push(`🏁 미국 주도 업종${u.open ? "(장중)" : "(직전 장 기준)"}: ${top3(u.industry)}`);
      const f = ["나스닥100", "S&P500", "WTI", "브렌트", "달러인덱스"].map(fv).filter(Boolean);
      if (f.length) L.push(`📈 지수·유가(24시간 선물): ${f.join(" · ")}${brief && brief.us10y ? ` · 미 10년물 ${(+brief.us10y.px).toFixed(3)}%` : ""}`);
      const hu = leaders && leaders.hourly && leaders.hourly.us && (leaders.hourly.us.slots || [])[0];
      if (hu && hu.live) L.push(`⏱ 이번 시간(${hu.h}시~) 강세: ${(hu.sectors || []).slice(0, 2).map((g) => `${esc(g.name)} ${sg2(g.slot)}`).join(" · ")} | ${(hu.stocks || []).slice(0, 3).map((r) => `${esc(r.name)} ${sg2(r.slot)}`).join(" · ")}`);
      const k = ["코스피200", "삼성전자", "SK하이닉스", "원/달러"].map(fv).filter(Boolean);
      if (k.length) L.push(`🇰🇷 내일 한국장 연결(24시간 시세): ${k.join(" · ")}`);
      const evT = (c) => new Date(`${c.date}T${c.time}:00+09:00`).getTime();
      const cs = (checks || []).filter((c) => c.time && evT(c) >= Date.now() - 30 * 60000 && evT(c) <= Date.now() + 12 * 3600e3).sort((a, b) => evT(a) - evT(b));
      if (cs.length) L.push(`🗓️ 앞으로 12시간 일정: ${cs.slice(0, 4).map((c) => `<b>${c.date !== today ? `${+c.date.slice(5, 7)}/${+c.date.slice(8)} ` : ""}${esc(c.time)}</b> ${esc(c.title)}`).join(" · ")}`);
    } else {
      const r = (k, n) => reg[k] ? `${n} ${sg2(reg[k].chg)}` : "";
      const us_ = [r("SP500", "S&P500"), r("XYZ100", "나스닥100"), r("SOXL", "SOXL"), r("KORU", "KORU"), r("EWY", "EWY")].filter(Boolean);
      if (us_.length) L.push(`🌙 간밤 미국 정규장: ${us_.join(" · ")}`);
      const ki = [["KOSPI", "코스피"], ["KOSDAQ", "코스닥"], ["KR200", "코스피200"]].filter(([k]) => kr[k]).map(([k, n]) => `${n} ${(+kr[k].px).toLocaleString("ko-KR", { maximumFractionDigits: 2 })} ${sg2(kr[k].chg)}`);
      if (now.getHours() < 9 && fut["코스피200"]) L.push(`⏰ 개장 전 코스피200 야간(24시간): ${fv("코스피200")}`);
      if (ki.length) L.push(`🇰🇷 지수: ${ki.join(" · ")}`);
      const k = leaders && leaders.kr;
      if (k && (k.industry || []).length) L.push(`🏁 한국 주도 업종${k.open ? "(장중)" : "(직전 장 기준)"}: ${top3(k.industry)}`);
      if (k && (k.theme || []).length) L.push(`🏷️ 한국 주도 테마: ${top3(k.theme)}`);
      const hk = leaders && leaders.hourly && leaders.hourly.kr && (leaders.hourly.kr.slots || [])[0];
      if (hk && hk.live) L.push(`⏱ 이번 시간(${hk.h}시~) 강세: ${(hk.sectors || []).slice(0, 2).map((g) => `${esc(g.name)} ${sg2(g.slot)}`).join(" · ")} | ${(hk.stocks || []).slice(0, 3).map((r) => `${esc(r.name)} ${sg2(r.slot)}`).join(" · ")}`);
      if (s7 && s7.s7 && s7.day === today) {
        const kk = s7.kospi || {};
        L.push(`🏛️ S7 지수 기여 ${s7.s7.pts > 0 ? "+" : ""}${s7.s7.pts}p${s7.s7.share != null ? `(지수 변화의 ${s7.s7.share}%)` : ""} · S7 제외 코스피 ${sg2(s7.s7.ex_chg)} · 코스피 외국인 ${kk.frgn != null ? Math.round(kk.frgn).toLocaleString("ko-KR") + "억" : "-"} · 기관 ${kk.org != null ? Math.round(kk.org).toLocaleString("ko-KR") + "억" : "-"} · 프로그램 ${kk.prog != null ? Math.round(kk.prog).toLocaleString("ko-KR") + "억" : "-"}`);
      }
      const cs = (checks || []).filter((c) => c.date === today);
      if (cs.length) L.push(`🗓️ 오늘 일정: ${cs.slice(0, 4).map((c) => `${c.time ? `<b>${esc(c.time)}</b> ` : ""}${esc(c.title)}`).join(" · ")}`);
    }
    if (!L.length) return "";
    return `<div class="ses"><p class="spot-h">${md_ === "kr" ? "🇰🇷 오늘 한국장 관전 포인트" : "🇺🇸 오늘 밤 미국장 관전 포인트"} <small>${hm(Date.now())} 기준 · 1분마다 갱신 · 한국장 08~18시 / 미국장 18~08시 자동 전환</small></p>
      <ul class="ses-l">${L.map((t) => `<li>${t}</li>`).join("")}</ul></div>`;
  }
  function drawWatch() {
    const box = q("#watchBox"); if (!box) return;
    const h = sessionHtml() + watchHtml(watch);
    box.hidden = !h; box.innerHTML = h;
  }

  /* ── ↕ 표 정렬(등락률·거래대금·시가총액·수급 …): 머리글이나 정렬 버튼을 누르면 순서가 바뀐다. 같은 걸 다시 누르면 반대로 ── */
  const sortSt = { flow: { k: "chg", d: -1 }, s7: { k: null, d: -1 }, sec: { k: "chg", d: -1 }, ld: { k: "score", d: -1 }, ldm: { k: "val", d: -1 }, hr: { k: "slot", d: -1 } };
  const SORTK = {
    name: (r) => r.name, chg: (r) => r.chg, val: (r) => r.val, mcap: (r) => r.mcap, pts: (r) => r.pts, w: (r) => r.w,
    win: (r) => r.win ? r.win.amt : null, frgn: (r) => r.inv ? r.inv.frgn : null, org: (r) => r.inv ? r.inv.org : null,
    s5: (r) => r.inv ? (r.inv.frgn5 || 0) + (r.inv.org5 || 0) : null, score: (r) => r.score, breadth: (r) => r.breadth, slot: (r) => r.slot, prog: (r) => r.prog ? r.prog.amt : null, prog5: (r) => r.prog ? r.prog.amt5 : null,
  };
  function sortRows(rows, t) {
    const st = sortSt[t]; if (!st.k) return rows;
    const f = SORTK[st.k];
    return [...rows].sort((a, b) => {
      const x = f(a), y = f(b);
      if (x == null || x === "") return y == null || y === "" ? 0 : 1;      // 값 없는 종목은 항상 아래
      if (y == null || y === "") return -1;
      return (typeof x === "string" ? x.localeCompare(y, "ko") : x - y) * st.d;
    });
  }
  const arrow = (t, k) => sortSt[t].k === k ? (sortSt[t].d < 0 ? " ▼" : " ▲") : "";
  const sth = (t, k, label, sub) => `<th class="srt${sortSt[t].k === k ? " on" : ""}" data-sort="${t}:${k}" title="눌러서 정렬">${label}${arrow(t, k)}${sub ? `<small>${sub}</small>` : ""}</th>`;
  const sortChips = (t, list) => `<div class="fl-sort"><span class="dim">정렬</span>${list.map(([k, l]) =>
    `<button class="sc-chip${sortSt[t].k === k ? " on" : ""}" data-sort="${t}:${k}">${l}${arrow(t, k)}</button>`).join("")}</div>`;
  const mcapS = (v) => v ? eok(v) : "-";

  /* ── 💰 주도주 수급: 종목군 전 종목 등락·거래대금·시가총액·수급(사실 집계) ── */
  const eokS = (v) => v == null ? "-" : `<b class="${cls(v / 1e8)}">${v > 0 ? "+" : v < 0 ? "−" : ""}${eok(Math.abs(v))}</b>`;
  const md = (d) => d ? `${+d.slice(5, 7)}/${+d.slice(8, 10)}` : "";
  function flowTable(g, n, compact) {
    const rows = compact ? [...g.rows].sort((a, b) => (b.val || 0) - (a.val || 0)).slice(0, n) : sortRows(g.rows, "flow").slice(0, n);
    const invDay = (rows.find((r) => r.inv) || {}).inv;
    const dd = invDay ? md(invDay.day) : "";
    const head = compact ? "<tr><th>종목</th><th>등락</th><th>거래대금</th></tr>"
      : `<tr>${sth("flow", "name", "종목")}${sth("flow", "chg", "등락")}${sth("flow", "val", "거래대금", "통합")}${sth("flow", "mcap", "시가총액")}${sth("flow", "win", "외국계 창구", "오늘")}${sth("flow", "frgn", "외국인", dd)}${sth("flow", "org", "기관", dd)}${sth("flow", "s5", "외국인·기관", "5일 합계")}${sth("flow", "prog", "프로그램", "오늘")}${sth("flow", "prog5", "프로그램", "5일 합계")}</tr>`;
    const body = rows.map((r) => `<tr><td class="fl-n">${esc(r.name)}</td><td>${pct(r.chg)}</td><td>${r.val ? eok(r.val) : "-"}${!compact && r.val_krx && r.val - r.val_krx > 1e8 ? `<small class="fl-k">KRX ${eok(r.val_krx)}</small>` : ""}</td>${compact ? "" : `
      <td>${mcapS(r.mcap)}</td><td>${r.win ? eokS(r.win.amt) : "-"}</td><td>${r.inv ? eokS(r.inv.frgn) : "-"}</td><td>${r.inv ? eokS(r.inv.org) : "-"}</td>
      <td class="fl-5">${r.inv ? `${eokS(r.inv.frgn5)} / ${eokS(r.inv.org5)}` : "-"}</td><td>${r.prog ? eokS(r.prog.amt) : '<span class="dim">-</span>'}</td><td>${r.prog ? eokS(r.prog.amt5) : '<span class="dim">-</span>'}</td>`}</tr>`).join("");
    return `<div class="fl-g"><p class="fl-gh">${g.icon || ""} ${esc(g.name)}${g.n ? ` <small>상승 ${g.up}/${g.n}종목</small>` : ""}</p>
      <div class="fl-scroll"><table class="fl-t">${head}${body}</table></div></div>`;
  }
  /* ── 🏛️ S7: 코스피 영향 큰 삼성·SK 7종목 — 지수 기여 포인트, S7 제외 코스피, 수급 ── */
  let s7 = null;
  function drawS7() {
    const box = q("#s7Box"); if (!box) return;
    if (!s7 || !(s7.rows || []).length) { box.hidden = true; return; }
    box.hidden = false;
    const k = s7.kospi || {}, s = s7.s7 || {};
    const pt = (v) => v == null ? "-" : `<b class="${cls(v)}">${v > 0 ? "+" : ""}${(+v).toFixed(1)}p</b>`;
    const ek = (v) => v == null ? "-" : `<b class="${cls(v)}">${v > 0 ? "+" : ""}${Math.round(v).toLocaleString("ko-KR")}억</b>`;
    const mx = Math.max(...s7.rows.map((r) => Math.abs(r.pts || 0)), 1);
    const bar = (v) => `<span class="s7-bar"><i class="${v >= 0 ? "s7-u" : "s7-d"}" style="width:${Math.round(Math.abs(v || 0) / mx * 100)}%"></i></span>`;
    const st = `${hm(s7.at)} 기준${s7.open ? " · 1분마다 갱신" : " · 장 마감"}`;
    const body = sortRows(s7.rows, "s7").map((r) => `<tr><td class="fl-n">${esc(r.name)}</td><td>${pct(r.chg)}</td>
      <td class="s7-c">${r.w == null ? '<span class="dim">지수 미포함</span>' : `${pt(r.pts)}${bar(r.pts)}`}</td><td>${r.w == null ? "-" : r.w.toFixed(1) + "%"}</td>
      <td>${r.val ? eok(r.val) : "-"}</td><td>${r.win ? eokS(r.win.amt) : "-"}</td><td>${r.inv ? eokS(r.inv.frgn) : "-"}</td><td>${r.inv ? eokS(r.inv.org) : "-"}</td>
      <td class="fl-5">${r.inv ? `${eokS(r.inv.frgn5)} / ${eokS(r.inv.org5)}` : "-"}</td><td>${r.prog ? eokS(r.prog.amt) : "-"}</td></tr>`).join("");
    const invDay = (s7.rows.find((r) => r.inv) || {}).inv;
    box.innerHTML = `<p class="spot-h">🏛️ S7 · 코스피 영향 큰 7종목 <small>${st} · 삼성전자·삼성전자우·SK하이닉스·SK스퀘어·삼성전기·삼성생명·삼성물산</small></p>
      <div class="s7-sum">
        <div><span>코스피</span><b>${(+k.px).toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b> ${pct(k.chg)} ${pt(k.pts)}</div>
        <div><span>S7 기여</span>${pt(s.pts)} <small>${s.share != null ? `지수 변화의 ${s.share}%` : ""} · 비중 ${s.w}%</small></div>
        <div><span>S7 제외 코스피</span>${s.ex_chg != null ? pct(s.ex_chg) : "-"} ${pt(s.ex_pts)}</div>
        <div><span>상승·하락 종목</span><b>${k.up != null ? `${k.up} / ${k.dn}` : "-"}</b></div>
        <div><span>코스피 투자자 <small>${k.flow_day ? md(k.flow_day.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")) : ""}</small></span>개인 ${ek(k.ind)} · 외국인 ${ek(k.frgn)} · 기관 ${ek(k.org)}</div>
        <div><span>프로그램 매매</span>차익 ${ek(k.arb)} · 비차익 ${ek(k.nonarb)} · 합계 ${ek(k.prog)}</div>
      </div>
      <div class="fl-scroll"><table class="fl-t"><tr>${sth("s7", "name", "종목")}${sth("s7", "chg", "등락")}${sth("s7", "pts", "지수 기여", "포인트")}${sth("s7", "w", "코스피 비중", "전일 시총")}${sth("s7", "val", "거래대금", "통합")}${sth("s7", "win", "외국계 창구", "오늘")}${sth("s7", "frgn", "외국인", invDay ? md(invDay.day) : "")}${sth("s7", "org", "기관", invDay ? md(invDay.day) : "")}${sth("s7", "s5", "외국인·기관", "5일 합계")}${sth("s7", "prog", "프로그램", "오늘")}</tr>${body}</table></div>
      <p class="mm-f">지수 기여 = 코스피 전일 종가 × 종목 비중(전일 시가총액 ÷ 코스피 보통주 시가총액 합계) × 등락률 — 근사치 · 코스피는 보통주로만 계산해 삼성전자우는 지수에 들어가지 않음<br>
      S7 제외 코스피 = 코스피 변화 − S7 기여 · 투자자·프로그램은 코스피 전체(억 원, 장중 잠정) · 외국계 창구는 외국계 증권사 창구 합계로 외국인 수급과 다름 · 사실 집계이며 매수·매도 권유가 아닙니다</p>`;
  }
  function drawFlows() {
    const box = q("#flowBox"); if (!box) return;
    const gs = (flows && flows.groups) || [];
    if (!gs.length) { box.hidden = true; return; }
    box.hidden = false;
    const st = `${hm(flows.at)} 기준${flows.open ? " · 1분마다 갱신" : " · 장 마감(시간외 포함 시세)"}`;
    const sum = (rows, f) => rows.reduce((a, r) => a + (f(r) || 0), 0);
    const chips = gs.map((g) => { const v = g.val || sum(g.rows, (r) => r.val), w = sum(g.rows, (r) => r.win && r.win.amt);
      return `<button class="sc-chip fl-chip${flowOpen === g.name ? " on" : ""}" data-flow-open="${esc(g.name)}" aria-expanded="${flowOpen === g.name}">
        ${g.icon || ""} ${esc(g.name)} <small>상승 ${g.up}/${g.n}</small> <small>대금 ${eok(v)}</small> <small>외국계 창구 ${eokS(w)}</small></button>`; }).join("");
    const g = gs.find((x) => x.name === flowOpen);
    box.innerHTML = `<p class="spot-h">💰 주도주 수급 <small>${st} · 종목군을 누르면 종목별 거래대금·수급이 보입니다</small></p>
      <div class="sc-bar">${chips}</div>
      ${g ? `<div class="sc-panel">${sortChips("flow", [["chg", "등락률순"], ["val", "거래대금순"], ["mcap", "시가총액순"], ["frgn", "외국인순"], ["org", "기관순"], ["win", "외국계 창구순"], ["prog", "프로그램순"], ["name", "이름순"]])}${flowTable(g, 99)}
      <p class="mm-f">종목군 전 종목 · 정렬 버튼이나 표 머리글을 누르면 순서가 바뀌고, 다시 누르면 반대로 · 외국계 창구는 종목군 상위 종목만 2분마다 · 거래대금은 통합(KRX + 넥스트레이드 프리·애프터마켓), 작은 글씨는 KRX만 · 금액은 순매수 수량 × 종가(장중 현재가)로 계산한 추정치(억 원)<br>
      외국계 창구 = 외국계 증권사 창구 합계(장중, 다음 금융) — 외국인 투자자 수급과 다름 · 외국인·기관 = 거래소 확정치(네이버, 장 마감 후 확정되며 그 전에는 직전 거래일 값)<br>
      프로그램 = 종목별 프로그램 순매수(KB증권 Open API, 오늘 값은 장중 누적·주요 종목 3분마다) · 사실 집계이며 매수·매도 권유가 아닙니다</p></div>` : ""}`;
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
      <small>${hm(m.start)}–${hm(m.end)}</small>${m.news && m.news[0] ? `<span>🔴 ${esc(m.news[0])}</span>` : `<span class="dim">직전 관련 뉴스 없음</span>`}</li>`).join("");
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
      ${(b.heads || []).length ? `<div class="bcol"><h4>📰 주요 속보 <small class="dim">최근 3시간</small></h4><ul class="bn">${b.heads.map(li).join("")}</ul></div>` : ""}
      ${(b.analysis || []).length ? `<div class="bcol"><h4>📝 텔레 시황 분석 <small class="dim">최근 12시간 · 중요도 순</small></h4><ul class="bn">${b.analysis.map((n) => `<li><b>${hm(n.ts)}</b> ${esc(n.text)}${n.sub ? `<br><small class="dim">${esc(n.sub)}</small>` : ""} <small class="dim">${esc(n.src)}</small></li>`).join("")}</ul></div>` : ""}` : "";
    const of = b.official || {};
    const ofh = (of.ust || of.eia || (of.bls || []).length) ? `<div class="bcol"><h4>🏛 공식 발표 데이터 <small class="dim">미 재무부·EIA·BLS 원자료</small></h4><ul class="bn">
      ${of.ust ? `<li><b>미 국채 종가</b> <small class="dim">${esc(of.ust.date)}</small><br>${[["3M", "3개월"], ["2Y", "2년"], ["10Y", "10년"], ["30Y", "30년"]].filter(([k]) => of.ust.rates[k] && of.ust.rates[k].v != null).map(([k, n]) => `${n} ${of.ust.rates[k].v.toFixed(2)}%${of.ust.rates[k].bp ? ` <small class="${cls(of.ust.rates[k].bp)}">${of.ust.rates[k].bp > 0 ? "+" : ""}${of.ust.rates[k].bp}bp</small>` : ""}`).join(" · ")}${of.ust.s10_2 != null ? `<br><small class="dim">10년−2년 ${of.ust.s10_2}bp · 10년−3개월 ${of.ust.s10_3m}bp</small>` : ""}</li>` : ""}
      ${of.eia ? `<li><b>EIA 주간 석유 재고</b> <small class="dim">${esc(of.eia.week)} 주 · 백만 배럴 · 전주 대비</small><br>${of.eia.items.map((x) => `${esc(x.name)} ${x.v.toFixed(1)} <small class="${cls(x.chg)}">${x.chg > 0 ? "+" : ""}${x.chg.toFixed(2)}</small>`).join(" · ")}</li>` : ""}
      ${(of.bls || []).length ? `<li><b>BLS 물가·고용</b> <small class="dim">${esc(of.bls[0].period)}</small><br>${of.bls.filter((x) => x.v != null).map((x) => `${esc(x.name)} ${x.v > 0 && x.unit.startsWith("천") ? "+" : ""}${x.v}${x.unit.startsWith("%") ? "%" : x.unit.startsWith("천") ? "천 명" : ""}`).join(" · ")}<br><small class="dim">물가는 전년 같은 달 대비, 고용은 전월 대비 증감</small></li>` : ""}
    </ul></div>` : "";
    const cps = (b.checkpoints || []).length ? `<div class="bcol"><h4>🗓️ 오늘 체크포인트</h4><ul class="bn">${b.checkpoints.map((c) => `<li>${c.time ? `<b>${esc(c.time)}</b> ` : ""}${esc(c.title)}</li>`).join("")}</ul></div>` : "";
    const ktop = (b.kr_top || []).length ? `<div class="bcol"><h4>🇰🇷 국내 감시 종목 상승 상위</h4><ul class="bn">${b.kr_top.map((r) => `<li>${esc(r.name)} ${sg(r.chg)} <small class="dim">${esc(r.sector)}${r.val ? ` · 거래대금 ${eok(r.val)}` : ""}</small></li>`).join("")}</ul></div>` : "";
    const rg = b.reg && b.reg.SP500 ? `<div class="bcol"><h4>🇺🇸 미국 정규장 마감</h4><div class="bfs">${[["SP500", "S&P500"], ["XYZ100", "나스닥100"], ["SOXL", "SOXL"], ["EWY", "EWY"]].filter(([k]) => b.reg[k]).map(([k, n]) => `<span class="bf"><small>${n}</small> ${sg(b.reg[k].chg)}</span>`).join("")}</div></div>` : "";
    const fl = (b.flows || []).length ? `<div class="bcol">${b.flows.map((g) => flowTable(g, 5, true)).join("")}</div>` : "";
    const mom = (b.momentum || []).length ? `<div class="bcol">${momHtml({ sectors: b.momentum }, true)}</div>` : "";
    const lv = b.lev && (b.lev.items || []).length ? `<div class="bwide">${levHtml(b.lev, true)}</div>` : "";
    const ev = lv + (b.watch && (b.watch.items || []).length ? `<div class="bwide">${watchHtml(b.watch, true)}</div>` : "") + (b.eve && (b.eve.fut || []).length ? eveHtml(b.eve) : "");
    return ev + top + ofh + cps + rg + mom + fl + ktop + `<div class="bcol"><h4>📍 가장 크게 움직인 순간</h4><ul>${mv || '<li class="dim">최근 24시간 변곡점 없음</li>'}</ul></div>
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

  /* ── 첫 화면 '📰 메인 뉴스' — 운영자 주요 이슈(data/headline.json) + 최근 중요 속보(1분마다 갱신) ── */
  let headline = [], checks = [];
  async function loadHeadline() {
    try { checks = await (await fetch(`data/checkpoints.json?t=${Math.floor(Date.now() / 600000)}`)).json(); } catch { /* 없음 */ }
    try {
      const h = await (await fetch(`data/headline.json?t=${Math.floor(Date.now() / 60000)}`)).json();
      const today = kstDay(Date.now());
      headline = (h.items || []).filter((x) => !x.until || x.until >= today);
    } catch { /* 없음 */ }
  }
  const normT = (t) => String(t || "").replace(/^\[[^\]]*\]\s*/, "").replace(/[^0-9A-Za-z가-힣]/g, "").slice(0, 18);
  function mainNews() {
    const now = Date.now();
    const pool = news.filter((n) => n.text && now - n.ts < 6 * 3600e3 && !isStrat(n) && impScore(n) >= 55)
      .sort((a, b) => impScore(b) - impScore(a) || b.ts - a.ts);
    return dedupe(pool, false).slice(0, 6).sort((a, b) => b.ts - a.ts);
  }
  // 메인 뉴스 한 줄 요약: 앞머리 [속보]·❗·◈ 같은 꼬리표, 날짜·시각, 끝의 [작성자]·(종합) 제거 → 첫 문장 → 80자 안쪽
  function gist(t, max = 80) {
    let s = String(t || "").replace(/\s+/g, " ").trim();
    s = s.replace(/\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\.?\s*\d{1,2}:\d{2}(:\d{2})?/g, " ");
    for (let k = 0; k < 3; k++) s = s.replace(/^\s*(\[[^\]]{1,14}\]|【[^】]{1,14}】|[❗❕‼️⚠🔴🟥🚨⚡📢📣◈◆◇■□▶▷●○※•·\-–—>\uFE0F]+)\s*/u, "");
    s = s.replace(/\s*(\[[^\]]{2,30}\]|\((종합|상보|속보)\d?\))\s*$/u, "").replace(/…$/, "").trim();
    const m = s.match(/^(.{18,}?)(?:\.{2,}|…|[.!?。])(\s|$)/u);
    if (m && m[1].length < s.length) s = m[1];
    s = s.replace(/[.。…\s]+$/, "");
    if (s.length > max) {
      const cut = s.slice(0, max), sp = Math.max(cut.lastIndexOf(" "), cut.lastIndexOf(","));
      s = (sp > max * 0.6 ? cut.slice(0, sp) : cut).replace(/[,\s]+$/, "") + "…";
    }
    return s;
  }
  function drawHeroLive() {
    const box = q("#heroLive"); if (!box) return;
    const pins = headline.map((x) => `<li class="mn-pin"><a href="#headline"><span class="mn-t">📌 ${esc(x.tag || "주요 이슈")}</span> <b>${esc(x.title)}</b>${x.when ? ` <small>${esc(x.when)}</small>` : ""}</a></li>`);
    const live = mainNews().map((n) => {
      const g = gist(n.text), full = n.text.replace(/…$/, "");
      const t = g !== full ? `<span class="mn-x" data-open="0" title="눌러서 전체 보기">${esc(g)}</span><span class="mn-full" hidden>${esc(full)}</span>` : esc(g);
      const v = n.verify === "official" ? " · 🏛 공식" : n.verify === "multi" ? " · ✔ 복수 출처" : n.verify === "unconfirmed" ? " · ⚠ 미확인" : "";
      return `<li><span class="mn-t">${hm(n.ts)}</span> ${t}${n.series_n > 1 ? ` <small>· 같은 발언 외 ${n.series_n - 1}건</small>` : ""} <small>${esc(n.src || "")}${v}</small></li>`;
    });
    if (!pins.length && !live.length) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `<p class="mn-h"><span class="hl-dot"></span><b>📰 메인 뉴스</b> <small>최근 6시간 중요 속보 · 1분마다 갱신</small><a href="#news">속보 전체 →</a></p><ul class="mn-list">${pins.join("")}${live.join("")}</ul>`;
  }

  /* ── 속보 목록 ── */
  const serOpen = new Set();
  document.addEventListener("toggle", (e) => { const d = e.target; if (d && d.matches && d.matches(".nw-ser")) { if (d.open) serOpen.add(d.dataset.ser); else serOpen.delete(d.dataset.ser); } }, true);
  const VER = { official: ["🏛 공식 발표", "v-ok"], multi: ["✔ 복수 출처", "v-ok"], single: ["단일 출처", "v-one"], unconfirmed: ["⚠ 미확인·보도 인용", "v-warn"] };
  const isStrat = (n) => n.kind === "증권사 시황" || n.kind === "시황 분석";
  // 중요도: 서버가 매긴 imp(0~100, 상 60↑·중 35↑) — 없으면 예전 계산
  const impScore = (n) => n.imp != null ? n.imp : (n.pivot ? 8 : 0) + (n.hot ? 4 : 0) + (n.verify === "multi" ? 2 : 0) + (n.verify === "official" ? 3 : 0) + (n.nsrc || 1);
  const isMajor = (n) => n.imp != null ? n.imp >= 60 : (n.pivot || n.hot || n.verify === "multi" || n.verify === "official" || n.kind === "섹터 시세");
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
      const lvb = n.lv === "상" ? `<span class="nw-v v-imp" title="중요도 ${n.imp}">🔥 중요</span>` : n.lv === "중" ? `<span class="nw-v v-one" title="중요도 ${n.imp}">중요도 중</span>` : "";
      const v = VER[n.verify] ? `<span class="nw-v ${VER[n.verify][1]}">${VER[n.verify][0]}${n.nsrc > 1 ? ` ${n.nsrc}곳` : ""}</span>` : "";
      const tr = n.tr === "auto" ? `<span class="nw-v v-tr" title="${esc(n.orig || "")}">🌐 자동 번역</span>` : n.tr === "fail" ? `<span class="nw-v v-warn">🌐 번역 실패·원문</span>` : "";
      const XC = { ok: ["🌐 외신 확인", "v-ok"], ref: ["🌐 해외 보도", "v-one"], diff: ["⚠ 외신과 수치 다름", "v-warn"] };
      const xc = n.xc && XC[n.xc.st] ? `<span class="nw-v ${XC[n.xc.st][1]}">${XC[n.xc.st][0]} · ${n.xc.src.map(esc).join("·")}</span>` : "";
      const xcl = n.xc && XC[n.xc.st] ? `<p class="nw-xc"><b>원문</b> ${esc(n.xc.en)} <small class="dim">— ${esc(n.xc.src[0])}${n.xc.ko ? ` · 번역: ${esc(n.xc.ko)}` : ""}</small></p>` : "";
      const also = (n.also || []).length ? `<span class="nw-also">후속: ${n.also.map((a) => `${esc(a.osrc ? a.osrc + "·" + a.src : a.src)} ${hm(a.ts)}`).join(", ")}</span>` : "";
      return `<li class="nw${n.pivot ? " piv" : ""}${sel === n.ts ? " sel" : ""}${n.verify === "unconfirmed" ? " unv" : ""}" data-ts="${n.ts}">
        <div class="nw-t"><b>${hm(n.ts)}</b><span>${ago(n.ts)}</span></div>
        <div class="nw-b"><p class="nw-txt${n.kind === "섹터 시세" ? " sector" : ""}">${n.pivot ? "🔴 " : ""}${esc(n.text)}</p>${n.sub ? `<p class="nw-sub">${esc(n.sub)}</p>` : ""}${pv}
          <p class="nw-m">${n.tags.map((t) => `<span class="nw-tag">${esc(t)}</span>`).join("")}${isStrat(n) ? `<span class="nw-tag strat">${esc(n.kind)}</span>` : ""}${lvb}${v}${xc}${tr}
          <span class="nw-src">${n.verify ? "최초 " : ""}${n.osrc ? `${esc(n.osrc)} · ${esc(n.src)} 경유` : esc(n.src)} ${hm(n.ts)}${lag}</span></p>
          ${xcl}${also ? `<p class="nw-m">${also}</p>` : ""}${n.series_n > 1 ? `<details class="nw-ser" data-ser="${n.ts}"${serOpen.has(String(n.ts)) ? " open" : ""}><summary>🧹 같은 ${esc(n.series_key)} 발언·발표 ${n.series_n - 1}건 더(2시간 안 연속, 한 줄로 묶음)</summary><ul>${(n.series || []).map((x) => `<li><b>${hm(x.ts)}</b> ${esc(x.text)}</li>`).join("")}</ul></details>` : ""}${rs ? `<p class="nw-m">${rs}</p>` : ""}</div></li>`;
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

  const redraw = () => { drawHeroLive(); drawWorld(); drawSpot(); drawWatch(); drawSectors(); drawS7(); drawFlows(); drawBrief(); if (full) { drawCharts(); drawMoves(); drawTrend(); drawList(); } };
  const setKw = (label, pat) => {
    try { kwFilter = { label, rx: new RegExp(pat, "i") }; } catch { kwFilter = null; }
    tag = "전체"; shown = 30; drawTrend(); drawList(); q("#news").scrollIntoView({ behavior: "smooth" });
  };
  document.addEventListener("click", (e) => {
    const mx = e.target.closest(".mn-x, .mn-full");
    if (mx) { const li = mx.closest("li"), x = li.querySelector(".mn-x"), f = li.querySelector(".mn-full"), open = f.hidden; f.hidden = !open; x.hidden = open; return; }
    const t = e.target.closest("[data-kw]");
    if (t && q("#trendBox") && q("#trendBox").contains(t)) {
      if (kwFilter && kwFilter.label === t.dataset.name) { kwFilter = null; drawTrend(); drawList(); } else setKw(t.dataset.name, t.dataset.kw);
      return;
    }
    if (e.target.closest("[data-clear-kw]")) { kwFilter = null; drawTrend(); drawList(); return; }
    const ht = e.target.closest("[data-hr-tab]"); if (ht) { hrTab = ht.dataset.hrTab; hrSlot = null; drawSectors(); return; }
    const hs = e.target.closest("[data-hr-slot]"); if (hs) { hrSlot = hs.dataset.hrSlot; drawSectors(); return; }
    const lt = e.target.closest("[data-ld-tab]"); if (lt) { ldTab = lt.dataset.ldTab; ldOpen = null; drawSectors(); return; }
    const lo = e.target.closest("[data-ld-open]"); if (lo) { const n = lo.dataset.ldOpen; ldOpen = ldOpen === n ? null : n; drawSectors(); return; }
    if (e.target.closest("[data-fixsec]")) { fixSecOpen = !fixSecOpen; drawSectors(); return; }
    const so = e.target.closest("[data-sort]");
    if (so) {
      const [t, k] = so.dataset.sort.split(":"), st = sortSt[t];
      if (st.k === k) st.d = -st.d; else { st.k = k; st.d = k === "name" ? 1 : -1; }
      if (t === "flow") drawFlows(); else if (t === "s7") drawS7(); else drawSectors();
      return;
    }
    const fo = e.target.closest("[data-flow-open]"); if (fo) { const n = fo.dataset.flowOpen; flowOpen = flowOpen === n ? null : n; drawFlows(); return; }
    const tg = e.target.closest("[data-sec-toggle]");
    if (tg) { const n = tg.dataset.secToggle; openSector = openSector === n ? null : n; drawSectors(); return; }
    const st = e.target.closest("[data-sec-tag]"); if (st && q("#news")) { kwFilter = null; tag = st.dataset.secTag; shown = 30; drawTrend(); drawList(); q("#news").scrollIntoView({ behavior: "smooth" }); return; }
    const sk = e.target.closest("[data-spot-kw]"); if (sk && q("#news")) { setKw(sk.dataset.spotName, sk.dataset.spotKw); return; }
    const sc = e.target.closest("[data-spot-chart]"); if (sc && window.trlChart) window.trlChart.open({ coin: sc.dataset.spotChart, name: sc.dataset.spotName, sel: null, news });
  });
  (async () => { await Promise.all([loadNews(), loadNotes(), loadHeadline(), loadBriefs(), full ? loadCandles() : null]); redraw(); })();
  setInterval(loadBriefs, 600000);
  setInterval(async () => { await loadNews(); redraw(); }, 60000);                 // 속보·변곡점 1분마다
  setInterval(loadNotes, 600000);
  setInterval(async () => { await loadHeadline(); drawHeroLive(); }, 300000);   // 주요 이슈 5분마다
  if (full) setInterval(async () => { await loadCandles(); redraw(); }, 120000);  // 지수 2분마다
})();
