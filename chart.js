/* 1분봉 차트 창 — 속보 시각과 지수 반응을 크게 보기 (Hyperliquid candleSnapshot)
   window.trlChart.open({ coin: "xyz:XYZ100", sel: 속보시각ms|null, news: [...] }) */
"use strict";
(() => {
  const COINS = [
    { k: "xyz:XYZ100", n: "나스닥100", d: 1 }, { k: "xyz:SP500", n: "S&P500", d: 1 },
    { k: "xyz:KR200", n: "코스피200", d: 2 }, { k: "xyz:EWY", n: "EWY", d: 2, u: "$" },
    { k: "xyz:SKHX", n: "SK하이닉스", d: 2, u: "$" }, { k: "xyz:SMSN", n: "삼성전자", d: 2, u: "$" }, { k: "xyz:KORU", n: "KORU", d: 2, u: "$" }, { k: "xyz:SOXL", n: "SOXL", d: 2, u: "$" },
    { k: "xyz:CL", n: "WTI", d: 2, u: "$" }, { k: "xyz:BRENTOIL", n: "브렌트", d: 2, u: "$" },
    { k: "xyz:GOLD", n: "금", d: 1, u: "$" }, { k: "srv:USDKRW", n: "원/달러", d: 1 },
    { k: "srv:US10Y", n: "미 10년물 금리", d: 3, bp: true }, { k: "srv:DXY", n: "달러인덱스", d: 2 },
  ];
  // 변곡점 자산 코드(서버 news.json의 moves.asset)
  const CODE = { "xyz:XYZ100": "NQ", "xyz:SP500": "SP", "xyz:KR200": "K200", "xyz:CL": "WTI", "xyz:BRENTOIL": "BRENT", "xyz:GOLD": "GOLD", "srv:US10Y": "US10Y", "srv:DXY": "DXY" };
  const RANGES = [[60, "1시간"], [180, "3시간"], [360, "6시간"], [720, "12시간"], [1440, "24시간"]];
  const KAKAO = "https://invite.kakao.com/tc/p7OX5rMjd0";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const kst = (ms) => new Date(ms + (new Date().getTimezoneOffset() + 540) * 60000);
  const marketLocale = document.documentElement.dataset.marketLocale || "ko-KR";
  const ohlc = ({
    "en-US": ["O", "H", "L", "C"],
    "ja-JP": ["始", "高", "安", "終"],
    "zh-CN": ["开", "高", "低", "收"],
    "zh-TW": ["開", "高", "低", "收"],
  })[marketLocale] || ["시", "고", "저", "종"];
  const hm = (ms) => { const d = kst(ms); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const pctTxt = (v) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
  const cls = (v) => (v > 0.005 ? "c-up" : v < -0.005 ? "c-dn" : "c-fl");

  let st = { coin: COINS[0].k, range: 180, sel: null, bk: null, news: [], data: [], timer: null, hover: null, interval: 1 };
  // 11/21 운영자 "속보와 내용이 연결이 안 보인다 · 나스닥·유가·달러·채권·금 모두 연결": 선택한 속보 이후 다른 자산 반응을 한 줄로
  const LINKED = [["xyz:XYZ100", "나스닥100"], ["xyz:SP500", "S&P500"], ["xyz:KR200", "코스피200"], ["xyz:CL", "WTI"], ["xyz:GOLD", "금"], ["srv:USDKRW", "원/달러"], ["srv:DXY", "달러인덱스"], ["srv:US10Y", "미 10년물"]];
  const linked = { sel: null, at: 0, rows: {} };
  let root = null;
  let loadId = 0;

  function build() {
    root = document.createElement("div");
    root.className = "cm"; root.hidden = true;
    root.innerHTML = `<div class="cm-panel" role="dialog" aria-modal="true" aria-label="1분봉 차트">
      <div class="cm-head"><div class="cm-title" id="cmTitle"></div><button class="cm-x" id="cmX" aria-label="닫기">✕</button></div>
      <div class="cm-tabs" id="cmCoins"></div>
      <div class="cm-tabs sm" id="cmRanges"></div>
      <p class="cm-info" id="cmInfo"></p>
      <div class="cm-linked" id="cmLinked"></div>
      <div class="cm-chart" id="cmChart"><p class="fine" style="padding:20px">불러오는 중…</p></div>
      <div class="cm-tip" id="cmTip" hidden></div>
      <div class="cm-news" id="cmNews"></div>
    </div>`;
    document.body.appendChild(root);
    root.addEventListener("click", (e) => {
      if (e.target === root || e.target.id === "cmX") return close();
      const c = e.target.closest("[data-coin]"); if (c) { st.coin = c.dataset.coin; load(); }
      const r = e.target.closest("[data-range]"); if (r) { st.range = +r.dataset.range; load(); }
      const b = e.target.closest("[data-bk]");
      if (b) { const [f, t, sel] = b.dataset.bk.split(",").map(Number); st.bk = [f, t]; st.sel = sel; draw(); loadLinked(); return; }
      const n = e.target.closest("[data-sel]"); if (n) { st.sel = +n.dataset.sel; st.bk = null; fitRange(); load(); }
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
    const id = ++loadId, coin = st.coin;
    drawTabs();
    const end = Date.now(), start = end - st.range * 60000;
    const usePublished = () => {
      const code = coin.startsWith("srv:") ? coin.slice(4) : CODE[coin];
      const rows = (window.trlSeries?.[code] || []).filter(([t]) => t >= start);
      st.data = rows.map(([t, v]) => ({ t, o: v, h: v, l: v, c: v, v: 0 }));
      st.interval = 5;
      return draw();
    };
    loadLinked();
    if (coin.startsWith("srv:")) return usePublished();
    try {
      const r = await fetch("https://api.hyperliquid.xyz/info", { method: "POST", headers: { "Content-Type": "application/json" },
        signal: AbortSignal.timeout(8000),
        body: JSON.stringify({ type: "candleSnapshot", req: { coin, interval: "1m", startTime: start, endTime: end } }) });
      if (!r.ok) throw Error("Candle request failed");
      const d = await r.json();
      if (id !== loadId) return;
      if (!Array.isArray(d) || d.length < 2) return usePublished();
      st.data = d.map((c) => ({ t: c.t, o: +c.o, h: +c.h, l: +c.l, c: +c.c, v: +c.v }));
      st.interval = 1;
    } catch { if (id === loadId) usePublished(); return; }
    draw();
  }

  async function loadLinked() {
    const sel = st.sel;
    if (!sel || Date.now() - sel > 24 * 3600e3) return;
    if (linked.sel === sel && Date.now() - linked.at < 25000) return;
    if (linked.sel !== sel) linked.rows = {};
    linked.sel = sel; linked.at = Date.now();
    const from = sel - 10 * 60000, end = Date.now();
    await Promise.all(LINKED.map(async ([k]) => {
      if (k.startsWith("srv:")) { linked.rows[k] = window.trlSeries?.[k.slice(4)] || []; return; }
      try {
        const r = await fetch("https://api.hyperliquid.xyz/info", { method: "POST", headers: { "Content-Type": "application/json" }, signal: AbortSignal.timeout(8000),
          body: JSON.stringify({ type: "candleSnapshot", req: { coin: k, interval: sel < end - 12 * 3600e3 ? "5m" : "1m", startTime: from, endTime: end } }) });
        if (r.ok) linked.rows[k] = (await r.json()).map((c) => [c.t, +c.c]).filter(([t, v]) => t > 0 && v > 0);
      } catch { /* 이전 값 유지 */ }
    }));
    if (linked.sel === sel && root && !root.hidden) drawLinked();
  }
  function drawLinked() {
    const box = root && root.querySelector("#cmLinked"); if (!box) return;
    if (!st.sel || linked.sel !== st.sel) { box.innerHTML = ""; return; }
    const cells = LINKED.map(([k, n]) => {
      const rows = linked.rows[k] || [];
      let base = null; for (const [t, v] of rows) { if (t <= st.sel) base = v; else break; }
      if (base == null && rows.length && rows[0][0] - st.sel < 15 * 60000) base = rows[0][1];
      const last = rows.length ? rows[rows.length - 1][1] : null;
      if (base && rows[rows.length - 1][0] <= st.sel) return `<button class="chip cm-lk" data-coin="${k}">${n} <small>장 마감 · 이후 거래 없음</small></button>`;
      if (!base || !last) return `<button class="chip cm-lk" data-coin="${k}">${n} <small>자료 없음</small></button>`;
      const bp = k === "srv:US10Y", v = bp ? (last - base) * 100 : (last / base - 1) * 100;
      return `<button class="chip cm-lk${k === st.coin ? " on" : ""}" data-coin="${k}">${n} <b class="${cls(v)}">${bp ? `${v > 0 ? "+" : ""}${v.toFixed(1)}bp` : pctTxt(v)}</b></button>`;
    }).join("");
    box.innerHTML = `<p class="cm-nh">속보 ${hm(st.sel)} 이후 지금까지 · 자산별 변화 <small>누르면 그 자산 차트</small></p><div class="cm-tabs">${cells}</div>`;
  }

  function drawTabs() {
    root.querySelector("#cmCoins").innerHTML = COINS.map((c) => `<button class="chip${c.k === st.coin ? " on" : ""}" data-coin="${c.k}">${c.n}</button>`).join("");
    root.querySelector("#cmRanges").innerHTML = RANGES.map(([m, l]) => `<button class="chip${m === st.range ? " on" : ""}" data-range="${m}">${l}</button>`).join("");
  }

  let geo = null;
  function draw() {
    const box = root.querySelector("#cmChart"), D = st.data, meta = COINS.find((c) => c.k === st.coin);
    if (D.length < 2) {
      geo = null;
      root.querySelector("#cmTitle").textContent = meta.n;
      root.querySelector("#cmInfo").textContent = "";
      root.querySelector("#cmNews").textContent = "";
      root.querySelector("#cmTip").hidden = true;
      box.innerHTML = `<p class="fine" style="padding:20px">이 구간의 차트 데이터가 없습니다. 다른 시간 범위를 선택할 수 있습니다.</p>`;
      return;
    }
    const W = Math.max(300, box.clientWidth), H = window.innerWidth < 640 ? 300 : 420;
    const pad = { l: 8, r: 62, t: 46, b: 26 }, volH = H * 0.16;   // 위 46px = 속보 줄(크게 눌리게)
    const pw = W - pad.l - pad.r, ph = H - pad.t - pad.b - volH;
    const lo = Math.min(...D.map((x) => x.l)), hi = Math.max(...D.map((x) => x.h)), rg = hi - lo || 1;
    const t0 = D[0].t, t1 = D[D.length - 1].t, step = pw / D.length;
    const X = (t) => pad.l + ((t - t0) / (t1 - t0 || 1)) * (pw - step) + step / 2;
    const Y = (v) => pad.t + (1 - (v - lo) / rg) * ph;
    const vmax = Math.max(...D.map((x) => x.v)) || 1;
    geo = { X, Y, D, pad, W, H, ph, step, t0, t1, meta };
    const fmt = (v) => (meta.u || "") + v.toLocaleString(marketLocale, { minimumFractionDigits: meta.d, maximumFractionDigits: meta.d }) + (meta.bp ? "%" : "");
    const chgOf = (a, b) => (meta.bp ? (b - a) * 100 : (b / a - 1) * 100);
    const chgTxt = (v) => (meta.bp ? `${v > 0 ? "+" : ""}${v.toFixed(1)}bp` : pctTxt(v));
    const bw = Math.max(1, step * 0.65);
    let s = "";
    for (let i = 0; i <= 4; i++) {                                   // 가격 눈금
      const v = lo + (rg * i) / 4, y = Y(v);
      s += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y}" y2="${y}" class="cm-grid"/><text x="${W - pad.r + 6}" y="${y + 4}" class="cm-ax">${fmt(v)}</text>`;
    }
    const nt = Math.min(6, Math.floor(pw / 90));                     // 시간 눈금
    for (let i = 0; i <= nt; i++) { const t = t0 + ((t1 - t0) * i) / nt; s += `<text x="${X(t)}" y="${H - 8}" class="cm-ax" text-anchor="${i === 0 ? "start" : i === nt ? "end" : "middle"}">${hm(t)}</text>`; }
    if (st.interval === 5) {
      s += `<polyline fill="none" class="nc-line ${D.at(-1).c >= D[0].c ? "up" : "down"}" points="${D.map((x) => `${X(x.t)},${Y(x.c)}`).join(" ")}"/>`;
    } else D.forEach((x) => {                                       // 캔들 + 거래량
      const up = x.c >= x.o, cx = X(x.t), c = up ? "cm-up" : "cm-dn";
      s += `<line x1="${cx}" x2="${cx}" y1="${Y(x.h)}" y2="${Y(x.l)}" class="${c}"/>`;
      s += `<rect x="${cx - bw / 2}" y="${Y(Math.max(x.o, x.c))}" width="${bw}" height="${Math.max(1, Math.abs(Y(x.o) - Y(x.c)))}" class="${c} f"/>`;
      const vh = (x.v / vmax) * (volH - 6);
      s += `<rect x="${cx - bw / 2}" y="${H - pad.b - vh}" width="${bw}" height="${vh}" class="${c} v"/>`;
    });
    const inWin = st.news.filter((n) => n.ts >= t0 && n.ts <= t1 + 60000);
    // 변곡점 구간 색칠 + 그 관련 뉴스에만 빨간 점(이 자산 기준). 나머지 속보는 구간이 짧을 때만 회색 작은 점
    const myMoves = (window.trlMoves || []).filter((m) => m.asset === CODE[st.coin] && m.end >= t0 && m.start <= t1);
    const piv = new Set(myMoves.flatMap((m) => m.news || []));
    myMoves.forEach((m) => { const x0 = X(Math.max(m.start, t0)), x1 = X(Math.min(m.end, t1)); s += `<rect x="${x0}" y="${pad.t - 2}" width="${Math.max(3, x1 - x0)}" height="${ph + 4}" class="cm-zone ${m.move > 0 ? "up" : "dn"}"/>`; });
    // 속보 줄: 가까운 시각(18px 안)은 한 묶음 — 숫자로 건수, 🔴 변곡점 뉴스가 있으면 빨강. 묶음마다 가격선까지 점선으로 이어 '그때 가격'을 보인다
    const lane = pad.t - 22, gap = 18, bks = [];
    [...inWin].sort((a, b) => a.ts - b.ts).forEach((n) => {
      const x = X(Math.min(n.ts, t1)), last = bks[bks.length - 1];
      if (last && x - last.x0 < gap) { last.items.push(n); last.x1 = x; } else bks.push({ x0: x, x1: x, items: [n] });
    });
    const pxAt = (ts) => { let v = D[0].c; for (const x of D) { if (x.t <= ts) v = x.c; else break; } return v; };
    bks.forEach((b) => {
      const its = b.items, hot = its.some((n) => piv.has(n.ts)), imp = its.some((n) => n.hot);
      const best = its.find((n) => piv.has(n.ts)) || its.find((n) => n.hot) || its[its.length - 1];
      const cx = (b.x0 + b.x1) / 2, from = its[0].ts, to = its[its.length - 1].ts, on = st.bk ? st.bk[0] === from : its.some((n) => n.ts === st.sel);
      const py = Y(pxAt(best.ts)), r = its.length > 1 ? 9 : 7;
      s += `<line x1="${cx}" x2="${cx}" y1="${lane + r}" y2="${py}" class="cm-link${hot ? " hot" : ""}${on ? " on" : ""}"/><circle cx="${cx}" cy="${py}" r="3" class="cm-pt${hot ? " hot" : ""}"/>`;
      s += `<g class="cm-bk${hot ? " hot" : imp ? " imp" : ""}${on ? " on" : ""}" data-bk="${from},${to},${best.ts}"><rect x="${cx - gap / 2}" y="2" width="${gap}" height="${pad.t - 2}" fill="transparent"/>`
        + `<circle cx="${cx}" cy="${lane}" r="${r}"/>${its.length > 1 ? `<text x="${cx}" y="${lane + 4}" text-anchor="middle">${its.length > 9 ? "9+" : its.length}</text>` : ""}`
        + `<title>${esc(its.slice(0, 6).map((n) => `${piv.has(n.ts) ? "🔴 " : ""}${hm(n.ts)} ${n.text}`).join("\n") + (its.length > 6 ? `\n외 ${its.length - 6}건` : ""))}</title></g>`;
    });
    let info = "";
    const last = D[D.length - 1].c, first = D[0].o, chg = chgOf(first, last);
    if (st.sel && st.sel >= t0 - 60000) {                           // 선택한 속보: 세로선 + 기준 가격선 + 이후 변화
      let i = D.findIndex((x) => x.t > st.sel); i = i === -1 ? D.length - 1 : Math.max(0, i - 1);
      const base = D[i].c, after = D.slice(i), mx = Math.max(...after.map((x) => x.h)), mn = Math.min(...after.map((x) => x.l));
      const sx = X(D[i].t), by = Y(base);
      s += `<line x1="${sx}" x2="${sx}" y1="${pad.t - 4}" y2="${H - pad.b}" class="cm-sel"/><line x1="${sx}" x2="${W - pad.r}" y1="${by}" y2="${by}" class="cm-base"/>`;
      s += `<text x="${Math.min(sx + 4, W - pad.r - 70)}" y="${pad.t + 12}" class="cm-lbl">속보 ${hm(st.sel)}</text>`;
      const n = st.news.find((x) => x.ts === st.sel);
      const a1 = chgOf(base, last), a2 = chgOf(base, mx), a3 = chgOf(base, mn);
      info = `<b>${piv.has(st.sel) ? "🔴 " : ""}${hm(st.sel)}</b> ${n ? esc(n.text) : ""}${n ? ` <small>${esc(n.src || "")}</small>` : ""}<br>이후 <b class="${cls(a1)}">${chgTxt(a1)}</b> · 최고 <b class="${cls(a2)}">${chgTxt(a2)}</b> · 최저 <b class="${cls(a3)}">${chgTxt(a3)}</b>`;
      const mv = myMoves.find((m) => (m.news || []).includes(st.sel)) || myMoves.find((m) => st.sel >= m.start - 15 * 60000 && st.sel <= m.end);
      if (mv) {
        info += `<br><span class="cm-mv">변곡점 ${hm(mv.start)}–${hm(mv.end)} ${mv.kind === "cumulative" ? "누적 " : ""}${esc(mv.name)} ${mv.move > 0 ? "+" : ""}${mv.move}${mv.unit === "bp" ? "bp" : "%"}</span>`;
        const nt = (window.trlNotes || []).find((x) => x.assets.includes(mv.asset) && Date.parse(x.from) <= mv.end + 300000 && Date.parse(x.to) >= mv.start - 300000);
        if (nt) info += `<span class="cm-note"><b>💡 ${esc(nt.title)}</b> ${esc(nt.text)}</span>`;
      }
    } else {
      info = `최근 ${RANGES.find(([m]) => m === st.range)[1]} <b class="${cls(chg)}">${chgTxt(chg)}</b> · 색칠한 구간은 변곡점, 빨간 점(🔴)은 그 관련 뉴스입니다. 점을 누르면 그 뉴스 이후 변화를 보여 줍니다.`;
    }
    root.querySelector("#cmTitle").innerHTML = `${meta.n} <span>${fmt(last)}</span> <b class="${cls(chg)}">${chgTxt(chg)}</b> <small>${st.interval === 5 ? "5분 간격" : "1분봉"}</small>`;
    root.querySelector("#cmInfo").innerHTML = info;
    box.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${s}<g id="cmHover"></g></svg>`;
    // 차트 구간의 속보 목록(누르면 선택)
    const inBk = st.bk ? inWin.filter((n) => n.ts >= st.bk[0] && n.ts <= st.bk[1]) : [];
    const ordered = [...inWin].sort((a, b) => b.ts - a.ts);
    root.querySelector("#cmNews").innerHTML = inWin.length ? `<p class="cm-nh">${inBk.length ? `선택한 ${hm(st.bk[0])}${hm(st.bk[1]) !== hm(st.bk[0]) ? "–" + hm(st.bk[1]) : ""} 속보 ${inBk.length}건 · ` : ""}이 구간의 속보 ${inWin.length}건${piv.size ? ` · 🔴 변곡점 관련 뉴스 ${inWin.filter((n) => piv.has(n.ts)).length}건` : ""} <small>차트 점을 누르면 해당 시각을 선택합니다</small></p>` + ordered.slice(0, 60).map((n) =>
      `<button class="cm-ni${n.ts === st.sel ? " on" : ""}${piv.has(n.ts) ? " hot" : ""}" data-sel="${n.ts}"><b>${piv.has(n.ts) ? "🔴 " : ""}${hm(n.ts)}</b> ${esc(n.text)} <small>${esc(n.src || "")}</small></button>`).join("") : "";
    drawLinked();
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
    const f = (v) => (meta.u || "") + v.toLocaleString(marketLocale, { minimumFractionDigits: meta.d, maximumFractionDigits: meta.d }) + (meta.bp ? "%" : "");
    const prev = D[best - 1] ? D[best - 1].c : x.o, ch = (x.c / prev - 1) * 100;
    let since = "";
    if (st.sel) { let i = D.findIndex((y) => y.t > st.sel); i = i === -1 ? D.length - 1 : Math.max(0, i - 1); if (best >= i) since = `<br>속보 이후 <b class="${cls((x.c / D[i].c - 1) * 100)}">${pctTxt((x.c / D[i].c - 1) * 100)}</b>`; }
    const price = st.interval === 5 ? f(x.c) : [x.o, x.h, x.l, x.c].map((value, i) => `${ohlc[i]} ${f(value)}`).join(" · ");
    tip.innerHTML = `<b>${hm(x.t)}</b> ${price} <b class="${cls(ch)}">${pctTxt(ch)}</b>${since}`;
    tip.hidden = false;
  }

  function open(o) {
    if (!root) build();
    if (o.coin && !COINS.find((c) => c.k === o.coin)) COINS.push({ k: o.coin, n: o.name || o.coin.replace("xyz:", ""), d: 2, u: "$" });   // 화제 종목 등
    st.coin = o.coin || st.coin; st.sel = o.sel || null; st.bk = null; st.news = o.news || st.news;
    if (st.sel) fitRange(); else st.range = 180;
    root.hidden = false; document.body.style.overflow = "hidden";
    load();
    clearInterval(st.timer); st.timer = setInterval(load, 30000);   // 열려 있는 동안 30초마다
    if (window.trlCount) window.trlCount("chart");
  }
  function close() { root.hidden = true; document.body.style.overflow = ""; clearInterval(st.timer); }
  window.trlChart = { open, close };
})();
