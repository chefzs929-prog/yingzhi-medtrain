/* RadioCheck · 知识库问答核心（征象 / 疾病 / 对比 / 指南）
 *
 * 数据源：kb/data/student_lab.json（构建后为 data/lab/student_lab.json）
 * 与 kb/app/student-lab.js 共用同一套词条与评分口径；本文件只做纯查询，不碰 DOM。
 *
 * 浏览器：挂到 window.QACore
 * Node：module.exports（供交叉验证）
 *
 * 边界：
 *   - 只回答库内词条；没有对应词条就返回 null，由调用方决定“没匹配到”。
 *   - 对比必须两个不同实体；同一实体去重后不足两个不进对比。
 *   - 治疗/诊断/非胸部等越界仍由 AskCore.scopeReason 统一拦截。
 */
(function (root) {
  "use strict";

  var HIT_FLOOR = { sign: 50, concept: 50, guideline: 40, case: 40 };
  var WEAK_FLOOR = { sign: 30, concept: 30, guideline: 24, case: 24 };

  function norm(s) {
    return String(s == null ? "" : s)
      .replace(/[，。？！、；：\s"'“”‘’（）()《》〈〉·\-—]/g, "")
      .toLowerCase();
  }

  function textScore(text, q, base) {
    var t = norm(text);
    if (!t || !q) return 0;
    if (t === q) return base + 30;
    if (t.indexOf(q) >= 0 || q.indexOf(t) >= 0) return base;
    return 0;
  }

  function scoreSign(s, q) {
    var sc = 0;
    sc = Math.max(sc, textScore(s.name, q, 80));
    sc = Math.max(sc, textScore(s.en, q, 60));
    (s.aliases || []).forEach(function (a) { sc = Math.max(sc, textScore(a, q, 70)); });
    sc = Math.max(sc, textScore(s.appearance, q, 30));
    (s.may_see_in || []).forEach(function (x) { sc = Math.max(sc, textScore(x, q, 24)); });
    (s.pitfalls || []).forEach(function (x) { sc = Math.max(sc, textScore(x, q, 22)); });
    (s.tags || []).forEach(function (x) { sc = Math.max(sc, textScore(x, q, 18)); });
    return sc;
  }

  function scoreConcept(c, q) {
    var sc = 0;
    sc = Math.max(sc, textScore(c.name, q, 76));
    sc = Math.max(sc, textScore(c.en, q, 58));
    (c.aliases || []).forEach(function (a) { sc = Math.max(sc, textScore(a, q, 72)); });
    sc = Math.max(sc, textScore(c.note, q, 24));
    return sc;
  }

  function scoreGuideline(g, q) {
    var sc = 0;
    sc = Math.max(sc, textScore(g.standard_name, q, 52));
    sc = Math.max(sc, textScore(g.category, q, 40));
    sc = Math.max(sc, textScore(g.statement, q, 34));
    (g.conditions || []).forEach(function (x) { sc = Math.max(sc, textScore(x, q, 24)); });
    var hay = norm([g.standard_name, g.category, g.statement, (g.conditions || []).join(" ")].join(" "));
    var terms = ["结节", "随访", "复查", "实性", "磨玻璃", "部分实性", "6mm", "8mm",
      "fleischner", "lung-rads", "lungrads", "指南", "低剂量"];
    terms.forEach(function (w) { if (q.indexOf(w) >= 0 && hay.indexOf(w) >= 0) sc += 10; });
    if (/随访|复查|指南/.test(q)) sc += 12;
    if (/fleischner/.test(q) && /fleischner/.test(hay)) sc += 30;
    if (/lung\s*-?\s*rads/.test(q) && /lung\s*-?\s*rads/.test(hay)) sc += 30;
    return sc;
  }

  function topHits(list, scorer, q) {
    return (list || []).map(function (x) { return { x: x, score: scorer(x, q) }; })
      .filter(function (h) { return h.score > 0; })
      .sort(function (a, b) { return b.score - a.score; });
  }

  function signById(data, id) {
    return ((data && data.signs) || []).filter(function (s) { return s.id === id; })[0] || null;
  }

  function conceptById(data, id) {
    return ((data && data.concepts) || []).filter(function (c) { return c.id === id; })[0] || null;
  }

  function casesForSigns(data, signIds, limit) {
    var out = [];
    var seen = {};
    var perCase = {};
    var wanted = {};
    (signIds || []).forEach(function (id) { wanted[id] = true; });
    ((data && data.cases) || []).forEach(function (c) {
      var zones = (c.zones || []).filter(function (z) {
        return (z.sign_ids || []).some(function (id) { return wanted[id]; });
      });
      zones.forEach(function (z) {
        if ((perCase[c.id] || 0) >= 2) return;
        perCase[c.id] = (perCase[c.id] || 0) + 1;
        var key = c.id + "|" + z.id;
        if (seen[key]) return;
        seen[key] = true;
        out.push({ case: c, zone: z });
      });
      if (!zones.length && (c.signs || []).some(function (id) { return wanted[id]; })) {
        var z = (c.zones || []).filter(function (x) { return x.status === "abnormal"; })[0] || null;
        var key = c.id + "|" + (z ? z.id : "none");
        if (!seen[key]) {
          seen[key] = true;
          out.push({ case: c, zone: z });
        }
      }
    });
    return out.slice(0, limit || 8);
  }

  function sourcesForSigns(data, signIds) {
    var seen = {};
    var out = [];
    (signIds || []).forEach(function (id) {
      var s = signById(data, id);
      if (!s) return;
      (s.sources || []).forEach(function (src) {
        if (!src || seen[src.id]) return;
        seen[src.id] = true;
        out.push(src);
      });
    });
    return out.slice(0, 8);
  }

  function guidelinesForSigns(data, signIds) {
    var names = (signIds || []).map(function (id) {
      var s = signById(data, id);
      return s ? s.name : "";
    }).filter(Boolean);
    if (!names.length) return [];
    var out = [];
    ((data && data.guidelines) || []).forEach(function (g) {
      var hay = norm([g.standard_name, g.category, g.statement, (g.conditions || []).join(" ")].join(" "));
      if (names.some(function (n) { return hay.indexOf(norm(n)) >= 0; })) out.push(g);
    });
    return out.slice(0, 4);
  }

  function relatedConcepts(data, signIds) {
    var set = {};
    (signIds || []).forEach(function (id) { set[id] = true; });
    return ((data && data.concepts) || []).filter(function (c) {
      return (c.sign_ids || []).some(function (id) { return set[id]; }) ||
        (c.related_sign_ids || []).some(function (id) { return set[id]; });
    }).slice(0, 8);
  }

  // 从问句里找库内实体；征象优先于疾病，同名去重。
  function mentionedEntities(data, q, limit) {
    var pool = [];
    ((data && data.signs) || []).forEach(function (s) { pool.push({ kind: "sign", x: s }); });
    ((data && data.concepts) || []).forEach(function (c) { pool.push({ kind: "concept", x: c }); });
    var hits = [];
    var seen = {};
    pool.forEach(function (e) {
      var names = [e.x.name, e.x.en].concat(e.x.aliases || []).map(norm).filter(function (n) { return n.length >= 2; });
      var pos = -1;
      var hitName = "";
      names.forEach(function (n) {
        var i = q.indexOf(n);
        if (i >= 0 && (pos < 0 || i < pos)) { pos = i; hitName = n; }
      });
      if (pos < 0) return;
      var key = norm(e.x.name);
      if (seen[key]) return;
      seen[key] = true;
      hits.push({ kind: e.kind, x: e.x, pos: pos, name: hitName });
    });
    hits.sort(function (a, b) { return a.pos - b.pos; });
    return hits.slice(0, limit || 2);
  }

  function intentOf(query) {
    var s = norm(query);
    if (!s) return "";
    if (/(区分|鉴别|区别|不同|vs|对比)/.test(s)) return "compare";
    if (/(怎么找|如何识别|怎么识别|怎么看出|怎么看|是什么|什么是|定义|表现|长什么样|影像表现|胸片表现|x线表现|征象|特点)/.test(s)) return "knowledge";
    return "";
  }

  function modalityNote(s) {
    var m = (s && s.modality) || [];
    if (!m.length) return "";
    var hasCR = m.indexOf("CR") >= 0 || m.indexOf("X线") >= 0 || m.indexOf("DR") >= 0;
    if (hasCR) return "";
    if (m.indexOf("CT") >= 0) return "该征象的定义主要来自 CT 术语；胸片上的可辨识度有限，需结合 CT 判断。";
    return "该征象的定义来自 " + m.join(" / ") + "；不是胸片征象，本工具只作术语对照。";
  }

  function entityView(s) {
    return {
      id: s.id,
      name: s.name,
      appearance: s.appearance || s.note || "该词条暂无形态描述",
      pitfalls: (s.pitfalls || []).slice(0, 3),
      modality: s.modality || [],
    };
  }

  function buildCompare(data, ents, query) {
    var a = ents[0], b = ents[1];
    var idsOf = function (s) { return (s.sign_ids && s.sign_ids.length) ? s.sign_ids : [s.id]; };
    var ids = [];
    [a, b].forEach(function (e) {
      idsOf(e.x).forEach(function (id) { if (ids.indexOf(id) < 0) ids.push(id); });
    });
    var casesOut = [];
    var seen = {};
    ids.forEach(function (id) {
      casesForSigns(data, [id], 2).forEach(function (e) {
        var key = e.case.id + "|" + (e.zone ? e.zone.id : "none");
        if (seen[key]) return;
        seen[key] = true;
        casesOut.push(e);
      });
    });
    var av = entityView(a.x), bv = entityView(b.x);
    var notes = [];
    [av, bv].forEach(function (v) {
      var n = modalityNote({ modality: v.modality });
      if (n) notes.push(v.name + "：" + n);
    });
    return {
      kind: "compare",
      intent: "compare",
      query: String(query || "").trim(),
      hit: { name: av.name + " vs " + bv.name },
      entities: [av, bv],
      signIds: ids,
      cases: casesOut,
      sources: sourcesForSigns(data, ids),
      guidelines: guidelinesForSigns(data, ids),
      concepts: relatedConcepts(data, ids),
      conclusion: av.name + "：" + av.appearance + " " + bv.name + "：" + bv.appearance +
        " 鉴别时不要只看一个征象：" + av.name + " 的易错点——" + (av.pitfalls.join("；") || "暂未列出") +
        "；" + bv.name + " 的易错点——" + (bv.pitfalls.join("；") || "暂未列出") + "。",
      missing: notes.concat([
        "对比只并列知识库中的定义、位置与易错点，不是诊断路径。",
        "同一病例可能同时挂两个征象；以该区逐区标注和原始出处为准。",
      ]),
    };
  }

  function buildEntity(data, ent, query) {
    var x = ent.x;
    if (ent.kind === "sign") {
      var signIds = [x.id];
      var note = modalityNote(x);
      var missing = [];
      if (note) missing.push(note);
      var casesOut = casesForSigns(data, signIds, 6);
      if (!casesOut.length) missing.push("当前影像库中暂时没有直接标注该征象的分区，只能给出词条与文献。");
      if (!sourcesForSigns(data, signIds).length) missing.push("相关词条没有登记可引用的文献来源，因此不补造出处。");
      return {
        kind: "sign",
        intent: "knowledge",
        query: String(query || "").trim(),
        hit: { id: x.id, name: x.name },
        entities: [entityView(x)],
        signIds: signIds,
        cases: casesOut,
        sources: sourcesForSigns(data, signIds),
        guidelines: guidelinesForSigns(data, signIds),
        concepts: relatedConcepts(data, signIds),
        conclusion: x.name + "：" + (x.appearance || "该词条暂无形态描述"),
        missing: missing,
      };
    }
    // concept
    var direct = (x.sign_ids || []).filter(function (id) { return signById(data, id); });
    var related = (x.related_sign_ids || []).filter(function (id) { return signById(data, id); });
    var ids = direct.concat(related.filter(function (id) { return direct.indexOf(id) < 0; }));
    var names = direct.map(function (id) { return signById(data, id).name; });
    var relNames = related.map(function (id) { return signById(data, id).name; });
    var cMissing = [];
    if (!direct.length) cMissing.push("该疾病在知识库中没有直接对应的征象，只有关联征象；关联只作参考，不作为直接依据。");
    if (!sourcesForSigns(data, ids).length) cMissing.push("相关词条没有登记可引用的文献来源，因此不补造出处。");
    var cConclusion = names.length
      ? x.name + " 在知识库中对应的征象：" + names.join("、")
      : x.name + " 在知识库中没有直接对应的征象";
    if (relNames.length) cConclusion += "；可参考关联征象：" + relNames.join("、") + "（仅作参考，不作为直接依据）";
    if (x.note) cConclusion += "。" + x.note;
    return {
      kind: "concept",
      intent: "knowledge",
      query: String(query || "").trim(),
      hit: { id: x.id, name: x.name },
      entities: [entityView(x)],
      signIds: ids,
      cases: casesForSigns(data, ids, 6),
      sources: sourcesForSigns(data, ids),
      guidelines: /结节|随访|指南/.test(norm(query)) ? guidelinesForSigns(data, ids) : [],
      concepts: [],
      conclusion: cConclusion,
      missing: cMissing,
    };
  }

  // 只处理“是什么 / 怎么找 / 怎么区分”这类知识型问法；病例型问句返回 null。
  function intentAnswer(data, query) {
    var q = norm(query);
    if (!q) return null;
    var intent = intentOf(query);
    if (intent === "compare") {
      var two = mentionedEntities(data, q, 2);
      if (two.length < 2) return null;
      if (norm(two[0].x.name) === norm(two[1].x.name)) return null;
      return buildCompare(data, two, query);
    }
    if (intent === "knowledge") {
      var one = mentionedEntities(data, q, 1);
      if (!one.length) return null;
      return buildEntity(data, one[0], query);
    }
    return null;
  }

  var api = {
    norm: norm,
    intentOf: intentOf,
    intentAnswer: intentAnswer,
    mentionedEntities: mentionedEntities,
    buildCompare: buildCompare,
    buildEntity: buildEntity,
    signById: signById,
    conceptById: conceptById,
    casesForSigns: casesForSigns,
    sourcesForSigns: sourcesForSigns,
    guidelinesForSigns: guidelinesForSigns,
    relatedConcepts: relatedConcepts,
    HIT_FLOOR: HIT_FLOOR,
    WEAK_FLOOR: WEAK_FLOOR,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.QACore = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
