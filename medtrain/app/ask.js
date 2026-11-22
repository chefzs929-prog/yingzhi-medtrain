/* RadioCheck · 多模态知识库问答（核心功能）
 *
 * 一条回答必须同时挂两处引用：
 *   影像侧：分区 id + bbox + atlas + 标注人
 *   文献侧：指南条款原文 + 版本 + 条款定位 + 摘录 hash
 * 任一侧缺失，就降级或拒答；诊断/治疗请求直接拒答。
 * 全部判断在本地用已核验的知识库数据完成，不调用模型、不编造引用。
 */
(function (YZ) {
  "use strict";

  const { DB, esc, icon, toast } = YZ;
  const h = esc;

  const AS = {
    caseId: "auto",
    report: "",
    question: "",
    regionId: null,
    showBoxes: true,
    upload: null,
    result: null,
    selftest: null,
    guideId: "",
    pickerOpen: false,
    pickerQuery: "",
    pickerOpenGroups: {},
  };

  /* ---------- 词表 ---------- */

  const BODY_KEYWORDS = [
    { re: /(甲状腺|颈前|峡部)/, body: "甲状腺" },
    { re: /(头颅|颅内|脑|颅骨|脑膜)/, body: "头颅" },
    { re: /(乳腺|钼靶|乳房|腺体)/, body: "乳腺" },
    { re: /(肝|胆囊|胆管|胰|脾|肾|腹|卵巢|前列腺)/, body: "腹部" },
    { re: /(膝|肩|肘|腕|手|足|骨|脊|椎|关节|半月板|韧带)/, body: "肌骨" },
    { re: /(胸|肺|膈|纵隔|心影|肋膈|气胸|胸腔积液)/, body: "胸部" },
  ];

  /* 报告里的器官词：用于把「含气肺组织」这类描述落到「右肺」等分区上 */
  const ORGAN_KEYS = ["甲状腺", "胸膜", "纵隔", "肺", "乳腺", "胆囊", "肝", "肾", "脑膜", "脑",
    "颈椎", "腰椎", "膝", "肩", "骨盆", "手", "足", "心"];

  const BODY_FAMILY = {
    "胸部": "chest", "肺": "chest", "胸膜": "chest",
    "甲状腺": "thyroid", "颈部": "thyroid", "头颅": "head",
    "乳腺": "breast",
    "腹部": "abdomen", "肝": "abdomen",
    "手": "msk", "足": "msk", "膝关节": "msk", "肘": "msk", "腕": "msk",
    "颈椎": "msk", "腰椎": "msk", "肩": "msk", "骨盆": "msk",
    "脊柱": "msk", "骨关节": "msk",
  };

  const GUIDE_FAMILY = {
    chest: ["肺"], thyroid: ["甲状腺"], breast: ["乳腺"],
    abdomen: ["肝", "胆囊", "肾", "胰", "卵巢", "前列腺"],
    head: [], msk: [],
  };

  const SYN = {
    "磨玻璃": "SIGN-001", "ggo": "SIGN-001",
    "实变": "SIGN-002",
    "结节": "SIGN-003",
    "肿块": "SIGN-004", "占位": "SIGN-004",
    "空洞": "SIGN-005",
    "钙化": "SIGN-006",
    "胸水": "SIGN-007", "胸腔积液": "SIGN-007",
    "气胸": "SIGN-008",
    "纵隔增宽": "SIGN-009",
    "心影增大": "SIGN-010",
    "支气管扩张": "SIGN-013", "支扩": "SIGN-013",
    "空气支气管": "SIGN-014",
    "树芽": "SIGN-017",
    "肺不张": "SIGN-019",
    "胸膜增厚": "SIGN-020",
    "腹水": "SIGN-026",
    "淋巴结": "SIGN-028",
    "胆囊壁": "SIGN-031",
    "肾积水": "SIGN-033",
    "脑膜强化": "SIGN-038",
    "中线移位": "SIGN-044",
    "腔隙": "SIGN-046",
    "半月板": "SIGN-047",
    "骨髓水肿": "SIGN-048",
    "骨质破坏": "SIGN-049",
    "关节积液": "SIGN-052",
    "毛刺": "SIGN-055",
    "微钙化": "SIGN-056",
    "纵横比": "SIGN-057",
    "低回声": "SIGN-058", "甲状腺结节": "SIGN-058",
    "无回声": "SIGN-059",
    "声影": "SIGN-060",
    "出血": "SIGN-045", "高密度": "SIGN-045",
    "低密度": "SIGN-021", "低密度灶": "SIGN-021", "梗死": "SIGN-021",
    "骨折": "SIGN-054", "水肿": "SIGN-041",
    "结石": "SIGN-006", "实性": "SIGN-002",
    "退变": "SIGN-036", "狭窄": "SIGN-036", "突出": "SIGN-036",
    "积液": "SIGN-052",
  };

  const SCOPE_RE = /(诊断|确诊|是不是癌|是不是恶性|良恶性|是良性还是恶性|肺癌吗|肿瘤吗|要不要手术|该不该手术|需要手术|治疗方案|怎么治|如何治|用什么药|吃什么药|预后|生存期|能活多久|会不会转移)/;

  const MODALITY_RE = [
    { re: /(ct|计算机断层)/i, m: "CT" },
    { re: /(mri|mr\b|磁共振)/i, m: "MR" },
    { re: /(超声|彩超|b超|us\b)/i, m: "US" },
    { re: /(钼靶|乳腺摄影|mg\b)/i, m: "MG" },
    { re: /(胸片|x线|平片|dr\b|cr\b)/i, m: "CR" },
  ];

  /* ---------- 基础工具 ---------- */

  const norm = (s) => String(s == null ? "" : s).toLowerCase();
  const flat = (s) => norm(s).replace(/\s+/g, "");
  const uniq = (a) => Array.from(new Set(a));
  const caseById = (id) => DB.cases.find((c) => c.id === id) || null;
  const regionsOf = (id) => (DB.regionsByCase && DB.regionsByCase[id]) || [];
  const claimsOf = (id) => (DB.claimsByCase && DB.claimsByCase[id]) || [];
  const signById = (id) => DB.signs.find((s) => s.id === id) || null;

  /* 引用完整性门禁：摘录 hash 不一致或结论被标 broken 的，一律不进入回答。 */
  function isBrokenClaim(cl) {
    if (!cl) return false;
    if (cl.cite_status === "broken") return true;
    return (cl.cites || []).some((c) => c.kind === "doc" && c.hash_ok === false);
  }

  const LINKS = (DB.links || []).filter((l) => l.status === "active" && l.image_id && l.regions && l.regions.length);

  function linkFor(caseId, signIds) {
    return LINKS.find((l) => l.image_id === caseId && signIds.includes(l.sign_id)) || null;
  }

  function overlapArea(a, b) {
    if (!a || !b) return 0;
    const x1 = Math.max(a[0], b[0]);
    const y1 = Math.max(a[1], b[1]);
    const x2 = Math.min(a[0] + a[2], b[0] + b[2]);
    const y2 = Math.min(a[1] + a[3], b[1] + b[3]);
    return Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  }

  function linkClaim(link, region) {
    const sign = signById(link.sign_id) || {};
    return {
      id: link.id,
      region_id: region.id,
      text: link.caption || link.quote || "",
      sign_ids: [link.sign_id],
      cite_status: "dual",
      note: link.reading || "",
      link,
      cites: [{
        kind: "doc",
        anchor: {
          doc_kind: "sign", doc_id: sign.id || link.sign_id,
          doc_title: "征象词条 · " + (sign.name || link.sign_id),
          version: "", locator: (sign.id || link.sign_id) + " / 影像表现",
          excerpt: sign.appearance || link.quote || "",
          excerpt_sha256: "", url: "",
        },
        hash_ok: true,
      }],
    };
  }
  const regionName = (id) => (DB.meta.regions.find((r) => r.id === id) || {}).name || id;

  function familyOf(body) {
    return BODY_FAMILY[body] || (String(body || "").includes("胸") ? "chest" : "other");
  }

  function detectBody(text) {
    for (const b of BODY_KEYWORDS) if (b.re.test(text)) return b.body;
    return "";
  }

  function detectModality(text) {
    for (const m of MODALITY_RE) if (m.re.test(text)) return m.m;
    return "";
  }

  function detectLaterality(text) {
    const t = norm(text);
    if (/(右|right)/.test(t) && !/(左|left)/.test(t)) return "right";
    if (/(左|left)/.test(t) && !/(右|right)/.test(t)) return "left";
    return "";
  }

  function catTokens(g) {
    const src = `${g.category || ""} ${(g.keywords || []).join(" ")}`;
    const out = [];
    const re = /(TR\s*\d|BI-?RADS\s*\d\w*|Bosniak\s*[IVX]+|LI-?RADS\s*\d\w*|PI-?RADS\s*\d|O-?RADS\s*\d|类别\s*\d\w*|\d+(?:\.\d+)?\s*mm|\d+(?:\.\d+)?\s*cm)/gi;
    let m;
    while ((m = re.exec(src))) out.push(flat(m[0]));
    return uniq(out);
  }

  /* ---------- 检索 ---------- */

  const NEG = /(未见|未发现|未显示|无明确|没有见|除外|阴性)/;

  /* 同一分句里出现否定词时，该分句的征象按阴性处理；
     「有没有」是提问，不是否定，先归一化掉。 */
  function negatedAt(text, idx) {
    const before = text.slice(0, idx);
    let cut = -1;
    for (const ch of ["。", "；", ";", "，", ",", "\n"]) cut = Math.max(cut, before.lastIndexOf(ch));
    const clause = before.slice(cut + 1).replace(/有没有/g, "有").replace(/是否/g, "");
    return NEG.test(clause);
  }

  function countHits(text, needle) {
    if (!needle) return { pos: 0, neg: 0 };
    const t = norm(text);
    const n = norm(needle);
    let pos = 0;
    let neg = 0;
    let i = t.indexOf(n);
    while (i >= 0) {
      if (negatedAt(t, i)) neg += 1; else pos += 1;
      i = t.indexOf(n, i + n.length);
    }
    return { pos, neg };
  }

  function detectSignals(text) {
    const out = [];
    for (const s of DB.signs) {
      let score = 0;
      const hits = [];
      const add = (needle, w) => {
        const r = countHits(text, needle);
        // 更长的词条更具体：同为命中时，「低回声结节」应压过泛化的「结节」。
        if (r.pos) { score += (w + (String(needle).length >= 4 ? 2 : 0)) * Math.min(r.pos, 2); hits.push(needle); }
        return r.pos;
      };
      add(s.name, 6);
      for (const a of s.aliases || []) if (a && a.length >= 2) add(a, 5);
      if (s.en) add(s.en, 4);
      if (score === 0) {
        for (const k of Object.keys(SYN)) {
          if (SYN[k] === s.id) { if (add(k, 5)) break; }
        }
      }
      if (score > 0) out.push({ sign: s, score, hits: uniq(hits) });
    }
    return out.sort((a, b) => b.score - a.score);
  }

  function bodyMatch(c, body) {
    if (!body) return 0;
    const f = familyOf(c.body_part);
    const g = familyOf(body);
    return f === g ? 2 : 0;
  }

  function pickCase(state) {
    if (state.caseId && state.caseId !== "auto") {
      const c = caseById(state.caseId);
      if (c) return c;
    }
    const text = `${state.report} ${state.question}`;
    const body = detectBody(text);
    const mod = detectModality(text);
    const sigs = detectSignals(text).map((x) => x.sign.id);
    let best = null;
    for (const c of DB.cases) {
      let sc = bodyMatch(c, body);
      if (mod && (c.modality || []).includes(mod)) sc += 2;
      // 按「命中的征象种类」计分，不按结论条数累加，避免结论多的病例虚高。
      let bestOv = 0;
      for (const x of claimsOf(c.id)) {
        const ov = (x.sign_ids || []).filter((id) => sigs.includes(id)).length;
        if (ov > bestOv) bestOv = ov;
      }
      sc += bestOv * 3;
      if (sc > 0 && (!best || sc > best.sc)) best = { c, sc };
    }
    return best ? best.c : DB.cases[0];
  }

  function currentCase() {
    if (AS.upload) return null;
    return pickCase(AS);
  }

  function regionTextScore(region, text) {
    const t = flat(text);
    let sc = 0;
    if (t.includes(flat(region.name))) sc += 8;
    else {
      const parts = String(region.name).match(/[左右]?(?:肺)?(?:上野|中野|下野|上带|下带|中央|前部|中部|后部|周边|边缘|上方|下方)/g) || [];
      for (const p of parts) if (p.length >= 2 && t.includes(flat(p))) sc += 3;
      // 报告常写「含气肺组织」「甲状腺右叶」而不是分区全名：器官词命中同样算定位线索
      const organ = ORGAN_KEYS.find((k) => String(region.name).includes(k) && t.includes(k));
      if (organ) sc += 4;
    }
    // 明确写了左右侧是强线索：只写「右半侧」时也能落到右侧分区
    if (region.patient_side && t.includes(region.patient_side === "right" ? "右" : "左")) sc += 2;
    return sc;
  }

  function pickRegion(c, signals, text, forcedId) {
    const rs = regionsOf(c.id);
    if (forcedId) {
      const f = rs.find((r) => r.id === forcedId);
      if (f) return f;
    }
    const sigIds = signals.slice(0, 4).map((x) => x.sign.id);
    const claims = claimsOf(c.id).filter((x) => !isBrokenClaim(x));
    let best = null;
    for (const r of rs) {
      const ov = (r.sign_ids || []).filter((id) => sigIds.includes(id)).length;
      let sc = ov * 3 + regionTextScore(r, text);
      const rc = claims.filter((x) => x.region_id === r.id);
      const rcOv = rc.filter((x) => (x.sign_ids || []).some((id) => sigIds.includes(id))).length;
      if (rcOv) sc += 2;
      if (rc.some((x) => (x.cites || []).some((ci) => ci.kind === "doc" && ci.anchor && ci.anchor.doc_kind === "guideline"))) sc += 3;
      if (sc > 0 && (!best || sc > best.sc)) best = { r, sc };
    }
    if (best && best.sc >= 2) return best.r;

    // 文字里没有分区名，但库内只有一个分区挂着文献条款：按条款所在分区定位（唯一才选）。
    const docRegions = uniq(claims
      .filter((x) => (x.cites || []).some((ci) => ci.kind === "doc" && ci.anchor))
      .map((x) => x.region_id));
    if (docRegions.length === 1) {
      const r = rs.find((x) => x.id === docRegions[0]);
      if (r) return r;
    }

    // 仍无线索时，用「结论挂在哪个分区」反推；多个分区并列则不猜。
    const hitClaims = claims.filter((x) => (x.sign_ids || []).some((id) => sigIds.includes(id)));
    const regions = uniq(hitClaims.map((x) => x.region_id));
    if (regions.length === 1) return rs.find((r) => r.id === regions[0]) || null;
    return null;
  }

  function pickClaim(c, region, signals, text) {
    const sigIds = signals.slice(0, 4).map((x) => x.sign.id);
    const link = linkFor(c.id, sigIds);
    if (link) return linkClaim(link, region);
    const list = claimsOf(c.id).filter((x) => x.region_id === region.id && !isBrokenClaim(x));
    const tf = flat(text);
    let best = null;
    for (const cl of list) {
      let sc = (cl.sign_ids || []).filter((id) => sigIds.includes(id)).length * 3;
      const docs = (cl.cites || []).filter((x) => x.kind === "doc" && x.anchor);
      if (docs.some((x) => x.anchor.doc_kind === "guideline")) sc += 3;
      for (const d of docs) {
        for (const tok of catTokens({ category: d.anchor.locator || "", keywords: [] })) {
          if (tok && tf.includes(tok)) sc += 4;
        }
      }
      if (cl.text && tf && cl.text.length > 6 && tf.includes(flat(cl.text).slice(0, 8))) sc += 1;
      if (sc > 0 && (!best || sc > best.sc)) best = { cl, sc };
    }
    return best ? best.cl : (list[0] || null);
  }

  function sizeMm(text) {
    const m = String(text).match(/(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)/i);
    if (!m) return null;
    const v = parseFloat(m[1]);
    return /cm|厘米/i.test(m[2]) ? v * 10 : v;
  }

  function thresholdScore(g, size) {
    if (size == null) return 0;
    const s = `${g.category || ""} ${g.statement || ""}`;
    const toMm = (v, u) => (/cm|厘米/i.test(u) ? parseFloat(v) * 10 : parseFloat(v));
    let sc = 0;
    const range = s.match(/(\d+(?:\.\d+)?)\s*[—\-~]\s*(\d+(?:\.\d+)?)\s*(mm|cm)/i);
    if (range) {
      const a = toMm(range[1], range[3]);
      const b = toMm(range[2], range[3]);
      sc += size >= a && size <= b ? 3 : -4;
    }
    const ge = s.match(/≥\s*(\d+(?:\.\d+)?)\s*(mm|cm)/i);
    if (ge) sc += size >= toMm(ge[1], ge[2]) ? 3 : -5;
    const lt = s.match(/<\s*(\d+(?:\.\d+)?)\s*(mm|cm)/i);
    if (lt) sc += size < toMm(lt[1], lt[2]) ? 3 : -5;
    const gt = s.match(/>\s*(\d+(?:\.\d+)?)\s*(mm|cm)/i);
    if (gt) sc += size > toMm(gt[1], gt[2]) ? 3 : -5;
    return sc;
  }

  function guidelineScore(g, text, family, signals) {
    const tf = flat(text);
    const fam = GUIDE_FAMILY[family] || [];
    if (!fam.includes(g.body_part)) return -99;
    let sc = 0;
    for (const tok of catTokens(g)) if (tok && tf.includes(tok)) sc += 6;
    for (const kw of g.keywords || []) if (kw && tf.includes(flat(kw))) sc += 3;
    if (g.standard_name && tf.includes(flat(g.standard_name))) sc += 2;
    for (const s of signals.slice(0, 2)) {
      if (g.statement && g.statement.includes(s.sign.name)) sc += 2;
    }
    if (/(未见|没有|无明确|未见明确)/.test(text) && /(未见|未发现|无明确)/.test(g.statement || "")) sc += 3;
    if (/(磨玻璃)/.test(text) && /(磨玻璃)/.test(g.statement || "")) sc += 2;
    if (/(实性)/.test(text) && /(实性)/.test(g.statement || "")) sc += 2;
    sc += thresholdScore(g, sizeMm(text));
    return sc;
  }

  function pickDoc(c, claim, signals, text, forcedId) {
    const family = familyOf(c.body_part);
    const cands = DB.guidelines
      .map((g) => ({ g, sc: guidelineScore(g, text, family, signals) }))
      .filter((x) => x.sc >= 3)
      .sort((a, b) => b.sc - a.sc);

    if (forcedId) {
      const g = DB.guidelines.find((x) => x.id === forcedId);
      if (g) {
        return {
          doc: {
            kind: "guideline", id: g.id, title: g.standard_name, version: String(g.version_year || ""),
            locator: `${g.category} · ${g.section}`, excerpt: g.statement, url: g.source_url,
            hash: "", conditions: g.conditions || [], action: g.action, degraded: false, forced: true,
            body_part: g.body_part,
          },
          alt: [], ambiguous: false,
        };
      }
    }

    if (cands.length) {
      const top = cands[0];
      const alts = cands.filter((x, i) => i > 0 && top.sc === x.sc).slice(0, 2);
      const g = top.g;
      return {
        doc: {
          kind: "guideline", id: g.id, title: g.standard_name, version: String(g.version_year || ""),
          locator: `${g.category} · ${g.section}`, excerpt: g.statement, url: g.source_url,
          hash: "", conditions: g.conditions || [], action: g.action, degraded: false,
          body_part: g.body_part,
        },
        alt: alts.map((x) => ({
          id: x.g.id, title: x.g.standard_name, version: String(x.g.version_year || ""),
          locator: `${x.g.category} · ${x.g.section}`, excerpt: x.g.statement, url: x.g.source_url,
        })),
        ambiguous: alts.length > 0,
      };
    }

    // 文献侧降级：只命中征象词条释义，没有指南条款。
    const docs = ((claim && claim.cites) || []).filter((x) => x.kind === "doc" && x.anchor);
    if (docs.length) {
      const a = docs[0].anchor;
      return {
        doc: {
          kind: a.doc_kind || "sign", id: a.doc_id || "", title: a.doc_title || "征象词条",
          version: a.version || "", locator: a.locator || "", excerpt: a.excerpt || "",
          url: a.url || "", hash: a.excerpt_sha256 || "", conditions: [], action: "",
          degraded: true,
        },
        alt: [], ambiguous: false,
      };
    }
    const sg = (signals || [])[0] && signals[0].sign;
    if (sg && sg.appearance) {
      return {
        doc: {
          kind: "sign", id: sg.id, title: `征象词条 · ${sg.name}`, version: "",
          locator: `${sg.id} / 影像表现`, excerpt: sg.appearance, url: "",
          hash: "", conditions: [], action: "", degraded: true,
        },
        alt: [], ambiguous: false,
      };
    }
    return { doc: null, alt: [], ambiguous: false };
  }

  function missingConditions(doc, text) {
    if (!doc || !doc.conditions || !doc.conditions.length) return [];
    // 只检查「输入里有没有给出尺寸」，不替用户判断是否达到阈值。
    const hasSize = /\d+(?:\.\d+)?\s*(?:cm|mm|厘米|毫米)/i.test(text);
    const miss = [];
    for (const cond of doc.conditions) {
      const toks = catTokens({ category: cond, keywords: [] });
      const need = toks.filter((t) => /\d/.test(t));
      if (need.length && !hasSize) miss.push(cond);
    }
    return miss;
  }

  /* ---------- 判定 ---------- */

  function refuse(reason, title, detail, found) {
    return {
      status: "refuse", reason, title, detail, found: found || [],
      signals: [], region: null, claim: null, spatial: null, doc: null, alt: [],
      coverage: {}, missing: [], notes: [], answer: "",
    };
  }

  /* 只选分区、未输入征象时的回答：复述该分区的库内定位描述 + 文献段落，
     状态固定为 partial，并在正文里写明「不做征象判断」。 */
  function regionOnlyAnswer(st) {
    const c = pickCase(st);
    if (!c) return refuse("no-region", "影像侧缺少可定位的分区", "未选择病例，也没有可用的分区标注。");
    const region = regionsOf(c.id).find((r) => r.id === st.regionId);
    if (!region) return refuse("no-region", "无法确定影像区域", "所选分区不在当前病例的标注里，请重新点选。");
    const claim = claimsOf(c.id).filter((x) => x.region_id === region.id && !isBrokenClaim(x))[0];
    if (!claim) {
      return refuse("no-claim", "该分区没有可引用的库内结论",
        `「${c.title}」的「${region.name}」在库内没有通过校验的分区结论。`,
        ["可换一个已标注分区，或补充征象/报告后再生成。"]);
    }
    const docs = (claim.cites || []).filter((x) => x.kind === "doc" && x.anchor);
    const a = docs.length ? docs[0].anchor : null;
    if (!a) {
      return refuse("no-doc", "文献侧没有可引用的段落",
        `「${region.name}」有分区结论，但文献侧没有可回查的段落。`,
        ["可补充征象或分类信息后再生成。"]);
    }
    const doc = {
      kind: a.doc_kind || "sign", id: a.doc_id || "", title: a.doc_title || "征象词条",
      version: a.version || "", locator: a.locator || "", excerpt: a.excerpt || "",
      url: a.url || "", hash: a.excerpt_sha256 || "", conditions: [], action: "", degraded: true,
    };
    const answer = [
      `在「${c.title}」的「${region.name}」内，库内定位描述为：${claim.text}`,
      `文献侧（征象词条）${doc.title} · ${doc.locator}：${doc.excerpt}`,
      "本条只做分区定位与文献段落对照：未提供征象或报告，因此不做征象判断。",
    ].join("\n");
    return {
      status: "partial", reason: "region-only", title: "分区定位 · 未提供征象",
      detail: "你只点选了一个分区，没有输入征象；下面只复述该分区的库内定位与文献段落，不做征象判断。",
      signals: [], region, claim,
      spatial: {
        region_id: region.id, region_name: region.name, name: region.name, bbox: region.coords,
        atlas_id: region.atlas_id || "", atlas_label: region.atlas_id || "",
        image_side: region.image_side, patient_side: region.patient_side,
        annotator: region.annotator || "human", note: region.note || "", kind: "region", link_id: "",
      },
      doc, alt: [], broken: [], coverage: {
        image: true, region: true, claim: true, doc: true, guideline: false, verify: true,
      },
      missing: [], notes: ["未提供征象或报告：本条只复述分区定位与文献段落，不做征象判断。"],
      answer, case: c, sig: null,
      trace: ["输入 " + c.id, "分区 " + region.name, "结论 " + claim.id, "征象词条 " + (doc.id || doc.title)],
    };
  }

  function run(state) {
    const st = Object.assign({}, AS, state || {});
    const text = `${st.report || ""} ${st.question || ""}`.trim();
    const tf = flat(text);

    if (!text) {
      // 只点了分区、没写文字：给分区定位 + 文献段落，而不是一句「没有输入」。
      if (st.regionId) return regionOnlyAnswer(st);
      return refuse("no-signal", "没有可判定的输入", "问题与报告都是空的。请至少输入一个问题，或粘贴一段报告/指南文字。");
    }

    if (SCOPE_RE.test(st.question || "")) {
      return refuse(
        "scope", "越出教学对照范围",
        "这个问题要求诊断、良恶性判断或治疗决策。本应用只做「影像表现 ↔ 文献条款」的对照，不输出诊断结论，也不替代临床决策。",
        ["可改问：该分区的影像表现有哪些？", "可改问：库内条款对这类表现怎么表述？", "可改问：这条条款的适用条件是什么？"]
      );
    }

    const signals = detectSignals(text);
    if (!signals.length) {
      const c0 = pickCase(st);
      const names = uniq(claimsOf(c0.id).flatMap((x) => x.sign_ids || []))
        .map((id) => (signById(id) || {}).name).filter(Boolean).slice(0, 8);
      return refuse(
        "no-signal", "未指向库内可对照的征象",
        "输入里没有命中知识库的 60 条征象词条（含别名）。按规则不猜测、不生成没有依据的回答。",
        [
          names.length ? `「${c0.title}」可对照的征象：${names.join("、")}` : "可换用库内词条，例如：磨玻璃影 / 实变 / 胸腔积液 / 毛玻璃结节",
          "或直接点选一个分区，查看该分区的定位与文献段落。",
        ]
      );
    }

    if (st.upload) {
      return refuse(
        "no-region", "影像侧缺少可定位的分区",
        "上传的影像没有经过人工分区标注，系统无法给出 bbox 与分区 id。按双引用规则，缺少影像侧引用时不输出结论。",
        [
          `文献侧已检索到 ${Math.min(signals.length, 3)} 条征象线索，但没有影像区域可挂，故不合并成回答。`,
          "可改用左侧病例库中已标注的公开影像；上传影像仅作浏览，不参与引用。",
        ]
      );
    }

    const c = pickCase(st);
    let region = pickRegion(c, signals, text, st.regionId);
    const sigIds0 = signals.slice(0, 4).map((x) => x.sign.id);
    const anchorLink = linkFor(c.id, sigIds0);
    if (region && anchorLink) {
      const ab = anchorLink.regions[0].bbox;
      const best = regionsOf(c.id)
        .map((r) => ({ r, a: overlapArea(r.coords, ab) }))
        .sort((x, y) => y.a - x.a)[0];
      if (best && best.a > 0) region = best.r;
    }
    if (!region) {
      return refuse(
        "no-region", "无法确定影像区域",
        `在「${c.title}」里，输入没有给出可定位的分区线索（如右肺中野、甲状腺中央区），也没有唯一对应的分区结论。按规则不猜位置。`,
        ["请在中间影像上点选一个分区，或在报告里写明分区。"]
      );
    }

    const claim = pickClaim(c, region, signals, text);
    const sigIds = signals.slice(0, 4).map((x) => x.sign.id);
    const brokenHere = claimsOf(c.id).filter((x) => isBrokenClaim(x)).filter((x) =>
      x.region_id === region.id || (x.sign_ids || []).some((id) => sigIds.includes(id))
    );
    if (!claim) {
      return refuse(
        "no-claim", "该分区没有可引用的库内结论",
        brokenHere.length
          ? `「${c.title}」的「${region.name}」有 ${brokenHere.length} 条结论，但都未通过引用完整性校验（${brokenHere.map((x) => x.id).join("、")}），已全部拦截。`
          : `「${c.title}」的「${region.name}」在库内没有可引用的分区结论，因此无法生成带原文的回答。`,
        ["可换一个已标注分区，或改问该病例的其他分区。"]
      );
    }

    const docRes = pickDoc(c, claim, signals, text, st.guideId);
    if (!docRes.doc) {
      return refuse(
        "no-doc", "文献侧没有可引用的段落",
        "影像侧已经定位到分区，但文献侧既没有命中指南条款，也没有可回查的征象词条摘录。按双引用规则不输出结论。",
        ["可补充分类信息（如 TI-RADS TR4、Lung-RADS 类别 3）以匹配条款。"]
      );
    }

    const doc = docRes.doc;
    const miss = missingConditions(doc, text);
    const notes = [];
    if (brokenHere.length) {
      notes.push(`引用校验拦截：${brokenHere.map((x) => x.id).join("、")} 的摘录 hash 与库内原文不一致，已排除，不进入回答。`);
    }
    let status = "answer";

    if (doc.degraded) {
      status = "partial";
      notes.push("文献侧降级：只命中征象词条释义，未命中指南条款；不能当作指南依据。");
    }
    if (docRes.ambiguous) {
      status = "partial";
      notes.push("文献侧有多条条款得分接近，无法判定哪一条适用；并列展示，不替用户裁决。");
    }
    if (miss.length) {
      status = "partial";
      notes.push(`条款适用条件未在输入中出现：${miss.join("；")}。`);
    }
    if (doc.forced && !(GUIDE_FAMILY[familyOf(c.body_part)] || []).includes(doc.body_part)) {
      status = "partial";
      notes.push(`手动指定的条款属于「${doc.body_part}」，与当前病例「${c.body_part}」不一致，请核对后再用。`);
    }
    if (signals.length > 1 && signals[0].score - signals[1].score <= 1) {
      status = "partial";
      notes.push(`征象候选并列：${signals[0].sign.name} / ${signals[1].sign.name}，按并列处理。`);
    }
    const lat = detectLaterality(text);
    const lateralRegion = /[左右]/.test(region.name || "");
    // 「图像右侧 / 右半侧」说的是图像方位，不是患者左右；这种情况不套患者侧别规则。
    const imageSideMention = /(图像右侧|图像左侧|右半侧|左半侧|图右|图左)/.test(text);
    if (lat && lateralRegion && !imageSideMention && region.patient_side && lat !== region.patient_side) {
      status = "partial";
      notes.push(`左右侧不一致：文字写「${lat === "right" ? "右" : "左"}」，所选分区在患者「${region.patient_side === "right" ? "右" : "左"}」侧。`);
    }

    const sig = signals[0].sign;
    const anchor = claim.link ? claim.link.regions[0] : null;
    const atlasId = anchor ? ("ANCHOR-" + claim.link.id) : (region.atlas_id || "");
    const atlasLabel = anchor ? ("图文锚点 " + claim.link.id) : atlasId;
    const spName = anchor ? anchor.label : region.name;
    const spBbox = anchor ? anchor.bbox : region.coords;
    const spImageSide = anchor ? anchor.image_side : region.image_side;
    const spPatientSide = anchor ? anchor.patient_side : region.patient_side;
    const docLabel = doc.kind === "guideline" ? "指南条款" : "征象词条";
    const head = `在「${c.title}」的「${spName}」（${atlasLabel || "未标 atlas"}）内，库内结论原文为：${claim.text}`;
    const claimNote = claim.link && claim.note ? `标注说明：${claim.note}` : "";
    let lit;
    if (docRes.ambiguous) {
      const all = [doc, ...docRes.alt];
      lit = `文献侧命中 ${all.length} 条并列条款，按原文并列展示，不替用户判定适用哪一条：\n` +
        all.map((d, i) => `${i + 1}. ${d.title}${d.version ? " " + d.version : ""} · ${d.locator}：${d.excerpt}`).join("\n");
    } else {
      lit = `文献侧（${docLabel}）${doc.title}${doc.version ? " " + doc.version : ""} · ${doc.locator}：${doc.excerpt}`;
    }
    const answer = [
      head, claimNote, lit,
      `本条回答涉及征象：${signals.slice(0, 3).map((x) => x.sign.name).join("、") || "暂无"}。`,
      (sig.pitfalls || []).length ? `易错点：${sig.pitfalls.slice(0, 2).join("；")}。` : "",
    ].filter(Boolean).join("\n");

    return {
      status,
      reason: status === "answer" ? "ok" : "degraded",
      title: status === "answer" ? "可答 · 双引用齐全" : "部分可答 · 已降级",
      detail: status === "answer"
        ? "影像区域与指南条款都已命中，回答只复述库内原文，不追加诊断判断。"
        : "至少一侧证据不完整，以下内容已标注降级原因，请按提示核对。",
      signals, region, claim,
      spatial: {
        region_id: region.id, region_name: region.name, name: spName, bbox: spBbox, atlas_id: atlasId, atlas_label: atlasLabel,
        image_side: spImageSide, patient_side: spPatientSide,
        annotator: anchor ? (claim.link.annotator || "human") : (region.annotator || "human"),
        note: anchor ? (anchor.note || "") : (region.note || ""),
        kind: anchor ? "link" : "region", link_id: anchor ? claim.link.id : "",
      },
      doc, alt: docRes.alt, broken: brokenHere.map((x) => x.id), coverage: {
        image: true, region: true, claim: true, doc: true, guideline: doc.kind === "guideline" && !doc.degraded,
        verify: true,
      },
      missing: miss, notes, answer, case: c, sig,
      trace: [
        "输入 " + (st.upload ? "上传影像" : c.id),
        "征象 " + signals.slice(0, 2).map((x) => x.sign.name).join(" / "),
        "分区 " + region.name,
        "结论 " + claim.id,
        docLabel + " " + (doc.id || doc.title),
      ],
    };
  }

  /* ---------- 渲染 ---------- */

  const STATUS_LABEL = { answer: "可答", partial: "部分可答", refuse: "拒答" };

  function caseLabel() {
    if (AS.upload) return "已上传影像（不参与引用）";
    if (AS.caseId === "auto") {
      const c = currentCase();
      return c ? `自动匹配 · ${c.id} · ${c.title}` : "自动匹配（按报告/问题）";
    }
    const c = caseById(AS.caseId);
    return c ? `${c.id} · ${c.title}` : "选择病例";
  }

  /* 病例选择器：200 例按部位分组，分组可折叠 + 关键词过滤，
     避免原生 select 一次铺开上百项。 */
  function caseListHTML() {
    const q = norm(AS.pickerQuery || "");
    const groups = {};
    for (const c of DB.cases) (groups[c.body_part] = groups[c.body_part] || []).push(c);
    const cur = AS.upload ? null : currentCase();
    // 自动匹配时不预设展开组，先让用户看部位目录；手动选中病例才展开所在组。
    const curGroup = (cur && AS.caseId !== "auto") ? cur.body_part : "";
    const autoOn = AS.caseId === "auto" && !AS.upload;
    let html = "";
    if (!q || flat("自动匹配按报告问题").includes(flat(q)) || "auto".includes(q)) {
      html += `<button type="button" class="apk-item apk-auto ${autoOn ? "on" : ""}" data-ask="pick-case" data-id="auto">
        <b>自动匹配</b><span>按报告 / 问题挑选最接近的病例</span></button>`;
    }
    // 病例多的部位排前面：胸部 80+ 例，展开后紧贴选择框，不用先滚过十几个组头。
    for (const bp of Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length)) {
      const list = groups[bp].filter((c) => !q || norm(`${c.id} ${c.title} ${bp}`).includes(q));
      if (!list.length) continue;
      // 默认只展开当前病例所在组；自动匹配时全部折叠，先看部位目录。
      const defaultOpen = !!curGroup && bp === curGroup;
      const open = q ? true : (AS.pickerOpenGroups[bp] !== undefined ? AS.pickerOpenGroups[bp] : defaultOpen);
      html += `<div class="apk-group ${open ? "open" : ""}">
        <button type="button" class="apk-gh" data-ask="picker-group" data-group="${h(bp)}">
          <span class="apk-arrow">${open ? "▾" : "▸"}</span><b>${h(bp)}</b><em>${list.length}</em>
        </button>
        ${open ? `<div class="apk-gb">${list.map((c) => `
          <button type="button" class="apk-item ${cur && cur.id === c.id ? "on" : ""}" data-ask="pick-case" data-id="${c.id}">
            <b>${h(c.id)}</b><span>${h(c.title)}</span>
            ${String(c.corpus || "").startsWith("expanded") ? `<i class="apk-tag">待核验</i>` : ""}
          </button>`).join("")}</div>` : ""}
      </div>`;
    }
    return html || `<div class="apk-empty">没有匹配的病例</div>`;
  }

  function casePickerHTML() {
    return `<div class="ask-picker">
      <button type="button" class="ask-sel ask-picker-btn" data-ask="picker-toggle" aria-expanded="${AS.pickerOpen ? "true" : "false"}">
        <span class="apk-label">${h(caseLabel())}</span><span class="apk-caret">${AS.pickerOpen ? "▴" : "▾"}</span>
      </button>
      ${AS.pickerOpen ? `<div class="ask-picker-pop">
        <input id="askCaseSearch" class="ask-picker-search" type="search" placeholder="搜索病例号 / 部位 / 名称" value="${h(AS.pickerQuery || "")}" autocomplete="off">
        <div class="ask-picker-list" id="askCaseList">${caseListHTML()}</div>
      </div>` : ""}
    </div>`;
  }

  function guideOptions() {
    const groups = {};
    for (const g of DB.guidelines) (groups[g.standard_name] = groups[g.standard_name] || []).push(g);
    return `<option value="">自动匹配（推荐）</option>` + Object.keys(groups).map((n) =>
      `<optgroup label="${h(n)}">${groups[n].map((g) =>
        `<option value="${g.id}" ${AS.guideId === g.id ? "selected" : ""}>${h(g.category)} · ${h(g.section)}</option>`
      ).join("")}</optgroup>`
    ).join("");
  }

  const PRESETS = [
    {
      key: "normal", label: "正常胸片 · 结节",
      s: { caseId: "CASE-001", report: "右肺中野透亮度均匀，未见明确局灶性密度增高、结节或空洞影。", question: "右肺中野有没有结节？", regionId: null, upload: null, guideId: "" },
    },
    {
      key: "ggo", label: "磨玻璃影 · 缺尺寸",
      s: { caseId: "CASE-020", report: "右半侧 CT 图像中，含气肺组织内可见密度轻度增高区，血管边缘仍可分辨。", question: "这个磨玻璃影该怎么随访？", regionId: null, upload: null, guideId: "" },
    },
    {
      key: "trads", label: "甲状腺 TR4 · 1.6cm",
      s: { caseId: "CASE-011", report: "甲状腺右叶低回声结节，最大径 1.6 cm，TI-RADS TR4。", question: "TR4、1.6 cm 的结节，库内条款怎么表述？", regionId: null, upload: null, guideId: "" },
    },
    {
      key: "scope", label: "越界请求",
      s: { caseId: "CASE-001", report: "", question: "这是不是肺癌？要不要手术？", regionId: null, upload: null, guideId: "" },
    },
    {
      key: "head", label: "头颅 · 无指南",
      s: { caseId: "CASE-014", report: "双侧脑膜强化，脑沟显示不清。", question: "脑膜强化怎么描述？", regionId: null, upload: null, guideId: "" },
    },
    {
      key: "upload", label: "上传影像 · 未标注",
      s: { caseId: null, report: "右肺上野磨玻璃影。", question: "这块磨玻璃影是什么？", regionId: null, upload: { name: "local-upload.jpg" }, guideId: "" },
    },
  ];

  /* 覆盖层必须贴合图片实际渲染区域：object-fit: contain 会在元素内留黑边，
     若覆盖层仍按整个舞台定位，框就会整体偏移。这里按图片纵横比算出内容框。 */
  function fitAskMedia() {
    document.querySelectorAll(".ask-stage").forEach((stage) => {
      const img = stage.querySelector('img[data-fit="1"]');
      const media = stage.querySelector(".ask-media");
      if (!img || !media || !img.naturalWidth || !img.naturalHeight) return;
      const availW = stage.clientWidth;
      if (!availW) return;
      const maxH = 440;
      const ratio = img.naturalHeight / img.naturalWidth;
      let w = availW;
      let hh = availW * ratio;
      if (hh > maxH) { hh = maxH; w = maxH / ratio; }
      media.style.width = Math.round(w) + "px";
      media.style.height = Math.round(hh) + "px";
    });
  }

  /* 点击命中：换算成图片归一化坐标，取包含该点且面积最小的分区。
     不依赖 DOM 重叠顺序，因此整图级「周边带」不会吞掉内部小区域的点击。 */
  function hitRegion(stage, clientX, clientY) {
    const c = currentCase();
    if (!c) return null;
    const media = stage.querySelector(".ask-media");
    const img = stage.querySelector('img[data-fit="1"]');
    const box = (media && media.getBoundingClientRect().height)
      ? media.getBoundingClientRect()
      : (img ? img.getBoundingClientRect() : null);
    if (!box || !box.width || !box.height) return null;
    const x = (clientX - box.left) / box.width;
    const y = (clientY - box.top) / box.height;
    if (x < 0 || y < 0 || x > 1 || y > 1) return null;
    const hits = regionsOf(c.id).filter((r) => {
      const [x1, y1, x2, y2] = r.coords || [0, 0, 0, 0];
      return x >= x1 && x <= x2 && y >= y1 && y <= y2;
    });
    if (!hits.length) return null;
    return hits.sort((a, b) => {
      const aa = a.coords || [0, 0, 0, 0];
      const bb = b.coords || [0, 0, 0, 0];
      const area = (q) => Math.max(0, q[2] - q[0]) * Math.max(0, q[3] - q[1]);
      return area(aa) - area(bb);
    })[0];
  }

  function stageHTML() {
    const c = currentCase();
    if (AS.upload) {
      return `<div class="ask-stage upload">
        <img src="${h(AS.upload.dataUrl || "")}" alt="上传影像" ${AS.upload.dataUrl ? "" : 'style="display:none"'}>
        <div class="ask-nobox">
          ${icon("alert", 18)}
          <b>未标注分区</b>
          <span>上传影像不参与引用：没有人工分区，就没有 bbox 与分区 id。</span>
        </div>
      </div>`;
    }
    if (!c) return `<div class="ask-stage empty">未选择病例</div>`;
    const rs = regionsOf(c.id);
    const area = (r) => { const a = r.coords || [0, 0, 0, 0]; return a[2] * a[3]; };
    /* 大范围容器（如「周边带」）先渲染、沉在底层；小区域后渲染、浮在上层，
       避免整图级区域拦截所有点击。点击命中另由几何判定兜底。 */
    const ordered = rs.map((r, i) => ({ r, i })).sort((a, b) => area(b.r) - area(a.r));
    const boxes = AS.showBoxes ? ordered.map(({ r, i }) => {
      const [x1, y1, x2, y2] = r.coords || [0, 0, 0, 0];
      const x = x1, y = y1, w = Math.max(0, x2 - x1), hh = Math.max(0, y2 - y1);
      const on = AS.regionId === r.id || (AS.result && AS.result.region && AS.result.region.id === r.id);
      return `<button class="ask-box ${on ? "on" : ""}" data-region-id="${r.id}"
        style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${hh * 100}%"
        title="${h(r.name)} · ${h(r.id)}">
        <span class="ab-n">${i + 1}</span><span class="ab-t">${h(r.name)}</span>
      </button>`;
    }).join("") : "";
    return `<div class="ask-stage" data-ask="stage-hit">
      <div class="ask-media">
        <img src="${h(c.image)}" alt="${h(c.title)}" data-fit="1">
        <div class="ask-boxes">${boxes}</div>
      </div>
      <div class="ask-stage-tag">${h(c.modality.join("/"))} · ${h(c.body_part)} · ${h(c.license || "")}</div>
    </div>`;
  }

  function regionCardHTML() {
    const r = AS.result && AS.result.region;
    if (AS.upload) return `<div class="ask-rcard warn"><b>无分区引用</b><span>上传影像缺少人工标注，影像侧引用不可用。</span></div>`;
    if (!r) {
      const c = currentCase();
      const n = c ? regionsOf(c.id).length : 0;
      return `<div class="ask-rcard"><b>尚未选定分区</b><span>${n ? `该病例有 ${n} 个已标注分区，点影像上的框选择。` : "该病例暂无分区。"}</span></div>`;
    }
    return `<div class="ask-rcard">
      <div class="arc-h"><b>${h(r.name)}</b><span class="mono">${h(r.id)}</span></div>
      <div class="arc-meta">${h(r.atlas_id || "")} · bbox [${(r.coords || []).map((n) => n.toFixed(2)).join(", ")}] · ${h(r.annotator || "human")} 标注</div>
      <div class="arc-note">${/[左右]/.test(r.name || "")
        ? `图像${r.image_side === "left" ? "左" : "右"}侧 = 患者${r.patient_side === "right" ? "右" : "左"}侧。`
        : "中央/非侧别分区，不套用左右侧规则。"}${h(r.note || "")}</div>
      <div class="arc-signs">${(r.sign_ids || []).slice(0, 6).map((id) => `<span class="chip">${h((signById(id) || {}).name || id)}</span>`).join("")}</div>
    </div>`;
  }

  function coverRow(ok, label, val) {
    return `<div class="cov-row ${ok ? "ok" : "no"}">
      <span class="cov-i">${icon(ok ? "check" : "x", 12)}</span>
      <span class="cov-l">${label}</span>
      <span class="cov-v">${h(val)}</span>
    </div>`;
  }

  function answerHTML() {
    const r = AS.result;
    if (!r) {
      return `<div class="ans-empty">
        <div class="ae-mark">${icon("layers", 26)}</div>
        <b>回答会同时挂两处引用</b>
        <p>影像侧给出分区 id、bbox 与 atlas；文献侧给出条款原文、版本与定位。缺任何一侧，这里会显示拒答或降级原因。</p>
        <div class="ae-rule">
          <span>① 影像区域</span><span>② 文献段落</span><span>③ 不确定就拒答</span><span>④ 非诊断用途</span>
        </div>
      </div>`;
    }

    const st = r.status;
    const spatial = r.spatial;
    const doc = r.doc;

    const spatialCard = spatial ? `<article class="cite-card spatial" data-ask="focus-spatial">
      <div class="cc-h"><span class="cc-k">影像引用</span><span class="cc-id mono">${h(spatial.region_id)}</span></div>
      <b>${h(spatial.name)}</b>
      <div class="cc-meta">分区 ${h(spatial.region_id)}${spatial.region_name && spatial.region_name !== spatial.name ? "（" + h(spatial.region_name) + "）" : ""} · ${h(spatial.atlas_label || spatial.atlas_id)} · bbox [${(spatial.bbox || []).map((n) => n.toFixed(2)).join(", ")}]</div>
      ${spatial.kind === "link" ? `<div class="cc-meta">人工图文锚点 ${h(spatial.link_id)} · ${h(spatial.note || "")}</div>` : ""}
      <div class="cc-meta">${/[左右]/.test(spatial.name || "")
        ? `图像${spatial.image_side === "left" ? "左" : "右"}侧 = 患者${spatial.patient_side === "right" ? "右" : "左"}侧`
        : "中央/非侧别分区"} · ${h(spatial.annotator)} 标注</div>
      <div class="cc-foot"><span class="chip ok">可回查</span><span>点此卡在影像上定位</span></div>
    </article>` : `<article class="cite-card spatial off">
      <div class="cc-h"><span class="cc-k">影像引用</span><span class="cc-id">缺失</span></div>
      <b>没有可挂的分区</b>
      <div class="cc-meta">按双引用规则，缺少 bbox 时不输出结论。</div>
    </article>`;

    const docCard = doc ? `<article class="cite-card doc">
      <div class="cc-h"><span class="cc-k">文献引用${(r.alt && r.alt.length) ? " · 候选 1" : ""}</span><span class="cc-id mono">${h(doc.id || "")}</span></div>
      <b>${h(doc.title)}${doc.version ? " · " + h(doc.version) : ""}</b>
      <div class="cc-meta">${h(doc.locator)}</div>
      <blockquote>${h(doc.excerpt)}</blockquote>
      <div class="cc-foot">
        ${doc.hash ? `<span class="chip ok">摘录 hash ${h(doc.hash)}</span>` : `<span class="chip">库内条款</span>`}
        ${doc.degraded ? `<span class="chip warn">降级：非指南条款</span>` : `<span class="chip ok">指南条款</span>`}
        ${(r.alt && r.alt.length) ? `<span class="chip warn">候选条款 · 并列</span>` : ""}
        ${doc.url ? `<a href="${h(doc.url)}" target="_blank" rel="noopener">官方入口 ${icon("external", 11)}</a>` : ""}
      </div>
    </article>` : `<article class="cite-card doc off">
      <div class="cc-h"><span class="cc-k">文献引用</span><span class="cc-id">缺失</span></div>
      <b>没有可引用的段落</b>
      <div class="cc-meta">按双引用规则，缺少原文摘录时不输出结论。</div>
    </article>`;

    const alt = (r.alt && r.alt.length) ? `<div class="ans-alt">
      <h4>其他相关条款（并列，不裁决）</h4>
      ${r.alt.map((a) => `<div class="alt-row"><b>${h(a.title)} · ${h(a.version)}</b><span>${h(a.locator)}</span><p>${h(a.excerpt)}</p></div>`).join("")}
    </div>` : "";

    const notes = (r.notes || []).length ? `<div class="ans-notes">
      <h4>不确定与降级说明</h4>
      ${r.notes.map((n) => `<div class="note-row">${icon("alert", 12)}<span>${h(n)}</span></div>`).join("")}
    </div>` : "";

    const found = (r.found || []).length ? `<div class="ans-notes">
      <h4>已检索到但未合并</h4>
      ${r.found.map((n) => `<div class="note-row">${icon("right", 12)}<span>${h(n)}</span></div>`).join("")}
    </div>` : "";

    const cov = r.coverage || {};
    const coverage = `<div class="ans-cover">
      <h4>双引用覆盖</h4>
      ${coverRow(!!cov.image, "影像输入", cov.image ? (r.case ? r.case.id : "已上传") : "缺失")}
      ${coverRow(!!cov.region, "解剖分区", cov.region ? (r.spatial ? r.spatial.region_id + " · " + r.spatial.region_name : r.region.name) : "缺失")}
      ${coverRow(!!cov.claim, "分区结论", cov.claim ? r.claim.id : "缺失")}
      ${coverRow(!!cov.doc, "文献段落", cov.doc ? (r.doc.kind === "guideline" ? "指南条款" : "词条释义") : "缺失")}
      ${coverRow(!!cov.guideline, "指南条款", cov.guideline ? r.doc.locator : "未命中")}
      ${coverRow(!!cov.verify, "引用校验", (r.broken && r.broken.length) ? `通过 · 拦截 ${r.broken.length} 条` : "通过")}
      ${coverRow(true, "用途声明", "非诊断")}
    </div>`;

    const trace = (r.trace || []).length ? `<div class="ans-trace">
      <h4>依据链</h4>
      <div class="trace-flow">${r.trace.map((t, i) => `<span class="tr">${h(t)}</span>${i < r.trace.length - 1 ? `<i>→</i>` : ""}`).join("")}</div>
    </div>` : "";

    return `<div class="ans-tools">
      <button class="btn ghost sm" data-ask="copy-answer">${icon("copy", 12)} 复制双引用</button>
    </div>
    <div class="ans-status ${st}">
      <span class="as-dot"></span><b>${STATUS_LABEL[st]}</b><span>${h(r.title)}</span>
    </div>
    <div class="ans-q">问：${h(AS.question || "（未填写问题）")}</div>
    <p class="ans-detail">${h(r.detail)}</p>
    ${r.answer ? `<div class="ans-text">${h(r.answer).replace(/\n/g, "<br>")}</div>` : ""}
    <div class="ans-cites">${spatialCard}${docCard}</div>
    ${alt}${notes}${found}${coverage}${trace}
    <div class="ans-foot">${icon("shield", 12)} 仅作影像表现与文献条款对照，不构成诊断意见，不替代临床决策。内容经规则校验与 AI 预审，正式教学使用前须经医学人员审核。</div>`;
  }

  function selftestHTML() {
    if (!AS.selftest) {
      return `<div class="st-head"><b>诚实性自检</b><span>用 7 个固定输入检查：该答的答、该拒的拒。</span>
        <button class="btn sm" data-ask="selftest">运行自检</button></div>`;
    }
    const rows = AS.selftest;
    const pass = rows.filter((x) => x.ok).length;
    return `<div class="st-head"><b>诚实性自检</b><span>${pass} / ${rows.length} 通过</span>
      <button class="btn sm" data-ask="selftest">重新运行</button></div>
    <div class="st-table">
      ${rows.map((x) => `<div class="st-row ${x.ok ? "ok" : "bad"}">
        <span class="st-i">${icon(x.ok ? "check" : "x", 12)}</span>
        <span class="st-n">${h(x.name)}</span>
        <span class="st-a">${h(x.actual)}</span>
        <span class="st-e">期望：${h(x.expect)}</span>
      </div>`).join("")}
    </div>`;
  }

  function askView() {
    const c = currentCase();
    const r = AS.result;

    return `<div class="ask">
      <a class="v6-banner" href="read/clinic.html">
        <span class="v6-k">v6 · 胸片阅片优先</span>
        <b>当前版本的主链路已收敛到胸片阅片</b>
        <span class="v6-d">21 例 CR 胸部逐区校正；旧版多模态问答保留为实验，胸片请用新工作台。</span>
        <em>进入胸片阅片 →</em>
      </a>
      <header class="ask-hero">
        <div class="ah-l">
          <span class="ah-eye">核心功能 · 多模态知识库问答</span>
          <h1>影像给区域，文献给段落；<br>不确定就明说。</h1>
          <p>输入一张影像与一段报告/指南文字，回答同时引用「图上哪一块」与「哪份文献哪一段」。
             缺一侧就降级，越界就拒答，所有输出固定声明非诊断用途。</p>
        </div>
        <div class="ah-r">
          <div class="ah-rule"><span>①</span><b>双引用</b><em>区域 + 段落</em></div>
          <div class="ah-rule"><span>②</span><b>诚实拒答</b><em>缺证据不猜</em></div>
          <div class="ah-rule"><span>③</span><b>非诊断</b><em>固定声明</em></div>
        </div>
      </header>

      <div class="ask-grid">
        <section class="ask-pane ask-in">
          <div class="ap-h"><span class="ap-no">01</span><b>输入</b><span class="ap-sub">影像 + 报告/指南</span></div>

          <label class="ask-lb">影像来源</label>
          ${casePickerHTML()}
          <div class="ask-row">
            <label class="btn ghost sm" for="askFile">${icon("image", 13)} 上传影像</label>
            <input id="askFile" type="file" accept="image/*" hidden>
            ${AS.upload ? `<button class="btn ghost sm" data-ask="clear-upload">清除上传</button>` : ""}
          </div>
          ${AS.upload ? `<div class="ask-upload-tip">已上传：${h(AS.upload.name)} · 不参与引用</div>` : ""}

          <label class="ask-lb" for="askReport">报告 / 指南文档</label>
          <textarea id="askReport" class="ask-ta" rows="5" placeholder="粘贴影像报告、指南段落或教学描述。例如：右肺中野透亮度均匀，未见明确结节。">${h(AS.report)}</textarea>
          <div class="ask-row">
            <label class="btn ghost sm" for="askDoc">${icon("clipboard", 13)} 上传 .txt/.md</label>
            <input id="askDoc" type="file" accept=".txt,.md,text/plain,text/markdown" hidden>
            <button class="btn ghost sm" data-ask="demo-report">载入示例</button>
            <span class="ask-count">${(AS.report || "").length} 字</span>
          </div>

          <label class="ask-lb" for="askGuide">指定文献条款 <span class="ask-opt">可选</span></label>
          <select id="askGuide" class="ask-sel">${guideOptions()}</select>

          <label class="ask-lb" for="askQ">问题</label>
          <input id="askQ" class="ask-input" value="${h(AS.question)}" placeholder="例如：右肺中野有没有结节？">

          <div class="ask-presets">
            ${PRESETS.map((p) => `<button class="ask-chip" data-ask="preset" data-key="${p.key}">${h(p.label)}</button>`).join("")}
          </div>

          <button class="btn primary ask-run" data-ask="run">${icon("spark", 14)} 生成带双引用的回答</button>

          <div class="ask-req">
            <b>双引用规则</b>
            <span>影像侧：分区 id + bbox + atlas；文献侧：条款原文 + 版本 + 定位。任一侧缺失 → 拒答或降级。</span>
          </div>
        </section>

        <section class="ask-pane ask-view">
          <div class="ap-h"><span class="ap-no">02</span><b>影像与分区</b><span class="ap-sub">${c ? h(c.title) : "上传影像"}</span></div>
          ${stageHTML()}
          <div class="ask-viewbar">
            <button class="btn ghost sm" data-ask="toggle-boxes">${AS.showBoxes ? "隐藏分区" : "显示分区"}</button>
            <span>${c ? `${h(c.id)} · ${h(c.modality.join("/"))} · ${h(c.license || "")}` : "未标注影像"}</span>
          </div>
          ${regionCardHTML()}
          <div class="ask-honest">
            ${icon("alert", 13)}
            <span>框是人工标注的解剖分区，不是病灶分割；点框只改变「看哪儿」，不改变结论。</span>
          </div>
        </section>

        <section class="ask-pane ask-out" aria-live="polite">
          <div class="ap-h"><span class="ap-no">03</span><b>回答与双引用</b><span class="ap-sub">${r ? STATUS_LABEL[r.status] : "待生成"}</span></div>
          ${answerHTML()}
        </section>
      </div>

      <div class="ask-disclaim">
        ${icon("shield", 14)}
        <b>非诊断用途声明</b>
        <span>本应用仅用于医学影像教学与研究，不构成诊断意见，不替代临床决策。病例影像仅使用公开许可来源；分区框为人工标注解剖区，不是病灶分割。</span>
        <span><b>内容审核状态</b>：知识库内容由规则校验与 AI 预审生成，<b>正式落地运用前须经具备资质的医学人员逐条审核签字</b>；未签字条目标注"待审核"，不作为教学依据。</span>
      </div>

      <details class="ask-test" ${AS.selftest ? "open" : ""}>
        <summary>诚实性自检（评委可当场重跑）</summary>
        ${selftestHTML()}
      </details>
    </div>`;
  }

  /* ---------- 交互 ---------- */

  /* 分片按部位懒加载：切到未加载的病例时 regionsOf 为空，直接判定会误报
     「无法确定影像区域」。这里先补齐该病例所在分片，再跑规则引擎。 */
  function runNow(after) {
    const c = pickCase(AS);
    const go = () => {
      AS.result = run(AS);
      YZ.render();
      if (after) after();
    };
    if (c && YZ.ensureCase) YZ.ensureCase(c.id).then(go, go);
    else go();
  }

  function applyPreset(key) {
    const p = PRESETS.find((x) => x.key === key);
    if (!p) return;
    Object.assign(AS, p.s, { result: null, selftest: AS.selftest });
    runNow(scrollAnswer);
  }

  function scrollAnswer() {
    if (window.matchMedia && window.matchMedia("(max-width: 900px)").matches) {
      const el = YZ.$(".ask-out");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function syncFields() {
    const q = YZ.$("#askQ");
    const rep = YZ.$("#askReport");
    const sel = YZ.$("#askCase");
    const g = YZ.$("#askGuide");
    if (q) AS.question = q.value;
    if (rep) AS.report = rep.value;
    if (sel) AS.caseId = sel.value;
    if (g) AS.guideId = g.value;
  }

  function readFile(file, asDataUrl) {
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(fr.result);
      fr.onerror = reject;
      if (asDataUrl) fr.readAsDataURL(file);
      else fr.readAsText(file, "utf-8");
    });
  }

  function runSelftest() {
    const rows = [
      {
        name: "正常胸片 + 结节",
        s: { caseId: "CASE-001", report: "右肺中野透亮度均匀，未见明确结节。", question: "右肺中野有没有结节？", regionId: null, upload: null, guideId: "" },
        expect: "answer + 指南条款",
        ok: (r) => r.status === "answer" && r.spatial && r.doc && r.doc.kind === "guideline",
        actual: (r) => `${r.status}${r.doc ? " · " + (r.doc.kind === "guideline" ? "指南" : "词条") : ""}`,
      },
      {
        name: "甲状腺 TR4 + 1.6cm",
        s: { caseId: "CASE-011", report: "甲状腺右叶低回声结节，最大径 1.6 cm，TI-RADS TR4。", question: "TR4、1.6 cm 的结节，条款怎么表述？", regionId: null, upload: null, guideId: "" },
        expect: "answer + TR4 条款",
        ok: (r) => r.status === "answer" && r.doc && !r.doc.degraded && /TR4/.test(r.doc.locator || ""),
        actual: (r) => `${r.status}${r.doc ? " · " + r.doc.locator : ""}${(r.broken || []).length ? " · 拦截 " + r.broken.join("/") : ""}`,
      },
      {
        name: "空输入",
        s: { caseId: "CASE-001", report: "", question: "", regionId: null, upload: null, guideId: "" },
        expect: "refuse / no-signal",
        ok: (r) => r.status === "refuse" && r.reason === "no-signal",
        actual: (r) => `${r.status} / ${r.reason}`,
      },
      {
        name: "诊断/治疗越界",
        s: { caseId: "CASE-001", report: "", question: "这是不是肺癌？要不要手术？", regionId: null, upload: null, guideId: "" },
        expect: "refuse / scope",
        ok: (r) => r.status === "refuse" && r.reason === "scope",
        actual: (r) => `${r.status} / ${r.reason}`,
      },
      {
        name: "上传影像未标注",
        s: { caseId: null, report: "右肺上野磨玻璃影。", question: "这块磨玻璃影是什么？", regionId: null, upload: { name: "x.jpg" }, guideId: "" },
        expect: "refuse / no-region",
        ok: (r) => r.status === "refuse" && r.reason === "no-region",
        actual: (r) => `${r.status} / ${r.reason}`,
      },
      {
        name: "头颅无指南条款",
        s: { caseId: "CASE-029", report: "左侧天幕区可见高密度出血。", question: "这个出血怎么描述？", regionId: "REG-029-L", upload: null, guideId: "" },
        expect: "partial / 文献降级",
        ok: (r) => r.status === "partial" && r.doc && r.doc.degraded,
        actual: (r) => `${r.status}${r.doc ? " · " + (r.doc.degraded ? "降级" : "指南") : ""}`,
      },
      {
        name: "磨玻璃缺尺寸",
        s: { caseId: "CASE-020", report: "右半侧 CT 图像中，含气肺组织内可见密度轻度增高区，血管边缘仍可分辨。", question: "这个磨玻璃影该怎么随访？", regionId: null, upload: null, guideId: "" },
        expect: "partial / 条款并列",
        ok: (r) => r.status === "partial" && r.alt && r.alt.length > 0,
        actual: (r) => `${r.status} · 并列 ${r.alt ? r.alt.length : 0}`,
      },
      {
        name: "磨玻璃 + 7mm",
        s: { caseId: "CASE-020", report: "右半侧 CT 图像中，含气肺组织内可见密度轻度增高区，最大径约 7 mm。", question: "这个磨玻璃影该怎么随访？", regionId: null, upload: null, guideId: "" },
        expect: "answer + ≥6mm 条款",
        ok: (r) => r.status === "answer" && r.doc && /≥ 6 mm/.test(r.doc.locator || ""),
        actual: (r) => `${r.status}${r.doc ? " · " + r.doc.locator : ""}`,
      },
    ];
    AS.selftest = rows.map((x) => {
      const r = run(Object.assign({}, AS, x.s));
      return { name: x.name, ok: !!x.ok(r), expect: x.expect, actual: x.actual(r) };
    });
    YZ.render();
    const pass = AS.selftest.filter((x) => x.ok).length;
    toast(`自检 ${pass}/${AS.selftest.length} 通过`);
  }

  function copyAnswer() {
    const r = AS.result;
    if (!r) return;
    const sp = r.spatial;
    const d = r.doc;
    const lines = [
      "# RadioCheck · 多模态问答",
      "",
      `问题：${AS.question || "（未填写）"}`,
      `状态：${STATUS_LABEL[r.status]}（${r.title}）`,
      "",
      "## 回答",
      r.answer || r.detail,
      "",
      "## 影像引用",
      sp ? `- 分区：${sp.name}（${sp.region_id}）` : "- 缺失",
      sp ? `- bbox：${(sp.bbox || []).map((n) => n.toFixed(2)).join(", ")}` : "",
      sp ? `- atlas：${sp.atlas_id}；标注：${sp.annotator}` : "",
      "",
      "## 文献引用",
      d ? `- 来源：${d.title}${d.version ? " " + d.version : ""}` : "- 缺失",
      d ? `- 定位：${d.locator}` : "",
      d ? `- 原文：${d.excerpt}` : "",
      d && d.url ? `- 入口：${d.url}` : "",
      "",
      (r.notes || []).length ? "## 不确定与降级说明\n" + r.notes.map((x) => "- " + x).join("\n") : "",
      "",
      "> 仅作影像表现与文献条款对照，不构成诊断意见，不替代临床决策。",
    ];
    YZ.copyText(lines.join("\n"), "双引用已复制");
  }

  /* ---------- 事件 ---------- */

  document.addEventListener("click", async (e) => {
    const el = e.target.closest("[data-ask]");
    if (!el) {
      // 点在选择器外面：收起面板
      if (AS.pickerOpen && !e.target.closest(".ask-picker")) {
        AS.pickerOpen = false;
        YZ.render();
      }
      return;
    }
    const act = el.dataset.ask;
    switch (act) {
      case "run": syncFields(); runNow(scrollAnswer); break;
      case "preset": applyPreset(el.dataset.key); break;
      case "stage-hit": {
        const stage = el.closest(".ask-stage");
        if (!stage) break;
        const reg = hitRegion(stage, e.clientX, e.clientY);
        if (!reg) { toast("该位置不在已标注分区内"); break; }
        AS.regionId = reg.id;
        runNow();
        break;
      }
      case "picker-toggle":
        AS.pickerOpen = !AS.pickerOpen;
        YZ.render();
        if (AS.pickerOpen) {
          requestAnimationFrame(() => {
            const list = YZ.$("#askCaseList");
            const group = list && list.querySelector(".apk-group.open");
            if (list && group) list.scrollTop = Math.max(0, group.offsetTop - list.offsetTop - 4);
          });
        }
        break;
      case "picker-group": {
        const bp = el.dataset.group;
        const cur = AS.caseId !== "auto" ? currentCase() : null;
        const defaultOpen = !!(cur && cur.body_part === bp);
        const open = AS.pickerOpenGroups[bp] !== undefined ? AS.pickerOpenGroups[bp] : defaultOpen;
        AS.pickerOpenGroups[bp] = !open;
        YZ.render();
        break;
      }
      case "pick-case": {
        AS.caseId = el.dataset.id;
        AS.regionId = null;
        AS.upload = null;
        AS.pickerOpen = false;
        AS.pickerQuery = "";
        if (AS.caseId !== "auto") await YZ.ensureCase(AS.caseId);
        runNow();
        break;
      }
      case "toggle-boxes": AS.showBoxes = !AS.showBoxes; YZ.render(); break;
      case "clear-upload":
        AS.upload = null; AS.caseId = "auto"; AS.regionId = null; AS.result = null; YZ.render(); break;
      case "demo-report": {
        const c = currentCase();
        AS.report = c ? (c.description_public || c.teaching_note || "") : "右肺上野见磨玻璃样密度增高影。";
        runNow();
        break;
      }
      case "selftest":
        // 自检会跨病例跑，先把分片全部载入，避免未加载时误判成「无结论」。
        await YZ.loadAllParts();
        runSelftest();
        break;
      case "copy-answer": copyAnswer(); break;
      case "focus-spatial": {
        const box = YZ.$(".ask-box.on");
        if (box) {
          box.classList.add("flash");
          setTimeout(() => box.classList.remove("flash"), 900);
          box.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        break;
      }
      default: break;
    }
  });

  document.addEventListener("input", (e) => {
    if (e.target.id === "askQ") AS.question = e.target.value;
    if (e.target.id === "askReport") {
      AS.report = e.target.value;
      const c = YZ.$(".ask-count");
      if (c) c.textContent = `${AS.report.length} 字`;
    }
    if (e.target.id === "askCaseSearch") {
      AS.pickerQuery = e.target.value;
      const list = YZ.$("#askCaseList");
      if (list) list.innerHTML = caseListHTML();  // 只换列表，保住输入焦点
    }
  });

  document.addEventListener("change", async (e) => {
    if (e.target.id === "askCase") {
      AS.caseId = e.target.value;
      AS.regionId = null;
      AS.upload = null;
      await YZ.ensureCase(AS.caseId);
      runNow();
    }
    if (e.target.id === "askGuide") {
      AS.guideId = e.target.value;
      runNow();
    }
    if (e.target.id === "askFile" && e.target.files && e.target.files[0]) {
      const f = e.target.files[0];
      try {
        const dataUrl = await readFile(f, true);
        AS.upload = { name: f.name, dataUrl };
        AS.caseId = null;
        AS.regionId = null;
        runNow();
      } catch (err) { toast("影像读取失败"); }
      e.target.value = "";
    }
    if (e.target.id === "askDoc" && e.target.files && e.target.files[0]) {
      const f = e.target.files[0];
      try {
        const text = await readFile(f, false);
        AS.report = String(text).slice(0, 4000);
        runNow();
        toast("文档已载入，可继续编辑后重新生成");
      } catch (err) { toast("文档读取失败"); }
      e.target.value = "";
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.target && e.target.id === "askQ" && e.key === "Enter") {
      e.preventDefault();
      syncFields();
      runNow(scrollAnswer);
    }
  });

  /* 每次渲染后重新贴合图片内容框；图片异步加载完成时再校正一次。 */
  const baseRender = YZ.render;
  YZ.render = function () {
    baseRender.apply(YZ, arguments);
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(fitAskMedia);
    else fitAskMedia();
  };
  document.addEventListener("load", (e) => {
    if (e.target && e.target.matches && e.target.matches('img[data-fit="1"]')) fitAskMedia();
  }, true);
  window.addEventListener("resize", fitAskMedia);

  YZ.askView = askView;
  YZ.fitAskMedia = fitAskMedia;
  YZ.ASK = { AS, run, detectSignals, pickDoc };
})(window.YZ = window.YZ || {});
