/* 用 · 学生端：实习任务 */
(function (YZ) {
  "use strict";
  const { esc, icon, DB, state, progress, drillDone, avgScore, learnedCount, pct, today } = YZ;

  function errorBook() {
    const rows = [];
    Object.entries(progress.drills).forEach(([id, r]) => (r.wrong || []).forEach((w) => rows.push({ w, id, score: r.score, date: r.date })));
    if (!rows.length) return '<p class="small muted">还没有错题。完成一次演练后，错因会自动记在这里。</p>';
    return rows.slice(0, 8).map((x) => `<div class="list-item"><div class="li-ic">${icon("alert", 14)}</div><div class="grow"><b>${esc(x.w)}</b><span>${esc((YZ.DRILL.get(x.id) || {}).title || x.id)} · ${esc(x.date || "")}</span></div><button class="btn sm" data-act="drill-start" data-id="${x.id}">重练</button></div>`).join("");
  }

  function studentApply() {
    const done = drillDone();
    const avg = avgScore();
    return `<div class="page-head">
      <div><div class="eyebrow">CHAIN 04 · REAL TASK</div><h1>用 · 实习任务</h1><p>把练习记录变成可交付的学习任务：完成情况、错题本、能力画像和一份可导出的学习报告。</p></div>
      <div class="page-actions"><button class="btn primary" data-act="report">${icon("download", 15)} 生成学习报告</button></div>
    </div>
    <div class="grid g2">
      <div class="card panel">
        <div class="panel-h"><h3>待完成任务</h3><span class="sub">${progress.assignments.length} 项</span></div>
        ${progress.assignments.map((a) => {
          const ids = a.cases || [];
          const finished = ids.filter((id) => progress.drills[id]).length;
          return `<div class="assign" style="margin-bottom:9px"><div class="row spread"><h4>${esc(a.title)}</h4><span class="chip ${finished >= a.count ? "ok" : ""}">${finished}/${a.count}</span></div><p>${esc(a.note || "")} · 截止 ${esc(a.due)}</p><div class="progress"><i style="width:${pct(finished, a.count)}%"></i></div><div class="row" style="margin-top:7px"><button class="btn sm primary" data-act="assign-start" data-id="${a.id}">${finished >= a.count ? "复习" : "继续"}</button></div></div>`;
        }).join("") || '<p class="small muted">暂无任务。</p>'}
      </div>
      <div class="stack">
        <div class="card panel">
          <div class="panel-h"><h3>能力画像</h3><span class="sub">按四链条</span></div>
          <div class="bars">
            <div class="bar-row"><span>学 · 词条</span><div class="track"><i style="width:${pct(learnedCount(), 20)}%"></i></div><b>${learnedCount()}</b></div>
            <div class="bar-row"><span>迁 · 迁移卡</span><div class="track"><i style="width:${pct(progress.cards.length, 3)}%"></i></div><b>${progress.cards.length}</b></div>
            <div class="bar-row"><span>练 · 均分</span><div class="track"><i style="width:${avg}%"></i></div><b>${avg}</b></div>
            <div class="bar-row"><span>用 · 完成</span><div class="track"><i style="width:${pct(done, 8)}%"></i></div><b>${done}</b></div>
          </div>
        </div>
        <div class="card panel">
          <div class="panel-h"><h3>错题本</h3><span class="sub">${Object.values(progress.drills).reduce((n, x) => n + (x.wrong || []).length, 0)} 条</span></div>
          ${errorBook()}
        </div>
      </div>
    </div>`;
  }

  function studentReportText() {
    const rows = Object.entries(progress.drills);
    return [
      `# RadioCheck · 学习报告`,
      ``,
      `- 生成日期：${today()}`,
      `- 角色：学生端`,
      `- 已学词条：${learnedCount()} / ${DB.meta.counts.signs}`,
      `- 迁移卡：${progress.cards.length}`,
      `- 完成演练：${rows.length} 例，平均 ${avgScore()} 分`,
      ``,
      `## 四链条记录`,
      `- 学：${progress.bookmarks.length} 个收藏，${learnedCount()} 个词条`,
      `- 迁：${progress.cards.length} 张迁移卡`,
      `- 练：${rows.map(([id, r]) => `${(YZ.DRILL.get(id) || {}).title || id}（${r.score} 分）`).join("；") || "暂无"}`,
      `- 用：${progress.assignments.length} 项实习任务`,
      ``,
      `## 错题与下一步`,
      ...(rows.flatMap(([id, r]) => (r.wrong || []).map((w) => `- ${(YZ.DRILL.get(id) || {}).title || id}：${w}`)).slice(0, 10)),
      ``,
      `> 本报告由本地学习记录生成，仅用于教学；不构成诊断意见。`,
    ].join("\n");
  }

  Object.assign(YZ, { studentApply, errorBook, studentReportText });
})(window.YZ);
