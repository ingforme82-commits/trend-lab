(() => {
  "use strict";
  /* 11/21 운영자 "기본을 영어로": 글로벌 사이트 — 처음 오는 사람은 영어로 연다.
   * - 메뉴에서 고른 언어(한국어 포함)는 기억(trl_lang 쿠키 + localStorage)해서 다음 방문에도 그대로.
   * - 주소에 ?lang=… 이 있으면(공유 링크) 그대로 따른다. ?lang=ko 로 한국어 링크를 줄 수 있다.
   * - 검색엔진·링크 미리보기(카카오톡 등)는 한국어 원문 그대로 둔다.
   */
  try {
    if (/bot|crawl|spider|slurp|lighthouse|preview|scrap|facebookexternalhit|headlesschrome/i.test(navigator.userAgent)) return;
    const u = new URL(location.href);
    if (u.searchParams.has("lang")) return;
    if (/(?:^|;\s*)googtrans=\/ko\/(?!ko)/.test(document.cookie)) return;   // 구글 번역 언어로 보는 중
    let pick = (document.cookie.match(/(?:^|;\s*)trl_lang=([^;]+)/) || [])[1] || "";
    if (!pick) try { pick = localStorage.getItem("trl:lang") || ""; } catch { /* 저장소 없음 */ }
    pick = decodeURIComponent(pick || "en");
    if (pick === "ko") return;
    if (pick.startsWith("g:")) {
      const host = location.hostname, v = "googtrans=/ko/" + pick.slice(2) + "; max-age=31536000; path=/";
      document.cookie = v;
      if (host.includes(".")) { document.cookie = v + "; domain=" + host; document.cookie = v + "; domain=." + host.replace(/^www\./, ""); }
      return;
    }
    if (!/^(en|ja|zh-hans|fr)$/.test(pick)) pick = "en";
    u.searchParams.set("lang", pick);
    location.replace(u.href);
  } catch { /* 실패하면 원문(한국어) 그대로 */ }
})();
