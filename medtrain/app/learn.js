/* 学 · 基础知识问答 */
(function (YZ) {
  "use strict";
  const { esc, icon, DB, state, progress, save, sign, signCases, signGuides, relatedSigns, modsOf, filteredSigns, searchSigns, traceLive, isMobile, toast } = YZ;

  function anatomySVG(active) {
    const hot = (id, x, y, w, h, label, tx, ty) =>
      `<rect class="hot ${active === id ? "on" : ""}" data-act="part" data-part="${id}" x="${x}" y="${y}" width="${w}" height="${h}" rx="8"><title>${label}</title></rect><text x="${tx}" y="${ty}" text-anchor="middle">${label}</text>`;
    return `<svg class="anatomy" viewBox="0 0 200 280" role="img" aria-label="人体部位导航">
      <ellipse class="body" cx="100" cy="34" rx="22" ry="25"/>
      <rect class="body" x="89" y="56" width="22" height="16" rx="5"/>
      <path class="body" d="M62 78 Q100 66 138 78 L145 150 Q140 180 130 190 L70 190 Q60 180 55 150 Z"/>
      <path class="body" d="M62 84 Q42 100 38 140 L30 196 Q28 208 36 210 Q44 212 46 200 L58 150 Z"/>
      <path class="body" d="M138 84 Q158 100 162 140 L170 196 Q172 208 164 210 Q156 212 154 200 L142 150 Z"/>
      <path class="body" d="M78 190 L74 258 Q73 268 82 268 Q90 268 91 258 L96 196 Z"/>
      <path class="body" d="M122 190 L126 258 Q127 268 118 268 Q110 268 109 258 L104 196 Z"/>
      ${hot("REG-HEAD-NECK", 76, 8, 48, 62, "头颈", 100, 22)}
      ${hot("REG-CHEST", 60, 76, 80, 54, "胸部", 100, 108)}
      <rect class="hot ${active === "REG-BREAST" ? "on" : ""}" data-act="part" data-part="REG-BREAST" x="72" y="94" width="22" height="20" rx="10"><title>乳腺</title></rect>
      <rect class="hot ${active === "REG-BREAST" ? "on" : ""}" data-act="part" data-part="REG-BREAST" x="106" y="94" width="22" height="20" rx="10"><title>乳腺</title></rect>
      <text x="100" y="146" text-anchor="middle">乳腺</text>
      ${hot("REG-ABDOMEN", 62, 134, 76, 54, "腹部", 100, 166)}
      ${hot("REG-MSK", 30, 200, 36, 50, "肌骨", 48, 232)}
      ${hot("REG-MSK", 134, 200, 36, 50, "肌骨", 152, 232)}
    </svg>`;
  }

  function signItem(s) {
    return `<button class="sign-item ${s.id === state.signId ? "on" : ""}" data-act="sign" data-id="${s.id}">
      <div class="nm"><b>${esc(s.name)}</b>${signCases(s.id).length ? '<span class="tag dot" style="color:#0f7a5a">影像</span>' : ""}</div>
      <span class="en">${esc(s.en || "")}</span>
      <span class="ds">${esc(s.appearance)}</span>
      <span class="mt">${modsOf(s).map((m) => `<span class="tag">${esc(m)}</span>`).join("")}<span class="tag">${esc(s.body_part)}</span></span>
    </button>`;
  }

  function signListHTML() {
    const arr = filteredSigns();
    return arr.length ? arr.map(signItem).join("") : '<div class="empty"><h3>库内暂无足够依据</h3><p class="small">换一个更具体的影像学术语，或清空部位/模态筛选。</p></div>';
  }

  function learnView() {
    const arr = filteredSigns();
    let s = sign(state.signId);
    if (!s || !arr.find((x) => x.id === state.signId)) s = arr[0] || sign(state.signId) || DB.signs[0];
    if (s) state.signId = s.id;
    const copy = state.role === "teacher"
      ? { h: "学 · 知识备课", p: "按部位、模态与条款条件备课。每条解释都带库内出处；没有依据时明确说没有。" }
      : state.role === "doctor"
        ? { h: "学 · 知识速查", p: "读片前 30 秒速查：定义、易错点、条款条件与可对照病例，出处随手可核。" }
        : { h: "学 · 基础知识问答", p: "先问“是什么、怎么看、容易错在哪”。每条解释都带库内出处；没有依据时明确说没有。" };
    const compact = isMobile() && state.mobileSignOpen;
    return `${compact
      ? `<div class="page-head" style="margin-bottom:10px"><div><h1 style="font-size:20px">${copy.h}</h1></div></div>`
      : `<div class="page-head">
      <div><div class="eyebrow">CHAIN 01 · FOUNDATION</div><h1>${copy.h}</h1><p>${copy.p}</p></div>
      <div class="page-actions"><button class="btn" data-act="nav" data-view="transfer">${icon("transfer", 15)} 去迁移</button><button class="btn primary" data-act="drill-random">${icon("target", 15)} 用一例检验</button></div>
    </div>`}
    ${compact ? "" : `<div class="searchbar"><div class="wrap"><span class="si">${icon("search", 18)}</span><input id="learnQ" value="${esc(state.query)}" placeholder="输入征象或问题，回车问 Agent；Shift+回车只做本地检索" autocomplete="off"></div><button class="btn" data-act="learn-search">本地检索</button><button class="btn primary" data-act="learn-ask">${icon("spark", 15)} 问 Agent</button></div>`}
    ${compact ? "" : `<div class="filters">
      <span class="lbl">部位</span>
      <button class="chip ${!state.part ? "on" : ""}" data-act="part" data-part="">全部</button>
      ${DB.meta.regions.map((r) => `<button class="chip ${state.part === r.id ? "on" : ""}" data-act="part" data-part="${r.id}">${r.name}</button>`).join("")}
      <span class="lbl" style="margin-left:8px">模态</span>
      <select id="modSel" style="height:30px;border:1px solid var(--line);border-radius:8px;background:#fff;padding:0 8px;font-size:12px">
        <option value="">全部</option>${["CT", "CR", "MR", "US", "MG"].map((m) => `<option ${state.modality === m ? "selected" : ""}>${m}</option>`).join("")}
      </select>
      <span class="lbl" style="margin-left:auto">${arr.length} 条结果</span>
    </div>`}
    ${compact ? "" : `<div id="agentZone">${agentZoneHTML()}</div>`}
    ${isMobile() && state.mobileSignOpen ? `<button class="btn sm" data-act="sign-back" style="margin-bottom:10px">${icon("left", 13)} 返回词条列表</button>` : ""}
    <div class="learn-split${isMobile() && !state.mobileSignOpen ? " list-only" : ""}${isMobile() && state.mobileSignOpen ? " detail-only" : ""}">
      ${!isMobile() || !state.mobileSignOpen ? `<div class="sign-list" id="signList">
        <div class="sign-list-h"><b>征象词条</b><span>${arr.length} / ${DB.meta.counts.signs}</span></div>
        ${signListHTML()}
      </div>` : ""}
      ${!isMobile() || state.mobileSignOpen ? `<div class="sign-detail">${s ? signDetail(s) : ""}</div>` : ""}
    </div>`;
  }

  function signDetail(s) {
    const rel = relatedSigns(s.id);
    const cmp = sign(state.compareId) || (rel[0] && rel[0].sign) || null;
    const cases = signCases(s.id).slice(0, 3);
    const guides = signGuides(s.id).slice(0, 3);
    const dual = state.dualQuery && DB.dualPresets[state.dualQuery] ? DB.dualPresets[state.dualQuery] : null;
    const bookmarked = progress.bookmarks.includes(s.id);
    return `<div class="detail-head">
      <div><h2>${esc(s.name)}</h2><div class="en">${esc(s.en || "")}</div></div>
      <div class="detail-actions">
        <button class="btn sm ${bookmarked ? "primary" : ""}" data-act="bookmark" data-id="${s.id}">${icon("book", 13)} ${bookmarked ? "已收藏" : "收藏"}</button>
        <button class="btn sm" data-act="transfer-sign" data-id="${s.id}">${icon("transfer", 13)} 迁移</button>
        <button class="btn sm" data-act="drill-sign" data-id="${s.id}">${icon("target", 13)} 找病例</button>
      </div>
    </div>
    <div class="row wrap" style="margin:8px 0 14px">${modsOf(s).map((m) => `<span class="chip solid">${esc(m)}</span>`).join("")}<span class="chip">${esc(s.body_part)}</span>${(s.aliases || []).slice(0, 3).map((a) => `<span class="chip">${esc(a)}</span>`).join("")}</div>
    <div class="quote">${esc(s.appearance)}</div>
    <div class="grid g2" style="margin-top:16px">
      <div><div class="sec-title" style="margin-top:0"><h2 style="font-size:14px">可见于</h2><span>不是诊断</span></div><div class="row wrap">${(s.may_see_in || []).map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</div></div>
      <div><div class="sec-title" style="margin-top:0"><h2 style="font-size:14px">易错点</h2><span>读片时先核对</span></div><ul class="bullets warn">${(s.pitfalls || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
    </div>
    <div class="divider"></div>
    <div class="sec-title" style="margin-top:0"><h2 style="font-size:14px">相关病例</h2><span>公开许可 · 点开看该征象在图上的位置</span></div>
    ${cases.length ? `<div class="thumbs">${cases.map((c) => `<button class="thumb-card" data-act="case-open" data-id="${c.id}"><img src="${c.image}" alt=""><b>${esc(c.title).slice(0, 18)}</b><span>${c.modality.join("/")}</span></button>`).join("")}</div>` : '<p class="small muted">该词条暂未关联公开影像；可到「病例演练」按部位浏览。</p>'}
    <div class="row wrap" style="margin-top:10px"><button class="btn sm" data-act="nav" data-view="drill">${icon("target", 13)} 去病例演练</button></div>
    <details class="fold-block" style="margin-top:14px">
      <summary><span>出处与引用</span><span class="fb-n">${(s.source_refs || []).length} 个来源</span></summary>
      <div class="fb-body">
        ${(s.source_refs || []).map((src) => `<div class="src"><div class="si">${icon("link", 13)}</div><div class="grow"><b>${esc(src.title)}</b><span>${esc(src.publisher || "")} · ${esc(src.license_note || "")}</span>${src.url ? `<a href="${esc(src.url)}" target="_blank" rel="noopener" class="tiny">打开来源 ${icon("external", 10)}</a>` : ""}</div></div>`).join("")}
        <p class="tiny muted" style="margin-top:8px">词条级出处；病例结论的双引用（空间锚点 + 文献锚点）在工作台逐条核验。</p>
      </div>
    </details>
    <div class="divider"></div>
    <div class="grid g2">
      <div>
        <div class="sec-title" style="margin-top:0"><h2 style="font-size:14px">对比着看</h2><span>同部位 / 同标签</span></div>
        ${cmp ? `<table class="compare"><thead><tr><th></th><th>${esc(s.name)}</th><th>${esc(cmp.name)}</th></tr></thead><tbody>
          <tr><td>定义</td><td>${esc(s.appearance).slice(0, 70)}…</td><td>${esc(cmp.appearance).slice(0, 70)}…</td></tr>
          <tr><td>模态</td><td>${modsOf(s).join("/")}</td><td>${modsOf(cmp).join("/")}</td></tr>
          <tr><td>可见于</td><td>${(s.may_see_in || []).slice(0, 3).join("、")}</td><td>${(cmp.may_see_in || []).slice(0, 3).join("、")}</td></tr>
          <tr><td>易错点</td><td>${esc((s.pitfalls || [])[0] || "—")}</td><td>${esc((cmp.pitfalls || [])[0] || "—")}</td></tr>
        </tbody></table>` : '<p class="small muted">暂无可对比词条。</p>'}
        <div class="row wrap" style="margin-top:8px">${rel.slice(0, 4).map((x) => `<button class="chip ${cmp && cmp.id === x.sign.id ? "on" : ""}" data-act="compare" data-id="${x.sign.id}">对比 ${esc(x.sign.name)}</button>`).join("")}</div>
      </div>
      <div>
        <div class="sec-title" style="margin-top:0"><h2 style="font-size:14px">双线判断</h2><span>影像线 × 指南线</span></div>
        ${dual ? dualCard(dual) : `<p class="small muted" style="margin-bottom:8px">选一条预置问句，查看库内影像证据与指南条款的对齐结果。判断的是“证据是否对齐”，不是病情。</p><div class="row wrap">${Object.keys(DB.dualPresets).map((q) => `<button class="chip" data-act="dual" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>`}
        ${guides.length ? `<div style="margin-top:12px"><h4 class="small" style="margin-bottom:6px">该部位相关条款</h4>${guides.map((g) => `<div class="src"><div class="si">${icon("clipboard", 13)}</div><div class="grow"><b>${esc(g.standard_name)} · ${esc(g.category || "")}</b><span>${esc(g.statement)}</span><span class="tiny muted">条件：${esc((g.conditions || []).join("；"))}</span></div></div>`).join("")}</div>` : ""}
      </div>
    </div>
    <div class="divider"></div>
    <div class="row" style="margin-top:10px">
      <button class="btn primary sm" data-act="learn-ask-sign" data-id="${s.id}">${icon("spark", 13)} 让 Agent 解释「${esc(s.name)}」</button>
      <span class="tiny muted">走真实链路；回执与耗时显示在搜索框下方</span>
    </div>`;
  }

  function dualCard(d) {
    const a = d.alignment || {};
    const level = a.level || "insufficient";
    const label = { aligned: "两线对齐", partial: "条件待补", insufficient: "依据不足", divergent: "方向不一致" }[level] || level;
    return `<div class="dual">
      <div class="dual-head"><span class="chip ${level === "aligned" ? "ok" : level === "partial" ? "warn" : "danger"}">${label}</span><span class="tiny muted">${esc(d.query)}</span></div>
      <div class="dual-lines">
        <div class="dual-line"><b>影像线</b><span>${d.signIds.map((id) => esc((sign(id) || {}).name || id)).join("、") || "未命中"}</span></div>
        <div class="dual-line"><b>指南线</b><span>${d.guidelineIds.map((id) => esc((YZ.guide(id) || {}).standard_name || id)).join("、") || "未命中"}</span></div>
      </div>
      <div class="dual-res ${level}">
        <b>${esc(a.note || "")}</b>
        ${(a.matched || []).length ? `<div style="margin-top:4px">已覆盖：${a.matched.map(esc).join("；")}</div>` : ""}
        ${(a.missing || []).length ? `<div style="margin-top:4px">待补充：${a.missing.map(esc).join("；")}</div>` : ""}
        ${a.action ? `<div style="margin-top:4px">条款方向：${esc(a.action)}（原文摘录，不是建议）</div>` : ""}
      </div>
      <div class="tiny muted">${esc(d.disclaimer || "")}</div>
    </div>`;
  }

  /* ---------- Agent 问答区（唯一真实链路入口） ---------- */

  function agentZoneHTML() {
    const a = state.agent || { status: "idle" };

    if (a.status === "idle") {
      return `<div class="agent-zone idle">
        <div class="az-h"><b>${icon("spark", 14)} Agent 问答</b>
          <span class="az-tip">「本地检索」秒回词条；「问 Agent」把问题交给 DeepWorks 引擎，回执是真实运行记录。</span></div>
      </div>`;
    }

    const running = a.status === "running";
    const cls = a.blocked ? "bad" : a.degraded ? "warn" : a.status === "error" ? "bad" : running ? "run" : "ok";
    const stateText = running ? "运行中"
      : a.status === "error" ? "失败"
      : a.blocked ? "已拦截 · 超范围"
      : a.degraded ? "降级 · 本地演示态" : "真实运行";

    // 优先级：拦截 > 引用编造 > 降级 > 失败。引用编造比降级更严重，
    // 因为降级是「能力不足」且已如实标注，编造 id 是「看起来可信但错误」。
    const banner = a.blocked
      ? `<div class="az-banner">${icon("alert", 13)} <b>已拦截</b>：问题涉及诊断或治疗，按边界规则不回答，也未调用模型。</div>`
      : (a.unverified && a.unverified.length)
        ? `<div class="az-banner bad">${icon("alert", 13)} <b>引用校验未通过</b>：${a.unverified.map((x) => esc(x)).join("、")} 不在知识库中，本回答不可作为依据。</div>`
        : a.degraded
          ? `<div class="az-banner">${icon("alert", 13)} <b>本地演示态</b>：${esc(a.reason || "Agent 不可用")}。回答来自库内关键词检索，回执如实标注未运行阶段。</div>`
          : a.grounding === "general"
            ? `<div class="az-banner">${icon("alert", 13)} <b>库外问题</b>：库内未覆盖该主题，以下为模型通识，不是本库证据，也不能当作可核验引用。</div>`
            : a.status === "error"
            ? `<div class="az-banner bad">${icon("alert", 13)} 调用失败：${esc(a.reason || "unknown")}。可重试，或改用本地检索。</div>`
            : "";

    const body = a.text
      ? `<div class="az-body">${esc(a.text)}</div>`
      : running ? `<div class="az-body muted">正在运行，首字延迟通常 6–15 秒…</div>` : "";

    const cites = (a.citations || []).length
      ? `<div class="az-cites"><span class="lbl">出处</span>${a.citations.map((c) => `<span class="chip">${esc(c.title || c.id || "")}</span>`).join("")}</div>`
      : "";

    const showTrace = (a.spans || []).length > 0 || a.status === "done" || a.status === "error";

    /* 证据来源标签：让评审一眼看出哪部分是库内证据、哪部分是模型通识。
     * 未标注通识来源（marker_ok=false）或通识段越界带 id，都按最严重处理。 */
    const tag = (() => {
      if (running) return "";
      if (a.degraded) return `<span class="az-tag bad">降级 · 本地演示态</span>`;
      const g = a.grounding || "";
      const badIds = (a.generalIds || []).length;
      if (badIds) return `<span class="az-tag bad">通识段越界 id ${badIds}</span>`;
      if (a.markerOk === false) return `<span class="az-tag bad">未标注通识来源</span>`;
      if (g === "mixed") return `<span class="az-tag warn">库内证据 + 通识补充</span>`;
      if (g === "general") return `<span class="az-tag bad">纯通识 · 非库内证据</span>`;
      if (g === "grounded") return `<span class="az-tag ok">库内证据</span>`;
      return "";
    })();

    return `<div class="agent-zone ${cls}">
      <div class="az-h">
        <b>${icon("spark", 14)} Agent 问答</b>
        <span class="az-q">${esc(a.query || "")}</span>
        ${tag}
        <span class="az-st">${stateText}</span>
        ${running ? `<button class="btn sm" data-act="learn-ask-stop">停止</button>` : ""}
      </div>
      ${banner}${body}${cites}
      ${showTrace ? traceLive(a.spans, { runId: a.runId, ttft: a.ttft, total: a.total, traceUrl: a.traceUrl }) : ""}
    </div>`;
  }

  function paintAgent() {
    const el = document.getElementById("agentZone");
    if (el) el.innerHTML = agentZoneHTML();
  }

  function stopAgentAsk() {
    const a = state.agent;
    if (a && a.stream && typeof a.stream.abort === "function") a.stream.abort();
    if (a) { a.status = "error"; a.reason = "已手动停止"; a.stream = null; }
    paintAgent();
  }

  function startAgentAsk(query) {
    const q = (query || "").trim();
    if (!q) { toast("先输入一个问题"); return; }

    const prev = state.agent;
    if (prev && prev.stream && typeof prev.stream.abort === "function") prev.stream.abort();

    state.agent = {
      status: "running", query: q, text: "", spans: [], citations: [],
      runId: "", degraded: false, blocked: false, unverified: [], cited: [],
      grounding: "", markerOk: true, generalIds: [],
      reason: "", ttft: null, total: null,
      traceUrl: "", stream: null,
    };
    paintAgent();

    /* 用对象引用隔离：旧请求被 abort 后仍可能有已在队列里的事件，
     * 不能让它们写进新请求的状态。 */
    const self = state.agent;

    state.agent.stream = YZ.askStream(q, {
      role: state.role,
      device: isMobile() ? "mobile" : "desktop",
      onTrace(p) { if (state.agent !== self) return; self.spans.push(p); paintAgent(); },
      onDelta(p) { if (state.agent !== self) return; self.text += (p && p.text) || ""; paintAgent(); },
      onCitation(p) { if (state.agent !== self) return; self.citations.push(p); paintAgent(); },
      onReset() { if (state.agent !== self) return; self.text = ""; paintAgent(); },
      onDone(p) {
        if (state.agent !== self) return;
        self.status = "done";
        self.runId = p.run_id || "";
        self.degraded = !!p.degraded;
        self.blocked = !!p.blocked;
        self.unverified = p.unverified_citations || [];
        self.cited = p.cited || [];
        self.grounding = p.grounding || "";
        self.markerOk = p.marker_ok !== false;
        self.generalIds = p.general_section_ids || [];
        self.reason = p.reason || "";
        self.ttft = p.first_token_ms != null ? p.first_token_ms : null;
        self.total = p.total_ms != null ? p.total_ms : null;
        self.traceUrl = p.trace_url || "";
        self.stream = null;
        paintAgent();
      },
      onError(p) {
        if (state.agent !== self) return;
        if (self.status === "done") return;
        self.status = "error";
        self.reason = (p && p.reason) || "unknown";
        self.stream = null;
        paintAgent();
      },
    });
  }

  Object.assign(YZ, { learnView, signDetail, signListHTML, anatomySVG, dualCard,
                      agentZoneHTML, paintAgent, startAgentAsk, stopAgentAsk });
})(window.YZ);
