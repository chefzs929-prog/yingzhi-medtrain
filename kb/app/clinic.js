/* 胸片阅片工作台
 * 一条主链路：选片 → 点分区/拖框 → 看所见与出处 → 生成阅片记录。
 * 数据来自 data/chest/chest_reading.json（kb/scripts/build_chest_reading.py 生成）。
 * 设计约束：
 *   - 只答当前病例；不跨病例拼答案。
 *   - unmentioned 不渲染成 normal。
 *   - 上传只做 SHA-256 精确匹配；匹配不上就明确拒绝。
 */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
  const clamp = (n, a, b) => Math.max(a, Math.min(b, n));

  const DATA_URL = "../data/chest/chest_reading.json";
  const STATUS = {
    abnormal: "异常",
    normal: "未见异常",
    unmentioned: "来源未提及",
    limited: "判读受限",
  };
  const SIDE = { right: "患者右侧", left: "患者左侧", midline: "中线" };
  const SHORT = {
    RUL: "右上", RML: "右中", RLL: "右下",
    LUL: "左上", LML: "左中", LLL: "左下",
    MED: "纵隔", SUB: "膈下",
    ANT: "胸骨后", MID: "肺门", POST: "后野",
  };

  const ZONE_ALIASES = {
    RUL: ["右肺上野", "右上肺", "右上野", "右肺上", "右肺尖"],
    RML: ["右肺中野", "右中肺", "右中野"],
    RLL: ["右肺下野", "右下肺", "右下野", "右肋膈角"],
    LUL: ["左肺上野", "左上肺", "左上野", "左肺上", "左肺尖"],
    LML: ["左肺中野", "左中肺", "左中野"],
    LLL: ["左肺下野", "左下肺", "左下野", "左肋膈角"],
    MED: ["纵隔", "心影", "心脏", "心包", "气管"],
    SUB: ["膈下", "膈肌", "膈面", "胃泡"],
    ANT: ["胸骨后", "前纵隔", "胸骨后间隙"],
    MID: ["肺门", "中区", "肺门区"],
    POST: ["后肺野", "后肋膈角", "后部", "后野"],
  };

  const SCOPE_WORDS = [
    "诊断", "治疗", "手术", "用药", "化疗", "放疗", "预后", "生存期", "能活",
    "是不是癌", "是癌", "良性", "恶性", "要不要", "怎么办", "严重吗", "晚期",
    "早期", "分期", "吃什么药", "怎么治", "能否确诊", "确诊",
    "肺癌", "癌症", "肿瘤", "转移", "治愈", "存活", "能活多久",
  ];

  const S = {
    data: null,
    caseId: null,
    zoneId: null,
    tab: "zone",
    filter: "all",
    query: "",
    qa: [],
    qaDraft: "",
    upload: null,
    showZones: true,
    zoom: 1,
    reportOpen: false,
  };

  /* ---------------- 数据与查询 ---------------- */

  function currentCase() {
    if (!S.data) return null;
    return S.data.cases.find((c) => c.id === S.caseId) || null;
  }

  function currentZone() {
    const c = currentCase();
    if (!c || !S.zoneId) return null;
    return c.zones.find((z) => z.id === S.zoneId) || null;
  }

  function signOf(id) {
    return (S.data && S.data.sign_index && S.data.sign_index[id]) || null;
  }

  function statusLabel(s) {
    return STATUS[s] || s || "未标注";
  }

  function sideLabel(s) {
    return SIDE[s] || s || "侧别未知";
  }

  function enabledCases() {
    return (S.data ? S.data.cases : []).filter((c) => c.enabled);
  }

  function tagsOf(c) {
    const t = [];
    if (!c.signs.length) {
      const allNormal = c.zones.every((z) => z.status === "normal") &&
        c.system.every((x) => x.status === "normal");
      t.push(allNormal ? "正常" : "未见异常");
    }
    if (c.signs.includes("SIGN-002")) t.push("气腔影");
    if (c.signs.includes("SIGN-008")) t.push("气胸");
    if (c.signs.includes("SIGN-007")) t.push("积液");
    if (c.signs.includes("SIGN-003")) t.push("结节");
    if (isTb(c)) t.push("结核");
    return t;
  }

  function isTb(c) {
    const hay = `${c.title} ${c.description_public || ""} ${c.teaching_note || ""}`.toLowerCase();
    return hay.includes("结核") || hay.includes("tuberculosis");
  }

  function summaryOf(c) {
    const ab = c.zones.filter((z) => z.status === "abnormal");
    const un = c.zones.filter((z) => z.status === "unmentioned");
    const lim = c.zones.filter((z) => z.status === "limited");
    if (ab.length) return `异常 ${ab.length} 区`;
    const sysLim = c.system.filter((x) => x.status !== "normal" && x.status !== "unmentioned");
    if (!c.signs.length && !un.length && !lim.length && !sysLim.length) return "正常";
    if (!c.signs.length) return "未见异常";
    return "弥漫/其他";
  }

  function matchFilter(c, f) {
    if (f === "all") return true;
    if (f === "normal") return !c.signs.length;
    if (f === "airspace") return c.signs.includes("SIGN-002");
    if (f === "pneumothorax") return c.signs.includes("SIGN-008");
    if (f === "effusion") return c.signs.includes("SIGN-007");
    if (f === "tb") return isTb(c);
    if (f === "nodule") return c.signs.includes("SIGN-003");
    if (f === "other") {
      return c.signs.length > 0 &&
        !c.signs.includes("SIGN-002") && !c.signs.includes("SIGN-008") &&
        !c.signs.includes("SIGN-007") && !c.signs.includes("SIGN-003") &&
        !isTb(c);
    }
    return true;
  }

  function visibleCases() {
    const q = S.query.trim().toLowerCase();
    return enabledCases().filter((c) => {
      if (!matchFilter(c, S.filter)) return false;
      if (!q) return true;
      const hay = [c.id, c.title, c.quality, c.pose_label, ...tagsOf(c), ...c.signs.map((id) => (signOf(id) || {}).name || "")]
        .join(" ").toLowerCase();
      return hay.includes(q);
    });
  }

  /* ---------------- 渲染：队列 ---------------- */

  function renderQueue() {
    const rows = visibleCases();
    const list = $("#queueList");
    $("#queueCount").textContent = rows.length;
    if (!rows.length) {
      list.innerHTML = `<div class="empty-state"><b>没有匹配的胸片</b><span>换一个筛选条件，或清空搜索词。</span></div>`;
      return;
    }
    list.innerHTML = rows.map((c) => {
      const on = c.id === S.caseId ? " on" : "";
      const tags = Array.from(new Set(tagsOf(c))).map((t) => {
        const cls = (t === "正常" || t === "未见异常") ? "nm" : (t === "气腔影" || t === "气胸" || t === "积液" || t === "结节" ? "ab" : "q");
        return `<span class="q-tag ${cls}">${esc(t)}</span>`;
      }).join("");
      const sum = summaryOf(c);
      const sumTag = Array.from(new Set(tagsOf(c))).includes(sum) ? "" : `<span class="q-tag q">${esc(sum)}</span>`;
      return `<div class="q-row${on}" data-case="${esc(c.id)}">
        <span class="q-no">${esc(c.id.replace("CASE-", ""))}</span>
        <div class="q-main">
          <b>${esc(c.title)}</b>
          <div class="q-tags">${tags}${sumTag}</div>
        </div>
      </div>`;
    }).join("");
  }

  /* ---------------- 渲染：影像 ---------------- */

  function renderViewer() {
    const c = currentCase();
    if (!c) return;
    $("#caseId").textContent = c.id;
    $("#casePose").textContent = `${c.modality} · ${c.pose_label}`;
    $("#caseTitle").textContent = c.title;
    $("#caseMeta").textContent = `${c.quality} · ${c.zones.length} 个教学分区 · ${c.signs.length ? c.signs.map((id) => (signOf(id) || {}).name || id).join(" / ") : "未挂征象词条"}`;
    $("#caseQuality").textContent = c.quality;
    const src = $("#caseSource");
    src.href = c.source_page || "#";
    src.style.display = c.source_page ? "" : "none";

    const img = $("#img");
    const zones = $("#zones");
    const empty = $("#stageEmpty");
    empty.hidden = false;
    empty.innerHTML = `<b>正在载入影像…</b><span>${esc(c.image)}</span>`;

    img.onload = () => {
      empty.hidden = true;
      fitStage();
    };
    img.onerror = () => {
      empty.hidden = false;
      empty.innerHTML = `<b>影像未找到</b><span>${esc(c.image)} · 请确认 outputs/medtrain/images 下存在该文件。</span>`;
    };
    img.src = "../" + c.image;
    if (img.complete && img.naturalWidth) {
      empty.hidden = true;
      fitStage();
    }

    zones.innerHTML = c.zones.map((z) => {
      const on = z.id === S.zoneId ? " on" : "";
      const hide = S.showZones ? "" : " hide";
      const style = `left:${(z.coords[0] * 100).toFixed(2)}%;top:${(z.coords[1] * 100).toFixed(2)}%;width:${(z.coords[2] * 100).toFixed(2)}%;height:${(z.coords[3] * 100).toFixed(2)}%`;
      return `<div class="zone ${z.status}${on}${hide}" data-zone="${esc(z.id)}" style="${style}"
        title="${esc(z.name)} · ${esc(statusLabel(z.status))}">
        <span class="zl">${esc(SHORT[z.id] || z.name)}</span>
      </div>`;
    }).join("");

    $("#srcLine").innerHTML = c.source_page
      ? `来源：<a href="${esc(c.source_page)}" target="_blank" rel="noopener">${esc(c.source_page.replace(/^https?:\/\//, "").slice(0, 82))}</a>`
      : "来源：—";
    $("#licLine").textContent = `${c.license || "许可未标注"} · ${(c.artist || "作者未标注").slice(0, 60)}`;
    $("#bboxMeta").textContent = S.zoneId ? `分区 ${S.zoneId} · ${SIDE[currentZone() ? currentZone().side : ""] || ""}` : "未选分区";

    const zt = $("#zoneToggle");
    if (zt) zt.classList.toggle("on", S.showZones);
    $("#step2").classList.toggle("on", !!S.zoneId);
    $("#step3").classList.toggle("on", !!S.zoneId);
    $("#chainHint").textContent = S.zoneId
      ? `已选：${currentZone().name} · 右栏显示所见与出处`
      : "点影像上的彩色分区，或直接提问";
    applyZoom();
  }

  function fitStage() {
    const stage = $("#stage");
    const frame = $("#frame");
    const img = $("#img");
    if (!stage || !frame || !img || !img.naturalWidth) return;
    const maxW = Math.max(120, stage.clientWidth - 40);
    const maxH = Math.max(120, stage.clientHeight - 40);
    const sc = Math.min(maxW / img.naturalWidth, maxH / img.naturalHeight);
    frame.style.width = Math.round(img.naturalWidth * sc) + "px";
    frame.style.height = Math.round(img.naturalHeight * sc) + "px";
    applyZoom();
  }

  function applyZoom() {
    const frame = $("#frame");
    if (!frame) return;
    frame.style.transform = `scale(${S.zoom})`;
    const badge = $("#zoomBadge");
    if (badge) badge.textContent = Math.round(S.zoom * 100) + "%";
  }

  /* ---------------- 渲染：右栏 ---------------- */

  function renderPanel() {
    const c = currentCase();
    const body = $("#panelBody");
    if (!c) {
      body.innerHTML = `<div class="empty-state"><b>正在载入…</b></div>`;
      return;
    }
    if (S.tab === "zone") body.innerHTML = zoneTabHTML(c);
    else if (S.tab === "system") body.innerHTML = systemTabHTML(c);
    else if (S.tab === "qa") body.innerHTML = qaTabHTML(c);
    else body.innerHTML = sourceTabHTML(c);
    $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === S.tab));
  }

  function zoneTabHTML(c) {
    const z = currentZone();
    const ab = c.zones.filter((x) => x.status === "abnormal");
    const un = c.zones.filter((x) => x.status === "unmentioned");
    const head = `<div class="sec-title">本病例速览</div>
      <div class="zone-card ${ab.length ? "abnormal" : "normal"}">
        <div class="zc-head">
          <b>${esc(c.title)}</b>
          <span class="badge ${ab.length ? "abnormal" : "normal"}">${ab.length ? `异常 ${ab.length} 区` : "未见明确异常"}</span>
        </div>
        <div class="zc-text">${esc(c.description_public || "—")}</div>
        <div class="zc-basis">质量：${esc(c.quality)} · 体位：${esc(c.pose_label)}</div>
      </div>
      ${c.caveats.length ? `<div class="hint-box" style="border-color:#f0d3a8;background:var(--warn-soft)"><b>来源提示：</b>${esc(c.caveats[0])}</div>` : ""}`;

    if (!z) {
      const chips = ab.length
        ? `<div class="chips">${ab.map((x) => `<button class="chip ab" data-zone="${esc(x.id)}">${esc(x.name)} · ${esc(statusLabel(x.status))}</button>`).join("")}</div>`
        : `<div class="hint-box">本病例没有标注为异常的分区。你可以点任意分区，查看“未见异常”的依据。</div>`;
      return `${head}
        <div class="sec-title">从哪看起</div>
        ${chips}
        <div class="hint-box">
          <b>怎么用：</b>点影像上的彩色分区 → 右栏显示该分区的所见、状态与依据。
          青绿=未见异常，琥珀=异常，灰虚线=公开来源未提及，蓝色=判读受限。
        </div>
        ${un.length ? `<div class="hint-box"><b>未提及 ${un.length} 区：</b>公开来源没有逐区描述，本工具不把“未提及”写成“正常”。</div>` : ""}`;
    }

    const signs = (z.sign_ids || []).map((id) => signOf(id)).filter(Boolean);
    const signChips = signs.length
      ? `<div class="chips">${signs.map((s) => `<button class="chip ab" data-sign="${esc(s.id)}">${esc(s.name)} · ${esc(s.en || "")}</button>`).join("")}</div>`
      : `<div class="zc-basis">该分区没有挂征象词条。</div>`;

    return `${head}
      <div class="sec-title">分区所见</div>
      <div class="zone-card ${z.status}">
        <div class="zc-head">
          <b>${esc(z.name)}</b>
          <span class="zc-side">${esc(sideLabel(z.side))}</span>
          <span class="badge ${z.status}">${esc(statusLabel(z.status))}</span>
        </div>
        <div class="zc-text">${esc(z.text)}</div>
        <div class="zc-basis">依据：${esc(z.basis)} · 分区 ${esc(z.id)} · bbox [${z.coords.map((n) => n.toFixed(2)).join(", ")}]</div>
        ${signChips}
      </div>
      <div class="hint-box">
        <b>边界：</b>${esc(z.note || "教学分区，按解剖比例近似，不是病灶分割。")}
        ${z.status === "unmentioned" ? " 该分区为“来源未提及”，不是“正常”。" : ""}
      </div>
      <div class="sys-actions">
        <button class="btn sm" data-ask="${esc(`${z.name}有没有异常？`)}">问这个分区</button>
        <button class="btn sm" data-tab="qa">去问答</button>
      </div>`;
  }

  function systemTabHTML(c) {
    const rows = c.system.map((it) => `<div class="sys-row">
      <i class="sys-dot ${it.status}"></i>
      <div class="sys-main">
        <b>${esc(it.name)} <span class="badge ${it.status}">${esc(statusLabel(it.status))}</span></b>
        <p>${esc(it.text)}</p>
        <em>依据：${esc(it.basis)}</em>
      </div>
    </div>`).join("");
    const ab = c.system.filter((x) => x.status === "abnormal").length;
    return `<div class="sec-title">系统阅片顺序</div>
      <div class="hint-box" style="margin-top:0">
        按“气管与纵隔 → 肺野 → 肺门 → 心影 → 膈肌与肋膈角 → 骨骼与软组织 → 导管与植入物”排列。
        本病例系统所见：<b>${ab ? `${ab} 项异常` : "未见明确异常项"}</b>。
      </div>
      <div style="margin-top:10px">${rows}</div>
      <div class="sys-actions">
        <button class="btn sm" id="reportBtn2">生成阅片记录</button>
        <button class="btn sm" data-tab="qa">针对所见提问</button>
      </div>`;
  }

  function qaTabHTML(c) {
    const ab = c.zones.find((z) => z.status === "abnormal");
    const zoneName = ab ? ab.name : (c.pose === "LAT" ? "后肺野" : "右肺上野");
    const presets = [
      "这张片怎么读？",
      "总结这张片",
      "有没有气胸？",
      "有没有胸腔积液？",
      `${zoneName}有没有异常？`,
    ];
    const log = S.qa.length
      ? S.qa.map((m) => m.role === "user"
        ? `<div class="qa-msg user">${esc(m.text)}</div>`
        : qaAnswerHTML(m.answer)).join("")
      : `<div class="hint-box">
          <b>只答当前病例：</b>${esc(c.id)} · ${esc(c.title)}。
          可以问分区（右肺上野）、征象（气胸/积液/结节）或“这张片怎么读”。
          本页不回答诊断、治疗、分期与预后。
        </div>`;
    return `<div class="qa-log" id="qaLog">${log}</div>
      <div class="qa-presets">${presets.map((p) => `<button data-ask="${esc(p)}">${esc(p)}</button>`).join("")}</div>
      <div class="qa-input">
        <input id="qaInput" value="${esc(S.qaDraft)}" placeholder="问这张胸片：右肺上野有没有异常？" autocomplete="off">
        <button class="btn sm primary" id="qaSend">发送</button>
      </div>`;
  }

  function qaAnswerHTML(a) {
    const cls = a.status === "refuse" ? "refuse" : (a.status === "partial" ? "partial" : "");
    const body = (a.body || []).map((p) => `<p>${esc(p)}</p>`).join("");
    const bullets = (a.bullets && a.bullets.length)
      ? `<ul>${a.bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : "";
    const cites = (a.cites && a.cites.length)
      ? `<div class="qa-cites">${a.cites.map(citeHTML).join("")}</div>` : "";
    return `<div class="qa-msg bot ${cls}">
      <div class="qa-title">${esc(a.title || "回答")}</div>
      <div class="qa-body">${body}${bullets}</div>
      ${cites}
    </div>`;
  }

  function citeHTML(x) {
    const url = x.url
      ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.url.replace(/^https?:\/\//, "").slice(0, 72))}</a>`
      : "";
    const extra = x.extra ? `<span>${esc(x.extra)}</span>` : "";
    return `<div class="cite">
      <b>${esc(x.title)}${x.name ? " · " + esc(x.name) : ""}</b>
      <span>${esc(x.detail || "")}</span>
      ${extra}${url}
    </div>`;
  }

  function sourceTabHTML(c) {
    const upload = S.upload
      ? (S.upload.ok
        ? `<div class="src-block"><b>上传匹配成功</b><p>${esc(S.upload.name)} → ${esc(S.upload.caseId)}（SHA-256 精确匹配）。</p></div>`
        : `<div class="upload-alert">
            <b>该影像未入库，不能定位或回答</b>
            <p>文件：${esc(S.upload.name)} · ${(S.upload.size / 1024).toFixed(0)} KB<br>
            SHA-256：${esc(S.upload.hash || "浏览器不支持，未能计算")}<br>
            静态版只做库内原图的精确匹配，不猜“最像的一例”。请换用左侧队列中的胸片，或在本地服务下接入视觉模型。</p>
          </div>`)
      : "";
    const signs = c.signs.length
      ? `<div class="chips">${c.signs.map((id) => {
        const s = signOf(id);
        return s ? `<button class="chip" data-sign="${esc(s.id)}">${esc(s.name)} · ${esc(s.en || "")}</button>` : "";
      }).join("")}</div>`
      : `<p>本病例未挂征象词条（正常对照或仅做解剖/软组织对照）。</p>`;
    const caveats = c.caveats.length
      ? `<div class="src-block caveat"><b>需要注意</b>${c.caveats.map((x) => `<p>· ${esc(x)}</p>`).join("")}</div>`
      : "";
    const teaching = c.teaching.length
      ? `<div class="src-block"><b>教学要点</b>${c.teaching.map((x) => `<p>· ${esc(x)}</p>`).join("")}</div>`
      : "";
    return `${upload}
      <div class="sec-title">病例出处</div>
      <div class="src-block">
        <b>${esc(c.id)} · ${esc(c.title)}</b>
        <p>${esc(c.description_public || "—")}</p>
        <p>许可：${esc(c.license || "未标注")} · 作者：${esc(c.artist || "未标注")}</p>
        ${c.source_page ? `<a href="${esc(c.source_page)}" target="_blank" rel="noopener">打开来源页 ↗</a>` : ""}
      </div>
      <div class="sec-title">征象词条</div>
      ${signs}
      ${teaching}
      ${caveats}
      <div class="sec-title">数据方法</div>
      <div class="src-block">
        <p>逐区结构化校正（AI 辅助，待医学人员审核）；状态四值：异常 / 未见异常 / 来源未提及 / 判读受限。</p>
        <p>分区框是教学分区，按解剖比例近似，不是病灶分割。未提及的分区不推断为正常。</p>
        <p class="mono">SHA-256 ${esc((c.sha256 || "").slice(0, 16))}…</p>
      </div>
      <div class="sec-title">运行方式</div>
      <div class="src-block">
        <p><b>静态演示层：</b>本页只读 <span class="mono">data/chest/chest_reading.json</span>，不调用后端；上传只做 SHA-256 精确匹配。</p>
        <p><b>DeepWorks：</b>知识库与技能配置见 <span class="mono">docs/Agent接入指南.md</span>；本地服务可用时再叠加 Agent 问答。</p>
        <p>这样现场断网也能逐条复现；不把静态兜底伪装成模型输出。</p>
      </div>`;
  }

  /* ---------------- 问答引擎 ---------------- */

  function isScope(q) {
    return SCOPE_WORDS.some((w) => q.includes(w));
  }

  function isOrder(q) {
    return /怎么读|阅片顺序|读片顺序|系统读|怎么看|读法|读这张/.test(q);
  }

  function isSummary(q) {
    return /有什么异常|有异常|异常吗|所见|总结|报告|这张片|这片|胸片|什么问题|看出什么/.test(q);
  }

  function isHelp(q) {
    return /能问什么|帮助|怎么用|可以问/.test(q);
  }

  function detectZone(q, c) {
    let best = null;
    for (const z of c.zones) {
      const aliases = [z.name, ...(ZONE_ALIASES[z.id] || [])];
      for (const a of aliases) {
        if (!a) continue;
        if (q.includes(a) && (!best || a.length > best.len)) best = { zone: z, len: a.length };
      }
    }
    return best ? best.zone : null;
  }

  function detectSign(q) {
    if (!S.data || !S.data.sign_index) return null;
    let best = null;
    const low = q.toLowerCase();
    for (const s of Object.values(S.data.sign_index)) {
      const names = [s.name, s.en, ...(s.aliases || [])].filter(Boolean);
      for (const a of names) {
        const al = String(a).toLowerCase();
        if (al && low.includes(al) && (!best || al.length > best.len)) best = { sign: s, len: al.length };
      }
    }
    return best ? best.sign : null;
  }

  function caseCite(c) {
    return {
      title: "病例来源",
      name: `${c.id} · ${c.title}`,
      detail: `${c.license || "许可未标注"} · ${c.artist || "作者未标注"}`,
      url: c.source_page,
    };
  }

  function zoneCite(z) {
    return {
      title: "分区标注",
      name: z.name,
      detail: `${statusLabel(z.status)} · 依据：${z.basis} · bbox [${z.coords.map((n) => n.toFixed(2)).join(", ")}]`,
    };
  }

  function sourceById(id) {
    const list = (S.data && S.data.sources && S.data.sources.sources) || [];
    return list.find((x) => x.id === id) || null;
  }

  function signCite(s) {
    const srcs = (s.sources || []).map(sourceById).filter(Boolean);
    const parts = [];
    if ((s.pitfalls || []).length) parts.push("易错点：" + s.pitfalls.join("；"));
    if (srcs.length) parts.push("参考：" + srcs.map((x) => x.title).join("、"));
    return {
      title: "征象词条",
      name: `${s.name} · ${s.en || ""}`,
      detail: s.appearance || "",
      extra: parts.join(" ｜ "),
      url: srcs.length ? srcs[0].url : "",
    };
  }

  function refuse(title, body) {
    return { status: "refuse", title, body, cites: [] };
  }

  function scopeAnswer() {
    return refuse("超出本页范围", [
      "本页只做胸片影像表现、分区定位与出处对照，不提供诊断、分期、治疗或预后判断。",
      "可以换成具体分区或征象来问，例如“右肺上野有没有异常”“有没有气胸”“这张片怎么读”。",
    ]);
  }

  function orderAnswer(c) {
    const bullets = c.system.map((it) => `${it.name}：${statusLabel(it.status)}。${it.text}`);
    return {
      status: "answer",
      title: "胸片系统阅片顺序",
      body: [
        "建议按固定顺序读，避免只看最显眼的一处：气管与纵隔 → 肺野 → 肺门 → 心影 → 膈肌与肋膈角 → 骨骼与软组织 → 导管与植入物。",
        `当前病例是 ${c.id} · ${c.title}（${c.pose_label}）。`,
      ],
      bullets,
      cites: [caseCite(c)],
    };
  }

  function zoneAnswer(c, z, sign) {
    if (sign) return zoneSignAnswer(c, z, sign);
    let body = [z.text];
    if (z.status === "unmentioned") {
      body.push("这条不是“正常”，而是“公开来源没有逐区描述”。本工具不把它推断成正常或异常。");
    } else if (z.status === "limited") {
      body.push("判读受限的原因见影像质量说明；受限不等于正常。");
    } else if (z.status === "normal") {
      body.push("该分区在本病例的公开说明中为未见明确异常；这不等于排除了所有细微病变。");
    } else {
      body.push("该分区在本病例的公开说明/图注中标注为异常。");
    }
    const signs = (z.sign_ids || []).map(signOf).filter(Boolean);
    if (signs.length) body.push(`相关征象：${signs.map((s) => s.name).join("、")}。`);
    return {
      status: z.status === "abnormal" || z.status === "normal" ? "answer" : "partial",
      title: `${z.name} · ${statusLabel(z.status)}`,
      body,
      cites: [caseCite(c), zoneCite(z), ...signs.map(signCite)],
    };
  }

  function zoneSignAnswer(c, z, sign) {
    const inZone = (z.sign_ids || []).includes(sign.id);
    let status = "partial";
    let body = [];
    if (inZone) {
      status = "answer";
      body.push(`是。该分区标注包含「${sign.name}」：${z.text}`);
    } else if (z.status === "normal") {
      body.push(`该分区标注为未见明确异常，公开说明未提及「${sign.name}」。不能据此排除，也不能据此诊断。`);
    } else if (z.status === "unmentioned") {
      body.push(`该分区在本病例中没有逐区描述，不能判断有没有「${sign.name}」。`);
    } else if (z.status === "limited") {
      body.push(`该分区判读受限，不能可靠判断有没有「${sign.name}」。`);
    } else {
      body.push(`该分区标注为「${statusLabel(z.status)}」，没有标注「${sign.name}」；不能据此排除。`);
    }
    body.push(`征象释义：${sign.appearance}`);
    if ((sign.pitfalls || []).length) body.push(`易错点：${sign.pitfalls.join("；")}。`);
    return {
      status,
      title: `${z.name} · ${sign.name}`,
      body,
      cites: [caseCite(c), zoneCite(z), signCite(sign)],
    };
  }

  function signAnswer(c, sign) {
    const hits = c.zones.filter((z) => (z.sign_ids || []).includes(sign.id));
    let status = hits.length ? "answer" : "partial";
    let body = [];
    if (hits.length) {
      body.push(`本病例的公开说明/标注中出现「${sign.name}」，位于：${hits.map((z) => z.name).join("、")}。`);
      body.push(hits[0].text);
    } else {
      body.push(`本病例的公开说明未提及「${sign.name}」。不能据此排除，也不能据此诊断。`);
      body.push("如果问题指向其他病例，请先在左侧切换病例；本页不跨病例拼答案。");
    }
    body.push(`征象释义：${sign.appearance}`);
    if ((sign.pitfalls || []).length) body.push(`易错点：${sign.pitfalls.join("；")}。`);
    return {
      status,
      title: `征象 · ${sign.name}`,
      body,
      cites: [caseCite(c), ...hits.map(zoneCite), signCite(sign)],
    };
  }

  function summaryAnswer(c) {
    const ab = c.zones.filter((z) => z.status === "abnormal");
    const un = c.zones.filter((z) => z.status === "unmentioned");
    const lim = c.zones.filter((z) => z.status === "limited");
    const sysAb = c.system.filter((x) => x.status === "abnormal");
    let body = [];
    if (ab.length) {
      body.push(`本病例公开说明的异常位于：${ab.map((z) => z.name).join("、")}。`);
    } else if (!c.signs.length) {
      body.push("本病例公开说明为正常胸片；已标注分区均未见明确异常。");
    } else {
      body.push("本病例没有逐区标注为异常的分区；公开说明的描述见下方系统所见。");
    }
    if (sysAb.length) body.push(`系统所见异常：${sysAb.map((x) => x.name + "（" + x.text + "）").join("；")}。`);
    if (un.length) body.push(`另有 ${un.length} 个分区公开来源未逐区描述，本工具不作正常/异常推断。`);
    if (lim.length) body.push(`有 ${lim.length} 个分区判读受限，受限不等于正常。`);
    if (c.caveats.length) body.push(`需要注意：${c.caveats.join("；")}。`);
    return {
      status: ab.length || (!un.length && !lim.length) ? "answer" : "partial",
      title: `${c.id} · 阅片摘要`,
      body,
      cites: [caseCite(c), ...ab.slice(0, 3).map(zoneCite)],
    };
  }

  function fallbackAnswer(c, q) {
    return {
      status: "partial",
      title: "没有匹配到库内分区或征象",
      body: [
        `没有在「${c.title}」里识别到与“${q}”对应的分区或征象词条。`,
        "可以直接点影像上的分区，或换用库内说法：右肺上野 / 右肺中野 / 右肺下野 / 左肺上野 / 左肺中野 / 左肺下野 / 纵隔与心影 / 膈下；征象如气胸、胸腔积液、实变、结节、磨玻璃影。",
      ],
      cites: [caseCite(c)],
    };
  }

  function answer(q) {
    const c = currentCase();
    if (!c) return refuse("未选择病例", ["先在左侧选一例胸片。"]);
    const text = q.trim();
    if (!text) return refuse("问题为空", ["输入一个分区或征象，例如“右肺上野有没有异常”。"]);
    if (isScope(text)) return scopeAnswer();
    const zone = detectZone(text, c);
    const sign = detectSign(text);
    if (zone) return zoneAnswer(c, zone, sign);
    if (sign) return signAnswer(c, sign);
    if (isOrder(text)) return orderAnswer(c);
    if (isSummary(text)) return summaryAnswer(c);
    if (isHelp(text)) {
      return {
        status: "answer",
        title: "可以这样问",
        body: ["分区：右肺上野 / 左肺下野 / 纵隔与心影……", "征象：气胸 / 胸腔积液 / 实变 / 结节 / 磨玻璃影……", "流程：这张片怎么读 / 总结这张片。"],
        cites: [caseCite(c)],
      };
    }
    return fallbackAnswer(c, text);
  }

  function ask(q) {
    const text = String(q || "").trim();
    if (!text) return;
    S.qa.push({ role: "user", text });
    S.qa.push({ role: "bot", answer: answer(text) });
    S.qaDraft = "";
    S.tab = "qa";
    renderPanel();
    requestAnimationFrame(() => {
      const log = $("#qaLog");
      if (log) log.scrollIntoView({ block: "end", behavior: "smooth" });
    });
  }

  /* ---------------- 阅片记录 ---------------- */

  function buildReport() {
    const c = currentCase();
    if (!c) return "";
    const L = [];
    L.push("胸片阅片记录（教学用，非诊断）");
    L.push("=".repeat(38));
    L.push(`病例：${c.id} · ${c.title}`);
    L.push(`体位：${c.pose_label} · 质量：${c.quality}`);
    L.push(`来源：${c.source_page || "—"}`);
    L.push(`许可：${c.license || "未标注"} · 作者：${c.artist || "未标注"}`);
    L.push("");
    L.push("一、影像质量");
    L.push(`  ${c.quality}`);
    L.push("");
    L.push("二、系统所见");
    for (const it of c.system) {
      L.push(`  ${it.name}：${statusLabel(it.status)}。${it.text}（依据：${it.basis}）`);
    }
    L.push("");
    L.push("三、分区所见");
    for (const z of c.zones) {
      L.push(`  ${z.name}（${sideLabel(z.side)}）：${statusLabel(z.status)}。${z.text}（依据：${z.basis}）`);
    }
    L.push("");
    L.push("四、征象对照");
    if (c.signs.length) {
      for (const id of c.signs) {
        const s = signOf(id);
        if (s) L.push(`  ${s.name}（${s.en || ""}）：${s.appearance}`);
      }
    } else {
      L.push("  本病例未挂征象词条。");
    }
    if (c.caveats.length) {
      L.push("");
      L.push("五、需要注意");
      for (const x of c.caveats) L.push(`  · ${x}`);
    }
    L.push("");
    L.push("六、边界与声明");
    L.push("  本记录只复述公开来源、原图标注与本库结构化校正，不构成诊断意见，不替代临床决策。");
    L.push("  分区框为教学分区，不是病灶分割；未提及的分区不作正常或异常推断。");
    L.push("  正式教学或对外发布前，须由具备资质的医学人员逐条审核。");
    return L.join("\n");
  }

  function openReport() {
    const text = buildReport();
    if (!text) return;
    $("#reportText").textContent = text;
    $("#reportMask").hidden = false;
    S.reportOpen = true;
  }

  function closeReport() {
    $("#reportMask").hidden = true;
    S.reportOpen = false;
  }

  function copyReport() {
    const text = $("#reportText").textContent || "";
    const done = () => toast("已复制阅片记录");
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

  function downloadReport() {
    const c = currentCase();
    if (!c) return;
    const text = $("#reportText").textContent || buildReport();
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${c.id}_胸片阅片记录.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  /* ---------------- 上传 ---------------- */

  async function sha256Hex(buf) {
    if (!window.crypto || !window.crypto.subtle) return "";
    const d = await window.crypto.subtle.digest("SHA-256", buf);
    return Array.from(new Uint8Array(d)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  async function handleUpload(file) {
    if (!file) return;
    let hash = "";
    try {
      hash = await sha256Hex(await file.arrayBuffer());
    } catch (e) {
      hash = "";
    }
    const hit = hash ? enabledCases().find((c) => c.sha256 === hash || c.sha256_source === hash) : null;
    if (hit) {
      S.upload = { ok: true, name: file.name, size: file.size, hash, caseId: hit.id };
      selectCase(hit.id);
      toast(`已匹配库内病例 ${hit.id}`);
    } else {
      S.upload = { ok: false, name: file.name, size: file.size, hash };
      S.tab = "source";
      renderPanel();
      toast("该影像未入库，不能定位或回答");
    }
  }

  /* ---------------- 交互 ---------------- */

  function selectCase(id) {
    const c = S.data.cases.find((x) => x.id === id);
    if (!c || !c.enabled) return;
    S.caseId = id;
    S.zoneId = null;
    S.qa = [];
    S.qaDraft = "";
    S.zoom = 1;
    S.upload = null;
    S.tab = "zone";
    render();
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function selectZone(id) {
    const c = currentCase();
    if (!c) return;
    const z = c.zones.find((x) => x.id === id);
    if (!z) return;
    S.zoneId = id;
    S.tab = "zone";
    renderViewer();
    renderPanel();
  }

  function render() {
    renderQueue();
    renderViewer();
    renderPanel();
  }

  function toast(msg) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("on");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("on"), 2400);
  }

  function bind() {
    document.addEventListener("click", (e) => {
      const qRow = e.target.closest("[data-case]");
      if (qRow) { selectCase(qRow.dataset.case); return; }

      const f = e.target.closest("[data-f]");
      if (f) {
        S.filter = f.dataset.f;
        $$("#filters button").forEach((b) => b.classList.toggle("on", b === f));
        renderQueue();
        return;
      }

      const tab = e.target.closest("[data-tab]");
      if (tab) { S.tab = tab.dataset.tab; renderPanel(); return; }

      const zone = e.target.closest("[data-zone]");
      if (zone) { selectZone(zone.dataset.zone); return; }

      const askBtn = e.target.closest("[data-ask]");
      if (askBtn) { ask(askBtn.dataset.ask); return; }

      const signBtn = e.target.closest("[data-sign]");
      if (signBtn) {
        const s = signOf(signBtn.dataset.sign);
        if (s) {
          S.qa.push({ role: "user", text: `「${s.name}」是什么？` });
          S.qa.push({
            role: "bot",
            answer: {
              status: "answer",
              title: `征象 · ${s.name}`,
              body: [`定义：${s.appearance}`, `可见于：${(s.may_see_in || []).join("、") || "—"}`, `易错点：${(s.pitfalls || []).join("；") || "—"}`],
              cites: [signCite(s)],
            },
          });
          S.tab = "qa";
          renderPanel();
        }
        return;
      }
    });

    $("#q").addEventListener("input", (e) => {
      S.query = e.target.value;
      renderQueue();
    });

    $("#zoneToggle").addEventListener("click", () => {
      S.showZones = !S.showZones;
      $("#zoneToggle").classList.toggle("on", S.showZones);
      $$("#zones .zone").forEach((z) => z.classList.toggle("hide", !S.showZones));
    });

    $("#fitBtn").addEventListener("click", fitStage);
    $("#zoomIn").addEventListener("click", () => { S.zoom = Math.min(2.4, +(S.zoom + 0.15).toFixed(2)); applyZoom(); });
    $("#zoomOut").addEventListener("click", () => { S.zoom = Math.max(1, +(S.zoom - 0.15).toFixed(2)); applyZoom(); });

    let drag = null;
    const framePoint = (e) => {
      const r = $("#frame").getBoundingClientRect();
      return {
        x: clamp((e.clientX - r.left) / Math.max(1, r.width), 0, 1),
        y: clamp((e.clientY - r.top) / Math.max(1, r.height), 0, 1),
      };
    };
    const selbox = $("#selbox");
    const paintSel = (a, b) => {
      if (!selbox) return;
      selbox.style.left = (Math.min(a.x, b.x) * 100).toFixed(2) + "%";
      selbox.style.top = (Math.min(a.y, b.y) * 100).toFixed(2) + "%";
      selbox.style.width = (Math.abs(b.x - a.x) * 100).toFixed(2) + "%";
      selbox.style.height = (Math.abs(b.y - a.y) * 100).toFixed(2) + "%";
      selbox.hidden = false;
    };
    $("#frame").addEventListener("pointerdown", (e) => {
      if (e.pointerType === "touch") return;
      if (e.target.closest(".zone")) return;
      drag = { a: framePoint(e), b: framePoint(e) };
      paintSel(drag.a, drag.b);
      e.preventDefault();
    });
    document.addEventListener("pointermove", (e) => {
      if (!drag) return;
      drag.b = framePoint(e);
      paintSel(drag.a, drag.b);
    });
    document.addEventListener("pointerup", () => {
      if (!drag) return;
      const a = drag.a, b = drag.b;
      drag = null;
      if (selbox) selbox.hidden = true;
      const box = [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y)];
      if (box[2] < 0.02 || box[3] < 0.02) {
        toast("拖框太小，请框住一个分区");
        return;
      }
      const c = currentCase();
      if (!c || !window.YZLocate) return;
      const res = window.YZLocate.locate(c.zones, box);
      if (res.status === "single" && res.primary) {
        selectZone(res.primary.region.id);
        toast(`框选命中 ${res.primary.region.name}`);
      } else {
        toast(res.message || "未命中单一分区，请缩小范围或直接点分区");
      }
    });
    document.addEventListener("pointercancel", () => {
      drag = null;
      if (selbox) selbox.hidden = true;
    });

    $("#fileInput").addEventListener("change", (e) => {
      const f = e.target.files && e.target.files[0];
      if (f) handleUpload(f);
      e.target.value = "";
    });

    $("#reportBtn").addEventListener("click", openReport);
    $("#reportBtn2") && $("#reportBtn2").addEventListener("click", openReport);
    $("#reportClose").addEventListener("click", closeReport);
    $("#reportCopy").addEventListener("click", copyReport);
    $("#reportDownload").addEventListener("click", downloadReport);
    $("#reportMask").addEventListener("click", (e) => {
      if (e.target.id === "reportMask") closeReport();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && S.reportOpen) closeReport();
      if (e.key === "Enter" && e.target && e.target.id === "qaInput") {
        e.preventDefault();
        ask(e.target.value);
      }
    });

    document.addEventListener("input", (e) => {
      if (e.target && e.target.id === "qaInput") S.qaDraft = e.target.value;
    });

    document.addEventListener("click", (e) => {
      if (e.target && e.target.id === "qaSend") {
        const input = $("#qaInput");
        ask(input ? input.value : S.qaDraft);
      }
      if (e.target && e.target.id === "reportBtn2") openReport();
    });

    window.addEventListener("resize", () => {
      clearTimeout(bind._rz);
      bind._rz = setTimeout(fitStage, 120);
    });
  }

  /* ---------------- 启动 ---------------- */

  async function boot() {
    try {
      const r = await fetch(DATA_URL, { cache: "no-cache" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      S.data = await r.json();
    } catch (e) {
      $("#queueList").innerHTML = `<div class="empty-state"><b>胸片数据载入失败</b><span>${esc(DATA_URL)}<br>请先运行 python3 kb/scripts/build_chest_reading.py。</span></div>`;
      $("#stageEmpty").innerHTML = `<b>胸片数据未载入</b><span>${esc(String(e.message || e))}</span>`;
      return;
    }
    const first = enabledCases()[0];
    const qp = (() => { try { return new URLSearchParams(location.search).get("case") || ""; } catch (e) { return ""; } })();
    const deep = qp ? enabledCases().find((c) => c.id === qp) : null;
    if (deep) S.caseId = deep.id;
    else if (first) S.caseId = first.id;
    bind();
    render();
    $("#barNote").textContent = `CR 胸部 · ${enabledCases().length} 例逐区校正`;
  }

  boot();
})();
