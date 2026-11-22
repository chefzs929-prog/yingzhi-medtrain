/* RadioCheck · 影像临床思维平台
 * 核心：数据、状态、路由、外壳、通用组件
 * 单引擎多版本：角色与设备只改变外壳与可见模块，不复制业务逻辑。
 */
(function (YZ) {
  "use strict";

  const DB = window.__KB__;
  DB.regionsByCase = DB.regionsByCase || {};
  DB.claimsByCase = DB.claimsByCase || {};
  const app = document.getElementById("app");
  if (!DB) {
    app.innerHTML = '<div class="boot"><div class="boot-mark">!</div><p>知识数据未载入，请先运行 build_data.py。</p></div>';
    return;
  }

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (n, d) => (d ? Math.round((n / d) * 100) : 0);
  const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
  const uniq = (arr) => Array.from(new Set(arr));
  const today = () => new Date().toISOString().slice(0, 10);
  const byId = (arr) => new Map(arr.map((x) => [x.id, x]));
  const modsOf = (x) => (x && x.modality) || [];

  const SIGN = byId(DB.signs);
  const CASE = byId(DB.cases);
  const GUIDE = byId(DB.guidelines);
  const GROUP = byId(DB.groups);
  const DRILL = byId(DB.drills);
  const REGION_LABEL = Object.fromEntries(DB.meta.regions.map((r) => [r.id, r.name]));

  const ROLES = {
    student: {
      key: "student", name: "学生", full: "医学生 / 规培生", mark: "学",
      desc: "从术语到病例，按四链条建立可追溯的影像思维",
      nav: [
        { id: "ask", label: "问 · 多模态问答", short: "问答", icon: "spark" },
        { id: "home", label: "学习首页", short: "首页", icon: "home" },
        { id: "learn", label: "学 · 基础知识", short: "学", icon: "book" },
        { id: "transfer", label: "迁 · 临床迁移", short: "迁", icon: "transfer" },
        { id: "drill", label: "练 · 病例演练", short: "练", icon: "target" },
        { id: "apply", label: "用 · 实习任务", short: "用", icon: "briefcase" },
        { id: "me", label: "我的记录", icon: "user" },
      ],
      tabs: ["ask", "home", "learn", "drill", "apply"],
    },
    teacher: {
      key: "teacher", name: "教师", full: "课程教师 / 带教老师", mark: "教",
      desc: "用同一套病例与错题数据备课、布置、讲评",
      nav: [
        { id: "ask", label: "问 · 多模态问答", short: "问答", icon: "spark" },
        { id: "home", label: "教学首页", short: "首页", icon: "home" },
        { id: "learn", label: "学 · 知识备课", short: "备课", icon: "book" },
        { id: "transfer", label: "迁 · 迁移设计", short: "迁移", icon: "transfer" },
        { id: "drill", label: "练 · 组卷演练", short: "组卷", icon: "target" },
        { id: "apply", label: "教 · 班级管理", short: "班级", icon: "users" },
        { id: "me", label: "我的记录", icon: "user" },
      ],
      tabs: ["ask", "home", "learn", "drill", "apply"],
    },
    doctor: {
      key: "doctor", name: "医生", full: "影像科医生 / 临床带教", mark: "医",
      desc: "把可追溯的影像证据带进读片、交班与带教",
      nav: [
        { id: "ask", label: "问 · 多模态问答", short: "问答", icon: "spark" },
        { id: "home", label: "临床首页", short: "首页", icon: "home" },
        { id: "learn", label: "学 · 知识速查", short: "速查", icon: "book" },
        { id: "transfer", label: "迁 · 跨场景鉴别", short: "鉴别", icon: "transfer" },
        { id: "drill", label: "练 · 读片演练", short: "演练", icon: "target" },
        { id: "apply", label: "用 · 病例工作台", short: "工作台", icon: "stethoscope" },
        { id: "me", label: "我的记录", icon: "user" },
      ],
      tabs: ["ask", "home", "learn", "apply", "drill"],
    },
  };

  /* 四链条：同一组能力，在三种角色下换任务说法与完成口径 */
  const CHAINS = {
    student: [
      { id: "learn", no: "01", title: "基础知识问答", desc: "征象是什么、怎么看、容易错在哪；每条解释都能回到出处。" },
      { id: "transfer", no: "02", title: "临床知识迁移", desc: "换模态、换部位、换病种，同一征象的判断会不会跟着变。" },
      { id: "drill", no: "03", title: "真实病例演练", desc: "在公开病例上完成定位、描述、征象与依据四步，按步计分。" },
      { id: "apply", no: "04", title: "真实实习场景", desc: "把练习记录变成实习任务、能力画像与可导出的学习报告。" },
    ],
    teacher: [
      { id: "learn", no: "01", title: "基础知识问答", desc: "按部位、模态、条款条件备课；每条解释都能回到出处。" },
      { id: "transfer", no: "02", title: "临床知识迁移", desc: "设计换模态、换部位、换病种的对照任务，把易错点变成课堂问题。" },
      { id: "drill", no: "03", title: "真实病例演练", desc: "从题库按部位组卷、预览、投屏讲评；学生记录回流班级。" },
      { id: "apply", no: "04", title: "真实教学场景", desc: "班级概览、作业编排、错题分析与课堂投屏共用一套数据。" },
    ],
    doctor: [
      { id: "learn", no: "01", title: "基础知识问答", desc: "读片前 30 秒速查征象定义、易错点与条款条件。" },
      { id: "transfer", no: "02", title: "临床知识迁移", desc: "跨模态、跨部位对照，避免把“看起来像”当成同一条证据。" },
      { id: "drill", no: "03", title: "真实病例演练", desc: "在公开病例上做定位—描述—征象—依据四步读片演练。" },
      { id: "apply", no: "04", title: "真实临床场景", desc: "病例工作台、双引用核验、引用审计与交班摘要。" },
    ],
  };

  const ICONS = {
    home: '<path d="M3 10.6 12 3l9 7.6V21a1 1 0 0 1-1 1h-5.2v-7.1H9.2V22H4a1 1 0 0 1-1-1z"/>',
    book: '<path d="M4 19.4A2.4 2.4 0 0 1 6.4 17H20"/><path d="M6.4 2H20v20H6.4A2.4 2.4 0 0 1 4 19.6V4.4A2.4 2.4 0 0 1 6.4 2z"/>',
    transfer: '<path d="M4 7h13"/><path d="m14 3 4 4-4 4"/><path d="M20 17H7"/><path d="m10 13-4 4 4 4"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/>',
    user: '<circle cx="12" cy="8" r="3.4"/><path d="M5 21a7 7 0 0 1 14 0"/>',
    users: '<circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0"/><path d="M16 5.5a3 3 0 0 1 0 5.6"/><path d="M18 14.5a6 6 0 0 1 3 5.5"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.4-3.4"/>',
    right: '<path d="m9 5 7 7-7 7"/>',
    left: '<path d="m15 5-7 7 7 7"/>',
    check: '<path d="m4 12.5 5 5L20 6.5"/>',
    x: '<path d="m6 6 12 12M18 6 6 18"/>',
    alert: '<path d="M12 3 2.8 20h18.4z"/><path d="M12 9v5"/><path d="M12 17.2v.1"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.4l2-2a5 5 0 0 0-7-7l-1.2 1.2"/><path d="M14 11a5 5 0 0 0-7.5-.4l-2 2a5 5 0 0 0 7 7l1.2-1.2"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9" r="1.5"/><path d="m21 16-5-5L5 20"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
    stethoscope: '<path d="M6 3v5a4 4 0 0 0 8 0V3"/><path d="M10 12v3a5 5 0 0 0 10 0v-2"/><circle cx="20" cy="10" r="2"/>',
    graduation: '<path d="m2 9 10-5 10 5-10 5z"/><path d="M6 11.5V16c0 1.7 2.7 3 6 3s6-1.3 6-3v-4.5"/><path d="M22 9v6"/>',
    spark: '<path d="m12 3 1.7 4.8L18.5 9.5l-4.8 1.7L12 16l-1.7-4.8L5.5 9.5l4.8-1.7z"/><path d="M19 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
    download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M4 20h16"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
    filter: '<path d="M4 5h16l-6.5 8v5l-3 2v-7z"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    shield: '<path d="m12 3 8 3v5c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6z"/><path d="m9 12 2 2 4-4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    monitor: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
    phone: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18.5h2"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.4"/><rect x="14" y="3" width="7" height="7" rx="1.4"/><rect x="3" y="14" width="7" height="7" rx="1.4"/><rect x="14" y="14" width="7" height="7" rx="1.4"/>',
    activity: '<path d="M3 12h4l2.5-7 5 14 2.5-7H21"/>',
    clipboard: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="M9 9h6M9 13h6M9 17h4"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    play: '<path d="m8 5 11 7-11 7z"/>',
    refresh: '<path d="M20 11a8 8 0 1 0-2 6"/><path d="M20 4v7h-7"/>',
    external: '<path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M20 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5"/>',
    lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    eye: '<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.6"/>',
    eyeOff: '<path d="m3 3 18 18"/><path d="M10.6 6.2A9.7 9.7 0 0 1 12 6c6.4 0 10 6 10 6a17.6 17.6 0 0 1-3.2 3.8"/><path d="M6.5 8.3C3.9 9.9 2 12 2 12s3.6 6 10 6a9.7 9.7 0 0 0 3.3-.6"/><path d="M9.9 9.9a2.6 2.6 0 0 0 3.7 3.6"/>',
    trash: '<path d="M4 7h16M9 7V5h6v2M6 7l1 14h10l1-14"/>',
    arrow: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  };
  function icon(name, size) {
    const s = size || 18;
    return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.spark}</svg>`;
  }

  /* ---------- 持久化 ---------- */
  const params = new URLSearchParams(location.search);
  const PRESET = window.__MT__ || {};
  const KEY = "yingzhi.v2";
  function loadProgress() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; }
  }
  const progress = Object.assign({
    learned: [], bookmarks: [], cards: [], drills: {}, quiz: {}, assignments: [], checks: {}, last: {}, reviewed: [],
  }, loadProgress());
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(progress)); } catch (e) { /* file:// 可能不可用 */ }
  }
  const seededAssignments = [
    { id: "A-01", title: "胸部急症：气腔影与气胸", chain: "drill", count: 3, due: "11-20", note: "先定位，再说征象，最后选依据。", cases: ["D-CASE-005", "D-CASE-006", "D-CASE-019"] },
    { id: "A-02", title: "甲状腺结节：描述要素与条款条件", chain: "drill", count: 2, due: "11-22", note: "注意 TI-RADS 条款的适用条件，不背处理结论。", cases: ["D-CASE-011", "D-CASE-023"] },
    { id: "A-03", title: "正常解剖对照：先把“正常”看准", chain: "learn", count: 4, due: "11-18", note: "完成 4 个正常/解剖对照词条。", cases: ["SIGN-001", "SIGN-002", "SIGN-003", "SIGN-007"] },
  ];
  if (!progress.assignments.length) { progress.assignments = seededAssignments.slice(); save(); }

  const savedRole = (() => { try { return localStorage.getItem("yingzhi.role"); } catch (e) { return null; } })();
  const state = {
    role: params.get("role") || PRESET.role || savedRole || "student",
    device: params.get("device") || PRESET.device || "auto",
    view: "ask",
    signId: "SIGN-001", compareId: null, transferId: "SIGN-001", dualQuery: "",
    query: "", part: "", modality: "",
    drillId: null, drillStep: 1, drillAnswers: {}, drillResult: null, drillFilter: "",
    /* 练页双题库：病例演练 / 考点练习 */
    drillTab: "case", quizId: null, quizPicks: [], quizDone: false, quizResult: null, quizFilter: "", quizWrongOnly: false,
    caseId: "CASE-006", caseQuery: "", regionId: null, claimId: null, sync: true,
    applyTab: "workbench", teacherTab: "overview", auditBrokenOnly: false,
    modal: null, projection: null, toast: "",
    /* 移动端学习页：列表 → 详情二级页 */
    mobileSignOpen: false,
    /* 右侧证据栏：默认收起为 34px 折叠条，用户展开后跨页保持；窄屏由 CSS 自动隐藏 */
    evidence: false,
    /* 顶栏身份按钮的弹出菜单 */
    roleMenu: false,
    /* 医生端工作台：分区框默认显示，可一键隐藏只看影像 */
    showRegions: true,
    /* Agent 通道状态：唯一由真实 /api/ask 事件写入的地方，界面只读它 */
    agent: {
      status: "idle",      // idle | running | done | error
      query: "",
      text: "",
      spans: [],
      citations: [],
      runId: "",
      degraded: false,
      reason: "",
      ttft: null,
      total: null,
      traceUrl: "",
      stream: null,
    },
  };
  if (!ROLES[state.role]) state.role = "student";

  /* ---------- 数据辅助 ---------- */
  function regionName(id) { return REGION_LABEL[id] || id || ""; }
  function sign(id) { return SIGN.get(id); }
  function caseOf(id) { return CASE.get(id); }
  function guide(id) { return GUIDE.get(id); }
  function signCases(id) { const t = DB.transfer[id]; return (t ? t.cases : []).map(caseOf).filter(Boolean); }
  function signGuides(id) { const t = DB.transfer[id]; return (t ? t.guidelines : []).map(guide).filter(Boolean); }
  function relatedSigns(id) { const t = DB.transfer[id]; return (t ? t.related : []).map((x) => ({ sign: sign(x.id), shared: x.shared })).filter((x) => x.sign); }
  function crossPartSigns(id) { const t = DB.transfer[id]; return (t ? t.cross_part : []).map(sign).filter(Boolean); }
  function claimsOf(cid) { return DB.claimsByCase[cid] || []; }
  function regionsOf(cid) { return DB.regionsByCase[cid] || []; }

  /* ---------- 分片加载：cases 在首包，regions/claims 按部位懒加载 ---------- */
  const partsLoaded = new Set();
  function partOf(cid) {
    const c = DB.cases.find((x) => x.id === cid);
    return (c && c.part) || Object.keys(DB.parts || {})[0] || "chest_cr";
  }
  function loadPart(part) {
    if (!part || partsLoaded.has(part)) return Promise.resolve();
    partsLoaded.add(part);
    return new Promise((resolve) => {
      const s = document.createElement("script");
      s.src = "data/kb.part." + part + ".js";
      s.async = true;
      s.onload = () => {
        const d = (window.__KB_PARTS__ || {})[part];
        if (d) {
          Object.assign(DB.regionsByCase, d.regionsByCase || {});
          Object.assign(DB.claimsByCase, d.claimsByCase || {});
        }
        resolve();
      };
      s.onerror = () => { partsLoaded.delete(part); resolve(); };
      document.head.appendChild(s);
    });
  }
  function ensureCase(cid) {
    if (!cid || DB.regionsByCase[cid]) return Promise.resolve();
    return loadPart(partOf(cid));
  }
  function loadAllParts() {
    return Promise.all(Object.keys(DB.parts || {}).map(loadPart));
  }
  function currentSign() { return sign(state.signId) || DB.signs[0]; }
  function currentDrill() { return DRILL.get(state.drillId); }
  function role() { return ROLES[state.role]; }
  function isMobile() { return state.device === "mobile"; }
  function drillDone() { return Object.keys(progress.drills).length; }
  function chains() { return CHAINS[state.role] || CHAINS.student; }
  function taskDone() {
    return progress.assignments.filter((a) => {
      const ids = a.cases || [];
      if (a.chain === "learn") return ids.some((id) => progress.learned.includes(id));
      if (a.chain === "transfer") return progress.cards.length > 0;
      return ids.filter((id) => progress.drills[id]).length >= a.count;
    }).length;
  }
  function avgScore() {
    const vals = Object.values(progress.drills).map((x) => x.score || 0);
    return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : 0;
  }
  function learnedCount() { return uniq(progress.learned).length; }
  function classAvg(key) {
    const arr = DB.mockClass.map((s) => s[key]);
    return Math.round(arr.reduce((a, b) => a + b, 0) / arr.length);
  }
  function scoreOf(id) { return progress.drills[id] ? progress.drills[id].score : null; }
  function statusChip(status) {
    const map = { dual: ["双引用", "ok"], single: ["单引用", "warn"], broken: ["已拦截", "danger"], none: ["无引用", "danger"] };
    const [t, c] = map[status] || ["未知", ""];
    return `<span class="chip ${c}">${t}</span>`;
  }
  function citeBadge(c) {
    if (c.cite_status === "broken") return '<span class="chip danger">hash 不一致</span>';
    if (c.cite_status === "dual") return '<span class="chip ok">空间 + 文献</span>';
    return '<span class="chip warn">单引用</span>';
  }
  function docCite(claim) { return (claim.cites || []).find((x) => x.kind === "doc"); }
  function spatialCite(claim) { return (claim.cites || []).find((x) => x.kind === "spatial"); }
  function reviewedCount() { return uniq(progress.reviewed).length; }

  /* Agent 运行回执：把一次回答拆成可核对的知识库 → 技能 → 工作流 → Agent 四段 */
  /* ---------- 运行回执 ----------
   * 两种回执，口径必须分开，不能互相伪装：
   *   traceLive  —— 真实 Agent 运行，span 全部来自 /api/ask 的 trace 事件
   *   traceLocal —— 本地计算（检索/判分/核验），标注「本地计算」，不冒充 Agent
   */
  const TRACE_STAGES = [
    ["kb_retrieve", "知识库检索"],
    ["skill_invoke", "技能调用"],
    ["workflow", "工作流编排"],
    ["agent_generate", "Agent 生成"],
    ["persist", "结果落盘"],
  ];

  const SPAN_CLASS = {
    completed: "ok", error: "bad", blocked: "bad",
    degraded: "warn", unavailable: "off", skipped: "off", pending: "run",
  };

  function spanValue(s) {
    if (!s) return "未运行";
    const parts = [];
    if (s.skill && s.skill !== "none") parts.push(s.skill);
    // 命中数优先于状态词：completed 但 0 行，是「跑过了但没查到」，不是成功检索
    if (s.hits != null) parts.push(s.hits > 0 ? `命中 ${s.hits} 行` : "未命中");
    if (s.ms != null) parts.push(`${s.ms} ms`);
    if (s.status && s.status !== "completed") parts.push(s.status);
    return parts.length ? parts.join(" · ") : "completed";
  }

  /* 数据来源徽章：任何不是来自 Agent 真实链路的数据，都必须带一个。
   * 统一入口，避免每个页面各写各的「演示数据」小字，也避免漏标。 */
  const DATA_BADGES = {
    demo: ["演示数据", "班级/题目为演示数据，不是真实用户记录"],
    local: ["本地记录", "来自本机 localStorage，未上传服务端"],
    agent: ["Agent 运行", "来自 DeepWorks 引擎的真实调用"],
  };

  function dataBadge(kind) {
    const item = DATA_BADGES[kind] || DATA_BADGES.demo;
    return `<i class="data-badge ${kind}" title="${esc(item[1])}">${item[0]}</i>`;
  }

  function traceLive(spans, meta) {
    const by = {};
    (spans || []).forEach((s) => { if (s && s.stage) by[s.stage] = s; });
    const rows = TRACE_STAGES.map(([stage, label], i) => {
      const s = by[stage];
      const st = s ? (s.status || "pending") : "pending";
      const cls = (st === "completed" && s && s.hit === false) ? "warn" : (SPAN_CLASS[st] || "run");
      return `<div class="trace-step ${cls}" data-stage="${stage}">
        <span class="ts-no">${String(i + 1).padStart(2, "0")}</span>
        <b>${label}</b><span>${esc(spanValue(s))}</span>
      </div>`;
    }).join('<i class="trace-arrow">→</i>');

    const m = meta || {};
    const bits = [];
    if (m.runId) bits.push(`run …${esc(String(m.runId).slice(-8))}`);
    if (m.ttft != null) bits.push(`首字 ${m.ttft} ms`);
    if (m.total != null) bits.push(`总耗时 ${m.total} ms`);
    const base = typeof YZ.apiBase === "function" ? YZ.apiBase() : "";
    const link = m.traceUrl
      ? `<a href="${esc(base + m.traceUrl)}" target="_blank" rel="noopener" class="tiny">trace.json ${icon("external", 10)}</a>`
      : "";

    return `<div class="trace live">
      <div class="trace-h"><b>本次运行的真实链路</b><span>知识库 → 技能 → 工作流 → Agent → 落盘</span></div>
      <div class="trace-flow">${rows}</div>
      ${bits.length || link ? `<div class="trace-meta">${bits.map((x) => `<span>${x}</span>`).join("")}${link}</div>` : ""}
    </div>`;
  }

  /* 本地计算回执：只陈述前端真实做了什么，不写「Agent 运行」 */
  function traceLocal(title, steps) {
    return `<div class="trace local">
      <div class="trace-h"><b>${esc(title || "本地计算过程")}</b><span>本地计算 · 未调用 Agent</span></div>
      <div class="trace-flow">${(steps || []).map((s, i) => `<div class="trace-step ${s.state || ""}">
        <span class="ts-no">${String(i + 1).padStart(2, "0")}</span>
        <b>${esc(s.label || "")}</b><span>${esc(s.value || "")}</span>
      </div>`).join('<i class="trace-arrow">→</i>')}</div>
    </div>`;
  }

  function searchSigns(q) {
    const raw = (q || "").trim().toLowerCase();
    if (!raw) return [];
    const terms = raw.split(/\s+/).filter(Boolean);
    return DB.signs.map((s) => {
      const hay = [s.name, s.en, s.body_part, s.appearance, ...(s.aliases || []), ...(s.tags || []), ...(s.may_see_in || [])].join(" ").toLowerCase();
      let score = 0;
      for (const t of terms) {
        if (s.name.toLowerCase() === t) score += 120;
        if (s.name.toLowerCase().includes(t)) score += 36;
        if ((s.aliases || []).some((a) => a.toLowerCase().includes(t))) score += 24;
        if ((s.en || "").toLowerCase().includes(t)) score += 18;
        if (hay.includes(t)) score += 8;
        else {
          const hit = Array.from(t).filter((ch) => hay.includes(ch)).length;
          if (hit >= Math.max(2, Math.ceil(t.length * 0.6))) score += 3;
        }
      }
      return { s, score };
    }).filter((x) => x.score > 0).sort((a, b) => b.score - a.score).slice(0, 24).map((x) => x.s);
  }

  function filteredSigns() {
    let arr = DB.signs.slice();
    if (state.part) arr = arr.filter((s) => s.region_id === state.part);
    if (state.modality) arr = arr.filter((s) => (s.modality || []).includes(state.modality));
    if (state.query.trim()) {
      const found = searchSigns(state.query);
      const order = new Map(found.map((s, i) => [s.id, i]));
      arr = arr.filter((s) => order.has(s.id)).sort((a, b) => order.get(a.id) - order.get(b.id));
    }
    return arr;
  }

  /* ---------- 外壳 ---------- */
  function navButton(item) {
    const on = state.view === item.id;
    return `<button data-act="nav" data-view="${item.id}" class="${on ? "on" : ""}" title="${item.label}">
      <span class="ni">${icon(item.icon, 18)}</span><span>${item.label}</span>
      ${item.id === "drill" && drillDone() ? `<span class="badge">${drillDone()}</span>` : ""}
    </button>`;
  }

  function rail() {
    const r = role();
    return `<aside class="rail">
      <nav class="nav">
        ${r.nav.map(navButton).join("")}
        <a class="nav-a" href="read/clinic.html">
          <span class="ni">${icon("image", 18)}</span><span>读 · 胸片阅片</span>
        </a>
        <button data-act="nav" data-view="about" class="${state.view === "about" ? "on" : ""}">
          <span class="ni">${icon("shield", 18)}</span><span>关于与合规</span>
        </button>
      </nav>
      <div class="rail-foot">
        <b>${icon("lock", 12)} 教学研究用途</b>
        不构成诊断意见，不替代临床决策。病例均为公开许可影像。内容经 AI 预审，正式使用前须经医学人员审核。
      </div>
    </aside>`;
  }

  function tabbar() {
    const r = role();
    return `<nav class="tabbar">
      ${r.tabs.map((id) => {
        const item = r.nav.find((x) => x.id === id);
        const on = state.view === id;
        return `<button data-act="nav" data-view="${id}" class="${on ? "on" : ""}">
          <span class="ti">${icon(item.icon, 21)}</span><span>${item.short || item.label.split(" · ")[0]}</span>
          ${id === "drill" && drillDone() ? `<span class="badge">${drillDone()}</span>` : ""}
        </button>`;
      }).join("")}
    </nav>`;
  }

  function roleMenuHTML() {
    const r = role();
    return `<div class="id-menu" id="idMenu">
      <div class="idm-h">当前身份</div>
      <div class="idm-now"><i></i>${r.name}端 · ${r.full}</div>
      <div class="idm-sep"></div>
      <div class="idm-h">切换演示角色</div>
      ${["student", "teacher", "doctor"].map((k) => `<button data-act="role" data-role="${k}" class="${state.role === k ? "on" : ""}">
        <span class="ck">${state.role === k ? icon("check", 12) : ""}</span>
        <span class="grow"><b>${ROLES[k].name}端</b><em>${ROLES[k].full}</em></span>
      </button>`).join("")}
      <div class="idm-sep"></div>
      <button data-act="reset"><span class="ck"></span><span class="grow"><b>重置本地进度</b></span></button>
      <button data-act="nav" data-view="about"><span class="ck"></span><span class="grow"><b>关于与合规</b></span></button>
    </div>`;
  }

  function topbar() {
    const r = role();
    return `<header class="topbar">
      <div class="brand" data-act="nav" data-view="home" style="cursor:pointer">
        <div class="brand-mark">影</div>
        <div class="brand-txt"><b>RadioCheck</b><span>影像临床思维平台</span></div>
      </div>
      <div class="top-search">
        <span class="si">${icon("search", 17)}</span>
        <input id="topQ" placeholder="问一句或搜征象，例如：右肺中野有没有结节？" autocomplete="off">
        <kbd>⌘K</kbd>
      </div>
      <div class="top-actions">
        <button class="btn ghost sm top-me" data-act="nav" data-view="me">我的记录</button>
        <div class="identity-wrap">
          <button class="identity" data-act="role-menu" aria-haspopup="menu" aria-expanded="${state.roleMenu ? "true" : "false"}" title="${r.name}端 · ${r.full}">
            <span class="av">${r.mark}</span>
            <span class="who"><b>${r.name}端</b><span>${r.full}</span></span>
            <span class="car"></span>
          </button>
          ${state.roleMenu ? roleMenuHTML() : ""}
        </div>
      </div>
    </header>`;
  }

  /* ---------- 右侧证据栏 ----------
   * 只展示已经存在的数据：当前征象的引用、最近一次 Agent 回执的 span、本地进度。
   * 不在这里发起任何请求，也不推算缺失值；没有数据就写「暂无」。
   */
  function evidenceBody() {
    if (state.view === "drill") return drillEvidence();
    if (state.view === "apply") return caseEvidence();

    const s = currentSign();
    // signCases 返回病例对象，不是 id；这里要的是病例 id 才能取到该病例的引用
    const c0 = s ? signCases(s.id)[0] : null;
    const cid = c0 && c0.id;
    // 一个征象可能关联多个病例，逐个找明确包含该征象的结论。
    // 找不到就不回退到别的结论——显示无关引用比显示「暂无」更误导。
    const cases = s ? signCases(s.id) : [];
    let claim = null;
    let list = [];
    for (const c of cases) {
      const l = (DB.claimsByCase[c.id] || []);
      const hit = l.find((x) => (x.sign_ids || []).includes(s.id));
      if (hit) { claim = hit; list = l; break; }
    }
    if (!claim && cases.length) list = DB.claimsByCase[cases[0].id] || [];
    const doc = claim ? docCite(claim) : null;
    const sp = claim ? spatialCite(claim) : null;
    const a = state.agent;
    const spans = (a.spans || []).filter((x) => TRACE_STAGES.some((t) => t[0] === x.stage));

    const citeRow = (label, cite) => {
      if (!cite) return `<div class="evr-cite"><span class="evr-k">${label}</span><span class="evr-none">暂无</span></div>`;
      const anchor = cite.anchor || {};
      const title = anchor.doc_title || anchor.image_id || anchor.doc_id || cite.kind;
      const loc = anchor.locator || anchor.bbox ? (anchor.locator || "空间框选") : "";
      const bad = cite.hash_ok === false;
      return `<div class="evr-cite">
        <span class="evr-k">${label}</span>
        <span class="evr-v ${bad ? "bad" : ""}">${esc(title)}</span>
        ${loc ? `<span class="evr-loc">${esc(loc)}</span>` : ""}
        ${bad ? `<span class="chip danger">hash 不一致</span>` : ""}
      </div>`;
    };

    return `<div class="evr-body">
      <div class="evr-head">
        <span>证据栏</span>
        <span class="evr-hint">随当前内容变化</span>
      </div>

      <section class="evr-sec">
        <h4>当前内容</h4>
        ${s ? `<div class="evr-sign" data-act="sign" data-id="${s.id}">
          <b>${esc(s.name)}</b>
          <span class="evr-meta">${esc(s.id)} · ${esc(regionName(s.region_id))} · ${esc((s.modality || []).join("/"))}</span>
        </div>` : `<div class="evr-none">未选中内容</div>`}
      </section>

      <section class="evr-sec">
        <h4>引用出处 ${claim ? statusChip(claim.cite_status) : ""}</h4>
        ${claim
          ? `${citeRow("文献", doc)}${citeRow("空间", sp)}`
          : `<div class="evr-none">该征象暂无专属引用结论。${list.length ? `所属病例另有 ${list.length} 条分区结论，未计入本条。` : ""}</div>`}
      </section>

      <section class="evr-sec">
        <h4>最近一次 Agent 回执</h4>
        ${a.status === "idle"
          ? `<div class="evr-none">本页尚未发起问答。去「学」里提问后会在这里留下回执。</div>`
          : `<div class="evr-agent ${a.degraded ? "warn" : ""}">
              <div class="evr-q">${esc(a.query || "")}</div>
              ${spans.length
                ? spans.map((x) => `<div class="evr-span ${x.status === "completed" && x.hit === false ? "warn" : ""}">
                    <span>${esc(stageLabel(x.stage))}</span>
                    <span class="evr-ms">${x.ms != null ? x.ms + "ms" : x.status}</span>
                  </div>`).join("")
                : `<div class="evr-none">回执为空</div>`}
              ${a.degraded ? `<div class="evr-deg">降级：${esc(a.reason || "未知原因")}</div>` : ""}
            </div>`}
      </section>

      <section class="evr-sec">
        <h4>本地进度</h4>
        <div class="evr-stats">
          <div><b>${learnedCount()}</b><span>已学词条</span></div>
          <div><b>${drillDone()}</b><span>已完成演练</span></div>
          <div><b>${reviewedCount()}</b><span>已核验病例</span></div>
        </div>
      </section>

      <div class="evr-foot">教学研究用途 · 不构成诊断意见</div>
    </div>`;
  }

  function stageLabel(id) {
    const hit = TRACE_STAGES.find((t) => t[0] === id);
    return hit ? hit[1] : id;
  }

  /* 演练页：作答前不展示证据，避免剧透；只给影像来源与许可 */
  function drillEvidence() {
    // 考点练习没有影像，证据栏改为「题目 + 出处」，易错点在作答后才展开
    const q = state.quizId ? (DB.quiz || []).find((x) => x.id === state.quizId) : null;
    if (q) {
      return `<div class="evr-body">
        <div class="evr-head"><span>证据栏</span><span class="evr-hint">考点练习</span></div>
        <section class="evr-sec">
          <h4>当前题目</h4>
          <div class="evr-sign"><b>${esc(q.signName)}</b>
            <span class="evr-meta">${esc(q.typeName)} · ${esc(q.bodyPart || "")} · ${esc(q.signId)}</span>
          </div>
        </section>
        <section class="evr-sec">
          <h4>知识库出处</h4>
          <div class="evr-cite"><span class="evr-k">来源</span>
            <span class="evr-v">${esc(q.source || "未标注")}</span></div>
          ${q.sourceUrl ? `<div class="evr-cite"><span class="evr-k">原文</span><span class="evr-v" style="word-break:break-all">${esc(q.sourceUrl)}</span></div>` : ""}
        </section>
        <section class="evr-sec">
          <h4>易错点</h4>
          ${state.quizDone
            ? `<ul class="evr-pits">${(q.pitfalls || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
            : `<div class="evr-none">作答后展开，避免剧透。</div>`}
        </section>
        <div class="evr-foot">教学研究用途 · 不构成诊断意见</div>
      </div>`;
    }

    const d = currentDrill();
    const head = `<div class="evr-head"><span>证据栏</span><span class="evr-hint">演练中</span></div>`;
    if (!d) {
      return `<div class="evr-body">${head}<section class="evr-sec">
        <div class="evr-none">尚未选择题目。进入「练」后选一道题，这里会显示影像来源与许可。</div>
      </section></div>`;
    }
    return `<div class="evr-body">${head}
      <section class="evr-sec">
        <h4>当前题目</h4>
        <div class="evr-sign"><b>${esc(d.title)}</b>
          <span class="evr-meta">${esc(d.caseId)} · ${esc(d.bodyPart || "")} · ${esc((d.modality || []).join("/"))}</span>
        </div>
      </section>
      <section class="evr-sec">
        <h4>证据</h4>
        <div class="evr-none">为避免剧透，证据栏在提交本次作答后展开。作答前只显示影像来源与许可。</div>
      </section>
      <section class="evr-sec">
        <h4>影像来源</h4>
        <div class="evr-cite"><span class="evr-k">许可</span><span class="evr-v">${esc(d.license || "未标注")}</span></div>
        ${d.artist ? `<div class="evr-cite"><span class="evr-k">作者</span><span class="evr-v">${esc(d.artist)}</span></div>` : ""}
        ${d.sourcePage ? `<div class="evr-cite"><span class="evr-k">页面</span><span class="evr-v" style="word-break:break-all">${esc(d.sourcePage)}</span></div>` : ""}
      </section>
      <div class="evr-foot">教学研究用途 · 不构成诊断意见</div>
    </div>`;
  }

  /* 应用页：展示当前病例的分区结论与引用状态 */
  function caseEvidence() {
    const c = caseOf(state.caseId);
    const head = `<div class="evr-head"><span>证据栏</span><span class="evr-hint">当前病例</span></div>`;
    if (!c) {
      return `<div class="evr-body">${head}<section class="evr-sec">
        <div class="evr-none">尚未选择病例。</div>
      </section></div>`;
    }
    const claims = claimsOf(c.id);
    const dual = claims.filter((x) => x.cite_status === "dual").length;
    const broken = claims.filter((x) => x.cite_status === "broken").length;
    return `<div class="evr-body">${head}
      <section class="evr-sec">
        <h4>当前病例</h4>
        <div class="evr-sign"><b>${esc(c.title)}</b>
          <span class="evr-meta">${esc(c.id)} · ${esc(regionName(c.region_id))} · ${esc((c.modality || []).join("/"))}</span>
        </div>
      </section>
      <section class="evr-sec">
        <h4>分区结论</h4>
        <div class="evr-stats">
          <div><b>${claims.length}</b><span>结论</span></div>
          <div><b>${dual}</b><span>双引用</span></div>
          <div><b class="${broken ? "bad" : ""}">${broken}</b><span>已拦截</span></div>
        </div>
        ${claims.slice(0, 3).map((x) => `<div class="evr-cite">
          <span class="evr-k">${esc(x.id)} ${statusChip(x.cite_status)}</span>
          <span class="evr-v">${esc((x.text || "").slice(0, 46))}${(x.text || "").length > 46 ? "…" : ""}</span>
        </div>`).join("")}
      </section>
      <div class="evr-foot">教学研究用途 · 不构成诊断意见</div>
    </div>`;
  }

  function evidence() {
    // 问答页的引用已在回答栏内成对呈现，右侧证据栏会重复并挤占影像宽度。
    if (state.view === "ask") return "";
    const on = state.evidence;
    return `<aside class="evr-rail ${on ? "on" : "off"}" id="evrRail">
      <button class="evr-fold" data-act="evidence" title="${on ? "收起证据栏" : "展开证据栏"}" aria-label="证据栏开关">
        ${icon(on ? "right" : "left", 14)}
      </button>
      ${on ? evidenceBody() : `<span class="evr-tab" data-act="evidence" title="展开证据栏">证据</span>`}
    </aside>`;
  }

  function focusMode() {
    if (state.role !== "doctor" || state.view !== "apply" || state.applyTab !== "workbench") return false;
    return !isMobile();
  }

  function shell(content) {
    document.body.className = `role-${state.role}` + (isMobile() ? " force-mobile" : "") + (focusMode() ? " focus-mode" : "");
    const noEvr = state.view === "ask" ? " no-evr" : "";
    return `${topbar()}
      <div class="shell evr-${state.evidence ? "on" : "off"}${noEvr}">${rail()}<main class="main"><div class="main-inner">${content}</div></main>${evidence()}</div>
      ${tabbar()}
      <div class="toast ${state.toast ? "on" : ""}" id="toast">${esc(state.toast)}</div>
      ${state.modal ? YZ.modalHTML() : ""}
      ${state.projection ? YZ.projectionHTML() : ""}`;
  }

  /* 医生端病例工作台：影像与结论已同屏，右侧证据栏内容重复。
   * 进入该页时默认收起证据栏，把宽度让给影像（分区框太窄会把标注挤成一团）；
   * 用户仍可点折叠按钮手动展开，展开后保持，不强制。 */
  function syncEvidenceForView(view) {
    if (view === "apply" && state.role === "doctor") state.evidence = false;
    if (view === "ask") state.evidence = false;
  }

  function go(view, opts) {
    const r = role();
    const allowed = r.nav.some((x) => x.id === view) || view === "about";
    if (!allowed) view = "home";
    state.view = view;
    if (opts && opts.tab) { state.applyTab = opts.tab; state.teacherTab = opts.tab; }
    state.modal = null;
    state.roleMenu = false;
    syncEvidenceForView(view);
    const hash = "#/" + view + (view === "learn" && state.signId ? "/" + state.signId : view === "transfer" && state.transferId ? "/" + state.transferId : view === "drill" && state.drillId ? "/" + state.drillId : "");
    if (location.hash !== hash) history.pushState(null, "", hash);
    render();
    window.scrollTo({ top: 0, behavior: "instant" in document.documentElement.style ? "instant" : "auto" });
  }

  function setRole(k) {
    if (!ROLES[k]) return;
    state.role = k;
    try { localStorage.setItem("yingzhi.role", k); } catch (e) { /* ignore */ }
    state.view = "home";
    state.modal = null;
    state.projection = null;
    state.roleMenu = false;
    state.drillId = null;
    state.drillResult = null;
    history.pushState(null, "", "#/home");
    render();
  }

  function setDevice(d) {
    state.device = d;
    render();
  }

  function toast(msg) {
    state.toast = msg;
    render();
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { state.toast = ""; const t = $("#toast"); if (t) t.classList.remove("on"); }, 2200);
  }

  function render() {
    let content;
    switch (state.view) {
      case "ask": content = YZ.askView(); break;
      case "learn": content = YZ.learnView(); break;
      case "transfer": content = YZ.transferView(); break;
      case "drill": content = YZ.drillView(); break;
      case "apply": content = YZ.applyView(); break;
      case "me": content = YZ.meView(); break;
      case "about": content = YZ.aboutView(); break;
      default: content = YZ.homeView();
    }
    app.innerHTML = shell(content);
    if (state.projection) document.body.classList.add("projecting");
    else document.body.classList.remove("projecting");
  }

  function copyText(text, okMsg) {
    const done = () => toast(okMsg || "已复制");
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else fallbackCopy(text, done);
  }
  function fallbackCopy(text, done) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { toast("复制失败，请手动选择"); }
    document.body.removeChild(ta);
  }
  function download(name, text, type) {
    const blob = new Blob([text], { type: type || "text/markdown;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
    toast("已下载 " + name);
  }

  function parseHash() {
    const h = (location.hash || "").replace(/^#\/?/, "");
    if (!h) return;
    const [view, id] = h.split("/");
    const r = role();
    if (view === "about" || r.nav.some((x) => x.id === view)) state.view = view;
    syncEvidenceForView(state.view);
    if (view === "learn" && id) state.signId = id;
    if (view === "transfer" && id) { state.transferId = id; state.signId = id; }
    if (view === "drill" && id) { state.drillId = id; state.drillStep = 1; state.drillAnswers = {}; state.drillResult = null; }
  }

  /* ---------- 导出 ---------- */
  Object.assign(YZ, {
    DB, app, ROLES, CHAINS, SIGN, CASE, GUIDE, GROUP, DRILL, REGION_LABEL,
    $, $$, esc, pct, clamp, uniq, today, modsOf, icon,
    progress, save, state, role, isMobile, go, setRole, setDevice, render, toast,
    regionName, sign, caseOf, guide, signCases, signGuides, relatedSigns, crossPartSigns,
    claimsOf, regionsOf, loadPart, ensureCase, loadAllParts, partOf, currentSign, currentDrill, drillDone, chains, taskDone, avgScore, learnedCount, classAvg,
    scoreOf, statusChip, citeBadge, docCite, spatialCite, reviewedCount,
    traceLive, traceLocal, TRACE_STAGES, dataBadge, searchSigns, filteredSigns,
    shell, copyText, download, parseHash,
  });
})(window.YZ = window.YZ || {});
