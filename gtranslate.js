(() => {
  "use strict";
  /* 11/21 운영자 "언어 선택은 10개 정도로, 각 언어 이름은 그 나라 말로" — 메뉴 하나(#trlLanguage)에 10개.
   * 11/21 밤 개정: Deutsch·Tiếng Việt·Bahasa Indonesia·العربية 도 구글 사이트 번역 위젯 대신 자체 번역(localize.js, ?lang=de…)으로.
   *   위젯은 1~2초마다 다시 그려지는 시세·속보 칸을 따라가지 못해 독일어 화면의 절반 넘는 글이 한국어로 남았다(3,725조각 중 2,014).
   * 이 파일은 이제 ① 메뉴에 4개 언어를 끼워 넣고 ② 예전에 남은 구글 번역 쿠키를 지우고 ③ 고른 언어를 기억하는 일만 한다.
   */
  const EXTRA = [
    ["de", "Deutsch", "fr"],
    ["vi", "Tiếng Việt", "de"],
    ["id", "Bahasa Indonesia", "vi"],
    ["ar", "العربية", "id"],
  ];
  const box = document.getElementById("trlGoogleTranslate");
  if (box) box.hidden = true;
  const menu = document.getElementById("trlLanguage");
  if (!menu) return;

  // 예전 구글 번역 쿠키(googtrans) 지우기 — 남아 있으면 구글 번역이 다시 켜질 수 있다
  const host = location.hostname;
  const domains = host && host.includes(".") ? ["", "; domain=" + host, "; domain=." + host.replace(/^www\./, "")] : [""];
  if (/(?:^|;\s*)googtrans=/.test(document.cookie)) {
    for (const d of domains) document.cookie = "googtrans=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/" + d;
  }

  menu.classList.add("notranslate");
  menu.setAttribute("translate", "no");
  for (const [code, name, after] of EXTRA) {
    if ([...menu.options].some((o) => o.value === code)) continue;
    [...menu.options].filter((o) => o.value === "g:" + code).forEach((o) => o.remove());
    const opt = new Option(name, code);
    opt.lang = code;
    const ref = [...menu.options].find((o) => o.value === after);
    menu.add(opt, ref ? ref.index + 1 : null);
  }
  const now = (new URL(location.href).searchParams.get("lang") || "ko").toLowerCase();
  if ([...menu.options].some((o) => o.value === now)) menu.value = now;

  // 고른 언어 기억(langauto.js 가 다음 방문에 사용) — 이동은 localize.js 가 한다
  window.addEventListener("change", (e) => {
    if (e.target !== menu) return;
    document.cookie = "trl_lang=" + encodeURIComponent(menu.value) + "; max-age=31536000; path=/; samesite=lax";
    try { localStorage.setItem("trl:lang", menu.value); } catch { /* 저장소 없음 */ }
  }, true);
})();
