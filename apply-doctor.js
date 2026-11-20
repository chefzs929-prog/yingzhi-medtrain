/* 用 · 医生端：病例工作台 */
(function (YZ) {
  "use strict";
  const { esc, icon, DB, state, progress, save, claimsOf, regionsOf, docCite, spatialCite, citeBadge, statusChip, sign, caseOf, pct, today, reviewedCount, traceLocal } = YZ;

  function doctorApply() {
    const tabs = [["workbench", "病例工作台"], ["audit", "引用审计"], ["summary", "教学要点"]];
    return `<div class="page-head">
      <div><div class="eyebrow">CHAIN 04 · CLINICAL</div><h1>用 · 病例工作台</h1><p>把“图上哪一块”与“哪份文献哪一条”并排核验；缺一条就降级，hash 不一致就拦截。</p></div>
      <div class="page-actions"><span class="chip ok">${icon("check", 13)} 已核验 ${reviewedCount()} 条</span><label class="chip ${state.sync ? "on" : ""}" style="cursor:pointer" data-act="sync">${icon("layers", 13)} 并排核验</label><button class="btn" data-act="apply-tab" data-tab="audit">${icon("shield", 15)} 引用审计</button></div>
    </div>
    <div class="tabs">${tabs.map(([id, label]) => `<button class="${state.applyTab === id ? "on" : ""}" data-act="apply-tab" data-tab="${id}">${label}</button>`).join("")}</div>
    ${state.applyTab === "workbench" ? doctorWorkbench() : state.applyTab === "audit" ? doctorAudit() : doctorSummary()}`;
  }

  function doctorWorkbench() {
    const c = caseOf(state.caseId) || DB.cases[0];
    state.caseId = c.id;
    const regions = regionsOf(c.id);
    const claims = claimsOf(c.id);
    const regionClaims = state.regionId ? claims.filter((x) => x.region_id === state.regionId) : claims;
    const active = state.claimId ? claims.find((x) => x.id === state.claimId) : null;
    const shown = state.showRegions !== false;
    const claimsIn = (rid) => claims.filter((x) => x.region_id === rid).length;
    const note = state.regionId
      ? `当前分区：<b>${esc((regions.find((r) => r.id === state.regionId) || {}).name || "")}</b>`
      : shown ? "点图上的编号或下方图例，查看该区结论" : "分区框已隐藏，可用下方图例按名称选分区";
    const dual = claims.filter((x) => x.cite_status === "dual").length;
    const broken = claims.filter((x) => x.cite_status === "broken").length;
    const verified = claims.filter((x) => progress.reviewed.includes(x.id)).length;
    return `<div class="case-banner">
      <span class="cb-id">${esc(c.id)}</span>
      <b>${esc(c.title)}</b>
      <span class="cb-meta">${c.modality.join("/")} · ${esc(c.body_part)} · ${esc(c.license)}</span>
      <div class="cb-st">
        <span>已核验 ${verified}/${claims.length}</span>
        <span>双引用 ${dual}</span>
        ${broken ? `<span class="cb-bad">拦截 ${broken}</span>` : ""}
      </div>
    </div>
    <div class="workbench">
      <aside class="queue">
        <div class="queue-h"><b>病例队列</b><span>${DB.cases.length}</span></div>
        <div style="padding:8px 10px;border-bottom:1px solid var(--line)"><input id="caseQ" value="${esc(state.caseQuery)}" placeholder="搜病例 / 部位 / 模态" style="width:100%;height:32px;border:1px solid var(--line);border-radius:8px;padding:0 9px;font-size:12px"></div>
        <div class="queue-list" id="queueList">${queueHTML()}</div>
      </aside>
      <section class="viewer">
        <div class="viewer-h"><div><span>${regions.length} 分区 · 编号为人工标注解剖区，不是病灶分割</span></div>
          <div class="wb-h-acts">
            <button class="wb-toggle" data-act="regions" aria-pressed="${shown}" title="${shown ? "隐藏分区框，只看影像" : "显示分区框"}">${icon(shown ? "eye" : "eyeOff", 13)}<span>${shown ? "隐藏分区" : "显示分区"}</span></button>
            <span class="chip" style="background:rgba(255,255,255,.1);border-color:rgba(255,255,255,.2);color:#fff">${regions.length} 分区</span>
          </div>
        </div>
        <div class="stage">
          <div class="frame">
          <img src="${c.image}" alt="${esc(c.title)}">
          ${shown ? `<div class="overlay">${regions.map((r, i) => {
            const [x, y, w, h] = r.coords;
            const on = state.regionId === r.id || (active && active.region_id === r.id);
            return `<button class="bbox mark ${on ? "correct labeled" : ""}" style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%" data-act="region" data-id="${r.id}" title="${esc(r.name)}" aria-label="分区 ${i + 1} ${esc(r.name)}"><span>${i + 1}</span></button>`;
          }).join("")}</div>` : ""}
          </div>
        </div>
        <div class="wb-legend" aria-label="分区标注图例">
          ${regions.map((r, i) => `<button class="wb-leg ${state.regionId === r.id ? "on" : ""}" data-act="region" data-id="${r.id}" title="选择「${esc(r.name)}」">
            <i>${i + 1}</i><b>${esc(r.name)}</b><em>${claimsIn(r.id)}</em>
          </button>`).join("")}
        </div>
        <div class="stage-note"><span>${note}</span><span>编号为人工标注解剖区，不是病灶分割</span></div>
      </section>
      <aside class="evidence">
        <div class="ev-h"><b>${active ? "结论与引用" : state.regionId ? "该分区结论" : "全部结论"}</b><span class="tiny muted">${regionClaims.length} 条</span></div>
        <div class="ev-body">
          ${active ? claimDetail(active) : regionClaims.slice(0, 10).map((cl) => `<button class="claim ${state.claimId === cl.id ? "on" : ""}" data-act="claim" data-id="${cl.id}"><div class="ct">${esc(cl.text)}</div><div class="cm">${citeBadge(cl)}<span class="chip">${esc((regions.find((r) => r.id === cl.region_id) || {}).name || "")}</span></div></button>`).join("") || '<p class="small muted">该病例暂无分区结论。</p>'}
        </div>
      </aside>
      <div class="wb-actions">
        <button class="btn sm" data-act="case-prev">${icon("left", 13)} 上一例</button>
        <button class="btn sm" data-act="verify-case">${icon("check", 13)} 标记本病例已核验</button>
        <button class="btn sm" data-act="apply-tab" data-tab="summary">${icon("copy", 13)} 生成交班摘要</button>
        <span class="grow"></span>
        <button class="btn primary sm" data-act="case-next">下一例 ${icon("right", 13)}</button>
      </div>
    </div>`;
  }

  function queueHTML() {
    const q = (state.caseQuery || "").trim().toLowerCase();
    const arr = DB.cases.filter((c) => !q || [c.title, c.body_part, c.modality.join(" "), c.id].join(" ").toLowerCase().includes(q)).slice(0, 80);
    return arr.map((c) => `<button class="qitem ${c.id === state.caseId ? "on" : ""}" data-act="case" data-id="${c.id}"><img src="${c.image}" alt=""><div class="grow"><b>${esc(c.title).slice(0, 24)}</b><span>${c.modality.join("/")} · ${esc(c.body_part)}</span></div></button>`).join("");
  }

  function claimDetail(cl) {
    const sp = spatialCite(cl);
    const dc = docCite(cl);
    const r = regionsOf(state.caseId).find((x) => x.id === cl.region_id);
    return `<div class="claim on" style="cursor:default"><div class="ct">${esc(cl.text)}</div><div class="cm">${citeBadge(cl)}${(cl.sign_ids || []).slice(0, 2).map((id) => `<span class="chip">${esc((sign(id) || {}).name || id)}</span>`).join("")}</div></div>
      <div class="cite"><b>空间锚点</b>${sp ? `${esc((r || {}).name || cl.region_id)} · bbox [${(sp.anchor.bbox || []).map((n) => Number(n).toFixed(2)).join(", ")}]<br><span class="tiny muted">${esc(sp.anchor.annotator || "human")} · ${esc(sp.anchor.annotated_at || "")} · ${esc(sp.anchor.atlas_id || "")}</span>` : "缺空间锚点，已降级"}</div>
      <div class="cite ${dc && dc.hash_ok === false ? "bad" : ""}"><b>文献锚点</b>${dc ? `<span class="ex">${esc(dc.anchor.excerpt || "")}</span><br><span class="tiny muted">${esc(dc.anchor.doc_title || dc.anchor.doc_id)} · ${esc(dc.anchor.locator || "")} · ${esc(dc.anchor.version || "")}</span><br>${dc.hash_ok === false ? '<span class="chip danger" style="margin-top:5px">hash 不一致，已拦截</span>' : '<span class="chip ok" style="margin-top:5px">hash 校验通过</span>'}` : "缺文献锚点，已降级"}</div>
      <div class="row wrap"><button class="btn sm ${progress.reviewed.includes(cl.id) ? "primary" : ""}" data-act="verify-claim" data-id="${cl.id}">${icon("check", 13)} ${progress.reviewed.includes(cl.id) ? "已核验" : "标记已核验"}</button><button class="btn sm" data-act="copy-claim" data-id="${cl.id}">${icon("copy", 13)} 复制结论与出处</button><button class="btn sm" data-act="claim-close">返回列表</button></div>
      ${traceLocal("本次核验的计算过程", [
        { label: "空间锚点", value: sp ? `${(r || {}).name || cl.region_id} · bbox` : "缺失，已降级", state: sp ? "ok" : "bad" },
        { label: "文献锚点", value: dc ? (dc.anchor.doc_title || dc.anchor.doc_id) : "缺失，已降级", state: dc ? "ok" : "bad" },
        { label: "hash", value: dc ? (dc.hash_ok === false ? "不一致，已拦截" : "校验通过") : "未提供", state: dc && dc.hash_ok !== false ? "ok" : "bad" },
        { label: "结论", value: { dual: "双引用可用", single: "单引用降级", broken: "已拦截", none: "无引用" }[cl.cite_status] || cl.cite_status, state: cl.cite_status === "dual" ? "ok" : "warn" },
      ])}
      <p class="tiny muted">仅作影像表现与条款对照，不构成诊断意见。</p>`;
  }

  function doctorAudit() {
    const all = DB.cases.flatMap((c) => claimsOf(c.id));
    const counts = {
      dual: all.filter((x) => x.cite_status === "dual").length,
      single: all.filter((x) => x.cite_status === "single").length,
      broken: all.filter((x) => x.cite_status === "broken").length,
    };
    const rows = all.filter((x) => !state.auditBrokenOnly || x.cite_status === "broken").slice(0, 200);
    return `<div class="stat-strip" style="margin-bottom:14px">
      <div class="stat"><b>${all.length}</b><span>结论总数</span><i>全库</i></div>
      <div class="stat"><b>${counts.dual}</b><span>双引用完整</span><i>空间 + 文献</i></div>
      <div class="stat"><b>${counts.single}</b><span>单引用</span><i>已降级</i></div>
      <div class="stat"><b style="color:#c2413a">${counts.broken}</b><span>hash 拦截</span><i>摘录不一致</i></div>
      <div class="stat"><b>${pct(counts.dual, all.length)}%</b><span>双引用覆盖率</span><i>可回溯</i></div>
    </div>
    <div class="card panel">
      <div class="panel-h"><h3>引用审计表</h3><div class="row"><button class="chip ${state.auditBrokenOnly ? "on" : ""}" data-act="audit-filter">只看拦截</button><span class="sub">显示前 200 条</span></div></div>
      <div style="max-height:520px;overflow:auto"><table class="table"><thead><tr><th>结论</th><th>病例</th><th>分区</th><th>状态</th><th>文献锚点</th><th>hash</th></tr></thead><tbody>
        ${rows.map((x) => {
          const dc = docCite(x);
          return `<tr class="${x.cite_status === "broken" ? "bad" : ""}"><td style="max-width:280px">${esc(x.text).slice(0, 70)}…</td><td>${esc(x.image_id)}</td><td>${esc((regionsOf(x.image_id).find((r) => r.id === x.region_id) || {}).name || x.region_id)}</td><td>${statusChip(x.cite_status)}</td><td>${esc(dc ? (dc.anchor.doc_title || dc.anchor.doc_id) : "—")}</td><td class="mono tiny">${esc(dc && dc.anchor.excerpt_sha256 || "—")}</td></tr>`;
        }).join("")}
      </tbody></table></div>
    </div>`;
  }

  function summaryText(c, claims) {
    return [
      `# 交班摘要 · ${c.title}`,
      ``,
      `- 病例：${c.id}`,
      `- 模态 / 部位：${c.modality.join(" / ")} · ${c.body_part}`,
      `- 来源：${c.source_page}`,
      `- 许可：${c.license} · ${c.artist}`,
      ``,
      `## 分区结论`,
      ...claims.map((cl) => {
        const dc = docCite(cl);
        const r = regionsOf(c.id).find((x) => x.id === cl.region_id);
        return `- ${r ? r.name : cl.region_id}：${cl.text}\n  出处：${dc ? (dc.anchor.doc_title || dc.anchor.doc_id) + " · " + (dc.anchor.locator || "") : "缺文献锚点"}`;
      }),
      ``,
      `## 边界`,
      `本摘要只做影像表现与公开文献对照，不构成诊断意见，不替代临床决策。`,
    ].join("\n");
  }

  function doctorSummary() {
    const c = caseOf(state.caseId) || DB.cases[0];
    const claims = claimsOf(c.id).slice(0, 3);
    const text = summaryText(c, claims);
    return `<div class="grid g2">
      <div class="card panel">
        <div class="panel-h"><h3>交班摘要</h3><span class="sub">${esc(c.title)}</span></div>
        <textarea id="summaryBox" style="width:100%;min-height:360px;border:1px solid var(--line);border-radius:10px;padding:12px;font:12px/1.7 var(--mono);background:var(--surface-2)">${esc(text)}</textarea>
        <div class="row" style="margin-top:10px"><button class="btn primary" data-act="copy-summary">${icon("copy", 14)} 复制摘要</button><button class="btn" data-act="download-summary">${icon("download", 14)} 下载 .md</button></div>
      </div>
      <div class="stack">
        <div class="card panel">
          <div class="panel-h"><h3>本病例引用</h3><span class="sub">${claims.length} 条</span></div>
          ${claims.map((cl) => `<div class="claim" style="margin-bottom:7px"><div class="ct">${esc(cl.text)}</div><div class="cm">${citeBadge(cl)}</div></div>`).join("")}
        </div>
        <div class="notice"><span class="ni">${icon("alert", 15)}</span><div><b>为什么保留“拦截”</b> 库内 1 条条款摘录与当前版本不一致，系统不把它当作可用证据。这是能力，不是瑕疵。</div></div>
      </div>
    </div>`;
  }

  function copyClaim(id) {
    const c = caseOf(state.caseId);
    const cl = claimsOf(state.caseId).find((x) => x.id === id);
    if (!cl || !c) return;
    const dc = docCite(cl);
    const text = `${cl.text}\n出处：${dc ? (dc.anchor.doc_title || dc.anchor.doc_id) + " · " + (dc.anchor.locator || "") : "缺文献锚点"}\n边界：仅作影像表现对照，不构成诊断意见。`;
    YZ.copyText(text, "结论与出处已复制");
  }

  Object.assign(YZ, { doctorApply, doctorWorkbench, doctorAudit, doctorSummary, summaryText, copyClaim, queueHTML, claimDetail });
})(window.YZ);
