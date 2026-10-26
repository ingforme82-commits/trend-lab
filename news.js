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
  const cls = (v) => (v > 0.005 ? "c-up" : v < -0.005 ? "c-dn" : "c-fl");
  const pct = (v) => v == null ? "-" : `<b class="${cls(v)}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</b>`;

  let news = [], moves = [], series = {}, notes = [], candles = {}, sel = null, tag = "전체", shown = 15;
  let world = [], spot = [], trend = [], sectors = [], brief = null, briefs = [], kwFilter = null;   // kwFilter: {label, rx}

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
      news = j.items || []; moves = j.moves || []; series = j.series || {};
      world = j.world || []; spot = j.spot || []; trend = j.trending || []; sectors = j.sectors || []; brief = j.brief || null;
      window.trlMoves = moves; window.trlSeries = series; window.trlNews = news;
      setText("#newsStamp", `속보 갱신 ${hm(j.updated)} KST · ${ago(j.updated)}`);
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
  }
  const rowsOf = (k) => (k.startsWith("srv:") ? series[k.slice(4)] || [] : candles[k] || []);

  // 노트: 같은 자산 + 시간이 겹치는 변곡점에 붙는다
  const noteFor = (m) => notes.find((n) => n.assets.includes(m.asset) && Date.parse(n.from) <= m.end + 5 * 60000 && Date.parse(n.to) >= m.start - 5 * 60000);
  const movesOfNews = (ts) => moves.filter((m) => (m.news || []).includes(ts));

  /* ── 맨 위 띠: 변곡점 뉴스 먼저, 그다음 최신 속보 ── */
  let tickerKey = "";
  function drawTicker() {
    const box = q("#ticker"); if (!box) return;
    const recent = news.filter((n) => Date.now() - n.ts < 12 * 3600e3);
    const pick = [...recent.filter((n) => n.pivot).slice(0, 6), ...recent.filter((n) => !n.pivot)].slice(0, 14).sort((a, b) => b.ts - a.ts);
    const key = pick.map((n) => n.ts + (n.pivot ? "p" : "")).join(",");
    if (!pick.length || key === tickerKey) return;
    tickerKey = key;
    const row = pick.map((n) => `<a class="tk-i${n.pivot ? " hot" : ""}" href="${q("#news") ? "#news" : "index.html#news"}" data-ts="${n.ts}"><b>${hm(n.ts)}</b>${n.pivot ? "🔴 " : ""}${n.lang === "en" ? "🌐 " : ""}${esc(n.text)}</a>`).join("");
    box.innerHTML = `<span class="tk-label">📡 주요 시황</span><div class="tk-view"><div class="tk-track" style="animation-duration:${Math.max(40, pick.length * 9)}s">${row}${row}</div></div>`;
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

  /* ── 🔥 이번 주 화제 종목 ── */
  function drawSpot() {
    const box = q("#spotBox"); if (!box) return;
    if (!spot.length) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `<p class="spot-h">🔥 이번 주 화제 종목 <small>뉴스·가격 움직임이 많은 종목 · 추천 아님</small></p>` + spot.map((s) => {
      let rx; try { rx = new RegExp(s.kw || s.name, "i"); } catch { rx = /$^/; }
      const rel = news.filter((n) => rx.test(n.text + " " + (n.orig || "") + " " + (n.sub || "")));
      const today = rel.filter((n) => Date.now() - n.ts < 24 * 3600e3).length;
      return `<article class="spot">
        <div class="spot-top"><b class="spot-n">${esc(s.name)}</b><span class="spot-m">${esc(s.market || "")} · ${esc(s.since || "")}부터</span>
          ${s.px ? `<span class="spot-px">$${(+s.px).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}</span><b class="${cls(s.chg)}">${s.chg > 0 ? "+" : ""}${(+s.chg).toFixed(2)}%</b>` : ""}</div>
        ${s.reason ? `<p class="spot-r">${esc(s.reason)}</p>` : ""}
        <p class="spot-c">최근 24시간 관련 속보 <b>${today}건</b></p>
        ${rel.length ? `<ul class="spot-news">${rel.slice(0, 3).map((n) => `<li><b>${hm(n.ts)}</b> ${n.pivot ? "🔴 " : ""}${esc(n.text)}</li>`).join("")}</ul>` : ""}
        <div class="spot-btns">${s.hl ? `<button class="btn btn-gold btn-sm" data-spot-chart="${esc(s.hl)}" data-spot-name="${esc(s.name)}">1분봉 차트</button>` : ""}
          <button class="btn btn-ghost-dark btn-sm" data-spot-kw="${esc(s.kw || s.name)}" data-spot-name="${esc(s.name)}">관련 속보 보기</button></div>
      </article>`;
    }).join("");
  }

  /* ── 섹터 카드(종목 등락·고점 대비 위치) ── */
  function drawSectors() {
    const box = q("#sectorBox"); if (!box) return;
    if (!sectors.length) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = sectors.map((c) => `<article class="sec-card">
      <div class="sec-top"><b>${c.icon} ${esc(c.name)} 섹터</b><span>평균 <b class="${cls(c.avg)}">${c.avg > 0 ? "+" : ""}${c.avg.toFixed(2)}%</b></span>
        <button class="btn btn-ghost-dark btn-sm" data-sec-tag="${esc(c.tag)}">관련 속보</button></div>
      <div class="sec-rows">${c.rows.map((r) => `<div class="sec-r${r.flags.length ? " flag" : ""}"><span class="sec-n">${esc(r.name)}</span>
        <b class="${cls(r.chg)}">${r.chg > 0 ? "+" : ""}${r.chg.toFixed(2)}%</b>
        <small>${r.to3m != null && r.to3m > 0 ? "3개월 고점 돌파" : r.to52 != null ? `52주 고가 ${r.to52 > 0 ? "+" : ""}${r.to52}%` : ""}${Date.now() - r.at > 3 * 3600e3 ? ` · ${kst(r.at).getMonth() + 1}/${kst(r.at).getDate()} 마감` : ""}</small>
        ${r.flags.length ? `<span class="sec-f">${r.flags.map(esc).join(" · ")}</span>` : ""}</div>`).join("")}</div>
      <p class="fine" style="margin:6px 0 0">정규장 시세(야후, 5분 갱신) · 하루 ±3%, 3개월 고점 돌파, 52주 신고가 3% 이내가 생기면 속보 목록에 '섹터 시세'로 올라갑니다.</p>
    </article>`).join("");
  }

  /* ── 📋 시장 브리핑(실시간 + 매일 12시 기록) ── */
  async function loadBriefs() {
    try { briefs = await (await fetch(`data/briefs.json?t=${Math.floor(Date.now() / 600000)}`)).json(); } catch { briefs = []; }
  }
  const sg = (v, u = "%") => `<b class="${cls(v)}">${v > 0 ? "+" : ""}${(+v).toFixed(2)}${u}</b>`;
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
    return `<div class="bcol"><h4>📍 가장 크게 움직인 순간</h4><ul>${mv || '<li class="dim">최근 24시간 변곡점 없음</li>'}</ul></div>
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
    hb.innerHTML = briefs.length ? briefs.slice(0, 14).map((h, i) => `<details class="bh"${i === 0 ? "" : ""}><summary><b>${h.day.slice(5).replace("-", "/")}</b> ${hm(h.at)} 기록
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
  function drawList() {
    const PIV = "🔴 변곡점 뉴스", STRAT = "📊 시황·전략";
    const isStrat = (n) => n.kind === "증권사 시황" || n.kind === "시황 분석";
    const tags = ["전체", PIV, STRAT, ...new Set(news.flatMap((n) => n.tags).filter((t) => t !== "시황"))];
    q("#newsChips").innerHTML = tags.map((t) => `<button class="chip${t === tag ? " on" : ""}" data-t="${esc(t)}">${esc(t)}</button>`).join("");
    const byTag = (n) => tag === "전체" || (tag === PIV ? n.pivot : tag === STRAT ? isStrat(n) : n.tags.includes(tag));
    const byKw = (n) => !kwFilter || kwFilter.rx.test(n.text + " " + (n.orig || "") + " " + (n.sub || ""));
    const list = news.filter((n) => byTag(n) && byKw(n));
    if (kwFilter) q("#newsChips").insertAdjacentHTML("afterbegin", `<button class="chip on kw-chip" data-clear-kw="1">🔎 ${esc(kwFilter.label)} ✕</button>`);
    q("#newsList").innerHTML = list.slice(0, shown).map((n) => {
      const rs = REACT.map((s) => `${s.n} ${pct(reaction(s.k, n.ts))}`).join(" · ");
      const pv = n.pivot ? `<p class="nw-pv">🔴 변곡점 직전 뉴스 — ${movesOfNews(n.ts).map((m) => `${esc(m.name)} ${fmtMove(m)} (${hm(m.start)}–${hm(m.end)})`).join(", ") || (n.pv || []).map(esc).join(", ")}</p>` : "";
      return `<li class="nw${n.pivot ? " piv" : ""}${sel === n.ts ? " sel" : ""}" data-ts="${n.ts}">
        <div class="nw-t"><b>${hm(n.ts)}</b><span>${ago(n.ts)}</span></div>
        <div class="nw-b"><p class="nw-txt${n.kind === "섹터 시세" ? " sector" : ""}">${n.pivot ? "🔴 " : ""}${n.lang === "en" ? "🌐 " : ""}${esc(n.text)}</p>${n.sub ? `<p class="nw-sub">${esc(n.sub)}</p>` : ""}${pv}
          <p class="nw-m">${n.tags.map((t) => `<span class="nw-tag">${esc(t)}</span>`).join("")}${isStrat(n) ? `<span class="nw-tag strat">${esc(n.kind)}</span>` : ""}<span class="nw-r">이후 ${rs}</span>
          <span class="nw-src">${n.osrc ? `${esc(n.osrc)} · ${esc(n.src)} 경유` : `${esc(n.src)}${n.kind ? ` · ${esc(n.kind)}` : ""}`}</span></p></div></li>`;
    }).join("") || `<li class="empty">이 분류의 속보가 아직 없습니다.</li>`;
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

  const redraw = () => { drawHeroLive(); drawWorld(); drawSpot(); drawSectors(); drawBrief(); if (full) { drawCharts(); drawMoves(); drawTrend(); drawList(); } };
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
