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

  async function loadNews() {
    try {
      const r = await fetch(`${NEWS_URL}?t=${Math.floor(Date.now() / 60000)}`);
      const j = await r.json();
      news = j.items || [];
      q("#newsStamp").textContent = `속보 갱신 ${hm(j.updated)} KST · ${ago(j.updated)}`;
    } catch { q("#newsStamp").textContent = "속보를 불러오지 못했습니다."; }
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
      return `<div class="nc"><div class="nc-h"><span class="nc-n">${s.n}</span><span class="nc-v">${s.u || ""}${last.toLocaleString("ko-KR", { maximumFractionDigits: s.d, minimumFractionDigits: s.d })}</span>${pct(chg)}</div>
        <svg viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none" class="nc-svg"><path d="${path}" class="nc-line ${chg >= 0 ? "up" : "down"}"/>${marks}${line}</svg>
        <p class="nc-f">${sel ? `선택한 속보(${hm(sel)}) 이후 ${pct(r)}` : `최근 ${H}시간 · 점은 주요 속보 시각`}</p></div>`;
    }).join("");
  }

  function drawList() {
    const tags = ["주요", "전체", ...new Set(news.flatMap((n) => n.tags))];
    q("#newsChips").innerHTML = tags.map((t) => `<button class="chip${t === tag ? " on" : ""}" data-t="${esc(t)}">${t === "주요" ? "🔴 주요" : esc(t)}</button>`).join("");
    const list = news.filter((n) => tag === "전체" || (tag === "주요" ? n.hot : n.tags.includes(tag)));
    q("#newsList").innerHTML = list.slice(0, shown).map((n) => {
      const rs = SERIES.map((s) => `${s.n} ${pct(reaction(s.k, n.ts))}`).join(" · ");
      return `<li class="nw${n.hot ? " hot" : ""}${sel === n.ts ? " sel" : ""}" data-ts="${n.ts}">
        <div class="nw-t"><b>${hm(n.ts)}</b><span>${ago(n.ts)}</span></div>
        <div class="nw-b"><p class="nw-txt">${n.hot ? "🔴 " : ""}${esc(n.text)}</p>
          <p class="nw-m">${n.tags.map((t) => `<span class="nw-tag">${esc(t)}</span>`).join("")}<span class="nw-r">이후 ${rs}</span>
          <a href="${esc(n.url)}" target="_blank" rel="noopener" class="nw-src">${esc(n.src)} ↗</a></p></div></li>`;
    }).join("") || `<li class="empty">이 분류의 속보가 아직 없습니다.</li>`;
    q("#newsMore").hidden = list.length <= shown;
  }

  q("#newsChips").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (!b) return; tag = b.dataset.t; shown = 15; drawList(); });
  q("#newsList").addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const li = e.target.closest(".nw"); if (!li) return;
    const ts = +li.dataset.ts; sel = sel === ts ? null : ts;
    drawCharts(); drawList();
    if (sel && window.innerWidth < 760) q("#newsCharts").scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  q("#newsMore").addEventListener("click", () => { shown += 15; drawList(); });

  async function tick() { await Promise.all([loadNews(), loadCandles()]); drawCharts(); drawList(); }
  tick();
  setInterval(tick, 120000);          // 2분마다
})();
