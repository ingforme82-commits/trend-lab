/* 1분봉 차트 창 — 속보 시각과 지수 반응을 크게 보기 (Hyperliquid candleSnapshot)
   window.trlChart.open({ coin: "xyz:XYZ100", sel: 속보시각ms|null, news: [...] }) */
"use strict";
(() => {
  const COINS = [
    { k: "xyz:XYZ100", n: "나스닥100", d: 1 }, { k: "xyz:SP500", n: "S&P500", d: 1 },
    { k: "xyz:KR200", n: "코스피200", d: 2 }, { k: "xyz:EWY", n: "EWY", d: 2, u: "$" },
    { k: "xyz:SKHX", n: "SK하이닉스", d: 2, u: "$" }, { k: "xyz:SMSN", n: "삼성전자", d: 2, u: "$" },
    { k: "xyz:CL", n: "WTI", d: 2, u: "$" }, { k: "xyz:BRENTOIL", n: "브렌트", d: 2, u: "$" },
    { k: "xyz:GOLD", n: "금", d: 1, u: "$" }, { k: "xyz:KRW", n: "원/달러", d: 1 },
  ];
  const RANGES = [[60, "1시간"], [180, "3시간"], [360, "6시간"], [720, "12시간"], [1440, "24시간"]];
  const KAKAO = "https://invite.kakao.com/tc/p7OX5rMjd0";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const kst = (ms) => new Date(ms + (new Date().getTimezoneOffset() + 540) * 60000);
  const hm = (ms) => { const d = kst(ms); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const pctTxt = (v) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
  const cls = (v) => (v > 0.005 ? "c-up" : v < -0.005 ? "c-dn" : "c-fl");

  let st = { coin: COINS[0].k, range: 180, sel: null, news: [], data: [], timer: null, hover: null };
  let root = null;

  function build() {
    root = document.createElement("div");
    root.className = "cm"; root.hidden = true;
    root.innerHTML = `<div class="cm-panel" role="dialog" aria-modal="true" aria-label="1분봉 차트">
      <div class="cm-head"><div class="cm-title" id="cmTitle"></div><button class="cm-x" id="cmX" aria-label="닫기">✕</button></div>
      <div class="cm-tabs" id="cmCoins"></div>
      <div class="cm-tabs sm" id="cmRanges"></div>
      <p class="cm-info" id="cmInfo"></p>
      <div class="cm-chart" id="cmChart"><p class="fine" style="padding:20px">불러오는 중…</p></div>
      <div class="cm-tip" id="cmTip" hidden></div>
      <div class="cm-news" id="cmNews"></div>
      <p class="fine cm-src">Hyperliquid 24시간 선물 1분봉(참고용) · 점은 속보 시각 · 인과관계를 뜻하지 않으며 매매 권유가 아닙니다.</p>
    </div>`;
    document.body.appendChild(root);
    root.addEventListener("click", (e) => {
      if (e.target === root || e.target.id === "cmX") return close();
      const c = e.target.closest("[data-coin]"); if (c) { st.coin = c.dataset.coin; load(); }
      const r = e.target.closest("[data-range]"); if (r) { st.range = +r.dataset.range; load(); }
      const n = e.target.closest("[data-sel]"); if (n) { st.sel = +n.dataset.sel; fitRange(); load(); }
    });
    document.addEventListener("keydown", (e) => { if (!root.hidden && e.key === "Escape") close(); });
    window.addEventListener("resize", () => { if (!root.hidden) draw(); });
    const ch = root.querySelector("#cmChart");
    const move = (x) => { st.hover = x; drawHover(); };
    ch.addEventListener("pointermove", (e) => move(e.clientX - ch.getBoundingClientRect().left));
    ch.addEventListener("pointerdown", (e) => move(e.clientX - ch.getBoundingClientRect().left));
    ch.addEventListener("pointerleave", () => { st.hover = null; drawHover(); });
  }

  function fitRange() {
    if (!st.sel) return;
    const need = (Date.now() - st.sel) / 60000 + 20;            // 속보 20분 전부터 보이게
    st.range = (RANGES.find(([m]) => m >= need) || RANGES[RANGES.length - 1])[0];
  }

  async function load() {
    drawTabs();
    const end = Date.now(), start = end - st.range * 60000;
    try {
      const r = await fetch("https://api.hyperliquid.xyz/info", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "candleSnapshot", req: { coin: st.coin, interval: "1m", startTime: start, endTime: end } }) });
      const d = await r.json();
      st.data = d.map((c) => ({ t: c.t, o: +c.o, h: +c.h, l: +c.l, c: +c.c, v: +c.v }));
    } catch { st.data = []; }
    draw();
  }

  function drawTabs() {
    root.querySelector("#cmCoins").innerHTML = COINS.map((c) => `<button class="chip${c.k === st.coin ? " on" : ""}" data-coin="${c.k}">${c.n}</button>`).join("");
    root.querySelector("#cmRanges").innerHTML = RANGES.map(([m, l]) => `<button class="chip${m === st.range ? " on" : ""}" data-range="${m}">${l}</button>`).join("");
  }

  let geo = null;
  function draw() {
    const box = root.querySelector("#cmChart"), D = st.data, meta = COINS.find((c) => c.k === st.coin);
    if (D.length < 2) { box.innerHTML = `<p class="fine" style="padding:20px">차트 데이터를 불러오지 못했습니다.</p>`; return; }
    const W = Math.max(300, box.clientWidth), H = window.innerWidth < 640 ? 300 : 420;
    const pad = { l: 8, r: 62, t: 22, b: 26 }, volH = H * 0.16;
    const pw = W - pad.l - pad.r, ph = H - pad.t - pad.b - volH;
    const lo = Math.min(...D.map((x) => x.l)), hi = Math.max(...D.map((x) => x.h)), rg = hi - lo || 1;
    const t0 = D[0].t, t1 = D[D.length - 1].t, step = pw / D.length;
    const X = (t) => pad.l + ((t - t0) / (t1 - t0 || 1)) * (pw - step) + step / 2;
    const Y = (v) => pad.t + (1 - (v - lo) / rg) * ph;
    const vmax = Math.max(...D.map((x) => x.v)) || 1;
    geo = { X, Y, D, pad, W, H, ph, step, t0, t1, meta };
    const fmt = (v) => (meta.u || "") + v.toLocaleString("ko-KR", { minimumFractionDigits: meta.d, maximumFractionDigits: meta.d });
    const bw = Math.max(1, step * 0.65);
    let s = "";
    for (let i = 0; i <= 4; i++) {                                   // 가격 눈금
      const v = lo + (rg * i) / 4, y = Y(v);
      s += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y}" y2="${y}" class="cm-grid"/><text x="${W - pad.r + 6}" y="${y + 4}" class="cm-ax">${fmt(v)}</text>`;
    }
    const nt = Math.min(6, Math.floor(pw / 90));                     // 시간 눈금
    for (let i = 0; i <= nt; i++) { const t = t0 + ((t1 - t0) * i) / nt; s += `<text x="${X(t)}" y="${H - 8}" class="cm-ax" text-anchor="${i === 0 ? "start" : i === nt ? "end" : "middle"}">${hm(t)}</text>`; }
    D.forEach((x) => {                                               // 캔들 + 거래량
      const up = x.c >= x.o, cx = X(x.t), c = up ? "cm-up" : "cm-dn";
      s += `<line x1="${cx}" x2="${cx}" y1="${Y(x.h)}" y2="${Y(x.l)}" class="${c}"/>`;
      s += `<rect x="${cx - bw / 2}" y="${Y(Math.max(x.o, x.c))}" width="${bw}" height="${Math.max(1, Math.abs(Y(x.o) - Y(x.c)))}" class="${c} f"/>`;
      const vh = (x.v / vmax) * (volH - 6);
      s += `<rect x="${cx - bw / 2}" y="${H - pad.b - vh}" width="${bw}" height="${vh}" class="${c} v"/>`;
    });
    const inWin = st.news.filter((n) => n.ts >= t0 && n.ts <= t1 + 60000);
    // 점이 너무 많으면 주요 속보·선택한 속보만 찍는다(1시간 구간은 모두)
    const dots = st.range <= 60 || inWin.length <= 30 ? inWin : inWin.filter((n) => n.hot || n.ts === st.sel);
    dots.forEach((n) => { s += `<circle cx="${X(Math.min(n.ts, t1))}" cy="${pad.t - 10}" r="${n.hot ? 4.5 : 3}" class="cm-dot${n.hot ? " hot" : ""}" data-sel="${n.ts}"><title>${esc(hm(n.ts) + " " + n.text)}</title></circle>`; });
    let info = "";
    const last = D[D.length - 1].c, first = D[0].o, chg = (last / first - 1) * 100;
    if (st.sel && st.sel >= t0 - 60000) {                           // 선택한 속보: 세로선 + 기준 가격선 + 이후 변화
      let i = D.findIndex((x) => x.t > st.sel); i = i === -1 ? D.length - 1 : Math.max(0, i - 1);
      const base = D[i].c, after = D.slice(i), mx = Math.max(...after.map((x) => x.h)), mn = Math.min(...after.map((x) => x.l));
      const sx = X(D[i].t), by = Y(base);
      s += `<line x1="${sx}" x2="${sx}" y1="${pad.t - 4}" y2="${H - pad.b}" class="cm-sel"/><line x1="${sx}" x2="${W - pad.r}" y1="${by}" y2="${by}" class="cm-base"/>`;
      s += `<text x="${Math.min(sx + 4, W - pad.r - 70)}" y="${pad.t + 12}" class="cm-lbl">속보 ${hm(st.sel)}</text>`;
      const n = st.news.find((x) => x.ts === st.sel);
      info = `<b>${hm(st.sel)}</b> ${n ? esc(n.text) : ""}<br>이후 <b class="${cls((last / base - 1) * 100)}">${pctTxt((last / base - 1) * 100)}</b> · 최고 <b class="${cls((mx / base - 1) * 100)}">${pctTxt((mx / base - 1) * 100)}</b> · 최저 <b class="${cls((mn / base - 1) * 100)}">${pctTxt((mn / base - 1) * 100)}</b>`;
    } else {
      info = `최근 ${RANGES.find(([m]) => m === st.range)[1]} <b class="${cls(chg)}">${pctTxt(chg)}</b> · 위쪽 점(●)을 누르면 그 속보 이후 변화를 보여 줍니다.`;
    }
    root.querySelector("#cmTitle").innerHTML = `${meta.n} <span>${fmt(last)}</span> <b class="${cls(chg)}">${pctTxt(chg)}</b> <small>1분봉</small>`;
    root.querySelector("#cmInfo").innerHTML = info;
    box.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${s}<g id="cmHover"></g></svg>`;
    // 차트 구간의 속보 목록(누르면 선택)
    root.querySelector("#cmNews").innerHTML = inWin.length ? `<p class="cm-nh">이 구간의 속보 ${inWin.length}건</p>` + inWin.slice(0, 30).map((n) =>
      `<button class="cm-ni${n.ts === st.sel ? " on" : ""}${n.hot ? " hot" : ""}" data-sel="${n.ts}"><b>${hm(n.ts)}</b> ${esc(n.text)}</button>`).join("") : "";
    drawHover();
  }

  function drawHover() {
    const g = root && root.querySelector("#cmHover"), tip = root && root.querySelector("#cmTip");
    if (!g || !geo) return;
    if (st.hover == null) { g.innerHTML = ""; tip.hidden = true; return; }
    const { D, X, Y, pad, H, W, meta } = geo;
    let best = 0, bd = Infinity;
    D.forEach((x, i) => { const d = Math.abs(X(x.t) - st.hover); if (d < bd) { bd = d; best = i; } });
    const x = D[best], cx = X(x.t);
    g.innerHTML = `<line x1="${cx}" x2="${cx}" y1="${pad.t}" y2="${H - pad.b}" class="cm-cross"/><line x1="${pad.l}" x2="${W - pad.r}" y1="${Y(x.c)}" y2="${Y(x.c)}" class="cm-cross"/>`;
    const f = (v) => v.toLocaleString("ko-KR", { minimumFractionDigits: meta.d, maximumFractionDigits: meta.d });
    const prev = D[best - 1] ? D[best - 1].c : x.o, ch = (x.c / prev - 1) * 100;
    let since = "";
    if (st.sel) { let i = D.findIndex((y) => y.t > st.sel); i = i === -1 ? D.length - 1 : Math.max(0, i - 1); if (best >= i) since = `<br>속보 이후 <b class="${cls((x.c / D[i].c - 1) * 100)}">${pctTxt((x.c / D[i].c - 1) * 100)}</b>`; }
    tip.innerHTML = `<b>${hm(x.t)}</b> 시 ${f(x.o)} · 고 ${f(x.h)} · 저 ${f(x.l)} · 종 ${f(x.c)} <b class="${cls(ch)}">${pctTxt(ch)}</b>${since}`;
    tip.hidden = false;
  }

  function open(o) {
    if (!root) build();
    st.coin = o.coin || st.coin; st.sel = o.sel || null; st.news = o.news || st.news;
    if (st.sel) fitRange(); else st.range = 180;
    root.hidden = false; document.body.style.overflow = "hidden";
    load();
    clearInterval(st.timer); st.timer = setInterval(load, 30000);   // 열려 있는 동안 30초마다
    if (window.trlCount) window.trlCount("chart");
  }
  function close() { root.hidden = true; document.body.style.overflow = ""; clearInterval(st.timer); }
  window.trlChart = { open, close };
})();
