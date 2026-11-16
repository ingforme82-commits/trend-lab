const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const crypto = require('node:crypto').webcrypto;
const source = fs.readFileSync(require('node:path').join(__dirname, '../presence.js'), 'utf8');

async function browser(options = {}) {
  const calls = [], storage = new Map(options.storage || []), timers = [];
  const element = () => ({ style: {}, append() {}, addEventListener() {} });
  const context = {
    crypto, Date, Uint8Array, JSON, Array, AbortSignal,
    window: {trlRtUrl: options.url ?? 'https://example-test.trycloudflare.com'},
    location: {hostname: options.host ?? 'ingforme82-commits.github.io'},
    navigator: options.navigator || {},
    document: {hidden: options.hidden || false, createElement: element, querySelector: element, addEventListener() {}, body: element()},
    localStorage: {getItem: k => storage.get(k) ?? null, setItem: (k,v) => storage.set(k,v)},
    fetch: async (url, request) => { calls.push({url, ...request}); return {ok:true}; },
    setInterval: fn => timers.push(fn), setTimeout: fn => timers.push(fn)
  };
  vm.runInNewContext(source, context);
  await timers.at(-1)();
  return {calls, storage, context, timers};
}

test('anonymous payload contains only random identifiers', async () => {
  const {calls} = await browser();
  assert.equal(calls.length, 1);
  const payload = JSON.parse(calls[0].body);
  assert.deepEqual(Object.keys(payload).sort(), ['browser', 'page']);
  assert.match(payload.browser, /^[a-f0-9]{32}$/);
  assert.equal(calls[0].credentials, 'omit');
  assert.equal(calls[0].referrerPolicy, 'no-referrer');
});
test('owner, opt-out, privacy signals, hidden and local screens excluded', async () => {
  for (const options of [{storage:[['trl-me','1']]}, {storage:[['trl-analytics-off','1']]}, {navigator:{globalPrivacyControl:true}}, {navigator:{doNotTrack:'1'}}, {hidden:true}, {host:'localhost'}, {url:'https://malicious.example'}]) {
    assert.equal((await browser(options)).calls.length, 0);
  }
});
test('same-day browser survives reload while page id changes', async () => {
  const a = await browser();
  const b = await browser({storage:[...a.storage]});
  const first = JSON.parse(a.calls[0].body), second = JSON.parse(b.calls[0].body);
  assert.equal(first.browser, second.browser);
  assert.notEqual(first.page, second.page);
});
