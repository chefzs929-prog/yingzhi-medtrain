/* RadHearing 问答匹配核心（JS 唯一实现）。
 *
 * 与 kb/scripts/ask_engine.py 逐行对齐。
 * 浏览器：挂到 window.AskCore
 * Node：module.exports（供 crosscheck.py 做交叉验证）
 */
(function (root) {
  "use strict";

  var STOP = new Set(["有没有", "什么", "这张", "片子", "问题", "吗", "有吗", "怎样", "怎么"]);
  var THR_ANSWER = 0.32;
  var THR_REFUSE = 0.25;
  var ZONE_KEY = { RUL: "右上", RML: "右中", RLL: "右下", LUL: "左上", LML: "左中", LLL: "左下" };

  function norm(s) {
    return String(s == null ? "" : s).replace(/[，。？！、；：\s"'“”‘’]/g, "").toLowerCase();
  }

  function bigrams(s) {
    var r = [];
    for (var i = 0; i < s.length - 1; i++) r.push(s.slice(i, i + 2));
    return r;
  }

  function dice(a, b) {
    var A = bigrams(a), B = bigrams(b);
    if (!A.length || !B.length) return 0;
    var m = new Map();
    A.forEach(function (x) { m.set(x, (m.get(x) || 0) + 1); });
    var hit = 0;
    B.forEach(function (x) {
      var c = m.get(x) || 0;
      if (c > 0) { hit++; m.set(x, c - 1); }
    });
    return (2 * hit) / (A.length + B.length);
  }

  function parseRegion(q) {
    var side = q.indexOf("右") >= 0 ? "右" : (q.indexOf("左") >= 0 ? "左" : "");
    var m = q.match(/(上|中|下)\s*(野|部|叶|面|头|半|方|肺野|间|段)/);
    if (!m) return side;
    return side + m[1];
  }

  function scoreOf(query, item) {
    var nq = norm(query);
    var text = norm(item.question + " " + (item.keywords || []).join(" "));
    var s = dice(nq, text);

    (item.keywords || []).forEach(function (k) {
      var nk = norm(k);
      if (nk.length >= 2 && !STOP.has(nk) && nq.indexOf(nk) >= 0) s += 0.18;
    });

    var aliases = item.aliases || [];
    for (var i = 0; i < aliases.length; i++) {
      var na = norm(aliases[i]);
      if (na.length >= 2 && nq.indexOf(na) >= 0) { s += 0.5; break; }
    }

    var qk = parseRegion(nq);
    if (qk) {
      var zk = ZONE_KEY[(item.region || {}).zone_id] || "";
      if (zk) {
        var all = true;
        for (var j = 0; j < qk.length; j++) {
          if (zk.indexOf(qk[j]) < 0) { all = false; break; }
        }
        if (all) s += 0.45;
      }
    }

    var reg = item.region;
    if (reg && reg.label) {
      var nl = norm(reg.label);
      if (nl && nq.indexOf(nl) >= 0) s += 0.28;
    }
    return s;
  }

  function poolOf(caseId, items) {
    return items.filter(function (it) {
      return caseId == null || it.case_id == null || it.case_id === caseId;
    });
  }

  function best(q, caseId, items) {
    var pool = poolOf(caseId, items);
    var top = null, ts = 0;
    pool.forEach(function (it) {
      var s = scoreOf(q, it);
      if (s > ts) { ts = s; top = it; }
    });
    return { item: top, score: ts };
  }

  function classify(q, caseId, items) {
    var r = best(q, caseId, items);
    if (!r.item) return { kind: "unknown", score: r.score, item: null };
    if (!r.item.answerable) {
      return { kind: r.score >= THR_REFUSE ? "refusal" : "unknown", score: r.score, item: r.item };
    }
    if (r.score < THR_ANSWER) return { kind: "unknown", score: r.score, item: r.item };
    return { kind: r.item.kind, score: r.score, item: r.item };
  }

  var api = {
    norm: norm,
    bigrams: bigrams,
    dice: dice,
    parseRegion: parseRegion,
    scoreOf: scoreOf,
    best: best,
    classify: classify,
    STOP: STOP,
    ZONE_KEY: ZONE_KEY,
    THR_ANSWER: THR_ANSWER,
    THR_REFUSE: THR_REFUSE,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.AskCore = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
