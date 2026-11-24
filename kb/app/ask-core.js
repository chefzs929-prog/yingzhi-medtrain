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

  // 越界范围：与 kb/scripts/ask_engine.py、kb/app/student-lab.js 保持同一套口径。
  // 提问页与 DeepWorks 技能必须共用这套边界，不能一个答一个拒。
  var SCOPE_WORDS = [
    "治疗", "怎么治", "如何治", "治吗", "手术", "用药", "药物", "吃什么药", "用什么药",
    "抗生素", "抗结核", "剂量", "化疗", "放疗", "靶向", "免疫治疗",
    "预后", "生存期", "能活多久", "活多久", "分期", "处方", "急救", "抢救",
    "住院", "出院", "引流", "穿刺", "抽水", "抽液", "置管", "闭式引流",
    "活检", "要不要做", "需要做", "建议做", "固定", "复位", "石膏",
    "气管插管", "插管", "机械通气", "疫苗", "接种", "护理", "康复", "预防",
    "严重吗", "会死吗",
  ];
  var SCOPE_RULES = [
    ["分期判断", ["分期", "早期还是晚期", "晚期还是早期", "几期", "tnm"]],
    ["病因判断", ["细菌还是病毒", "病毒还是细菌", "细菌感染", "病毒感染", "什么原因引起", "病因", "病原体"]],
    ["检查方式（本工具只判胸片）", ["ct上", "ct片", "核磁", "mri", "磁共振", "超声", "b超", "彩超", "pet"]],
    ["患者隐私", ["叫什么名字", "叫什么", "姓名", "多大年纪", "身份证", "电话号码", "住址", "哪家医院"]],
    ["准确性保证", ["100%", "百分之百", "保证准确", "一定能确诊", "包准", "保证不出错"]],
    ["非医学任务", ["写代码", "python", "翻译成", "写作文", "做表格", "写一段代码"]],
    ["就诊指引", ["挂哪个科", "看哪个科", "挂号", "去哪个医院"]],
    ["特殊人群与放射防护", ["儿童拍", "孕妇拍", "辐射剂量", "防护"]],
    ["骨骼与关节系统", ["骨折", "退变", "骨质疏松", "骨破坏"]],
  ];
  var NON_CHEST = ["甲状腺", "乳腺", "肝脏", "胆囊", "胰腺", "脾脏", "肾脏", "肾上腺",
    "盆腔", "子宫", "卵巢", "前列腺", "头颅", "大脑", "脊柱", "脊髓", "骨盆",
    "髋关节", "膝关节", "踝关节", "肩关节", "腕关节", "肘关节"];
  var CHEST_WORDS = ["胸", "肺", "心", "纵隔", "膈", "肋", "气胸", "实变", "积液"];
  var TOO_BROAD = ["胸片", "片子", "影像", "图片", "看看", "这个"];
  var SCOPE_SUGGESTIONS = ["气胸在胸片上怎么找", "实变和胸腔积液怎么区分", "这个分区标注的依据是什么"];

  function scopeReason(q) {
    var s = norm(q);
    if (!s) return "";
    for (var i = 0; i < SCOPE_WORDS.length; i++) {
      if (s.indexOf(norm(SCOPE_WORDS[i])) >= 0) return "治疗 / 预后 / 操作建议";
    }
    for (var r = 0; r < SCOPE_RULES.length; r++) {
      var words = SCOPE_RULES[r][1];
      for (var j = 0; j < words.length; j++) {
        if (s.indexOf(norm(words[j])) >= 0) return SCOPE_RULES[r][0];
      }
    }
    if (/(诊断|确诊|是不是.{0,4}(癌|肿瘤|病)|什么病|良性还是恶性|恶性还是良性)/.test(s) &&
        !/(依据|标准|怎么找|表现|征象|鉴别|区分)/.test(s)) return "诊断结论";
    return "";
  }

  function nonChestReason(q) {
    var s = norm(q);
    if (!s) return "";
    var hasNon = NON_CHEST.some(function (w) { return s.indexOf(norm(w)) >= 0; });
    if (!hasNon) return "";
    var hasChest = CHEST_WORDS.some(function (w) { return s.indexOf(norm(w)) >= 0; });
    return hasChest ? "" : "非胸部部位";
  }

  function tooBroadReason(q) {
    var s = norm(q);
    return TOO_BROAD.some(function (w) { return s === norm(w); }) ? "问句过于宽泛" : "";
  }

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
    // 先过范围门：治疗/预后/操作/非胸部/过宽问句一律不进入检索。
    var scope = scopeReason(q) || nonChestReason(q) || tooBroadReason(q);
    if (scope) return { kind: "refusal", scope: scope, score: 1, item: null };
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
    scopeReason: scopeReason,
    nonChestReason: nonChestReason,
    tooBroadReason: tooBroadReason,
    SCOPE_SUGGESTIONS: SCOPE_SUGGESTIONS,
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
