const test = require('node:test');
const assert = require('node:assert/strict');
const flow = require('../flow-core.js');
test('clock skew, missing values, stale and fresh receipts differ', () => {
  assert.equal(flow.quoteState({px:10,at:100000},110000),'recent');
  assert.equal(flow.quoteState({px:10,at:100000},116000),'delayed');
  assert.equal(flow.quoteState({px:10,at:120000},110000),'clock');
  assert.equal(flow.quoteState({px:10},110000),'unknown');
});
test('receipt time is never synthesized from publication', () => {
  assert.equal(flow.newsTiming({ts:1000},5000).collectSeconds,null);
  assert.equal(flow.newsTiming({ts:5000,got:1000},6000).collectSeconds,null);
  assert.equal(flow.newsTiming({ts:1000,got:2500},5000).collectSeconds,1.5);
});
test('daily direction uses actual reference and is not a trend signal', () => {
  assert.equal(flow.dailyDirection({px:90,prev:100}),-9.999999999999998);
  assert.equal(flow.dailyDirection({px:90}),null);
  assert.equal(flow.dailyDirection({px:90,prev:0}),null);
});
