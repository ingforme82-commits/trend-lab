(() => {
  "use strict";

  const languages = {
    ko: ["한국어", "언어 선택", ""],
    en: ["English", "Language", "Some text could not be translated. The original is shown."],
    ja: ["日本語", "言語", "翻訳できなかった箇所は原文を表示しています。"],
    "zh-hans": ["简体中文", "语言", "部分内容无法翻译，已显示原文。"],
    fr: ["Français", "Langue", "Certaines parties sont affichées dans leur langue d’origine."],
  };
  const page = new URL(location.href);
  const requested = (page.searchParams.get("lang") || "ko").toLowerCase();
  const language = Object.hasOwn(languages, requested) ? requested : "ko";
  const tag = language === "zh-hans" ? "zh-Hans" : language;
  const menu = document.getElementById("trlLanguage");
  if (menu && !menu.options.length) {
    for (const [code, info] of Object.entries(languages)) {
      const option = new Option(info[0], code);
      option.lang = code === "zh-hans" ? "zh-Hans" : code;
      menu.add(option);
    }
    menu.value = language;
    menu.setAttribute("aria-label", languages[language][1]);
    menu.addEventListener("change", () => {
      const url = new URL(location.href);
      if (menu.value === "ko") url.searchParams.delete("lang");
      else url.searchParams.set("lang", menu.value);
      location.assign(url);
    });
  }
  if (language === "ko") return;

  document.documentElement.lang = tag;
  const note = document.getElementById("trlLanguageNote");
  if (note) {
    note.textContent = languages[language][2];
    note.hidden = true;
  }
  const excluded = "script, style, noscript, select, textarea, input, [contenteditable], [translate=no], #trlLanguageNote";
  const cacheKey = "trl:public-translations:v1:" + language;
  let saved = [];
  try {
    const entries = JSON.parse(localStorage.getItem(cacheKey) || "[]");
    if (Array.isArray(entries)) saved = entries;
  } catch { /* Storage is optional. */ }
  const cache = new Map(saved);
  const pending = new Map();
  const queue = [];
  let running = 0;
  let cooldown = 0;
  let nextPump;
  let saveTimer;

  function remember(source, translated) {
    cache.set(source, translated);
    while (cache.size > 600) cache.delete(cache.keys().next().value);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try { localStorage.setItem(cacheKey, JSON.stringify([...cache])); }
      catch { /* Storage is optional. */ }
    }, 300);
  }

  async function fetchTranslation(source) {
    const params = new URLSearchParams({
      client: "gtx", sl: /[가-힣]/.test(source) ? "ko" : "en", tl: language === "zh-hans" ? "zh-CN" : language, dt: "t", q: source,
    });
    const response = await fetch("https://translate.googleapis.com/translate_a/single?" + params, {
      credentials: "omit", referrerPolicy: "no-referrer", signal: AbortSignal.timeout(8000),
    });
    if (response.status === 429 || response.status === 403) cooldown = Date.now() + 60000;
    if (!response.ok) throw Error("Translation unavailable");
    const data = await response.json();
    const output = data[0]?.map((part) => part[0] || "").join("").trim();
    if (!output) throw Error("Empty translation");
    return output;
  }

  function pump() {
    clearTimeout(nextPump);
    if (!queue.length) return;
    if (Date.now() < cooldown) {
      nextPump = setTimeout(pump, cooldown - Date.now());
      return;
    }
    while (running < 4 && queue.length) {
      const { source, resolve } = queue.shift();
      running++;
      fetchTranslation(source).then((output) => {
        remember(source, output);
        resolve(output);
      }).catch(() => {
        if (note) note.hidden = false;
        resolve(null);
      }).finally(() => {
        pending.delete(source);
        running--;
        pump();
      });
    }
  }

  function translate(source) {
    if (cache.has(source)) return Promise.resolve(cache.get(source));
    if (pending.has(source)) return pending.get(source);
    const promise = new Promise((resolve) => queue.push({ source, resolve }));
    pending.set(source, promise);
    pump();
    return promise;
  }

  const tracked = new WeakMap();
  function translateValue(node, attribute) {
    const original = attribute ? node.getAttribute(attribute) : node.data;
    const source = original?.trim();
    if (!source) return;
    const korean = /[가-힣]/.test(source);
    const englishSentence = language !== "en" && (attribute ? node : node.parentElement).closest("[lang=en]") && (source.match(/[A-Za-z]{2,}/g) || []).length >= 5;
    if (!korean && !englishSentence) return;
    const key = attribute || "text";
    const states = tracked.get(node) || {};
    if (states[key] === original) return;
    states[key] = original;
    tracked.set(node, states);
    translate(source).then((output) => {
      if (!output) {
        if (states[key] === original) delete states[key];
        return;
      }
      if (!node.isConnected) return;
      const current = attribute ? node.getAttribute(attribute) : node.data;
      if (current !== original) return;
      const value = original.replace(source, () => output);
      states[key] = value;
      if (attribute) node.setAttribute(attribute, value);
      else node.data = value;
    });
  }

  function scan(root) {
    if (!root || (root.nodeType !== 1 && root.nodeType !== 3)) return;
    const element = root.nodeType === 3 ? root.parentElement : root;
    if (!element || element.closest(excluded)) return;
    if (root.nodeType === 3) {
      translateValue(root);
      return;
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.parentElement.closest(excluded)) translateValue(node);
    }
    for (const node of [element, ...element.querySelectorAll("[title], [aria-label], [alt]")]) {
      if (node.closest(excluded)) continue;
      for (const attribute of ["title", "aria-label", "alt"]) translateValue(node, attribute);
    }
  }

  function preserveLanguage(anchor) {
    const href = anchor.getAttribute("href");
    if (!href || href.startsWith("#")) return;
    let url;
    try { url = new URL(href, location.href); } catch { return; }
    if (url.origin !== location.origin || !/(?:\/|\/index\.html|\/study\.html)$/.test(url.pathname)) return;
    if (!url.searchParams.has("lang")) {
      url.searchParams.set("lang", language);
      anchor.href = url.href;
    }
  }

  function scanLinks(node) {
    if (node.nodeType !== 1) return;
    if (node.matches("a[href]")) preserveLanguage(node);
    node.querySelectorAll("a[href]").forEach(preserveLanguage);
  }

  scan(document.body);
  scan(document.querySelector("title"));
  scanLinks(document.body);
  new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === "attributes") {
        if (record.attributeName === "href") preserveLanguage(record.target);
        else if (!record.target.closest(excluded)) translateValue(record.target, record.attributeName);
      } else if (record.type === "characterData") scan(record.target);
      else for (const node of record.addedNodes) {
        scan(node);
        scanLinks(node);
      }
    }
  }).observe(document.documentElement, {
    childList: true, subtree: true, characterData: true, attributes: true,
    attributeFilter: ["href", "title", "aria-label", "alt"],
  });
})();
