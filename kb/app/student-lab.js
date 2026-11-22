/* RadioCheck · 学生影像实验室
 * 影像库问答（区域定位 + 文献溯源双引用）、读片陪练、自测出题器。
 *
 * 依赖：
 *   classroom-core.js  RCClass（班级、学生、评分）
 *   ../data/lab/student_lab.json  21 例胸片索引与规则题
 *
 * 边界：
 *   - 只覆盖 21 例 CR 胸部；问答只在库内检索，不调用大模型。
 *   - 越界（诊断/治疗/预后/操作）、低置信、库外未命中一律拒答；不编造 id。
 *   - 文献引用到来源级 + 段落级摘要锚点；原文页码待补。
 *   - 自测题为库内逐区标注规则生成，不是考试真题。
 */
(function () {
  "use strict";

  const RC = window.RCClass;
  const DATA_URL = "../data/lab/student_lab.json";
  const HISTORY_KEY = "radiocheck.studentlab.v1";
  const STATUS = { abnormal: "异常", normal: "未见异常", unmentioned: "来源未提及", limited: "判读受限" };
  const KIND_LABEL = { sign: "征象词条", concept: "疾病 / 病理概念", guideline: "指南条款", case: "病例", compare: "对比检索", report: "报告文本映射", general: "未命中" };
  // 越界词：只做影像表现与出处对照，不提供诊断/治疗/预后/操作建议。
  const SCOPE_WORDS = [
    "治疗", "手术", "用药", "药物", "剂量", "化疗", "放疗", "靶向", "免疫治疗",
    "预后", "生存期", "能活多久", "活多久", "分期", "处方", "急救", "抢救",
    "住院", "出院", "引流", "穿刺", "活检", "要不要做", "需要做", "建议做",
    "严重吗", "会死吗",
  ];
  const SCOPE_SUGGESTIONS = ["气胸在胸片上怎么找", "实变和胸腔积液怎么区分", "这个分区标注的依据是什么"];
  const HIT_FLOOR = { sign: 50, concept: 50, guideline: 40, case: 40 };
  const WEAK_FLOOR = { sign: 30, concept: 30, guideline: 24, case: 24 };
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  const L = {
    data: null,
    tab: "qa",
    qa: { query: "", result: null, reportText: "" },
    coach: { caseId: "", step: 1, zoneId: "", status: "", signs: [], touched: false, hint: 0, revealed: false, result: null },
    quiz: { paper: null, result: null, timer: null, config: { scope: "all", type: "mixed", count: 10, minutes: 0 } },
    history: { practice: [], quizzes: [] },
  };
  let loading = null;

  function toast(msg) {
    if (window.YZCommon && window.YZCommon.toast) window.YZCommon.toast(msg);
    else if (window.RCClass && window.RCClass.toast) window.RCClass.toast(msg);
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16).replace("T", " ");
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function fmtLeft(ms) {
    const s = Math.max(0, Math.ceil(ms / 1000));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  }

  function shuffle(list) {
    const a = list.slice();
    for (let i = a.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function loadHistory() {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      if (!raw) return { practice: [], quizzes: [] };
      const v = JSON.parse(raw);
      return {
        practice: Array.isArray(v.practice) ? v.practice.slice(0, 30) : [],
        quizzes: Array.isArray(v.quizzes) ? v.quizzes.slice(0, 20) : [],
      };
    } catch (e) {
      return { practice: [], quizzes: [] };
    }
  }

  function saveHistory() {
    try {
      L.history.practice = L.history.practice.slice(0, 30);
      L.history.quizzes = L.history.quizzes.slice(0, 20);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(L.history));
    } catch (e) { /* ignore */ }
  }

  function recordPractice(row) {
    L.history.practice.unshift(Object.assign({ at: new Date().toISOString() }, row));
    saveHistory();
  }

  function recordQuiz(row) {
    L.history.quizzes.unshift(Object.assign({ at: new Date().toISOString() }, row));
    saveHistory();
  }

  function download(name, text) {
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function load() {
    if (L.data) return Promise.resolve(L.data);
    if (loading) return loading;
    loading = fetch(DATA_URL, { cache: "no-cache" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        L.data = d;
        return d;
      })
      .catch((e) => {
        loading = null;
        throw e;
      });
    return loading;
  }

  function cases() { return (L.data && L.data.cases) || []; }
  function caseById(id) { return cases().find((c) => c.id === id) || null; }
  function signById(id) { return ((L.data && L.data.signs) || []).find((s) => s.id === id) || null; }
  function sourceById(id) { return ((L.data && L.data.sources) || []).find((s) => s.id === id) || null; }
  function imagePath(p) { return p ? "../" + String(p).replace(/^\.\.\//, "") : ""; }
  function signName(id) { const s = signById(id); return s ? s.name : id; }

  function zoneOf(c, zoneId) {
    if (!c) return null;
    return (c.zones || []).find((z) => z.id === zoneId) || null;
  }

  function statusLabel(status) { return STATUS[status] || "未标注"; }

  function bboxStyle(coords) {
    if (!Array.isArray(coords) || coords.length !== 4) return "";
    const [x, y, w, h] = coords;
    return `left:${(x * 100).toFixed(2)}%;top:${(y * 100).toFixed(2)}%;width:${(w * 100).toFixed(2)}%;height:${(h * 100).toFixed(2)}%`;
  }

  /* ==================== 问答检索 ==================== */

  function norm(s) {
    return String(s || "").toLowerCase()
      .replace(/[，。？！、；：""''（）()【】\[\]《》<>]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function scopeReason(q) {
    const s = norm(q);
    if (!s) return "";
    if (SCOPE_WORDS.some((w) => s.includes(norm(w)))) return "治疗 / 预后 / 操作建议";
    if (/(诊断|确诊|是不是癌|是不是肿瘤|什么病)/.test(s) &&
        !/(依据|标准|怎么找|表现|征象|鉴别|区分)/.test(s)) return "诊断结论";
    return "";
  }

  function textScore(text, q, base) {
    const t = norm(text);
    if (!t || !q) return 0;
    if (t === q) return base + 30;
    if (t.includes(q) || q.includes(t)) return base;
    return 0;
  }

  function scoreSign(s, q) {
    let sc = 0;
    sc = Math.max(sc, textScore(s.name, q, 80));
    sc = Math.max(sc, textScore(s.en, q, 60));
    (s.aliases || []).forEach((a) => { sc = Math.max(sc, textScore(a, q, 70)); });
    sc = Math.max(sc, textScore(s.appearance, q, 30));
    (s.may_see_in || []).forEach((x) => { sc = Math.max(sc, textScore(x, q, 24)); });
    (s.pitfalls || []).forEach((x) => { sc = Math.max(sc, textScore(x, q, 22)); });
    (s.tags || []).forEach((x) => { sc = Math.max(sc, textScore(x, q, 18)); });
    return sc;
  }

  function scoreConcept(c, q) {
    let sc = 0;
    sc = Math.max(sc, textScore(c.name, q, 76));
    sc = Math.max(sc, textScore(c.en, q, 58));
    (c.aliases || []).forEach((a) => { sc = Math.max(sc, textScore(a, q, 72)); });
    sc = Math.max(sc, textScore(c.note, q, 24));
    return sc;
  }

  function scoreGuideline(g, q) {
    let sc = 0;
    sc = Math.max(sc, textScore(g.standard_name, q, 52));
    sc = Math.max(sc, textScore(g.category, q, 40));
    sc = Math.max(sc, textScore(g.statement, q, 34));
    (g.conditions || []).forEach((x) => { sc = Math.max(sc, textScore(x, q, 24)); });
    return sc;
  }

  function scoreCase(c, q) {
    let sc = textScore(c.title, q, 58);
    (c.sign_names || []).forEach((x) => { sc = Math.max(sc, textScore(x, q, 34)); });
    return sc;
  }

  function topHits(list, scorer, q) {
    return list.map((x) => ({ x, score: scorer(x, q) }))
      .filter((h) => h.score > 0)
      .sort((a, b) => b.score - a.score);
  }

  function casesForSigns(signIds, limit) {
    const out = [];
    const seen = new Set();
    const perCase = new Map();
    const wanted = new Set(signIds || []);
    cases().forEach((c) => {
      const zones = (c.zones || []).filter((z) => (z.sign_ids || []).some((id) => wanted.has(id)));
      zones.forEach((z) => {
        if ((perCase.get(c.id) || 0) >= 2) return;
        perCase.set(c.id, (perCase.get(c.id) || 0) + 1);
        const key = c.id + "|" + z.id;
        if (seen.has(key)) return;
        seen.add(key);
        out.push({ case: c, zone: z });
      });
      if (!zones.length && (c.signs || []).some((id) => wanted.has(id))) {
        const z = (c.zones || []).find((x) => x.status === "abnormal") || null;
        const key = c.id + "|" + (z ? z.id : "none");
        if (!seen.has(key)) {
          seen.add(key);
          out.push({ case: c, zone: z });
        }
      }
    });
    return out.slice(0, limit || 8);
  }

  function sourcesForSigns(signIds) {
    const seen = new Set();
    const out = [];
    (signIds || []).forEach((id) => {
      const s = signById(id);
      if (!s) return;
      (s.sources || []).forEach((src) => {
        if (!src || seen.has(src.id)) return;
        seen.add(src.id);
        out.push(src);
      });
    });
    return out.slice(0, 8);
  }

  function guidelinesForSigns(signIds) {
    const names = (signIds || []).map(signName).filter(Boolean);
    if (!names.length) return [];
    const out = [];
    ((L.data && L.data.guidelines) || []).forEach((g) => {
      const hay = norm([g.standard_name, g.category, g.statement, (g.conditions || []).join(" ")].join(" "));
      if (names.some((n) => hay.includes(norm(n))) || (hay.includes("结节") && names.includes("结节"))) {
        out.push(g);
      }
    });
    return out.slice(0, 4);
  }

  function relatedConcepts(signIds) {
    const set = new Set(signIds || []);
    return ((L.data && L.data.concepts) || []).filter((c) =>
      (c.sign_ids || []).some((id) => set.has(id)) || (c.related_sign_ids || []).some((id) => set.has(id))
    ).slice(0, 8);
  }

  function buildCompare(q, signs, rawQuery) {
    const ids = signs.map((s) => s.id);
    const seen = new Set();
    const casesOut = [];
    ids.forEach((id) => {
      casesForSigns([id], 2).forEach((e) => {
        const key = e.case.id + "|" + (e.zone ? e.zone.id : "none");
        if (seen.has(key)) return;
        seen.add(key);
        casesOut.push(e);
      });
    });
    const guidelines = guidelinesForSigns(ids);
    const sources = sourcesForSigns(ids);
    const relation = {};
    ids.forEach((id) => { relation[id] = "direct"; });
    const a = signs[0];
    const b = signs[1];
    const pitfalls = (s) => (s.pitfalls || []).slice(0, 2).join("；") || "库内未列易错点";
    return {
      kind: "compare",
      tier: "hit",
      query: String(rawQuery || "").trim(),
      hit: { id: "", name: `${a.name} vs ${b.name}` },
      signIds: ids,
      relation,
      cases: casesOut,
      guidelines,
      sources,
      concepts: relatedConcepts(ids),
      conclusion: `${a.name}：${a.appearance} ${b.name}：${b.appearance} ` +
        `鉴别时不要只看一个征象：${a.name} 的易错点——${pitfalls(a)}；${b.name} 的易错点——${pitfalls(b)}。`,
      missing: [
        "对比检索只并列库内定义、影像位置与易错点，不是诊断路径。",
        "同一病例可能同时挂两个征象；以该区逐区标注和原始出处为准。",
      ],
    };
  }

  function buildAnswer(query) {
    const q = norm(query);
    if (!q) return null;
    const scope = scopeReason(q);
    if (scope) {
      return {
        kind: "refuse",
        tier: "refuse",
        reason: "scope",
        scopeLabel: scope,
        query: String(query || "").trim(),
        message: `“${String(query || "").trim()}”涉及${scope}，本工具不提供这类内容。`,
        suggestions: SCOPE_SUGGESTIONS,
      };
    }
    // “A 和 B 怎么区分”这类对比问法：并列两个库内征象，而不是只命中一个
    const mentioned = ((L.data && L.data.signs) || []).filter((s) => {
      const names = [s.name, s.en].concat(s.aliases || []).map(norm).filter(Boolean);
      return names.some((n) => n.length >= 2 && q.includes(n));
    }).slice(0, 2);
    if (mentioned.length === 2 && /区分|鉴别|区别|vs|和|与|还是|怎么/.test(q)) {
      return buildCompare(q, mentioned, query);
    }
    const signHits = topHits((L.data && L.data.signs) || [], scoreSign, q);
    const conceptHits = topHits((L.data && L.data.concepts) || [], scoreConcept, q);
    const guideHits = topHits((L.data && L.data.guidelines) || [], scoreGuideline, q);
    const caseHits = topHits(cases(), scoreCase, q);
    const candidates = [
      signHits[0] && { kind: "sign", hit: signHits[0], score: signHits[0].score },
      conceptHits[0] && { kind: "concept", hit: conceptHits[0], score: conceptHits[0].score },
      guideHits[0] && { kind: "guideline", hit: guideHits[0], score: guideHits[0].score },
      caseHits[0] && { kind: "case", hit: caseHits[0], score: caseHits[0].score },
    ].filter(Boolean).sort((a, b) => b.score - a.score);
    if (!candidates.length) {
      const guesses = [];
      ((L.data && L.data.signs) || []).forEach((s) => {
        if (norm(s.name).slice(0, 1) && q.includes(norm(s.name).slice(0, 1))) guesses.push(s.name);
      });
      return {
        kind: "refuse",
        tier: "refuse",
        reason: "miss",
        query: String(query || "").trim(),
        message: `库内没有找到与“${String(query || "").trim()}”可对应的词条或分区；不编造答案。`,
        suggestions: Array.from(new Set(guesses)).slice(0, 6).length
          ? Array.from(new Set(guesses)).slice(0, 6)
          : SCOPE_SUGGESTIONS,
      };
    }
    const primary = candidates[0];
    const kind = primary.kind;
    const hitFloor = HIT_FLOOR[kind] || 50;
    const weakFloor = WEAK_FLOOR[kind] || 30;
    if (primary.score < weakFloor) {
      return {
        kind: "refuse",
        tier: "refuse",
        reason: "low",
        query: String(query || "").trim(),
        message: `库内最接近的匹配只有 ${primary.score} 分，低于可回答阈值；不把弱相关当成结论。`,
        suggestions: SCOPE_SUGGESTIONS,
      };
    }
    const tier = primary.score < hitFloor ? "weak" : "hit";
    const hit = primary.hit.x;
    let signIds = [];
    let relation = {};
    let casesOut = [];
    let guidelines = [];
    let conclusion = "";
    let missing = [];

    if (kind === "sign") {
      signIds = [hit.id];
      relation[hit.id] = "direct";
      casesOut = casesForSigns(signIds, 8);
      guidelines = guidelinesForSigns(signIds);
      conclusion = `${hit.name}：${hit.appearance} ${hit.modality && hit.modality.length ? `（${hit.modality.join(" / ")}）` : ""}`;
      if (!casesOut.length) missing.push("库内 21 例胸片中暂无直接挂载该征象的分区；只能给出词条与文献。");
    } else if (kind === "concept") {
      const direct = (hit.sign_ids || []).filter((id) => signById(id));
      const related = (hit.related_sign_ids || []).filter((id) => signById(id));
      signIds = direct.concat(related.filter((id) => !direct.includes(id)));
      direct.forEach((id) => { relation[id] = "direct"; });
      related.forEach((id) => { relation[id] = "related"; });
      casesOut = casesForSigns(signIds, 8);
      guidelines = /结节|随访|指南/.test(q) ? guidelinesForSigns(signIds) : [];
      const names = direct.map((id) => `${signName(id)}（${id}）`);
      const relNames = related.map((id) => `${signName(id)}（${id}，关联）`);
      conclusion = `${hit.name} 在库内对应的征象：${names.length ? names.join("、") : "无直接挂载征象"}` +
        (relNames.length ? `；关联征象（非 may_see_in 原文）：${relNames.join("、")}` : "") +
        (hit.note ? `。${hit.note}` : "");
      if (!direct.length) missing.push("该概念在库内没有直接挂载征象，只有关联征象；关联不能当作原文依据。");
    } else if (kind === "guideline") {
      const names = ((L.data && L.data.signs) || []).filter((s) => norm(hit.statement + " " + (hit.conditions || []).join(" ")).includes(norm(s.name))).map((s) => s.id);
      signIds = names;
      names.forEach((id) => { relation[id] = "direct"; });
      casesOut = casesForSigns(signIds, 6);
      guidelines = [hit];
      conclusion = `${hit.standard_name} · ${hit.category}：${hit.statement}`;
      missing.push("指南条款有明确适用条件；不能把 CT 随访建议直接外推到胸片或个体诊断。");
    } else {
      const c = hit;
      signIds = (c.signs || []).filter((id) => signById(id));
      signIds.forEach((id) => { relation[id] = "direct"; });
      const zone = (c.zones || []).find((z) => z.status === "abnormal" && (z.sign_ids || []).length) ||
        (c.zones || []).find((z) => z.status === "abnormal") || null;
      casesOut = [{ case: c, zone }];
      guidelines = /结节|随访|指南/.test(q) ? guidelinesForSigns(signIds) : [];
      conclusion = `${c.id} · ${c.title}：${c.teaching_note || "按库内逐区标注阅读。"}`;
    }

    const sources = sourcesForSigns(signIds);
    if (!sources.length && kind !== "general") missing.push("相关词条未登记可引用的文献来源；不能补造出处。");
    if (!guidelines.length && (kind === "sign" || kind === "concept")) {
      missing.push("库内暂无与该征象直接对应的胸部指南条款；已检索 guidelines.jsonl。");
    }
    if (casesOut.some((e) => e.zone && e.zone.status === "unmentioned")) {
      missing.push("标注为「来源未提及」的分区不等于正常，本工具不作推断。");
    }
    const concepts = kind === "sign" ? relatedConcepts(signIds) : [];
    return {
      kind,
      tier,
      query: String(query || "").trim(),
      hit,
      signIds,
      relation,
      cases: casesOut,
      guidelines,
      sources,
      concepts,
      conclusion,
      missing,
    };
  }

  /* ==================== 报告 / 指南文本映射 ==================== */

  function extractSites(text) {
    const raw = String(text || "");
    const hits = raw.match(/(左|右)?(上|中|下)?肺野|(左|右)?肺(上|中|下)野|肺门|心影|纵隔|膈肌|肋膈角|胸膜|肺尖|肺底/g) || [];
    return Array.from(new Set(hits)).filter((s) => s !== "肺野").slice(0, 8);
  }

  function parseReport(text) {
    const raw = String(text || "").trim();
    const q = norm(raw);
    if (!q) return null;
    const sites = extractSites(raw);
    const signHits = ((L.data && L.data.signs) || []).filter((s) => {
      const names = [s.name, s.en].concat(s.aliases || []).map(norm).filter(Boolean);
      return names.some((n) => n.length >= 2 && q.includes(n));
    }).slice(0, 6);
    const conceptHits = ((L.data && L.data.concepts) || []).filter((c) => {
      const names = [c.name, c.en].concat(c.aliases || []).map(norm).filter(Boolean);
      return names.some((n) => n.length >= 2 && q.includes(n));
    }).slice(0, 3);
    const signIds = signHits.map((s) => s.id);
    const relation = {};
    signIds.forEach((id) => { relation[id] = "direct"; });

    const siteKey = (s) => norm(s).replace(/肺/g, "");
    const siteOk = (zoneName) => !sites.length || sites.some((site) => {
      const a = norm(zoneName);
      const b = norm(site);
      return a.includes(b) || b.includes(a) ||
        siteKey(a).includes(siteKey(b)) || siteKey(b).includes(siteKey(a));
    });

    let casesOut = [];
    signHits.forEach((s) => {
      const matched = [];
      cases().forEach((c) => {
        (c.zones || []).forEach((z) => {
          if (!(z.sign_ids || []).includes(s.id)) return;
          if (siteOk(z.name)) matched.push({ case: c, zone: z });
        });
      });
      const picked = matched.length ? matched : casesForSigns([s.id], 4);
      picked.forEach((e) => {
        const key = e.case.id + "|" + (e.zone ? e.zone.id : "");
        if (!casesOut.some((x) => x.case.id + "|" + (x.zone ? x.zone.id : "") === key)) casesOut.push(e);
      });
    });
    casesOut = casesOut.slice(0, 8);

    let guidelines = [];
    if (/结节|随访|指南|筛查|推荐/.test(q)) {
      guidelines = signIds.length
        ? guidelinesForSigns(signIds)
        : ((L.data && L.data.guidelines) || []).filter((g) =>
          /随访|筛查|推荐/.test(norm([g.statement, g.category].join(" ")))).slice(0, 2);
    }

    const guideIntent = /指南|随访|推荐|筛查/.test(q);
    if (guideIntent && guidelines.length) {
      const g = guidelines[0];
      const ids = signIds.length ? signIds : ["SIGN-003"];
      return {
        kind: "guideline", tier: "hit", query: raw,
        hit: g, signIds: ids, relation,
        cases: casesForSigns(ids, 6),
        guidelines,
        sources: sourcesForSigns(ids),
        concepts: relatedConcepts(ids),
        conclusion: `${g.standard_name} · ${g.category}：${g.statement}`,
        missing: [
          "指南条款有明确适用条件；不能把 CT 随访建议直接外推到胸片或个体诊断。",
          "以下只做指南条款与库内征象的对照，不构成诊断。",
        ],
      };
    }

    if (!signHits.length && !sites.length && !guidelines.length) {
      return {
        kind: "refuse", tier: "refuse", reason: "miss", query: raw,
        message: "报告文本里没有匹配到库内征象、分区或指南条款；不猜测报告含义。",
        suggestions: SCOPE_SUGGESTIONS,
      };
    }

    const conclusion = `报告文本命中：${sites.length ? sites.join("、") : "未识别明确分区"}；` +
      `${signHits.length ? signHits.map((s) => s.name).join("、") : "未识别征象"}` +
      `${conceptHits.length ? `；相关概念：${conceptHits.map((c) => c.name).join("、")}` : ""}。` +
      "以下只做文本到库内证据的映射，不判断报告对错。";
    const missing = [
      "报告解析只做关键词映射，不替代影像阅片；未提到的征象不等于不存在。",
      "若报告描述与库内标注冲突，以原始出处与医学审核为准。",
    ];
    if (guidelines.length) missing.push("指南条款有适用条件，不能直接外推到个体。");

    return {
      kind: "report", tier: "hit", query: raw,
      hit: { id: "REPORT", name: "报告文本 → 库内证据" },
      signIds, relation, cases: casesOut, guidelines,
      sources: sourcesForSigns(signIds), concepts: relatedConcepts(signIds),
      conclusion, missing,
      report: { sites, signs: signHits.map((s) => s.name) },
    };
  }

  /* ==================== 问答渲染 ==================== */

  function qaShell(host) {
    const chips = [
      "气胸在胸片上怎么找",
      "实变和胸腔积液怎么区分",
      "肺结核在胸片上有哪些征象",
      "肺结节随访看哪条指南",
      "心影增大提示什么",
    ];
    const result = L.qa.result;
    host.innerHTML = `<div class="lab-head">
      <div><div class="eyebrow">IMAGE LIBRARY Q&amp;A</div><h2>教学影像库问答</h2>
      <p>只检索 21 例胸片库内词条与逐区标注；命中给“影像区域定位”和“文献段落溯源”两条引用链，越界/低置信/未命中明确拒答。</p></div>
      <span class="lab-scope">库内 ${cases().length} 例 · ${(L.data.signs || []).length} 条征象</span>
    </div>
    <div class="lab-ask">
      <div class="lab-ask-row"><input id="labQ" value="${esc(L.qa.query)}" maxlength="80"
        placeholder="问一个征象或疾病，例如：气胸、实变、肺结核、肺水肿、肺结节随访">
        <button class="btn solid" data-lab-ask>检索库内证据</button></div>
      <div class="lab-chips">${chips.map((c) => `<button data-lab-q="${esc(c)}">${esc(c)}</button>`).join("")}</div>
      <details class="lab-report" ${L.qa.reportText ? "open" : ""}>
        <summary>粘贴报告 / 指南问题（可选）</summary>
        <textarea id="labReport" rows="4" placeholder="粘贴一段公开教学报告，例如：右肺上野见片状密度增高影，边界模糊，余肺野清晰。&#10;也可以贴一句指南问题，例如：6 mm 实性结节怎么随访？">${esc(L.qa.reportText || "")}</textarea>
        <button class="btn" data-lab-report>解析报告并找证据</button>
        <span class="lab-small">只做“文本 → 库内征象/分区/段落”的关键词映射，不判断报告对错，不生成诊断。</span>
      </details>
    </div>
    <div id="labQaResult">${result ? answerHTML(result) : qaEmptyHTML()}</div>`;
  }

  function qaEmptyHTML() {
    return `<div class="lab-empty">
      <div class="lab-empty-ic">Q</div>
      <b>先问一个具体征象或疾病</b>
      <p>问答会先查 signs / concepts / guidelines，再回到 21 例胸片的分区框。越界、低置信或库内未命中都会明确拒答，不把通识伪装成库内证据。</p>
      <div class="lab-empty-grid">
        <div><b>① 影像定位</b><span>病例 + 分区框 + 状态 + 影像出处</span></div>
        <div><b>② 文献溯源</b><span>征象词条 + 来源 + 段落锚点（para_id / sha256）</span></div>
      </div>
    </div>`;
  }

  function answerHTML(a) {
    if (a.kind === "refuse" || a.kind === "general") return refuseHTML(a);
    const kind = KIND_LABEL[a.kind] || a.kind;
    const title = a.kind === "sign" ? `${a.hit.name}` :
      a.kind === "concept" ? a.hit.name :
      a.kind === "guideline" ? `${a.hit.standard_name} · ${a.hit.category}` :
      a.kind === "compare" ? a.hit.name :
      a.kind === "report" ? a.hit.name :
      `${a.hit.id} · ${a.hit.title}`;
    const id = a.kind === "report" ? "" : (a.hit.id || "");
    const signCites = (a.signIds || []).map((sid, i) => ({ sign: signById(sid), relation: a.relation[sid], n: i + 1 })).filter((x) => x.sign);
    const evidence = a.cases || [];
    const chain = [];
    if (evidence[0]) chain.push(`E1 ${evidence[0].case.id}${evidence[0].zone ? " / " + evidence[0].zone.name : ""}`);
    if (signCites[0]) chain.push(`L1 ${signCites[0].sign.id} ${signCites[0].sign.name}`);
    if (a.sources[0]) chain.push(`${a.sources[0].id}`);
    return `<div class="lab-answer ${a.tier === "weak" ? "weak" : ""}">
      <div class="lab-ans-head">
        <div><span class="lab-kind ${a.tier === "weak" ? "warn" : ""}">${a.tier === "weak" ? "弱命中 · 需确认" : "库内命中"} · ${esc(kind)}</span>
          <h3>${esc(title)} ${id ? `<code>${esc(id)}</code>` : ""}</h3></div>
        <span class="lab-hit">${a.signIds.length} 条征象 · ${evidence.length} 个影像位置</span>
      </div>
      ${a.tier === "weak" ? `<div class="lab-weak-note">弱命中：库内匹配度不足，以下只作候选，不应当作确定答案。</div>` : ""}
      <p class="lab-conclusion">${esc(a.conclusion)}</p>
      <div class="lab-dual">
        <section class="lab-evidence">
          <div class="lab-sec-h"><h4>① 影像区域定位</h4><span>E = evidence</span></div>
          ${evidence.length ? evidence.map((e, i) => caseEvidenceHTML(e, i + 1)).join("") :
            `<div class="lab-none">库内暂无该征象的胸片分区定位。</div>`}
        </section>
        <section class="lab-citations">
          <div class="lab-sec-h"><h4>② 文献溯源</h4><span>L = literature</span></div>
          ${signCites.length ? signCites.map((x, i) => signCiteHTML(x.sign, i + 1, x.relation)).join("") :
            `<div class="lab-none">该条没有可引用的征象词条。</div>`}
          ${a.guidelines.length ? a.guidelines.map((g, i) => guidelineHTML(g, i + 1)).join("") : ""}
        </section>
      </div>
      ${chain.length ? `<div class="lab-chain"><b>双引用链</b><span>${chain.map(esc).join(" → ")}</span>
        <em>影像位置与文献条目分别可点开核对；链只表示“该病例该区挂载了该征象”，不表示诊断。</em></div>` : ""}
      ${a.concepts && a.concepts.length ? `<div class="lab-related"><b>相关概念</b>${a.concepts.map((c) =>
        `<span class="mini-chip">${esc(c.name)} · ${esc(c.id)}</span>`).join("")}</div>` : ""}
      ${a.missing && a.missing.length ? `<div class="lab-missing"><b>缺失与边界</b><ul>${a.missing.map((m) =>
        `<li>${esc(m)}</li>`).join("")}</ul></div>` : ""}
      <p class="lab-disclaimer">仅用于医学影像教学与研究，不构成诊断意见，不替代临床决策。</p>
    </div>`;
  }

  function caseEvidenceHTML(e, n) {
    const c = e.case;
    const z = e.zone;
    const box = z && z.coords && z.coords.length === 4
      ? `<span class="lab-bbox" style="${bboxStyle(z.coords)}"></span>` : "";
    return `<article class="lab-case">
      <a class="lab-thumb" href="clinic.html?case=${encodeURIComponent(c.id)}" target="_blank" rel="noopener" title="在阅片台打开">
        <img src="${esc(imagePath(c.image))}" alt="${esc(c.title)}" loading="lazy">${box}
      </a>
      <div class="lab-case-main">
        <div class="lab-case-top"><b>E${n} · ${esc(c.id)}</b>
          <span class="lab-status ${z ? esc(z.status) : ""}">${esc(z ? z.status_label : "无异常分区")}</span></div>
        <strong>${esc(c.title)}</strong>
        <p>${z ? `${esc(z.name)} · ${esc(z.text)}` : "该例库内没有挂载异常分区。"}</p>
        <div class="lab-meta">${esc(c.license || "许可见来源")} · ${esc(c.artist || "来源未署名")}</div>
        <a class="lab-link" href="clinic.html?case=${encodeURIComponent(c.id)}" target="_blank" rel="noopener">在阅片台打开 →</a>
      </div>
    </article>`;
  }

  function paraHTML(p, open) {
    const hash = (p.sha256 || "").slice(0, 12);
    return `<details class="lab-para" ${open ? "open" : ""}>
      <summary><code>${esc(p.para_id)}</code><span>${esc(p.section)} · char ${p.char_start}-${p.char_end}</span></summary>
      <p>${esc(p.text)}</p>
      <div class="lab-para-meta">sha256 ${esc(hash)}… · ${p.page ? "页码 " + esc(p.page) : "页码待补（自撰摘要）"} · ${esc(p.license_note || "见来源")}</div>
    </details>`;
  }

  function signCiteHTML(s, n, relation) {
    const src = (s.sources || []).map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.id)} · ${esc(x.title)}</a>`);
    const paras = ((L.data && L.data.sign_paragraphs) || {})[s.id] || [];
    return `<article class="lab-cite">
      <div class="lab-cite-h"><b>L${n} · ${esc(s.id)} ${esc(s.name)}</b>
        <span>${relation === "related" ? "关联征象" : "直接挂载"}</span></div>
      <p>${esc(s.appearance)}</p>
      <div class="lab-cite-meta">${(s.modality || []).join(" / ")} · ${esc(s.body_part || "")}</div>
      <div class="lab-src">${src.length ? src.join("") : `<span class="lab-none">该词条未登记来源</span>`}</div>
      ${paras.length ? `<div class="lab-para-block"><b>段落 L2 · ${paras.length} 条</b>${paras.map((p, i) => paraHTML(p, i === 0)).join("")}</div>` :
        `<div class="lab-none">该词条暂无段落锚点，只有来源级引用。</div>`}
    </article>`;
  }

  function guidelineHTML(g, n) {
    const paras = ((L.data && L.data.guideline_paragraphs) || {})[g.id] || [];
    return `<article class="lab-guide">
      <div class="lab-cite-h"><b>G${n} · ${esc(g.id)}</b><span>${esc(g.standard_name)}</span></div>
      <p>${esc(g.statement)}</p>
      <div class="lab-cite-meta">${esc(g.category)} · ${esc(g.version_year || "")}</div>
      <div class="lab-guide-note">适用条件：${esc((g.conditions || []).join("；") || "见原文")}。${esc(g.license_note || "")}</div>
      ${paras.length ? `<div class="lab-para-block"><b>段落 L2 · ${paras.length} 条</b>${paras.map((p, i) => paraHTML(p, i === 0)).join("")}</div>` : ""}
    </article>`;
  }

  function refuseHTML(a) {
    const scope = a.reason === "scope";
    const low = a.reason === "low";
    const tag = scope ? "越界拒答" : low ? "低置信拒答" : "库内未覆盖";
    const title = scope ? "这个问题不在本工具范围内" :
      low ? "匹配太弱，不能回答" : "库内没有可引用的证据";
    const suggestions = (a.suggestions && a.suggestions.length) ? a.suggestions : SCOPE_SUGGESTIONS;
    return `<div class="lab-answer refuse">
      <div class="lab-ans-head"><div><span class="lab-kind refuse">${tag}</span>
        <h3>${title}</h3></div><span class="lab-hit">诚实拒答</span></div>
      <p class="lab-conclusion">${esc(a.message || `库内未命中“${a.query}”；不编造答案。`)}</p>
      <div class="lab-suggest"><b>可以改问</b>${suggestions.map((x) =>
        `<button data-lab-q="${esc(x)}">${esc(x)}</button>`).join("")}</div>
      <div class="lab-missing"><b>边界</b><p>本工具只做影像表现与出处对照，不提供诊断、治疗、预后或操作建议；未命中时不编造 id，也不把通识内容标成库内证据。</p></div>
      <p class="lab-disclaimer">仅用于医学影像教学与研究，不构成诊断意见，不替代临床决策。</p>
    </div>`;
  }

  /* ==================== 读片陪练 ==================== */

  function coachCase() { return caseById(L.coach.caseId); }

  function startCoach(caseId) {
    const pool = cases().filter((c) => c.signs && c.signs.length);
    const c = caseById(caseId) || (pool.length ? pool[Math.floor(Math.random() * pool.length)] : cases()[0]);
    if (!c) return;
    L.coach = { caseId: c.id, step: 1, zoneId: "", status: "", signs: [], touched: false, hint: 0, revealed: false, result: null };
  }

  function coachSignOptions(c) {
    const correct = (c.signs || []).slice();
    const pool = ((L.data && L.data.signs) || []).map((s) => s.id).filter((id) => !correct.includes(id));
    const picked = shuffle(pool).slice(0, 4);
    const ids = correct.concat(picked);
    return ids.map((id) => ({ id, name: signName(id) }));
  }

  function coachHintText(c, step) {
    if (step === 1) {
      return "先按顺序扫：气管与纵隔、双侧肺野、肺门、心影、膈面与肋膈角、骨骼与软组织。异常区常表现为密度、轮廓或位置与对侧不对称。";
    }
    if (step === 2) {
      return "四种状态要分清：异常＝该区有明确异常描述；未见异常＝来源明确描述正常；来源未提及＝来源没写，不等于正常；判读受限＝质量或体位限制。";
    }
    if (step === 3) {
      return "只选库内实际挂载的征象；正常对照不要硬选。若不确定，先想“这个征象的定义是否真的能在该区看到”，再决定。";
    }
    return "对照时先看定位是否正确，再看状态与征象；分数只代表库内标注匹配度，不代表临床诊断能力。";
  }

  function coachHTML(host) {
    if (!L.coach.caseId) startCoach("");
    const c = coachCase();
    if (!c) { host.innerHTML = `<div class="lab-none">没有可练习的病例。</div>`; return; }
    const z = zoneOf(c, L.coach.zoneId);
    const steps = [
      ["1", "定位"], ["2", "判读"], ["3", "征象"], ["4", "对照"],
    ];
    const stepBar = `<div class="lab-steps">${steps.map(([n, label], i) => {
      const idx = i + 1;
      const cls = L.coach.step > idx ? "done" : (L.coach.step === idx ? "on" : "");
      return `<span class="${cls}"><i>${L.coach.step > idx ? "✓" : n}</i>${label}</span>`;
    }).join("")}</div>`;
    const caseOptions = cases().map((x) => `<option value="${esc(x.id)}" ${x.id === c.id ? "selected" : ""}>${esc(x.id)} · ${esc(x.pose_label || "胸片")}</option>`).join("");
    const zones = (c.zones || []).map((x) => {
      const on = x.id === L.coach.zoneId ? " on" : "";
      const st = L.coach.revealed ? ` ${x.status}` : "";
      const clickable = L.coach.step === 1 && !L.coach.revealed;
      return `<button class="lab-zone${on}${st}" ${clickable ? `data-lab-coach-zone="${esc(x.id)}"` : "disabled"}
        style="${bboxStyle(x.coords)}"><span>${esc(x.name)}</span></button>`;
    }).join("");
    host.innerHTML = `<div class="lab-head">
      <div><div class="eyebrow">GUIDED READING</div><h2>读片练习陪练</h2>
      <p>按“定位 → 判读 → 征象 → 对照”四步走；提示只给方法，不直接给答案。</p></div>
      <div class="lab-head-actions">
        <select id="labCoachCase" class="lab-select">${caseOptions}</select>
        <button class="btn" data-lab-coach-new>换一例</button>
      </div>
    </div>
    ${stepBar}
    <div class="lab-work">
      <div class="lab-stage-wrap">
        <div class="lab-stage ${L.coach.revealed ? "revealed" : ""}">
          <img src="${esc(imagePath(c.image))}" alt="${esc(c.title)}">
          ${zones}
        </div>
        <div class="lab-stage-foot"><span>${esc(c.id)} · ${esc(c.pose_label || "")}</span>
          <span>${L.coach.revealed ? esc(c.title) : "提交对照前不显示病例标题与分区颜色"}</span></div>
      </div>
      <div class="lab-panel">${coachStepHTML(c, z)}</div>
    </div>`;
  }

  function coachStepHTML(c, z) {
    if (L.coach.step === 1) {
      return `<div class="lab-step">
        <span class="lab-step-no">第 1 步 / 共 4 步</span><h3>先定位：异常在哪个分区？</h3>
        <p>点击影像上的分区框；如果没有明确异常，选“未见明确异常”。此时不显示分区颜色。</p>
        <div class="lab-choice-row">
          <button class="btn sm ${L.coach.zoneId === "none" ? "solid" : ""}" data-lab-coach-zone="none">未见明确异常</button>
        </div>
        ${L.coach.zoneId ? `<div class="lab-picked">已选：<b>${L.coach.zoneId === "none" ? "未见明确异常" : esc(z ? z.name : "")}</b></div>` : ""}
        <div class="lab-actions"><button class="btn sm" data-lab-coach-hint>给一个方法提示</button>
          <button class="btn solid" data-lab-coach-next ${L.coach.zoneId ? "" : "disabled"}>下一步 →</button></div>
        ${L.coach.hint ? `<div class="lab-hint"><b>提示</b>${esc(coachHintText(c, 1))}</div>` : ""}
      </div>`;
    }
    if (L.coach.step === 2) {
      return `<div class="lab-step">
        <span class="lab-step-no">第 2 步 / 共 4 步</span><h3>这个分区在库内是什么状态？</h3>
        <p>“来源未提及”不是“正常”；请按库内逐区标注的含义选择。</p>
        <div class="lab-choice-col">${Object.keys(STATUS).map((k) =>
          `<button class="lab-choice ${L.coach.status === k ? "on" : ""}" data-lab-coach-status="${k}">${STATUS[k]}</button>`).join("")}</div>
        <div class="lab-actions"><button class="btn sm" data-lab-coach-hint>给一个方法提示</button>
          <button class="btn solid" data-lab-coach-next ${L.coach.status ? "" : "disabled"}>下一步 →</button></div>
        ${L.coach.hint ? `<div class="lab-hint"><b>提示</b>${esc(coachHintText(c, 2))}</div>` : ""}
      </div>`;
    }
    if (L.coach.step === 3) {
      const opts = coachSignOptions(c);
      return `<div class="lab-step">
        <span class="lab-step-no">第 3 步 / 共 4 步</span><h3>该病例在库内挂载了哪些征象？</h3>
        <p>可多选；不确定的不要硬选。正常对照可以选择“未见明确征象”。</p>
        <div class="lab-sign-grid">${opts.map((o) =>
          `<button class="lab-sign ${L.coach.signs.includes(o.id) ? "on" : ""}" data-lab-coach-sign="${o.id}">${esc(o.name)}</button>`).join("")}
          <button class="lab-sign ${L.coach.touched && !L.coach.signs.length ? "on" : ""}" data-lab-coach-sign="none">未见明确征象</button>
        </div>
        <div class="lab-actions"><button class="btn sm" data-lab-coach-hint>给一个方法提示</button>
          <button class="btn solid" data-lab-coach-submit>提交并对照 →</button></div>
        ${L.coach.hint ? `<div class="lab-hint"><b>提示</b>${esc(coachHintText(c, 3))}</div>` : ""}
      </div>`;
    }
    const r = L.coach.result;
    if (!r) return `<div class="lab-none">还没有结果。</div>`;
    const detail = r.detail || {};
    const correctZone = (detail.correctZoneIds || []).map((id) => {
      const x = zoneOf(c, id);
      return x ? x.name : id;
    }).join("、") || "未见明确异常";
    const correctSigns = (detail.expectedSigns || []).map(signName).join("、") || "未见明确征象";
    const zz = zoneOf(c, L.coach.zoneId);
    return `<div class="lab-step">
      <span class="lab-step-no">第 4 步 / 共 4 步</span><h3>对照库内标注</h3>
      <div class="lab-score"><b>${r.score}</b><span>/ 100</span><em>定位 ${detail.zonePoints || 0} · 判读 ${detail.statusPoints || 0} · 征象 ${detail.signPoints || 0}</em></div>
      <div class="lab-check">
        <div class="${detail.zoneOk ? "ok" : "bad"}"><b>${detail.zoneOk ? "✓" : "×"} 定位</b><span>你选：${L.coach.zoneId === "none" ? "未见明确异常" : esc(zz ? zz.name : L.coach.zoneId)}；库内异常区：${esc(correctZone)}</span></div>
        <div class="${detail.statusOk ? "ok" : "bad"}"><b>${detail.statusOk ? "✓" : "×"} 判读</b><span>你选：${esc(statusLabel(L.coach.status))}；该区库内状态：${esc(statusLabel(detail.expectedStatus))}</span></div>
        <div class="${(detail.signRatio || 0) >= 0.99 ? "ok" : "bad"}"><b>${(detail.signRatio || 0) >= 0.99 ? "✓" : "×"} 征象</b><span>你选：${esc((L.coach.signs || []).map(signName).join("、") || "未见明确征象")}；库内：${esc(correctSigns)}</span></div>
      </div>
      ${zz ? `<div class="lab-truth"><b>该区库内所见</b><p>${esc(zz.text)}</p><span>依据：${esc(zz.basis || "库内逐区标注")}</span></div>` : ""}
      <div class="lab-truth"><b>病例教学提示</b><p>${esc(c.teaching_note || "无")}</p><span>${esc(c.license || "")} · ${esc(c.artist || "")}</span></div>
      <div class="lab-actions"><button class="btn sm" data-lab-coach-hint>看方法提示</button>
        <button class="btn solid" data-lab-coach-reset>重练本例</button>
        <a class="btn sm" href="clinic.html?case=${encodeURIComponent(c.id)}" target="_blank" rel="noopener">在阅片台打开 →</a></div>
      ${L.coach.hint ? `<div class="lab-hint"><b>提示</b>${esc(coachHintText(c, 4))}</div>` : ""}
    </div>`;
  }

  function submitCoach() {
    const c = coachCase();
    if (!c || !L.coach.zoneId || !L.coach.status) return;
    const signs = L.coach.signs.slice();
    const graded = RC.gradeCase(c, { zoneId: L.coach.zoneId, status: L.coach.status, signs });
    L.coach.result = graded;
    L.coach.revealed = true;
    L.coach.step = 4;
    recordPractice({ kind: "coach", caseId: c.id, score: graded.score, hints: L.coach.hint });
    render();
  }

  /* ==================== 自测出题器 ==================== */

  function quizScopePool(scope, type) {
    let pool = ((L.data && L.data.questions) || []).slice();
    if (scope === "abnormal") pool = pool.filter((q) => { const c = caseById(q.case_id); return c && c.signs && c.signs.length; });
    else if (scope === "normal") pool = pool.filter((q) => { const c = caseById(q.case_id); return c && (!c.signs || !c.signs.length); });
    else if (scope.startsWith("sign:")) {
      const sid = scope.slice(5);
      pool = pool.filter((q) => (q.citations && q.citations.sign_ids || []).includes(sid) ||
        ((caseById(q.case_id) || {}).signs || []).includes(sid));
    }
    if (type !== "mixed") pool = pool.filter((q) => q.type === type);
    return pool;
  }

  function quizConfigHTML(host) {
    const signs = (L.data && L.data.signs) || [];
    const cfg = L.quiz.config;
    const hist = L.history.quizzes.slice(0, 6);
    host.innerHTML = `<div class="lab-head">
      <div><div class="eyebrow">SELF-ASSESSMENT BUILDER</div><h2>自测出题器</h2>
      <p>从 21 例胸片库内规则题中抽题：定位、判读、征象；交卷后逐题给影像位置与文献来源。</p></div>
      <span class="lab-scope">题库 ${(L.data.questions || []).length} 题</span>
    </div>
    <div class="lab-quiz-config">
      <div class="field"><label for="labScope">范围</label><select id="labScope">
        <option value="all" ${cfg.scope === "all" ? "selected" : ""}>全部 21 例</option>
        <option value="abnormal" ${cfg.scope === "abnormal" ? "selected" : ""}>有异常标注的病例</option>
        <option value="normal" ${cfg.scope === "normal" ? "selected" : ""}>正常 / 对照病例</option>
        ${signs.map((s) => `<option value="sign:${esc(s.id)}" ${cfg.scope === "sign:" + s.id ? "selected" : ""}>按征象：${esc(s.name)}</option>`).join("")}
      </select></div>
      <div class="field"><label for="labType">题型</label><select id="labType">
        <option value="mixed" ${cfg.type === "mixed" ? "selected" : ""}>混合（定位 + 判读 + 征象）</option>
        <option value="locate" ${cfg.type === "locate" ? "selected" : ""}>只考影像定位</option>
        <option value="status" ${cfg.type === "status" ? "selected" : ""}>只考分区判读</option>
        <option value="sign" ${cfg.type === "sign" ? "selected" : ""}>只考征象识别</option>
      </select></div>
      <div class="field"><label for="labCount">题量</label><select id="labCount">
        ${[5, 10, 15, 20].map((n) => `<option value="${n}" ${cfg.count === n ? "selected" : ""}>${n} 题</option>`).join("")}
      </select></div>
      <div class="field"><label for="labMinutes">限时</label><select id="labMinutes">
        <option value="0" ${cfg.minutes === 0 ? "selected" : ""}>不限时</option>
        <option value="10" ${cfg.minutes === 10 ? "selected" : ""}>10 分钟</option>
        <option value="20" ${cfg.minutes === 20 ? "selected" : ""}>20 分钟</option>
        <option value="30" ${cfg.minutes === 30 ? "selected" : ""}>30 分钟</option>
      </select></div>
    </div>
    <div class="lab-actions"><button class="btn solid" data-lab-quiz-start>生成试卷 →</button>
      <span class="lab-small">题目由库内逐区标注生成，不是考试真题；答案只代表库内标注。</span></div>
    ${hist.length ? `<div class="panel-card" style="margin-top:16px"><div class="panel-h"><h3>最近自测</h3><span class="sub">本机记录</span></div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>时间</th><th class="num">得分</th><th class="num">正确</th><th>范围 / 题型</th></tr></thead><tbody>
      ${hist.map((h) => `<tr><td class="muted">${fmtTime(h.at)}</td><td class="num ${h.score < 60 ? "warn" : "ok"}">${h.score}</td>
        <td class="num">${h.correct}/${h.total}</td><td>${esc(h.scopeLabel || h.scope || "")} · ${esc(h.typeLabel || h.type || "")}</td></tr>`).join("")}
      </tbody></table></div></div>` : ""}`;
  }

  function scopeLabel(v) {
    if (v === "all") return "全部 21 例";
    if (v === "abnormal") return "有异常标注";
    if (v === "normal") return "正常 / 对照";
    if (v.startsWith("sign:")) return "征象：" + signName(v.slice(5));
    return v;
  }
  function typeLabel(v) {
    return { mixed: "混合", locate: "定位", status: "判读", sign: "征象" }[v] || v;
  }

  function startQuiz() {
    const scope = ($("#labScope") && $("#labScope").value) || "all";
    const type = ($("#labType") && $("#labType").value) || "mixed";
    const count = Number(($("#labCount") && $("#labCount").value) || 10);
    const minutes = Number(($("#labMinutes") && $("#labMinutes").value) || 0);
    L.quiz.config = { scope, type, count, minutes };
    let pool = quizScopePool(scope, type);
    if (!pool.length) { toast("该范围没有可用题目，请换一个范围或题型"); return; }
    const qs = shuffle(pool).slice(0, Math.min(count, pool.length));
    L.quiz.paper = {
      id: "QZ-" + Date.now().toString(36),
      questions: qs,
      answers: {},
      index: 0,
      startedAt: Date.now(),
      endsAt: minutes ? Date.now() + minutes * 60000 : 0,
      config: { scope, type, count: qs.length, minutes },
    };
    L.quiz.result = null;
    startTimer();
    render();
  }

  function clearTimer() {
    if (L.quiz.timer) {
      clearInterval(L.quiz.timer);
      L.quiz.timer = null;
    }
  }

  function startTimer() {
    clearTimer();
    const paper = L.quiz.paper;
    if (!paper || !paper.endsAt) return;
    L.quiz.timer = setInterval(() => {
      if (!L.quiz.paper || L.quiz.result) { clearTimer(); return; }
      const left = L.quiz.paper.endsAt - Date.now();
      const el = $("#labTimer");
      if (el) el.textContent = fmtLeft(left);
      if (left <= 0) submitQuiz(true);
    }, 1000);
  }

  function quizPaperHTML(host) {
    const p = L.quiz.paper;
    const q = p.questions[p.index];
    if (!q) { host.innerHTML = `<div class="lab-none">试卷为空。</div>`; return; }
    const c = caseById(q.case_id);
    const z = zoneOf(c, q.zone_id);
    const picked = p.answers[q.qid];
    const answered = Object.keys(p.answers).length;
    const box = q.coords && q.coords.length === 4 ? `<span class="lab-bbox" style="${bboxStyle(q.coords)}"></span>` : "";
    const sheet = p.questions.map((x, i) => {
      const on = i === p.index ? " on" : "";
      const done = p.answers[x.qid] != null ? " done" : "";
      return `<button class="lab-sheet-cell${on}${done}" data-lab-jump="${i}">${i + 1}</button>`;
    }).join("");
    host.innerHTML = `<div class="lab-quiz-bar">
      <div><span class="lab-kind">自测 · ${esc(scopeLabel(p.config.scope))} · ${esc(typeLabel(p.config.type))}</span>
        <b>第 ${p.index + 1} / ${p.questions.length} 题</b></div>
      <div class="lab-quiz-bar-r">
        ${p.endsAt ? `<span class="lab-timer" id="labTimer">${fmtLeft(p.endsAt - Date.now())}</span>` : `<span class="lab-small">不限时</span>`}
        <span class="lab-small">已答 ${answered}/${p.questions.length}</span>
        <button class="btn solid sm" data-lab-submit>交卷</button>
      </div>
    </div>
    <div class="lab-work">
      <div class="lab-stage-wrap">
        <div class="lab-stage">
          <img src="${esc(imagePath(c ? c.image : ""))}" alt="${esc(c ? c.title : "")}">
          ${box}
        </div>
        <div class="lab-stage-foot"><span>${esc(c ? c.id : "")} · ${esc(c ? (c.pose_label || "") : "")}</span>
          <span>${esc(q.type_label)} · 框选位置以库内 coords 为准</span></div>
      </div>
      <div class="lab-panel">
        <span class="lab-step-no">${esc(q.type_label)}</span>
        <h3 class="lab-qtitle">${esc(q.prompt)}</h3>
        <div class="lab-options">${q.options.map((o, i) =>
          `<button class="lab-option ${picked === i ? "on" : ""}" data-lab-pick="${i}"><i>${String.fromCharCode(65 + i)}</i><span>${esc(o)}</span></button>`).join("")}</div>
        <div class="lab-actions"><button class="btn sm" data-lab-prev ${p.index === 0 ? "disabled" : ""}>← 上一题</button>
          <button class="btn sm" data-lab-next ${p.index >= p.questions.length - 1 ? "disabled" : ""}>下一题 →</button></div>
      </div>
    </div>
    <div class="lab-sheet"><div class="lab-sheet-h"><b>答题卡</b><span>点击题号跳转</span></div>
      <div class="lab-sheet-grid">${sheet}</div>
      <div class="lab-sheet-legend"><span class="done">已答</span><span class="on">当前</span><span>未答</span></div></div>`;
  }

  function submitQuiz(auto) {
    const p = L.quiz.paper;
    if (!p || L.quiz.result) return;
    const unanswered = p.questions.filter((q) => p.answers[q.qid] == null).length;
    if (!auto && unanswered && !window.confirm(`还有 ${unanswered} 题未答，确定交卷？`)) return;
    clearTimer();
    const rows = p.questions.map((q) => {
      const picked = p.answers[q.qid];
      const ok = picked === q.answer_index;
      return { q, picked: picked == null ? null : picked, ok };
    });
    const correct = rows.filter((r) => r.ok).length;
    const score = Math.round((correct / rows.length) * 100);
    L.quiz.result = {
      score, correct, total: rows.length, rows,
      at: new Date().toISOString(),
      config: p.config,
      scopeLabel: scopeLabel(p.config.scope),
      typeLabel: typeLabel(p.config.type),
      used: p.startedAt ? Math.round((Date.now() - p.startedAt) / 1000) : 0,
    };
    recordQuiz({
      score, correct, total: rows.length,
      scope: p.config.scope, type: p.config.type,
      scopeLabel: scopeLabel(p.config.scope), typeLabel: typeLabel(p.config.type),
    });
    render();
  }

  function quizResultHTML(host) {
    const r = L.quiz.result;
    if (!r) { quizConfigHTML(host); return; }
    const wrong = r.rows.filter((x) => !x.ok).length;
    host.innerHTML = `<div class="lab-result">
      <div class="lab-result-head">
        <div><span class="lab-kind">自测结果</span><h2>${r.score} 分</h2>
          <p>${r.correct}/${r.total} 正确 · ${wrong} 题待复习 · 用时 ${Math.floor(r.used / 60)} 分 ${r.used % 60} 秒</p></div>
        <div class="lab-result-actions">
          <button class="btn" data-lab-retry-wrong ${wrong ? "" : "disabled"}>只重做错题</button>
          <button class="btn" data-lab-export>导出成绩单</button>
          <button class="btn solid" data-lab-quiz-again>再测一次</button>
        </div>
      </div>
      <div class="lab-result-list">${r.rows.map((row, i) => quizRowHTML(row, i + 1)).join("")}</div>
      <p class="lab-small" style="margin-top:12px">分数只代表与库内逐区标注的匹配度，不评价临床诊断能力；正式教学前须由医学人员审核。</p>
    </div>`;
  }

  function quizRowHTML(row, n) {
    const q = row.q;
    const c = caseById(q.case_id);
    const z = zoneOf(c, q.zone_id);
    const your = row.picked == null ? "未作答" : q.options[row.picked];
    const signText = (q.citations && q.citations.sign_ids || []).map((id) => {
      const s = signById(id);
      return s ? `${s.id} ${s.name}` : id;
    }).join("、");
    const evidence = z
      ? `病例 ${q.case_id}，分区 ${z.name}（${z.id}），状态 ${z.status_label}，所见：${z.text}，关联征象：${signText || "无"}`
      : "";
    return `<article class="lab-qr ${row.ok ? "ok" : "bad"}">
      <div class="lab-qr-h"><b>${n}. ${esc(q.type_label)} · ${esc(c ? c.id : q.case_id)}${z ? " / " + esc(z.name) : ""}</b>
        <span>${row.ok ? "✓ 正确" : "× 错误"}</span></div>
      <p class="lab-qr-prompt">${esc(q.prompt)}</p>
      <div class="lab-qr-answer">你的答案：<b>${esc(your)}</b> · 正确答案：<b>${esc(q.answer)}</b></div>
      <p class="lab-explain">${esc(q.explain)}</p>
      <div class="lab-qr-cites">
        ${c ? `<a href="clinic.html?case=${encodeURIComponent(c.id)}" target="_blank" rel="noopener">影像 E1 · ${esc(c.id)}${z ? " / " + esc(z.name) : ""}</a>` : ""}
        ${(q.citations && q.citations.sign_ids || []).map((sid) => {
          const s = signById(sid);
          return s ? `<span>文献 L · ${esc(s.id)} ${esc(s.name)}${(s.sources || []).length ? `（${s.sources.map((x) => esc(x.id)).join("、")}）` : "（未登记来源）"}</span>` : "";
        }).join("")}
      </div>
      ${!row.ok ? `<div class="qa-agent"><button class="btn sm" data-agent-ask data-agent-surface="lab"
        data-agent-case="${esc(q.case_id || "")}" data-agent-zone="${esc(q.zone_id || "")}"
        data-agent-signs="${esc((q.citations && q.citations.sign_ids || []).join(","))}"
        data-agent-evidence="${esc(evidence)}"
        data-agent-query="${esc(`这道题我答错了：${q.prompt} 我的答案：${your}；正确答案：${q.answer}。请解释为什么错，只引用库内证据，不诊断、不治疗、不判分。`)}">问 Agent 为什么错</button></div>` : ""}
    </article>`;
  }

  function retryWrong() {
    const r = L.quiz.result;
    if (!r) return;
    const qs = r.rows.filter((x) => !x.ok).map((x) => x.q);
    if (!qs.length) { toast("没有错题可重做"); return; }
    L.quiz.paper = {
      id: "QZ-" + Date.now().toString(36),
      questions: qs,
      answers: {},
      index: 0,
      startedAt: Date.now(),
      endsAt: r.config.minutes ? Date.now() + r.config.minutes * 60000 : 0,
      config: r.config,
    };
    L.quiz.result = null;
    startTimer();
    render();
  }

  function exportQuiz() {
    const r = L.quiz.result;
    if (!r) return;
    const lines = [
      "# RadioCheck 自测成绩单",
      "",
      `- 得分：${r.score} / 100`,
      `- 正确：${r.correct}/${r.total}`,
      `- 范围：${r.scopeLabel}`,
      `- 题型：${r.typeLabel}`,
      `- 时间：${fmtTime(r.at)}`,
      "",
      "## 逐题",
      ...r.rows.map((row, i) => {
        const q = row.q;
        const your = row.picked == null ? "未作答" : q.options[row.picked];
        const paraIds = (q.citations.sign_ids || []).flatMap((id) =>
          (((L.data && L.data.sign_paragraphs) || {})[id] || []).slice(0, 1).map((p) => p.para_id));
        return `${i + 1}. [${row.ok ? "正确" : "错误"}] ${q.type_label} · ${q.case_id} / ${q.zone_id}\n` +
          `   - 题干：${q.prompt}\n   - 你的答案：${your}\n   - 正确答案：${q.answer}\n` +
          `   - 解析：${q.explain}\n   - 引用：${q.case_id} / ${q.zone_id}；${(q.citations.sign_ids || []).join("、") || "无征象引用"}；段落：${paraIds.join("、") || "无"}`;
      }),
      "",
      "> 仅用于教学与研究，不构成诊断意见。",
    ];
    download(`RadioCheck_自测_${r.score}分_${new Date().toISOString().slice(0, 10)}.md`, lines.join("\n"));
    toast("成绩单已导出");
  }

  /* ==================== 渲染入口 ==================== */

  function render() {
    const host = $("#studentTabBody");
    if (!host) return;
    if (L.tab === "qa") qaShell(host);
    else if (L.tab === "coach") coachHTML(host);
    else if (L.tab === "quiz") {
      if (L.quiz.result) quizResultHTML(host);
      else if (L.quiz.paper) quizPaperHTML(host);
      else quizConfigHTML(host);
    }
  }

  function mount(tab, hostEl) {
    L.tab = tab;
    const host = hostEl || $("#studentTabBody");
    if (!host) return;
    if (tab !== "quiz") clearTimer();
    else if (L.quiz.paper && !L.quiz.result && L.quiz.paper.endsAt) startTimer();
    if (!L.data) {
      host.innerHTML = `<div class="lab-empty"><b>正在载入影像库…</b><p>${esc(DATA_URL)}</p></div>`;
      load().then(() => {
        if (L.tab === tab) render();
      }).catch((e) => {
        host.innerHTML = `<div class="lab-empty"><b>影像库载入失败</b><p>${esc(String(e.message || e))}<br>请先运行 python3 kb/scripts/build_student_lab.py 与 python3 medtrain/build.py。</p></div>`;
      });
      return;
    }
    if (tab === "coach" && !L.coach.caseId) startCoach("");
    render();
  }

  /* ==================== 事件 ==================== */

  function bind() {
    document.addEventListener("click", (e) => {
      const rep = e.target.closest("[data-lab-report]");
      if (rep) {
        const el = $("#labReport");
        const text = el ? el.value.trim() : "";
        if (!text) { toast("请先粘贴一段报告或指南问题"); return; }
        L.qa.reportText = text;
        L.qa.query = text.slice(0, 80);
        L.qa.result = parseReport(text);
        render();
        return;
      }
      const ask = e.target.closest("[data-lab-ask]");
      if (ask) {
        const el = $("#labQ");
        const q = el ? el.value.trim() : "";
        if (!q) { toast("请先输入一个征象或疾病名"); return; }
        L.qa.query = q;
        L.qa.result = buildAnswer(q);
        render();
        return;
      }
      const chip = e.target.closest("[data-lab-q]");
      if (chip) {
        const q = chip.dataset.labQ;
        L.qa.query = q;
        L.qa.result = buildAnswer(q);
        if (L.tab !== "qa") { L.tab = "qa"; }
        render();
        return;
      }
      const coachZone = e.target.closest("[data-lab-coach-zone]");
      if (coachZone) {
        L.coach.zoneId = coachZone.dataset.labCoachZone;
        render();
        return;
      }
      const coachStatus = e.target.closest("[data-lab-coach-status]");
      if (coachStatus) {
        L.coach.status = coachStatus.dataset.labCoachStatus;
        render();
        return;
      }
      const coachSign = e.target.closest("[data-lab-coach-sign]");
      if (coachSign) {
        const id = coachSign.dataset.labCoachSign;
        L.coach.touched = true;
        if (id === "none") L.coach.signs = [];
        else {
          const set = new Set(L.coach.signs);
          if (set.has(id)) set.delete(id); else set.add(id);
          L.coach.signs = Array.from(set);
        }
        render();
        return;
      }
      const coachNext = e.target.closest("[data-lab-coach-next]");
      if (coachNext) {
        if (L.coach.step === 1 && !L.coach.zoneId) { toast("请先选择一个分区"); return; }
        if (L.coach.step === 2 && !L.coach.status) { toast("请先选择该区状态"); return; }
        L.coach.step = Math.min(4, L.coach.step + 1);
        render();
        return;
      }
      const coachHint = e.target.closest("[data-lab-coach-hint]");
      if (coachHint) { L.coach.hint += 1; render(); return; }
      const coachNew = e.target.closest("[data-lab-coach-new]");
      if (coachNew) { startCoach(""); render(); return; }
      const coachReset = e.target.closest("[data-lab-coach-reset]");
      if (coachReset) { startCoach(L.coach.caseId); render(); return; }
      const coachSubmit = e.target.closest("[data-lab-coach-submit]");
      if (coachSubmit) { submitCoach(); return; }

      const quizStart = e.target.closest("[data-lab-quiz-start]");
      if (quizStart) { startQuiz(); return; }
      const pick = e.target.closest("[data-lab-pick]");
      if (pick && L.quiz.paper) {
        const i = Number(pick.dataset.labPick);
        const q = L.quiz.paper.questions[L.quiz.paper.index];
        if (q) L.quiz.paper.answers[q.qid] = i;
        render();
        return;
      }
      const jump = e.target.closest("[data-lab-jump]");
      if (jump && L.quiz.paper) {
        L.quiz.paper.index = Number(jump.dataset.labJump);
        render();
        return;
      }
      const prev = e.target.closest("[data-lab-prev]");
      if (prev && L.quiz.paper) { L.quiz.paper.index = Math.max(0, L.quiz.paper.index - 1); render(); return; }
      const next = e.target.closest("[data-lab-next]");
      if (next && L.quiz.paper) { L.quiz.paper.index = Math.min(L.quiz.paper.questions.length - 1, L.quiz.paper.index + 1); render(); return; }
      const submit = e.target.closest("[data-lab-submit]");
      if (submit) { submitQuiz(false); return; }
      const retry = e.target.closest("[data-lab-retry-wrong]");
      if (retry) { retryWrong(); return; }
      const again = e.target.closest("[data-lab-quiz-again]");
      if (again) { L.quiz.paper = null; L.quiz.result = null; clearTimer(); render(); return; }
      const exp = e.target.closest("[data-lab-export]");
      if (exp) { exportQuiz(); return; }
    });

    document.addEventListener("change", (e) => {
      if (e.target && e.target.id === "labCoachCase") {
        startCoach(e.target.value);
        render();
      }
    });
  }

  L.history = loadHistory();
  bind();

  window.RCLab = { mount, render, data: () => L.data, buildAnswer, startCoach };
})();
