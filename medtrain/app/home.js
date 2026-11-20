/* 首页：角色化工作台 */
(function (YZ) {
  "use strict";
  const { esc, pct, clamp, uniq, icon, DB, state, progress, role, drillDone, avgScore, learnedCount, classAvg, sign, caseOf, claimsOf, modsOf, chains, taskDone, reviewedCount } = YZ;

  function todayPath() {
    const learned = learnedCount();
    const cards = progress.cards.length;
    const done = drillDone();
    const last = progress.last.signId ? sign(progress.last.signId) : null;
    const steps = [
      { n: "学", t: last ? `磨玻璃影之后：${last.name}` : "选一条征象，先看定义与易错点", st: learned ? "done" : "now" },
      { n: "迁", t: cards ? `${cards} 张迁移卡已存` : "换模态、换部位，还成立吗", st: cards ? "done" : learned ? "now" : "next" },
      { n: "练", t: done ? `${done} 例已练` : "在公开病例上四步作答", st: done ? "done" : cards ? "now" : "next" },
    ];
    return `<aside class="hero-path">
      <div class="hp-h">今日路径</div>
      ${steps.map((x, i) => `<div class="hp-step ${x.st}">
        <i>${x.st === "done" ? icon("check", 10) : i + 1}</i>
        <span><b>${x.n}</b>${esc(x.t)}</span>
      </div>`).join("")}
      <div class="hp-foot">按上次停留位置继续，不重置进度</div>
    </aside>`;
  }

  function hero() {
    const r = role();
    const greet = state.role === "student" ? "把一条知识，练成四种能力"
      : state.role === "teacher" ? "把一份病例，讲成一条证据链"
      : "把一次读片，留下可核对的依据";
    return `<section class="hero${state.role === "student" ? "" : " solo"}">
      <div class="hero-main">
        <div class="eyebrow">RADIOCHECK · TRACK B · 医学影像知识问答</div>
        <h1>${greet}</h1>
        <p>${r.desc}。知识、指南、病例、分区与双引用结论共用一套底座。</p>
        <div class="row wrap">
          <button class="btn primary lg" data-act="nav" data-view="${state.role === "student" ? "drill" : "apply"}">${icon("play", 16)} ${state.role === "student" ? "开始今日一例" : state.role === "teacher" ? "查看班级概览" : "打开病例工作台"}</button>
          <button class="btn ghost" data-act="nav" data-view="learn">${icon("search", 15)} 先查一个征象</button>
        </div>
      </div>
      ${state.role === "student" ? todayPath() : ""}
    </section>`;
  }

  function chainCard(item, meta, p, cls) {
    const ic = item.id === "learn" ? "book" : item.id === "transfer" ? "transfer" : item.id === "drill" ? "target" : "briefcase";
    return `<button class="chain ${cls}" data-act="nav" data-view="${item.id}">
      <div class="row spread"><span class="no">${item.no}</span><span class="ci">${icon(ic, 18)}</span></div>
      <b>${item.title}</b><p>${item.desc}</p>
      <div class="bar"><i style="width:${clamp(p, 0, 100)}%"></i></div>
      <div class="meta"><span>${meta}</span><span>${p}%</span></div>
    </button>`;
  }

  function chainProgress(id) {
    const learned = learnedCount(), cards = progress.cards.length, done = drillDone();
    if (id === "learn") return { p: pct(learned, DB.meta.counts.signs), meta: `${learned}/${DB.meta.counts.signs} 词条` };
    if (id === "transfer") return { p: pct(cards, 3), meta: `${cards} 张迁移卡` };
    if (id === "drill") {
      if (state.role === "teacher") return { p: pct(progress.assignments.length, 5), meta: `${progress.assignments.length} 项作业 · ${done} 例已练` };
      return { p: pct(done, DB.drills.length), meta: `${done}/${DB.drills.length} 例` };
    }
    if (state.role === "teacher") return { p: classAvg("apply"), meta: `班级应用均分 ${classAvg("apply")}` };
    if (state.role === "doctor") return { p: pct(reviewedCount(), 12), meta: `${reviewedCount()}/12 条已核验` };
    return { p: pct(taskDone(), progress.assignments.length || 1), meta: `${taskDone()}/${progress.assignments.length} 项任务` };
  }

  function statStrip() {
    const c = DB.meta.counts;
    return `<div class="stat-strip">
      <div class="stat"><b>${c.signs}</b><span>征象词条</span><i>描述性定义 · 有出处</i></div>
      <div class="stat"><b>${c.guidelines}</b><span>指南条款</span><i>适用条件单列</i></div>
      <div class="stat"><b>${c.cases}</b><span>公开病例</span><i>CC0 / CC BY 许可</i></div>
      <div class="stat"><b>${c.regions}</b><span>解剖分区</span><i>人工标注 · 非病灶分割</i></div>
      <div class="stat"><b>${c.dual}</b><span>双引用结论</span><i>空间 + 文献 · 1 条拦截</i></div>
    </div>`;
  }

  function radar(vals) {
    const cx = 100, cy = 100, r = 66;
    const angles = [-Math.PI / 2, 0, Math.PI / 2, Math.PI];
    const pts = vals.map((v, i) => [cx + Math.cos(angles[i]) * r * (v / 100), cy + Math.sin(angles[i]) * r * (v / 100)]);
    const poly = pts.map((p) => p.join(",")).join(" ");
    const labels = [["学", 0], ["迁", 1], ["练", 2], ["用", 3]];
    return `<svg class="radar" viewBox="0 0 200 200">
      ${[0.25, 0.5, 0.75, 1].map((k) => `<polygon points="${angles.map((a) => `${cx + Math.cos(a) * r * k},${cy + Math.sin(a) * r * k}`).join(" ")}" fill="none" stroke="#e4eef1"/>`).join("")}
      ${angles.map((a) => `<line x1="${cx}" y1="${cy}" x2="${cx + Math.cos(a) * r}" y2="${cy + Math.sin(a) * r}" stroke="#e4eef1"/>`).join("")}
      <polygon points="${poly}" fill="rgba(14,124,123,.18)" stroke="#0e7c7b" stroke-width="2"/>
      ${pts.map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="#0e7c7b"/>`).join("")}
      ${labels.map(([t, i]) => `<text x="${cx + Math.cos(angles[i]) * (r + 20)}" y="${cy + Math.sin(angles[i]) * (r + 20) + 4}" text-anchor="middle" font-size="11" fill="#657b89">${t}</text>`).join("")}
    </svg>`;
  }

  function topErrors() {
    const counter = {};
    Object.values(progress.drills).forEach((r) => (r.wrong || []).forEach((w) => { counter[w] = (counter[w] || 0) + 1; }));
    const seeded = [["实变", 14], ["磨玻璃影", 11], ["胸腔积液", 9], ["低回声结节", 8], ["气胸", 6], ["肺不张", 5]];
    seeded.forEach(([n, c]) => { if (!counter[n]) counter[n] = c; });
    return Object.entries(counter).sort((a, b) => b[1] - a[1]).map(([name, count]) => ({ name, count })).slice(0, 8);
  }

  function studentSide() {
    const next = DB.drills.find((d) => !progress.drills[d.id]) || DB.drills[0];
    return `<div class="card panel">
      <div class="panel-h"><h3>今日一例</h3><span class="sub">${next.modality.join(" / ")}</span></div>
      <img src="${next.image}" alt="" style="width:100%;height:130px;object-fit:cover;border-radius:10px;margin-bottom:10px">
      <b style="font-size:13.5px">${esc(next.title)}</b>
      <p class="small muted" style="margin:4px 0 10px">${esc(next.stem).slice(0, 56)}…</p>
      <button class="btn primary" style="width:100%" data-act="drill-start" data-id="${next.id}">${icon("play", 15)} 开始演练</button>
    </div>
    <div class="card panel">
      <div class="panel-h"><h3>能力画像</h3><span class="sub">本地记录</span></div>
      ${radar([clamp(pct(learnedCount(), 20), 8, 100), clamp(pct(progress.cards.length, 3), 5, 100), clamp(avgScore(), 5, 100), clamp(pct(drillDone(), 8), 5, 100)])}
      <div class="bars" style="margin-top:8px">
        <div class="bar-row"><span>学</span><div class="track"><i style="width:${pct(learnedCount(), 20)}%"></i></div><b>${learnedCount()}</b></div>
        <div class="bar-row"><span>迁</span><div class="track"><i style="width:${pct(progress.cards.length, 3)}%"></i></div><b>${progress.cards.length}</b></div>
        <div class="bar-row"><span>练</span><div class="track"><i style="width:${avgScore()}%"></i></div><b>${avgScore()}</b></div>
        <div class="bar-row"><span>用</span><div class="track"><i style="width:${pct(drillDone(), 8)}%"></i></div><b>${drillDone()}</b></div>
      </div>
    </div>
    <div class="notice"><span class="ni">${icon("alert", 15)}</span><div><b>使用边界</b> 平台只做教学对照，不输出诊断结论，不替代临床决策。</div></div>`;
  }

  function teacherSide() {
    return `<div class="card panel">
      <div class="panel-h"><h3>班级概览</h3><span class="sub">演示班级 · 32 人</span></div>
      <div class="row spread" style="margin-bottom:10px"><div class="kpi"><b>${classAvg("drill")}</b><span>演练均分</span></div><div class="kpi"><b>${classAvg("learn")}</b><span>知识均分</span></div></div>
      <div class="bars">
        <div class="bar-row"><span>学</span><div class="track"><i style="width:${classAvg("learn")}%"></i></div><b>${classAvg("learn")}</b></div>
        <div class="bar-row"><span>迁</span><div class="track"><i style="width:${classAvg("transfer")}%"></i></div><b>${classAvg("transfer")}</b></div>
        <div class="bar-row"><span>练</span><div class="track"><i style="width:${classAvg("drill")}%"></i></div><b>${classAvg("drill")}</b></div>
        <div class="bar-row"><span>用</span><div class="track"><i style="width:${classAvg("apply")}%"></i></div><b>${classAvg("apply")}</b></div>
      </div>
      <button class="btn" style="width:100%;margin-top:12px" data-act="nav" data-view="apply">${icon("users", 15)} 进入班级管理</button>
    </div>
    <div class="card panel">
      <div class="panel-h"><h3>待讲评</h3><span class="sub">按错题聚合</span></div>
      <div class="list">${topErrors().slice(0, 3).map((x) => `<div class="list-item"><div class="li-ic">${icon("alert", 14)}</div><div class="grow"><b>${esc(x.name)}</b><span>${x.count} 人次错选</span></div><span class="chip warn">讲评</span></div>`).join("") || '<p class="small muted">暂无错题记录，先让学生完成一次演练。</p>'}</div>
    </div>`;
  }

  function doctorSide() {
    const c = caseOf(state.caseId) || DB.cases[0];
    const claims = claimsOf(c.id);
    const dual = claims.filter((x) => x.cite_status === "dual").length;
    const broken = claims.filter((x) => x.cite_status === "broken").length;
    return `<div class="card panel">
      <div class="panel-h"><h3>最近病例</h3><span class="sub">${esc(c.modality.join("/"))}</span></div>
      <img src="${c.image}" alt="" style="width:100%;height:130px;object-fit:cover;border-radius:10px;margin-bottom:10px">
      <b style="font-size:13px">${esc(c.title)}</b>
      <p class="small muted" style="margin:4px 0 10px">${claims.length} 条分区结论 · ${dual} 条双引用${broken ? ` · <span style="color:#c2413a">${broken} 条拦截</span>` : ""}</p>
      <button class="btn primary" style="width:100%" data-act="nav" data-view="apply">${icon("stethoscope", 15)} 打开工作台</button>
    </div>
    <div class="card panel">
      <div class="panel-h"><h3>引用健康度</h3><span class="sub">全库</span></div>
      <div class="row spread"><div class="kpi"><b>${DB.meta.counts.dual}</b><span>双引用</span></div><div class="kpi"><b style="color:#c2413a">${DB.meta.counts.broken}</b><span>拦截</span></div><div class="kpi"><b>${reviewedCount()}</b><span>已核验</span></div></div>
      <div class="progress" style="margin-top:10px"><i style="width:${pct(DB.meta.counts.dual, DB.meta.counts.claims)}%"></i></div>
      <p class="tiny muted" style="margin-top:8px">摘录 sha256 与库内原文不一致时，结论不展示为可用证据。核验记录只存本机。</p>
    </div>`;
  }

  function studentPanel() {
    const last = progress.last.signId ? sign(progress.last.signId) : null;
    return `<div class="grid g2">
      <div class="card panel">
        <div class="panel-h"><h3>继续上次</h3><span class="sub">${last ? "知识卡" : "从推荐开始"}</span></div>
        ${last ? `<div class="row"><div class="li-ic">${icon("book", 16)}</div><div class="grow"><b>${esc(last.name)}</b><span class="small muted">${esc(last.body_part)} · ${modsOf(last).join("/")}</span></div><button class="btn sm" data-act="sign" data-id="${last.id}">继续</button></div>` : `<p class="small muted">还没有学习记录。先从「磨玻璃影」或「实变」开始。</p><button class="btn sm" data-act="sign" data-id="SIGN-001">打开磨玻璃影</button>`}
      </div>
      <div class="card panel">
        <div class="panel-h"><h3>实习任务</h3><span class="sub">${progress.assignments.length} 项</span></div>
        ${progress.assignments.slice(0, 2).map((a) => `<div class="row" style="padding:6px 0"><div class="grow"><b style="font-size:12.5px">${esc(a.title)}</b><div class="small muted">${a.count} 例 · 截止 ${esc(a.due)}</div></div><button class="btn sm" data-act="nav" data-view="apply">查看</button></div>`).join("")}
      </div>
    </div>`;
  }

  function teacherPanel() {
    const errors = topErrors();
    return `<div class="card panel">
      <div class="panel-h"><h3>本周教学动作</h3><span class="sub">从错题到讲评</span></div>
      <div class="grid g3">
        <div class="side-card"><h4>${icon("clipboard", 14)} 已布置</h4><div class="kpi"><b>${progress.assignments.length}</b><span>项作业</span></div><p class="tiny muted">覆盖 ${uniq(progress.assignments.flatMap((a) => a.cases || [])).length} 个病例/词条</p></div>
        <div class="side-card"><h4>${icon("chart", 14)} 班级均分</h4><div class="kpi"><b>${classAvg("drill")}</b><span>演练</span></div><p class="tiny muted">知识 ${classAvg("learn")} · 迁移 ${classAvg("transfer")}</p></div>
        <div class="side-card"><h4>${icon("alert", 14)} 高频错题</h4><div class="kpi"><b>${errors[0] ? errors[0].count : 0}</b><span>${errors[0] ? esc(errors[0].name) : "暂无"}</span></div><p class="tiny muted">可一键生成讲评清单</p></div>
      </div>
      <div class="divider"></div>
      <div class="row wrap"><button class="btn primary" data-act="nav" data-view="apply">${icon("users", 15)} 打开班级管理</button><button class="btn" data-act="nav" data-view="drill">${icon("target", 15)} 从题库布置</button><button class="btn" data-act="nav" data-view="learn">${icon("book", 15)} 备课查词条</button></div>
    </div>`;
  }

  function doctorPanel() {
    const recent = DB.cases.slice(0, 4);
    return `<div class="card panel">
      <div class="panel-h"><h3>读片入口</h3><span class="sub">按病例或按征象</span></div>
      <div class="case-grid case-grid-4">
        ${recent.map((c) => `<button class="case-card" data-act="case" data-id="${c.id}"><img src="${c.image}" alt=""><div class="cc"><b>${esc(c.title).slice(0, 16)}</b><span>${c.modality.join("/")} · ${esc(c.body_part)}</span></div></button>`).join("")}
      </div>
    </div>`;
  }

  function coreBanner() {
    return `<button class="core-banner" data-act="nav" data-view="ask">
      <span class="cb-k">核心功能</span>
      <b>多模态知识库问答</b>
      <span class="cb-d">影像区域 + 文献段落，缺证据就降级或拒答</span>
      <em>进入问答 ${icon("right", 13)}</em>
    </button>`;
  }

  function homeView() {
    return `${hero()}${coreBanner()}
      <div class="dash-grid">
        <div class="dash-main">${statStrip()}${state.role === "teacher" ? teacherPanel() : state.role === "doctor" ? doctorPanel() : studentPanel()}</div>
        <aside class="stack">${state.role === "student" ? studentSide() : state.role === "teacher" ? teacherSide() : doctorSide()}</aside>
      </div>
      <div class="sec-title"><h2>四个基本功能链条</h2><span>同一条学习/工作流的四段，按顺序推进</span></div>
      <div class="chain-grid">
        ${chains().map((item, i) => {
          const p = chainProgress(item.id);
          return chainCard(item, p.meta, p.p, ["student", "teacher", "doctor"][i % 3]);
        }).join("")}
      </div>`;
  }

  Object.assign(YZ, { homeView, topErrors, radar });
})(window.YZ);
