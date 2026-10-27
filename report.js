/* 🔎 시황 리포트 만들기 — 방문자가 입력한 주제(유가·반도체·테슬라·금리…)로 사이트의 실시간 데이터를
   블로그 글 형식으로 정리해 보여 준다. AI가 문장을 지어내지 않는다: 가격·변곡점·속보·섹터·운영자 해석 노트·
   블로그 분석 글·체크포인트를 모아 사실과 수치로만 구성한다(해석·전망·매매 권유 없음). */
"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  if (!$("#rqForm")) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const kst = (ms) => new Date(ms + (new Date().getTimezoneOffset() + 540) * 60000);
  const hm = (ms) => { const d = kst(ms); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const md = (ms) => { const d = kst(ms); return `${d.getMonth() + 1}/${d.getDate()}`; };
  const sg = (v, u = "%") => `${v > 0 ? "+" : ""}${(+v).toFixed(2)}${u}`;
  const cls = (v) => (v > 0.005 ? "c-up" : v < -0.005 ? "c-dn" : "c-fl");

  // 주제 → 관련 자산·뉴스 분류·섹터
  const TOPICS = [
    { n: "유가·중동", rx: /유가|원유|wti|브렌트|oil|이란|중동|호르무즈|opec|오펙|사우디|후티|이스라엘/i, assets: ["WTI", "BRENT"], tags: ["중동·유가"] },
    { n: "반도체", rx: /반도체|하이닉스|삼성전자|엔비디아|마이크론|hbm|메모리|tsmc|soxl|칩/i, assets: ["NQ", "K200"], tags: ["반도체"], sectors: ["미국 반도체", "한국 반도체"] },
    { n: "금리·달러", rx: /금리|연준|fomc|fed|국채|채권|파월|인플레|물가|pce|cpi|달러|환율/i, assets: ["US10Y", "DXY"], tags: ["연준·금리"] },
    { n: "한국 증시", rx: /코스피|국장|한국|kospi|코스닥|원화/i, assets: ["K200"], tags: ["한국"] },
    { n: "미국 증시", rx: /나스닥|미국장|미장|s&p|다우|뉴욕/i, assets: ["NQ"], tags: ["지수", "AI·빅테크"] },
    { n: "AI·빅테크", rx: /\bai\b|인공지능|앤트로픽|오픈ai|openai|데이터센터|빅테크|마이크로소프트|구글|메타|애플|아마존/i, assets: ["NQ"], tags: ["AI·빅테크"] },
    { n: "원전", rx: /원전|원자력|smr|우라늄|두산에너빌리티/i, assets: ["K200"], tags: ["원전"], sectors: ["원전", "미국 원전·SMR"] },
    { n: "방산", rx: /방산|방위|무기|한화에어로|현대로템/i, assets: ["K200"], tags: ["방산"], sectors: ["방산"] },
    { n: "2차전지", rx: /2차전지|이차전지|배터리|리튬|에코프로|lg에너지/i, assets: ["K200"], tags: ["2차전지"], sectors: ["2차전지"] },
    { n: "조선", rx: /조선|선박|lng선|한화오션|hd현대/i, assets: ["K200"], tags: ["조선"], sectors: ["조선"] },
    { n: "사이버보안", rx: /보안|해킹|사이버|크라우드스트라이크|팔로알토|지스케일러/i, assets: ["NQ"], tags: ["사이버보안"], sectors: ["사이버보안"] },
    { n: "금", rx: /^금$|금값|금 가격|gold/i, assets: ["GOLD"], tags: [] },
    { n: "코인", rx: /코인|비트코인|암호화폐|crypto|이더리움/i, assets: [], tags: ["코인"] },
  ];
  const ASSET = {
    NQ: { n: "나스닥100", hl: "xyz:XYZ100", d: 0 }, K200: { n: "코스피200", hl: "xyz:KR200", d: 2 },
    WTI: { n: "WTI", hl: "xyz:CL", d: 2, u: "$" }, BRENT: { n: "브렌트", hl: "xyz:BRENTOIL", d: 2, u: "$" },
    GOLD: { n: "금", hl: "xyz:GOLD", d: 1, u: "$" }, US10Y: { n: "미 10년물 금리", srv: "US10Y", bp: true }, DXY: { n: "달러인덱스", srv: "DXY" },
  };
  const SUGGEST = ["유가", "반도체", "테슬라", "금리", "코스피", "원전", "방산", "2차전지", "조선", "보안", "AI"];

  $("#rqSug").innerHTML = SUGGEST.map((s) => `<button type="button" class="rq-chip" data-q="${s}">${s}</button>`).join("");
  $("#rqSug").addEventListener("click", (e) => { const b = e.target.closest("[data-q]"); if (b) { $("#rqInput").value = b.dataset.q; run(b.dataset.q); } });
  $("#rqForm").addEventListener("submit", (e) => { e.preventDefault(); run($("#rqInput").value.trim()); });
  $("#rqInput").addEventListener("input", (e) => {           // 입력하는 동안 블로그 글 목록도 함께 검색
    window.trlFeedQuery = e.target.value.trim();
    if (window.trlRenderFeed) window.trlRenderFeed();
  });

  // 주소에 ?q=유가 가 있으면 데이터가 준비되는 대로 바로 리포트(공유 링크용)
  const q0 = new URLSearchParams(location.search).get("q");
  if (q0) {
    $("#rqInput").value = q0;
    let tries = 0;
    const wait = setInterval(() => {
      if ((window.trlNews && window.trlNews.length && window.trlPosts) || ++tries > 40) { clearInterval(wait); run(q0); }
    }, 250);
  }

  async function hlCtx() {
    try {
      const r = await fetch("https://api.hyperliquid.xyz/info", { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"type":"metaAndAssetCtxs","dex":"xyz"}' });
      const [m, c] = await r.json();
      return Object.fromEntries(m.universe.map((a, i) => [a.name, c[i]]));
    } catch { return {}; }
  }

  async function run(q) {
    if (!q) return;
    window.trlFeedQuery = q; if (window.trlRenderFeed) window.trlRenderFeed();
    if (window.trlCount) window.trlCount("report");
    const out = $("#rqOut");
    out.innerHTML = `<p class="dim">리포트를 만드는 중…</p>`;
    const news = window.trlNews || [], moves = window.trlMoves || [], sectors = window.trlSectors || [], notes = window.trlNotes || [];
    const spot = window.trlSpot || [], trend = window.trlTrend || [], series = window.trlSeries || {};
    const words = q.split(/[\s,]+/).filter((w) => w.length >= 1).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    let qrx = new RegExp(words.join("|") || "$^", "i");
    const topics = TOPICS.filter((t) => t.rx.test(q));
    // 종목 이름(화제 종목·많이 나온 종목)과 맞으면 그 종목 사전으로 넓혀 찾는다
    const stock = [...spot, ...trend].find((s) => qrx.test(s.name) || (s.kw && new RegExp(s.kw, "i").test(q)));
    if (stock && stock.kw) { try { qrx = new RegExp(`${qrx.source}|${stock.kw}`, "i"); } catch { /* 그대로 */ } }
    const assets = [...new Set(topics.flatMap((t) => t.assets || []))];
    if (!assets.length) assets.push("NQ", "K200");
    const tags = new Set(topics.flatMap((t) => t.tags || []));
    const secNames = new Set(topics.flatMap((t) => t.sectors || []));
    const now = Date.now();
    const textOf = (n) => `${n.text} ${n.orig || ""} ${n.sub || ""}`;
    const rel = news.filter((n) => now - n.ts < 30 * 3600e3 && (qrx.test(textOf(n)) || (n.tags || []).some((t) => tags.has(t))))
      .sort((a, b) => (b.pivot ? 1 : 0) - (a.pivot ? 1 : 0) || b.ts - a.ts);
    const relMoves = moves.filter((m) => now - m.start < 24 * 3600e3 && (assets.includes(m.asset) || (m.items || []).some((it) => qrx.test(it.text))));
    const relSec = sectors.filter((s) => secNames.has(s.name) || s.rows.some((r) => qrx.test(r.name)));
    const relNotes = notes.filter((nt) => nt.assets.some((a) => assets.includes(a)) || qrx.test(nt.title + nt.text)).slice(0, 3);
    let posts = window.trlPosts || [];
    const relPosts = posts.filter((p) => qrx.test(`${p.title} ${p.summary} ${(p.tags || []).join(" ")}`) || topics.some((t) => t.rx.test(p.title))).slice(0, 5);
    let checks = [];
    try { checks = await (await fetch(`data/checkpoints.json?t=${Math.floor(now / 600000)}`)).json(); } catch { /* 없음 */ }
    const today = `${kst(now).getFullYear()}-${String(kst(now).getMonth() + 1).padStart(2, "0")}-${String(kst(now).getDate()).padStart(2, "0")}`;
    checks = checks.filter((c) => c.date >= today);
    const relChecks = (checks.filter((c) => qrx.test(c.title + " " + (c.note || "")) || topics.some((t) => t.rx.test(c.title + " " + (c.note || "")))).length
      ? checks.filter((c) => qrx.test(c.title + " " + (c.note || "")) || topics.some((t) => t.rx.test(c.title + " " + (c.note || "")))) : checks).slice(0, 4);

    // 가격
    const ctx = await hlCtx();
    const prices = assets.map((a) => {
      const A = ASSET[a]; if (!A) return null;
      if (A.hl && ctx[A.hl]) { const px = +ctx[A.hl].markPx, prev = +ctx[A.hl].prevDayPx; return { n: A.n, txt: `${A.u || ""}${px.toLocaleString("ko-KR", { maximumFractionDigits: A.d, minimumFractionDigits: A.d })}`, chg: (px / prev - 1) * 100, unit: "%" }; }
      const s = series[A.srv]; if (s && s.length > 1) { const last = s[s.length - 1][1], first = s[0][1]; return { n: A.n, txt: `${last}${A.bp ? "%" : ""}`, chg: A.bp ? (last - first) * 100 : (last / first - 1) * 100, unit: A.bp ? "bp" : "%" }; }
      return null;
    }).filter(Boolean);
    if (stock && stock.hl && ctx[stock.hl]) { const px = +ctx[stock.hl].markPx, prev = +ctx[stock.hl].prevDayPx; prices.unshift({ n: stock.name, txt: `$${px.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}`, chg: (px / prev - 1) * 100, unit: "%" }); }

    // 글 구성
    const label = topics.map((t) => t.n).concat(stock && !topics.length ? [stock.name] : []).join(" · ") || q;
    const big = relMoves.slice().sort((a, b) => b.ratio - a.ratio)[0];
    const sum = [
      prices.length ? prices.map((p) => `${p.n} ${p.txt}(${sg(p.chg, p.unit === "bp" ? "bp" : "%")}, 24시간)`).join(", ") + "입니다." : "",
      `최근 30시간 '${esc(q)}' 관련 속보는 ${rel.length}건${rel.filter((n) => n.pivot).length ? `, 그중 변곡점 직전 뉴스는 ${rel.filter((n) => n.pivot).length}건` : ""}입니다.`,
      big ? `가장 크게 움직인 순간은 ${hm(big.start)}–${hm(big.end)} ${big.name} ${big.move > 0 ? "+" : ""}${big.move}${big.unit === "bp" ? "bp" : "%"}였습니다.` : "최근 24시간 관련 자산에 평소보다 크게 움직인 구간은 없었습니다.",
      relSec.length ? relSec.map((s) => `${s.name} 섹터 평균 ${sg(s.avg)}`).join(", ") + "." : "",
    ].filter(Boolean).join(" ");
    const title = `[자동 시황 정리] ${label} — ${md(now)} ${hm(now)} KST 기준`;
    const tagsLine = ["#시황", ...new Set([...topics.map((t) => t.n.replace(/·/g, "")), ...(stock ? [stock.name] : [])])].map((t) => t.startsWith("#") ? t : `#${t}`).join(" ");

    const H = [];
    H.push(`<h3 class="rp-title">${esc(title)}</h3><p class="rp-tags">${esc(tagsLine)}</p>`);
    H.push(`<div class="rp-box sum"><b>📌 한 줄 요약</b><p>${sum}</p></div>`);
    if (prices.length) H.push(`<h4>📊 1. 지금 숫자</h4><ul>${prices.map((p) => `<li>${esc(p.n)} <b>${p.txt}</b> <b class="${cls(p.chg)}">${sg(p.chg, p.unit === "bp" ? "bp" : "%")}</b> <small>(24시간)</small></li>`).join("")}</ul>`);
    H.push(`<h4>📍 2. 변곡점(평소보다 크게 움직인 순간)</h4>` + (relMoves.length ? `<ul>${relMoves.slice(0, 5).map((m) => `<li><b class="${m.move > 0 ? "c-up" : "c-dn"}">${hm(m.start)}–${hm(m.end)} ${esc(m.name)} ${m.move > 0 ? "+" : ""}${m.move}${m.unit === "bp" ? "bp" : "%"}</b>${(m.items || []).length ? `<br>직전 뉴스: ${m.items.map((it) => `🔴 ${hm(it.ts)} ${esc(it.text)} <small>(${esc(it.osrc ? it.osrc + " · " + it.src + " 경유" : it.src)})</small>`).join(" / ")}` : `<br><small>직전 관련 뉴스 없음</small>`}</li>`).join("")}</ul>` : `<p class="dim">최근 24시간 관련 자산의 변곡점이 없습니다.</p>`));
    H.push(`<h4>📰 3. 관련 속보 타임라인 <small>(최근 30시간, 변곡점 뉴스 먼저)</small></h4>` + (rel.length ? `<ul>${rel.slice(0, 12).map((n) => `<li>${n.pivot ? "🔴 " : ""}<b>${md(n.ts)} ${hm(n.ts)}</b> ${n.lang === "en" ? "🌐 " : ""}${esc(n.text)} <small>(${esc(n.osrc ? n.osrc + " · " + n.src + " 경유" : n.src)})</small></li>`).join("")}</ul>${rel.length > 12 ? `<p class="dim">외 ${rel.length - 12}건은 아래 '전체 속보'에서 볼 수 있습니다.</p>` : ""}` : `<p class="dim">관련 속보가 없습니다.</p>`));
    if (relSec.length) H.push(`<h4>📊 4. 섹터</h4><ul>${relSec.map((s) => `<li><b>${s.icon} ${esc(s.name)}</b> 평균 <b class="${cls(s.avg)}">${sg(s.avg)}</b><br>${s.rows.slice(0, 4).map((r) => `${esc(r.name)} <b class="${cls(r.chg)}">${sg(r.chg)}</b>`).join(" · ")}${s.rows.length > 4 ? ` … ${esc(s.rows[s.rows.length - 1].name)} <b class="${cls(s.rows[s.rows.length - 1].chg)}">${sg(s.rows[s.rows.length - 1].chg)}</b>` : ""}${s.rows.some((r) => r.flags.length) ? `<br><small>신호: ${s.rows.filter((r) => r.flags.length).map((r) => `${esc(r.name)}(${r.flags.map(esc).join("·")})`).join(", ")}</small>` : ""}</li>`).join("")}</ul>`);
    H.push(`<h4>💡 ${relSec.length ? 5 : 4}. 운영자 해석과 블로그 분석 글</h4>` +
      (relNotes.length ? relNotes.map((nt) => `<div class="rp-box note"><b>${esc(nt.title)}</b><p>${esc(nt.text)}</p>${nt.post ? `<a href="posts/${encodeURIComponent(nt.post)}.html" target="_blank" rel="noopener">블로그 분석 글 보기 →</a>` : ""}</div>`).join("") : "") +
      (relPosts.length ? `<ul>${relPosts.map((p) => `<li><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a> <small>${esc(p.date.slice(5).replace("-", "/"))}</small></li>`).join("")}</ul>` : (relNotes.length ? "" : `<p class="dim">이 주제의 운영자 분석 글은 아직 없습니다.</p>`)));
    if (relChecks.length) H.push(`<h4>📅 앞으로 확인할 일정</h4><ul>${relChecks.map((c) => `<li><b>${esc(c.date.slice(5).replace("-", "/"))}${c.time ? " " + esc(c.time) : ""}</b> ${esc(c.title)}${c.note ? ` <small>— ${esc(c.note)}</small>` : ""}</li>`).join("")}</ul>`);
    H.push(`<p class="rp-disc">※ 이 리포트는 사이트에 모인 시세·속보·변곡점을 자동으로 정리한 것입니다. 해석과 전망은 담지 않으며 매매 권유가 아닙니다. 운영자 해석은 '💡' 표시와 블로그 분석 글을 참고하세요.</p>`);
    H.push(`<div class="rp-btns"><button class="btn btn-gold btn-sm" id="rpCopy">텍스트 복사</button><button class="btn btn-ghost-dark btn-sm" id="rpClose">닫기</button></div>`);
    out.innerHTML = `<article class="rp">${H.join("")}</article>`;
    out.scrollIntoView({ behavior: "smooth", block: "start" });
    $("#rpClose").onclick = () => { out.innerHTML = ""; };
    $("#rpCopy").onclick = async (e) => {
      const t = out.querySelector(".rp").innerText.replace(/텍스트 복사\s*닫기\s*$/, "").trim();
      try { await navigator.clipboard.writeText(t); e.target.textContent = "복사됐어요 ✓"; } catch { e.target.textContent = "복사 실패"; }
    };
  }
})();
