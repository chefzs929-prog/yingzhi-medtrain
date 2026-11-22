/* 课堂 · 教师端 / 学生端
 * 数据层在 classroom-core.js；本文件只负责渲染与交互。
 */
(function () {
  "use strict";

  const RC = window.RCClass;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  const S = {
    data: null,
    role: "",
    teacherTab: "overview",
    studentTab: "home",
    groupId: "",
    postId: "",
    groupFilter: "all",
    analysisId: "",
    setup: { className: "2026 春季影像规培班", teacherName: "带教老师" },
    draft: { title: "", due: RC.plusDays(7), note: "", caseIds: [] },
    join: { name: "", code: "" },
  };

  function toast(msg) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("on");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("on"), 2400);
  }

  function allCases() {
    if (!S.data || !Array.isArray(S.data.cases)) return [];
    return S.data.cases.filter((c) => c.enabled);
  }

  function caseById(id) {
    return allCases().find((c) => c.id === id) || null;
  }

  function caseTitle(id) {
    const c = caseById(id);
    return c ? `${c.id} · ${c.title}` : id;
  }

  function tagsOf(c) {
    const t = [];
    if (!c.signs.length) t.push("正常/对照");
    if (c.signs.includes("SIGN-002")) t.push("气腔影");
    if (c.signs.includes("SIGN-008")) t.push("气胸");
    if (c.signs.includes("SIGN-007")) t.push("积液");
    if (c.signs.includes("SIGN-003")) t.push("结节");
    if (c.signs.includes("SIGN-010")) t.push("心影增大");
    return t;
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16).replace("T", " ");
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function pctText(n) {
    return typeof n === "number" ? `${Math.round(n * 10) / 10}%` : "—";
  }

  function scoreText(n) {
    return typeof n === "number" ? String(n) : "—";
  }

  function progressBar(done, total, warn) {
    const pct = total ? Math.min(100, Math.round((done / total) * 100)) : 0;
    return `<div class="bar-track${warn ? " warn" : ""}"><i style="width:${pct}%"></i></div>`;
  }

  function copyText(text) {
    const done = () => toast("已复制");
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else fallbackCopy(text, done);
  }

  function fallbackCopy(text, done) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
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
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  /* ---------------- 角色入口 ---------------- */

  function gateHTML() {
    return `<div class="page-head">
      <div><div class="eyebrow">RADIOLOGY CLASSROOM</div><h1>课堂 · 教师与学生</h1>
      <p>教师建班、布置胸片作业；学生用班级码加入，在阅片工作台完成定位、判读与征象三题；提交后自动回流成绩与错题。</p></div>
    </div>
    <div class="role-gate">
      <div class="gate-card teacher">
        <div class="g-ic">T</div>
        <h2>教师端</h2>
        <p>把 21 例胸片按教学进度组成本班作业，查看提交率、均分与逐题错误分布。</p>
        <ul>
          <li>建班后生成 6 位班级码，学生凭码加入</li>
          <li>按病例布置作业，设置截止日期与及格线</li>
          <li>按学生 / 病例 / 题型三段查看学情</li>
          <li>查看班级互助小组与组内论坛</li>
          <li>导出班级报告，可直接用于讲评</li>
        </ul>
        <button class="btn solid" data-act="role" data-role="teacher">进入教师端 →</button>
      </div>
      <div class="gate-card student">
        <div class="g-ic">S</div>
        <h2>学生端</h2>
        <p>加入班级后领取作业；另有影像库问答、读片陪练、自测出题器与班级互助小组。</p>
        <ul>
          <li>班级码 + 姓名即可加入，无需注册</li>
          <li>考核模式下分区不着色、病例标题隐藏</li>
          <li>影像库问答：区域定位 + 文献溯源双引用</li>
          <li>读片陪练、自测出题器与错题重做</li>
          <li>班级互助小组：组内论坛提问与回复</li>
        </ul>
        <button class="btn" data-act="role" data-role="student">进入学生端 →</button>
      </div>
    </div>
    <div class="local-note"><b>本地演示：</b>班级、作业与答题记录保存在当前浏览器的 localStorage，不会上传服务器。
      换一台设备或换浏览器需要重新建班；跨设备同步需接入后端。教师端与学生端可在同一浏览器切换，便于现场演示。</div>`;
  }

  function setupHTML() {
    return `<div class="page-head">
      <div><div class="eyebrow">TEACHER · SETUP</div><h1>教师端 · 先建一个班级</h1>
      <p>建班后生成班级码。学生用班级码加入，教师再按病例布置作业。</p></div>
    </div>
    <div class="panel-card">
      <div class="panel-h"><h3>班级信息</h3><span class="sub">只在本机保存</span></div>
      <div class="form-grid">
        <div class="field"><label for="className">班级名称</label>
          <input id="className" value="${esc(S.setup.className)}" maxlength="40" placeholder="例如：2026 春季影像规培班"></div>
        <div class="field"><label for="teacherName">教师姓名</label>
          <input id="teacherName" value="${esc(S.setup.teacherName)}" maxlength="30" placeholder="例如：王老师"></div>
      </div>
      <div class="form-actions">
        <button class="btn solid" data-act="create-class">创建班级并生成班级码</button>
        <button class="btn" data-act="demo-class">载入演示班级（6 名学生 + 1 份作业）</button>
      </div>
      <p class="note" style="margin-top:10px">演示班级会写入 6 名演示学生和 1 份 6 例作业，方便直接看教师端与学情分析。</p>
    </div>`;
  }

  /* ---------------- 教师端 ---------------- */

  function teacherHTML() {
    const cls = RC.activeClass();
    if (!cls) return setupHTML();
    const stats = RC.classStats(cls.id);
    const tabs = [
      ["overview", "班级概览"],
      ["assign", "作业编排"],
      ["analysis", "学情分析"],
      ["group", "互助小组"],
    ];
    const head = `<div class="page-head">
      <div><div class="eyebrow">TEACHING CONSOLE</div><h1>教师端 · ${esc(cls.name)}</h1>
      <p>${esc(cls.teacher)} · 班级码 <b class="mono">${esc(cls.code)}</b> · 数据只在本机浏览器</p></div>
      <div class="page-actions">
        <button class="btn" data-act="role" data-role="student">切到学生端</button>
        <button class="btn solid" data-act="new-assignment">布置作业</button>
      </div>
    </div>`;
    const metrics = `<div class="metric-grid">
      <div class="metric"><b>${stats.students}</b><span>学生</span><em>已加入班级</em></div>
      <div class="metric"><b>${stats.assignments}</b><span>作业</span><em>按病例组卷</em></div>
      <div class="metric"><b>${pctText(stats.rate)}</b><span>提交率</span><em>${stats.submitted}/${stats.cells} 个病例作答</em></div>
      <div class="metric"><b>${scoreText(stats.avg)}</b><span>平均分</span><em>${stats.passRate == null ? "尚无作答" : `及格率 ${pctText(stats.passRate)}`}</em></div>
    </div>`;
    const tabsHTML = `<div class="class-tabs">${tabs.map(([id, label]) =>
      `<button data-teacher-tab="${id}" class="${S.teacherTab === id ? "on" : ""}">${label}</button>`).join("")}</div>`;
    let body = "";
    if (S.teacherTab === "assign") body = teacherAssignHTML(cls);
    else if (S.teacherTab === "analysis") body = teacherAnalysisHTML(cls);
    else if (S.teacherTab === "group") body = teacherGroupHTML(cls);
    else body = teacherOverviewHTML(cls);
    return head + metrics + tabsHTML + body;
  }

  function teacherOverviewHTML(cls) {
    const rows = cls.students.map((s) => {
      const st = RC.studentStats(cls.id, s.id);
      const total = st.cells;
      const lastAt = st.attempts.reduce((m, a) => (String(a.at) > m ? String(a.at) : m), "");
      return `<tr>
        <td class="name">${esc(s.name)}</td>
        <td class="num">${st.submitted}/${total}</td>
        <td class="num">${scoreText(st.avg)}</td>
        <td class="num muted">${fmtTime(lastAt)}</td>
        <td class="num"><button class="btn sm" data-as-student="${esc(s.id)}">以该生身份进入</button>
          <button class="btn sm ghost" data-remove-student="${esc(s.id)}">移除</button></td>
      </tr>`;
    }).join("");
    const roster = `<div class="panel-card">
      <div class="panel-h"><h3>学生名单</h3><span class="sub">${cls.students.length} 人</span></div>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>姓名</th><th class="num">完成病例</th><th class="num">均分</th><th class="num">最近提交</th><th class="num">操作</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="5"><div class="empty-inline"><b>还没有学生</b>把班级码发给学生，或在下面手动添加。</div></td></tr>`}</tbody>
      </table></div>
      <div class="form-actions">
        <input id="newStudentName" placeholder="手动添加学生姓名" maxlength="20" style="height:32px;border:1px solid var(--line);border-radius:8px;padding:0 10px;font-size:12px;background:var(--surface-2);min-width:180px">
        <button class="btn" data-act="add-student">添加学生</button>
      </div>
    </div>`;
    const progress = cls.assignments.length ? `<div class="assign-list">${cls.assignments.map((a) => {
      const st = RC.assignmentStats(cls.id, a.id);
      const done = st ? st.totals.submitted : 0;
      const total = st ? st.totals.cells : 0;
      return `<div class="assign-card">
        <div class="ac-top">
          <div><h4>${esc(a.title)}</h4>
            <div class="ac-meta"><span>${a.caseIds.length} 例</span><span>截止 ${esc(a.due || "待定")}</span><span>及格 ${a.passScore}</span></div>
          </div>
          <span class="badge ${done >= total && total ? "ok" : "info"}">${done}/${total}</span>
        </div>
        <div class="ac-prog" style="margin-top:9px">
          <div class="lbl"><span>提交进度</span><span>${total ? Math.round(done / total * 100) : 0}%</span></div>
          ${progressBar(done, total, total && done < total)}
        </div>
        <div class="ac-foot">
          <span class="mini-chip">均分 ${st ? scoreText(st.totals.avg) : "—"}</span>
          <span class="mini-chip">及格率 ${st ? pctText(st.totals.passRate) : "—"}</span>
          <span class="spacer"></span>
          <button class="btn sm" data-analysis="${esc(a.id)}">看学情</button>
          <button class="btn sm" data-student-try="${esc(a.id)}">学生试做</button>
        </div>
      </div>`;
    }).join("")}</div>` : `<div class="empty-inline"><b>还没有作业</b>点右上角「布置作业」，从 21 例胸片里选病例。</div>`;

    return `<div class="grid-2">
      <div class="stack">
        <div class="panel-card">
          <div class="panel-h"><h3>班级码</h3><span class="sub">学生凭码加入</span></div>
          <div class="code-box">
            <div class="cb-l"><span>CLASS CODE</span><b>${esc(cls.code)}</b>
              <p>${esc(cls.name)} · ${cls.students.length} 名学生</p></div>
            <button class="btn sm" data-act="copy-code">复制班级码</button>
          </div>
          <p class="note" style="margin-top:10px">演示时可在同一浏览器切到学生端，用这个班级码加入；换设备需重新建班。</p>
        </div>
        ${roster}
      </div>
      <div class="stack">
        <div class="panel-card">
          <div class="panel-h"><h3>作业进度</h3><span class="sub">${cls.assignments.length} 份</span></div>
          ${progress}
        </div>
        <div class="panel-card">
          <div class="panel-h"><h3>讲评建议</h3><span class="sub">通用</span></div>
          <ul class="plain-list">
            <li>先让学生自己定位异常分区，再揭示分区状态；不要一上来就给答案。</li>
            <li>错得最多的一般不是“看不见”，而是把「来源未提及」当成「正常」。</li>
            <li>讲评时回到影像：让学生指出分区框，再读出该区依据。</li>
          </ul>
        </div>
      </div>
    </div>`;
  }

  function teacherAssignHTML(cls) {
    const cases = allCases();
    const selected = new Set(S.draft.caseIds);
    const picker = cases.map((c) => {
      const tags = tagsOf(c).slice(0, 2).map((t) =>
        `<span class="tag${t === "正常/对照" ? "" : " ab"}">${esc(t)}</span>`).join("");
      return `<label class="case-opt${selected.has(c.id) ? " on" : ""}">
        <input type="checkbox" value="${esc(c.id)}" ${selected.has(c.id) ? "checked" : ""}>
        <span><b>${esc(c.id.replace("CASE-", ""))} · ${esc(c.title)}</b>
        <span>${esc(c.pose_label)} · ${esc(c.quality)}</span>${tags}</span>
      </label>`;
    }).join("");
    const list = cls.assignments.length ? `<div class="assign-list">${cls.assignments.map((a) => {
      const st = RC.assignmentStats(cls.id, a.id);
      return `<div class="assign-card">
        <div class="ac-top"><div><h4>${esc(a.title)}</h4>
          <div class="ac-meta"><span>${a.caseIds.length} 例</span><span>截止 ${esc(a.due || "待定")}</span><span>创建 ${fmtTime(a.createdAt)}</span></div></div>
          <span class="badge info">${st ? `${st.totals.submitted}/${st.totals.cells}` : "0/0"}</span></div>
        ${a.note ? `<div class="ac-note">${esc(a.note)}</div>` : ""}
        <div class="ac-foot"><span class="mini-chip">均分 ${st ? scoreText(st.totals.avg) : "—"}</span>
          <span class="spacer"></span>
          <button class="btn sm" data-analysis="${esc(a.id)}">看学情</button>
          <button class="btn sm" data-student-try="${esc(a.id)}">学生试做</button>
          <button class="btn sm ghost" data-del-assign="${esc(a.id)}">删除</button>
        </div>
      </div>`;
    }).join("")}</div>` : `<div class="empty-inline"><b>还没有作业</b>在上方选病例后发布。</div>`;

    return `<div class="panel-card">
      <div class="panel-h"><h3>新建作业</h3><span class="sub">从 21 例 CR 胸部里选</span></div>
      <div class="form-grid">
        <div class="field full"><label for="assignTitle">作业标题</label>
          <input id="assignTitle" value="${esc(S.draft.title)}" maxlength="60" placeholder="例如：胸片基础：定位与征象"></div>
        <div class="field"><label for="assignDue">截止日期</label>
          <input id="assignDue" type="date" value="${esc(S.draft.due)}"></div>
        <div class="field"><label for="assignNote">讲评提示（可选）</label>
          <input id="assignNote" value="${esc(S.draft.note)}" maxlength="200" placeholder="例如：先定位，再判断状态，最后选征象"></div>
      </div>
      <div class="panel-h" style="margin-top:16px"><h3>选择病例</h3><span class="sub" id="pickCount">已选 ${S.draft.caseIds.length} 例</span></div>
      <div class="picker-tools">
        <button class="btn sm" data-preset="all">全选 21 例</button>
        <button class="btn sm" data-preset="clear">清空</button>
        <button class="btn sm" data-preset="demo">推荐 6 例（正常 / 实变 / 气胸 / 积液 / 结节 / 结核）</button>
      </div>
      <div class="case-picker" id="casePicker">${picker}</div>
      <div class="form-actions">
        <button class="btn solid" data-act="create-assignment">发布作业</button>
        <span class="note">学生提交后，成绩与错题会自动出现在「学情分析」。</span>
      </div>
    </div>
    <div class="panel-card">
      <div class="panel-h"><h3>已布置作业</h3><span class="sub">${cls.assignments.length} 份</span></div>
      ${list}
    </div>`;
  }

  function ensureAnalysisId(cls) {
    if (!cls.assignments.length) return null;
    if (!S.analysisId || !cls.assignments.some((a) => a.id === S.analysisId)) {
      S.analysisId = cls.assignments[0].id;
    }
    return S.analysisId;
  }

  function teacherAnalysisHTML(cls) {
    if (!cls.assignments.length) {
      return `<div class="panel-card"><div class="empty-inline"><b>还没有可分析的作业</b>先在「作业编排」里发布一份作业。</div></div>`;
    }
    const aid = ensureAnalysisId(cls);
    const st = RC.assignmentStats(cls.id, aid);
    const a = st.assignment;
    const options = cls.assignments.map((x) =>
      `<option value="${esc(x.id)}" ${x.id === aid ? "selected" : ""}>${esc(x.title)}</option>`).join("");
    const head = `<div class="panel-card">
      <div class="panel-h"><h3>选择作业</h3>
        <div class="page-actions"><select id="analysisSel" style="height:32px;border:1px solid var(--line);border-radius:8px;padding:0 9px;background:var(--surface-2);font-size:12px">${options}</select>
        <button class="btn" data-act="export-report">导出班级报告</button></div>
      </div>
      <p class="note">${esc(a.title)} · ${a.caseIds.length} 例 · 截止 ${esc(a.due || "待定")} · 及格线 ${a.passScore}</p>
    </div>`;
    if (!st.totals.submitted) {
      return head + `<div class="panel-card"><div class="empty-inline">
        <b>还没有学生提交</b>把班级码发给学生，或点「学生试做」先走一遍流程。<br>
        <button class="btn sm" data-act="seed-attempts" style="margin-top:9px">填充演示答题（本地，仅用于看板演示）</button>
      </div></div>`;
    }
    const metrics = `<div class="metric-grid">
      <div class="metric"><b>${pctText(st.totals.rate)}</b><span>提交率</span><em>${st.totals.submitted}/${st.totals.cells}</em></div>
      <div class="metric"><b>${scoreText(st.totals.avg)}</b><span>平均分</span><em>满分 100</em></div>
      <div class="metric"><b>${pctText(st.totals.passRate)}</b><span>及格率</span><em>≥ ${a.passScore} 分</em></div>
      <div class="metric"><b>${pctText(st.totals.signRate)}</b><span>征象得分率</span><em>定位 ${pctText(st.totals.zoneRate)} · 判读 ${pctText(st.totals.statusRate)}</em></div>
    </div>`;
    const studentRows = st.students.map((s) => `<tr>
      <td class="name">${esc(s.name)}</td>
      <td class="num">${s.completed}/${s.total}</td>
      <td class="num">${scoreText(s.avg)}</td>
      <td class="num muted">${fmtTime(s.lastAt)}</td>
      <td>${progressBar(s.completed, s.total, s.completed < s.total)}</td>
    </tr>`).join("");
    const caseRows = st.cases.map((x) => {
      const low = (v) => typeof v === "number" && v < 60;
      return `<tr>
        <td class="name">${esc(caseTitle(x.caseId))}</td>
        <td class="num">${x.attempts}</td>
        <td class="num">${scoreText(x.avg)}</td>
        <td class="num ${low(x.zoneRate) ? "warn" : ""}">${pctText(x.zoneRate)}</td>
        <td class="num ${low(x.statusRate) ? "warn" : ""}">${pctText(x.statusRate)}</td>
        <td class="num ${low(x.signRate) ? "warn" : ""}">${pctText(x.signRate)}</td>
        <td class="num">${pctText(x.passRate)}</td>
      </tr>`;
    }).join("");
    const errors = st.errors.length ? st.errors.slice(0, 10).map((e) => `<div class="error-row">
      <div class="er-ic">!</div>
      <div class="er-main"><b>${esc(e.studentName)} · ${esc(caseTitle(e.caseId))}</b>
        <span>${esc(wrongSummary(e.detail))} · ${fmtTime(e.at)}</span></div>
      <div class="er-score">${e.score}</div>
    </div>`).join("") : `<div class="empty-inline"><b>没有不及格记录</b>当前作业全部达到及格线。</div>`;

    return head + metrics + `<div class="grid-2">
      <div class="panel-card">
        <div class="panel-h"><h3>学生完成情况</h3><span class="sub">按人</span></div>
        <div class="table-wrap"><table class="data-table">
          <thead><tr><th>姓名</th><th class="num">完成</th><th class="num">均分</th><th class="num">最近提交</th><th>进度</th></tr></thead>
          <tbody>${studentRows}</tbody></table></div>
      </div>
      <div class="panel-card">
        <div class="panel-h"><h3>错题与讲评</h3><span class="sub">不及格优先</span></div>
        ${errors}
      </div>
    </div>
    <div class="panel-card">
      <div class="panel-h"><h3>逐例分析</h3><span class="sub">定位 / 判读 / 征象三段得分率</span></div>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>病例</th><th class="num">提交</th><th class="num">均分</th><th class="num">定位</th><th class="num">判读</th><th class="num">征象</th><th class="num">及格率</th></tr></thead>
        <tbody>${caseRows}</tbody></table></div>
      <p class="note" style="margin-top:9px">低于 60% 的格子标为琥珀色。定位题接受该病例任一异常分区；判读题按学生所选分区的真实状态判分；征象题按命中数减错选计分。</p>
    </div>`;
  }

  function wrongSummary(d) {
    if (!d) return "无作答明细";
    const parts = [];
    if (!d.zoneOk) parts.push("定位错误");
    if (!d.statusOk) parts.push("状态判断错误");
    if (typeof d.signRatio === "number" && d.signRatio < 1) parts.push(`征象 ${Math.round(d.signRatio * 100)}%`);
    return parts.join(" · ") || "全部正确";
  }

  /* ---------------- 学生端 ---------------- */

  function studentJoinHTML() {
    const db = RC.read();
    const first = RC.activeClass() || db.classes[0];
    const code = S.join.code || (first ? first.code : "");
    return `<div class="page-head">
      <div><div class="eyebrow">STUDENT · JOIN</div><h1>学生端 · 加入班级</h1>
      <p>向教师索取班级码，填写姓名即可加入；不需要注册，答题记录只在本机浏览器。</p></div>
    </div>
    <div class="grid-2">
      <div class="panel-card">
        <div class="panel-h"><h3>加入班级</h3><span class="sub">班级码 + 姓名</span></div>
        <div class="form-grid">
          <div class="field full"><label for="joinName">姓名</label>
            <input id="joinName" value="${esc(S.join.name)}" maxlength="20" placeholder="例如：张同学"></div>
          <div class="field full"><label for="joinCode">班级码</label>
            <input id="joinCode" value="${esc(code)}" maxlength="12" placeholder="RC-XXXX" style="font-family:var(--mono);letter-spacing:.06em"></div>
        </div>
        <div class="form-actions">
          <button class="btn solid" data-act="join-class">加入班级</button>
          ${first ? `<span class="note">本机已有班级：<b class="mono">${esc(first.code)}</b></span>` : ""}
        </div>
      </div>
      <div class="panel-card">
        <div class="panel-h"><h3>学生会看到什么</h3><span class="sub">考核模式</span></div>
        <ul class="plain-list">
          <li>作业按病例逐例作答：先定位异常分区，再判断状态，最后选征象。</li>
          <li>提交前病例标题与分区颜色隐藏，避免直接从界面读出答案。</li>
          <li>提交后立即给分，并解锁分区所见、系统阅片与出处对照。</li>
          <li>低于 80 分的病例进入错题本，可重做；重做会保留历史记录。</li>
        </ul>
        <p class="note" style="margin-top:12px">教师还没建班？请先切到教师端创建班级，或载入演示班级。</p>
      </div>
    </div>`;
  }

  function studentHeroHTML(cls, stu) {
    return `<div class="student-hero">
      <div class="avatar">${esc(stu.name.slice(0, 1))}</div>
      <div class="sh-main"><h2>${esc(stu.name)} · 学生端</h2>
        <p>${esc(cls.name)} · ${esc(cls.teacher)} · 加入于 ${fmtTime(stu.joinedAt)}</p></div>
      <span class="sh-code">${esc(cls.code)}</span>
      <button class="btn sm" data-act="role" data-role="teacher">切到教师端</button>
      <button class="btn sm ghost" data-act="leave-class">退出班级</button>
    </div>`;
  }

  function studentTabsHTML() {
    const tabs = [
      ["home", "我的作业"],
      ["qa", "影像问答"],
      ["coach", "读片陪练"],
      ["quiz", "自测出题"],
      ["group", "互助小组"],
    ];
    return `<div class="student-tabs">${tabs.map(([id, label]) =>
      `<button data-student-tab="${id}" class="${S.studentTab === id ? "on" : ""}">${label}</button>`).join("")}</div>`;
  }

  function studentHTML() {
    const cls = RC.activeClass();
    const stu = RC.activeStudent();
    if (!cls || !stu) return studentJoinHTML();
    let body = "";
    if (S.studentTab === "home") body = studentHomeHTML();
    else if (S.studentTab === "group") body = studentGroupHTML(cls, stu);
    else body = `<div class="empty-state"><b>正在载入影像实验室…</b></div>`;
    const heads = {
      home: ["学生端 · 我的作业", "先自己读片，再提交；系统只对照库内逐区标注评分，不评价临床诊断。"],
      qa: ["学生端 · 影像问答", "在 21 例胸片库内检索；每个结论给影像区域定位与文献溯源两条引用。"],
      coach: ["学生端 · 读片陪练", "按定位、判读、征象、对照四步练习；提示只给方法，不直接给答案。"],
      quiz: ["学生端 · 自测出题", "从库内规则题中自建试卷；交卷后逐题对照影像位置与文献来源。"],
      group: ["学生端 · 互助小组", "按主题加入小组，在组内论坛提问、回复与标记解决。"],
    };
    const head = heads[S.studentTab] || heads.home;
    return `<div class="page-head">
      <div><div class="eyebrow">STUDENT CONSOLE</div><h1>${head[0]}</h1>
      <p>${head[1]}</p></div>
    </div>
    ${studentHeroHTML(cls, stu)}
    ${studentTabsHTML()}
    <div id="studentTabBody">${body}</div>`;
  }

  function studentHomeHTML() {
    const cls = RC.activeClass();
    const stu = RC.activeStudent();
    if (!cls || !stu) return studentJoinHTML();
    const st = RC.studentStats(cls.id, stu.id);
    const metrics = `<div class="metric-grid">
      <div class="metric"><b>${st.assignments.length}</b><span>作业</span><em>来自 ${esc(cls.name)}</em></div>
      <div class="metric"><b>${st.submitted}</b><span>已完成病例</span><em>共 ${st.cells} 例</em></div>
      <div class="metric"><b>${scoreText(st.avg)}</b><span>平均分</span><em>满分 100</em></div>
      <div class="metric"><b>${st.errors.length}</b><span>待重练</span><em>低于 80 分</em></div>
    </div>`;
    const assignments = st.assignments.length ? `<div class="assign-list">${st.assignments.map((x) => {
      const a = x.assignment;
      const label = x.completed >= x.total ? "复习" : (x.completed ? "继续" : "开始");
      return `<div class="assign-card">
        <div class="ac-top"><div><h4>${esc(a.title)}</h4>
          <div class="ac-meta"><span>${a.caseIds.length} 例</span><span>截止 ${esc(a.due || "待定")}</span><span>及格 ${a.passScore}</span></div></div>
          <span class="badge ${x.completed >= x.total ? "ok" : "info"}">${x.completed}/${x.total}</span></div>
        ${a.note ? `<div class="ac-note">${esc(a.note)}</div>` : ""}
        <div class="ac-prog" style="margin-top:9px">
          <div class="lbl"><span>完成进度</span><span>${x.total ? Math.round(x.completed / x.total * 100) : 0}%</span></div>
          ${progressBar(x.completed, x.total, x.completed < x.total)}
        </div>
        <div class="ac-foot">
          <span class="mini-chip">均分 ${scoreText(x.avg)}</span>
          <span class="mini-chip">最近 ${fmtTime(x.lastAt)}</span>
          <span class="spacer"></span>
          <a class="btn sm primary" href="clinic.html?task=${encodeURIComponent(a.id)}&student=${encodeURIComponent(stu.id)}">${label} →</a>
        </div>
      </div>`;
    }).join("")}</div>` : `<div class="empty-inline"><b>还没有作业</b>等教师布置后再来。</div>`;
    const errors = st.errors.length ? st.errors.slice(0, 10).map((e) => `<div class="error-row">
      <div class="er-ic">!</div>
      <div class="er-main"><b>${esc(caseTitle(e.caseId))}</b>
        <span>${esc(wrongSummary(e.detail))} · ${fmtTime(e.at)}</span></div>
      <div class="er-score">${e.score}</div>
      <a class="btn sm" href="clinic.html?task=${encodeURIComponent(e.assignmentId)}&student=${encodeURIComponent(stu.id)}&case=${encodeURIComponent(e.caseId)}">重练</a>
    </div>`).join("") : `<div class="empty-inline"><b>没有待重练的病例</b>完成作业后，低于 80 分的病例会自动出现在这里。</div>`;

    return `${metrics}
    <div class="grid-2">
      <div class="panel-card">
        <div class="panel-h"><h3>待完成作业</h3><span class="sub">${st.assignments.length} 份</span></div>
        ${assignments}
      </div>
      <div class="stack">
        <div class="panel-card">
          <div class="panel-h"><h3>错题本</h3><span class="sub">${st.errors.length} 条</span></div>
          ${errors}
        </div>
        <div class="panel-card">
          <div class="panel-h"><h3>最近作答</h3><span class="sub">最新 8 条</span></div>
          ${st.attempts.length ? `<div class="table-wrap"><table class="data-table">
            <thead><tr><th>病例</th><th class="num">得分</th><th class="num">时间</th></tr></thead>
            <tbody>${st.attempts.slice().sort((a, b) => String(b.at).localeCompare(String(a.at))).slice(0, 8).map((r) =>
              `<tr><td class="name">${esc(caseTitle(r.caseId))}</td><td class="num ${r.score < 60 ? "warn" : "ok"}">${r.score}</td><td class="num muted">${fmtTime(r.at)}</td></tr>`).join("")}</tbody>
          </table></div>` : `<div class="empty-inline"><b>还没有作答</b>从左侧作业开始。</div>`}
        </div>
      </div>
    </div>`;
  }


  /* ---------------- 互助小组 ---------------- */

  function groupCardHTML(g, isTeacher) {
    const joined = isTeacher ? true : !!g.joined;
    return `<article class="group-card">
      <div class="gc-h"><b>${esc(g.name)}</b>
        <span class="badge ${isTeacher ? "info" : (joined ? "ok" : "info")}">${isTeacher ? "班级小组" : (joined ? "已加入" : "未加入")}</span></div>
      <p>${esc(g.topic || "未填写主题")}</p>
      ${g.note ? `<div class="gc-note">${esc(g.note)}</div>` : ""}
      <div class="gc-stats">
        <span>${g.stats.members} 成员</span><span>${g.stats.posts} 帖</span>
        <span class="${g.stats.unresolved ? "warn" : ""}">${g.stats.unresolved} 待解决</span>
        <span>最近 ${fmtTime(g.stats.lastAt)}</span>
      </div>
      <div class="gc-foot">
        <button class="btn sm solid" data-group-open="${esc(g.id)}">进入论坛 →</button>
        ${!isTeacher && !joined ? `<button class="btn sm" data-group-join="${esc(g.id)}">加入小组</button>` : ""}
        ${isTeacher ? `<button class="btn sm ghost" data-group-del="${esc(g.id)}">删除小组</button>` : ""}
      </div>
    </article>`;
  }

  function groupCreateHTML(isTeacher) {
    return `<div class="panel-card">
      <div class="panel-h"><h3>${isTeacher ? "创建班级小组" : "发起一个学习小组"}</h3><span class="sub">本机保存</span></div>
      <div class="form-grid">
        <div class="field"><label for="groupName">小组名称</label>
          <input id="groupName" maxlength="24" placeholder="例如：肺野读片互助组"></div>
        <div class="field"><label for="groupTopic">讨论主题</label>
          <input id="groupTopic" maxlength="40" placeholder="例如：气腔影与正常对照"></div>
        <div class="field full"><label for="groupNote">小组说明（可选）</label>
          <input id="groupNote" maxlength="160" placeholder="例如：先定位，再描述密度与边界"></div>
      </div>
      <div class="form-actions"><button class="btn solid" data-group-create>创建小组</button>
        ${isTeacher ? `<button class="btn" data-group-seed>载入演示小组与帖子</button>` : ""}</div>
    </div>`;
  }

  function postCaseHTML(post) {
    const c = caseById(post.caseId);
    if (!c) return "";
    return `<a class="post-case" href="clinic.html?case=${encodeURIComponent(c.id)}" target="_blank" rel="noopener">
      <img src="../${esc(c.image)}" alt="${esc(c.title)}" loading="lazy">
      <div><b>${esc(c.id)} · ${esc(c.title)}</b><span>关联病例 · 点击在阅片台打开</span></div>
    </a>`;
  }

  function postRowHTML(p) {
    return `<button class="post-row" data-post-open="${esc(p.id)}">
      <div class="pr-main"><b>${esc(p.title)}</b>
        <span>${esc(p.authorName)} · ${fmtTime(p.updatedAt || p.createdAt)} · ${p.replyCount} 回复</span></div>
      <span class="badge ${p.status === "resolved" ? "ok" : "warn"}">${p.status === "resolved" ? "已解决" : "待解决"}</span>
    </button>`;
  }

  function postDetailHTML(p, cls, stu, isTeacher) {
    const canReply = !isTeacher && p.groupJoined;
    return `<div class="post-detail">
      <div class="post-detail-h">
        <button class="btn sm" data-post-back>← 返回帖子列表</button>
        <div class="spacer"></div>
        <button class="btn sm" data-post-resolve="${esc(p.id)}">${p.status === "resolved" ? "重新打开" : "标记已解决"}</button>
        ${isTeacher ? `<button class="btn sm ghost" data-post-delete="${esc(p.id)}">删除帖子</button>` : ""}
      </div>
      <div class="post-head">
        <span class="badge ${p.status === "resolved" ? "ok" : "warn"}">${p.status === "resolved" ? "已解决" : "待解决"}</span>
        <h3>${esc(p.title)}</h3>
        <p>${esc(p.authorName)} · ${fmtTime(p.createdAt)} · ${esc(p.groupName)}</p>
      </div>
      <div class="post-body">${esc(p.body)}</div>
      ${postCaseHTML(p)}
      <div class="post-replies">
        <div class="panel-h"><h4>回复 · ${p.replyCount}</h4><span class="sub">组内可见</span></div>
        ${p.replies.length ? p.replies.map((r) => `<div class="reply-row">
          <div class="reply-avatar">${esc((r.authorName || "?").slice(0, 1))}</div>
          <div><b>${esc(r.authorName)}</b><span>${fmtTime(r.at)}</span><p>${esc(r.body)}</p></div>
        </div>`).join("") : `<div class="empty-inline"><b>还没有回复</b>把你的读片思路或分区框发出来。</div>`}
      </div>
      ${canReply ? `<div class="reply-form">
        <label for="replyBody">写回复</label>
        <textarea id="replyBody" maxlength="600" placeholder="例如：我会先看肋膈角是否变钝，再看空气支气管征；最后回到该区库内标注。"></textarea>
        <div class="form-actions"><button class="btn solid" data-reply-submit="${esc(p.id)}">发布回复</button>
          <span class="note">只在本机保存；请勿填写真实患者信息。</span></div>
      </div>` : `<div class="note" style="margin-top:10px">${isTeacher ? "教师可查看与整理帖子。" : "加入小组后可以回复。"}</div>`}
    </div>`;
  }

  function forumHTML(cls, stu, group, isTeacher) {
    const joined = !!(stu && (group.memberIds || []).includes(stu.id));
    const allPosts = RC.postsFor(cls.id, group.id, S.groupFilter, stu ? stu.id : "");
    const detail = S.postId ? RC.postsFor(cls.id, group.id, "all", stu ? stu.id : "").find((p) => p.id === S.postId) : null;
    const filters = [
      ["all", "最新"], ["open", "待解决"], ["mine", "我的参与"], ["resolved", "已解决"],
    ];
    return `<div class="forum">
      <div class="forum-head">
        <button class="btn sm" data-group-back>← 小组列表</button>
        <div class="spacer"></div>
        ${!isTeacher && !joined ? `<button class="btn sm solid" data-group-join="${esc(group.id)}">加入小组</button>` : ""}
        ${!isTeacher && joined ? `<button class="btn sm ghost" data-group-leave="${esc(group.id)}">退出小组</button>` : ""}
      </div>
      <div class="forum-title"><div><span class="lab-kind">互助小组 · 组内论坛</span>
        <h3>${esc(group.name)}</h3><p>${esc(group.topic || "")} · ${group.memberIds.length} 成员 · ${allPosts.length} 帖</p></div>
        <span class="badge ${allPosts.filter((p) => p.status !== "resolved").length ? "warn" : "ok"}">
          ${allPosts.filter((p) => p.status !== "resolved").length} 待解决</span></div>
      ${detail ? postDetailHTML(Object.assign({}, detail, { groupJoined: joined }), cls, stu, isTeacher) : `
        ${!isTeacher && joined ? `<div class="post-form">
          <div class="panel-h"><h4>向组内论坛提问</h4><span class="sub">先搜一下有没有同类问题</span></div>
          <div class="form-grid">
            <div class="field full"><label for="postTitle">问题标题</label>
              <input id="postTitle" maxlength="60" placeholder="例如：CASE-007 下肺野密度增高，实变还是积液？"></div>
            <div class="field full"><label for="postBody">问题描述</label>
              <textarea id="postBody" maxlength="1200" placeholder="写清你看到的征象、分区框、已查过的出处；不要填真实患者信息。"></textarea></div>
            <div class="field"><label for="postCase">关联病例（可选）</label>
              <select id="postCase"><option value="">不关联病例</option>
                ${allCases().map((c) => `<option value="${esc(c.id)}">${esc(c.id)} · ${esc(c.title)}</option>`).join("")}
              </select></div>
          </div>
          <div class="form-actions"><button class="btn solid" data-post-submit>发布到组内论坛</button>
            <span class="note">组内成员可见；本机保存。</span></div>
        </div>` : ""}
        ${!isTeacher && !joined ? `<div class="empty-inline"><b>先加入小组</b>加入后才能发帖与回复。</div>` : ""}
        <div class="post-filters">${filters.map(([id, label]) =>
          `<button class="${S.groupFilter === id ? "on" : ""}" data-group-filter="${id}">${label}</button>`).join("")}</div>
        <div class="post-list">${allPosts.length ? allPosts.map(postRowHTML).join("") :
          `<div class="empty-inline"><b>这个小组还没有帖子</b>${!isTeacher && joined ? "把你的第一个问题发出来。" : "等待学生提问。"}</div>`}</div>
      `}
    </div>`;
  }

  function studentGroupHTML(cls, stu) {
    const groups = RC.groupsFor(cls.id, stu.id);
    if (S.groupId) {
      const g = groups.find((x) => x.id === S.groupId);
      if (g) return forumHTML(cls, stu, g, false);
      S.groupId = "";
      S.postId = "";
    }
    return `<div class="lab-head">
      <div><div class="eyebrow">PEER SUPPORT</div><h2>班级互助小组</h2>
      <p>按主题加入小组，在组内论坛提问、回复、标记已解决；帖子可关联 21 例胸片。</p></div>
      <span class="lab-scope">${groups.length} 个小组</span>
    </div>
    ${groupCreateHTML(false)}
    <div class="group-grid">${groups.length ? groups.map((g) => groupCardHTML(g, false)).join("") :
      `<div class="empty-inline"><b>还没有小组</b>可以自己发起一个，或等教师创建。</div>`}</div>`;
  }

  function teacherGroupHTML(cls) {
    const groups = RC.groupsFor(cls.id, "");
    if (S.groupId) {
      const g = groups.find((x) => x.id === S.groupId);
      if (g) return forumHTML(cls, null, g, true);
      S.groupId = "";
      S.postId = "";
    }
    const totalPosts = groups.reduce((n, g) => n + g.stats.posts, 0);
    const unresolved = groups.reduce((n, g) => n + g.stats.unresolved, 0);
    return `<div class="panel-card">
      <div class="panel-h"><h3>小组与组内论坛</h3><span class="sub">${groups.length} 组 · ${totalPosts} 帖 · ${unresolved} 待解决</span></div>
      <p>学生按主题加入小组，在组内论坛提问；教师可查看帖子、标记解决或删除。数据只在本机浏览器。</p>
    </div>
    ${groupCreateHTML(true)}
    <div class="group-grid">${groups.length ? groups.map((g) => groupCardHTML(g, true)).join("") :
      `<div class="empty-inline"><b>还没有小组</b>创建小组，或载入演示小组与帖子。</div>`}</div>`;
  }

  /* ---------------- 渲染 ---------------- */

  function render() {
    const main = $("#classroomMain");
    if (!main) return;
    $$("#roleSwitch button").forEach((b) => b.classList.toggle("on", b.dataset.role === S.role));
    if (!S.role) {
      main.innerHTML = gateHTML();
      $("#barNote").textContent = "班级与答题记录只存在本机浏览器";
      return;
    }
    if (S.role === "teacher") {
      main.innerHTML = teacherHTML();
      $("#barNote").textContent = "教师端 · 建班、布置作业、看学情";
    } else {
      main.innerHTML = studentHTML();
      $("#barNote").textContent = "学生端 · 作业、影像问答、陪练、自测与互助小组";
      if (["qa", "coach", "quiz"].includes(S.studentTab) && window.RCLab) {
        window.RCLab.mount(S.studentTab, $("#studentTabBody"));
      }
    }
  }

  /* ---------------- 交互 ---------------- */

  function setRole(role) {
    if (role !== "teacher" && role !== "student") return;
    RC.setRole(role);
    S.role = role;
    S.groupId = "";
    S.postId = "";
    S.groupFilter = "all";
    render();
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function createClassFromSetup() {
    const name = ($("#className") && $("#className").value || S.setup.className).trim();
    const teacher = ($("#teacherName") && $("#teacherName").value || S.setup.teacherName).trim();
    if (!name) { toast("请填写班级名称"); return; }
    RC.createClass(name, teacher);
    S.role = "teacher";
    S.teacherTab = "overview";
    toast("班级已创建，班级码已生成");
    render();
  }

  function createAssignmentFromDraft() {
    const cls = RC.activeClass();
    if (!cls) return;
    const title = ($("#assignTitle") && $("#assignTitle").value || S.draft.title).trim();
    const due = ($("#assignDue") && $("#assignDue").value || S.draft.due);
    const note = ($("#assignNote") && $("#assignNote").value || S.draft.note).trim();
    if (!title) { toast("请填写作业标题"); return; }
    if (!S.draft.caseIds.length) { toast("至少选择 1 个病例"); return; }
    const res = RC.createAssignment({ classId: cls.id, title, due, note, caseIds: S.draft.caseIds });
    if (!res.ok) { toast(res.error); return; }
    S.draft = { title: "", due: RC.plusDays(7), note: "", caseIds: [] };
    S.analysisId = res.assignment.id;
    S.teacherTab = "analysis";
    toast(`已发布：${res.assignment.title}`);
    render();
  }

  function addStudentFromInput() {
    const cls = RC.activeClass();
    if (!cls) return;
    const el = $("#newStudentName");
    const name = el ? el.value.trim() : "";
    if (!name) { toast("请填写学生姓名"); return; }
    const res = RC.addStudent(cls.id, name);
    if (!res.ok) { toast(res.error); return; }
    toast(res.exists ? "该学生已在班级中" : `已添加：${name}`);
    render();
  }

  function seedAttempts() {
    const cls = RC.activeClass();
    if (!cls || !S.analysisId) return;
    const res = RC.seedDemoAttempts(cls.id, S.analysisId, allCases());
    if (!res.ok) { toast(res.error); return; }
    toast(`已生成 ${res.created} 条演示答题（仅本地）`);
    render();
  }

  function exportReport() {
    const cls = RC.activeClass();
    if (!cls || !S.analysisId) return;
    const st = RC.assignmentStats(cls.id, S.analysisId);
    if (!st) return;
    const a = st.assignment;
    const lines = [
      `# ${cls.name} · 胸片阅片作业报告`,
      "",
      `- 班级码：${cls.code}`,
      `- 教师：${cls.teacher}`,
      `- 作业：${a.title}`,
      `- 截止：${a.due || "待定"} · 及格线：${a.passScore}`,
      `- 生成时间：${new Date().toLocaleString("zh-CN")}`,
      "",
      "## 总体",
      `- 学生：${st.totals.students} 人`,
      `- 提交：${st.totals.submitted}/${st.totals.cells}（${pctText(st.totals.rate)}）`,
      `- 平均分：${scoreText(st.totals.avg)} · 及格率：${pctText(st.totals.passRate)}`,
      `- 定位得分率：${pctText(st.totals.zoneRate)} · 判读：${pctText(st.totals.statusRate)} · 征象：${pctText(st.totals.signRate)}`,
      "",
      "## 学生完成情况",
      ...st.students.map((s) => `- ${s.name}：${s.completed}/${s.total}，均分 ${scoreText(s.avg)}，最近 ${fmtTime(s.lastAt)}`),
      "",
      "## 逐例分析",
      ...st.cases.map((x) => `- ${caseTitle(x.caseId)}：提交 ${x.attempts}，均分 ${scoreText(x.avg)}，定位 ${pctText(x.zoneRate)}，判读 ${pctText(x.statusRate)}，征象 ${pctText(x.signRate)}`),
      "",
      "## 错题",
      ...(st.errors.length ? st.errors.map((e) => `- ${e.studentName} · ${caseTitle(e.caseId)}：${e.score} 分，${wrongSummary(e.detail)}`) : ["- 无不及格记录"]),
      "",
      "> 本报告由本地课堂记录生成，仅用于教学；分区为教学分区，不构成诊断意见。",
    ];
    download(`${cls.code}_${a.title}_班级报告.md`, lines.join("\n"));
    toast("班级报告已导出");
  }

  function bind() {
    document.addEventListener("click", (e) => {
      const stab = e.target.closest("[data-student-tab]");
      if (stab) {
        S.studentTab = stab.dataset.studentTab;
        S.groupId = "";
        S.postId = "";
        render();
        return;
      }

      const gopen = e.target.closest("[data-group-open]");
      if (gopen) { S.groupId = gopen.dataset.groupOpen; S.postId = ""; S.groupFilter = "all"; render(); return; }
      const gback = e.target.closest("[data-group-back]");
      if (gback) { S.groupId = ""; S.postId = ""; render(); return; }
      const gjoin = e.target.closest("[data-group-join]");
      if (gjoin) {
        const cls = RC.activeClass();
        const stu = RC.activeStudent();
        if (!cls || !stu) return;
        const res = RC.joinGroup(cls.id, gjoin.dataset.groupJoin, stu.id);
        toast(res.ok ? "已加入小组" : res.error);
        render();
        return;
      }
      const gleave = e.target.closest("[data-group-leave]");
      if (gleave) {
        if (!window.confirm("退出该小组？已发布的帖子会保留。")) return;
        const cls = RC.activeClass();
        const stu = RC.activeStudent();
        if (!cls || !stu) return;
        RC.leaveGroup(cls.id, gleave.dataset.groupLeave, stu.id);
        toast("已退出小组");
        render();
        return;
      }
      const gcreate = e.target.closest("[data-group-create]");
      if (gcreate) {
        const cls = RC.activeClass();
        if (!cls) return;
        const stu = RC.activeStudent();
        const name = ($("#groupName") && $("#groupName").value || "").trim();
        const topic = ($("#groupTopic") && $("#groupTopic").value || "").trim();
        const note = ($("#groupNote") && $("#groupNote").value || "").trim();
        if (!name) { toast("请填写小组名称"); return; }
        const res = RC.createGroup(cls.id, {
          name, topic, note,
          createdBy: stu ? stu.id : "teacher",
          studentId: stu ? stu.id : "",
        });
        if (!res.ok) { toast(res.error); return; }
        S.groupId = res.group.id;
        S.postId = "";
        toast(`已创建：${res.group.name}`);
        render();
        return;
      }
      const gseed = e.target.closest("[data-group-seed]");
      if (gseed) {
        const cls = RC.activeClass();
        if (!cls) return;
        const res = RC.seedDemoGroups(cls.id);
        if (!res.ok) { toast(res.error); return; }
        toast(res.exists ? "演示小组已存在" : `已载入 ${res.groups} 个小组与 ${res.created} 个帖子`);
        render();
        return;
      }
      const gdel = e.target.closest("[data-group-del]");
      if (gdel) {
        if (!window.confirm("删除该小组及其全部帖子？")) return;
        const cls = RC.activeClass();
        if (!cls) return;
        RC.deleteGroup(cls.id, gdel.dataset.groupDel);
        if (S.groupId === gdel.dataset.groupDel) { S.groupId = ""; S.postId = ""; }
        toast("已删除小组");
        render();
        return;
      }
      const gfilter = e.target.closest("[data-group-filter]");
      if (gfilter) { S.groupFilter = gfilter.dataset.groupFilter; render(); return; }

      const popen = e.target.closest("[data-post-open]");
      if (popen) { S.postId = popen.dataset.postOpen; render(); return; }
      const pback = e.target.closest("[data-post-back]");
      if (pback) { S.postId = ""; render(); return; }
      const psubmit = e.target.closest("[data-post-submit]");
      if (psubmit) {
        const cls = RC.activeClass();
        const stu = RC.activeStudent();
        if (!cls || !stu || !S.groupId) return;
        const title = ($("#postTitle") && $("#postTitle").value || "").trim();
        const body = ($("#postBody") && $("#postBody").value || "").trim();
        const caseId = ($("#postCase") && $("#postCase").value || "").trim();
        const res = RC.createPost({ classId: cls.id, groupId: S.groupId, studentId: stu.id, title, body, caseId });
        if (!res.ok) { toast(res.error); return; }
        S.postId = res.post.id;
        toast("问题已发布到组内论坛");
        render();
        return;
      }
      const rsubmit = e.target.closest("[data-reply-submit]");
      if (rsubmit) {
        const cls = RC.activeClass();
        const stu = RC.activeStudent();
        if (!cls || !stu) return;
        const body = ($("#replyBody") && $("#replyBody").value || "").trim();
        const res = RC.replyPost({ classId: cls.id, postId: rsubmit.dataset.replySubmit, studentId: stu.id, body });
        if (!res.ok) { toast(res.error); return; }
        toast("回复已发布");
        render();
        return;
      }
      const presolve = e.target.closest("[data-post-resolve]");
      if (presolve) {
        const cls = RC.activeClass();
        if (!cls) return;
        const post = RC.postsFor(cls.id, S.groupId, "all").find((p) => p.id === presolve.dataset.postResolve);
        if (!post) return;
        RC.setPostStatus(cls.id, post.id, post.status === "resolved" ? "open" : "resolved");
        toast(post.status === "resolved" ? "已重新打开" : "已标记解决");
        render();
        return;
      }
      const pdel = e.target.closest("[data-post-delete]");
      if (pdel) {
        if (!window.confirm("删除该帖子及其回复？")) return;
        const cls = RC.activeClass();
        if (!cls) return;
        RC.deletePost(cls.id, pdel.dataset.postDelete);
        S.postId = "";
        toast("已删除帖子");
        render();
        return;
      }

      const roleBtn = e.target.closest("[data-role]");
      if (roleBtn) { setRole(roleBtn.dataset.role); return; }

      const tab = e.target.closest("[data-teacher-tab]");
      if (tab) { S.teacherTab = tab.dataset.teacherTab; render(); return; }

      const asStudent = e.target.closest("[data-as-student]");
      if (asStudent) {
        const cls = RC.activeClass();
        if (cls && RC.setActiveStudent(cls.id, asStudent.dataset.asStudent)) {
          RC.setRole("student");
          S.role = "student";
          toast("已切换到该学生视角");
          render();
        }
        return;
      }

      const removeStudent = e.target.closest("[data-remove-student]");
      if (removeStudent) {
        const cls = RC.activeClass();
        if (!window.confirm("移除该学生及其答题记录？")) return;
        if (cls && RC.removeStudent(cls.id, removeStudent.dataset.removeStudent)) {
          toast("已移除学生及其答题记录");
          render();
        }
        return;
      }

      const analysis = e.target.closest("[data-analysis]");
      if (analysis) { S.analysisId = analysis.dataset.analysis; S.teacherTab = "analysis"; render(); return; }

      const studentTry = e.target.closest("[data-student-try]");
      if (studentTry) {
        const cls = RC.activeClass();
        if (!cls) return;
        const stu = RC.ensureStudent(cls.id, "教师试做");
        if (!stu) { toast("无法创建试做学生"); return; }
        RC.setRole("student");
        location.href = `clinic.html?task=${encodeURIComponent(studentTry.dataset.studentTry)}&student=${encodeURIComponent(stu.id)}`;
        return;
      }

      const del = e.target.closest("[data-del-assign]");
      if (del) {
        if (!window.confirm("删除该作业及其全部答题记录？")) return;
        const cls = RC.activeClass();
        if (cls && RC.deleteAssignment(cls.id, del.dataset.delAssign)) {
          if (S.analysisId === del.dataset.delAssign) S.analysisId = "";
          toast("已删除作业及其答题记录");
          render();
        }
        return;
      }

      const preset = e.target.closest("[data-preset]");
      if (preset) {
        const kind = preset.dataset.preset;
        if (kind === "all") S.draft.caseIds = allCases().map((c) => c.id);
        else if (kind === "clear") S.draft.caseIds = [];
        else S.draft.caseIds = RC.DEMO_CASES.filter((id) => caseById(id));
        $$("#casePicker input[type=checkbox]").forEach((box) => {
          box.checked = S.draft.caseIds.includes(box.value);
          const label = box.closest(".case-opt");
          if (label) label.classList.toggle("on", box.checked);
        });
        const count = $("#pickCount");
        if (count) count.textContent = `已选 ${S.draft.caseIds.length} 例`;
        return;
      }

      const act = e.target.closest("[data-act]");
      if (!act) return;
      const name = act.dataset.act;
      if (name === "role") { setRole(act.dataset.role); return; }
      if (name === "create-class") { createClassFromSetup(); return; }
      if (name === "demo-class") {
        RC.seedDemoClass();
        S.role = "teacher";
        S.teacherTab = "overview";
        toast("已载入演示班级与 1 份作业");
        render();
        return;
      }
      if (name === "copy-code") {
        const cls = RC.activeClass();
        if (cls) copyText(cls.code);
        return;
      }
      if (name === "add-student") { addStudentFromInput(); return; }
      if (name === "new-assignment") { S.teacherTab = "assign"; render(); return; }
      if (name === "create-assignment") { createAssignmentFromDraft(); return; }
      if (name === "seed-attempts") { seedAttempts(); return; }
      if (name === "export-report") { exportReport(); return; }
      if (name === "join-class") {
        const nameEl = $("#joinName");
        const codeEl = $("#joinCode");
        const res = RC.joinClass(codeEl ? codeEl.value : S.join.code, nameEl ? nameEl.value : S.join.name);
        if (!res.ok) { toast(res.error); return; }
        S.role = "student";
        toast(`已加入 ${res.class.name}`);
        render();
        return;
      }
      if (name === "leave-class") {
        RC.leaveClass();
        toast("已退出班级");
        render();
        return;
      }
    });

    document.addEventListener("input", (e) => {
      const id = e.target && e.target.id;
      if (!id) return;
      if (id === "className") S.setup.className = e.target.value;
      else if (id === "teacherName") S.setup.teacherName = e.target.value;
      else if (id === "assignTitle") S.draft.title = e.target.value;
      else if (id === "assignDue") S.draft.due = e.target.value;
      else if (id === "assignNote") S.draft.note = e.target.value;
      else if (id === "joinName") S.join.name = e.target.value;
      else if (id === "joinCode") S.join.code = e.target.value;
    });

    document.addEventListener("change", (e) => {
      if (e.target && e.target.id === "analysisSel") {
        S.analysisId = e.target.value;
        render();
        return;
      }
      if (e.target && e.target.matches("#casePicker input[type=checkbox]")) {
        const id = e.target.value;
        const set = new Set(S.draft.caseIds);
        if (e.target.checked) set.add(id); else set.delete(id);
        S.draft.caseIds = Array.from(set);
        const label = e.target.closest(".case-opt");
        if (label) label.classList.toggle("on", e.target.checked);
        const count = $("#pickCount");
        if (count) count.textContent = `已选 ${S.draft.caseIds.length} 例`;
      }
    });

  }

  /* ---------------- 课堂数据导出 / 导入 ---------------- */

  function exportClassroom() {
    const db = RC.read();
    if (!db.classes.length) { toast("本机还没有班级数据"); return; }
    const payload = {
      app: "RadioCheck",
      kind: "classroom-export",
      version: RC.VERSION,
      exported_at: new Date().toISOString(),
      data: db,
    };
    download(`RadioCheck_课堂数据_${new Date().toISOString().slice(0, 10)}.json`,
      JSON.stringify(payload, null, 2), "application/json;charset=utf-8");
    toast("课堂数据已导出 JSON");
  }

  function mergeClassroom(incoming) {
    const db = RC.read();
    (incoming.classes || []).forEach((ic) => {
      const c = db.classes.find((x) => x.code === ic.code);
      if (!c) { db.classes.push(ic); return; }
      (ic.students || []).forEach((s) => {
        if (!c.students.some((x) => x.name === s.name)) c.students.push(s);
      });
      (ic.assignments || []).forEach((a) => {
        const i = c.assignments.findIndex((x) => x.id === a.id);
        if (i >= 0) c.assignments[i] = a; else c.assignments.push(a);
      });
      (ic.groups || []).forEach((g) => {
        if (!c.groups.some((x) => x.name === g.name)) c.groups.push(g);
      });
    });
    (incoming.attempts || []).forEach((a) => {
      if (!db.attempts.some((x) => x.id === a.id)) db.attempts.push(a);
    });
    (incoming.posts || []).forEach((p) => {
      const cur = db.posts.find((x) => x.id === p.id);
      if (!cur) { db.posts.push(p); return; }
      (p.replies || []).forEach((r) => {
        if (!(cur.replies || []).some((x) => x.id === r.id)) cur.replies.push(r);
      });
    });
    if (!db.teacher.name && incoming.teacher) db.teacher = incoming.teacher;
    return db;
  }

  function importClassroom(file) {
    if (!file) return;
    const fr = new FileReader();
    fr.onload = () => {
      try {
        const j = JSON.parse(String(fr.result || "{}"));
        const data = j && j.data ? j.data : j;
        if (!data || !Array.isArray(data.classes)) throw new Error("不是课堂数据 JSON");
        RC.write(mergeClassroom(data));
        toast("已合并课堂数据，正在刷新");
        setTimeout(() => location.reload(), 600);
      } catch (e) {
        toast("导入失败：" + (e.message || e));
      }
    };
    fr.readAsText(file);
  }

  function bindTransfer() {
    const exp = $("#exportClassroom");
    if (exp) exp.addEventListener("click", exportClassroom);
    const imp = $("#importClassroom");
    if (imp) imp.addEventListener("change", (e) => {
      importClassroom(e.target.files && e.target.files[0]);
      e.target.value = "";
    });
  }

  async function boot() {
    S.role = RC.getRole();
    try {
      const qp = new URLSearchParams(location.search);
      const role = qp.get("role");
      if (role === "teacher" || role === "student") {
        RC.setRole(role);
        S.role = role;
      }
    } catch (e) { /* ignore */ }
    try {
      const r = await fetch("../data/chest/chest_reading.json", { cache: "no-cache" });
      if (r.ok) S.data = await r.json();
    } catch (e) { S.data = null; }
    bind();
    bindTransfer();
    render();
  }

  boot();
})();
