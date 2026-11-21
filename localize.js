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
    if (Array.isArray(entries)) saved = entries.filter((entry) =>
      Array.isArray(entry) && typeof entry[0] === "string" && typeof entry[1] === "string"
    ).slice(-CACHE_MAX);
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
      const extra = new URLSearchParams({ q: "\n" + item.text }).toString().length;
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
  "달러": "USD",
  // 11/21 운영자 "추세 추종 차트도 영어로 바꾸었을 때 표시 문제 없나": 기계번역이 틀리던 카드 문구(선물→gift, 프리→free, 5일선→front line, 넥장→Neck length 등)
  "애프터": "After-hours",
  "프리": "Pre-market",
  "선물": "Futures",
  "선물 {0}시간": "Futures {0}h",
  "현재 세션 등락률 높은 순": "Sorted by current-session change",
  "시간외 · 애프터마켓": "Extended · After hours",
  "시간외 · 프리마켓": "Extended · Premarket",
  "시간외 · 애프터마켓 · 마지막 · {0}": "Extended · After hours · last · {0}",
  "시간외 · 프리마켓 · 마지막 · {0}": "Extended · Premarket · last · {0}",
  "시간외 · 애프터마켓 · {0}": "Extended · After hours · {0}",
  "시간외 · 프리마켓 · {0}": "Extended · Premarket · {0}",
  "정규장 · {0}": "Regular session · {0}",
  "정규장 · 마지막 · {0}": "Regular session · last · {0}",
  "마감 · 마지막 · {0}": "Closed · last · {0}",
  "마감 · 마지막": "Closed · last",
  "KRX 종가 · 기준가": "KRX close · reference",
  "통합 종가 · 넥장 {0}시": "Combined close · NXT {0}:00",
  "KRX 정규장 진행 중": "KRX regular session live",
  "넥장 애프터마켓 · 지금": "NXT after-hours · now",
  "넥장 프리마켓 · 지금": "NXT premarket · now",
  "넥장 시간외": "NXT extended hours",
  "오늘 체결 없음": "No trades today",
  "애프터마켓 · 지금": "After hours · now",
  "프리마켓 · 지금": "Premarket · now",
  "시세 확인 중": "Checking quotes",
  "전일 정규장 종가": "Prior regular-session close",
  "종가 대비": "vs. close",
  "KRX 종가 대비": "vs. KRX close",
  "{0}일선 통합": "{0}-day MA combined",
  "KRX": "KRX",
  "{0}/{1}": "{0}/{1}",
  "없음(최근 고점 위)": "None (above recent high)",
  "없음": "None",
  "오늘 고가가 닿고 밀린 선:": "Today's high was rejected at:",
  "오늘 저가를 받친 선:": "Today's low held at:",
  "{0}/{1} · {2}/{3} 저점 · 하단 위": "{0}/{1} · {2}/{3} lows · above floor",
  "{0}/{1} · {2}/{3} 저점 · 하단 이탈": "{0}/{1} · {2}/{3} lows · below floor",
  "{0}/{1} · {2}/{3} 저점 · 구간 안": "{0}/{1} · {2}/{3} lows · inside band",
  "최근 고점 위": "Above recent high",
  "일봉·하락 채널·{0}일선": "Daily · downtrend channel · {0}-day MA",
  "오늘 봉에 돌파": "Broke out on today's bar",
  "수평 하단 기준": "Horizontal floor level",
  "수평 저항·지지": "Horizontal resistance · support",
  "오늘 고가가 닿고 밀린 선": "Today's high was rejected at",
  "오늘 저가를 받친 선": "Today's low held at",
  "양봉": "Bullish candle",
  "음봉": "Bearish candle",
  "장대양봉": "Long bullish candle",
  "장대음봉": "Long bearish candle",
  "도지 — 방향 탐색": "Doji — indecision",
  "망치형 — 아래꼬리(저가 매수 유입)": "Hammer — long lower wick (dip buying)",
  "윗꼬리 — 위에서 매도": "Upper wick — selling from above",
  "돌파 관찰": "Breakout watch",
  "돌파 전": "Before breakout",
  "돌파 시그널": "Breakout signal",
  "돌파 확정": "Breakout confirmed",
  "돌파 시그널·확정": "Breakout signal · confirmed",
  "돌파 시도(세션 참고)": "Breakout attempt (session-based)",
  "{0}일선 돌파 실패(채널 상단과 겹침)": "Failed at {0}-day MA (overlaps channel ceiling)",
  "{0}일선 위로(돌파 전)": "Back above {0}-day MA (pre-breakout)",
  "{0}일선 저항": "{0}-day MA resistance",
  "{0}일선 저항(채널 상단과 겹침)": "{0}-day MA resistance (overlaps channel ceiling)",
  "채널 상단 돌파 실패": "Failed at channel ceiling",
  "채널 상단 저항": "Channel ceiling resistance",
  "하락 시그널 · {0}일선 이탈": "Sell signal · lost {0}-day MA",
  "하락 시그널 · 채널 하단 이탈": "Sell signal · broke channel floor",
  "⚡ 돌파·저항 시그널": "⚡ Breakout · resistance signals",
  "돌파 관찰: {0}일선 위·채널 상단 {1}% 이내 · 종가와 이후 지지 확인": "Breakout watch: above {0}-day MA, within {1}% of channel ceiling · confirm on close and follow-through support",
  "{0}분봉 시세 대기": "Awaiting {0}-minute quotes",
  "공모가 위 · 첫 시가 아래": "Above IPO price · below first open",
  "인버스 · 숏": "Inverse · Short",
  "지수 선물": "Index futures",
  "메모리": "Memory",
  "메모리 반도체": "Memory chips",
  "반도체 · 레버리지": "Semiconductors · Leveraged",
  "파운드리": "Foundry",
  "AI 대장": "AI leaders",
  "코스피·코스닥 지수": "KOSPI · KOSDAQ",
  "전자부품 · MLCC·기판": "Electronic parts · MLCC · substrates",
  "SK스퀘어": "SK Square",
  "삼성전기": "Samsung Electro-Mechanics",
  "SK하이닉스 ADR": "SK hynix ADR",
  "NVDQ 엔비디아 인버스 {0}배": "NVDQ NVIDIA inverse {0}x",
  "SQQQ 나스닥{0} 인버스 {1}배": "SQQQ Nasdaq-{0} inverse {1}x",
  "SKDD SK하이닉스 인버스 {0}배": "SKDD SK hynix inverse {0}x",
  "SOXL 반도체 {0}배": "SOXL semiconductors {0}x",
  "KORU 한국 {0}배": "KORU Korea {0}x",
  "나스닥{0} 선물": "Nasdaq-{0} futures",
  "S&P{0} 선물": "S&P {0} futures",
  "TSMC ADR": "TSMC ADR",
  "키옥시아": "Kioxia",
  "무라타제작소": "Murata Manufacturing",
  "다이요유덴": "Taiyo Yuden",
  "이비덴": "Ibiden",
  "금 선물": "Gold futures",
  "한국": "Korea",
  "미국": "U.S.",
  "일본": "Japan"
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

  // 시장 용어: 기계번역이 엉뚱하게 옮기는 낱말을 보내기 전에 영어로 바꿔 둔다(긴 말부터)
  const TERMS = [["장대양봉", "long bullish candle"], ["장대음봉", "long bearish candle"], ["프리마켓", "premarket"], ["애프터마켓", "after-hours"],
    ["정규장", "regular session"], ["시간외", "extended hours"], ["넥스트레이드", "Nextrade"], ["넥장", "NXT"], ["분봉", "-minute candles"],
    ["일선", "-day MA"], ["양봉", "bullish candle"], ["음봉", "bearish candle"], ["선물", "futures"], ["체결", "trades"], ["기준가", "reference price"]];
  function preTerms(text) {
    if (language !== "en") return text;
    let out = text;
    for (const [ko, en] of TERMS) out = out.split(ko).join(" " + en + " ");
    return out.replace(/(\d) -/g, "$1-").replace(/\s+/g, " ").trim();
  }

  async function translate(raw) {
    const source = preTerms(raw);
    if (!/[가-힣]/.test(source)) return source;
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
    if (!node.isConnected) return;
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
      if (value === original) return;
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
      if (current !== original || states[key] !== original) return;
      const trimmed = original.trim();
      const value = original.replace(trimmed, () => output);
      states[key] = value;
      if (attribute) node.setAttribute(attribute, value);
      else node.data = value;
    });
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

  // Yield between small batches so market rendering and input can run.
  const work = new Map();
  let active;
  let timer;
  function enqueue(node, attribute = null) {
    if (node?.nodeType !== 1 && node?.nodeType !== 3) return;
    const entry = work.get(node);
    if (!entry || attribute === null || entry.attribute !== null) {
      work.set(node, { node, attribute: entry && entry.attribute !== attribute ? null : attribute });
    }
    if (!timer) timer = setTimeout(flush, 0);
  }

  function visit(node, attribute) {
    const element = node.nodeType === 3 ? node.parentElement : node;
    if (!element || element.closest(excluded)) return;
    if (node.nodeType === 3) translateValue(node);
    else {
      if ((!attribute || attribute === "href") && node.matches("a[href]")) preserveLanguage(node);
      for (const name of ["title", "aria-label", "alt"]) {
        if (!attribute || attribute === name) translateValue(node, name);
      }
    }
  }

  function flush() {
    timer = null;
    const deadline = performance.now() + 5;
    for (let count = 0; count < 100 && performance.now() < deadline; count++) {
      if (!active) {
        const next = work.values().next().value;
        if (!next) break;
        work.delete(next.node);
        if (!next.node.isConnected) continue;
        visit(next.node, next.attribute);
        if (!next.attribute && next.node.nodeType === 1 && !next.node.closest(excluded)) {
          active = document.createTreeWalker(next.node, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
        }
        continue;
      }
      const node = active.currentNode.isConnected ? active.nextNode() : null;
      if (node) visit(node);
      else active = null;
    }
    if (active || work.size) timer = setTimeout(flush, 0);
  }

  enqueue(document.body);
  enqueue(document.querySelector("title"));
  new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === "attributes") enqueue(record.target, record.attributeName);
      else if (record.type === "characterData") enqueue(record.target);
      else for (const node of record.addedNodes) enqueue(node);
    }
  }).observe(document.documentElement, {
    childList: true, subtree: true, characterData: true, attributes: true,
    attributeFilter: ["href", "title", "aria-label", "alt"],
  });
})();
