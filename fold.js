/* fold.js — 화면 길이 줄이기(2026-11-18 운영자: "모바일·웹에서 너무 길지 않게, 옛날 건 줄이고 최신 위주로")
 *
 * 렌더러(app.js·news.js)는 1분마다 innerHTML을 다시 그린다. 그래서 각 렌더러를 고치지 않고,
 * 컨테이너를 지켜보다가(MutationObserver) 다시 그려질 때마다 같은 규칙을 다시 적용한다.
 *
 *  ITEMS  : 목록은 위(최신)에서 N개만 보이고 나머지는 '더 보기 +k'로 접는다.
 *  CLAMP  : 한 덩어리가 긴 칸은 높이를 잘라 두고 '펼치기'로 연다.
 *  누른 상태는 페이지를 닫기 전까지 기억한다(1분 갱신 때 다시 접히지 않게).
 */
(() => {
  "use strict";
  const mobile = () => window.matchMedia("(max-width:760px)").matches;

  // [컨테이너 id, 모바일 개수, PC 개수, 대상 자식 선택자(없으면 모든 자식)]
  const ITEMS = [
    ["hlList", 3, 3],                 // 📌 오늘 핵심: 대표 3개(11/21 UX) — 나머지는 더 보기
    ["moveList", 3, 4],               // 크게 움직인 순간
    ["earnList", 5, 8],               // 미국 실적 일정: 가까운 것부터
    ["archList", 3, 6, ".arc, .arc-record"], // 스터디 아카이브: 최근 회차부터
    ["eduList", 2, 3],                // 교육용 멘트
    ["checkList", 4, 6],              // 이번 주 체크포인트
    ["curList", 2, 5, ".cur-part"],   // 연간 커리큘럼: 모바일은 앞 2단계(11/21 UX)
    ["bookList", 4, 6],               // 독서 토론 도서: 대표 4~6권(11/21 UX)
  ];
  // [CSS 선택자, 모바일 높이(px), PC 높이(px)]
  const CLAMP = [
    ["#chanBoard > .ch-country", 760, 900],  // 📐 추세 판단 나라별 카드
    ["#tgSum > .tg-grid", 700, 800],          // 텔레그램·뉴스 통합 정리
    ["#briefNow", 1100, 1300],                // 지금 브리핑
    ["#heroLive .mn-list", 520, 640],         // 첫 화면 메인 뉴스
    ["#watchBox > .lvbox", 600, 800],         // SOXL·KORU 한눈에
    ["#sectorBox", 900, 1100],                // 주도 섹터·시간대별 강세·모멘텀
    ["#s7Box", 560, 1400],                    // S7 코스피 영향 큰 7종목(11/21 UX: 모바일 시세 칸 길이 줄이기)
    ["#flowBox", 620, 1400],                  // 주도주 수급(11/21 UX)
  ];

  const open = new Set();     // 펼친 칸(키)
  const btn = (key, label) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "btn btn-ghost-dark btn-fold"; b.dataset.fold = key; b.textContent = label;
    return b;
  };
  const syncBtn = (el, key, label) => {
    const n = el.nextElementSibling, existing = n && n.dataset && n.dataset.fold === key ? n : null;
    if (!label) { if (existing) existing.remove(); return; }
    if (existing) { if (existing.textContent !== label) existing.textContent = label; }
    else el.after(btn(key, label));
  };

  function foldItems([id, nm, np, sel]) {
    const box = document.getElementById(id); if (!box) return;
    const key = "i:" + id, limit = mobile() ? nm : np;
    let kids = [...box.children];
    if (sel) kids = kids.filter((c) => c.matches(sel));
    kids = kids.filter((c) => !c.classList.contains("arc-intro"));
    const extra = kids.length - limit;
    kids.forEach((c, i) => c.classList.toggle("fold-hide", !open.has(key) && i >= limit));
    syncBtn(box, key, extra > 0 ? (open.has(key) ? "접기" : `더 보기 +${extra}`) : "");
  }

  function clampOne(el, key, h) {
    // scrollHeight is the full content height even while max-height clips it.
    // Do not temporarily unfold the page merely to measure it.
    const needs = el.scrollHeight > h + 160, clamped = needs && !open.has(key);
    el.classList.toggle("fold-clamp", clamped);
    if (clamped) { if (el.style.getPropertyValue("--fold-h") !== h + "px") el.style.setProperty("--fold-h", h + "px"); }
    else if (el.style.getPropertyValue("--fold-h")) el.style.removeProperty("--fold-h");
    syncBtn(el, key, needs ? (open.has(key) ? "접기" : "펼쳐 보기 ▾") : "");
  }
  function clampAll([sel, hm, hp]) {
    document.querySelectorAll(sel).forEach((el, i) => clampOne(el, `c:${sel}:${i}`, mobile() ? hm : hp));
  }

  let busy = false, queued = false, mo = null;
  function apply() {
    if (busy) return;
    const work = () => {
      busy = true;
      try { ITEMS.forEach(foldItems); CLAMP.forEach(clampAll); }
      finally { if (mo) mo.takeRecords(); busy = false; }
    };
    if (window.trlViewport && !window.trlViewport.updating) window.trlViewport.update(work);
    else work();
  }
  window.trlFold = {apply};
  const later = () => {
    if (busy || queued) return;
    queued = true;
    queueMicrotask(() => { queued = false; apply(); });
  };

  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-fold]"); if (!b) return;
    const key = b.dataset.fold, wasOpen = open.has(key);
    wasOpen ? open.delete(key) : open.add(key);
    // 접을 때는 칸의 처음으로 돌아가 읽던 위치를 잃지 않게
    const box = b.previousElementSibling;
    apply();
    if (wasOpen && box) box.scrollIntoView({ block: "start", behavior: "smooth" });
  });

  function watch() {
    const ids = new Set(ITEMS.map((x) => x[0]).concat(["chanBoard", "tgSum", "briefNow", "heroLive", "watchBox", "sectorBox"]));
    mo = new MutationObserver(() => { if (!busy) later(); });
    ids.forEach((id) => { const el = document.getElementById(id); if (el) mo.observe(el, { childList: true, subtree: true }); });
    apply();
    window.addEventListener("resize", later);
    document.addEventListener("load", later, true); // 늦게 로드되는 이미지
    if (document.fonts) document.fonts.ready.then(later);
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", watch) : watch();
})();
