/* 방문자 수 세기 — 개인정보 없이 숫자만 올린다(abacus 카운터).
   운영자 본인은 주소 끝에 ?me=1 로 한 번 열면 그 브라우저는 세지 않는다(?me=0 으로 해제). */
"use strict";
(() => {
  const NS = "trendlab-ing82", API = "https://abacus.jasoncameron.dev/hit/" + NS + "/";
  const k = new Date(Date.now() + (new Date().getTimezoneOffset() + 540) * 60000);
  const day = `${k.getFullYear()}${String(k.getMonth() + 1).padStart(2, "0")}${String(k.getDate()).padStart(2, "0")}`;
  const ls = { get: (x) => { try { return localStorage.getItem(x); } catch { return null; } }, set: (x, v) => { try { localStorage.setItem(x, v); } catch { /* 무시 */ } } };
  const me = new URLSearchParams(location.search).get("me");
  if (me === "1") ls.set("trl-me", "1");
  if (me === "0") ls.set("trl-me", "");
  const skip = ls.get("trl-me") === "1" || /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname) || location.protocol === "file:";
  const hit = (key) => { if (!skip) fetch(API + key, { keepalive: true, mode: "cors" }).catch(() => {}); };
  window.trlCount = (ev) => { hit(`${ev}-${day}`); hit(`${ev}-total`); };

  window.trlCount("pv");                                  // 페이지뷰
  if (ls.get("trl-day") !== day) {                        // 오늘 처음 온 브라우저 = 방문자 1명
    ls.set("trl-day", day);
    window.trlCount("v");
    if (!ls.get("trl-first")) { ls.set("trl-first", day); hit("u-total"); }   // 처음 와 본 사람(누적 순방문자)
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a"); if (!a) return;
    if (a.href.includes("invite.kakao.com")) window.trlCount("kakao");
    else if (a.href.includes("t.me/")) window.trlCount("tg");
  }, true);
})();
