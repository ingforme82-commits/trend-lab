(() => {
  "use strict";
  /* 11/21 운영자 "구글 사이트 번역 — 여러 언어를 드롭다운으로": 구글 공식 사이트 번역 위젯(100개 넘는 언어).
   * - 사이트 자체 번역(?lang=en/ja/zh-hans/fr, 시장 용어 고정표)과 겹치지 않게 한 번에 하나만 켠다.
   *   · 자체 언어(?lang=…)로 볼 때는 구글 번역 쿠키를 지운다.
   *   · 구글 드롭다운에서 언어를 고르면 ?lang 을 빼고 다시 연다(구글 번역만 남김).
   * - 위젯 스크립트는 구글(translate.google.com)에서 받는다.
   */
  const box = document.getElementById("trlGoogleTranslate");
  if (!box) return;
  const url = new URL(location.href);
  const own = (url.searchParams.get("lang") || "ko").toLowerCase() !== "ko";

  function clearGoogle() {
    const past = "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    document.cookie = "googtrans" + past;
    const host = location.hostname;
    if (host && host.includes(".")) {
      document.cookie = "googtrans" + past + "; domain=" + host;
      document.cookie = "googtrans" + past + "; domain=." + host.replace(/^www\./, "");
    }
  }
  if (own) clearGoogle();

  // 자체 언어 메뉴를 바꾸면 구글 번역은 끈다
  const menu = document.getElementById("trlLanguage");
  if (menu) {
    menu.classList.add("notranslate");
    menu.setAttribute("translate", "no");
    menu.addEventListener("change", clearGoogle);
  }

  window.trlGoogleInit = () => {
    try {
      /* global google */
      new google.translate.TranslateElement({ pageLanguage: "ko", autoDisplay: false }, "trlGoogleTranslate");
    } catch { box.hidden = true; return; }
    box.hidden = false;
    // 구글 드롭다운에서 언어를 고르면: 자체 번역(?lang) 중이었다면 빼고 다시 연다
    const hook = () => {
      const combo = box.querySelector("select.goog-te-combo");
      if (!combo) return setTimeout(hook, 300);
      combo.setAttribute("aria-label", "Google Translate");
      combo.addEventListener("change", () => {
        if (!own) return;
        const lang = combo.value;
        const next = new URL(location.href);
        next.searchParams.delete("lang");
        if (lang) next.hash = "googtrans(ko|" + lang + ")";
        location.assign(next.href);
      });
    };
    hook();
  };

  const load = () => {
    const s = document.createElement("script");
    s.src = "https://translate.google.com/translate_a/element.js?cb=trlGoogleInit";
    s.async = true;
    s.onerror = () => { box.hidden = true; };
    document.head.appendChild(s);
  };
  if (document.readyState === "complete") load();
  else window.addEventListener("load", load, { once: true });
})();
