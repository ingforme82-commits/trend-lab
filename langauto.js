(() => {
  "use strict";
  /* 11/21 운영자 "기본을 영어로": 글로벌 사이트 — 처음 오는 사람은 영어로 연다.
   * - 메뉴에서 고른 언어(한국어 포함)는 기억(trl_lang 쿠키 + localStorage)해서 다음 방문에도 그대로.
   * - 주소에 ?lang=… 이 있으면(공유 링크) 그대로 따른다. ?lang=ko 로 한국어 링크를 줄 수 있다.
   * - 검색엔진·링크 미리보기(카카오톡 등)는 한국어 원문 그대로 둔다.
   */
  try {
    const u = new URL(location.href);
    const explicit = u.searchParams.get("lang")?.toLowerCase();
    const legacyTaiwan = /(?:^|;\s*)(?:googtrans=\/ko\/zh-TW|trl_lang=g%3Azh-TW)(?:;|$)/i.test(document.cookie);
    const profiles = { ko: "ko-KR", en: "en-US", ja: "ja-JP", "zh-hans": "zh-CN", "zh-hant": "zh-TW", fr: "fr-FR" };
    const profile = (key) => {
      document.documentElement.dataset.marketLocale = profiles[key] || "ko-KR";
    };
    profile(explicit || (legacyTaiwan ? "zh-hant" : "ko"));
    if (explicit || /bot|crawl|spider|slurp|lighthouse|preview|scrap|facebookexternalhit|headlesschrome/i.test(navigator.userAgent)) return;
    if (legacyTaiwan) {
      u.searchParams.set("lang", "zh-hant");
      location.replace(u.href);
      return;
    }
    // 11/21: 구글 위젯 언어(de·vi·id·ar)도 자체 번역으로 옮김 — 예전 googtrans 쿠키가 있으면 그 언어로 이어서 연다
    const legacyG = (document.cookie.match(/(?:^|;\s*)googtrans=\/ko\/(de|vi|id|ar)(?:;|$)/) || [])[1];
    let pick = (document.cookie.match(/(?:^|;\s*)trl_lang=([^;]+)/) || [])[1] || "";
    if (!pick) try { pick = localStorage.getItem("trl:lang") || ""; } catch { /* 저장소 없음 */ }
    pick = decodeURIComponent(legacyG || pick || "en");
    if (pick === "ko") return;
    if (pick === "g:zh-TW") pick = "zh-hant";
    if (pick.startsWith("g:")) pick = pick.slice(2);
    if (!/^(en|ja|zh-hans|zh-hant|fr|de|vi|id|ar)$/.test(pick)) pick = "en";
    u.searchParams.set("lang", pick);
    location.replace(u.href);
  } catch { /* 실패하면 원문(한국어) 그대로 */ }
})();
