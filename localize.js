(() => {
  "use strict";
  /* 다국어 자동 번역 — 2026-11-21 개정(v2)
   * 고친 문제: 실시간 시세·속보 칸은 1~2초마다 숫자만 바뀐 새 문장("기준 전일 종가 53,400원")을 만든다.
   * 예전에는 이 문장마다 번역 요청을 따로 보내서 요청이 폭주 → 번역 서버가 429(요청 과다)로 막음 →
   * 60초 쉬는 동안 대기 줄에 있던 나머지 문장(속보·브리핑·버튼)까지 한국어로 남았다. 캐시(600개)도 숫자 문장으로 금방 밀려났다.
   * 지금: ① 숫자는 {0},{1}… 자리표로 빼고 '틀'만 번역해 캐시(숫자가 바뀌어도 재요청 없음)
   *       ② 여러 문장을 한 요청으로 묶어 보냄(요청 수 수십 분의 1)  ③ 429·실패는 버리지 않고 쉬었다가 최대 3번 다시 시도
   */

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
  const spaced = language === "en" || language === "fr";
  const target = language === "zh-hans" ? "zh-CN" : language;

  /* ── 캐시: 숫자를 뺀 '틀' 단위로 저장. 값 "" = 자리표가 깨져서 조각 번역으로 처리하는 틀 ── */
  const cacheKey = "trl:public-translations:v2:" + language;
  const CACHE_MAX = 4000;
  let saved = [];
  try {
    localStorage.removeItem("trl:public-translations:v1:" + language);   // 숫자 문장으로 가득 찬 예전 캐시 정리
    const entries = JSON.parse(localStorage.getItem(cacheKey) || "[]");
    if (Array.isArray(entries)) saved = entries;
  } catch { /* Storage is optional. */ }
  const cache = new Map(saved);
  let saveTimer;
  function remember(source, translated) {
    cache.delete(source);
    cache.set(source, translated);
    while (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try { localStorage.setItem(cacheKey, JSON.stringify([...cache])); }
      catch { /* Storage is optional. */ }
    }, 500);
  }

  /* ── 요청 묶음 보내기 ── */
  const BATCH_ITEMS = 25;          // 한 요청에 담는 문장 수
  const BATCH_URL = 6000;          // 주소 길이 상한(인코딩 후)
  const PARALLEL = 2;              // 동시에 보내는 요청 수
  const MAX_TRIES = 3;
  const pending = new Map();       // text → Promise
  const queue = [];                // { text, sl, resolve, tries, single }
  let running = 0;
  const GAP = 400;                 // 요청 출발 최소 간격(ms) — 몰아 보내면 429
  let cooldown = 0;
  let backoff = 0;
  let lastStart = 0;
  let nextPump;

  function endpoint(sl, q) {
    return "https://translate.googleapis.com/translate_a/single?" + new URLSearchParams({ client: "gtx", sl, tl: target, dt: "t", q });
  }

  async function call(sl, q) {
    const response = await fetch(endpoint(sl, q), {
      credentials: "omit", referrerPolicy: "no-referrer", signal: AbortSignal.timeout(10000),
    });
    if (response.status === 429 || response.status === 403) {
      backoff = Math.min(backoff ? backoff * 2 : 5000, 60000);   // 5초 → 10초 → … 최대 60초
      cooldown = Date.now() + backoff;
      const error = Error("Rate limited");
      error.limited = true;
      throw error;
    }
    if (!response.ok) throw Error("Translation unavailable");
    backoff = 0;
    const data = await response.json();
    return (data[0] || []).map((part) => part[0] || "").join("");
  }

  function take() {
    const first = queue.shift();
    const batch = [first];
    if (first.single) return batch;
    let size = endpoint(first.sl, first.text).length;
    for (let i = 0; i < queue.length && batch.length < BATCH_ITEMS;) {
      const item = queue[i];
      const extra = encodeURIComponent("\n" + item.text).length;
      if (item.single || item.sl !== first.sl || size + extra > BATCH_URL) { i++; continue; }
      batch.push(item);
      size += extra;
      queue.splice(i, 1);
    }
    return batch;
  }

  function settle(item, output) {
    pending.delete(item.text);
    if (output) remember(item.text, output);
    item.resolve(output || null);
  }

  function retry(item, limited) {
    item.tries++;
    if (item.tries >= MAX_TRIES) {
      if (note) note.hidden = false;
      settle(item, null);
      return;
    }
    if (!limited) item.single = true;   // 묶음이 깨졌으면 다음엔 한 문장씩
    queue.push(item);
  }

  function pump() {
    clearTimeout(nextPump);
    if (!queue.length || running >= PARALLEL) return;
    const wait = Math.max(cooldown, lastStart + GAP) - Date.now();
    if (wait > 0) {
      nextPump = setTimeout(pump, wait + 20);
      return;
    }
    {
      const batch = take();
      lastStart = Date.now();
      running++;
      call(batch[0].sl, batch.map((item) => item.text).join("\n")).then((output) => {
        const lines = output.split("\n").map((line) => line.trim());
        while (lines.length > batch.length && lines[lines.length - 1] === "") lines.pop();
        if (lines.length !== batch.length || lines.some((line) => !line)) {
          if (batch.length === 1) throw Error("Empty translation");
          batch.forEach((item) => { item.single = true; queue.push(item); });   // 줄 수가 안 맞으면 한 문장씩 다시
          return;
        }
        batch.forEach((item, i) => settle(item, lines[i]));
      }).catch((error) => {
        batch.forEach((item) => retry(item, error.limited));
      }).finally(() => {
        running--;
        pump();
      });
      pump();   // 다음 묶음은 GAP 뒤에 출발
    }
  }

  function request(text) {
    if (cache.has(text)) return Promise.resolve(cache.get(text));
    if (pending.has(text)) return pending.get(text);
    const sl = /[가-힣]/.test(text) ? "ko" : "en";
    const promise = new Promise((resolve) => queue.push({ text, sl, resolve, tries: 0, single: false }));
    pending.set(text, promise);
    pump();
    return promise;
  }

  /* ── 숫자 자리표 ── */
  const NUMBER = /\d+(?:[.,:]\d+)*/g;
  const ENGLISH_UI = {
  "개장 전": "Before market open",
  "장중": "Intraday",
  "마감": "Closed",
  "정규장": "Regular session",
  "프리마켓": "Premarket",
  "애프터마켓": "After hours",
  "주간거래": "Day session",
  "마지막": "Last available",
  "자료 확인 중": "Checking data",
  "확인 중": "Checking",
  "시세 대기": "Awaiting quotes",
  "시세를 받지 못함": "Quotes unavailable",
  "조회 시각 확인 불가": "Quote retrieval time unavailable",
  "원천 시각 확인 불가": "Source timestamp unavailable",
  "전일 종가": "Previous close",
  "전일 종가 기준": "Previous-close basis",
  "전일 종가 대비": "vs. previous close",
  "전일 종가부터": "Since the previous close",
  "당일 정규장 마지막 {0}분봉 종가": "Last regular-session {0}-minute close today",
  "직전 정규장 마지막 {0}분봉 종가": "Last {0}-minute close of the prior regular session",
  "정규장 종가": "Regular-session close",
  "정규장 진행 중 · 지금": "Regular session · now",
  "시간외": "Extended hours",
  "시가": "Open",
  "고가": "High",
  "저가": "Low",
  "종가": "Close",
  "현재가": "Last price",
  "등락률": "Change (%)",
  "종목": "Symbol",
  "업종": "Industry",
  "오늘": "Today",
  "이번 시간": "This hour",
  "거래대금": "Trading value",
  "거래량": "Volume",
  "거래대금 상위": "Most traded by value",
  "상승": "Advancing",
  "하락": "Declining",
  "보합": "Unchanged",
  "전체": "All",
  "더 보기": "Show more",
  "닫기": "Close",
  "불러오는 중…": "Loading…",
  "채널 안": "Inside channel",
  "채널 상단": "Channel ceiling",
  "채널 하단": "Channel floor",
  "수평 하단": "Horizontal floor",
  "수평 지지": "Horizontal support",
  "수평 저항": "Horizontal resistance",
  "위 저항": "Resistance above",
  "아래 지지": "Support below",
  "⬆ 위 저항": "Resistance above",
  "⬇ 아래 지지": "Support below",
  "상단 근접": "Near the channel ceiling",
  "하단 이탈": "Below the channel floor",
  "하단 위": "Above the floor",
  "구간 안": "Inside the band",
  "채널선 교차·재확인": "Channel lines cross · recheck",
  "접촉 검증 대기": "Awaiting confirmation of touches",
  "돌파 확인": "Breakout confirmed",
  "돌파 시도(장중)": "Intraday breakout attempt",
  "돌파 관찰·상단 근접": "Watching for a breakout · near ceiling",
  "채널 위·{0}일선 아래": "Above channel · below {0}-day MA",
  "채널 돌파·전고점 아래": "Above channel · below prior high",
  "{0}일선": "{0}-day MA",
  "마지막 봉": "Latest bar",
  "{0}분봉 · 한국시간 · 시간외는 음영": "{0}-minute candles · KST · extended hours shaded",
  "정규장·시간외 {0}분봉": "Regular and extended-hours {0}-minute candles",
  "등락 기준가 확인 중": "Checking the reference price",
  "한국 시간 조회": "Retrieved in Korea time",
  "코스피": "KOSPI",
  "코스닥": "KOSDAQ",
  "코스피{0}": "KOSPI {0}",
  "엔비디아": "NVIDIA",
  "앤트로픽": "Anthropic",
  "삼성전자": "Samsung Electronics",
  "삼성전자우": "Samsung Electronics Preferred",
  "SK하이닉스": "SK hynix",
  "마이크론": "Micron",
  "샌디스크": "SanDisk",
  "미국 반도체": "U.S. semiconductors",
  "시장 브리핑": "Market briefing",
  "실시간 시세": "Live quotes",
  "주요 시황": "Market highlights",
  "실시간 속보": "Breaking news",
  "연결된 뉴스 없음": "No related news",
  "최근 관련 속보가 없습니다.": "No recent related news.",
  "최근 {0}시간": "Past {0} hours",
  "약 {0}분 지연": "About {0} minutes delayed",
  "{0}일선 위": "Above the {0}-day MA",
  "{0}일선 아래": "Below the {0}-day MA",
  "원화": "KRW",
  "달러": "USD"
};
  const SLOT = /[{｛]\s*(\d+)\s*[}｝]/g;

  function fill(output, numbers) {
    const normal = output.replace(SLOT, (_, i) => "{" + i + "}");
    const found = normal.match(/\{\d+\}/g) || [];
    if (found.length !== numbers.length) return null;
    const seen = new Set(found);
    if (seen.size !== numbers.length || numbers.some((_, i) => !seen.has("{" + i + "}"))) return null;
    return normal.replace(/\{(\d+)\}/g, (_, i) => numbers[+i]);
  }

  async function bySegments(template, numbers) {
    const parts = template.split(/\{\d+\}/);
    const outputs = await Promise.all(parts.map((part) => {
      const core = part.trim();
      if (!/[가-힣]/.test(core)) return part;
      return request(core).then((out) => (out ? part.replace(core, () => out) : null));
    }));
    if (outputs.some((out) => out == null)) return null;
    // 한국어는 '53,400원'처럼 단위를 붙여 쓰므로, 영어·프랑스어는 번역된 낱말과 숫자 사이에 한 칸 띄운다.
    const letter = /[A-Za-zÀ-ÿ]/;
    let text = outputs[0];
    for (let i = 0; i < numbers.length; i++) {
      const before = /[가-힣]$/.test(parts[i]) && letter.test(text.slice(-1));
      const after = /^[가-힣]/.test(parts[i + 1]) && letter.test(outputs[i + 1].charAt(0));
      text += (spaced && before ? " " : "") + numbers[i] + (spaced && after ? " " : "") + outputs[i + 1];
    }
    return text;
  }

  async function translate(source) {
    const numbers = [];
    const template = source.replace(NUMBER, (match) => { numbers.push(match); return "{" + (numbers.length - 1) + "}"; });
    if (!numbers.length) return request(source);
    if (cache.get(template) !== "") {
      const out = await request(template);
      const filled = out && fill(out, numbers);
      if (filled) return filled;
      if (out) remember(template, "");   // 자리표가 깨지는 틀 → 다음부터 바로 조각 번역
    }
    return bySegments(template, numbers);
  }

  /* ── 화면 적용 ── */
  const tracked = new WeakMap();
  function translateValue(node, attribute) {
    const original = attribute ? node.getAttribute(attribute) : node.data;
    const source = original?.trim().replace(/\s+/g, " ");
    if (!source) return;
    const korean = /[가-힣]/.test(source);
    const englishSentence = language !== "en" && (attribute ? node : node.parentElement).closest("[lang=en]") && (source.match(/[A-Za-z]{2,}/g) || []).length >= 5;
    if (!korean && !englishSentence) return;
    const key = attribute || "text";
    const states = tracked.get(node) || {};
    if (states[key] === original) return;
    states[key] = original;
    tracked.set(node, states);
    const numbers = [];
    const template = source.replace(NUMBER, (number) => {
      numbers.push(number);
      return "{" + (numbers.length - 1) + "}";
    });
    const fixed = language === "en" && Object.hasOwn(ENGLISH_UI, template)
      ? fill(ENGLISH_UI[template], numbers) : null;
    if (fixed) {
      const value = original.replace(original.trim(), () => fixed);
      states[key] = value;
      if (attribute) node.setAttribute(attribute, value);
      else node.data = value;
      return;
    }
    translate(source).then((output) => {
      if (!output) {
        if (states[key] === original) delete states[key];
        return;
      }
      if (!node.isConnected) return;
      const current = attribute ? node.getAttribute(attribute) : node.data;
      if (current !== original) return;
      const trimmed = original.trim();
      const value = original.replace(trimmed, () => output);
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
