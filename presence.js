/* Visible-page presence only. Daily random browser id; no names/IP/accounts. */
"use strict";
(() => {
  const read = key => { try { return localStorage.getItem(key); } catch { return null; } };
  const write = (key, value) => { try { localStorage.setItem(key, value); } catch { /* session fallback */ } };
  const random = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2, "0")).join("");
  const page = random();
  let browser = null, browserDay = null, busy = false;
  function excluded() {
    return read("trl-me") === "1" || read("trl-analytics-off") === "1" || navigator.globalPrivacyControl === true || navigator.doNotTrack === "1" || location.hostname !== "ingforme82-commits.github.io";
  }
  async function beat() {
    if (busy || document.hidden || excluded()) return;
    const url = window.trlRtUrl;
    if (!/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(url || "")) return;
    const day = new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);
    if (browserDay !== day) {
      const saved = read("trl-presence-day") === day ? read("trl-presence-id") : null;
      browser = /^[a-f0-9]{32}$/.test(saved || "") ? saved : random();
      browserDay = day; write("trl-presence-day", day); write("trl-presence-id", browser);
    }
    busy = true;
    try {
      await fetch(url + "/presence", {method:"POST", mode:"cors", credentials:"omit", referrerPolicy:"no-referrer", headers:{"Content-Type":"text/plain"}, body:JSON.stringify({browser, page}), signal:AbortSignal.timeout(7000)});
    } catch { /* Failed collection must not interrupt market data. */ }
    finally { busy = false; }
  }
  const note = document.createElement("div");
  note.style.cssText = "font-size:11px;margin:10px auto;text-align:center;color:inherit";
  const label = document.createElement("span");
  label.textContent = "익명 방문 집계 · 최근 2분 활성 브라우저 기준 · 이름·계좌 정보 수집 없음 ";
  const toggle = document.createElement("button");
  toggle.type = "button";
  const updateLabel = () => { toggle.textContent = read("trl-analytics-off") === "1" ? "이 브라우저 집계 켜기" : "이 브라우저 집계 끄기"; };
  toggle.addEventListener("click", () => { write("trl-analytics-off", read("trl-analytics-off") === "1" ? "0" : "1"); updateLabel(); beat(); });
  updateLabel(); note.append(label, toggle); (document.querySelector("footer") || document.body).append(note);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) beat(); });
  setInterval(beat, 30000);
  setTimeout(beat, 5000);
})();
