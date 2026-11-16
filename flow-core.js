"use strict";
(function(root) {
  const finite = value => typeof value === "number" && Number.isFinite(value);
  function quoteState(row, now = Date.now()) {
    if (!row || !finite(row.px) || row.px <= 0 || !finite(row.at) || row.at <= 0) return "unknown";
    if (row.at > now + 1000) return "clock";
    return now - row.at <= 15000 ? "recent" : "delayed";
  }
  function newsTiming(row, now = Date.now()) {
    const published = finite(row?.ts) && row.ts > 0 ? row.ts : null;
    const received = finite(row?.got) && row.got > 0 ? row.got : null;
    return {published, received,
      collectSeconds: published && received && received >= published && received <= now + 1000 ? (received - published) / 1000 : null};
  }
  function dailyDirection(row) {
    if (!row || !finite(row.px) || row.px <= 0 || !finite(row.prev) || row.prev <= 0) return null;
    return (row.px / row.prev - 1) * 100;
  }
  const api = {quoteState, newsTiming, dailyDirection};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.TRLFlow = api;
})(typeof window === "undefined" ? globalThis : window);
