/* 실시간 속보 + 지수 반응 — 텔레그램 헤드라인(live 브랜치)과 하이퍼리퀴드 5분봉 */
"use strict";
(() => {
  const NEWS_URL = "https://raw.githubusercontent.com/ingforme82-commits/trend-lab/live/news.json";
  const SERIES = [
    { k: "xyz:XYZ100", n: "나스닥100", d: 0 },
    { k: "xyz:KR200", n: "코스피200", d: 2 },
    { k: "xyz:CL", n: "WTI", d: 2, u: "$" },
  ];
  const H = 24;                       // 차트·반응 계산 구간(시간)
  const q = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const kst = (ms) => new Date(ms + (new Date().getTimezoneOffset() + 540) * 60000);
  const hm = (ms) => { const d = kst(ms); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const ago = (ms) => { const m = Math.round((Date.now() - ms) / 60000); return m < 1 ? "방금" : m < 60 ? `${m}분 전` : m < 1440 ? `${Math.floor(m / 60)}시간 전` : `${Math.floor(m / 1440)}일 전`; };
  let news = [], candles = {}, sel = null, tag = "주요", shown = 15;

  async function loadCandles() {
    const end = Date.now(), start = end - H * 3600e3;
    await Promise.all(SERIES.map(async (s) => {
      try {
        const r = await fetch("https://api.hyperliquid.xyz/info", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: "candleSnapshot", req: { coin: s.k, interval: "5m", startTime: start, endTime: end } }) });
        const d = await r.json();
        candles[s.k] = d.map((c) => [c.t, +c.c]);
      } catch { /* 이전 값 유지 */ }
    }));
  }

  // 1순위: GitHub API(바로 반영, 바뀐 게 없으면 304라 한도 소모 없음) → 한도 초과 등 실패 시 raw(최대 5분 캐시)
  const API_URL = "https://api.github.com/repos/ingforme82-commits/trend-lab/contents/news.json?ref=live";
  let apiBlockedUntil = 0;
  async function fetchNews() {
    if (Date.now() > apiBlockedUntil) {
      try {
        const r = await fetch(API_URL, { headers: { Accept: "application/vnd.github.raw+json" }, cache: "no-cache" });
        if (r.ok) return await r.json();
        if (r.status === 403 || r.status === 429) apiBlockedUntil = Date.now() + 20 * 60000;
      } catch { /* raw로 */ }
    }
    const r = await fetch(`${NEWS_URL}?t=${Math.floor(Date.now() / 60000)}`);
    return r.json();
  }
  async function loadNews() {
    try {
      const j = await fetchNews();
      news = j.items || [];
      setText("#newsStamp", `속보 갱신 ${hm(j.updated)} KST · ${ago(j.updated)}`);
      drawTicker();
    } catch { setText("#newsStamp", "속보를 불러오지 못했습니다."); }
  }
  const setText = (s, t) => { const e = q(s); if (e) e.textContent = t; };

  // 방문자를 오픈채팅 → 오프라인 그룹 스터디로 잇는 안내 문구(다음 스터디 일정은 데이터에서)
  const KAKAO = "https://invite.kakao.com/tc/p7OX5rMjd0";
  const base = q("#news") ? "" : "index.html";
  let nextStudies = [];
  fetch(`data/studies.json?t=${Math.floor(Date.now() / 600000)}`).then((r) => r.json()).then((list) => {
    const k = kst(Date.now()), today = `${k.getFullYear()}-${String(k.getMonth() + 1).padStart(2, "0")}-${String(k.getDate()).padStart(2, "0")}`;
    const up = list.filter((s) => s.date > today || (s.date === today && !(s.photos || []).length)).sort((a, b) => a.date.localeCompare(b.date));
    nextStudies = ["regular", "book"].map((x) => up.find((s) => s.series === x)).filter(Boolean);
    tickerKey = ""; drawTicker(); if (q("#newsList")) drawList();
  }).catch(() => {});
  function funnel() {
    const md = (d) => { const x = new Date(d + "T00:00:00"); return `${x.getMonth() + 1}/${x.getDate()}(${"일월화수목금토"[x.getDay()]})`; };
    const out = [{ t: "💬 이 속보, 내 계좌엔 무슨 의미일까? 오픈채팅에서 같이 해석해요 →", big: "💬 <b>속보 하나에 지수가 이렇게 움직입니다.</b> 내 계좌에는 어떤 의미인지, 오픈채팅방에서 매일 함께 해석합니다.", btn: "오픈채팅 참여하기", href: KAKAO, ext: true }];
    nextStudies.forEach((s) => out.push({
      t: `${s.series === "book" ? "📚" : "📈"} ${md(s.date)} 그룹 스터디 「${esc(s.title)}」 함께해요 →`,
      big: `${s.series === "book" ? "📚" : "📈"} <b>${md(s.date)} 오프라인 그룹 스터디 「${esc(s.title)}」</b> — 차트와 매매 기록을 들고 와서 함께 점검합니다. 참가비 무료.`,
      btn: "자세히 보기", href: `study.html?id=${encodeURIComponent(s.id)}`, ext: false }));
    out.push({ t: "🧭 나의 투자 스타일은? 2분 테스트 →", big: "🧭 <b>나는 추세추종형일까, 역발상형일까?</b> 2분 테스트로 내 스타일과 조심할 습관을 확인하고 스터디에서 함께 점검해요.", btn: "테스트 하러 가기", href: `${base}#quiz`, ext: false });
    return out;
  }

  // 맨 위 '주요 시황' 띠: 최근 속보 한 줄씩 계속 흐름(주요 속보 우선)
  let tickerKey = "";
  function drawTicker() {
    const box = q("#ticker"); if (!box) return;
    const recent = news.filter((n) => Date.now() - n.ts < 12 * 3600e3);
    const pick = [...recent.filter((n) => n.hot), ...recent.filter((n) => !n.hot)].slice(0, 14).sort((a, b) => b.ts - a.ts);
    const key = pick.map((n) => n.ts).join(",");
    if (!pick.length || key === tickerKey) return;
    tickerKey = key;
    const ctas = funnel();
    const row = pick.map((n, i) => `<a class="tk-i${n.hot ? " hot" : ""}" href="${q("#news") ? "#news" : "index.html#news"}" data-ts="${n.ts}"><b>${hm(n.ts)}</b>${n.lang === "en" ? "🌐 " : ""}${esc(n.text)}</a>`
      + ((i + 1) % 4 === 0 && ctas.length ? (({ t, href, ext }) => `<a class="tk-cta" href="${href}"${ext ? ' target="_blank" rel="noopener"' : ""}>${t}</a>`)(ctas[((i + 1) / 4 - 1) % ctas.length]) : "")).join("");
    box.innerHTML = `<span class="tk-label">🔴 주요 시황</span><div class="tk-view"><div class="tk-track" style="animation-duration:${Math.max(40, pick.length * 9)}s">${row}${row}</div></div>`;
    box.hidden = false;
  }

  // ts 시점 가격(그 이후 첫 봉의 시가 대신 직전 봉 종가) → 최신 종가 대비 변화율
  function reaction(k, ts) {
    const c = candles[k]; if (!c || c.length < 2 || ts < c[0][0]) return null;
    let i = c.findIndex((x) => x[0] > ts); i = i === -1 ? c.length - 1 : Math.max(0, i - 1);
    const p0 = c[i][1], p1 = c[c.length - 1][1];
    return p0 ? (p1 / p0 - 1) * 100 : null;
  }
  const pct = (v) => v == null ? "-" : `<b class="${v > 0.005 ? "c-up" : v < -0.005 ? "c-dn" : "c-fl"}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</b>`;

  function drawCharts() {
    const hot = news.filter((n) => n.hot);
    q("#newsCharts").innerHTML = SERIES.map((s) => {
      const c = candles[s.k] || [];
      if (c.length < 2) return `<div class="nc"><p class="nc-n">${s.n}</p><p class="fine">불러오는 중…</p></div>`;
      const W = 300, Hh = 76, t0 = c[0][0], t1 = c[c.length - 1][0];
      const vs = c.map((x) => x[1]), lo = Math.min(...vs), hi = Math.max(...vs), rg = hi - lo || 1;
      const X = (t) => ((t - t0) / (t1 - t0 || 1)) * W, Y = (v) => Hh - 6 - ((v - lo) / rg) * (Hh - 12);
      const path = c.map((x, i) => `${i ? "L" : "M"}${X(x[0]).toFixed(1)},${Y(x[1]).toFixed(1)}`).join("");
      const last = vs[vs.length - 1], chg = (last / vs[0] - 1) * 100;
      const marks = hot.filter((n) => n.ts >= t0 && n.ts <= t1).map((n) => {
        let i = c.findIndex((x) => x[0] > n.ts); i = i === -1 ? c.length - 1 : Math.max(0, i - 1);
        return `<circle cx="${X(c[i][0]).toFixed(1)}" cy="${Y(c[i][1]).toFixed(1)}" r="3" class="nc-dot"/>`;
      }).join("");
      const line = sel && sel >= t0 && sel <= t1 ? `<line x1="${X(sel).toFixed(1)}" x2="${X(sel).toFixed(1)}" y1="0" y2="${Hh}" class="nc-sel"/>` : "";
      const r = sel ? reaction(s.k, sel) : null;
      return `<div class="nc" data-coin="${s.k}" role="button" tabindex="0"><div class="nc-h"><span class="nc-n">${s.n}</span><span class="nc-v">${s.u || ""}${last.toLocaleString("ko-KR", { maximumFractionDigits: s.d, minimumFractionDigits: s.d })}</span>${pct(chg)}</div>
        <svg viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none" class="nc-svg"><path d="${path}" class="nc-line ${chg >= 0 ? "up" : "down"}"/>${marks}${line}</svg>
        <p class="nc-f">${sel ? `선택한 속보(${hm(sel)}) 이후 ${pct(r)}` : `최근 ${H}시간 · 누르면 1분봉 차트`}</p></div>`;
    }).join("");
  }

  function drawList() {
    const tags = ["주요", "전체", ...new Set(news.flatMap((n) => n.tags))];
    q("#newsChips").innerHTML = tags.map((t) => `<button class="chip${t === tag ? " on" : ""}" data-t="${esc(t)}">${t === "주요" ? "🔴 주요" : esc(t)}</button>`).join("");
    const list = news.filter((n) => tag === "전체" || (tag === "주요" ? n.hot : n.tags.includes(tag)));
    const ctas = funnel();
    q("#newsList").innerHTML = list.slice(0, shown).map((n, i) => {
      const rs = SERIES.map((s) => `${s.n} ${pct(reaction(s.k, n.ts))}`).join(" · ");
      const item = `<li class="nw${n.hot ? " hot" : ""}${sel === n.ts ? " sel" : ""}" data-ts="${n.ts}">
        <div class="nw-t"><b>${hm(n.ts)}</b><span>${ago(n.ts)}</span></div>
        <div class="nw-b"><p class="nw-txt">${n.hot ? "🔴 " : ""}${n.lang === "en" ? "🌐 " : ""}${esc(n.text)}</p>
          <p class="nw-m">${n.tags.map((t) => `<span class="nw-tag">${esc(t)}</span>`).join("")}<span class="nw-r">이후 ${rs}</span>
          <span class="nw-src">${esc(n.src)}${n.kind ? ` · ${esc(n.kind)}` : ""}</span></p></div></li>`;
      // 6건마다 오픈채팅·그룹 스터디로 이어지는 안내 한 칸
      const c = (i + 1) % 6 === 0 && ctas.length ? ctas[((i + 1) / 6 - 1) % ctas.length] : null;
      return item + (c ? `<li class="nw-cta"><p>${c.big}</p><a class="btn ${c.ext ? "btn-kakao" : "btn-gold"} btn-sm" href="${c.href}"${c.ext ? ' target="_blank" rel="noopener"' : ""}>${c.btn}</a></li>` : "");
    }).join("") || `<li class="empty">이 분류의 속보가 아직 없습니다.</li>`;
    q("#newsMore").hidden = list.length <= shown;
  }

  const full = !!q("#newsList");       // 메인 페이지(속보 칸 있음) / 다른 페이지(띠만)
  if (full) {
    q("#newsChips").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (!b) return; tag = b.dataset.t; shown = 15; drawList(); });
    q("#newsList").addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      const li = e.target.closest(".nw"); if (!li) return;
      const ts = +li.dataset.ts; sel = ts; if (window.trlCount) window.trlCount("news");
      drawCharts(); drawList();
      // 속보를 누르면 관련 지수의 1분봉 차트를 그 시각 기준으로 연다
      const n = news.find((x) => x.ts === ts) || { tags: [] };
      const coin = n.tags.includes("중동·유가") ? "xyz:CL" : (n.tags.includes("한국") || n.tags.includes("반도체")) ? "xyz:KR200" : "xyz:XYZ100";
      if (window.trlChart) window.trlChart.open({ coin, sel: ts, news });
    });
    q("#newsMore").addEventListener("click", () => { shown += 15; drawList(); });
    const openCard = (e) => { const c = e.target.closest(".nc[data-coin]"); if (c && window.trlChart) window.trlChart.open({ coin: c.dataset.coin, sel, news }); };
    q("#newsCharts").addEventListener("click", openCard);
    q("#newsCharts").addEventListener("keydown", (e) => { if (e.key === "Enter") openCard(e); });
    // 띠에서 속보를 누르면 속보 칸으로 내려가 그 속보를 선택
    document.addEventListener("click", (e) => {
      const a = e.target.closest(".tk-i"); if (!a) return;
      e.preventDefault(); sel = +a.dataset.ts; tag = "전체"; shown = Math.max(shown, 40);
      drawCharts(); drawList(); q("#news").scrollIntoView({ behavior: "smooth" });
    });
  }

  async function tickNews() { await loadNews(); if (full) { drawCharts(); drawList(); } }
  async function tickAll() { await Promise.all([loadNews(), full ? loadCandles() : null]); if (full) { drawCharts(); drawList(); } }
  tickAll();
  setInterval(tickNews, 60000);        // 속보 1분마다
  if (full) setInterval(async () => { await loadCandles(); drawCharts(); drawList(); }, 120000);   // 지수 2분마다
})();
