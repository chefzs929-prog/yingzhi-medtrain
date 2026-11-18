/* 用 · 教师端：班级管理 */
(function (YZ) {
  "use strict";
  const { esc, icon, DB, state, progress, save, pct, today, classAvg, dataBadge } = YZ;

  function teacherApply() {
    const tabs = [["overview", "班级概览"], ["assign", "作业编排"], ["errors", "错题分析"], ["projection", "课堂投屏"]];
    return `<div class="page-head">
      <div><div class="eyebrow">CHAIN 04 · TEACHING</div><h1>教 · 班级管理</h1><p>用同一套病例与错题数据备课、布置、讲评；课堂投屏只展示题干，不提前泄露答案。</p></div>
      <div class="page-actions"><button class="btn primary" data-act="teacher-report">${icon("download", 15)} 班级报告</button></div>
    </div>
    <div class="tabs">${tabs.map(([id, label]) => `<button class="${state.teacherTab === id ? "on" : ""}" data-act="teacher-tab" data-tab="${id}">${label}</button>`).join("")}</div>
    ${state.teacherTab === "overview" ? teacherOverview() : state.teacherTab === "assign" ? teacherAssign() : state.teacherTab === "errors" ? teacherErrors() : teacherProjection()}`;
  }

  function teacherOverview() {
    const avg = (k) => classAvg(k);
    return `<div class="stat-strip" style="margin-bottom:14px">
      <div class="stat"><b>${DB.mockClass.length}</b><span>班级人数</span>${dataBadge("demo")}</div>
      <div class="stat"><b>${avg("learn")}</b><span>知识均分</span><i>四链条</i></div>
      <div class="stat"><b>${avg("drill")}</b><span>演练均分</span><i>四步计分</i></div>
      <div class="stat"><b>${avg("transfer")}</b><span>迁移均分</span><i>迁移卡</i></div>
      <div class="stat"><b>${avg("apply")}</b><span>应用均分</span><i>任务完成</i></div>
    </div>
    <div class="grid g2">
      <div class="card panel">
        <div class="panel-h"><h3>学生进度</h3><span class="sub">按演练均分排序</span></div>
        <div class="students"><table class="table"><thead><tr><th>学生</th><th>学</th><th>迁</th><th>练</th><th>用</th><th>时长</th><th>最近</th></tr></thead><tbody>
          ${DB.mockClass.slice().sort((a, b) => b.drill - a.drill).map((s) => `<tr><td>${esc(s.name)}</td><td>${s.learn}</td><td>${s.transfer}</td><td><b>${s.drill}</b></td><td>${s.apply}</td><td>${s.minutes}m</td><td class="muted">${s.last}</td></tr>`).join("")}
        </tbody></table></div>
      </div>
      <div class="stack">
        <div class="card panel">
          <div class="panel-h"><h3>班级分布</h3><span class="sub">演练分数段</span></div>
          ${[["85—100", DB.mockClass.filter((s) => s.drill >= 85).length], ["60—84", DB.mockClass.filter((s) => s.drill >= 60 && s.drill < 85).length], ["0—59", DB.mockClass.filter((s) => s.drill < 60).length]].map(([k, v]) => `<div class="bar-row" style="grid-template-columns:70px 1fr 30px"><span>${k}</span><div class="track"><i style="width:${pct(v, DB.mockClass.length)}%"></i></div><b>${v}</b></div>`).join("")}
        </div>
        <div class="card panel">
          <div class="panel-h"><h3>本周建议</h3><span class="sub">从错题来</span></div>
          <ul class="bullets">${YZ.topErrors().slice(0, 3).map((e) => `<li>讲评「${esc(e.name)}」：${e.count} 人次错选，建议用一例对照 + 一条条款条件做 10 分钟微课。</li>`).join("")}</ul>
        </div>
      </div>
    </div>`;
  }

  function teacherAssign() {
    return `<div class="grid g2">
      <div class="card panel">
        <div class="panel-h"><h3>布置一项任务</h3><span class="sub">写入本地演示数据</span></div>
        <form class="form" id="assignForm">
          <div class="field"><label>任务名称</label><input name="title" required placeholder="例如：胸部急症：气腔影与气胸"></div>
          <div class="grid g2" style="gap:10px">
            <div class="field"><label>链条</label><select name="chain"><option value="drill">练 · 病例演练</option><option value="learn">学 · 词条学习</option><option value="transfer">迁 · 迁移卡</option></select></div>
            <div class="field"><label>截止日期</label><input name="due" placeholder="11-22" value="11-22"></div>
          </div>
          <div class="grid g2" style="gap:10px">
            <div class="field"><label>病例数</label><input name="count" type="number" min="1" max="8" value="2"></div>
            <div class="field"><label>病例组</label><select name="group">${DB.groups.map((g) => `<option value="${g.id}">${esc(g.name)}</option>`).join("")}</select></div>
          </div>
          <div class="field"><label>讲评提示</label><textarea name="note" placeholder="例如：先定位，再说征象，最后选依据。"></textarea></div>
          <button class="btn primary" type="submit">${icon("plus", 15)} 布置任务</button>
        </form>
      </div>
      <div class="card panel">
        <div class="panel-h"><h3>已布置</h3><span class="sub">${progress.assignments.length} 项</span></div>
        ${progress.assignments.map((a) => `<div class="assign" style="margin-bottom:9px"><div class="row spread"><h4>${esc(a.title)}</h4><span class="chip">${esc(a.chain)}</span></div><p>${a.count} 例 · 截止 ${esc(a.due)} · ${esc(a.note || "")}</p><div class="row"><button class="btn sm" data-act="assign-start" data-id="${a.id}">${icon("play", 13)} 预览</button><button class="btn sm ghost" data-act="assign-del" data-id="${a.id}">${icon("trash", 13)} 删除</button></div></div>`).join("") || '<p class="small muted">还没有布置任务。</p>'}
      </div>
    </div>`;
  }

  function teacherErrors() {
    const errs = YZ.topErrors();
    const max = Math.max.apply(null, errs.map((e) => e.count).concat([1]));
    return `<div class="grid g2">
      <div class="card panel">
        <div class="panel-h"><h3>高频错题</h3><span class="sub">本地记录 + 演示班级</span></div>
        <div class="bars">${errs.map((e) => `<div class="bar-row" style="grid-template-columns:96px 1fr 38px"><span>${esc(e.name)}</span><div class="track"><i style="width:${pct(e.count, max)}%"></i></div><b>${e.count}</b></div>`).join("")}</div>
        <div class="divider"></div>
        <button class="btn" data-act="copy-errors">${icon("copy", 14)} 生成讲评清单</button>
      </div>
      <div class="stack">
        <div class="card panel">
          <div class="panel-h"><h3>错题分布</h3><span class="sub">按部位</span></div>
          <div class="heat">${Array.from({ length: 48 }).map((_, i) => `<i data-l="${Math.max(1, Math.min(5, ((i * 7) % 5) + 1))}"></i>`).join("")}</div>
          <p class="tiny muted" style="margin-top:8px">演示热力：颜色越深表示该部位错题越集中。真实版本按班级记录聚合。</p>
        </div>
        <div class="card panel">
          <div class="panel-h"><h3>讲评建议</h3><span class="sub">可直接投屏</span></div>
          <ul class="bullets">${errs.slice(0, 4).map((e) => `<li>${esc(e.name)}：先让学生指出“它在图上哪儿”，再问“哪条依据能支撑”。</li>`).join("")}</ul>
        </div>
      </div>
    </div>`;
  }

  function teacherProjection() {
    return `<div class="card panel">
      <div class="panel-h"><h3>课堂投屏</h3><span class="sub">只显示题干，答案后置</span></div>
      <p class="small muted" style="margin-bottom:12px">选一道题进入全屏投屏。学生先定位/描述，教师再揭示答案与依据。</p>
      <div class="grid g3">
        ${DB.drills.slice(0, 6).map((d) => `<button class="version-card" data-act="projection" data-id="${d.id}"><b>${esc(d.title)}</b><span>${d.modality.join("/")} · ${esc(d.bodyPart)}</span></button>`).join("")}
      </div>
    </div>`;
  }

  function addAssignment(form) {
    const data = new FormData(form);
    const count = Math.max(1, Math.min(8, Number(data.get("count")) || 1));
    const group = data.get("group");
    let pool = DB.drills.filter((d) => {
      const g = DB.groups.find((x) => x.id === group);
      return g && (g.sign_ids || []).some((sid) => d.correctSigns.includes(sid));
    });
    if (!pool.length) pool = DB.drills.filter((d) => d.bodyPart === "胸部");
    const cases = pool.slice(0, count).map((d) => d.id);
    const a = {
      id: "A-" + Date.now().toString(36),
      title: String(data.get("title") || "未命名任务").slice(0, 40),
      chain: String(data.get("chain") || "drill"),
      count, due: String(data.get("due") || "待定"),
      note: String(data.get("note") || "").slice(0, 80),
      cases,
      createdAt: today(),
    };
    progress.assignments.unshift(a);
    save();
    YZ.toast("已布置：" + a.title);
    YZ.render();
  }

  function deleteAssignment(id) {
    progress.assignments = progress.assignments.filter((a) => a.id !== id);
    save();
    YZ.toast("已删除任务");
    YZ.render();
  }

  function startAssignment(id) {
    const a = progress.assignments.find((x) => x.id === id);
    if (!a) return;
    if (a.chain === "learn") {
      const sid = (a.cases || []).find((x) => String(x).startsWith("SIGN")) || "SIGN-001";
      state.signId = sid;
      YZ.go("learn");
      return;
    }
    if (a.chain === "transfer") {
      state.transferId = (a.cases || [])[0] || "SIGN-001";
      YZ.go("transfer");
      return;
    }
    const next = (a.cases || []).find((x) => !progress.drills[x]) || (a.cases || [])[0];
    if (next && DB.drills.some((d) => d.id === next)) YZ.startDrill(next);
    else YZ.go("drill");
  }

  function teacherReportText() {
    return [
      `# 影知 · 班级学习报告`,
      ``,
      `- 生成日期：${today()}`,
      `- 班级：演示班级 · ${DB.mockClass.length} 人`,
      `- 知识均分：${classAvg("learn")} · 迁移均分：${classAvg("transfer")} · 演练均分：${classAvg("drill")} · 应用均分：${classAvg("apply")}`,
      ``,
      `## 分数段`,
      `- 85—100：${DB.mockClass.filter((s) => s.drill >= 85).length} 人`,
      `- 60—84：${DB.mockClass.filter((s) => s.drill >= 60 && s.drill < 85).length} 人`,
      `- 0—59：${DB.mockClass.filter((s) => s.drill < 60).length} 人`,
      ``,
      `## 高频错题`,
      ...YZ.topErrors().map((e) => `- ${e.name}：${e.count} 人次`),
      ``,
      `## 已布置任务`,
      ...progress.assignments.map((a) => `- ${a.title}（${a.count} 例，截止 ${a.due}）`),
      ``,
      `> 班级数据为演示数据；平台不输出诊断结论。`,
    ].join("\n");
  }

  Object.assign(YZ, {
    teacherApply, addAssignment, deleteAssignment, startAssignment, teacherReportText,
  });
})(window.YZ);
