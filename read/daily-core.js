/* 今日查房：与 kb/scripts/daily_brief.py 同一套确定性算法。
   同一天在任何设备、任何时间算出的结果完全一致，不依赖网络定时任务。 */
(function (root) {
  var DAY = 86400000;

  function daysSince(iso, epoch) {
    var a = String(iso).split("-").map(Number);
    var b = String(epoch).split("-").map(Number);
    return Math.round((Date.UTC(a[0], a[1] - 1, a[2]) - Date.UTC(b[0], b[1] - 1, b[2])) / DAY);
  }

  function rel(i) {
    return (i.citation && i.citation.relevance_score) || 0;
  }

  function num(q) {
    return parseInt(String(q).slice(1), 10);
  }

  function mod(n, m) {
    return ((n % m) + m) % m;
  }

  function pick(D, iso) {
    var d = daysSince(iso, D.epoch);
    var order = D.topics && D.topics.length ? D.topics : D.topic_order.filter(function (t) {
      return D.items.some(function (i) { return i.topic_id === t; });
    });
    var n = order.length;
    var topic = order[mod(d, n)];

    var byCase = {};
    D.items.forEach(function (i) {
      if (i.topic_id !== topic || i.main === false) return;
      var p = byCase[i.case_id];
      if (!p || rel(i) > rel(p) || (rel(i) === rel(p) && num(i.qid) < num(p.qid))) {
        byCase[i.case_id] = i;
      }
    });
    var keys = Object.keys(byCase).sort();
    var focus = byCase[keys[mod(Math.floor(d / n), keys.length)]];

    var ct = D.confusion[topic];
    var pool = D.items
      .filter(function (i) { return i.topic_id === ct && i.citation && i.case_id !== focus.case_id; })
      .sort(function (a, b) {
        if (a.case_id !== b.case_id) return a.case_id < b.case_id ? -1 : 1;
        return num(a.qid) - num(b.qid);
      });
    var contrast = pool.length ? pool[mod(d, pool.length)] : null;

    return {
      day: d,
      topic: topic,
      topic_cn: (D.topic_cn && D.topic_cn[topic]) || topic,
      focus: focus,
      contrast: contrast,
      topics: order
    };
  }

  root.DailyBrief = { pick: pick, daysSince: daysSince };
})(window);
