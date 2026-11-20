/* 迁 · 临床知识迁移 */
(function (YZ) {
  "use strict";
  const { esc, icon, DB, state, progress, sign, signCases, signGuides, relatedSigns, crossPartSigns, modsOf, traceLocal } = YZ;

  function transferView() {
    const s = sign(state.transferId) || DB.signs[0];
    const rel = relatedSigns(s.id);
    const cross = crossPartSigns(s.id);
    const cmp = sign(state.compareId) || (rel[0] && rel[0].sign);
    const guides = signGuides(s.id).slice(0, 3);
    const presets = [
      { id: "SIGN-002", title: "换模态", sub: "实变：CT 与 CR 的定义边界" },
      { id: "SIGN-058", title: "换部位", sub: "低回声结节：甲状腺 → 乳腺" },
      { id: "SIGN-001", title: "换病种", sub: "磨玻璃影：炎症 / 纤维化 / 肿瘤 / 水肿" },
    ];
    const cells = ["CT", "CR", "MR", "US", "MG"];
    const copy = state.role === "teacher"
      ? { h: "迁 · 迁移设计", p: "把“换模态、换部位、换病种”设计成可布置的对照任务；先给条件，再让学生判断还成不成立。" }
      : state.role === "doctor"
        ? { h: "迁 · 跨场景鉴别", p: "跨模态、跨部位对照，先核对条件与易错点，避免把“看起来像”当成同一条证据。" }
        : { h: "迁 · 临床知识迁移", p: "同一个词，换模态、换部位、换病种还成不成立？把“看起来像”拆成可核对的条件。" };
    return `<div class="page-head">
      <div><div class="eyebrow">CHAIN 02 · TRANSFER</div><h1>${copy.h}</h1><p>${copy.p}</p></div>
      <div class="page-actions">
        <button class="btn" data-act="nav" data-view="learn">${icon("book", 15)} 回到基础</button>
        ${state.role === "teacher" ? `<button class="btn" data-act="teacher-go" data-tab="assign">${icon("users", 15)} 去布置</button>` : state.role === "doctor" ? `<button class="btn" data-act="nav" data-view="apply">${icon("stethoscope", 15)} 去工作台</button>` : ""}
        <button class="btn primary" data-act="card-open">${icon("copy", 15)} 生成迁移卡</button>
      </div>
    </div>
    <div class="transfer-layout">
      <aside class="stack">
        <div class="card panel">
          <div class="panel-h"><h3>选一个征象</h3><span class="sub">60 条</span></div>
          <select id="transferSel" style="width:100%;height:38px;border:1px solid var(--line);border-radius:9px;padding:0 9px;background:#fff;font-size:12.5px">
            ${DB.meta.regions.map((r) => `<optgroup label="${r.name}">${DB.signs.filter((x) => x.region_id === r.id).map((x) => `<option value="${x.id}" ${x.id === s.id ? "selected" : ""}>${esc(x.name)} · ${modsOf(x).join("/")}</option>`).join("")}</optgroup>`).join("")}
          </select>
        </div>
        <div class="card panel">
          <div class="panel-h"><h3>迁移任务</h3><span class="sub">三个方向</span></div>
          <div class="preset">${presets.map((p) => `<button data-act="transfer-sign" data-id="${p.id}"><b>${p.title} · ${esc((sign(p.id) || {}).name || "")}</b><span>${p.sub}</span></button>`).join("")}</div>
        </div>
        <div class="card panel">
          <div class="panel-h"><h3>迁移记录</h3><span class="sub">${progress.cards.length} 张</span></div>
          ${progress.cards.length ? progress.cards.slice(0, 3).map((c) => `<div class="card-saved" style="margin-bottom:7px"><b>${esc(c.title)}</b><span>${esc(c.date)}</span></div>`).join("") : '<p class="small muted">还没有迁移卡。选好征象后点右上角生成。</p>'}
        </div>
      </aside>
      <div class="stack">
        <div class="card panel">
          <div class="panel-h"><div><h3 style="font-size:17px">${esc(s.name)} <span class="tiny muted mono">${esc(s.en || "")}</span></h3><span class="sub">${esc(s.body_part)} · ${modsOf(s).join(" / ")}</span></div><span class="chip solid">${esc(s.appearance).slice(0, 26)}…</span></div>
          <div class="grid g2">
            <div>
              <h4 class="small" style="margin-bottom:6px">迁移坐标：部位 × 模态</h4>
              <table class="matrix"><thead><tr><th></th>${cells.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>
                ${DB.meta.regions.map((r) => `<tr><th>${r.name}</th>${cells.map((m) => {
                  const n = DB.signs.filter((x) => x.region_id === r.id && (x.modality || []).includes(m)).length;
                  const now = s.region_id === r.id && (s.modality || []).includes(m);
                  return `<td class="${now ? "now" : n ? "has" : ""}" title="${r.name} · ${m}：${n} 条">${now ? "●" : n || "·"}</td>`;
                }).join("")}</tr>`).join("")}
              </tbody></table>
              <p class="tiny muted" style="margin-top:6px">● 当前词条所在格；数字为该部位/模态下的词条数。</p>
            </div>
            <div>
              <h4 class="small" style="margin-bottom:6px">迁移三问</h4>
              <div class="stack" style="gap:8px">
                <div class="qcard" style="padding:11px"><div class="qh"><span class="qn">1</span><h4>换模态，定义变了吗？</h4></div><p>${esc(s.name)} 在 ${modsOf(s).join(" / ") || "库内"} 下成立。${esc((s.pitfalls || [])[0] || "")}</p></div>
                <div class="qcard" style="padding:11px"><div class="qh"><span class="qn">2</span><h4>换部位，判读重点变了吗？</h4></div><p>${cross.length ? `同标签跨部位：${cross.slice(0, 3).map((x) => esc(x.name) + "（" + esc(x.body_part) + "）").join("、")}。` : "库内暂无同标签跨部位词条。"}${esc((s.pitfalls || [])[1] || "")}</p></div>
                <div class="qcard" style="padding:11px"><div class="qh"><span class="qn">3</span><h4>换病种，还可能是哪些？</h4></div><p>${(s.may_see_in || []).map(esc).join("、")}。这些只是“可见于”，不是概率排序。</p></div>
              </div>
            </div>
          </div>
        </div>
        <div class="card panel">
          <div class="panel-h"><h3>对照着迁移</h3><span class="sub">选一个近邻词条</span></div>
          ${cmp ? `<table class="compare"><thead><tr><th></th><th>${esc(s.name)}</th><th>${esc(cmp.name)}</th></tr></thead><tbody>
            <tr><td>定义</td><td>${esc(s.appearance)}</td><td>${esc(cmp.appearance)}</td></tr>
            <tr><td>模态</td><td>${modsOf(s).join("/")}</td><td>${modsOf(cmp).join("/")}</td></tr>
            <tr><td>部位</td><td>${esc(s.body_part)}</td><td>${esc(cmp.body_part)}</td></tr>
            <tr><td>易错点</td><td>${esc((s.pitfalls || []).join("；"))}</td><td>${esc((cmp.pitfalls || []).join("；"))}</td></tr>
          </tbody></table>` : '<p class="small muted">暂无可对照词条。</p>'}
          <div class="row wrap" style="margin-top:10px">${rel.slice(0, 6).map((x) => `<button class="chip ${cmp && cmp.id === x.sign.id ? "on" : ""}" data-act="compare" data-id="${x.sign.id}">${esc(x.sign.name)}</button>`).join("")}</div>
        </div>
        <div class="grid g2">
          <div class="card panel">
            <div class="panel-h"><h3>指南条款：先核对条件</h3><span class="sub">${guides.length} 条</span></div>
            ${guides.length ? guides.map((g) => `<div class="qcard" style="padding:11px;margin-bottom:8px"><div class="row spread"><b class="small">${esc(g.standard_name)} · ${esc(g.category || "")}</b><span class="chip warn">条件待核对</span></div><p style="margin-top:5px">${esc(g.statement)}</p><div class="checklist" style="margin-top:8px">${(g.conditions || []).map((c, i) => `<label><input type="checkbox" data-act="check" data-key="${g.id}-${i}"> ${esc(c)}</label>`).join("")}</div></div>`).join("") : '<p class="small muted">该词条暂无同部位条款。</p>'}
            <p class="tiny muted">勾选只代表你完成了条件核对；平台不判断个体是否满足条件，也不输出建议。</p>
          </div>
          <div class="card panel">
            <div class="panel-h"><h3>可以落到哪些病例</h3><span class="sub">公开影像</span></div>
            ${signCases(s.id).slice(0, 4).map((c) => `<div class="list-item"><img src="${c.image}" alt="" style="width:52px;height:40px;border-radius:6px;object-fit:cover"><div class="grow"><b>${esc(c.title).slice(0, 22)}</b><span>${c.modality.join("/")} · ${esc(c.body_part)}</span></div><button class="btn sm" data-act="case-open" data-id="${c.id}">打开</button></div>`).join("") || '<p class="small muted">暂未关联病例。</p>'}
          </div>
        </div>
        ${traceLocal("本次迁移判断的计算过程", [
          { label: "选词条", value: `${s.name} · ${s.body_part}` },
          { label: "换维度", value: `模态 ${modsOf(s).join("/")} × 近邻 ${rel.length} 条 × 跨部位 ${cross.length} 条` },
          { label: "核条件", value: `${guides.length} 条条款 · 只对照不裁决`, state: guides.length ? "ok" : "" },
          { label: "落病例", value: `${signCases(s.id).length} 例公开影像` },
        ])}
      </div>
    </div>`;
  }

  function transferCardText() {
    const s = sign(state.transferId) || DB.signs[0];
    const rel = relatedSigns(s.id).slice(0, 3);
    const cross = crossPartSigns(s.id).slice(0, 3);
    const guides = signGuides(s.id).slice(0, 2);
    const cases = signCases(s.id).slice(0, 3);
    return [
      `# 迁移卡 · ${s.name}`,
      ``,
      `- 词条：${s.id} · ${s.en || ""}`,
      `- 部位 / 模态：${s.body_part} · ${modsOf(s).join(" / ")}`,
      `- 定义：${s.appearance}`,
      ``,
      `## 换模态`,
      `易错点：${(s.pitfalls || []).join("；")}`,
      `近邻：${rel.map((x) => x.sign.name).join("、") || "无"}`,
      ``,
      `## 换部位`,
      `同标签跨部位：${cross.map((x) => `${x.name}（${x.body_part}）`).join("、") || "库内暂无"}`,
      ``,
      `## 换病种`,
      `可见于：${(s.may_see_in || []).join("、")}`,
      ``,
      `## 条款条件（只作对照）`,
      ...(guides.length ? guides.map((g) => `- ${g.standard_name} · ${g.category || ""}：${g.statement}\n  条件：${(g.conditions || []).join("；")}`) : ["- 暂无同部位条款"]),
      ``,
      `## 可对照病例`,
      ...(cases.length ? cases.map((c) => `- ${c.title}（${c.modality.join("/")}，${c.license}）`) : ["- 暂无"]),
      ``,
      `> 本卡仅用于医学影像教学与研究，不构成诊断意见，不替代临床决策。`,
    ].join("\n");
  }

  Object.assign(YZ, { transferView, transferCardText });
})(window.YZ);
