/* TRL 앱 설치(PWA) — 서비스 워커 등록 + '📲 앱 설치' 버튼. 2026-11-12 */
(function () {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
  }
  const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  const btn = document.getElementById("installBtn");
  if (!btn || standalone) return;                       // 이미 앱으로 열었으면 버튼 숨김
  let deferred = null;
  window.addEventListener("beforeinstallprompt", (e) => {   // 안드로이드·PC 크롬·엣지
    e.preventDefault(); deferred = e; btn.hidden = false;
  });
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  if (ios) btn.hidden = false;                            // 아이폰은 사파리 '홈 화면에 추가'로 안내
  btn.addEventListener("click", async () => {
    if (deferred) {
      deferred.prompt();
      await deferred.userChoice.catch(() => null);
      deferred = null; btn.hidden = true;
    } else if (ios) {
      alert("아이폰: 사파리 아래쪽 공유 버튼(□↑) → '홈 화면에 추가'를 누르면 TRL 앱이 설치됩니다.");
    } else {
      alert("브라우저 메뉴(⋮) → '앱 설치' 또는 '홈 화면에 추가'를 누르세요.");
    }
  });
  window.addEventListener("appinstalled", () => { btn.hidden = true; });
})();
