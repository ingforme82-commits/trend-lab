/* tint.js — 등락 색을 종목명까지(2026-11-18 운영자: "+는 양봉 빨간색, -는 음봉 파란색 — 종목명에서도")
 *
 * 렌더러는 등락률 숫자에만 색(c-up·c-dn 등)을 입힌다. 이 파일은 화면이 다시 그려질 때마다
 *  ① 색이 입혀진 등락 값 바로 앞의 이름(종목·지수·섹터)에 같은 색을 입히고
 *  ② 색이 없는 글(띠·속보 문장)의 "이름 +3.1%" 꼴은 이름과 값을 함께 칠한다.
 * 데이터·문구는 바꾸지 않고 색만 더한다. 상승=빨강, 하락=파랑(국내 관행).
 */
(() => {
  "use strict";
  const UPC = ["c-up", "up", "pos"], DNC = ["c-dn", "down", "neg"];
  const SIGNED = /^[\s(▲▼]*[+\-−]?\s*\d/;
  const NUMISH = /^[\s$₩¥€(]*[\d,.]+\s*(pt|p|원|엔|달러|%|억|조)?[\s)]*$/;
  const SKIP = "script,style,svg,canvas,textarea,input,select,code,.tn-up,.tn-dn";
  const dirOf = (el) => {
    const t = (el.textContent || "").trim();
    if (!SIGNED.test(t) || t.length > 24) return "";
    const cl = el.classList;
    if (UPC.some((c) => cl.contains(c))) return "up";
    if (DNC.some((c) => cl.contains(c))) return "dn";
    return "";
  };
  // 이름이 아닌 말(값만 칠하고 이 말은 그대로)
  const STOP = /^(대비|기준|전일|전날|종가|평균|등락|등락률|합계|상승|하락|변화|누적|오늘|어제|주간|월간|연초|최근|약|각각|및|또는|시간외|프리|애프터|정규장|아래|위|위쪽|아래쪽|돌파|이탈|기초)$/;
  const isColored = (el) => el.nodeType === 1 && (UPC.concat(DNC).some((c) => el.classList.contains(c)) || el.classList.contains("tn-up") || el.classList.contains("tn-dn"));

  // 문장 끝 조각만 이름으로 본다: "🏁 주도 업종: 무선 통신 서비스 " → "무선 통신 서비스"
  function wrapTail(tn, d) {
    // 마지막 구분자(: · | 줄바꿈 괄호) 뒤 조각에서 끝의 가격(1,331.98원·$147.42)을 떼고 남은 말이 이름
    const s = tn.nodeValue, m = s.match(/([^:：·|\n()]*?)((?:\s*[$₩¥]?[\d,]+(?:\.\d+)?\s*(?:pt|p|원|엔|달러)?)?\s*)$/u);
    if (!m) return false;
    let name = m[1].replace(/^[\s\p{Extended_Pictographic}️,]+/u, "").replace(/\s+$/, "");
    if (!name || name.length > 24 || !/[\p{L}]/u.test(name) || STOP.test(name)) return false;
    const start = m.index + (m[1].length - m[1].replace(/^[\s\p{Extended_Pictographic}️,]+/u, "").length), end = start + name.length;
    const span = document.createElement("span");
    span.className = "tn-" + d; span.textContent = s.slice(start, end);
    const after = tn.splitText(start); after.nodeValue = after.nodeValue.slice(name.length);
    tn.parentNode.insertBefore(span, after);
    return true;
  }
  function tintName(v, d) {
    // 카드형(이름이 따로 있는 시세 카드)
    const card = v.closest(".tick");
    if (card) { const n = card.querySelector(".t-name"); if (n) n.classList.add("tn-" + d); return; }
    // 표: 같은 줄 첫 칸이 종목명
    const cell = v.closest("td,th"), row = cell && cell.parentElement;
    if (row && row.tagName === "TR" && row.cells[0] !== cell) {
      const n = row.cells[0], t = n.textContent.trim();
      // 줄의 첫 등락 값(보통 등락률)만 이름 색을 정한다 — 뒤쪽 수급 금액은 이름 색을 바꾸지 않음
      if (n.classList.contains("tn-up") || n.classList.contains("tn-dn")) return;
      if (t && t.length <= 24 && /[\p{L}]/u.test(t) && !NUMISH.test(t) && !n.querySelector(".c-up,.c-dn")) n.classList.add("tn-" + d);
      return;
    }
    let p = v.previousSibling, steps = 0;
    while (p && steps < 4) {
      steps++;
      if (p.nodeType === 3) {
        if (!p.nodeValue.trim()) { p = p.previousSibling; continue; }
        if (NUMISH.test(p.nodeValue)) { p = p.previousSibling; continue; }
        wrapTail(p, d); return;
      }
      if (p.nodeType === 1) {
        if (isColored(p) || p.matches("small,br,hr")) return;
        const t = p.textContent.trim();
        if (!t || NUMISH.test(t)) { p = p.previousSibling; continue; }
        if (t.length <= 24 && /[\p{L}]/u.test(t)) p.classList.add("tn-" + d);
        return;
      }
      p = p.previousSibling;
    }
  }

  // ② 색 없는 글: 이름 (가격) ±x.x%
  const RX = /(?<![\p{L}\p{N},.\/])([\p{L}&][\p{L}\p{N}&.\/]{0,17}|\d+\p{L}[\p{L}\p{N}]*)(\s*(?:[$₩]?[\d,]+(?:\.\d+)?(?:pt|원|엔|달러)?\s*)?)(\(?[+\-−]\d[\d,]*(?:\.\d+)?%\)?)/gu;
  function tintText(tn) {
    const s = tn.nodeValue;
    if (!s || s.indexOf("%") < 0) return;
    RX.lastIndex = 0;
    if (!RX.test(s)) return;
    RX.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0, m;
    while ((m = RX.exec(s))) {
      const d = /^\(?[+]/.test(m[3]) ? "up" : "dn";
      if (/^\(?[+\-−]0(?:\.0+)?%/.test(m[3])) continue;   // 보합은 그대로
      frag.append(s.slice(last, m.index));
      const a = document.createElement("span"); if (!STOP.test(m[1])) a.className = "tn-" + d; a.textContent = m[1];
      const b = document.createElement("span"); b.className = "tn-" + d + " tn-v"; b.textContent = m[3];
      frag.append(a, m[2], b);
      last = m.index + m[0].length;
    }
    if (!last) return;
    frag.append(s.slice(last));
    tn.parentNode.replaceChild(frag, tn);
  }

  function run(root) {
    if (!root || root.nodeType !== 1 || root.closest(SKIP)) return;
    root.querySelectorAll(".c-up,.c-dn,.up,.down,.pos,.neg,.t-ch").forEach((v) => {
      if (v.dataset.tn) return;
      const d = dirOf(v) || (v.classList.contains("t-ch") ? (/^[\s▲]*\+/.test(v.textContent) ? "up" : /^[\s▼]*[-−]/.test(v.textContent) ? "dn" : "") : "");
      v.dataset.tn = "1";
      if (d) tintName(v, d);
    });
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.nodeValue.indexOf("%") < 0 || n.parentElement.closest(SKIP) || isColored(n.parentElement) || n.parentElement.closest(".c-up,.c-dn,.pos,.neg,.t-ch")) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    const list = []; while (w.nextNode()) list.push(w.currentNode);
    list.forEach(tintText);
  }

  let mo = null, pend = new Set(), timer = 0;
  const flush = () => {
    const roots = [...pend]; pend.clear();
    roots.filter((r) => r.isConnected && !roots.some((o) => o !== r && o.contains(r))).forEach(run);
    if (mo) mo.takeRecords();   // 내가 넣은 색 칠은 다시 감지하지 않는다
  };
  function start() {
    run(document.body);
    mo = new MutationObserver((recs) => {
      for (const r of recs) { const t = r.target.nodeType === 1 ? r.target : r.target.parentElement; if (t) pend.add(t); }
      clearTimeout(timer); timer = setTimeout(flush, 250);
    });
    mo.observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", start) : start();
})();
