(() => {
  "use strict";
  /* 11/21 운영자 "언어 선택은 10개 정도로, 각 언어 이름은 그 나라 말로":
   * 언어 메뉴 하나(#trlLanguage)에 10개 — 한국어·English·日本語·简体中文·繁體中文·Français·Deutsch·Tiếng Việt·Bahasa Indonesia·العربية
   * - 자체 번역(?lang=en/ja/zh-hans/fr, 시장 용어 고정표) 4개 + 구글 사이트 번역(googtrans 쿠키) 5개.
   * - 둘이 겹치지 않게 한 번에 하나만: 자체 언어로 볼 때는 구글 쿠키를 지우고, 구글 언어를 고르면 ?lang 을 뺀다.
   * - 구글 위젯 스크립트는 translate.google.com 에서 받고, 위젯 자체 드롭다운은 숨긴다(메뉴는 우리 것 하나).
   */
  const GOOGLE = [
    ["zh-TW", "繁體中文", "zh-hans"],          // [구글 코드, 그 나라 말 이름, 이 옵션 뒤에 넣기]
    ["de", "Deutsch", "fr"],
    ["vi", "Tiếng Việt", "de"],
    ["id", "Bahasa Indonesia", "vi"],
    ["ar", "العربية", "id"],
  ];
  const box = document.getElementById("trlGoogleTranslate");
  const menu = document.getElementById("trlLanguage");
  if (!box || !menu) return;
  box.hidden = true;
  const url = new URL(location.href);
  const own = (url.searchParams.get("lang") || "ko").toLowerCase() !== "ko";

  const host = location.hostname;
  const domains = host && host.includes(".") ? ["", "; domain=" + host, "; domain=." + host.replace(/^www\./, "")] : [""];
  function setGoogle(code) {
    const v = code ? "/ko/" + code : "";
    const exp = code ? "; max-age=31536000" : "; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    for (const d of domains) document.cookie = "googtrans=" + v + exp + "; path=/" + d;
  }
  const current = () => ((document.cookie.match(/(?:^|;\s*)googtrans=\/ko\/([^;]+)/) || [])[1] || "");
  if (own) setGoogle("");

  // 메뉴에 구글 번역 언어 5개를 그 나라 말 이름으로 끼워 넣는다
  menu.classList.add("notranslate");
  menu.setAttribute("translate", "no");
  for (const [code, name, after] of GOOGLE) {
    if ([...menu.options].some((o) => o.value === "g:" + code)) continue;
    const opt = new Option(name, "g:" + code);
    opt.lang = code;
    const ref = [...menu.options].find((o) => o.value === after || o.value === "g:" + after);
    menu.add(opt, ref ? ref.index + 1 : null);
  }
  const g = own ? "" : current();
  if (g && GOOGLE.some(([c]) => c === g)) menu.value = "g:" + g;

  // 메뉴 변경: 다른 스크립트(자체 번역 이동)보다 먼저 받는다
  window.addEventListener("change", (e) => {
    if (e.target !== menu) return;
    const v = menu.value;
    if (!v.startsWith("g:")) {
      setGoogle("");
      if (v === "ko" && g) { e.stopImmediatePropagation(); location.replace(location.pathname + location.search.replace(/([?&])lang=[^&]*&?/, "$1").replace(/[?&]$/, "")); }
      return;                                            // 자체 언어 → 구글 끄고 기존 처리에 맡김
    }
    e.stopImmediatePropagation();
    setGoogle(v.slice(2));
    const next = new URL(location.href);
    next.searchParams.delete("lang");
    next.hash = location.hash.startsWith("#googtrans") ? "" : location.hash;
    if (next.href === location.href) location.reload(); else location.assign(next.href);
  }, true);

  // 구글 언어가 선택돼 있을 때만 위젯을 불러온다(한국어·자체 언어는 구글 스크립트 안 받음)
  if (!g) return;
  window.trlGoogleInit = () => {
    try {
      /* global google */
      new google.translate.TranslateElement({ pageLanguage: "ko", includedLanguages: GOOGLE.map(([c]) => c).join(","), autoDisplay: false }, "trlGoogleTranslate");
    } catch { /* 번역 실패 시 원문 그대로 */ }
  };
  const s = document.createElement("script");
  s.src = "https://translate.google.com/translate_a/element.js?cb=trlGoogleInit";
  s.async = true;
  document.head.appendChild(s);
})();
