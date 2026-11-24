/* 用 · 角色分发 + 我的 + 关于 + 弹层 */
(function (YZ) {
  "use strict";
  const { esc, icon, DB, state, progress, save, role, sign, caseOf, claimsOf, regionsOf, docCite, spatialCite, today, pct, uniq, modsOf, drillDone, avgScore, learnedCount } = YZ;

  function applyView() {
    if (state.role === "teacher") return YZ.teacherApply();
    if (state.role === "doctor") return YZ.doctorApply();
    return YZ.studentApply();
  }

  /* ---------- 我的 ---------- */
  function meView() {
    const r = role();
    return `<div class="page-head">
      <div><div class="eyebrow">PROFILE · LOCAL RECORD</div><h1>我的记录</h1><p>所有学习与演练记录保存在本机浏览器，不上传。可导出为 Markdown / JSON。</p></div>
      <div class="page-actions"><button class="btn" data-act="export-json">${icon("download", 15)} 导出记录</button><button class="btn" data-act="nav" data-view="about">${icon("shield", 15)} 关于与合规</button></div>
    </div>
    <div class="profile" style="margin-bottom:16px">
      <div class="big">${r.mark}</div>
      <div class="grow"><h2>${r.name}端 · ${r.full}</h2><p>${r.desc}</p></div>
      <div class="row"><span class="chip solid">${DB.meta.version}</span><span class="chip">${state.device === "mobile" ? "移动视图" : "自适应视图"}</span></div>
    </div>
    <div class="grid g2">
      <div class="card panel">
        <div class="panel-h"><h3>切换角色</h3><span class="sub">同一套底座，不同外壳</span></div>
        <div class="grid g3">
          ${["student", "teacher", "doctor"].map((k) => `<button class="version-card ${state.role === k ? "on" : ""}" data-act="role" data-role="${k}" style="${state.role === k ? "border-color:var(--accent);background:var(--accent-soft)" : ""}"><b>${YZ.ROLES[k].name}端</b><span>${YZ.ROLES[k].full}</span></button>`).join("")}
        </div>
        <div class="divider"></div>
        <div class="panel-h"><h3>设备视图</h3><span class="sub">同一页面，两种布局</span></div>
        <div class="row"><button class="btn ${!YZ.isMobile() ? "primary" : ""}" data-act="device-set" data-device="auto">${icon("monitor", 15)} 桌面 / 自适应</button><button class="btn ${YZ.isMobile() ? "primary" : ""}" data-act="device-set" data-device="mobile">${icon("phone", 15)} 移动视图</button></div>
        <p class="tiny muted" style="margin-top:8px">移动视图在桌面浏览器中收进 430px 画框，便于现场对比；真实手机访问会自动使用移动布局。</p>
      </div>
      <div class="stack">
        <div class="card panel">
          <div class="panel-h"><h3>学习记录</h3><span class="sub">本地</span></div>
          <div class="row spread"><div class="kpi"><b>${learnedCount()}</b><span>词条</span></div><div class="kpi"><b>${progress.cards.length}</b><span>迁移卡</span></div><div class="kpi"><b>${drillDone()}</b><span>演练</span></div><div class="kpi"><b>${avgScore()}</b><span>均分</span></div></div>
        </div>
        <div class="card panel">
          <div class="panel-h"><h3>收藏与迁移卡</h3><span class="sub">${progress.bookmarks.length + progress.cards.length} 项</span></div>
          <div class="list">
            ${progress.bookmarks.slice(0, 3).map((id) => `<div class="list-item"><div class="li-ic">${icon("book", 14)}</div><div class="grow"><b>${esc((sign(id) || {}).name || id)}</b><span>收藏词条</span></div><button class="btn sm" data-act="sign" data-id="${id}">打开</button></div>`).join("")}
            ${progress.cards.slice(0, 3).map((c) => `<div class="list-item"><div class="li-ic">${icon("copy", 14)}</div><div class="grow"><b>${esc(c.title)}</b><span>迁移卡 · ${esc(c.date)}</span></div><button class="btn sm" data-act="card-view" data-id="${c.id}">查看</button></div>`).join("")}
            ${!progress.bookmarks.length && !progress.cards.length ? '<p class="small muted">还没有收藏或迁移卡。</p>' : ""}
          </div>
        </div>
        <div class="card panel">
          <div class="panel-h"><h3>本地数据</h3><span class="sub">可随时清空</span></div>
          <div class="row"><button class="btn" data-act="export-json">${icon("download", 14)} 导出 JSON</button><button class="btn" data-act="reset">${icon("trash", 14)} 清空记录</button></div>
          <p class="tiny muted" style="margin-top:8px">演示班级、题目与病例来自知识库构建产物；个人记录只存在 localStorage。</p>
        </div>
      </div>
    </div>`;
  }

  /* ---------- 关于 ---------- */
  function aboutView() {
    const c = DB.meta.counts;
    const versions = [
      ["通用自适应版", "桌面三栏 + 移动单列，自动响应", "app.html"],
      ["学生端 · 桌面", "四链条学习路径、演练、实习任务", "app.html?role=student&device=desktop"],
      ["学生端 · 移动", "单列卡片 + 底部导航 + 触控定位", "app.html?role=student&device=mobile"],
      ["教师端 · 桌面", "备课、组卷、错题讲评、课堂投屏", "app.html?role=teacher&device=desktop"],
      ["教师端 · 移动", "随时看班、布置与讲评清单", "app.html?role=teacher&device=mobile"],
      ["医生端 · 桌面", "读片演练、病例工作台、引用审计", "app.html?role=doctor&device=desktop"],
      ["医生端 · 移动", "床旁/读片室速查、核验与交班摘要", "app.html?role=doctor&device=mobile"],
    ];
    return `<div class="page-head"><div><div class="eyebrow">ABOUT · COMPLIANCE</div><h1>关于 RadioCheck</h1><p>一个知识底座，四个功能链条，三种角色外壳，两种设备形态。</p></div></div>
    <div class="about-hero">
      <h1>RadioCheck · 影像临床思维平台</h1>
      <p>面向医学影像教学与临床带教：把征象、指南条款、公开病例、解剖分区与双引用结论组织成一条可回看的证据链。平台只做描述性解释、条款对照与出处定位，<b>不输出诊断结论，不替代临床决策</b>。</p>
      <div class="flow">
        <div><b>01 学</b><span>征象是什么、怎么看、错在哪</span></div>
        <div><b>02 迁</b><span>换模态 / 部位 / 病种还成不成立</span></div>
        <div><b>03 练</b><span>定位 → 描述 → 征象 → 依据</span></div>
        <div><b>04 用</b><span>实习任务 / 班级教学 / 病例工作台</span></div>
      </div>
    </div>
    <div class="grid g2">
      <div class="card panel">
        <div class="panel-h"><h3>知识底座</h3><span class="sub">${DB.meta.builtAt} 构建</span></div>
        <div class="grid g3" style="gap:8px">
          ${[["征象", c.signs], ["指南条款", c.guidelines], ["公开病例", c.cases], ["解剖分区", c.regions], ["双引用结论", c.dual], ["可练题目", c.drills]].map(([k, v]) => `<div class="side-card" style="padding:10px"><div class="kpi"><b style="font-size:22px">${v}</b><span>${k}</span></div></div>`).join("")}
        </div>
        <div class="divider"></div>
        <p class="small muted">数据来自公开标准摘要、公开许可影像与人工标注。${c.broken} 条条款摘录与当前版本不一致，已在引用审计中拦截，不作为可用证据。</p>
      </div>
      <div class="card panel">
        <div class="panel-h"><h3>版本矩阵</h3><span class="sub">一套代码 · 多入口</span></div>
        <div class="version-grid">
          ${versions.map(([name, desc, href]) => `<a class="version-card" href="${href}"><b>${name}</b><span>${desc}</span></a>`).join("")}
        </div>
        <p class="tiny muted" style="margin-top:8px">角色与设备只改变外壳、导航与可见模块；检索、双线判断、演练计分与引用审计共用同一引擎。</p>
      </div>
    </div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card panel">
        <div class="panel-h"><h3>三角色差异</h3><span class="sub">不是三套代码</span></div>
        <table class="table matrix-table"><thead><tr><th>能力</th><th>学生</th><th>教师</th><th>医生</th></tr></thead><tbody>
          <tr><td>01 基础知识问答</td><td>学习 + 收藏</td><td>备课 + 对比</td><td>速查 + 出处</td></tr>
          <tr><td>02 临床知识迁移</td><td>迁移卡</td><td>设计迁移任务</td><td>跨场景鉴别</td></tr>
          <tr><td>03 真实病例演练</td><td>四步计分</td><td>组卷 + 投屏</td><td>四步读片</td></tr>
          <tr><td>04 真实场景应用</td><td>实习任务 / 报告</td><td>班级 / 错题 / 投屏</td><td>工作台 / 审计 / 交班</td></tr>
          <tr><td>Agent 运行回执</td><td>回答链路</td><td>判分链路</td><td>核验链路</td></tr>
          <tr><td>引用审计</td><td>只读</td><td>只读</td><td>完整表 + 拦截</td></tr>
        </tbody></table>
      </div>
      <div class="card panel">
        <div class="panel-h"><h3>合规边界</h3><span class="sub">赛道 B</span></div>
        <ul class="bullets warn">
          <li>不使用真实患者数据；病例均为 CC0 / CC BY / CC BY-SA / 公有领域公开影像。</li>
          <li>不做病灶检测、分割、自动测量；分区框是人工标注的解剖区。</li>
          <li>不输出诊断、分级或治疗建议；条款只作原文摘录与条件对照。</li>
          <li>每条结论要求空间锚点 + 文献锚点；缺一条降级，hash 不一致拦截。</li>
          <li>固定声明：仅用于教学与研究，不构成诊断意见，不替代临床决策。</li>
          <li>内容审核：规则校验 + AI 预审后入库；<b>正式落地运用前须经医学人员逐条审核签字</b>，未签字条目标注"待审核"。</li>
        </ul>
      </div>
    </div>
    <div class="card panel" style="margin-top:16px">
      <div class="panel-h"><h3>DeepWorks 落地映射</h3><span class="sub">知识库 → 技能 → 工作流 → Agent</span></div>
      <table class="table"><thead><tr><th>平台能力</th><th>本作品中的位置</th><th>证据</th></tr></thead><tbody>
        <tr><td>知识库</td><td>征象 / 指南 / 病例三库 + 双引用元数据</td><td>kb-import 导入包、kb.js 构建产物</td></tr>
        <tr><td>技能</td><td>征象抽取、双线对齐、演练判分、引用审计</td><td>本应用的四条链路 + 可复现测试</td></tr>
        <tr><td>工作流</td><td>本地五步编排：解析 → 语义检索 → 分区定位 → 组证据 → 引用自证；另有教学任务流（学 → 迁 → 练 → 用）</td><td><code>workflow.py</code> + <code>workflow.json</code> + 8 项单测；<code>/api/health</code> 报 <code>real_workflow=true</code></td></tr>
        <tr><td>Agent</td><td>把检索、对齐、计分结果汇总成一句可核对回答</td><td>双线判断卡、交班摘要</td></tr>
        <tr><td>多模态</td><td>公开影像 + 人工分区框；不接诊断模型</td><td>${c.regions} 个分区锚点</td></tr>
        <tr><td>多端外壳</td><td>同一引擎按角色与设备分发 7 个入口</td><td>app.html + 6 个版本入口</td></tr>
      </tbody></table>
      <p class="tiny muted" style="margin-top:8px">语义检索与五步工作流已在本地服务真实执行：<code>/api/health</code> 可核验 <code>semantic_search=true</code>、<code>real_workflow=true</code>，每次问答的完整链路见 <code>/api/trace/{run_id}</code> 与 <code>workflow.json</code>；DeepWorks 内的知识库导入与技能配置见交付附件。</p>
    </div>`;
  }

  /* ---------- 弹层 ---------- */
  function modalHTML() {
    const m = state.modal;
    if (!m) return "";
    if (m.type === "card") {
      return `<div class="modal-mask" data-act="modal-close"><div class="modal" data-stop="1"><h3>迁移卡</h3><div class="sub">${esc(m.title || "")}</div><textarea id="modalText">${esc(m.text || "")}</textarea><div class="mfoot"><button class="btn" data-act="modal-close">关闭</button><button class="btn" data-act="copy-modal">${icon("copy", 14)} 复制</button><button class="btn" data-act="download-modal">${icon("download", 14)} 下载</button><button class="btn primary" data-act="save-card">${icon("plus", 14)} 保存到记录</button></div></div></div>`;
    }
    if (m.type === "report") {
      return `<div class="modal-mask" data-act="modal-close"><div class="modal" data-stop="1"><h3>${esc(m.title || "学习报告")}</h3><div class="sub">可复制或下载为 Markdown</div><textarea id="modalText">${esc(m.text || "")}</textarea><div class="mfoot"><button class="btn" data-act="modal-close">关闭</button><button class="btn" data-act="copy-modal">${icon("copy", 14)} 复制</button><button class="btn primary" data-act="download-modal">${icon("download", 14)} 下载 .md</button></div></div></div>`;
    }
    if (m.type === "case") {
      const c = caseOf(m.id);
      if (!c) return "";
      return `<div class="modal-mask" data-act="modal-close"><div class="modal" data-stop="1" style="width:min(820px,100%)"><h3>${esc(c.title)}</h3><div class="sub">${c.modality.join(" / ")} · ${esc(c.body_part)} · ${esc(c.license)}</div><img src="${c.image}" alt="" style="width:100%;max-height:52vh;object-fit:contain;background:#0d1b21;border-radius:10px"><p class="small muted" style="margin-top:10px">${esc(c.description_public || "")}</p><p class="small" style="margin-top:6px">教学要点：${esc(c.teaching_note || "")}</p><div class="mfoot"><a class="btn" href="${esc(c.source_page)}" target="_blank" rel="noopener">${icon("external", 14)} 来源页</a><button class="btn primary" data-act="modal-close">关闭</button></div></div></div>`;
    }
    if (m.type === "confirm") {
      return `<div class="modal-mask" data-act="modal-close"><div class="modal" data-stop="1" style="width:min(420px,100%)"><h3>${esc(m.title || "确认")}</h3><div class="sub">${esc(m.text || "")}</div><div class="mfoot"><button class="btn" data-act="modal-close">取消</button><button class="btn primary" data-act="confirm-reset">确认清空</button></div></div></div>`;
    }
    return "";
  }

  function projectionHTML() {
    const p = state.projection;
    const d = YZ.DRILL.get(p.drillId);
    if (!d) return "";
    const opts = d.descOptions;
    return `<div class="projection">
      <div class="row spread"><div><div class="eyebrow" style="color:rgba(255,255,255,.55)">课堂投屏 · ${esc(d.title)}</div><h2 style="margin-top:6px">${esc(d.stem)}</h2></div><button class="btn" data-act="projection-exit">${icon("x", 15)} 退出投屏</button></div>
      <div class="popt">${opts.map((o, i) => `<div class="${p.showAnswer && o.correct ? "ok" : ""}">${String.fromCharCode(65 + i)}. ${esc(o.text)}${p.showAnswer && o.correct ? " ✓" : ""}</div>`).join("")}</div>
      <div class="pfoot"><span class="small" style="color:rgba(255,255,255,.55);margin-right:auto">先让学生判断，再揭示答案；不展示诊断结论。</span><button class="btn" data-act="projection-toggle">${p.showAnswer ? "隐藏答案" : "显示答案"}</button></div>
    </div>`;
  }

  Object.assign(YZ, { applyView, meView, aboutView, modalHTML, projectionHTML });
})(window.YZ);
