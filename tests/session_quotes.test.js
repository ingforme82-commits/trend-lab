const fs = require("fs"), assert = require("assert");
const src = fs.readFileSync(__dirname + "/../news.js", "utf8").replace(/\r\n/g, "\n");
const code = src.match(/function sessionQuotesHtml\(\) \{[\s\S]*?\n  \}\n/)[0];
const quotes = JSON.parse(fs.readFileSync(__dirname + "/../data/session_quotes.json", "utf8"));
const date = new Date("2026-11-02T15:00:00+09:00").getTime();
const render = (data, now = date) => new Function("sessionQuotes", "Date", "esc", "cls", "md2", "hm", code + "return sessionQuotesHtml();")(
  data, { now: () => now, parse: Date.parse }, String, () => "c-up", () => "11/2", () => "14:42");
const html = render(quotes);
for (const text of ["KORU", "SOXL", "$11.98", "$82.34", "+12.70%", "+6.87%", "+$1.35", "+$5.29", "수동 캡처", "이전 애프터마켓", "14:42"]) assert(html.includes(text), text);
assert.strictEqual(render(null), "");
assert.strictEqual(render(quotes, Date.parse("2026-11-03T00:00:00+09:00")), "");
console.log("session_quotes.test.js OK");
