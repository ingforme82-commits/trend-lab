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
  // 구글 쿠키가 빠졌어도(이동 중 지워짐 등) 메뉴에서 고른 구글 언어가 기억돼 있으면 다시 켠다
  const saved = decodeURIComponent((document.cookie.match(/(?:^|;\s*)trl_lang=([^;]+)/) || [])[1] || "");
  if (!own && !current() && saved.startsWith("g:") && !new URL(location.href).searchParams.has("lang")) setGoogle(saved.slice(2));
  const g = own ? "" : current();
  if (g && GOOGLE.some(([c]) => c === g)) menu.value = "g:" + g;

  // 메뉴 변경: 다른 스크립트(자체 번역 이동)보다 먼저 받는다
  window.addEventListener("change", (e) => {
    if (e.target !== menu) return;
    const v = menu.value;
    // 고른 언어 기억(langauto.js 가 다음 방문에 사용, 기본은 영어)
    document.cookie = "trl_lang=" + encodeURIComponent(v) + "; max-age=31536000; path=/; samesite=lax";
    try { localStorage.setItem("trl:lang", v); } catch { /* 저장소 없음 */ }
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
  /* 구글이 틀리는 시장 용어는 번역 전에 뜻이 분명한 한국어로 바꿔 둔다
   * (속보 → 'Trab·말 걸음', 시세 → 'Zitat·인용', '뉴스 속보' → 'Blitz·섬광'으로 나오던 문제, 11/21 확인) */
  const FIX = [[/속보(?! 뉴스)/g, "속보 뉴스"], [/(?<!시장 )시세/g, "시장 시세"], [/넥장/g, "넥스트레이드"], [/물타기/g, "추가 매수"], [/조영근/g, "Cho Young-geun"]];
  const skip = "script, style, noscript, textarea, input, select, .notranslate, [translate=no]";
  const fixNode = (n) => {
    if (!/[속시넥물조]/.test(n.data) || !n.parentElement || n.parentElement.closest(skip)) return;
    let t = n.data; for (const [re, to] of FIX) t = t.replace(re, to);
    if (t !== n.data) n.data = t;
  };
  const fixTree = (root) => {
    if (root.nodeType === 3) return fixNode(root);
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) fixNode(n);
  };
  fixTree(document.body);
  new MutationObserver((ms) => { for (const m of ms) { if (m.type === "characterData") fixNode(m.target); else m.addedNodes.forEach(fixTree); } })
    .observe(document.body, { childList: true, subtree: true, characterData: true });
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
