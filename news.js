/* 실시간 속보 · 변곡점 — 뉴스(live 브랜치 news.json)와 가격 변화를 시각으로 연결
   - 빨간 점(🔴)은 '변곡점 구간 관련 뉴스'에만 붙는다.
   - 해석은 사람이 쓴 '💡 해석' 노트(data/notes.json)로만 싣는다(블로그 글 연결은 2026-10-28 뺌). */
"use strict";
(() => {
  const NEWS_URL = "https://raw.githubusercontent.com/ingforme82-commits/trend-lab/live/news.json";
  const API_URL = "https://api.github.com/repos/ingforme82-commits/trend-lab/contents/news.json?ref=live";
  // 작은 차트 카드: 하이퍼리퀴드 5분봉(xyz:) 또는 서버가 넣어 준 시계열(srv: 금리·달러)
  const CARDS = [
    { code: "NQ", k: "xyz:XYZ100", n: "나스닥100", d: 0 },
    { code: "K200", k: "xyz:KR200", n: "코스피200", d: 2 },
    { code: "WTI", k: "xyz:CL", n: "WTI 무기한", d: 2, u: "$" },
    { code: "US10Y", k: "srv:US10Y", n: "미 10년물 금리", d: 3, suf: "%", bp: true },
    { code: "DXY", k: "srv:DXY", n: "달러인덱스", d: 2 },
    { code: "GOLD", k: "xyz:GOLD", n: "금 선물", d: 1, u: "$" },   // 11/21 운영자: 금 변동성도 속보와 같이
  ];
  const COIN = { NQ: "xyz:XYZ100", SP: "xyz:SP500", K200: "xyz:KR200", WTI: "xyz:CL", BRENT: "xyz:BRENTOIL", GOLD: "xyz:GOLD", US10Y: "srv:US10Y", DXY: "srv:DXY", KOSPI: "srv:KOSPI", KOSDAQ: "srv:KOSDAQ" };
  const REACT = CARDS.slice(0, 3);   // 목록의 '이후' 변화: 나스닥100·코스피200·WTI
  const H = 24;
  const q = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const kst = (ms) => new Date(ms + (new Date().getTimezoneOffset() + 540) * 60000);
  const marketLocale = document.documentElement.dataset.marketLocale || "ko-KR";
  const hm = (ms) => { const d = kst(ms); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const ago = (ms) => { const m = Math.round((Date.now() - ms) / 60000); return m < 1 ? "방금" : m < 60 ? `${m}분 전` : m < 1440 ? `${Math.floor(m / 60)}시간 전` : `${Math.floor(m / 1440)}일 전`; };
  const setText = (s, t) => { const e = q(s); if (e) e.textContent = t; };
  const fmtMove = (m) => `${m.move > 0 ? "+" : ""}${m.move}${m.unit === "bp" ? "bp" : "%"}`;
  const eok = (v) => v >= 1e12 ? `${(v / 1e12).toFixed(1)}조` : `${Math.round(v / 1e8).toLocaleString("ko-KR")}억`;
  const cls = (v) => (v > 0.005 ? "c-up" : v < -0.005 ? "c-dn" : "c-fl");
  const pct = (v) => v == null ? "-" : `<b class="${cls(v)}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</b>`;

  const englishNews = new URLSearchParams(location.search).get("lang")?.toLowerCase() === "en";
  const sourceName = (item) => String(item.osrc || "").trim() || String(item.src || "").trim();
  function publicNews(snapshot) {
    const channels = new Set([
      ...Object.keys(snapshot.health?.tg?.by_src || {}),
      ...(snapshot.tgsum?.channels || []).map((entry) => entry.name),
    ].filter(Boolean).map((name) => String(name).trim().toLowerCase()));
    const channel = (name) => /^(telegram|텔레그램)$/i.test(name) || channels.has(name.toLowerCase());
    const visible = (item) => {
      const source = sourceName(item);
      if (channel(source)) return false;
      return Boolean(source || item.verify === "official") && (item.kind !== "텔레그램" || Boolean(String(item.osrc || "").trim()));
    };
    const items = snapshot.items.filter(visible).map((item) => ({
      ...item, also: item.also?.filter(visible),
    }));
    const moves = (snapshot.moves || []).map((move) => ({
      ...move, items: move.items?.filter(visible),
    }));
    const topics = (snapshot.tgsum?.topics || []).map((topic) => ({
      ...topic,
      lines: (topic.lines || []).map((line) => ({
        ...line, srcs: (line.srcs || []).filter((name) => typeof name === "string" && name.trim() && !channel(name.trim())),
      })).filter((line) => line.srcs.length),
    })).filter((topic) => topic.lines.length);
    return { items, moves, topics };
  }
  const newsText = (item) => englishNews && item.lang === "en" && typeof item.orig === "string" && item.orig.trim()
    ? item.orig : item.text;
  let news = [], moves = [], series = {}, notes = [], candles = {}, candles1 = {}, sel = null, tag = "전체", shown = 10;
  // 속보 필터: 중요도·시간·검증·정렬(분류는 tag 칩)
  const flt = { imp: "all", hrs: 0, ver: "all", sort: "new" };
  // 시황 구분·검색(2026-11-21 UX): 분류는 태그·출처 종류·문장 속 단어로만 나눈다(새 중요도 계산 없음)
  let view = "all", query = "";
  let tgsum = null, world = [], spot = [], trend = [], sectors = [], brief = null, kwFilter = null, momentum = null, watch = null, lev = null, flows = null, flowOpen = null;   // kwFilter: {label, rx}

  /* ── 데이터 ── */
  // GitHub API 는 IP당 시간당 60번 — 1분마다 부르면 1시간 뒤 막혀 20분 동안 5분 늦은 사본을 봤다(11/13 점검).
  // → API 는 2분에 한 번(시간당 30번)만, 사이에는 raw(최대 5분 캐시)를 받고, 둘 중 더 새 것(updated)을 쓴다. 숨긴 탭은 쉰다.
  let apiBlockedUntil = 0, apiLastAt = 0, newest = null;
  const API_GAP = 115000;
  const hasTrendGroups = (data) => {
    const groups = data?.chan?.groups;
    return Array.isArray(groups) && ["kr", "us", "jp", "tw"].every((cc) =>
      groups.some((group) => group.cc === cc && Array.isArray(group.items) && group.items.length > 0));
  };
  const keep = (j) => {
    const complete = j && Number.isFinite(j.updated) && Array.isArray(j.items) && hasTrendGroups(j);
    if (complete && (!newest || j.updated >= (newest.updated || 0))) newest = j;
    return newest;
  };
  async function fetchNews() {
    const now = Date.now();
    if (newest && window.trlNewsHealth?.direct && now - window.trlNewsHealth.checked < 15000) return newest;
    if (now > apiBlockedUntil && now - apiLastAt >= API_GAP) {
      apiLastAt = now;
      try {
        const r = await fetch(API_URL, { headers: { Accept: "application/vnd.github.raw+json" }, cache: "no-cache" });
        if (r.ok) {
          const payload = await r.json();
          if (payload && Number.isFinite(payload.updated) && Array.isArray(payload.items) && hasTrendGroups(payload)) {
            return keep(payload);
          }
        }
        if (r.status === 403 || r.status === 429) apiBlockedUntil = now + 20 * 60000;
      } catch { /* raw로 */ }
    }
    try { return keep(await (await fetch(`${NEWS_URL}?t=${Math.floor(now / 60000)}`)).json()); } catch (e) { if (newest) return newest; throw e; }
  }
  let nhSnapshot = null;
  let fastBusy = false, auxAt = 0, fastTag = '';
  async function directNews() {
    const url = window.trlRtUrl;
    if (!/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(url || "")) return null;
    const started = performance.now();
    const response = await fetch(url + '/news?tag=' + encodeURIComponent(fastTag), {cache:'no-store', signal:AbortSignal.timeout(2500)});
    if (!response.ok) throw Error('Direct news unavailable');
    window.trlNewsHealth = {direct:true, checked:Date.now(), roundTripMs:performance.now()-started};
    if (response.status === 204) return newest;
    const data = await response.json();
    if (!Array.isArray(data.items) || !Number.isFinite(data.updated)) throw Error('Invalid direct news');
    fastTag = response.headers.get('ETag') || '';
    window.trlNewsHealth = {direct:true, checked:Date.now(), roundTripMs:performance.now()-started};
    return keep(data);
  }
  const isRecent = (ts, now, hours) => Number.isFinite(ts) && ts <= now && now - ts < hours * 3600e3;
  async function loadNews(preloaded = null) {
    try {
      const incoming = preloaded || await fetchNews();
      const full = hasTrendGroups(incoming)
        ? incoming
        : hasTrendGroups(newest) ? newest : await fetchNews();
      const j = incoming && full && incoming !== full
        ? {...full, ...incoming, chan: full.chan}
        : full;
      if (hasTrendGroups(j)) window.trlChan = j.chan; // 추세 데이터는 속보 시각 비교와 비동기 보조 조회보다 먼저 반영
      if (!preloaded && !window.trlNewsHealth?.direct) window.trlNewsHealth = {direct:false, checked:Date.now()};
      if (Date.now() - auxAt >= 55000) {
        auxAt = Date.now();
        try {
          const url = `https://raw.githubusercontent.com/ingforme82-commits/trend-lab/quotes/nh-quotes.json?t=${Math.floor(Date.now() / 60000)}`;
          const response = await fetch(url, { signal: AbortSignal.timeout(8000), cache: "no-store" });
          if (response.ok) nhSnapshot = await response.json();
        } catch { /* 최근 발행본을 유지하고 마지막 성공 시각을 표시 */ }
      }
      if (!j || !Array.isArray(j.items) || !Number.isFinite(j.updated) || j.updated < (window.trlUpdated || 0)) return;
      for (const row of (j.lev && j.lev.items) || []) {
        const quote = nhSnapshot?.items?.find((item) => item.sym === row.sym);
        if (!quote || !Number.isFinite(quote.px) || !Number.isFinite(quote.base) || quote.px <= 0 || quote.base <= 0) continue;
        const age = Date.now() - quote.checked_at;
        if (quote.sess === "reg") row.nhRegular = quote;
        else row.ext = { ...quote, stale: quote.stale || !Number.isFinite(age) || age > 3 * 60000 || age < -60000 };
      }
      const board = (j.brief && j.brief.ext) || j.ext;              // 시간외 시세판(NH 우선, 실패 시 야후) — 1분마다
      for (const row of (j.lev && j.lev.items) || []) {
        const fresh = row.ext && !row.ext.stale && Date.now() - row.ext.checked_at < 3 * 60000;
        const r = board && (board.rows || []).find((x) => x.sym === row.sym);
        if (!fresh && r && r.px > 0 && r.base > 0) row.ext = { ...r, source: r.src === "NH" ? "NH투자증권" : "야후", board: true };
      }
      const commit = () => {
      if (j.updated < (window.trlUpdated || 0)) return;
      const visible = publicNews(j);
      news = visible.items.sort((a, b) => b.ts - a.ts); moves = visible.moves; series = j.series || {};
      tgsum = { topics: visible.topics }; window.trlAuto = j.auto_issues || []; world = j.world || []; spot = j.spot || []; trend = j.trending || []; sectors = j.sectors || []; brief = j.brief || null;

      window.trlRtUrl = /^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(j.rt_url || "") ? j.rt_url : null; window.trlDow = j.dow || {}; window.trlTnx = j.us10y || {}; window.trlUst = j.ust || {}; window.trlKr = j.kr || {}; window.trlReg = j.reg || {}; momentum = j.momentum || null; flows = j.flows || null; s7 = normalizeS7(j); leaders = j.leaders || null; watch = j.watch || null; lev = j.lev || null; window.trlBrief = brief || {}; window.trlFlows = flows || {}; window.trlS7 = s7 || {}; window.trlLev = lev || {}; window.trlUpdated = j.updated || Date.now(); if (typeof window.loadTicks === "function" && !window.__tickRefreshed) { window.__tickRefreshed = true; window.loadTicks(); } if (typeof window.loadBand === "function" && !window.__pinNotice) window.loadBand(); window.trlSectors = sectors; window.trlWorld = world; window.trlSpot = spot; window.trlTrend = trend; window.trlNotesReady = true; window.trlChan = j.chan || null;
      window.trlMoves = moves; window.trlSeries = series; window.trlNews = news;
      if (typeof window.renderHeadline === "function") window.renderHeadline();
      window.dispatchEvent(new Event('trl:news'));
      const status = q("#newsStamp"); if (status) status.hidden = true;
      drawTicker();
      };
      if(window.trlViewport)window.trlViewport.update(commit);else commit();
    } catch { const status = q("#newsStamp"); if (status && !window.trlUpdated) status.hidden = false; }
  }
  async function loadNotes() {
    try { notes = await (await fetch(`data/notes.json?t=${Math.floor(Date.now() / 600000)}`)).json(); window.trlNotes = notes; } catch { /* 없음 */ }
  }
  let sessionQuotes = null;
  async function loadSessionQuotes() {
    try {
      const r = await fetch(`data/session_quotes.json?t=${Math.floor(Date.now() / 60000)}`);
      if (r.ok) sessionQuotes = await r.json();
    } catch { /* 확인한 캡처 유지 */ }
  }
  function sessionQuotesHtml() {
    const s = sessionQuotes;
    if (!s || !s.until || Date.now() > Date.parse(s.until)) return "";
    const items = (s.items || []).filter((x) => Number.isFinite(x.px) && x.px > 0 && Number.isFinite(x.base) && x.base > 0 && Number.isFinite(Date.parse(x.at)));
    if (!items.length) return "";
    return `<div class="lvbox"><p class="mm-h">☀️ ${esc(s.session)} <small>수동 캡처</small></p><div class="lc-g">${items.map((x) => {
      const delta = x.px - x.base, chg = delta / x.base * 100, sign = delta > 0 ? "+" : delta < 0 ? "-" : "";
      return `<div class="lc"><p class="lc-h"><b>${esc(x.sym)}</b> <small>${esc(s.session)}</small></p><p class="lc-p"><span class="lc-quote"><b class="lc-px">$${x.px.toFixed(2)}</b> <b class="${cls(chg)}">${sign}${Math.abs(chg).toFixed(2)}%</b></span></p><p class="lc-f">정규장 종가 ${x.base.toFixed(2)} 대비</p><p class="lc-f">${md2(Date.parse(x.at))} ${hm(Date.parse(x.at))} KST 화면 확인</p></div>`;
    }).join("")}</div><p class="mm-f">${esc(s.source)}</p></div>`;
  }
  async function loadCandles() {
    const end = Date.now(), start = end - H * 3600e3;
    const fetchRows = async (s, interval, from) => {
      try {
        const r = await fetch("https://api.hyperliquid.xyz/info", { method: "POST", headers: { "Content-Type": "application/json" },
          signal: AbortSignal.timeout(8000),
          body: JSON.stringify({ type: "candleSnapshot", req: { coin: s.k, interval, startTime: from, endTime: end } }) });
        if (!r.ok) return;
        const rows = (await r.json()).map((c) => [c.t, +c.c]).filter(([t, v]) => Number.isFinite(t) && v > 0);
        if (rows.length < 2) return;
        if (interval === "5m") candles[s.k] = rows;
        else candles1[s.k] = rows;
      } catch { /* 이전 값 유지 */ }
    };
    await Promise.all(REACT.map((s) => fetchRows(s, "5m", start)));
    if (window.trlViewport) window.trlViewport.update(drawCharts); else drawCharts();
    await Promise.all(REACT.map((s) => fetchRows(s, "1m", start - 10 * 60000)));
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
  const rowsOf = (k) => {
    if (k.startsWith("srv:")) return series[k.slice(4)] || [];
    const direct = candles[k] || [];
    const published = series[CARDS.find((s) => s.k === k)?.code] || [];
    return published.length >= 2 && (published.at(-1)[0] > (direct.at(-1)?.[0] || 0) || direct.length < 2)
      ? published : direct;
  };

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
  const tickRow = (pick) => pick.map((n) => `<a class="tk-i${n.pivot ? " hot" : ""}" href="${q("#news") ? "#news" : "index.html#news"}" data-ts="${n.ts}"><b>${hm(n.ts)}</b>${n.pivot ? "🔴 " : ""}${n.lang === "en" ? "🌐 " : ""}${esc(gist(newsText(n), 110))}${n.series_n > 1 ? ` <small>· 같은 발언 외 ${n.series_n - 1}건</small>` : ""}</a>`).join("");
  function tickShow(pick) {
    const box = q("#ticker"); if (!box) return;
    const tr = box.querySelector(".tk-track");
    if (!tr) return;
    tickPick = pick; pick.shownAt = Date.now();
    tr.innerHTML = tickRow(pick);
    tr.style.animationDuration = `${Math.max(30, pick.reduce((a, n) => a + Math.min(110, n.text.length), 0) * 0.28) / 1.5}s`;   // 글 길이에 맞춰 기존보다 1.5배 빠르게
  }
  function drawTicker() {
    const box = q("#ticker"); if (!box) return;
    // 최근 1시간 안의 주요 뉴스만 표시한다.
    const score = (n) => (n.pivot ? 8 : 0) + (n.hot ? 4 : 0) + (n.kind === "섹터 시세" ? 3 : 0)
      + ((n.tags || []).some((t) => ["중동·유가", "연준·금리", "반도체", "AI·빅테크", "한국", "지수"].includes(t)) ? 1 : 0)
      - (n.kind === "증권사 시황" || n.kind === "시황 분석" ? 2 : 0) - (/입찰|낙찰|응찰|Bid-to-Cover|\$거시경제/.test(n.text) ? 2 : 0);
    const now = Date.now();
    const recent = news.filter((n) => isRecent(n.ts, now, 1));
    const pick = dedupe(recent.map((n) => [score(n), n]).sort((a, b) => b[0] - a[0] || b[1].ts - a[1].ts).map((x) => x[1])).slice(0, 12).sort((a, b) => b.ts - a.ts);
    const key = pick.map((n) => n.ts + (n.pivot ? "p" : "")).join(",");
    if (!pick.length) { box.hidden = true; box.innerHTML = ""; tickerKey = ""; tickPending = null; return; }
    if (key === tickerKey) return;
    tickerKey = key;
    const lab = `📡<span class="tk-lt"> 주요 시황</span> <small>최근 1시간<span class="tk-lt"> · ${pick.length}건 · 중복 없이</span></small>`;
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
      // 새 속보가 있거나 기존 항목이 만료되면 바로 반영한다.
      const stale = !tickPick.shownAt || now - tickPick.shownAt >= 60000 || document.hidden || pick[0]?.ts !== tickPick[0]?.ts || tickPick.some((n) => !isRecent(n.ts, now, 1));
      if (stale) { tickPending = null; tickShow(pick); const l = box.querySelector(".tk-label"); if (l) l.innerHTML = lab; }
      else tickPending = pick;
    }
  }
  // 탭·폰 화면으로 돌아오면 기다리던 새 목록을 바로 넣는다
  document.addEventListener("visibilitychange", () => {
    if (document.hidden || !tickPending) return;
    const box = q("#ticker"); if (!box) return;
    const p = tickPending; tickPending = null; tickShow(p);
    const l = box.querySelector(".tk-label"); if (l) l.innerHTML = p.lab;
  });

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
      if (c.length < 2) return `<div class="nc" data-coin="${s.k}" role="button" tabindex="0"><p class="nc-n">${s.n}</p><p class="fine">${s.k.startsWith("srv:") ? "미국장 시세 대기" : "시세 연결 대기 · 눌러서 차트 열기"}</p></div>`;
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

  /* ── 📊 변곡점 지수 반응표: 변곡점 구간마다 다른 지수·유가·금·금리가 같은 구간에 얼마나 움직였는지(사실 집계) ── */
  const REACT_COLS = [["나스닥100", "나스닥100"], ["S&P500", "S&P500"], ["코스피200", "코스피200"], ["WTI", "WTI"], ["브렌트", "브렌트"], ["금", "금"], ["미 10년물 금리", "미 10년물"], ["달러인덱스", "달러"]];
  function drawMoveReact(recent) {
    const box = q("#moveReact"); if (!box) return;
    const seen = new Set(), rows = [];
    for (const m of [...recent].sort((a, b) => b.end - a.end)) {
      const k = m.grp || m.id; if (seen.has(k)) continue; seen.add(k);
      const g = recent.filter((x) => (x.grp || x.id) === k).sort((a, b) => b.ratio - a.ratio)[0];
      const n = (g.items || (g.news || []).map((ts) => news.find((y) => y.ts === ts)).filter(Boolean))[0];
      rows.push({ m: g, n });
      if (rows.length >= 3) break;
    }
    if (!rows.length) { box.hidden = true; return; }
    const cell = (m, name) => {
      const v = m.name === name ? m.move : (m.others || {})[name];
      if (v == null) return `<td class="dim">-</td>`;
      const u = name.includes("금리") ? "bp" : "%";
      const t = `<b class="${cls(v)}">${v > 0 ? "+" : ""}${v}${u}</b>`;
      return m.name === name ? `<td class="mvr-self">${t}</td>` : `<td>${t}</td>`;
    };
    box.hidden = false;
    box.innerHTML = `<p class="fl-gh">📊 변곡점 지수 반응표 <small>최근 1시간</small></p>
      <div class="fl-scroll"><table class="fl-t"><tr><th>구간</th>${REACT_COLS.map(([, h]) => `<th>${h}</th>`).join("")}<th style="text-align:left">같은 시각 뉴스</th></tr>
      ${rows.map(({ m, n }) => `<tr><td class="fl-n">${hm(m.start)}–${hm(m.end)} <small class="dim">${esc(m.name)}${m.kind === "cumulative" ? " 누적" : m.kind === "level" ? " 가격대" : ""}</small></td>${REACT_COLS.map(([k]) => cell(m, k)).join("")}<td class="mvr-n">${n ? `${hm(n.ts)} ${esc(newsText(n).slice(0, 60))}${newsText(n).length > 60 ? "…" : ""}` : `<span class="dim">연결된 뉴스 없음</span>`}</td></tr>`).join("")}
      </table></div>`;
  }

  /* ── 시장을 움직인 순간(변곡점 카드) ── */
  function drawMoves() {
    const box = q("#moveList"); if (!box) return;
    const now = Date.now();
    const recent = moves.filter((m) => isRecent(m.end, now, 1));
    drawMoveReact(recent);
    // 같은 순간(시작 6분 안)은 카드 하나로: 평소 대비 배수가 가장 큰 자산이 제목, 나머지는 '함께 움직임'
    const groups = [];
    for (const m of recent) {
      const g = groups.find((x) => x.grp && x.grp === m.grp);
      if (g) g.list.push(m); else groups.push({ grp: m.grp, list: [m] });
    }
    const list = groups.sort((a, b) => Math.max(...b.list.map((m) => m.end)) - Math.max(...a.list.map((m) => m.end))).slice(0, 3);
    if (!list.length) { box.innerHTML = `<p class="empty">최근 1시간 데이터에서 새 변곡점이 확인되지 않았습니다.</p>`; return; }
    const px = (m) => m.unit === "bp" ? `${(+m.from).toFixed(3)}% → ${(+m.to).toFixed(3)}%` : `${(+m.from).toLocaleString("ko-KR", { maximumFractionDigits: 2 })} → ${(+m.to).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}`;
    box.innerHTML = list.map(({ list: ms }) => {
      ms.sort((a, b) => b.ratio - a.ratio);
      const m = ms[0], co = ms.slice(1);
      const nt = noteFor(m);
      const seenTs = new Set(), ns = [];
      for (const x of ms) for (const n of (x.items || (x.news || []).map((ts) => news.find((y) => y.ts === ts)).filter(Boolean))) {
        if (!seenTs.has(n.ts + n.text)) { seenTs.add(n.ts + n.text); ns.push({ ...n, _a: x.name }); }
      }
      ns.sort((a, b) => b.ts - a.ts);
      const inGrp = new Set(ms.map((x) => x.name));
      // 11/20 운영자: 같은 구간 반응은 자산별 평소 기준 대비 크기 순(m.rx) — 금리·달러·유가 반응이 묻히지 않게. 1배 이상이면 '동반'
      const rxList = m.rx ? m.rx.filter(([k]) => !inGrp.has(k)).slice(0, 4) : Object.entries(m.others || {}).filter(([k]) => !inGrp.has(k)).slice(0, 4);
      const others = rxList.map(([k, v, r]) => `${esc(k)} <b class="${cls(v)}">${v > 0 ? "+" : ""}${v}${k.includes("금리") ? "bp" : "%"}</b>${r >= 1 ? " <small>동반</small>" : ""}`).join(" · ");
      const a30 = m.after30 == null || m.kind === "level" ? "" : (() => { const v = m.after30, same = (v > 0) === (m.move > 0), big = Math.abs(v) >= Math.abs(m.move) * 0.5;
        return ` · 이후 30분 <b class="${cls(v)}">${v > 0 ? "+" : ""}${v}${m.unit === "bp" ? "bp" : "%"}</b> <small>(${Math.abs(v) < Math.abs(m.move) * 0.15 ? "멈춤" : same ? (big ? "크게 이어짐" : "이어짐") : (big ? "크게 되돌림" : "되돌림")})</small>`; })();
      return `<article class="mv" data-asset="${m.asset}" data-start="${m.start}">
        <div class="mv-h"><span class="mv-a ${m.move > 0 ? "pos" : "neg"}">${m.kind === "level" ? `🎯 ${esc(m.name)} ${m.unit === "bp" ? (+m.level).toFixed(2) + "%" : (m.asset === "WTI" || m.asset === "BRENT" || m.asset === "GOLD" ? "$" : "") + (+m.level).toLocaleString("ko-KR")} ${m.move > 0 ? "위로" : "아래로"}` : `${m.kind === "cumulative" ? "⏱ 누적 " : ""}${esc(m.name)} ${m.move > 0 ? "▲" : "▼"} ${fmtMove(m)}`}</span>
          <span class="mv-t">${hm(m.start)}–${hm(m.end)}${m.session ? ` · ${esc(m.session)}` : ""}</span></div>
        <p class="mv-o">${px(m)}${co.length ? ` · <b>함께 움직임</b> ${co.map((x) => `${x.kind === "level" ? "🎯 " : x.kind === "cumulative" ? "⏱ 누적 " : ""}${esc(x.name)}${x.kind === "level" ? ` ${(+x.level).toLocaleString("ko-KR")} ${x.move > 0 ? "위로" : "아래로"}` : ` <b class="${cls(x.move)}">${fmtMove(x)}</b>`} <small>(${hm(x.start)}–${hm(x.end)}${x.session ? ", " + esc(x.session) : ""})</small>`).join(" · ")}` : ""}</p>
        ${others || a30 ? `<p class="mv-o">${others ? `같은 구간 ${others}` : ""}${others ? a30 : a30.replace(/^ · /, "")}</p>` : ""}
        ${ns.length ? `<ul class="mv-n">${ns.slice(0, 4).map((n) => `<li><span class="mv-dot"></span><b>${hm(n.ts)}</b> ${n.lang === "en" ? "🌐 " : ""}${esc(newsText(n))} <small>${esc(sourceName(n))}${co.length ? ` · ${esc(n._a)} 쪽` : ""}${n.lag != null ? ` · <b class="mv-lag">${n.lag < 0 ? `움직임 ${-n.lag}분 전` : n.lag === 0 ? "움직임과 같은 분" : `가격이 먼저 움직이고 ${n.lag}분 뒤`}</b>` : ""}</small></li>`).join("")}</ul>`
          : `<p class="mv-none">시작 전 15분부터 확인한 구간에 연결할 관련 뉴스가 없습니다. 원인은 확인되지 않았습니다.</p>`}
        ${nt ? `<div class="mv-note"><b>💡 ${esc(nt.title)}</b><p>${esc(nt.text)}</p></div>` : ""}
      </article>`;
    }).join("");
  }

  /* ── 해외 지수 ── */
  let asiaQuotes = [];
  async function loadAsiaQuotes() {
    try {
      const url = "https://raw.githubusercontent.com/ingforme82-commits/trend-lab/quotes/asia-quotes.json";
      const response = await fetch(url + "?t=" + Math.floor(Date.now() / 60000), {
        cache: "no-store", signal: AbortSignal.timeout(8000)
      });
      if (!response.ok) return;
      const rows = await response.json();
      if (!Array.isArray(rows)) return;
      asiaQuotes = rows.filter((row) => (["TAIEX", "^N225"].includes(row?.sym) || /^(?:\d{4}|\d{3}[A-Z])\.T$/.test(row?.sym) || /^\d{4,6}[A-Z]?\.TW$/.test(row?.sym)) &&
        [row.px, row.chg, row.at].every(Number.isFinite) && row.px > 0);
      drawWorld();
      drawChan();
    } catch { /* Keep the last successful snapshot. */ }
  }
  function worldQuotes() {
    const rows = new Map(world.filter((w) => w.sym !== "GC=F").map((w) => [w.sym, w]));
    for (const row of asiaQuotes) {
      const prior = rows.get(row.sym);
      if (!prior || row.at > prior.at) rows.set(row.sym, {...row, trend: row.trend || prior?.trend});
      else if (row.at === prior.at && !prior.trend) rows.set(row.sym, row);
      else if (!prior.trend && row.trend) rows.set(row.sym, {...prior, trend: row.trend});
      if (row.sym === "TAIEX") rows.delete("xyz:EWT");
    }
    return [...rows.values()];
  }
  function worldQuoteStamp(w) {
    if (w.live) return "24시간 거래";
    const time = hm(w.at) + " KST";
    if (w.sym === "TAIEX" && w.day) {
      if (!w.intraday) return w.day + " 공식 종가 · TWSE";
      const local = new Date(w.at + 8 * 3600e3);
      const end = Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate(), 5, 30);
      const current = Date.now() < end && Date.now() - w.at <= 900000;
      return w.day + " " + time + (current ? " 장중" : " 마지막 장중값") + " · TWSE";
    }
    const zone = {"^N225": "Asia/Tokyo", "000001.SS": "Asia/Shanghai", "000300.SS": "Asia/Shanghai",
      "^HSI": "Asia/Hong_Kong", "^GDAXI": "Europe/Berlin", "^FCHI": "Europe/Paris", "^STOXX50E": "Europe/Paris"}[w.sym];
    const day = new Intl.DateTimeFormat("sv-SE", {timeZone: zone || "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit"}).format(w.at);
    return day + " 현지 · " + time + " 기준";
  }
  function taiwanAwaiting(day) {
    const now = kst(Date.now());
    return now.getDay() > 0 && now.getDay() < 6 &&
      (now.getHours() < 10 || day !== kstDay(Date.now()).slice(5).replace("-", "/"));
  }
  function taiwanStatus() {
    return kst(Date.now()).getHours() < 10 ? "개장 대기 · 10:00 KST" : "당일 시세 대기";
  }
  function drawWorld() {
    const box = q("#worldGrid"); if (!box) return;
    box.innerHTML = worldQuotes().filter((w) => !/\.(T|TW)$/.test(w.sym)).map((w) => {
      if (w.sym === "TAIEX" && taiwanAwaiting(w.day?.slice(5).replace("-", "/"))) {
        return `<div class="tick"><p class="t-name">대만 · 가권지수</p><p class="fine">${taiwanStatus()}</p></div>`;
      }
      return `<div class="tick"><p class="t-name">${esc(w.region)} · ${esc(w.name)}</p><p class="t-px">${w.px.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}</p>
        <p class="t-ch ${cls(w.chg)}">${w.chg > 0 ? "▲" : w.chg < 0 ? "▼" : ""} ${w.chg > 0 ? "+" : ""}${w.chg.toFixed(2)}%</p>
        ${w.low != null && w.rebound != null ? `<p class="fine">장중 저점 ${w.low.toLocaleString("ko-KR")} · 저점 대비 +${w.rebound.toFixed(2)}%</p>` : ""}
        <p class="fine" style="margin:2px 0 0">${esc(worldQuoteStamp(w))}</p></div>`;
    }).join("");
  }

  /* ── 🔥 화제 종목(종목군): 한 칸에서 번갈아 보이기 ── */
  let spotIdx = 0, spotActive = null, memOpen = null;   // memOpen: "종목군id:심볼"
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
      <div class="spot-top">${s.kind ? `<span class="spot-k">${esc(s.kind)}</span>` : ""}<b class="spot-n">${esc(s.name)}</b><span class="spot-m">${esc(s.market || "")} · ${esc(s.since || "")}부터</span>${head}</div>
      ${s.reason ? `<p class="spot-r">${esc(s.reason)}</p>` : ""}
      ${mem.length ? memBlock(s, mem) : ""}
      <p class="spot-c">최근 24시간 관련 속보 <b>${today}건</b></p>
      ${rel.length ? `<ul class="spot-news">${rel.slice(0, 3).map((n) => `<li><b>${hm(n.ts)}</b> ${n.pivot ? "🔴 " : ""}${esc(newsText(n))}</li>`).join("")}</ul>` : ""}
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
        ${rel.length ? `<ul class="spot-news">${rel.map((n) => `<li><b>${hm(n.ts)}</b> ${n.pivot ? "🔴 " : ""}${esc(newsText(n))} <small class="dim">${esc(sourceName(n))}</small></li>`).join("")}</ul>` : `<p class="dim" style="margin:4px 0">최근 관련 속보가 없습니다.</p>`}
        <div class="spot-btns">${HL_SYMS.has(open.sym) ? `<button class="btn btn-gold btn-sm" data-spot-chart="xyz:${esc(open.sym)}" data-spot-name="${esc(open.name)}">${esc(open.name)} 1분봉</button>` : ""}
          <button class="btn btn-ghost-dark btn-sm" data-mem="${esc(key(open))}">접기</button></div>
      </div>`;
    }
    return `<div class="mem-bar"><span class="mem-l">구성 종목</span>${btns}</div>${detail}`;
  }

  function drawSpot() { /* 종목군은 주도 섹터에 통합한다. */ }

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
      ${compact ? "" : `${methodNote("momentum", "점수 기준 보기", "거래대금 가속도·상대강도·5일선·신고가 근접을 비교합니다. 수급은 점수에 포함되지 않습니다.")}`}</div>`;
  }
  // 🔬 SOXL · KORU 한눈에: 가격 한 줄 + 상태 배지(5일선·20일선·연속 양봉·운영자 가격대) + 20일 범위 막대 + 기초지수 한 줄
  const md2 = (ms) => { const d = kst(ms); return `${d.getMonth() + 1}/${d.getDate()}`; };
  function levCard(x, level, checkedAt) {
    const $$ = (v) => v == null ? "-" : "$" + (+v).toFixed(2);
    const pc = (v) => v == null ? "-" : `${v > 0 ? "+" : ""}${(+v).toFixed(1)}%`;
    if (!x || x.err || x.px == null) return `<div class="lc"><b>${esc((x && x.sym) || "")}</b> <span class="dim">시세를 받지 못함</span></div>`;
    const e = x.ext;
    const active = e && e.live && !e.stale && (e.board ? Date.now() - e.checked_at < 5 * 60000 : e.source === "NH투자증권" ? Date.now() - e.checked_at < 3 * 60000 : Date.now() - e.at < 15 * 60000 && e.at >= x.at);
    const price = active ? e.px : x.px, change = active ? e.chg : x.chg;
    const queried = e && (e.checked_at || checkedAt);
    const nhRegular = x.nhRegular;
    const sourceTime = (quote) => {
      const time = String(quote?.source_time || "");
      const date = String(quote?.source_date || "");
      return /^\d{8}$/.test(date) && /^\d{6}$/.test(time)
        ? `${date.slice(4,6)}/${date.slice(6)} ${time.slice(0,2)}:${time.slice(2,4)}:${time.slice(4)} (증권사 원천)`
        : "원천 시각 확인 불가";
    };
    const regularLine = nhRegular ? `<p class="lc-f">NH 정규장 ${$$(nhRegular.px)} · ${sourceTime(nhRegular)}</p>` : "";
    const queryLabel = queried ? `${new Date(queried).toLocaleString(marketLocale, { timeZone: "Asia/Seoul" })} 한국 시간 조회` : "조회 시각 확인 불가";
    const SN = { pre: "프리마켓", post: "애프터마켓", day: "주간거래" };
    const label = active ? (SN[e.sess] || "시간외") : `${+x.day.slice(5, 7)}/${+x.day.slice(8, 10)} ${x.open ? "장중" : "마감"}`;
    const chip = (ok, t) => `<span class="lc-c ${ok ? "on" : "off"}">${ok ? "▲" : "▼"} ${t}</span>`;
    const C = [chip(x.over_ma5, `5일선 ${x.over_ma5 ? "위" : "아래"} ${pc(x.vs_ma5)}`)];
    if (x.ma20 != null) C.push(chip(x.over_ma20, `20일선 ${x.over_ma20 ? "위" : "아래"} ${pc(x.vs_ma20)}`));
    C.push(`<span class="lc-c ${x.three ? "on" : "mid"}">${x.three ? "적삼병 조건" + (x.open ? " 진행 중" : " 충족") : `연속 양봉 ${x.bull ? x.streak : 0}일`}</span>`);
    if (level) { const d = (x.px / level - 1) * 100; C.push(`<span class="lc-c ${Math.abs(d) < 0.15 ? "mid" : d > 0 ? "on" : "off"}">가격대 $${level} ${Math.abs(d) < 0.15 ? "부근" : d > 0 ? "위" : "아래"}</span>`); }
    let bar = "";
    if (x.hi20 != null && x.lo20 != null && x.hi20 > x.lo20) {
      const pos = Math.max(0, Math.min(100, (x.px - x.lo20) / (x.hi20 - x.lo20) * 100));
      bar = `<div class="lc-r"><small>20일 저가 ${$$(x.lo20)}</small><span class="lc-b"><i style="left:${pos.toFixed(0)}%"></i></span><small>고가 ${$$(x.hi20)}</small></div>`;
    }
    const ext = e ? `<p class="lc-f">${active ? `${e.base > 0 ? `정규장 종가 ${$$(e.base)} 대비` : "기준가 확인 중"}` : `${SN[e.sess] || "시간외"} 마지막 체결 ${$$(e.px)} ${pc(e.chg)} · ${e.at ? md2(e.at) + " " + hm(e.at) : ""}`} <small>· ${esc(e.source || "야후")}${active ? ` · ${e.source_time ? sourceTime(e) : queryLabel}` : ""}</small></p>` : `<p class="lc-f">${x.open ? "정규장 거래 중 — 위 가격이 실시간" : "시간외 거래 없는 시간(정규장 종가 표시)"}</p>`;
    const base = x.base_chg != null ? `기초 ${esc(String(x.base).replace(/\(.*\)/, ""))} <b class="${cls(x.base_chg)}">${pc(x.base_chg)}</b>` : "";
    const mem = x.members ? ` · 구성 대형주 ${x.members.n_up}/${x.members.n} 상승` : "";
    return `<div class="lc"><p class="lc-h"><b>${esc(x.sym)}</b> <small class="dim">${esc(x.name)}</small></p>
      <p class="lc-p"><span class="lc-quote"><b class="lc-px">${$$(price)}</b> <b class="${cls(change)}">${pc(change)}</b></span> <small class="dim">${label}</small></p>${regularLine}${ext}
      <div class="lc-cs">${C.join("")}</div>${bar}${base || mem ? `<p class="lc-f">${base}${mem}</p>` : ""}</div>`;
  }
  function levHtml(L) {
    // 11/18 운영자: SOXL → KORU → (나머지) → SOXS 순. 서버 데이터 순서와 상관없이 화면에서 맞춘다
    const ORD = ["SOXL", "KORU", "DRAM", "SKHY", "MU", "SOXS"], rk = (s) => { const i = ORD.indexOf(s); return i < 0 ? ORD.length - 1 : i; };
    const its = ((L && L.items) || []).slice().sort((a, b) => rk(a.sym) - rk(b.sym));
    if (!its.length) return "";
    return `<div class="lvbox"><p class="mm-h">🔬 SOXL · KORU 한눈에 <small>${hm(L.at)} KST</small></p><div class="lc-g">${its.map((x) => levCard(x, undefined, L.at)).join("")}</div></div>`;
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
    return `<div class="hr"><p class="spot-h">⏱ 시간대별 강세 종목·업종 <small>${hm(H.at)} 기준 KST${blk.open ? "" : " · 장 마감"}</small></p>
      <div class="fl-sort">${order.filter((k) => H[k]).map((k) => `<button class="sc-chip${tab === k ? " on" : ""}" data-hr-tab="${k}">${k === "kr" ? "🇰🇷 한국" : "🇺🇸 미국"}</button>`).join("")}
        <span class="dim">시간대</span>${slots.map((x) => `<button class="sc-chip${x === cur ? " on" : ""}" data-hr-slot="${x.h}">${lab(x)}</button>`).join("")}</div>
      <p class="hr-sec"><b>${lab(cur)} 강한 업종</b> ${(cur.sectors || []).map((g) => `${esc(g.name)} ${pct(g.slot)} <small class="dim">상승 ${g.up}/${g.n} · ${g.top.map(esc).join(", ")}</small>`).join(" · ") || '<span class="dim">-</span>'}
        <small class="dim">· 전체 ${cur.up}/${cur.n}종목 상승</small></p>
      <div class="fl-scroll"><table class="fl-t"><tr>${sth("hr", "name", "종목")}${sth("hr", "slot", "이번 시간", cur.gap ? "시가 갭 포함" : `${cur.h}시부터`)}${sth("hr", "chg", "오늘")}${sth("hr", "val", "거래대금")}<th>업종</th></tr>${rows}</table></div>
      </div>`;
  }
  const risingLeader = (g) => Number.isFinite(g.chg) && g.chg > 0 && g.n > 0 && g.up / g.n >= .5;
  function leaderGroups(blk, kind, market) {
    const result = (blk[kind] || []).filter(risingLeader).map(g => ({...g, rows:(g.rows || []).map(r=>({...r})), relatedPatterns:[]}));
    const symbols = g => new Set((g.rows || []).map(r=>r.sym || r.code).filter(Boolean));
    for (const s of spot || []) {
      if (s.pin || s.id === "ASIA" || s.market !== (market === "us" ? "미국" : "한국") || !Number.isFinite(s.chg) || s.chg <= 0) continue;
      const rows = s.members?.length ? s.members : s.px > 0 ? [{sym:s.id,name:s.name,px:s.px,chg:s.chg}] : [];
      if (!rows.length || rows.some(r=>!Number.isFinite(r.chg) || r.stale)) continue;
      const candidate = {name:s.name, chg:s.chg, n:rows.length, up:rows.filter(r=>r.chg>0).length,
        rows:rows.map(r=>({...r})), val:null, mcap:null, score:null, breadth:rows.filter(r=>r.chg>0).length/rows.length*100, kind:"종목군", relatedPatterns:s.kw ? [s.kw] : []};
      if (!risingLeader(candidate)) continue;
      const set = symbols(candidate);
      const host = result.find(g=>{
        const old = symbols(g), matches = [...set].filter(id=>old.has(id)).length;
        return g.name === candidate.name || (Math.min(old.size,set.size)>0 && matches / Math.min(old.size,set.size) >= .5);
      });
      if (host) host.relatedPatterns.push(...candidate.relatedPatterns);
      else result.push(candidate);
    }
    return result;
  }
  function leaderNews(group) {
    const patterns = (group.relatedPatterns || []).slice();
    const literal = text => Array.from(text, c => "\\^$.*+?()[]{}|".includes(c) ? "\\"+c : c).join("");
    for (const r of group.rows || []) if ((r.name || "").length >= 2) patterns.push(literal(r.name));
    if (group.name) patterns.push(literal(group.name));
    let rx; try {rx=new RegExp(patterns.join("|"),"i");} catch {return "";}
    const related = news.filter(n=>rx.test(n.text+" "+(n.orig || ""))).slice(0,3);
    return related.length ? '<ul class="spot-news">'+related.map(n=>'<li><b>'+hm(n.ts)+'</b> '+esc(newsText(n))+'</li>').join("")+'</ul>' : "";
  }
  function leadersHtml() {
    if (!leaders && !spot.length) return "";
    const tabs = [["kr.industry", "🇰🇷 한국 업종"], ["kr.theme", "🇰🇷 한국 테마"], ["us.industry", "🇺🇸 미국 업종"]];
    if (mode() === "us") tabs.unshift(tabs.pop());
    const tab = ldTab || tabs[0][0];
    const [mk, kd] = tab.split("."), blk = (leaders || {})[mk] || {}, isUs = mk === "us";
    const money = (v) => isUs ? usd(v) : v ? eok(v) : "-";
    const gs = sortRows(leaderGroups(blk, kd, mk), "ld");
    const chips = gs.map((g) => `<button class="sc-chip ld-chip${ldOpen === g.name ? " on" : ""}" data-ld-open="${esc(g.name)}" aria-expanded="${ldOpen === g.name}">
      ${esc(g.name)} ${sg2(g.chg)} <small>상승 ${g.up}/${g.n} · 대금 ${money(g.val)}${g.score == null ? " · 종목군" : ` · 점수 ${g.score}`}</small></button>`).join("");
    const g = gs.find((x) => x.name === ldOpen);
    const mem = g ? `<div class="sc-panel"><div class="fl-scroll"><table class="fl-t"><tr>${sth("ldm", "name", "종목")}${sth("ldm", "chg", "등락")}${sth("ldm", "val", "거래대금")}${sth("ldm", "mcap", "시가총액")}</tr>
      ${sortRows(g.rows || [], "ldm").map((r) => `<tr><td class="fl-n">${esc(r.name)}</td><td>${pct(r.chg)}</td><td>${money(r.val)}</td><td>${money(r.mcap)}</td></tr>`).join("")}</table></div>
      ${leaderNews(g)}</div>` : "";
    return `<div class="ld"><p class="spot-h">🏁 오늘의 주도 섹터·종목 <small>${hm(blk.at || leaders?.at || Date.now())} 기준 KST${blk.open ? "" : " · 장 마감"}</small></p>
      <div class="fl-sort">${tabs.map(([k, l]) => `<button class="sc-chip${tab === k ? " on" : ""}" data-ld-tab="${k}">${l}</button>`).join("")}</div>
      ${sortChips("ld", [["score", "주도 점수순"], ["chg", "등락률순"], ["val", "거래대금순"], ["mcap", "시가총액순"], ["breadth", "상승 비율순"]])}
      <div class="sc-bar">${chips || '<span class="dim">현재 기준을 충족하는 상승 주도 섹터가 없습니다.</span>'}</div>${mem}
      ${methodNote("leader", "주도 점수 기준 보기", "등락률 순위 50%·거래대금 순위 30%·상승 종목 비율 20%를 반영합니다.")}</div>`;
  }
  const methodOpen = new Set();
  function methodNote(key, label, copy) {
    return `<details class="mm-f" data-method="${key}"${methodOpen.has(key) ? " open" : ""}><summary>${label}</summary><p>${copy}</p></details>`;
  }
  document.addEventListener("toggle", (event) => {
    const key = event.target.dataset?.method;
    if (!key) return;
    if (event.target.open) methodOpen.add(key);
    else methodOpen.delete(key);
  }, true);
  function drawSectors() {
    const box = q("#sectorBox"); if (!box) return;
    if (!sectors.length && !leaders && !spot.length) { box.hidden = true; return; }
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
    box.innerHTML = leadersHtml() + hourlyHtml() + momHtml(momentum) + `<p class="fl-sort"><button class="sc-chip${fixSecOpen ? " on" : ""}" data-fixsec="1">📌 관심 섹터(고정) 시세 ${fixSecOpen ? "접기" : "보기"}</button></p>
      ${fixSecOpen ? `<p class="spot-h">📊 관심 섹터 시세</p>
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
      const lv0 = ((lev && lev.items) || []).find((y) => y.sym === x.sym);
      if (lv0 && lv0.px != null) return levCard(lv0, x.level);
      if (x.err || x.px == null) return `<div class="wt-i"><b>${esc(x.name)}</b> <span class="dim">${x.px == null && !x.err ? "개장 전 · 전일 종가 " + $$(x.prev) + " · 5일선 " + $$(x.ma5_prev) : "시세를 받지 못함"}</span></div>`;
      const st = x.open ? "진행 중" : "마감";
      const L = [];
      if (x.focus.includes("gap")) L.push(`갭: 시가 ${$$(x.o)} — 전일 종가 대비 ${sgn(x.gap)} · 전일 고가 ${$$(x.prev_h)} ${x.gap_over_high ? "위" : "아래"}에서 시작`);
      const e = ((lev && lev.items) || []).find((y) => y.sym === x.sym) || {};
      if (x.focus.includes("ma5")) L.push(`이동평균: 5일선 ${$$(x.ma5)} ${x.over_ma5 ? "위" : "아래"} ${sgn(x.vs_ma5)}${e.ma20 ? ` · 20일선 ${$$(e.ma20)} ${e.over_ma20 ? "위" : "아래"} ${sgn(e.vs_ma20)}` : ""}${x.focus.includes("gap") ? ` · 시가도 5일선 ${x.open_over_ma5 ? "위" : "아래"}` : ""}`);
      if (x.focus.includes("three")) L.push(`연속 양봉: 전일까지 ${x.streak_prev}일 → 오늘 ${x.bull ? `양봉 ${st} = ${x.streak}일째` : `양봉 아님(${st})`}${x.three ? ` · <b>적삼병 조건 ${x.open ? "충족 중(마감 전)" : "충족 마감"}</b>` : ""}`);
      if (x.level) L.push(`${$$(x.level)} 구간: ${(() => { const d = (x.px / x.level - 1) * 100; return Math.abs(d) < 0.15 ? "현재가가 그 부근" : `현재가가 ${sgn(d)} ${d > 0 ? "위" : "아래"}`; })()}${x.level_touched ? " · 오늘 고가가 도달" : ""}${(x.level_hits || []).length ? ` · 최근 10거래일 중 넘었다가 아래에서 마감한 날 ${x.level_hits.map((h) => md(h.d)).join("·")}` : ""}`);
      if (!compact) {
        if (e.ext) L.push(`🌙 ${e.ext.sess === "pre" ? "프리마켓" : e.ext.sess === "day" ? "주간거래" : "애프터마켓"} $${(+e.ext.px).toFixed(4)} · 정규장 종가 ${$$(e.ext.base)} 대비 ${(e.ext.px - e.ext.base) >= 0 ? "+" : "-"}$${Math.abs(e.ext.px - e.ext.base).toFixed(4)} (${sgn(e.ext.chg)}) <small class="dim">${e.ext.stale ? "마지막 체결 " : "체결 "}${new Date(e.ext.at).toLocaleString(marketLocale, { timeZone: "Asia/Seoul" })} KST</small>`);
        if (e.base_chg != null) L.push(`기초: ${esc(e.base || "")} ${sgn(e.base_chg)}${e.x3 != null ? ` · ×3 = ${sgn(e.x3)}, 실제와 차이 ${e.x3_gap > 0 ? "+" : ""}${e.x3_gap}%p` : ""}${e.kr200 != null ? ` · 코스피200 야간 ${sgn(e.kr200)}` : ""}${e.members ? ` · 구성 대형주 ${e.members.n_up}/${e.members.n} 상승` : ""}`);
        if (e.h24 && !x.open) L.push(`24시간 시세(하이퍼리퀴드) ${$$(e.h24.px)} · 정규장 가격 대비 ${sgn(e.h24.vs_reg)}`);
      }
      return `<div class="wt-i"><p class="wt-n"><b>${esc(x.name)}</b> ${$$(x.px)} ${sgn(x.chg)} <small class="dim">${md(x.day)} 정규장 ${st} · 고가 ${$$(x.h)} 저가 ${$$(x.l)}</small></p><ul>${L.map((t) => `<li>${t}</li>`).join("")}</ul></div>`;
    };
    return `<div class="wt"><p class="spot-h">👀 ${compact ? esc(w.title || "운영자 관전 포인트") : "운영자 메모·가격대"} <small>${hm(w.at)} KST</small></p>
      ${w.memo ? `<blockquote class="wt-memo">${esc(w.memo)}<cite>— 운영자 관전 포인트</cite></blockquote>` : ""}
      ${its.map(row).join("")}
      ${(w.events || []).filter((e) => e.k === "level" || e.k === "ma5").length ? `<p class="wt-n" style="margin-top:8px"><b>⏱ 가격대·5일선 마지막 전환</b></p><ul class="wt-ev">${w.events.filter((e) => e.k === "level" || e.k === "ma5").slice(0, compact ? 6 : 15).map((e) => `<li><b>${hm(e.ts)}</b> <span class="${e.up ? "c-up" : "c-dn"}">${e.up ? "▲" : "▼"}</span> ${esc(e.text)}${e.n > 1 ? ` <small class="dim">· 오늘 ${e.n}번째 전환</small>` : ""}</li>`).join("")}</ul>` : ""}</div>`;
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
    const rn = (v, u) => `${u === "$" ? "$" : ""}${(+v).toLocaleString("ko-KR", { maximumFractionDigits: 3 })}${u === "원" ? "원" : ""}`;
    const rfx = (f) => f && f.ref != null ? ` <small class="dim">(기준 ${esc(f.base || "")} ${rn(f.ref, f.u)})</small>` : "";   // 11/16 운영자: 기준 지표 숫자 명시
    const fv = (n) => { const f = fut[n]; return f ? `${esc(n)} ${f.u === "$" ? "$" : ""}${(+f.px).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}${f.u === "원" ? "원" : ""} ${sg2(f.chg)}${rfx(f)}` : ""; };
    // 한국 24시간 시세: 장 밖이면 '마지막 거래소 종가 이후 변화'(11/15 — 24시간 등락과 실제 종가가 섞여 보이던 문제)
    const fk = (n) => { const f = fut[n]; if (!f) return ""; if (f.since_close == null) return fv(n);
      return `${esc(n)} 야간·24시간 ${f.u === "$" ? "$" : ""}${(+f.px).toLocaleString("ko-KR", { maximumFractionDigits: 2 })} ${sg2(f.since_close)} <small class="dim">${kstDay(f.close_at) === kstDay(Date.now()) ? "" : `${+kstDay(f.close_at).slice(5, 7)}/${+kstDay(f.close_at).slice(8)} `}종가 이후${f.close_ref != null ? ` · 종가 시각 ${rn(f.close_ref, f.u)}` : ""}</small>`; };
    const top3 = (gs) => (gs || []).slice(0, 3).map((g) => `${esc(g.name)} ${sg2(g.chg)} <small class="dim">상승 ${g.up}/${g.n}</small>`).join(" · ");
    const reg = window.trlReg || {}, kr = window.trlKr || {};
    const L = [];
    const lvl = () => ((watch && watch.items) || []).filter((x) => x.px != null).map((x) => {
      const e = ((lev && lev.items) || []).find((y) => y.sym === x.sym);
      const ext = e && e.ext && !e.ext.stale ? ` · ${e.ext.sess === "pre" ? "프리" : e.ext.sess === "day" ? "주간" : "애프터"} $${e.ext.px} ${sg2(e.ext.chg)}` : "";
      return `${esc(x.sym)} $${(+x.px).toFixed(2)} ${sg2(x.chg)}${x.level ? (() => { const d = (x.px / x.level - 1) * 100; return ` (운영자 가격대 $${x.level} ${Math.abs(d) < 0.15 ? "부근" : `대비 ${sg2(d)} ${d > 0 ? "위" : "아래"}`})`; })() : ""}${ext}`;
    }).join(" · ");
    if (md_ === "us") {
      const u = leaders && leaders.us;
      if (u && (u.industry || []).length) L.push(`🏁 미국 주도 업종${u.open ? "(장중)" : "(직전 장 기준)"}: ${top3(u.industry)}`);
      const f = ["나스닥100", "S&P500", "WTI", "브렌트", "달러인덱스"].map(fv).filter(Boolean);
      if (f.length) L.push(`📈 지수·유가(24시간 선물): ${f.join(" · ")}${brief && brief.us10y ? ` · 미 10년물 ${(+brief.us10y.px).toFixed(3)}%${brief.ust && brief.ust["10Y"] && brief.ust["10Y"].prev != null ? ` <small class="dim">(전일 ${(+brief.ust["10Y"].prev).toFixed(3)}%)</small>` : ""}` : ""}`);
      const hu = leaders && leaders.hourly && leaders.hourly.us && (leaders.hourly.us.slots || [])[0];
      if (hu && hu.live) L.push(`⏱ 이번 시간(${hu.h}시~) 강세: ${(hu.sectors || []).slice(0, 2).map((g) => `${esc(g.name)} ${sg2(g.slot)}`).join(" · ")} | ${(hu.stocks || []).slice(0, 3).map((r) => `${esc(r.name)} ${sg2(r.slot)}`).join(" · ")}`);
      const kc = [["KOSPI", "코스피"], ["KR200", "코스피200"]].filter(([c]) => kr[c] && !kr[c].open).map(([c, n]) => `${n} ${(+kr[c].px).toLocaleString("ko-KR", { maximumFractionDigits: 2 })} ${sg2(kr[c].chg)}`);
      if (kc.length) L.push(`🏁 한국 마지막 종가${kr.KOSPI && kr.KOSPI.at ? ` <small class="dim">(${+kstDay(kr.KOSPI.at).slice(5, 7)}/${+kstDay(kr.KOSPI.at).slice(8)} 마감)</small>` : ""}: ${kc.join(" · ")}`);
      const rf = ["코스피200 야간선물", "코스피200 주간선물"].map((n) => fut[n] ? `<b>${esc(n)}</b> ${(+fut[n].px).toLocaleString("ko-KR", { maximumFractionDigits: 2 })} ${sg2(fut[n].chg)} <small class="dim">(기준 ${esc(fut[n].base || "")}${fut[n].ref != null ? " " + rn(fut[n].ref) : ""} · NH)</small>` : "").filter(Boolean);
      const k = [...rf, ...["코스피200", "삼성전자", "SK하이닉스"].map(fk), fv("원/달러")].filter(Boolean);
      if (k.length) L.push(`🇰🇷 내일 한국장 연결: ${k.join(" · ")}`);
      const evT = (c) => new Date(`${c.date}T${c.time}:00+09:00`).getTime();
      const cs = (checks || []).filter((c) => c.time && evT(c) >= Date.now() - 30 * 60000 && evT(c) <= Date.now() + 12 * 3600e3).sort((a, b) => evT(a) - evT(b));
      if (cs.length) L.push(`🗓️ 앞으로 12시간 일정: ${cs.slice(0, 4).map((c) => `<b>${c.date !== today ? `${+c.date.slice(5, 7)}/${+c.date.slice(8)} ` : ""}${esc(c.time)}</b> ${esc(c.title)}`).join(" · ")}`);
      const ipoDates = (checks || []).filter((c) => c.kind === "ipo" && c.date >= today && c.date <= kstDay(Date.now() + 2 * 86400e3))
        .sort((a, b) => (b.priority || 0) - (a.priority || 0) || a.date.localeCompare(b.date));
      if (ipoDates.length) L.push(`🗓️ 주요 IPO: ${ipoDates.slice(0, 3).map((c) => `<b>미국 ${esc(c.market_date || c.date)}</b> ${esc(c.title)} <small class="dim">· ${esc(c.timing || "정확한 한국 시각 미정")}</small>`).join(" · ")}`);

    } else {
      const r = (k, n) => reg[k] ? `${n} ${sg2(reg[k].chg)}` : "";
      const us_ = [r("SP500", "S&P500"), r("XYZ100", "나스닥100"), r("SOXL", "SOXL"), r("KORU", "KORU"), r("EWY", "EWY")].filter(Boolean);
      if (us_.length) L.push(`🌙 간밤 미국 정규장: ${us_.join(" · ")}`);
      const ki = [["KOSPI", "코스피"], ["KOSDAQ", "코스닥"], ["KR200", "코스피200"]].filter(([k]) => kr[k]).map(([k, n]) => `${n} ${(+kr[k].px).toLocaleString("ko-KR", { maximumFractionDigits: 2 })} ${sg2(kr[k].chg)}`);
      if (now.getHours() < 9 && fut["코스피200"]) L.push(`⏰ 개장 전: ${fk("코스피200")}`);
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
    return `<div class="ses"><p class="spot-h">${md_ === "kr" ? "🇰🇷 오늘 한국장 관전 포인트" : "🇺🇸 오늘 밤 미국장 관전 포인트"} <small>${hm(Date.now())} KST</small></p>
      <ul class="ses-l">${L.map((t) => `<li>${t}</li>`).join("")}</ul></div>`;
  }
  function oilWatchHtml() {
    const oil = (brief && brief.futures || []).find((x) => x.name === "WTI");
    if (!oil || !Number.isFinite(oil.px) || oil.px <= 0) return "";
    const level = 85;
    const distance = (oil.px / level - 1) * 100;
    const side = distance > 0 ? "위" : distance < 0 ? "아래" : "부근";
    const stale = !brief.at || Date.now() - brief.at > 5 * 60000;
    const context = sessionQuotes && sessionQuotes.oil && Date.now() <= Date.parse(sessionQuotes.until) ? sessionQuotes.oil : null;
    const flow = context && Number.isFinite(context.reference) ? `<p><b>${esc(context.label)} → 현재 $${oil.px.toFixed(2)}</b> · ${oil.px < level ? "85달러 아래 흐름" : oil.px === level ? "85달러 부근 흐름" : "85달러 위 흐름"}</p><p class="fine">${esc(context.memo)} 주말 전 참고값과 현재 시세는 출처·거래 시점이 다릅니다.</p>` : "";
    return `<div class="ses"><p class="spot-h">🛢 WTI 유가 흐름 <small>${brief.at ? hm(brief.at) + " 기준" : "시각 미확인"}${stale ? " · 시세 지연" : ""} · 하이퍼리퀴드</small></p>
      ${flow}
      <p>WTI <b>$${oil.px.toFixed(2)}</b> · <b>${oil.px < level ? "85달러 아래 — 중요 변곡점 확인" : "85달러 " + side}</b></p>
      <p class="fine">85달러 하향 이탈을 중요 변곡점으로 감지 · 이탈 시각 전후 관련 뉴스와 주요 지수 반응은 아래 변곡점 카드에서 확인</p></div>`;
  }

  function drawWatch() {
    const box = q("#watchBox"); if (!box) return;
    const wh = watchHtml(watch);
    const h = sessionQuotesHtml() + oilWatchHtml() + sessionHtml() + wh;
    box.hidden = !h; box.innerHTML = h;
  }

  /* ── ↕ 표 정렬(등락률·거래대금·시가총액·수급 …): 머리글이나 정렬 버튼을 누르면 순서가 바뀐다. 같은 걸 다시 누르면 반대로 ── */
  const sortSt = { flow: { k: "chg", d: -1 }, s7: { k: null, d: -1 }, sec: { k: "chg", d: -1 }, ld: { k: "score", d: -1 }, ldm: { k: "val", d: -1 }, hr: { k: "slot", d: -1 } };
  const SORTK = {
    name: (r) => r.name, chg: (r) => r.chg, val: (r) => r.val, mcap: (r) => r.mcap, pts: (r) => r.pts, w: (r) => r.w,
    win: (r) => r.win ? r.win.amt : null, frgn: (r) => r.est && r.est.frgn != null ? r.est.frgn : r.est_kw && r.est_kw.frgn != null ? r.est_kw.frgn : r.inv ? r.inv.frgn : null,
    org: (r) => r.est && r.est.org != null ? r.est.org : r.est_kw && r.est_kw.org != null ? r.est_kw.org : r.inv ? r.inv.org : null,
    s5: (r) => r.inv ? (r.inv.frgn3 ?? r.inv.frgn5 ?? 0) + (r.inv.org3 ?? r.inv.org5 ?? 0) : null, score: (r) => r.score, breadth: (r) => r.breadth, slot: (r) => r.slot, prog: (r) => r.prog ? r.prog.amt : null, prog5: (r) => r.prog ? r.prog.amt5 : null,
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
  // 운영자 11/16: 장중엔 외국인(09:20~)·기관(09:50~) 추정 가집계를 먼저, 없으면 직전 확정치. 프로그램은 KRX·넥스트레이드(08시 프리마켓) 나눠 표시
  const sgE = (v) => v == null ? "-" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${eok(Math.abs(v))}`;
  // 운영자 11/17: 키움 장중 집계(est_kw)를 두 번째 증권사로 나란히 — 한투 추정이 없으면 키움 값을 본 값으로
  const kwSub = (r, k) => r.est_kw && r.est_kw[k] != null ? `<small class="fl-k">키움 ${sgE(r.est_kw[k])}</small>` : "";
  const invCell = (r, k) => r.est ? (r.est[k] == null ? `<span class="dim">-</span><small class="fl-k">${k === "org" ? "기관 09:50~" : "집계 전"}</small>${kwSub(r, k)}`
    : `${eokS(r.est[k])}<small class="fl-k">한투 추정 ${esc(r.est.round || "")}</small>${kwSub(r, k)}`)
    : r.est_kw && r.est_kw[k] != null ? `${eokS(r.est_kw[k])}<small class="fl-k">키움 장중 ${esc(r.est_kw.hm || "")}</small>` : r.inv ? eokS(r.inv[k]) : "-";
  const progCell = (r) => !r.prog ? '<span class="dim">-</span>' : `${eokS(r.prog.amt)}${r.prog.nxt != null && r.prog.krx != null ? `<small class="fl-k">KRX ${sgE(r.prog.krx)} · NXT ${sgE(r.prog.nxt)}</small>` : r.prog.nxt != null ? '<small class="fl-k">NXT 프리마켓</small>' : ""}`;
  const invSub = (rows, dd) => { const e = (rows.find((r) => r.est) || {}).est; return e ? `오늘 추정 ${e.round || ""}` : dd; };
  function flowTable(g, n, compact) {
    const rows = compact ? [...g.rows].sort((a, b) => (b.val || 0) - (a.val || 0)).slice(0, n) : sortRows(g.rows, "flow").slice(0, n);
    const invDay = (rows.find((r) => r.inv) || {}).inv;
    const dd = invDay ? md(invDay.day) : "";
    const head = compact ? "<tr><th>종목</th><th>등락</th><th>거래대금</th></tr>"
      : `<tr>${sth("flow", "name", "종목")}${sth("flow", "chg", "등락")}${sth("flow", "val", "거래대금", "통합")}${sth("flow", "mcap", "시가총액")}${sth("flow", "win", "외국계 창구", "오늘")}${sth("flow", "frgn", "외국인", invSub(rows, dd))}${sth("flow", "org", "기관", invSub(rows, dd))}${sth("flow", "s5", "외국인·기관", "3일 합계")}${sth("flow", "prog", "프로그램", "오늘 통합")}${sth("flow", "prog5", "프로그램", "5일 합계")}</tr>`;
    const body = rows.map((r) => `<tr><td class="fl-n">${esc(r.name)}</td><td>${pct(r.chg)}</td><td>${r.val ? eok(r.val) : "-"}${!compact && r.val_krx && r.val - r.val_krx > 1e8 ? `<small class="fl-k">KRX ${eok(r.val_krx)}</small>` : ""}</td>${compact ? "" : `
      <td>${mcapS(r.mcap)}</td><td>${r.win ? eokS(r.win.amt) : "-"}</td><td>${invCell(r, "frgn")}</td><td>${invCell(r, "org")}</td>
      <td class="fl-5">${r.inv ? `${eokS(r.inv.frgn3 ?? r.inv.frgn5)} / ${eokS(r.inv.org3 ?? r.inv.org5)}` : "-"}</td><td>${progCell(r)}</td><td>${r.prog ? eokS(r.prog.amt5) : '<span class="dim">-</span>'}</td>`}</tr>`).join("");
    return `<div class="fl-g"><p class="fl-gh">${g.icon || ""} ${esc(g.name)}${g.n ? ` <small>상승 ${g.up}/${g.n}종목</small>` : ""}</p>
      <div class="fl-scroll"><table class="fl-t">${head}${body}</table></div></div>`;
  }
  /* ── 🏛️ S7: 코스피 영향 큰 삼성·SK 7종목 — 지수 기여 포인트, S7 제외 코스피, 수급 ── */
  let s7 = null;
  function normalizeS7(j) {
    const raw = j.s7, live = (j.kr || {}).KOSPI, base = raw && raw.kospi;
    if (!raw || !live || !base || Math.abs(live.chg || 0) < 0.5 || Math.sign(base.chg || 0) === Math.sign(live.chg || 0)) return raw;
    const copy = JSON.parse(JSON.stringify(raw)), quotes = new Map();
    for (const g of ((j.flows || {}).groups || [])) for (const r of (g.rows || [])) if (r.code) quotes.set(String(r.code), r);
    const kr = j.kr || {};
    if (kr.SMSN) quotes.set("005930", kr.SMSN);
    if (kr.SKHX) quotes.set("000660", kr.SKHX);
    let verified = 0;
    for (const r of copy.rows || []) {
      const q = quotes.get(String(r.code));
      r.indexUnverified = !q;
      r.pts = null; r.w = null;
      if (q && Number.isFinite(+q.px) && Number.isFinite(+q.chg)) {
        r.px = +q.px; r.chg = +q.chg;
        if (q.val != null) r.val = q.val;
        verified++;
      } else { r.px = null; r.chg = null; r.val = null; }
    }
    copy.kospi = { ...copy.kospi, px: live.px, prev: live.prev, pts: live.px - live.prev, chg: live.chg, up: null, dn: null };
    copy.s7 = { pts: null, w: null, share: null, ex_pts: null, ex_chg: null };
    copy.reconcile = { verified, total: (copy.rows || []).length };
    return copy;
  }
  /* ── 📐 추세 판단(운영자 11/17): 하락 채널 상단 돌파(+1%·5일선 위)가 진짜 반등 · 실시간 캔들 · 기록 ── */
  let chanOpen = null;
  const CH_ST = {"돌파 확인": "ok", "돌파 시도(장중)": "try", "돌파 관찰·상단 근접": "near", "채널 위·5일선 아래": "warn", "채널 돌파·전고점 아래": "warn", "상단 근접": "near", "채널 안": "in", "하단 이탈": "bad"};
  const CH_FLAG = {kr: "🇰🇷", kr_index: "🇰🇷", us: "🇺🇸", jp: "🇯🇵", tw: "🇹🇼", cn: "🇨🇳"};
  const chartPriceFormat = {
    kr_index: new Intl.NumberFormat(marketLocale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    us: new Intl.NumberFormat(marketLocale, { style: "currency", currency: "USD" }),
    kr: new Intl.NumberFormat(marketLocale, { style: "currency", currency: "KRW" }),
    jp: new Intl.NumberFormat(marketLocale, { style: "currency", currency: "JPY" }),
    tw: new Intl.NumberFormat(marketLocale, { style: "currency", currency: "TWD" }),
  };
  const chFmt = (cc, value) => value == null ? "-"
    : (chartPriceFormat[cc] || chartPriceFormat.kr).format(value) + (cc === "kr_index" ? " pt" : "");
  function chGlyph(r) {                                       // 오늘 봉(시가·고가·저가·현재가) 작은 그림
    const [, o, h, l, c] = r, rng = (h - l) || 1, Y = (v) => 3 + (h - v) / rng * 26, col = c >= o ? "var(--market-up)" : "var(--market-down)";
    return `<svg class="ch-gl" viewBox="0 0 14 32" aria-hidden="true"><line x1="7" x2="7" y1="${Y(h)}" y2="${Y(l)}" stroke="${col}" stroke-width="1.4"/><rect x="2.5" y="${Y(Math.max(o, c))}" width="9" height="${Math.max(1.5, Math.abs(Y(o) - Y(c)))}" fill="${col}" rx="1"/></svg>`;
  }
  // 📏 수평선(운영자 11/19 "수평 및 채널 추세선에서 움직이는 걸 숫자로"): 좌우 3봉보다 높은 고점·낮은 저점(스윙) 중
  // 현재가 바로 위 고점 = 수평 저항, 바로 아래 저점 = 수평 지지. 
  function chLevels(rows, px) {
    const n = rows.length, k = 3, from = Math.max(0, n - 80), ph = [], pl = [];
    for (let i = from + k; i < n - 2; i++) {
      let isH = true, isL = true;
      for (let j = i - k; j <= Math.min(n - 1, i + k); j++) { if (j === i) continue; if (rows[j][2] > rows[i][2]) isH = false; if (rows[j][3] < rows[i][3]) isL = false; }
      if (isH) ph.push(i); if (isL) pl.push(i);
    }
    const touch = (v, col) => rows.slice(from).filter((r) => Math.abs(r[col] / v - 1) <= 0.01).length;
    const pick = (idx, col, above) => { let best = null;
      idx.forEach((i) => { const v = rows[i][col]; if (above ? v > px : v < px) if (!best || (above ? v < best.v : v > best.v)) best = {i, v}; });
      return best && {...best, n: touch(best.v, col)}; };
    return {res: pick(ph, 2, true), sup: pick(pl, 3, false), top: Math.max(...rows.slice(from).map((r) => r[2]))};
  }
  const CH_HIDE = new Set(["YM=F"]);
  // 11/20 운영자 "이제 대장이 ANT와 엔비디아": 상장 초기 종목의 5분봉 종가 흐름
  function chIpoCard(it, cc) {
    const bars = (it.bars || []).filter((row) => row.length >= 5 && row[0] % 300000 === 0 && row.slice(0, 5).every(Number.isFinite));
    const sessions = { pre: "프리마켓", reg: "정규장", post: "애프터마켓" };
    let graph = '<p class="fine">5분봉 시세 대기</p>';
    const refs = [["공모가", it.ipo_px], [`첫 시가${it.open1_day ? " " + it.open1_day.slice(5).replace("-", "/") : ""}`, it.open1], ["상장 뒤 고점", it.hi]].filter(([, v]) => Number.isFinite(v) && v > 0);
    if (bars.length) {
      const W = 640, H = 180, left = 8, right = 62, top = 12, bottom = 24;
      const lo = Math.min(...bars.map((row) => row[3]));
      const hi = Math.max(...bars.map((row) => row[2]));
      const pad = (hi - lo) * 0.08 || 1;
      const step = (W - left - right) / bars.length;
      const x = (i) => left + step * (i + 0.5);
      const y = (v) => top + (hi + pad - v) / (hi - lo + 2 * pad) * (H - top - bottom);
      const axis = [...new Set([lo, hi])].map((v) => `<line class="ch-grid" x1="${left}" x2="${W - right}" y1="${y(v)}" y2="${y(v)}"/><text class="ch-ax" x="${W - right + 4}" y="${y(v) + 4}">${chFmt(cc, v)}</text>`).join("");
      const label = (t) => `${kstDay(t).slice(5)} ${hm(t)}`;
      const candles = bars.map(([, o, h, l, c, session, source], i) => {
        const color = c >= o ? "var(--market-up)" : "var(--market-down)";
        const shade = session === "pre" || session === "post"
          ? `<rect x="${left + i * step}" y="${top}" width="${step}" height="${H - top - bottom}" fill="var(--gold)" opacity=".17"/>`
          : "";
        const width = Math.min(12, step * 0.65);
        return `${shade}<g><title>${label(bars[i][0])} · ${sessions[session] || sessions.reg} · 종가 ${chFmt(cc, c)} · ${esc(source || "Yahoo Finance")}</title><line x1="${x(i)}" x2="${x(i)}" y1="${y(h)}" y2="${y(l)}" stroke="${color}"/><rect x="${x(i) - width / 2}" y="${y(Math.max(o, c))}" width="${width}" height="${Math.max(1, Math.abs(y(o) - y(c)))}" fill="${color}"/></g>`;
      }).join("");
      graph = `<svg class="ch-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(it.name)} 정규장·시간외 5분봉">
        ${axis}${candles}<text class="ch-ax" x="${left}" y="${H - 5}">${label(bars[0][0])}</text>
        ${refs.filter(([, v]) => v >= lo - pad && v <= hi + pad).map(([name, v]) => `<line x1="${left}" x2="${W - right}" y1="${y(v)}" y2="${y(v)}" stroke="var(--gold)" stroke-dasharray="4 3"/><text class="ch-ax" x="${left + 2}" y="${y(v) - 3}">${name} ${chFmt(cc, v)}</text>`).join("")}
        <text class="ch-ax" x="${W - right}" y="${H - 5}" text-anchor="end">${label(bars.at(-1)[0])}</text></svg>`;
    }
    // 11/28 운영자 "지난 번처럼": 11/20 첫 카드의 기준선 3개(공모가·첫 시가·상장 뒤 고점) — 차트 범위 밖이면 글로만
    const px = Number.isFinite(it.px) ? it.px : bars.at(-1)?.[4];
    const refLine = refs.length && px > 0 ? `<p class="ch-lv">${refs.map(([name, v]) => `<span>${name} <b>${chFmt(cc, v)}</b> <small>${px >= v ? "+" : "−"}${Math.abs((px / v - 1) * 100).toFixed(1)}%</small></span>`).join("")}</p>` : "";
    const last = bars.at(-1);
    let summary = "";
    if (last) {
      const session = last[5] || "reg";
      const et = new Intl.DateTimeFormat("en-CA", {
        timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
      });
      const day = et.format(last[0]);
      const reference = bars.slice(0, -1).findLast((bar) => (bar[5] || "reg") === "reg"
        && (session === "post" ? et.format(bar[0]) === day : et.format(bar[0]) !== day));
      const ipoDay = new Date(bars[0][0]).toLocaleDateString("sv-SE", { timeZone: "America/New_York" });
      const useIpo = session === "reg" && !reference && ipoDay === it.listed;
      const base = reference?.[4] ?? (useIpo ? it.ipo_px : null);
      const delta = base > 0 ? last[4] - base : null;
      const signed = (value) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(2)}`;
      const tick = delta == null ? "등락 기준가 확인 중"
        : `<b class="${cls(delta)}">${signed(delta)}달러 (${signed(delta / base * 100)}%)</b> <small>${useIpo ? "공모가" : session === "post" ? "당일 정규장 마지막 5분봉 종가" : "직전 정규장 마지막 5분봉 종가"} ${chFmt(cc, base)} 대비</small>`;
      summary = `<p class="ch-lv"><span>${sessions[session] || sessions.reg} <strong class="${delta == null ? "c-fl" : cls(delta)}">${chFmt(cc, last[4])}</strong></span><span>${tick}</span></p>`;
    }
    return `<article class="ch-card ch-ipo" data-viewport-key="channel:${esc(it.code)}">
      <div class="ch-top"><b class="ch-nm">${esc(it.name)} <small>${esc(it.code)}</small></b><small class="ch-session">5분봉 · 한국시간 · 시간외는 음영</small></div>${summary}${refLine}${graph}
      ${last ? `<p class="fine">마지막 봉 · ${sessions[last[5]] || "정규장"} · ${kstDay(last[0]).slice(5)} ${hm(last[0])} · ${chFmt(cc, last[4])} · ${esc(last[6] || "Yahoo Finance")}</p>` : ""}</article>`;
  }
  // 11/20 운영자 "지지·저항·추세선·5일선 명확히": 카드에 현재가 바로 위 저항·바로 아래 지지, 오늘 고가가 닿고 밀린 선·저가가 받친 선
  function chHorizontalLower(rows) {
    // 최근 완료 일봉에서 최소 세 거래일 떨어진 두 스윙 저점을 찾는다.
    const last = rows.length - 2;
    const pivots = [];
    for (let i = Math.max(1, last - 24); i < last; i++) {
      const low = rows[i][3];
      if (low > 0 && low < rows[i - 1][3] && low <= rows[i + 1][3]) pivots.push(i);
    }
    for (let right = pivots.length - 1; right > 0; right--) {
      const second = pivots[right];
      for (let left = right - 1; left >= 0; left--) {
        const first = pivots[left];
        if (second - first < 3) continue;
        const a = rows[first][3], b = rows[second][3], value = (a + b) / 2;
        if (Math.abs(a - b) / (2 * value) > 0.0075) continue;
        return { first, second, value, floor: Math.min(a, b), ceiling: Math.max(a, b) };
      }
    }
    return null;
  }

  function chLvLine(it, cc, horizontal) {
    const rows = it.rows || [], n = rows.length, px = it.px;
    if (!n || !(px > 0)) return "";
    const L = chLevels(rows, px), okCh = it.channel_valid !== false && it.channel_width_valid !== false;
    const lv = [["5일선", it.ma5], okCh && ["채널 상단", it.up_now], okCh && ["채널 하단", it.lo_now], L.res && ["수평 저항", L.res.v], L.sup && ["수평 지지", L.sup.v],
      (() => { const v = Math.max(...rows.slice(-20).map((r) => r[2])); return v > px && !(L.res && L.res.v <= v) && ["최근 고점", v]; })()]   // 11/21 돌파 뒤 새 저항(차트의 '돌파 뒤 고점'과 같은 값)
      .filter((x) => x && x[1] > 0);
    const horizontalLabel = horizontal ? `<span>수평 하단 <b>${chFmt(cc, horizontal.floor)}–${chFmt(cc, horizontal.ceiling)}</b> <small>${rows[horizontal.first][0]} · ${rows[horizontal.second][0]} 저점 · ${px < horizontal.floor ? "하단 이탈" : px > horizontal.ceiling ? "하단 위" : "구간 안"}</small></span>` : "";
    const [, , h, l] = rows[n - 1];
    const up = lv.filter((x) => x[1] > px).sort((a, b) => a[1] - b[1])[0], dn = lv.filter((x) => x[1] <= px).sort((a, b) => b[1] - a[1])[0];
    const g = (x) => `<b>${x[0]} ${chFmt(cc, x[1])}</b> <small>${(x[1] / px - 1) * 100 > 0 ? "+" : ""}${((x[1] / px - 1) * 100).toFixed(1)}%</small>`;
    return `<p class="ch-lv"><span>⬆ 위 저항 ${up ? g(up) : "<b>없음(최근 고점 위)</b>"}</span><span>⬇ 아래 지지 ${dn ? g(dn) : "<b>없음</b>"}</span>${horizontalLabel}</p>`;
  }
  // 11/20 운영자 "통합 종가로 하자 · KRX 종가도 따로 표시해 체크(종가가 지금은 기준가)": 5일선 = 통합(KRX+넥장 20시), 등락률 기준가 = KRX 종가
  // 11/21 운영자 "각 종목들 종가와 시간외 현재 시각 금액을 별도로 표시": 정규장 종가 줄 + 시간외(프리·애프터·넥장) 현재가·시각·종가 대비 따로
  function chCloseExt(regular, it, cc) {
    // 11/21 운영자 "주가 구분 표시도 가시성 좋게": 칸을 나눠 이름표·큰 숫자·대비를 따로(정규장 종가 = 회색 칸, 시간외 = 보라 칸, 정규장 진행 = 초록 칸)
    if (cc !== "kr" && cc !== "us") return "";
    const sgn = (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}%`;
    const kc = (v) => v > 0.005 ? "up" : v < -0.005 ? "down" : "dim";
    const when = (ms) => { if (!(ms > 0)) return ""; const d = kstDay(ms), t = kstDay(Date.now()); return (d === t ? "" : d.slice(5).replace("-", "/") + " ") + hm(ms); };
    const cell = (k, label, val, sub) => `<div class="cx ${k}"><span class="cx-l">${label}</span><b class="cx-v">${val}</b>${sub ? `<span class="cx-s">${sub}</span>` : ""}</div>`;
    const ext = (label, px, ms, base, vs) => px > 0 && base > 0
      ? cell("cx-ext", label, `<span class="cx-quote"><span class="${kc(px / base - 1)}">${chFmt(cc, px)}</span><span class="cx-pct ${kc(px / base - 1)}">${sgn((px / base - 1) * 100)}</span></span>`, `${vs} · ⏱ ${when(ms)}`) : "";
    const none = (label, why) => cell("cx-off", label, "—", why);
    if (cc === "kr") {
      const kx = regular.krx_close > 0 ? regular.krx_close : null;
      if (!kx) return "";
      const nx = regular.nxt || {}, hmK = (() => { const d = kst(Date.now()); return d.getHours() * 100 + d.getMinutes(); })();
      const krxOpen = regular.live && hmK >= 900 && hmK < 1530;
      const cells = [cell("cx-cls", "KRX 종가 · 기준가", chFmt(cc, kx), esc(regular.krx_close_day || ""))];
      if (regular.uni_close > 0) cells.push(cell("cx-cls", "통합 종가 · 넥장 20시", chFmt(cc, regular.uni_close), esc(regular.uni_close_day || "")));
      const nxtInHeader = regular.display && it.live && !it.stale && /^NXT (프리|애프터)$/.test(it.session);
      if (!krxOpen && !nxtInHeader) cells.push(nx.px > 0 && nx.last_only ? cell("cx-ext", nx.venue === "KRX" ? "KRX 시간외 마지막 체결" : "NXT 마지막 체결", chFmt(cc, nx.px), when(nx.at) + " KST")
        : nx.px > 0 ? ext(nx.venue === "KRX" ? "KRX 시간외" : `넥장 ${nx.session === "프리" ? "프리마켓" : "애프터마켓"}`, nx.px, nx.at, kx, "KRX 종가 대비") : none("넥장 시간외", "시세 없음"));
      const m5 = it.ma5 > 0 ? `<p class="cx-ma">5일선 통합 <b>${chFmt(cc, it.ma5)}</b>${regular.ma5_krx > 0 ? ` · KRX <b>${chFmt(cc, regular.ma5_krx)}</b>` : ""}</p>` : "";
      const basis = regular.uni_sma5_closed > 0
        ? `<p class="cx-ma">${esc(regular.uni_close_day || "")} 통합 확정 5일선 <b>${chFmt(cc, regular.uni_sma5_closed)}</b>${regular.uni_below_sma5 === true ? " · 통합 종가 5일선 아래" : ""}</p>`
        : '<p class="cx-ma">통합 5일선 확인 중</p>';
      return `<div class="cx-row">${cells.join("")}</div>${m5}${basis}`;
    }
    // U.S. cards already show the session price and change in the header.
    // Keep the comparison price visible on touch screens when it is distinct.
    if (!(it.base > 0) || it.base === it.px) return "";
    const basis = it.change_basis || "전일 정규장 종가";
    return `<p class="cx-ma">${esc(basis)} <b>${chFmt(cc, it.base)}</b></p>`;
  }
  function chChart(it, cc, sg, horizontal) {
    const fullRows = it.rows || [];
    const offset = Math.max(0, fullRows.length - 28); // 약 40일, 28거래일
    if (offset) {
      const shift = (values) => (values || []).filter((i) => i >= offset).map((i) => i - offset);
      const oldLowerPath = it.lower_path || [];
      let lowerPath = oldLowerPath
        .filter((point) => point[0] >= offset)
        .map((point) => [point[0] - offset, point[1]]);
      if (oldLowerPath.length === 3 && oldLowerPath[1][0] < offset && oldLowerPath[2][0] >= offset) {
        const [[a, av], [b, bv], end] = oldLowerPath;
        const atOffset = av + (bv - av) * (offset - a) / (b - a);
        lowerPath = [[0, atOffset], [end[0] - offset, end[1]]];
      }
      it = {
        ...it,
        rows: fullRows.slice(offset),
        hi: shift(it.hi),
        lo: shift(it.lo),
        upper_start: Math.max(0, (it.upper_start ?? it.hi?.[0] ?? offset) - offset),
        lower_start: Math.max(0, (it.lower_start ?? it.lo?.[0] ?? offset) - offset),
        lower_path: lowerPath
      };
    }

    if (offset && horizontal) {
      horizontal = {
        ...horizontal,
        first: Math.max(0, horizontal.first - offset),
        second: Math.max(0, horizontal.second - offset)
      };
    }
    const rows = it.rows, n = rows.length, N = n + 1, W = 640, H = 230, M = {l: 6, r: 74, t: 10, b: 20};
    const up = (i) => it.up_now + it.su * (i - (n - 1)), lo = (i) => {
      const path = it.lower_path;
      if (path?.length === 3 && i <= path[1][0]) {
        const [[a, av], [b, bv]] = path;
        return av + (bv - av) * (i - a) / (b - a);
      }
      return it.lo_now + it.sl * (i - (n - 1));
    };
    let ymax = Math.max(...rows.map((r) => r[2])), ymin = Math.min(...rows.map((r) => r[3]));
    ymin = Math.max(Math.min(ymin, lo(n)), ymin * 0.85);
    const pad = (ymax - ymin) * 0.05; ymax += pad; ymin -= pad;
    const pw = W - M.l - M.r, ph = H - M.t - M.b, st = pw / N, X = (i) => M.l + st * (i + 0.5), Y = (v) => M.t + (ymax - v) / (ymax - ymin) * ph;
    const cid = "cc" + it.code.replace(/\W/g, "");
    let s = `<defs><clipPath id="${cid}"><rect x="${M.l}" y="${M.t}" width="${pw}" height="${ph}"/></clipPath></defs>`;
    for (let k = 0; k <= 3; k++) { const v = ymin + (ymax - ymin) * k / 3;
      s += `<line x1="${M.l}" x2="${W - M.r}" y1="${Y(v)}" y2="${Y(v)}" class="ch-grid"/><text x="${W - M.r + 5}" y="${Y(v) + 3}" class="ch-ax">${chFmt(cc, v)}</text>`; }
    for (let i = 0; i < n - 4; i += 10) s += `<text x="${X(i)}" y="${H - 5}" class="ch-ax" text-anchor="middle">${rows[i][0]}</text>`;
    s += `<text x="${X(n - 1)}" y="${H - 5}" class="ch-ax" text-anchor="middle">${rows[n - 1][0]}</text><g clip-path="url(#${cid})">`;
    const upperStart = it.upper_start ?? it.hi[0], lowerStart = it.lower_start ?? it.lo[0];
    const a0 = Math.max(upperStart, lowerStart);
    // 11/21 운영자 "상단 저항 채널 돌파했는데도 선이 그대로": 종가가 상단 +1% 위로 마감한 첫 봉(bk)부터는
    // 상단선을 '돌파한 상단 → 지지'(회색 점선)로 바꾸고, 새 저항은 돌파 뒤 최고가 수평선으로 그린다
    const clB = chCl(it), hiLast = Math.max(...(it.hi || [upperStart]));
    let bk = null;
    if (it.channel_valid !== false) for (let i = hiLast + 1; i < n; i++) {
      const c = i === n - 1 && it.live ? it.px : clB[i];   // 마감 봉은 정규장 종가로 판단
      if (c > up(i) * 1.01) { bk = i; break; }
    }
    const upEnd = bk == null ? n : bk;
    if (it.channel_valid !== false) {
      const bottom = [a0, ...(it.lower_path || []).map(p => p[0]).filter(i => i > a0 && i < n), n].reverse();
      s += `<polygon class="ch-band" points="${X(a0)},${Y(up(a0))} ${X(n)},${Y(up(n))} ${bottom.map(i => `${X(i)},${Y(lo(i))}`).join(" ")}"/>`;
      if (bk != null) s += `<polygon class="ch-band-old" points="${X(bk)},${Y(up(bk))} ${X(n)},${Y(up(n))} ${X(n)},${Y(lo(n))} ${X(bk)},${Y(lo(bk))}"/>`;
    }
    const cw = Math.max(2, st * 0.6);
    rows.forEach((r, i) => { const [, o, h, l, c] = r, col = c >= o ? "var(--market-up)" : "var(--market-down)";
      s += `<line x1="${X(i)}" x2="${X(i)}" y1="${Y(h)}" y2="${Y(l)}" stroke="${col}"/><rect x="${X(i) - cw / 2}" y="${Y(Math.max(o, c))}" width="${cw}" height="${Math.max(1, Math.abs(Y(o) - Y(c)))}" fill="${col}" rx="1"${i === n - 1 && it.live ? ' class="ch-live"' : ""}/>`; });
    const cl5 = chCl(it), ma = rows.map((_, i) => i >= 4 ? cl5.slice(i - 4, i + 1).reduce((a, b) => a + b, 0) / 5 : null);   // 5일선 = 정규장 종가 기준
    s += `<polyline class="ch-ma" points="${ma.map((v, i) => v == null ? "" : `${X(i)},${Y(v)}`).join(" ").trim()}"/>`;
    if (bk == null) s += `<line x1="${X(upperStart)}" y1="${Y(up(upperStart))}" x2="${X(n - 1)}" y2="${Y(up(n - 1))}" class="ch-res${it.upper_verified === false ? " ch-unverified" : ""}"/><line x1="${X(n - 1)}" y1="${Y(up(n - 1))}" x2="${X(n)}" y2="${Y(up(n))}" class="ch-res ch-dash${it.upper_verified === false ? " ch-unverified" : ""}"/>`;
    else {
      s += `<line x1="${X(upperStart)}" y1="${Y(up(upperStart))}" x2="${X(bk)}" y2="${Y(up(bk))}" class="ch-res${it.upper_verified === false ? " ch-unverified" : ""}"/>`
        + `<line x1="${X(bk)}" y1="${Y(up(bk))}" x2="${X(n)}" y2="${Y(up(n))}" class="ch-res-old"><title>돌파한 상단 → 지지 ${chFmt(cc, up(n - 1))}</title></line>`;
    }
    const supportPoints = [lowerStart, ...(it.lower_path || []).map(p => p[0]).filter(i => i > lowerStart && i < n - 1), n - 1];
    s += `<polyline points="${supportPoints.map(i => `${X(i)},${Y(lo(i))}`).join(" ")}" fill="none" class="ch-sup${it.lower_verified === false ? " ch-unverified" : ""}"/><line x1="${X(n - 1)}" y1="${Y(lo(n - 1))}" x2="${X(n)}" y2="${Y(lo(n))}" class="ch-sup ch-dash${it.lower_verified === false ? " ch-unverified" : ""}"/></g>`;
    it.hi.forEach((i) => s += `<circle cx="${X(i)}" cy="${Y(rows[i][2])}" r="3.5" class="ch-dot-r"/>`);
    it.lo.forEach((i) => s += `<circle cx="${X(i)}" cy="${Y(rows[i][3])}" r="3.5" class="ch-dot-s"/>`);
    const L = chLevels(rows, it.px), okCh = it.channel_valid !== false && it.channel_width_valid !== false;
    const inY = (v) => v != null && v <= ymax && v >= ymin;
    let nh = null;
    if (bk != null) { for (let i = bk; i < n; i++) if (!nh || rows[i][2] > nh.v) nh = {i, v: rows[i][2]}; if (nh && !(nh.v > it.px)) nh = null; }
    if (nh && inY(nh.v)) s += `<line x1="${X(nh.i)}" x2="${W - M.r}" y1="${Y(nh.v)}" y2="${Y(nh.v)}" class="ch-res-new"><title>돌파 뒤 고점(새 저항) ${chFmt(cc, nh.v)}</title></line>`;
    [[L.res, "ch-hr"], [L.sup, "ch-hs"]].forEach(([lv, k]) => { if (lv && inY(lv.v)) s += `<line x1="${X(lv.i)}" x2="${W - M.r}" y1="${Y(lv.v)}" y2="${Y(lv.v)}" class="${k}"/>`; });
    if (horizontal && inY(horizontal.value)) {
      s += `<line x1="${X(horizontal.first)}" x2="${W - M.r}" y1="${Y(horizontal.value)}" y2="${Y(horizontal.value)}" stroke="#d6a348" stroke-width="2" stroke-dasharray="5 3"><title>수평 하단 기준 ${chFmt(cc, horizontal.value)}</title></line>`;
      for (const i of [horizontal.first, horizontal.second]) s += `<circle cx="${X(i)}" cy="${Y(rows[i][3])}" r="3" fill="#d6a348"/>`;
    }
    if (inY(it.px)) s += `<line x1="${M.l}" x2="${W - M.r}" y1="${Y(it.px)}" y2="${Y(it.px)}" class="ch-pxl"/>`;
    // 오른쪽 가격표: 값이 그대로 보이게(겹치면 위아래로 벌림)
    const tags = [[it.px, "t-px"], okCh && [it.up_now, bk != null ? "t-old" : "t-res"], nh && [nh.v, "t-res"], okCh && [it.lo_now, "t-sup"], L.res && [L.res.v, "t-hr"], L.sup && [L.sup.v, "t-hs"]]
      .filter((t) => t && inY(t[0])).map(([v, k]) => ({v, k, y: Y(v)})).sort((a, b) => a.y - b.y);
    for (let i = 1; i < tags.length; i++) if (tags[i].y - tags[i - 1].y < 15) tags[i].y = tags[i - 1].y + 15;
    for (let i = tags.length - 1; i >= 0; i--) { const lim = i === tags.length - 1 ? H - M.b + 6 : tags[i + 1].y - 15; if (tags[i].y > lim) tags[i].y = lim; }
    s = s.replace(/<text x="([^"]+)" y="([^"]+)" class="ch-ax">[^<]*<\/text>/g, (m, x, y) => +x !== W - M.r + 5 ? m : tags.some((t) => Math.abs(t.y - (+y - 3)) < 12) ? "" : m);
    tags.forEach((t) => s += `<g class="ch-tag ${t.k}"><rect x="${W - M.r + 2}" y="${t.y - 7}" width="${M.r - 3}" height="14" rx="3"/><text x="${W - M.r + 5}" y="${t.y + 4}">${chFmt(cc, t.v)}</text></g>`);
    if (sg && n) {                                            // 11/19 운영자: 오늘 봉에 돌파(빨강 ▲)·저항/하락(파랑 ▼) 표시
      const lr = rows[n - 1], x = X(n - 1), up = sg.tone !== "dn";
      const y = up ? Math.min(H - M.b - 2, Y(lr[3]) + 14) : Math.max(M.t + 12, Y(lr[2]) - 6);
      s += `<g class="ch-mk ${sg.tone}"><text x="${x}" y="${y}" text-anchor="middle">${({up: "▲", dn: "▼", wk: "△"})[sg.tone]}</text></g>`;
    }
    return `<svg class="ch-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(it.name)} 일봉·하락 채널·5일선">${s}</svg>
      <p class="ch-leg">${bk != null ? `<i class="lo"></i>돌파한 상단(지지) <i class="lr"></i>돌파 뒤 고점(저항)` : `<i class="lr"></i>채널 상단`} <i class="ls"></i>채널 하단 <i class="lh"></i>수평 저항·지지 <i class="lp"></i>현재가 <i class="lm"></i>5일선${it.live ? " · 진행 중" : ""}</p>`;
  }
  function chMarketQuote(regular, cc) {
    let it = chLive(chDisplay(regular));
    if (cc === "jp") {
      const quote = worldQuotes().find((row) => row.sym === it.code);
      if (quote?.trend?.source_at === quote?.at && quote?.trend &&
          quote.trend.day === kstDay(Date.now()).slice(5).replace("-", "/") &&
          (quote.trend.day !== it.day || it.stale || (it.source_at > 0 && quote.at > it.source_at))) {
        it = {...quote.trend, stale: quote.trend.live && Date.now() - quote.at > 900000};
      }
    }
    if (cc === "tw" && it.code.endsWith(".TW")) {
      const quote = worldQuotes().find((row) => row.sym === it.code);
      if (quote?.day && !taiwanAwaiting(quote.day)) {
        const fresh = !quote.intraday || Date.now() - quote.at <= 900000;
        if (fresh && quote.trend) {
          return {...quote.trend, stale: false};
        }
        if (fresh) {
          return {...it, day: quote.day, px: quote.px, chg: quote.chg, base: quote.prev,
            source_at: quote.at, live: quote.intraday, stale: false, quoteOnly: true};
        }
      }
    }
    if (cc === "tw" && taiwanAwaiting(it.day)) {
      return {...it, awaiting: taiwanStatus(), chg: null, stale: true};
    }
    const now = Date.now();
    if (cc === "us" && !it.code.endsWith("=F") &&
        now >= Date.parse("2026-11-26T05:00:00Z") && now < Date.parse("2026-11-28T02:30:00Z") &&
        it.day !== "11/27") {
      const status = now < Date.parse("2026-11-27T09:00:00Z") ?
        "미국 추수감사절 휴장" : "11/27 미국 시세 대기";
      return {...it, awaiting: status, chg: null, stale: true};
    }
    const today = kstDay(now);
    if (cc === "jp" && it.code !== "^N225" && today === "2026-11-26" &&
        it.day === "11/26" && it.rows?.at(-2)?.[0] !== "11/25") {
      return {...it, chg: null, stale: true, state: "전일 종가 확인 중"};
    }
    return it;
  }
  function chMarketSession(it, cc) {
    if (it.awaiting) return it.awaiting;
    const day = it.day ? it.day + " " : "";
    if (cc === "jp" && it.day === kstDay(Date.now()).slice(5).replace("-", "/")) {
      const now = kst(Date.now()), minute = now.getHours() * 60 + now.getMinutes();
      if (minute >= 690 && minute < 750) return day + "오전장 마감";
    }
    if (it.stale) return day + "시세 확인 중";
    if (it.session && it.session !== "정규장") return day + it.session + (it.live ? "" : " 마지막");
    if (it.live) return day + "장중";
    return day + (cc === "tw" && it.code === "TAIEX" ? "공식 종가" : "정규장 종가");
  }
  function chDisplay(regular) {
    if (!regular.display) return regular;
    const it = {...regular, ...regular.display};
    const rows = regular.rows || [];
    const same = it.day === regular.day, pre = String(it.session).includes("프리") || String(it.session).includes("선물");   // 11/21: 선물 24시간도 전일 대비
    const baseRow = rows[same && (pre || it.session === "정규장") ? rows.length - 2 : rows.length - 1];
    // 옛 게시본이 전일 시간외 종가로 계산했어도 브라우저에서 정규장 기준으로 바로잡는다.
    const base = it.change_basis && Number.isFinite(it.base) && it.base > 0 ? it.base : baseRow?.[4];
    if (Number.isFinite(base) && base > 0) {
      it.base = base; it.base_day = it.change_basis ? it.base_day : baseRow[0];
      it.change = it.px - base;
      it.chg = Math.round((it.px / base - 1) * 10000) / 100 || 0;
      it.change_basis = String(it.session).includes("선물") ? "전일 정산가" : it.session === "정규장" ? "전일 정규장 종가" : "정규장 종가";
    } else { it.base = null; it.chg = null; it.change = null; }
    return it;
  }
  // ⚡ 실시간 체결(KIS 웹소켓 rt.json, 2초) 덮어쓰기 — 11/18 운영자 "실시간 숫자들 api 연동해서 추세추종 차트 수정"
  // 진행 중인 마지막 봉만 현재가로 바꾸고(고가·저가 갱신) 5일선·상태·거리를 다시 계산한다. 15초 넘은 값은 쓰지 않는다.
  const CH_RT = {KOSPI: "KOSPI", KOSDAQ: "KOSDAQ", "005930": "SMSN", "000660": "SKHX", "402340": "SKSQ", SOXL: "SOXL", KORU: "KORU", SKHY: "SKHY", NVDA: "NVDA"};
  // 11/20 운영자: 5일선은 NH·KRX와 같은 정규장 종가로 — 시간외 차트(display)는 지난 날 종가를 정규장 종가(reg_closes)로 바꿔 계산, 오늘은 현재가
  function chCl(it) {
    const m = new Map((it.reg_closes || []).map((x) => [x[0], x[1]])), rows = it.rows || [];
    return rows.map((r, i) => (i === rows.length - 1 ? r[4] : (m.get(r[0]) ?? r[4])));
  }
  function chState(it, px) {                                  // tools/chan.py state() 와 같은 규칙
    if (it.channel_width_valid === false) return "채널선 교차·재확인";
    if (it.channel_valid === false) return "접촉 검증 대기";
    const above = px > it.up_now * 1.01, overRes = !it.res_h || px > it.res_h;   // 11/19 운영자: 채널 상단·수평 저항(전고점) 둘 다
    if (above && px > it.ma5 && overRes) return "돌파 시도(장중)";
    if (above && px > it.ma5) return "채널 돌파·전고점 아래";
    if (above) return "채널 위·5일선 아래";
    if (px < it.lo_now) return "하단 이탈";
    if (px > it.ma5 && Math.abs(it.up_now / px - 1) <= 0.03) return "돌파 관찰·상단 근접";
    if (Math.max(it.gap_next, it.res_h ? (it.res_h / px - 1) * 100 : -Infinity) <= 3) return "상단 근접";
    return "채널 안";
  }
  // 11/19 운영자 "대장만 갈 수 없다": 섹터 돌파는 가장 약한 종목(채널 상단+1%·전고점 중 높은 쪽까지 가장 먼 종목)까지 돌파해야 인정
  function chSector(its) {
    const need = (it) => (Math.max(it.up_now * 1.01, it.ma5, it.res_h || 0) / it.px - 1) * 100;
    const lag = its.reduce((a, b) => need(b) > need(a) ? b : a);
    const ok = its.filter((it) => !it.stale && (it.state === "돌파 확인" || it.state === "돌파 시도(장중)")).length;
    const all = ok === its.length, conf = its.every((it) => it.state === "돌파 확인");
    const txt = all ? (conf ? "섹터 돌파 확인" : "섹터 돌파 시도(장중)") : `섹터 동반 돌파 대기 · 조건 충족 ${ok}/${its.length} · ${esc(lag.name)} ${need(lag) > 0 ? `목표까지 +${need(lag).toFixed(1)}%` : "시세·조건 확인"}`;
    return ` <span class="ch-st s-${all ? (conf ? "ok" : "try") : "in"}" title="섹터 돌파 조건: 구성 종목 모두 채널 상단(+1%)·5일선·확인된 전고점 위">${txt}</span>`;
  }
  function chLive(it) {
    const k = CH_RT[it.code], q = k && ((window.trlRt || {}).q || {})[k];
    if (!q || !(q.px > 0) || !Number.isFinite(q.at) || Date.now() - q.at > 15000 || !it.live || !(it.rows || []).length) return it;
    const rows = it.rows.map((r) => r.slice()), n = rows.length, last = rows[n - 1];
    last[2] = Math.max(last[2], q.px); last[3] = Math.min(last[3], q.px); last[4] = q.px;
    const closes = chCl({...it, rows}), ma5 = closes.slice(-5).reduce((a, b) => a + b, 0) / Math.min(5, n);
    const pc = n > 1 ? rows[n - 2][4] : null;
    const o = {...it, rows, px: q.px, chg: it.base > 0 ? Math.round((q.px / it.base - 1) * 10000) / 100 || 0 : pc ? Math.round((q.px / pc - 1) * 10000) / 100 || 0 : it.chg, ma5,
      gap_next: (it.up_next / q.px - 1) * 100, gap_low: (it.lo_now / q.px - 1) * 100, rt_at: q.at, rt_mk: q.mk};
    o.state = chState(o, q.px);
    return o;
  }
  // 신호 앞 시점 P(dev-20261122-2300, 11/22 운영자 "추천대로" · 11/23 운영자 '장중' 정의 decisions/trading.md)
  //  국내: 장중 = 평일 08:00~20:00(NXT 프리·KRX 정규장·NXT 애프터) — live 일 때 '장중(정규장)'·'장중(NXT 프리)'·'장중(NXT 애프터)'처럼 세션을 같이 적는다.
  //        20시 뒤·live 아님 → '종가'(정규장) 또는 '<세션> 마지막 체결'(시간외 값을 보여 줄 때).
  //  미국·일본: live 정규장 → '장중', live 시간외 → 세션명(카드 ch-ptag 와 같은 짧은 표기), 마감 → '종가' 또는 '<세션> 마지막 체결'.
  //  지연(stale) 값은 chSigNow 가 아예 신호를 내지 않는다 — 마감 뒤·지연에 '장중'이 붙는 경우는 없다(tests/test_chan_labels.cjs).
  const chSesShort = (s) => s && s !== "정규장" ? String(s).replace("마켓", "").replace("선물 24시간", "선물") : "";
  function chKrOpen(now) {                                     // 국내 장중 시간(평일 08:00~20:00 KST)
    const k = new Date((now ?? Date.now()) + 9 * 3600e3), d = k.getUTCDay(), m = k.getUTCHours() * 60 + k.getUTCMinutes();
    return d > 0 && d < 6 && m >= 480 && m < 1200;
  }
  function chPhase(it, cc, now) {
    const sh = chSesShort(it.session);
    if (cc === "kr" || cc === "kr_index") return it.live && chKrOpen(now) ? `장중(${sh || "정규장"})` : sh ? sh + " 마지막 체결" : "종가";
    return it.live ? sh || "장중" : sh ? sh + " 마지막 체결" : "종가";
  }
  // 11/19 운영자: 시그널도 실시간 값으로 다시 판단 — 돌파 쪽은 빨강(up), 저항·하락 쪽은 파랑(dn)
  //  신호 종류·순서·색은 그대로, 글자 앞에 시점 P 만 붙인다("P · 신호"). base = P 없는 신호 글자.
  function chSigNow(it, cc, now) {
    const rows = it.rows || [], n = rows.length;
    if (it.stale || n < 6 || !(it.px > 0)) return null;
    const phase = chPhase(it, cc, now), sig = (tone, base) => ({tone, base, phase, label: phase + " · " + base});
    if (it.state === "돌파 확인") return sig("up", "돌파 확정");
    if (it.state === "돌파 시도(장중)") return sig("up", "돌파 시도(종가 확인 전)");   // 확정과 합치지 않음(진짜 반등 = 종가 +1% 돌파)
    if (it.state === "하단 이탈") return sig("dn", "하락 시그널 · 채널 하단 이탈");
    if (it.channel_valid === false || !(it.ma5 > 0)) return null;
    const cl = chCl(it), ma5p = cl.slice(-6, -1).reduce((a, b) => a + b, 0) / 5, pc = cl[n - 2], h = rows[n - 1][2], open = rows[n - 1][1];
    // 11/20 운영자(마이크론): 채널 상단을 넘었다가 밀린 것과 5일선에 막힌 것을 구분
    if (it.up_now > 0 && it.channel_width_valid !== false) {
      // 11/20 운영자(엔비디아): 5일선과 채널 상단이 0.5% 안으로 겹치면 5일선 저항으로 부른다(채널 상단과 겹침 표시)
      const ma5h = it.ma5 + (h - it.px) / 5, near = Math.abs(ma5h / it.up_now - 1) <= 0.005;   // 고가 때의 5일선(오늘 값이 고가였을 때)
      if (h >= it.up_now * 1.01 && it.px < it.up_now) return sig("dn", near ? "5일선 돌파 실패(채널 상단과 겹침)" : "채널 상단 돌파 실패");
      if (h >= it.up_now && it.px < it.up_now * 0.997) return sig("dn", near ? "5일선 저항(채널 상단과 겹침)" : "채널 상단 저항");
    }
    if (pc <= ma5p && h >= it.ma5 && it.px < it.ma5 * 0.997) return sig("dn", "5일선 저항");   // chan.py 저항 규칙과 같음
    // 정규장 값일 때만 '시가부터' 구분: 시가 때 5일선 = ma5 + (시가 − 현재가)/5
    const regular = !it.session || it.session === "정규장", openMa5 = it.ma5 + (open - it.px) / 5;
    if (pc > ma5p && it.px < it.ma5) return sig("dn", regular && open > 0 && open < openMa5 ? "시가부터 5일선 아래" : "하락 시그널 · 5일선 이탈");
    if (pc <= ma5p && it.px > it.ma5) return sig("wk", regular && open > 0 && open > openMa5 ? "시가부터 5일선 위(돌파 전)" : "5일선 위로(돌파 전)");   // 11/19 운영자: 빨강은 진짜 돌파(채널 상단+1%·5일선·전고점)만
    return null;
  }
  const chEvTone = (s) => s.kind === "resist" || /저항|이탈|하락/.test(s.text || "") ? "dn" : "up";
  // 11/19 운영자: 시각과 멘트 전체를 종목 아래에 그대로(조사만 바로잡음: '6,710엔로' → '6,710엔으로')
  const CH_JOSA = {"가": "이", "는": "은", "를": "을", "로": "으로"};
  const chEvText = (t) => String(t || "").replace(/(\d)(원|엔)(가|는|를|로)(?=[\s,·(])/g, (m, d, u, j) => d + u + CH_JOSA[j]);
  function chSigBox(c, live) {                                // 국가 → 종목별: 지금 시그널 + 오늘 기록
    const evs = {};
    (c.signals || []).concat(c.watch_signals || [], c.resists || []).forEach((s) => { (evs[s.code] = evs[s.code] || []).push(s); });
    const seen = new Set(), by = [];
    live.forEach(({g, it}) => {
      if (seen.has(it.code)) return; seen.add(it.code);
      const now = chSigNow(it, g.cc), ev = (evs[it.code] || []).sort((a, b) => b.ts - a.ts);
      if (!now && !ev.length) return;
      let ctry = by.find((x) => x.country === g.country);
      if (!ctry) by.push(ctry = {country: g.country, cc: g.cc, rows: []});
      ctry.rows.push({g, it, now, ev});
    });
    if (!by.length) return "";
    const pxCls = (v) => v == null || !isFinite(v) ? "dim" : v > 0.005 ? "up" : v < -0.005 ? "down" : "dim";
    return `<p class="ch-sg-h">⚡ 돌파·저항 시그널 <small><i class="ch-dot up"></i>돌파 시도·확정 <i class="ch-dot dn"></i>저항·하락 시그널 · 실시간 값으로 다시 판단</small></p>` +
      by.map((x) => `<div class="ch-sgc"><p class="ch-sgc-h">${CH_FLAG[x.cc] || ""} ${esc(x.country)}</p><ul>${x.rows.map(({g, it, now, ev}) =>
        `<li><b class="ch-nm">${esc(it.name)}</b> <b class="mn ${pxCls(it.chg)}">${chFmt(units, it.px)}</b> <small class="${pxCls(it.chg)}">${it.chg == null ? "" : `${it.chg > 0 ? "+" : ""}${(+it.chg).toFixed(2)}%`}</small>
          ${now ? `<span class="ch-sg ${now.tone}">${esc(now.label)}</span>` : ""}
          ${ev.map((s) => `<p class="ch-evl ${chEvTone(s)}"><time>⏱ ${hm(s.ts)}</time> ${esc(chEvText(s.text))}</p>`).join("")}</li>`).join("")}</ul></div>`).join("");
  }
  let chanRtSig = "";
  if (typeof window.addEventListener === "function") window.addEventListener("trl:quotes", () => {   // 실시간 값이 바뀌었을 때만 다시 그림
    const c = window.trlChan, q = (window.trlRt || {}).q || {}; if (!c) return;
    const sig = Object.values(CH_RT).map((k) => q[k] ? `${k}:${q[k].px}` : "").join("|");
    if (sig !== chanRtSig) { chanRtSig = sig; drawChan(); }
  });
  function drawChan() {
    return window.trlViewport ? window.trlViewport.update(drawChanRaw) : drawChanRaw();
  }
  function drawChanRaw() {                                       // 11/17 운영자: 표 대신 채널 그래프를 항상 펼쳐서(1분마다 갱신)
    const box = q("#chan"), c = window.trlChan; if (!box) return;
    const asiaGroups = worldQuotes().filter((row) => {
      if (!["TAIEX", "^N225"].includes(row.sym) || !row.trend ||
          !Array.isArray(row.trend.rows) || row.trend.rows.length < 20 ||
          !Number.isFinite(row.trend.source_at) || row.trend.source_at !== row.at || row.trend.px !== row.px || row.trend.chg !== row.chg) return false;
      const zone = row.sym === "^N225" ? "Asia/Tokyo" : "Asia/Taipei";
      const quoteDay = new Intl.DateTimeFormat("en-US", {timeZone: zone, month: "2-digit", day: "2-digit"}).format(row.at);
      return row.trend.day === quoteDay;
    }).map((row) => ({cc: row.sym === "TAIEX" ? "tw" : "jp", country: row.region, sector: "대표 지수",
      index: true, items: [row.trend]}));
    const allGroups = [...asiaGroups, ...(c?.groups || [])];
    if (!allGroups.length) { box.hidden = true; return; }
    box.hidden = false;
    q("#chanRule").textContent = "돌파 관찰: 5일선 위·채널 상단 3% 이내 · 종가와 이후 지지 확인";
    const sgBox = q("#chanSig"), liveItems = [];
    const live = allGroups.some((g) => g.items.some((it) => it.display ? it.display.live : it.live));
    const rtOn = Object.values(CH_RT).some((k) => { const r = ((window.trlRt || {}).q || {})[k]; return r && Date.now() - r.at < 15000; });
    const at = Math.max(c?.at || 0, ...asiaGroups.map((g) => g.items[0].source_at || 0));
    q("#chanStamp").textContent = `${hm(at)} KST${live ? " · 진행 중인 봉 포함" : ""}${rtOn ? " · 일부 실시간 체결" : ""}`;
    let html = "", lastC = null;
    // Cross-country sector comparison stays separate from local-currency price charts.
    const globalByCode = new Map();
    allGroups.forEach((g) => (g.items || []).forEach((regular) => {
      if (CH_HIDE.has(regular.code) || globalByCode.has(regular.code)) return;
      globalByCode.set(regular.code, {g, it: chMarketQuote(regular, g.cc)});
    }));
    const globalViews = (c?.global_sectors || []).map((view) => {
      const rows = (view.codes || []).map((code) => globalByCode.get(code)).filter(Boolean);
      return {view, rows};
    }).filter(({rows}) => rows.length > 1);
    if (globalViews.length) {
      html += '<section class="ch-global-flow"><p class="ch-global-title">글로벌 섹터 흐름 <small>국가별 등락 비교 · 실제 자금 유출입 집계가 아닙니다</small></p><div class="ch-global-grid">';
      globalViews.forEach(({view, rows}) => {
        const ordered = [...rows].sort((a, b) => (Number.isFinite(b.it.chg) ? b.it.chg : -Infinity) - (Number.isFinite(a.it.chg) ? a.it.chg : -Infinity));
        html += `<article class="ch-global-card"><h3>${esc(view.label)}</h3><ul>${ordered.map(({g, it}) => {
          const value = Number.isFinite(it.chg) ? `${it.chg > 0 ? "+" : ""}${it.chg.toFixed(2)}%` : "—";
          const tone = !Number.isFinite(it.chg) ? "dim" : it.chg > 0 ? "up" : it.chg < 0 ? "down" : "dim";
          const session = chMarketSession(it, g.cc);
          return `<li><span>${CH_FLAG[g.cc] || ""} ${esc(it.name)} <small>${esc(it.code)} · ${esc(session)}</small></span><b class="${tone}">${value}</b></li>`;
        }).join("")}</ul></article>`;
      });
      html += "</div></section>";
    }
    // 한국 거래시간에는 한국과 미국을 연속 배치한다.
    const hrK = (new Date().getUTCHours() + 9) % 24;
    const slot = hrK >= 8 && hrK < 20 ? ["kr", "us", "jp", "tw", "cn"] : ["us", "kr", "jp", "tw", "cn"];
    const cOrd = (cc) => slot.indexOf(cc === "kr_index" ? "kr" : cc);
    const groups = allGroups.map((g, i) => ({g, i})).sort((a, b) => cOrd(a.g.cc) - cOrd(b.g.cc) || a.i - b.i).map((x) => x.g);
    groups.forEach((g) => {
      if (g.country !== lastC) { if (lastC) html += `</div>`; html += `<div class="ch-country"><p class="ch-ch">${CH_FLAG[g.cc] || ""} ${esc(g.country)}${(window.trlMarketNoticesFor?.(g.cc === "kr_index" ? "kr" : g.cc) || []).map(({href,text}) => ` <a class="ch-holiday" href="${esc(href)}">${esc(text)}</a>`).join("")}</p>`; lastC = g.country; }
      const many = g.items.length > 1 && g.cc !== "kr_index";
      const items = g.items.filter((r) => !CH_HIDE.has(r.code)).map((regular) => ({regular, it: chMarketQuote(regular, g.cc)}));   // 11/19 운영자: 다우 선물 내림
      const rankable = ({it}) => Number.isFinite(it.chg) && !it.stale;
      const strength = (item) => rankable(item) ? item.it.chg : -Infinity;
      if (many) items.sort((a, b) => strength(b) - strength(a));
      html += `<div class="ch-sec"><p class="ch-sh">${esc(g.sector)}${many ? "<small>현재 세션 등락률 높은 순</small>" : ""}${many && items.filter(({it}) => !it.ipo).length > 1 ? chSector(items.map(({it}) => it).filter((x) => !x.ipo)) : ""}</p><div class="ch-grid2">`;
      items.forEach((item, index) => {
        const {regular, it} = item;
        const units = g.index ? "kr_index" : g.cc;
        if (it.awaiting) {
          html += `<article class="ch-card" data-viewport-key="channel:${esc(it.code)}"><div class="ch-top"><b class="ch-nm">${esc(it.name)}</b><small>${esc(it.awaiting)}</small></div></article>`;
          return;
        }
        if (it.quoteOnly) {
          const tone = it.chg > 0 ? "up" : it.chg < 0 ? "down" : "dim";
          html += `<article class="ch-card" data-viewport-key="channel:${esc(it.code)}"><div class="ch-top"><b class="ch-nm">${esc(it.name)}</b><span class="ch-quote"><b class="${tone}">${chFmt(units, it.px)}</b><b class="${tone}">${it.chg > 0 ? "+" : ""}${it.chg.toFixed(2)}%</b></span><small>TWSE · ${hm(it.source_at)} KST</small></div></article>`;
          return;
        }
        if (it.ipo) { html += chIpoCard(it, g.cc); return; }      // 상장 초기 종목은 5분봉 흐름을 표시
        liveItems.push({g, it});
        const horizontal = g.cc === "us" ? chHorizontalLower(it.rows || []) : null;
        const sgNow = chSigNow(it, g.cc);
        const rank = index + 1;
        const mdl = many && rankable(item) ? `<span class="ch-md m${Math.min(rank, 4)} notranslate" translate="no">${(/^(?:|ko)$/i.test(new URLSearchParams(location.search).get("lang") || "") && !/googtrans=\/ko\/(?!ko)/.test(document.cookie) ? ["금", "은", "동"][index] : "") || rank}</span>` : "";
        html += `<article class="ch-card${sgNow ? " t-" + sgNow.tone : ""}" data-viewport-key="channel:${esc(it.code)}">
          <div class="ch-top">${mdl}<b class="ch-nm">${esc(it.name)}</b>${(() => { const k = it.chg == null || !isFinite(it.chg) ? "dim" : it.chg > 0.005 ? "up" : it.chg < -0.005 ? "down" : "dim";   // 11/19 운영자: 현재가도 전일 종가 대비 색·굵게(상승 빨강·하락 파랑·보합 회색)
            const ses = [chMarketSession(it, g.cc), it.stale ? "cls" : it.session && it.session !== "정규장" ? "ext" : it.live ? "live" : "cls"];
            return `<span class="ch-ptag p-${ses[1]}">${esc(ses[0])}</span><span class="ch-quote"><b class="mn ${k}">${chFmt(units, it.px)}</b><b class="${k}"`; })()} title="${esc(it.change_basis || "전일 정규장 종가")}${it.base > 0 ? ` ${chFmt(units, it.base)}` : ""} 대비">${it.chg == null ? "확인 중" : `${it.chg > 0 ? "+" : ""}${(+it.chg).toFixed(2)}%`}</b></span>${sgNow ? `<span class="ch-sg ${sgNow.tone}">${({up: "▲", dn: "▼", wk: "△"})[sgNow.tone]} ${esc(sgNow.label)}</span>` : ""}<span class="ch-st s-${CH_ST[it.state] || "in"}">${esc(it.state)}</span><small class="ch-session">${g.cc === "kr_index" && it.stale ? `${esc(it.day)} 기준 · ${it.source_at ? "지연 " + hm(it.source_at) : "일봉"}` : it.rt_at || it.source_at ? hm(it.rt_at || it.source_at) + " KST" : ""}</small></div>
          ${chLvLine(it, units, horizontal)}${chCloseExt(regular, it, units)}${chChart(it, units, sgNow, horizontal)}</article>`;
      });
      html += `</div></div>`;
    });
    if (lastC) html += `</div>`;
    q("#chanBoard").innerHTML = html;
    if (sgBox) { sgBox.hidden = true; sgBox.innerHTML = ""; }   // 11/19 운영자: 위쪽 시그널 글 칸은 내림 — 카드 색·차트 표시로만
    // 11/17 운영자: 추세 기록 칸은 내림 — 그래프만 실시간으로
  }
  function s7Org(r) {
    if (s7?.open && r.est && r.est.org != null) return `${eokS(r.est.org)}<small class="fl-k">기관 장중 추정 · 한투 ${esc(r.est.round || "")}</small>`;
    if (s7?.open && r.est_kw && r.est_kw.org != null) return `${eokS(r.est_kw.org)}<small class="fl-k">기관 장중 추정 · 키움 ${esc(r.est_kw.hm || "")}</small>`;
    const p = r.org_public;
    if (p) return `<b class="${cls(p.org_q)}">${p.org_q > 0 ? "+" : ""}${p.org_q.toLocaleString("ko-KR")}주</b><small class="fl-k">기관 추정 ${esc(p.round)}</small>`;
    return invCell(r, "org") + (r.inv && !r.est && !r.est_kw ? `<small class="fl-k">${esc(md(r.inv.day))} 확정</small>` : "");
  }
  function s7Program(r) {
    if (!r.prog) return '<span class="dim">오늘 미확인</span>';
    if (r.prog.scope) return `${eokS(r.prog.amt)}<small class="fl-k">매동 잠정 · ${esc(r.prog.hm)}</small>`;
    return progCell(r);
  }
  function drawS7() {
    const box = q("#s7Box"); if (!box) return;
    if (!s7 || !(s7.rows || []).length) { box.hidden = true; return; }
    box.hidden = false;
    const k = s7.kospi || {}, s = s7.s7 || {};
    const pt = (v) => v == null ? "-" : `<b class="${cls(v)}">${v > 0 ? "+" : ""}${(+v).toFixed(1)}p</b>`;
    const ek = (v) => v == null ? "-" : `<b class="${cls(v)}">${v > 0 ? "+" : ""}${Math.round(v).toLocaleString("ko-KR")}억</b>`;
    const mx = Math.max(...s7.rows.map((r) => Math.abs(r.pts || 0)), 1);
    const bar = (v) => `<span class="s7-bar"><i class="${v >= 0 ? "s7-u" : "s7-d"}" style="width:${Math.round(Math.abs(v || 0) / mx * 100)}%"></i></span>`;
    const partial = s7.reconcile, st = `${hm(s7.at)} 기준${s7.open ? " · 1분마다 갱신" : " · 장 마감"}${partial ? " · 일부 종목 시세 확인 중" : ""}`;
    const body = sortRows(s7.rows, "s7").map((r) => `<tr><td class="fl-n">${esc(r.name)}</td><td>${pct(r.chg)}</td>
      <td class="s7-c">${partial ? (r.indexUnverified ? '<span class="dim">대조 중</span>' : r.code === "005935" ? '<span class="dim">지수 미포함</span>' : '<span class="dim">재계산 중</span>') : r.w == null ? '<span class="dim">지수 미포함</span>' : `${pt(r.pts)}${bar(r.pts)}`}</td><td>${partial ? (r.code === "005935" ? "-" : '<span class="dim">대조 중</span>') : r.w == null ? "-" : r.w.toFixed(1) + "%"}</td>
      <td>${r.val ? eok(r.val) : "-"}</td><td>${r.win ? eokS(r.win.amt) : "-"}</td><td>${invCell(r, "frgn")}</td><td>${s7Org(r)}</td>
      <td class="fl-5">${r.inv ? `${eokS(r.inv.frgn3 ?? r.inv.frgn5)} / ${eokS(r.inv.org3 ?? r.inv.org5)}` : "-"}</td><td>${s7Program(r)}</td></tr>`).join("");
    const orgRows = s7.rows.map((r) => {
      const value = s7.open
        ? (r.est?.org ?? r.est_kw?.org)
        : (r.inv?.day === s7.day ? r.inv.org : null);
      return value != null && Number.isFinite(+value) ? +value : null;
    }).filter((value) => value != null);
    const orgToday = orgRows.length ? orgRows.reduce((sum, value) => sum + value, 0) : null;
    const orgBasis = s7.open ? "장중 추정" : "당일 확정";
    const invDay = (s7.rows.find((r) => r.inv) || {}).inv;
    const futures = (brief?.futures || []).filter((f) =>
      ["코스피200 주간선물", "코스피200 야간선물"].includes(f.name) && Number.isFinite(f.px));
    box.innerHTML = `<p class="spot-h">🏛️ S7 · 코스피 영향 큰 7종목 <small>${st}</small></p>
      <div class="s7-sum">
        <div><span>코스피</span><b>${(+k.px).toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b> ${pct(k.chg)} ${pt(k.pts)}</div>
        <div><span>S7 기여</span>${partial ? '<b class="dim">재검증 중</b>' : `${pt(s.pts)} <small>${s.share != null ? `지수 변화의 ${s.share}%` : ""} · 비중 ${s.w}%</small>`}</div>
        <div><span>S7 제외 코스피</span>${partial ? '<b class="dim">재검증 중</b>' : `${s.ex_chg != null ? pct(s.ex_chg) : "-"} ${pt(s.ex_pts)}`}</div>
        <div><span>상승·하락 종목</span><b>${k.up != null ? `${k.up} / ${k.dn}` : "-"}</b></div>
        <div><span>S7 기관 합계 <small>${orgBasis} · ${orgRows.length}/7종목</small></span>${eokS(orgToday)}</div>
        <div><span>코스피 투자자 <small>${k.flow_day ? md(k.flow_day.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")) : ""}</small></span>개인 ${ek(k.ind)} · 외국인 ${ek(k.frgn)} · 기관 ${ek(k.org)}</div>
        <div><span>코스닥 투자자 <small>${s7.kosdaq?.flow_day ? md(s7.kosdaq.flow_day.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")) : ""}</small></span>${s7.kosdaq?.px ? `<b>${(+s7.kosdaq.px).toLocaleString("ko-KR", {minimumFractionDigits:2,maximumFractionDigits:2})}</b> ${pct(s7.kosdaq.chg)} · ` : ""}개인 ${ek(s7.kosdaq?.ind)} · 외국인 ${ek(s7.kosdaq?.frgn)} · 기관 ${ek(s7.kosdaq?.org)}</div>
        <div><span>프로그램 매매</span>차익 ${ek(k.arb)} · 비차익 ${ek(k.nonarb)} · 합계 ${ek(k.prog)}</div>
        ${futures.map((f) => `<div><span>${esc(f.name)}</span><b>${f.px.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}</b> ${f.chg == null ? "" : pct(f.chg)}${f.base ? ` <small>기준 ${esc(f.base)}</small>` : ""}</div>`).join("")}
      </div>
      <div class="fl-scroll"><table class="fl-t"><tr>${sth("s7", "name", "종목")}${sth("s7", "chg", "등락")}${sth("s7", "pts", "지수 기여", "추정 포인트")}${sth("s7", "w", "코스피 비중", "전일 시총")}${sth("s7", "val", "거래대금", "통합")}${sth("s7", "win", "외국계 창구", "오늘")}${sth("s7", "frgn", "외국인", invSub(s7.rows, invDay ? md(invDay.day) : ""))}${sth("s7", "org", "기관", invSub(s7.rows, invDay ? md(invDay.day) : ""))}${sth("s7", "s5", "외국인·기관", "3일 합계")}${sth("s7", "prog", "프로그램", "오늘 순매수")}</tr>${body}</table></div>`;
  }
  function drawFlows() {
    const box = q("#flowBox"); if (!box) return;
    const gs = (flows && flows.groups) || [];
    if (!gs.length) { box.hidden = true; return; }
    box.hidden = false;
    const st = `${hm(flows.at)} KST${flows.open ? " · 장중" : " · 마감 · 시간외 포함"}`;
    const sum = (rows, f) => rows.reduce((a, r) => a + (f(r) || 0), 0);
    const chips = gs.map((g) => { const v = g.val || sum(g.rows, (r) => r.val), w = sum(g.rows, (r) => r.win && r.win.amt);
      return `<button class="sc-chip fl-chip${flowOpen === g.name ? " on" : ""}" data-flow-open="${esc(g.name)}" aria-expanded="${flowOpen === g.name}">
        ${g.icon || ""} ${esc(g.name)} <small>상승 ${g.up}/${g.n}</small> <small>대금 ${eok(v)}</small> <small>외국계 창구 ${eokS(w)}</small>${g.rows.some((r) => r.prog) ? ` <small>프로그램 ${eokS(sum(g.rows, (r) => r.prog && r.prog.amt))}</small>` : ""}${g.rows.some((r) => r.est) ? ` <small>외국인 추정 ${eokS(sum(g.rows, (r) => r.est && r.est.frgn))}${g.rows.some((r) => r.est && r.est.org != null) ? ` · 기관 ${eokS(sum(g.rows, (r) => r.est && r.est.org))}` : ""}</small>` : ""}</button>`; }).join("");
    const g = gs.find((x) => x.name === flowOpen);
    box.innerHTML = `<p class="spot-h">💰 주도주 수급 <small>${st}</small></p>
      <div class="sc-bar">${chips}</div>
      ${g ? `<div class="sc-panel">${sortChips("flow", [["chg", "등락률순"], ["val", "거래대금순"], ["mcap", "시가총액순"], ["frgn", "외국인순"], ["org", "기관순"], ["win", "외국계 창구순"], ["prog", "프로그램순"], ["name", "이름순"]])}${flowTable(g, 99)}
      ${methodNote("flow", "수급 기준 보기", "외국계 창구는 증권사 창구 집계입니다. 외국인·기관 수급의 장중 추정치와 거래소 확정치는 표에서 구분합니다.")}</div>` : ""}`;
  }

  /* ── 📋 시장 브리핑(실시간 + 매일 12시 기록) ── */
  function briefHtml(b) {
    if (!b) return "";
    const of = b.official || {};
    const bk = of.bok || {}, ymd = (d) => String(d || "").replace(/^(\d{4})(\d{2})(\d{2})?$/, (_, y, m, dd) => dd ? `${m}/${dd}` : `${y}-${m}`);
    return (of.ust || of.eia || (of.bls || []).length || bk.usdkrw || bk.ktb3y || bk.base) ? `<div class="bcol"><h4>🏛 공식 발표 데이터 <small class="dim">미 재무부·EIA·BLS·한국은행 원자료</small></h4><ul class="bn">
      ${bk.usdkrw || bk.ktb3y || bk.base ? `<li><b>한국은행</b> <small class="dim">ECOS 공식 확정치</small><br>${bk.usdkrw ? `원/달러 매매기준율 ${bk.usdkrw.v.toFixed(1)}원${bk.usdkrw.chg ? ` <small class="${cls(bk.usdkrw.chg)}">${bk.usdkrw.chg > 0 ? "+" : ""}${bk.usdkrw.chg.toFixed(1)}</small>` : ""} <small class="dim">${esc(ymd(bk.usdkrw.date))}</small>` : ""}${bk.ktb3y ? ` · 국고채 3년 ${bk.ktb3y.v.toFixed(3)}%${bk.ktb3y.chg ? ` <small class="${cls(bk.ktb3y.chg)}">${bk.ktb3y.chg > 0 ? "+" : ""}${Math.round(bk.ktb3y.chg * 1000) / 10}bp</small>` : ""}` : ""}${bk.base ? ` · 기준금리 ${bk.base.v.toFixed(2)}% <small class="dim">${esc(ymd(bk.base.date))}</small>` : ""}</li>` : ""}
      ${of.ust ? `<li><b>미 국채 종가</b> <small class="dim">${esc(of.ust.date)}</small><br>${[["3M", "3개월"], ["2Y", "2년"], ["10Y", "10년"], ["30Y", "30년"]].filter(([k]) => of.ust.rates[k] && of.ust.rates[k].v != null).map(([k, n]) => `${n} ${of.ust.rates[k].v.toFixed(2)}%${of.ust.rates[k].bp ? ` <small class="${cls(of.ust.rates[k].bp)}">${of.ust.rates[k].bp > 0 ? "+" : ""}${of.ust.rates[k].bp}bp</small>` : ""}`).join(" · ")}${of.ust.s10_2 != null ? `<br><small class="dim">10년−2년 ${of.ust.s10_2}bp · 10년−3개월 ${of.ust.s10_3m}bp</small>` : ""}</li>` : ""}
      ${of.eia ? `<li><b>EIA 주간 석유 재고</b> <small class="dim">${esc(of.eia.week)} 주 · 백만 배럴 · 전주 대비</small><br>${of.eia.items.map((x) => `${esc(x.name)} ${x.v.toFixed(1)} <small class="${cls(x.chg)}">${x.chg > 0 ? "+" : ""}${x.chg.toFixed(2)}</small>`).join(" · ")}</li>` : ""}
      ${(of.bls || []).length ? `<li><b>BLS 물가·고용</b> <small class="dim">${esc(of.bls[0].period)}</small><br>${of.bls.filter((x) => x.v != null).map((x) => `${esc(x.name)} ${x.v > 0 && x.unit.startsWith("천") ? "+" : ""}${x.v}${x.unit.startsWith("%") ? "%" : x.unit.startsWith("천") ? "천 명" : ""}`).join(" · ")}<br><small class="dim">물가는 전년 같은 달 대비, 고용은 전월 대비 증감</small></li>` : ""}
    </ul></div>` : "";
  }
  function drawBrief() {
    const section = q("#brief"), box = q("#briefNow");
    if (!section || !box) return;
    const html = briefHtml(brief);
    section.hidden = !html;
    const link = q('nav a[href="#brief"]');
    if (link) link.hidden = !html;
    box.innerHTML = html;
  }
  const kstDay = (ms) => { const d = kst(ms); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

  /* ── 최근 24시간 뉴스에 많이 나온 종목 ── */
  /* ── 📡 텔레그램 통합 정리 — 리서치·시황 방 글을 주제별로 묶음(1분마다, tools/tg_digest.py) ── */
  function drawTgSum() {
    const box = q("#tgSum"); if (!box) return;
    const t = tgsum; if (!t || !(t.topics || []).length) { box.hidden = true; return; }
    const lines = (ln) => `<li${ln.hot ? ' class="hot"' : ""}><span class="tg-t">${esc(gist(ln.text, 110))}</span>`
      + `<span class="tg-m">${hm(ln.last)} · ${ln.srcs.map(esc).join(" · ")}</span></li>`;
    const open = box.querySelector("details")?.open ? " open" : "";
    box.innerHTML = `<details${open}><summary class="tg-head">📰 주제별 뉴스</summary>`
      + `<div class="tg-grid">` + t.topics.map((tp) => `<div class="tg-card"><p class="tg-name">${esc(tp.name)}</p><ul>${tp.lines.map(lines).join("")}</ul></div>`).join("") + `</div></details>`;
    box.hidden = false;
  }
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
  function mainNews(limit, featured) {
    const now = Date.now();
    const pool = news.filter((n) => n.text && isRecent(n.ts, now, 1) && !isStrat(n) && impScore(n) >= 55)
      .sort((a, b) => impScore(b) - impScore(a) || b.ts - a.ts);
    const differs = (n) => !featured || simTxt(bigr(featured), bigr(n.text)) < 0.45;
    const top = dedupe(pool.filter(differs), false).slice(0, limit);
    // 중요 속보가 적은 시간대(11/18 운영자 "앞단은 뉴스 위주로"): 같은 1시간 범위의 최신 속보를 더 보여 준다
    if (top.length < limit) {
      const seen = new Set(top.map((n) => n.ts));
      const fill = dedupe(news.filter((n) => n.text && isRecent(n.ts, now, 1) && !isStrat(n) && !seen.has(n.ts) && differs(n)).sort((a, b) => b.ts - a.ts));
      for (const n of fill) { if (top.length >= limit) break; if (!top.some((o) => simTxt(o._g || bigr(o.text), n._g) >= 0.45)) top.push(n); }
    }
    return top.sort((a, b) => b.ts - a.ts);
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
    // 11/22 UX: 기한(until)·'장중' 카드 마감(app.js trlHlStale)을 그릴 때마다 다시 확인 — 지난 카드가 첫 화면에 남지 않게
    const live_ = (x) => (!x.until || x.until >= kstDay(Date.now())) && !(window.trlHlStale && window.trlHlStale(x));
    const autoC = (window.trlAuto || []).filter(live_), autoT = new Set(autoC.map((x) => x.tag));
    const hl = [...autoC, ...headline.filter((x) => live_(x) && !autoT.has(x.tag))];
    const L = window.trlHlLang || ((y) => y);
    const featured = hl.find((x) => x.main) || hl[0];
    const pins = (featured ? [featured] : []).map((x0) => { const x = L(x0); return `<li class="mn-pin${x.main ? " mn-main" : ""}"><a href="#headline"${x._fixed ? ' translate="no"' : ""}><span class="mn-t">${x.main ? "🔴" : "📌"} ${esc(x.tag || "주요 이슈")}</span> <b>${esc(x.title)}</b>${x.when ? ` <small>${esc(x.when)}</small>` : ""}</a></li>`; });
    const live = mainNews(3 - pins.length, featured?.title).map((n) => {
      const g = gist(newsText(n)), full = newsText(n).replace(/…$/, "");
      const t = g !== full ? `<span class="mn-x" data-open="0" title="눌러서 전체 보기">${esc(g)}</span><span class="mn-full" hidden>${esc(full)}</span>` : esc(g);
      const v = n.verify === "official" ? " · 🏛 공식" : n.verify === "multi" ? " · ✔ 복수 출처" : n.verify === "unconfirmed" ? " · ⚠ 미확인" : "";
      return `<li class="mn-nw"><span class="mn-t">${hm(n.ts)}</span> <span class="mn-b">${t}${n.series_n > 1 ? ` <small>· 같은 발언 외 ${n.series_n - 1}건</small>` : ""} <small>${esc(sourceName(n))}${v}</small></span></li>`;
    });
    if (!pins.length && !live.length) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `<p class="mn-h"><span class="hl-dot"></span><b>📰 메인 뉴스</b> <small>핵심 뉴스 최대 3개</small><a href="#news">속보 전체 →</a></p><ul class="mn-list">${pins.join("")}${live.join("")}</ul>`;
  }

  /* ── 속보 목록 ── */
  const serOpen = new Set(), followOpen = new Set();
  document.addEventListener("toggle", (e) => { const d = e.target; if (d && d.matches && d.matches(".nw-ser")) { if (d.open) serOpen.add(d.dataset.ser); else serOpen.delete(d.dataset.ser); } }, true);
  document.addEventListener("toggle", (e) => {
    const d = e.target;
    if (!d.matches?.(".nw-follow")) return;
    if (d.open) followOpen.add(d.dataset.follow);
    else followOpen.delete(d.dataset.follow);
  }, true);
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
    box.addEventListener("change", (e) => { const f = e.target.dataset.f; if (!f) return; flt[f] = f === "hrs" ? +e.target.value : e.target.value; shown = 10; drawList(); });
  }
  const VIEWS = [["all", "전체", "모든 속보"], ["morning", "아침 시황", "증권사 시황·시황 분석 중 05~10시(한국 시간)에 올라온 글"],
    ["kr", "국내장", "'한국' 태그 또는 코스피·코스닥·외국인·한국거래소 등 국내 시장 단어가 든 글"],
    ["us", "미국장", "해외 뉴스·영문 기사, 'AI·빅테크' 태그, 나스닥·S&P·뉴욕증시 등 미국 시장 단어가 든 글"],
    ["macro", "매크로", "'연준·금리'·'중동·유가'·'환율'·'러·우' 태그 또는 금리·물가·환율·유가 단어가 든 글"],
    ["research", "증권사 리서치", "증권사 시황·시황 분석 채널 글"]];
  const KR_RX = /코스피|코스닥|KOSPI|KOSDAQ|외국인|기관 순매|한국거래소|KRX|넥스트레이드|NXT|국내 증시|국내증시|삼성전자|SK하이닉스|원\/달러 환율/;
  const US_RX = /나스닥|S&P|다우|뉴욕증시|뉴욕 증시|미국 증시|미 증시|월가|엔비디아|테슬라|애플|마이크로소프트|아마존|알파벳|메타|Nasdaq|Wall St/i;
  const MAC_RX = /금리|국채|연준|FOMC|CPI|PCE|고용지표|비농업|물가|환율|달러인덱스|유가|WTI|브렌트|OPEC|Fed\b|Treasury|yield|inflation/i;
  const MAC_T = new Set(["연준·금리", "중동·유가", "환율", "러·우"]);
  const hayOf = (n) => `${n.text || ""} ${n.orig || ""} ${n.sub || ""}`;
  const byView = (n, v = view) => {
    if (v === "all") return true;
    const t = n.tags || [], h = hayOf(n);
    if (v === "research") return isStrat(n);
    if (v === "morning") { const k = kst(n.ts).getHours(); return isStrat(n) && k >= 5 && k < 10; }
    if (v === "macro") return t.some((x) => MAC_T.has(x)) || MAC_RX.test(h);
    if (v === "kr") return t.includes("한국") || ["조선", "원전", "2차전지"].some((x) => t.includes(x)) || KR_RX.test(h);
    if (v === "us") return n.kind === "해외 뉴스" || n.lang === "en" || t.includes("AI·빅테크") || US_RX.test(h);
    return true;
  };
  const qNorm = (x) => String(x || "").toLowerCase().replace(/\s+/g, " ").trim();
  const bySearch = (n) => !query || qNorm(`${hayOf(n)} ${sourceName(n)} ${(n.tags || []).join(" ")} ${n.kind || ""}`).includes(query);
  const hit = (html) => {
    if (!query) return html;
    const rx = new RegExp(esc(query).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    return html.replace(/(^|>)([^<]+)/g, (m, a, t) => a + t.replace(rx, (x) => `<mark class="nw-hit">${x}</mark>`));
  };
  function drawViews(base) {
    const box = q("#newsViews"); if (!box) return;
    box.innerHTML = VIEWS.map(([k, label, rule]) => {
      const c = base.filter((n) => byView(n, k)).length;
      return `<button type="button" class="chip" data-view="${k}" aria-pressed="${k === view}" title="${esc(rule)}">${esc(label)} <small>${c}</small></button>`;
    }).join("");
  }
  function drawList() {
    drawFilters();
    const PIV = "🔴 변곡점 뉴스", STRAT = "📊 시황·전략";
    const tags = ["전체", PIV, STRAT, ...new Set(news.flatMap((n) => n.tags).filter((t) => t !== "시황"))];
    q("#newsChips").innerHTML = tags.map((t) => `<button class="chip${t === tag ? " on" : ""}" data-t="${esc(t)}">${esc(t)}</button>`).join("");
    const byTag = (n) => tag === "전체" || (tag === PIV ? n.pivot : tag === STRAT ? isStrat(n) : n.tags.includes(tag));
    const byKw = (n) => !kwFilter || kwFilter.rx.test(n.text + " " + (n.orig || "") + " " + (n.sub || ""));
    const now = Date.now();
    const byF = (n) => (flt.imp === "all" || isMajor(n)) && (!flt.hrs || isRecent(n.ts, now, flt.hrs))
      && (flt.ver === "all" || (flt.ver === "ok" ? ["multi", "official"].includes(n.verify) : flt.ver === "noun" ? n.verify !== "unconfirmed" : n.verify === "unconfirmed"));
    const base = news.filter((n) => byKw(n) && byF(n) && bySearch(n));
    drawViews(base.filter(byTag));
    let list = base.filter((n) => byTag(n) && byView(n));
    if (flt.sort === "imp") list = list.slice().sort((a, b) => impScore(b) - impScore(a) || b.ts - a.ts);
    if (flt.sort === "mkt") list = list.slice().sort((a, b) => mktScore(b) - mktScore(a) || b.ts - a.ts);
    if (kwFilter) q("#newsChips").insertAdjacentHTML("afterbegin", `<button class="chip on kw-chip" data-clear-kw="1">🔎 ${esc(kwFilter.label)} ✕</button>`);
    q("#newsList").innerHTML = list.slice(0, shown).map((n) => {
      const pv = n.pivot ? `<p class="nw-pv">🔴 변곡점 관련 뉴스 — ${movesOfNews(n.ts).map((m) => `${esc(m.name)} ${fmtMove(m)} (${hm(m.start)}–${hm(m.end)})`).join(", ") || (n.pv || []).map(esc).join(", ")}</p>` : "";

      const v = VER[n.verify] ? `<span class="nw-v ${VER[n.verify][1]}">${VER[n.verify][0]}${n.nsrc > 1 ? ` ${n.nsrc}곳` : ""}</span>` : "";
      const tr = n.tr === "auto" ? `<span class="nw-v v-tr" title="${esc(n.orig || "")}">🌐 자동 번역</span>` : "";
      const XC = { ok: ["🌐 외신 확인", "v-ok"], ref: ["🌐 해외 보도", "v-one"], diff: ["⚠ 외신과 수치 다름", "v-warn"] };
      const xc = n.xc && XC[n.xc.st] ? `<span class="nw-v ${XC[n.xc.st][1]}">${XC[n.xc.st][0]} · ${n.xc.src.map(esc).join("·")}</span>` : "";
      const xcl = n.xc && XC[n.xc.st] ? `<p class="nw-xc"><b>원문</b> ${esc(n.xc.en)} <small class="dim">— ${esc(n.xc.src[0])}${n.xc.ko ? ` · 번역: ${esc(n.xc.ko)}` : ""}</small></p>` : "";
      const also = (n.also || []).length ? `<details class="nw-follow" data-follow="${n.ts}"${followOpen.has(String(n.ts)) ? " open" : ""}><summary>후속 보도 ${n.also.length}건</summary><p class="nw-m">${n.also.map((a) => `${esc(sourceName(a))} ${hm(a.ts)}`).join(", ")}</p></details>` : "";
      return `<li class="nw${n.pivot ? " piv" : ""}${sel === n.ts ? " sel" : ""}${n.verify === "unconfirmed" ? " unv" : ""}" data-ts="${n.ts}">
        <div class="nw-t"><b>${hm(n.ts)}</b><span>${ago(n.ts)}</span></div>
        <div class="nw-b"><p class="nw-txt${n.kind === "섹터 시세" ? " sector" : ""}">${n.pivot ? "🔴 " : ""}${hit(esc(newsText(n)))}</p>${n.sub ? `<p class="nw-sub">${hit(esc(n.sub))}</p>` : ""}${pv}
          <p class="nw-m">${n.tags.map((t) => `<span class="nw-tag">${esc(t)}</span>`).join("")}${isStrat(n) ? `<span class="nw-tag strat">${esc(n.kind)}</span>` : ""}${v}${xc}${tr}
          <span class="nw-src">${esc(sourceName(n))}</span> <button type="button" class="chip nw-chart-open">차트 보기</button></p>
          ${xcl}${also}${n.series_n > 1 ? `<details class="nw-ser" data-ser="${n.ts}"${serOpen.has(String(n.ts)) ? " open" : ""}><summary>🧹 같은 ${esc(n.series_key)} 발언·발표 ${n.series_n - 1}건 더(2시간 안 연속, 한 줄로 묶음)</summary><ul>${(n.series || []).map((x) => `<li><b>${hm(x.ts)}</b> ${esc(x.text)}</li>`).join("")}</ul></details>` : ""}</div></li>`;
    }).join("") || `<li class="empty">조건에 맞는 속보가 없습니다.</li>`;
    q("#newsMore").hidden = list.length <= shown;
    const cnt = q("#newsCount");
    if (cnt) {
      const vl = (VIEWS.find((x) => x[0] === view) || VIEWS[0])[1];
      cnt.textContent = `${query ? `'${query}' 검색 · ` : ""}${view !== "all" ? vl + " · " : ""}${list.length}건${list.length > shown ? ` 중 ${shown}건 표시` : ""}`;
    }
  }

  const open = (coin, ts) => window.trlChart && window.trlChart.open({ coin, sel: ts, news });
  const full = !!q("#newsList");
  if (full) {
    q("#newsChips").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (!b) return; tag = b.dataset.t; shown = 10; drawList(); });
    q("#newsList").addEventListener("click", (e) => {
      if (e.target.closest("a, details")) return;
      const li = e.target.closest(".nw"); if (!li) return;
      const ts = +li.dataset.ts; sel = ts; if (window.trlCount) window.trlCount("news");
      drawCharts(); drawList();
      const m = movesOfNews(ts)[0], n = news.find((x) => x.ts === ts) || { tags: [] };
      const coin = m ? COIN[m.asset] : n.tags.includes("중동·유가") ? "xyz:CL" : (n.tags.includes("한국") || n.tags.includes("반도체")) ? "xyz:KR200" : n.tags.includes("연준·금리") ? "srv:US10Y" : "xyz:XYZ100";
      open(coin, ts);
    });
    q("#newsMore").addEventListener("click", () => { shown += 10; drawList(); });
    const vb = q("#newsViews");
    if (vb) vb.addEventListener("click", (e) => { const b = e.target.closest("[data-view]"); if (!b) return; view = b.dataset.view; shown = 10; drawList(); });
    const si = q("#newsSearch");
    if (si) {
      let t = 0;
      si.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { query = qNorm(si.value); shown = 10; drawList(); }, 160); });
      si.addEventListener("keydown", (e) => { if (e.key === "Escape" && si.value) { si.value = ""; query = ""; shown = 10; drawList(); } });
    }
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
      drawCharts(); drawList();
      goNews(q(`#newsList li[data-ts="${sel}"]`));   // 누른 속보 그 줄로 이동해 고정
    });
  }

  // 속보 칸으로 이동: 즉시 이동 + 잠깐 고정(viewport.js go). 없으면 예전 방식
  const goNews = (el) => { const t = el || q("#news"); if (!t) return; if (window.trlViewport && window.trlViewport.go) window.trlViewport.go(t); else t.scrollIntoView({ block: "start" }); };
  const redraw = () => (window.trlViewport ? window.trlViewport.update : (fn) => fn())(() => { if (full) drawCharts(); drawBrief(); drawChan(); drawTgSum(); drawHeroLive(); drawWorld(); drawSpot(); drawWatch(); drawSectors(); drawS7(); drawFlows(); if (full) { drawMoves(); drawTrend(); drawList(); } });
  const setKw = (label, pat) => {
    try { kwFilter = { label, rx: new RegExp(pat, "i") }; } catch { kwFilter = null; }
    tag = "전체"; shown = 30; drawTrend(); drawList(); goNews();
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
    const st = e.target.closest("[data-sec-tag]"); if (st && q("#news")) { kwFilter = null; tag = st.dataset.secTag; shown = 30; drawTrend(); drawList(); goNews(); return; }
    const sk = e.target.closest("[data-spot-kw]"); if (sk && q("#news")) { setKw(sk.dataset.spotName, sk.dataset.spotKw); return; }
    const sc = e.target.closest("[data-spot-chart]"); if (sc && window.trlChart) window.trlChart.open({ coin: sc.dataset.spotChart, name: sc.dataset.spotName, sel: null, news });
  });
  (async () => { await Promise.all([loadNews(), loadNotes(), loadSessionQuotes(), loadHeadline()]); redraw(); })();
  if (full) {
    drawCharts();
    const refreshCandles = async () => {
      if (document.hidden) return;
      await loadCandles();
      if (window.trlViewport) window.trlViewport.update(drawList); else drawList();
    };
    refreshCandles();
    setInterval(refreshCandles, 120000);
  }
  const refreshLive = async () => { if (document.hidden) return; await Promise.all([loadNews(), loadSessionQuotes()]); redraw(); };
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshLive(); });
  window.addEventListener("online", refreshLive);
  setInterval(refreshLive, 60000);                 // 속보·변곡점 1분마다
  const refreshDirect = async () => {
    if (document.hidden || fastBusy) return;
    fastBusy = true;
    try {
      const data = await directNews();
      if (data && data.updated > (window.trlUpdated || 0)) { await loadNews(data); redraw(); }
    } catch { window.trlNewsHealth = {direct:false, checked:Date.now(), failed:true}; }
    finally { fastBusy = false; window.dispatchEvent(new Event('trl:news')); }
  };
  setInterval(refreshDirect, 10000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshDirect(); });
  // 새 버전이 배포되면 오래 열어 둔 페이지도 스스로 새로고침(11/9: 고친 코드가 배포됐는데 열린 창은 옛 코드로 '시간외 확인 불가'를 계속 보여 줌)
  (() => {
    let first = null;
    const files = ["news.js", "app.js"];
    const stamp = async () => (await Promise.all(files.map(async (f) => {
      const r = await fetch(`${f}?v=${Date.now()}`, { method: "HEAD", cache: "no-store" });
      return r.ok ? (r.headers.get("last-modified") || r.headers.get("etag") || "") : "";
    }))).join("|");
    setInterval(async () => {
      try {
        const now = await stamp();
        if (!now.replace(/\|/g, "")) return;
        if (first === null) { first = now; return; }
        if (now !== first) { first = now; window.trlViewport?.offerUpdate(); }
      } catch { /* 다음에 다시 */ }
    }, 5 * 60000);
    stamp().then((v) => { if (first === null && v.replace(/\|/g, "")) first = v; }).catch(() => {});
  })();
  loadAsiaQuotes();
  setInterval(loadAsiaQuotes, 60000);
  setInterval(loadNotes, 600000);
  setInterval(async () => { await loadHeadline(); drawHeroLive(); }, 300000);   // 주요 이슈 5분마다
})();
