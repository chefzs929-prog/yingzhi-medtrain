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
  const IMG_SIDE = { right: "图像左侧", left: "图像右侧", midline: "图像中线" };
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
    qaMode: "kb",
    agent: { messages: [], draft: "", running: false },
    upload: null,
    showZones: true,
    zoom: 1,
    reportOpen: false,
    task: null,
    quiz: {
      zoneIds: [],
      zoneNone: false,
      status: "",
      signs: [],
      signsTouched: false,
      result: null,
      redo: false,
    },
  };

  /* ---------------- 课堂任务 ---------------- */

  function quizSubmitted(caseId) {
    if (!S.task) return false;
    if (S.quiz.redo) return false;
    return !!(S.quiz.result && S.quiz.result.caseId === caseId) ||
      !!taskAttempt(caseId);
  }

  function taskAttempt(caseId) {
    if (!S.task || !S.task.attempts) return null;
    return S.task.attempts.find((a) => a.caseId === caseId) || null;
  }

  function taskDoneCount() {
    if (!S.task) return 0;
    return new Set((S.task.attempts || []).map((a) => a.caseId)).size;
  }

  function syncTaskChrome() {
    const banner = $("#taskBanner");
    if (!banner) return;
    if (!S.task) {
      banner.hidden = true;
      return;
    }
    const a = S.task.assignment;
    const done = taskDoneCount();
    const total = a.caseIds.length;
    document.body.classList.toggle("task-locked", !quizSubmitted(S.caseId));
    banner.hidden = false;
    banner.innerHTML = `<div class="tb-main">
        <span class="tb-kicker">课堂任务</span>
        <b>${esc(a.title)}</b>
        <span class="tb-meta">${done}/${total} 例 · 截止 ${esc(a.due || "待定")} · ${esc(S.task.student.name)}</span>
      </div>
      <div class="tb-actions">
        <button class="btn sm" id="taskGoQuiz">去作答</button>
        <button class="btn sm" id="taskJumpNext">下一例未完成</button>
        <a class="btn sm" href="classroom.html?role=student">返回课堂</a>
        <a class="btn sm ghost" href="clinic.html">退出作业</a>
      </div>`;
  }

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
    let list = (S.data ? S.data.cases : []).filter((c) => c.enabled);
    if (S.task) {
      const ids = S.task.assignment.caseIds;
      list = ids.map((id) => list.find((c) => c.id === id)).filter(Boolean);
    }
    return list;
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
    if (S.task) return enabledCases();
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
    list.innerHTML = rows.map((c, idx) => {
      const on = c.id === S.caseId ? " on" : "";
      const reveal = !S.task || quizSubmitted(c.id);
      const title = reveal ? c.title : `考核病例 ${idx + 1} · ${c.pose_label}`;
      const tags = reveal ? Array.from(new Set(tagsOf(c))).map((t) => {
        const cls = (t === "正常" || t === "未见异常") ? "nm" : (t === "气腔影" || t === "气胸" || t === "积液" || t === "结节" ? "ab" : "q");
        return `<span class="q-tag ${cls}">${esc(t)}</span>`;
      }).join("") : `<span class="q-tag q">待作答</span>`;
      const sum = reveal ? summaryOf(c) : "";
      const sumTag = reveal && !Array.from(new Set(tagsOf(c))).includes(sum) ? `<span class="q-tag q">${esc(sum)}</span>` : "";
      const doneTag = S.task && reveal ? `<span class="q-tag nm">已提交</span>` : "";
      return `<div class="q-row${on}" data-case="${esc(c.id)}">
        <span class="q-no">${esc(c.id.replace("CASE-", ""))}</span>
        <div class="q-main">
          <b>${esc(title)}</b>
          <div class="q-tags">${tags}${sumTag}${doneTag}</div>
        </div>
      </div>`;
    }).join("");
  }

  /* ---------------- 渲染：影像 ---------------- */

  function renderViewer() {
    const up = S.upload;
    if (up && up.generic && up.url) { renderUploadViewer(up); return; }
    const c = currentCase();
    if (!c) return;
    const reveal = !S.task || quizSubmitted(c.id);
    const taskIndex = S.task ? S.task.assignment.caseIds.indexOf(c.id) + 1 : 0;
    $("#caseId").textContent = c.id;
    $("#casePose").textContent = `${c.modality} · ${c.pose_label}`;
    $("#caseTitle").textContent = reveal ? c.title : `考核病例 ${taskIndex} · ${c.pose_label}`;
    $("#caseMeta").textContent = reveal
      ? `${c.quality} · ${c.zones.length} 个教学分区 · ${c.signs.length ? c.signs.map((id) => (signOf(id) || {}).name || id).join(" / ") : "未挂征象词条"}`
      : "考核模式 · 提交后显示病例信息与征象";
    $("#caseQuality").textContent = reveal ? c.quality : "考核模式";
    const src = $("#caseSource");
    src.href = c.source_page || "#";
    src.style.display = reveal && c.source_page ? "" : "none";

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
      empty.innerHTML = `<b>影像未找到</b><span>请确认知识库影像目录可访问。</span>`;
    };
    img.src = window.RCKB ? window.RCKB.imageUrl(c.image) : "../" + c.image;
    if (img.complete && img.naturalWidth) {
      empty.hidden = true;
      fitStage();
    }

    zones.innerHTML = c.zones.map((z) => {
      const on = S.task && !reveal
        ? (!S.quiz.zoneNone && S.quiz.zoneIds.includes(z.id) ? " on" : "")
        : (z.id === S.zoneId ? " on" : "");
      const hide = S.showZones ? "" : " hide";
      const statusClass = reveal ? z.status : "quiz";
      const style = `left:${(z.coords[0] * 100).toFixed(2)}%;top:${(z.coords[1] * 100).toFixed(2)}%;width:${(z.coords[2] * 100).toFixed(2)}%;height:${(z.coords[3] * 100).toFixed(2)}%`;
      return `<div class="zone ${statusClass}${on}${hide}" data-zone="${esc(z.id)}" style="${style}"
        title="${esc(z.name)}${reveal ? " · " + esc(statusLabel(z.status)) : ""}">
        <span class="zl">${esc(SHORT[z.id] || z.name)}</span>
      </div>`;
    }).join("");

    if (reveal) {
      $("#srcLine").innerHTML = c.source_page
        ? `来源：<a href="${esc(c.source_page)}" target="_blank" rel="noopener">${esc(c.source_page.replace(/^https?:\/\//, "").slice(0, 82))}</a>`
        : "来源：—";
      $("#licLine").textContent = `${c.license || "许可未标注"} · ${(c.artist || "作者未标注").slice(0, 60)}${c.source_note ? " · " + c.source_note : ""}`;
      const zSel = currentZone();
      $("#bboxMeta").textContent = S.zoneId
        ? `分区 ${S.zoneId} · ${SIDE[zSel ? zSel.side : ""] || ""}${zSel ? `（${IMG_SIDE[zSel.side] || "—"}）` : ""}`
        : "未选分区";
    } else {
      $("#srcLine").textContent = "考核模式 · 提交后显示来源";
      $("#licLine").textContent = "提交后显示许可与作者";
      $("#bboxMeta").textContent = S.quiz.zoneNone
        ? "已选择：未见明确异常分区 · 提交后揭示状态"
        : (S.quiz.zoneIds.length
          ? `已选择 ${S.quiz.zoneIds.length} 个分区 · 提交后揭示状态`
          : "请选择异常分区（可多选）");
    }

    const legend = $("#legend");
    if (legend) legend.style.display = reveal ? "" : "none";
    const zt = $("#zoneToggle");
    if (zt) zt.classList.toggle("on", S.showZones);
    const quizZonePicked = S.quiz.zoneNone || S.quiz.zoneIds.length > 0;
    $("#step2").classList.toggle("on", S.task ? quizZonePicked : !!S.zoneId);
    $("#step3").classList.toggle("on", S.task ? reveal : !!S.zoneId);
    $("#chainHint").textContent = S.task && !reveal
      ? (quizZonePicked
        ? `已选择 ${S.quiz.zoneNone ? "未见明确异常分区" : S.quiz.zoneIds.length + " 个分区"} · 到右栏完成判读与征象`
        : "点影像分区作答（可多选），或到右栏课堂任务")
      : (S.zoneId ? `已选：${currentZone().name}` : "");
    applyZoom();
    syncTaskChrome();
  }

  function renderUploadViewer(up) {
    const v = up.vision || {};
    const loc = v.locate || {};
    const reg = (loc.primary && loc.primary.region) || {};
    const revealed = !!reg.name && !up.needsConfirm;
    $("#caseId").textContent = "上传影像";
    $("#casePose").textContent = v.vision_used ? "胸片 · 视觉定位" : "胸片 · 模板定位";
    $("#caseTitle").textContent = up.name || "上传影像";
    $("#caseMeta").textContent = up.locating ? "视觉定位中…"
      : (up.needsConfirm ? "未确认影像类型 · 暂不做分区判断"
        : (revealed ? `${reg.name} · ${loc.status || ""} · 模板推断（非人工）`
          : (up.notChest ? "非胸片：本产品暂不支持" : "未定位到分区")));
    $("#caseQuality").textContent = "非人工标注";
    const src = $("#caseSource");
    src.style.display = "none";

    const img = $("#img");
    const zones = $("#zones");
    const empty = $("#stageEmpty");
    empty.hidden = false;
    empty.innerHTML = `<b>正在载入上传影像…</b>`;
    img.onload = () => { empty.hidden = true; fitStage(); };
    img.onerror = () => { empty.hidden = false; empty.innerHTML = `<b>影像无法显示</b><span>文件可能不是浏览器可解码的图片。</span>`; };
    img.src = up.url;
    if (img.complete && img.naturalWidth) { empty.hidden = true; fitStage(); }

    const bb = reg.coords || up.bbox;
    zones.innerHTML = (revealed && bb)
      ? `<div class="zone on" style="left:${(bb[0] * 100).toFixed(2)}%;top:${(bb[1] * 100).toFixed(2)}%;width:${(bb[2] * 100).toFixed(2)}%;height:${(bb[3] * 100).toFixed(2)}%"><span class="zl">${esc(reg.name)}</span></div>`
      : "";

    $("#srcLine").textContent = "上传影像：仅在浏览器内显示，不上传服务器、不落盘";
    $("#licLine").textContent = "非诊断用途 · 请勿上传真实患者影像";
    $("#bboxMeta").textContent = revealed ? `模板分区 ${reg.name}（非人工）` : "未定位到分区";
    $("#step2").classList.remove("on");
    $("#step3").classList.remove("on");
    $("#chainHint").textContent = revealed ? "上传影像已定位；到右栏「出处」查看双引用" : "";
    const legend = $("#legend");
    if (legend) legend.style.display = "none";
    applyZoom();
    syncTaskChrome();
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

  function syncTabs() {
    const taskBtn = $("#taskTab");
    if (!taskBtn) return;
    taskBtn.hidden = !S.task;
    if (!S.task) {
      $$("#tabs button").forEach((b) => { b.hidden = false; });
      return;
    }
    const locked = !quizSubmitted(S.caseId);
    $$("#tabs button").forEach((b) => {
      if (b.dataset.tab === "task") b.hidden = false;
      else b.hidden = locked;
    });
    if (locked) S.tab = "task";
  }

  function renderPanel() {
    const c = currentCase();
    const body = $("#panelBody");
    if (!c) {
      body.innerHTML = `<div class="empty-state"><b>正在载入…</b></div>`;
      return;
    }
    syncTabs();
    if (S.tab === "task" && S.task) body.innerHTML = taskTabHTML(c);
    else if (S.tab === "zone") body.innerHTML = zoneTabHTML(c);
    else if (S.tab === "system") body.innerHTML = systemTabHTML(c);
    else if (S.tab === "qa") body.innerHTML = qaTabHTML(c);
    else body.innerHTML = sourceTabHTML(c);
    $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === S.tab));
  }

  function signNames(ids) {
    return (ids || []).map((id) => (signOf(id) || {}).name || id).filter(Boolean).join("、");
  }

  function zoneNames(c, ids) {
    const list = (ids || []).map((id) => (c.zones.find((z) => z.id === id) || {}).name).filter(Boolean);
    return list.length ? list.join("、") : "未见明确异常分区";
  }

  function taskTabHTML(c) {
    if (!S.task) return `<div class="empty-state"><b>当前不在课堂任务中</b><span>从课堂作业进入，或直接使用分区阅片。</span></div>`;
    const a = S.task.assignment;
    const idx = a.caseIds.indexOf(c.id) + 1;
    const total = a.caseIds.length;
    const reveal = quizSubmitted(c.id);
    const attempt = S.quiz.result || taskAttempt(c.id);
    if (reveal && attempt) {
      const d = attempt.detail || {};
      const score = attempt.score;
      const allDone = taskDoneCount() >= total;
      const answeredIds = Array.isArray(d.answeredZoneIds) && d.answeredZoneIds.length
        ? d.answeredZoneIds
        : (d.answeredZoneId && d.answeredZoneId !== "none" ? [d.answeredZoneId] : []);
      const answeredZone = d.answeredZoneNone || d.answeredZoneId === "none" || !answeredIds.length
        ? "未见明确异常分区"
        : zoneNames(c, answeredIds);
      const correctZone = zoneNames(c, d.correctZoneIds);
      return `<div class="task-quiz-head">
          <div class="tq-kicker">课堂任务 · 第 ${idx}/${total} 例 · 已提交</div>
          <h3>${esc(c.title)}</h3>
          <p>提交后已解锁分区所见、系统阅片与出处。先对照，再决定是否重做。</p>
        </div>
        <div class="quiz-result ${score >= 60 ? "ok" : "bad"}">
          <div class="qr-top">
            <div class="qr-score">${score}<span>/100</span></div>
            <div class="qr-lines">
              <div class="${d.zoneOk ? "ok" : "bad"}"><b>定位</b><span>${d.zonePoints || 0}/40 · ${d.zoneOk ? "正确" : (d.zonePoints ? "部分正确" : "错误")}</span></div>
              <div class="${d.statusOk ? "ok" : "bad"}"><b>判读</b><span>${d.statusPoints || 0}/30 · ${d.statusOk ? "正确" : "错误"}</span></div>
              <div class="${d.signRatio >= 0.8 ? "ok" : "bad"}"><b>征象</b><span>${d.signPoints || 0}/30 · ${Math.round((d.signRatio || 0) * 100)}%</span></div>
            </div>
          </div>
          <div class="qr-answer">
            <p><b>你的作答：</b>${esc(answeredZone)} · ${esc(statusLabel(d.answeredStatus))} · ${esc(signNames(d.answeredSigns) || "未见明确征象")}</p>
            <p><b>正确答案：</b>${esc(correctZone)} · ${esc(statusLabel(d.expectedStatus))} · ${esc(signNames(d.expectedSigns) || "无明确征象")}</p>
            <p class="qr-note">定位题按选中的异常分区计分：选全得分，漏选、错选都会扣分；判读题按你选择分区的共同状态判分；征象题按命中数减错选计分。</p>
          </div>
          <div class="sys-actions">
            <button class="btn sm primary" data-quiz-next>${allDone ? "全部完成，返回课堂" : "下一例"}</button>
            <button class="btn sm" data-quiz-redo>重做本病例</button>
            <button class="btn sm" data-tab="zone">对照分区所见</button>
          </div>
        </div>`;
    }

    const opts = window.RCClass ? window.RCClass.signOptions(c) : { options: c.signs.slice() };
    const zoneOpts = c.zones.map((z) =>
      `<button class="qopt ${!S.quiz.zoneNone && S.quiz.zoneIds.includes(z.id) ? "on" : ""}" data-quiz-zone="${esc(z.id)}">${esc(z.name)}</button>`).join("");
    const statusOpts = Object.keys(STATUS).map((k) =>
      `<button class="qopt ${S.quiz.status === k ? "on" : ""}" data-quiz-status="${k}">${esc(STATUS[k])}</button>`).join("");
    const signOpts = opts.options.map((id) =>
      `<button class="qopt sign ${S.quiz.signs.includes(id) ? "on" : ""}" data-quiz-sign="${esc(id)}">${esc((signOf(id) || {}).name || id)}</button>`).join("");
    const noneOn = S.quiz.signsTouched && !S.quiz.signs.length ? " on" : "";
    const zonePicked = S.quiz.zoneNone || S.quiz.zoneIds.length > 0;
    const canSubmit = zonePicked && !!S.quiz.status && S.quiz.signsTouched;

    return `<div class="task-quiz-head">
        <div class="tq-kicker">课堂任务 · 第 ${idx}/${total} 例 · ${esc(S.task.student.name)}</div>
        <h3>考核病例 · ${esc(c.pose_label)}</h3>
        <p>病例标题、分区颜色与出处暂时隐藏。先自己读片，提交后再对照。</p>
      </div>
      <div class="quiz-q">
        <div class="quiz-qh"><b>1</b><span>异常所见主要位于哪些分区？</span><em>40 分 · 可多选</em></div>
        <div class="quiz-opts">${zoneOpts}
          <button class="qopt ${S.quiz.zoneNone ? "on" : ""}" data-quiz-zone="none">未见明确异常分区</button>
        </div>
      </div>
      <div class="quiz-q">
        <div class="quiz-qh"><b>2</b><span>${S.quiz.zoneNone
          ? "本病例整体最符合哪种状态？"
          : (S.quiz.zoneIds.length > 1 ? "这些分区整体是什么状态？" : "你选择的分区是什么状态？")}</span><em>30 分</em></div>
        <div class="quiz-opts">${statusOpts}</div>
        ${S.quiz.zoneIds.length > 1 ? `<p class="quiz-hint" style="margin-top:6px">多选分区按共同状态作答；如果状态不一致，请只选异常分区。</p>` : ""}
      </div>
      <div class="quiz-q">
        <div class="quiz-qh"><b>3</b><span>本病例标注的征象是？</span><em>30 分 · 可多选</em></div>
        <div class="quiz-opts">${signOpts}
          <button class="qopt sign${noneOn}" data-quiz-sign="none">未见明确征象</button>
        </div>
      </div>
      <div class="quiz-submit">
        <button class="btn solid wide" id="quizSubmit" ${canSubmit ? "" : "disabled"}>提交本病例</button>
        <span class="quiz-hint">${canSubmit ? "提交后立即评分并解锁对照。" : "三题都作答后才能提交。"}</span>
      </div>`;
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
        : `<div class="hint-box">本病例没有标注为异常的分区。</div>`;
      return `${head}
        <div class="sec-title">分区速览</div>
        ${chips}
        ${un.length ? `<div class="hint-box"><b>未提及 ${un.length} 区：</b>原图注未逐区描述，不作推断。</div>` : ""}`;
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
        <div class="zc-basis">依据：${esc(z.basis)} · 教学分区</div>
        <details class="qa-tech"><summary>分区来源与审核状态</summary>
          <p>分区编号 ${esc(z.id)} · 位置框 [${z.coords.map((n) => n.toFixed(2)).join(", ")}]</p>
          <p>分区范围按公开胸片解剖分区规范与文献描述确定，逐区文本由 AI 辅助整理；<b>未经开发者人工标注，也未经影像科医师逐例复核</b>。</p>
        </details>
        ${signChips}
      </div>
      ${z.status === "unmentioned" ? `<div class="hint-box">该分区为“来源未提及”，不是“正常”。</div>` : ""}
      <div class="sys-actions">
        <button class="btn sm" data-ask="${esc(`${z.name}有没有异常？`)}">问这个分区</button>
        <button class="btn sm" data-tab="qa">去问答</button>
        <button class="btn sm" data-review="zone" data-review-id="${esc(z.id)}">反馈这个分区${reviewCount(c.id, z.id) ? `<span class="rv-badge">${reviewCount(c.id, z.id)}</span>` : ""}</button>
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
    return `<div class="sec-title">系统阅片</div>
      <div class="sys-sum">${ab ? `${ab} 项异常` : "未见明确异常"}</div>
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
    const mode = S.qaMode === "agent" ? "agent" : "kb";
    return `<div class="qa-mode" role="tablist" aria-label="问答方式">
        <button data-qa-mode="kb" role="tab" aria-selected="${mode === "kb"}" class="${mode === "kb" ? "on" : ""}">知识库检索</button>
        <button data-qa-mode="agent" role="tab" aria-selected="${mode === "agent"}" class="${mode === "agent" ? "on" : ""}">智能问答</button>
      </div>
      ${mode === "agent" ? qaAgentHTML(c, presets) : qaKbHTML(c, presets)}`;
  }

  function qaKbHTML(c, presets) {
    const log = S.qa.length
      ? S.qa.map((m) => m.role === "user"
        ? `<div class="qa-msg user">${esc(m.text)}</div>`
        : qaAnswerHTML(m.answer)).join("")
      : `<div class="hint-box">只回答当前病例：${esc(c.id)} · ${esc(c.title)}</div>`;
    return `<div class="qa-log" id="qaLog">${log}</div>
      <div class="qa-presets">${presets.map((p) => `<button data-ask="${esc(p)}">${esc(p)}</button>`).join("")}</div>
      <div class="qa-input">
        <input id="qaInput" value="${esc(S.qaDraft)}" placeholder="问这张胸片：右肺上野有没有异常？" autocomplete="off">
        <button class="btn sm primary" id="qaSend">查知识库</button>
      </div>`;
  }

  function qaAgentHTML(c, presets) {
    const log = S.agent.messages.length
      ? S.agent.messages.map(qaAgentMessageHTML).join("")
      : `<div class="hint-box">让 Agent 解释当前病例：${esc(c.id)} · ${esc(c.title)}</div>`;
    return `<div class="qa-log" id="qaAgentLog">${log}</div>
      <div class="qa-presets">${presets.map((p) => `<button data-ask="${esc(p)}">${esc(p)}</button>`).join("")}</div>
      <div class="qa-input">
        <input id="qaAgentInput" value="${esc(S.agent.draft)}" placeholder="问这张胸片，例如：右肺上野为什么标注为异常？" autocomplete="off" ${S.agent.running ? "disabled" : ""}>
        <button class="btn sm primary" id="qaAgentSend" ${S.agent.running ? "disabled" : ""}>${S.agent.running ? "解释中…" : "问 Agent"}</button>
      </div>`;
  }

  function qaAgentMessageHTML(m) {
    if (m.role === "user") return `<div class="qa-msg user">${esc(m.text)}</div>`;
    if (m.status === "error") {
      const connBtn = (window.RCAgent && window.RCAgent.connButtonHTML) ? window.RCAgent.connButtonHTML() : "";
      return `<div class="qa-msg bot refuse agent">
        <div class="qa-title">智能解释暂时不可用</div>
        <div class="qa-body">
          <p>${esc(m.error || "请稍后再试。")}</p>
          <p>你仍然可以用“知识库检索”查看当前病例的标注与出处。</p>
          ${connBtn}
        </div>
        ${m.detail ? `<details class="qa-tech"><summary>技术信息</summary><p>${esc(m.detail)}</p></details>` : ""}
      </div>`;
    }
    const sec = m.sections || splitAgent(m.text || "");
    // 新版回答是「首段结论 + 若干自然段」。没有「结论：」标记时 splitAgent 会把整段放进
    // conclusion，因此按行拆成独立段落渲染，否则 <p> 里的换行会被 HTML 折叠成一整块。
    const paras = sec.conclusion.concat(sec.other).map((x) => naturalize(x)).filter(Boolean);
    const conclusion = paras[0] || (m.status === "running" ? "正在生成…" : "本轮没有返回可读的解释。");
    const extra = paras.slice(1);
    const evidence = sec.evidence.map((x) => naturalize(x, true)).filter(Boolean);
    const missing = sec.missing.map(naturalize).filter(Boolean);
    const boundary = sec.boundary.map(naturalize).filter(Boolean);
    const cites = (m.cites || []).map((x) => agentCiteHTML(x, m.done));
    const evidenceBlock = (evidence.length || cites.length)
      ? `<details class="qa-more"><summary>依据与出处${cites.length ? ` · ${cites.length} 条` : ""}</summary>
          ${evidence.length ? `<div class="qa-evidence">${evidence.map((x) => `<p>${esc(x)}</p>`).join("")}</div>` : ""}
          ${cites.length ? `<div class="qa-cites">${cites.join("")}</div>` : ""}
        </details>`
      : "";
    const noteBlock = (missing.length || boundary.length)
      ? `<details class="qa-more"><summary>还需要注意</summary>
          ${missing.length ? `<ul>${missing.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
          ${boundary.length ? `<p class="qa-boundary">${esc(boundary.join(" "))}</p>` : ""}
        </details>`
      : "";
    const tech = m.done ? `<details class="qa-tech"><summary>技术信息</summary><p>${esc(techSummary(m.done))}</p></details>` : "";
    return `<div class="qa-msg bot agent ${m.status === "running" ? "running" : ""}">
      <div class="qa-title">智能解释${m.status === "running" ? `<span class="qa-running">正在生成</span>` : ""}</div>
      <div class="qa-body"><p class="qa-conclusion">${esc(conclusion)}</p>${extra.map((x) => `<p>${esc(x)}</p>`).join("")}</div>
      ${evidenceBlock}
      ${noteBlock}
      ${tech}
    </div>`;
  }

  function agentCiteHTML(c, done) {
    const label = c.type === "sign" ? "文献来源"
      : c.type === "case" ? "病例来源"
        : c.type === "guideline" ? "指南条款"
          : c.type === "region" ? "影像位置" : "知识库条目";
    const bad = !!(done && done.unverified_citations && done.unverified_citations.includes(c.id));
    const url = c.source_url
      ? `<a href="${esc(c.source_url)}" target="_blank" rel="noopener">查看来源 ↗</a>` : "";
    const kindLabel = { sign: "征象解释", case: "病例", guideline: "指南条款", region: "影像位置", claim: "结论条目" }[c.type] || "";
    return `<div class="cite ${bad ? "bad" : ""}">
      <b>${esc(label)}${c.title ? " · " + esc(c.title) : ""}</b>
      ${kindLabel ? `<span>${esc(kindLabel)}</span>` : ""}
      ${url}
      ${c.id ? `<code class="qa-cite-id">${esc(c.id)}</code>` : ""}
      ${bad ? `<em>未在知识库中校验</em>` : ""}
    </div>`;
  }

  function splitAgent(text) {
    const out = { conclusion: [], evidence: [], missing: [], boundary: [], other: [] };
    const map = { "结论": "conclusion", "依据": "evidence", "缺失": "missing", "边界": "boundary", "参考": "evidence", "说明": "evidence" };
    let cur = "other";
    String(text || "").split(/\n+/).forEach((line) => {
      const m = line.match(/^(结论|依据|缺失|边界|参考|说明)\s*[:：]\s*(.*)$/);
      if (m) {
        cur = map[m[1]] || "other";
        if (m[2].trim()) out[cur].push(m[2].trim());
      } else if (line.trim()) {
        out[cur].push(line.trim());
      }
    });
    if (!out.conclusion.length && out.other.length) {
      // 新版回答不强制「结论：」前缀：没有标记时整段就是结论，other 清空，
      // 避免渲染时既当结论又当补充段重复显示。
      out.conclusion = out.other.slice();
      out.other = [];
    }
    return out;
  }

  function naturalize(text, keepIds) {
    let s = String(text == null ? "" : text);
    s = s.replace(/【通识补充·非库内证据】/g, "补充说明：");
    s = s.replace(/【通识补充】/g, "补充说明：");
    s = s.replace(/^(依据|缺失|边界|结论)\s*[:：]\s*/, "");
    s = s.replace(/库内/g, "知识库");
    if (!keepIds) s = s.replace(/(?:SIGN|CASE|CLM|SL|REG|GL|GRP|STD|ATLAS)-[A-Za-z0-9-]+/g, "");
    // 去掉 id 后会留下空的 [] 或 [][]；不要让用户看到这种占位符。
    s = s.replace(/\[\s*\]/g, "");
    s = s.replace(/(?:sha256|para_id|bbox)\s*[:：=]?\s*[A-Za-z0-9_\-\[\],. ]+/gi, "");
    s = s.replace(/库内命中/g, "知识库中找到");
    s = s.replace(/弱命中/g, "匹配度较低");
    s = s.replace(/双引用链/g, "证据链");
    s = s.replace(/\bE1\b/g, "影像位置");
    s = s.replace(/\bL[12]\b/g, "文献来源");
    s = s.replace(/\s{2,}/g, " ").replace(/\s+([，。；：])/g, "$1");
    s = s.replace(/[，、；：]\s*。/g, "。").replace(/[（(]\s*[)）]/g, "");
    s = s.replace(/^[，、；：。]+/, "").replace(/[，、；：]+$/, "");
    return s.trim();
  }

  function techSummary(done) {
    const parts = [];
    if (done.served_by) {
      parts.push(done.served_by === "agent" ? "智能解释"
        : done.served_by === "fallback" ? "简化回答" : done.served_by);
    }
    if (done.degraded) parts.push("本次为降级回答");
    if (done.total_ms != null) parts.push(`${done.total_ms} ms`);
    if (done.run_id) parts.push(`运行 ${done.run_id}`);
    return parts.join(" · ") || "已完成";
  }

  function friendlyAgentError(e) {
    const msg = String((e && e.message) || e || "");
    const code = e && e.code;
    if (code === "unconfigured") return "线上页面还没有连接 Agent 服务。点下方“连接设置”填写已部署的服务地址后即可使用。";
    if (code === "mixed-content") return "当前是 HTTPS 页面，不能连接 http:// 地址。请在“连接设置”里换成 HTTPS 的 Agent 地址。";
    if (code === "timeout" || /超时|timeout|abort/i.test(msg)) return "这次解释用时较长，已停止等待。可以稍后重试，或改用知识库检索。";
    if (code === "network" || /无法连接|failed to fetch|networkerror|http/i.test(msg)) return "智能解释服务暂时没有响应。请检查“连接设置”里的地址，或稍后再试。";
    return "这次没有拿到可用的解释。可以稍后重试，或改用知识库检索。";
  }

  function buildAgentQuery(c, z, sign, text) {
    const parts = [`【胸片阅片】病例 ${c.id} · ${c.title}（${c.pose_label}）`];
    if (z) parts.push(`分区 ${z.name}（${z.id}），状态 ${statusLabel(z.status)}，所见：${z.text}`);
    if (sign) parts.push(`征象 ${sign.name}（${sign.id}）：${sign.appearance}`);
    parts.push(`问题：${text}`);
    parts.push("要求：像上级医师带教一样直接讲影像表现与鉴别要点，不诊断、不治疗、不判分、不编造引用；不要写来源说明、缺失、边界或免责声明，出处只在最后一行。");
    return parts.join("。");
  }

  async function runAgent(q) {
    const text = String(q || "").trim();
    if (!text || S.agent.running) return;
    const c = currentCase();
    if (!c) return;
    const z = detectZone(text, c);
    const sign = detectSign(text);
    const user = { role: "user", text };
    const bot = { role: "bot", text: "", status: "running", sections: null, cites: [], done: null, error: "" };
    S.agent.messages.push(user, bot);
    S.agent.draft = "";
    S.agent.running = true;
    S.qaMode = "agent";
    S.tab = "qa";
    renderPanel();
    const query = buildAgentQuery(c, z, sign, text);
    try {
      if (!window.RCAgent) throw new Error("智能解释服务未加载");
      const out = await window.RCAgent.ask({
        query,
        surface: "clinic",
        context: { case_id: c.id, zone_id: z ? z.id : "" },
      }, {
        onEvent: (kind, data, snapshot) => {
          if (kind !== "delta") return;
          bot.text = snapshot.text;
          bot.sections = splitAgent(bot.text);
          const last = $("#qaAgentLog .qa-msg.bot.agent:last-child .qa-conclusion");
          if (last) last.textContent = naturalize(bot.sections.conclusion.join("\n")) || "正在生成…";
        },
      });
      bot.text = out.text;
      bot.sections = splitAgent(out.text);
      bot.cites = out.cites || [];
      bot.done = out.done || null;
      bot.status = "done";
    } catch (e) {
      bot.status = "error";
      bot.error = friendlyAgentError(e);
      bot.detail = String((e && e.message) || e || "");
    } finally {
      S.agent.running = false;
      renderPanel();
      requestAnimationFrame(() => {
        const log = $("#qaAgentLog");
        if (log) log.scrollIntoView({ block: "end", behavior: "smooth" });
      });
    }
  }

  function qaAnswerHTML(a) {
    const cls = a.status === "refuse" ? "refuse" : (a.status === "partial" ? "partial" : "");
    const body = (a.body || []).map((p) => `<p>${esc(p)}</p>`).join("");
    const bullets = (a.bullets && a.bullets.length)
      ? `<ul>${a.bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : "";
    const cites = (a.cites && a.cites.length)
      ? `<details class="qa-more" open><summary>依据与出处</summary><div class="qa-cites">${a.cites.map(citeHTML).join("")}</div></details>` : "";
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
    const upload = uploadHTML(S.upload);
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
      <div class="sec-title">征象解释</div>
      ${signs}
      ${teaching}
      ${caveats}
      <div class="sec-title">数据说明</div>
      <div class="src-block">
        <p>分区框为教学分区，按公开解剖分区规范与文献描述确定范围，不是病灶分割；未提及的分区不推断为正常。</p>
        <p>开发者不具备医学专业资质，<b>未对影像做人工标注</b>：分区与逐区文本由文献资料 + AI 辅助整理，<b>尚未经影像科医师逐例复核</b>。</p>
        <button class="btn sm" data-review="case" data-review-id="${esc(c.id)}">反馈本病例${reviewCount(c.id, "") ? `<span class="rv-badge">${reviewCount(c.id, "")}</span>` : ""}</button>
      </div>
      <div class="sec-title">隐私与使用</div>
      <div class="src-block">
        <p>上传影像只在当前浏览器内显示，不上传服务器、不落盘。请勿上传真实患者影像。</p>
      </div>
      <details class="qa-tech"><summary>技术信息</summary>
        <p>影像指纹 ${esc((c.sha256 || "").slice(0, 16))}… · 数据接口 /api/kb/chest</p>
        <p>智能问答需要本地 Agent 服务；服务不可用时，知识库检索仍可正常使用。</p>
      </details>`;
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
      detail: `${statusLabel(z.status)} · 依据：${z.basis}`,
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
      title: "征象解释",
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
      body.push("该区在原始图注中没有逐区描述，因此不能判为正常或异常；请回到整张片子自行观察。");
    } else if (z.status === "limited") {
      body.push("判读受限的原因见影像质量说明；受限不等于正常。");
    } else if (z.status === "normal") {
      body.push("该区未见明确异常；仍要结合吸气程度、体位与曝光条件复核，不等于排除了细微病变。");
    } else {
      body.push("该区标注为异常，需结合具体征象判断性质。");
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
      body.push(`该区未见明确异常，也没有「${sign.name}」的标注；不能据此排除早期或细微病变。`);
    } else if (z.status === "unmentioned") {
      body.push(`该区没有逐区描述，不能判断有没有「${sign.name}」。`);
    } else if (z.status === "limited") {
      body.push(`该区判读受限，不能可靠判断有没有「${sign.name}」。`);
    } else {
      body.push(`该区标注为「${statusLabel(z.status)}」，没有「${sign.name}」的标注；不能据此排除。`);
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
      body.push(`本病例的「${sign.name}」位于：${hits.map((z) => z.name).join("、")}。`);
      body.push(hits[0].text);
    } else {
      body.push(`本病例没有「${sign.name}」的标注；不能据此排除，也不能据此诊断。`);
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
      body.push(`本病例的异常位于：${ab.map((z) => z.name).join("、")}。`);
    } else if (!c.signs.length) {
      body.push("本片为正常胸片；已标注分区均未见明确异常。");
    } else {
      body.push("没有逐区文本标为异常的分区；系统所见见下方。");
    }
    if (sysAb.length) body.push(`系统所见异常：${sysAb.map((x) => x.name + "（" + x.text + "）").join("；")}。`);
    if (un.length) body.push(`另有 ${un.length} 个分区原图注未逐区描述，不作正常/异常推断。`);
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
      title: "没有匹配到对应分区或征象",
      body: [
        `没有在「${c.title}」里识别到与“${q}”对应的分区或征象词条。`,
        "可以直接点影像上的分区，或换用规范说法：右肺上野 / 右肺中野 / 右肺下野 / 左肺上野 / 左肺中野 / 左肺下野 / 纵隔与心影 / 膈下；征象如气胸、胸腔积液、实变、结节、磨玻璃影。",
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
    const c = currentCase();
    const z = c ? detectZone(text, c) : null;
    const signText = z
      ? (z.sign_ids || []).map((id) => {
        const s = signOf(id);
        return s ? `${s.id} ${s.name}` : id;
      }).join("、")
      : "";
    const evidence = z
      ? `病例 ${c.id}，分区 ${z.name}（${z.id}），状态 ${statusLabel(z.status)}，所见：${z.text}，关联征象：${signText || "无"}`
      : "";
    S.qa.push({ role: "user", text });
    S.qa.push({
      role: "bot",
      answer: answer(text),
      agent: c ? { query: text, case_id: c.id, zone_id: z ? z.id : "", evidence } : null,
    });
    S.qaDraft = "";
    S.qaMode = "kb";
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
    L.push("  本记录仅整理影像表现与鉴别要点，不构成诊断意见，不替代临床决策。");
    L.push("  分区框为教学分区，不是病灶分割；未提及的分区不作正常或异常推断。");
    L.push("  分区与逐区文本由公开文献资料 + AI 辅助整理，未由开发者人工标注，尚未经影像科医师逐例复核。");
    L.push("  正式教学或对外发布前，须由具备资质的医学人员逐条复核；页面「反馈」入口可提交异议。");
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

  /* ---------------- 反馈 / 专家复核入口 ----------------
   * 开发者不具备医学专业资质，分区未人工标注、未经专家复核。
   * 反馈只做「收集 + 导出」：写入 localStorage，标记待专家复核，不自动改库内结论。
   */
  const REVIEW_KEY = "radiocheck.review.v1";
  const REVIEW_STATUS = "待专家复核";
  const REVIEW_TYPES = [
    ["bbox", "分区框位置或范围不准"],
    ["zone_name", "分区名称或解剖范围有误"],
    ["zone_text", "分区所见与影像不符"],
    ["cite", "出处或引用对不上"],
    ["other", "其他问题"],
  ];
  const REVIEW_ROLES = ["学生", "教师", "影像科医师", "其他"];
  let reviewCtx = null;
  let reviewView = "form";

  function loadReviews() {
    try {
      const a = JSON.parse(localStorage.getItem(REVIEW_KEY) || "[]");
      return Array.isArray(a) ? a : [];
    } catch (e) { return []; }
  }

  function saveReviews(list) {
    try { localStorage.setItem(REVIEW_KEY, JSON.stringify(list.slice(-500))); }
    catch (e) { toast("本机存储已满，反馈未能保存"); }
  }

  function reviewCount(caseId, zoneId) {
    return loadReviews().filter((r) => r.case_id === caseId && (!zoneId || r.zone_id === zoneId)).length;
  }

  function reviewTypeLabel(v) {
    const hit = REVIEW_TYPES.find((x) => x[0] === v);
    return hit ? hit[1] : "其他问题";
  }

  function openReview(kind, id) {
    const c = currentCase();
    if (!c) return;
    const z = kind === "zone" ? c.zones.find((x) => x.id === id) : null;
    reviewCtx = {
      kind,
      caseId: c.id,
      caseTitle: c.title,
      zoneId: z ? z.id : "",
      zoneName: z ? z.name : "",
    };
    reviewView = "form";
    renderReview();
    $("#reviewMask").hidden = false;
    setTimeout(() => { const n = $("#rvNote"); if (n) n.focus(); }, 30);
  }

  function closeReview() {
    $("#reviewMask").hidden = true;
  }

  function reviewItemHTML(r) {
    return `<div class="review-item">
      <div class="rv-top">
        <span class="rv-type">${esc(reviewTypeLabel(r.type))}</span>
        <b>${esc(r.case_id || "")}${r.zone_name ? " · " + esc(r.zone_name) : " · 整例"}</b>
        <span style="margin-left:auto">${esc((r.at || "").replace("T", " ").slice(0, 16))}</span>
      </div>
      <p>${esc(r.note || "")}</p>
      <div class="rv-top" style="margin:4px 0 0">
        <span>${esc(r.role || "未填身份")}${r.contact ? " · " + esc(r.contact) : ""}</span>
        <span style="margin-left:auto;color:var(--warn)">${esc(r.status || REVIEW_STATUS)}</span>
      </div>
    </div>`;
  }

  function renderReview() {
    const box = $("#reviewBody");
    if (!box) return;
    const list = loadReviews();
    if (reviewView === "list") {
      $("#reviewTitle").textContent = "我的反馈";
      box.innerHTML = `
        <div class="review-target">共 <b>${list.length}</b> 条反馈，全部标记为「${REVIEW_STATUS}」。反馈只保存在当前浏览器，不上传服务器。</div>
        ${list.length
          ? list.slice().reverse().map(reviewItemHTML).join("")
          : `<div class="review-empty">还没有提交过反馈。</div>`}
        <div class="review-actions">
          <button class="btn sm" id="rvExportJson">导出 JSON</button>
          <button class="btn sm" id="rvExportCsv">导出 CSV</button>
          <span class="spacer"></span>
          <button class="btn sm" id="rvClear">清空</button>
          <button class="btn sm primary" id="rvBack">返回</button>
        </div>`;
      return;
    }
    if (!reviewCtx) return;
    $("#reviewTitle").textContent = "提交反馈";
    const opts = REVIEW_TYPES.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("");
    const roles = REVIEW_ROLES.map((r) => `<option>${esc(r)}</option>`).join("");
    box.innerHTML = `
      <div class="review-target">
        <b>${esc(reviewCtx.caseTitle)}</b> · ${esc(reviewCtx.caseId)}
        ${reviewCtx.zoneName
          ? `<br>分区：<b>${esc(reviewCtx.zoneName)}</b>（${esc(reviewCtx.zoneId)}）`
          : `<br>对象：整例（分区框与逐区文本）`}
      </div>
      <label for="rvType">问题类型</label>
      <select id="rvType">${opts}</select>
      <label for="rvNote">具体说明（必填，至少 5 个字）</label>
      <textarea id="rvNote" placeholder="例：右侧肋膈角的分区框没有盖住实际肋膈角，建议下移约 1 个肋间隙；判断依据：……"></textarea>
      <label for="rvRole">你的身份</label>
      <select id="rvRole">${roles}</select>
      <label for="rvContact">联系方式（选填，便于复核时回访）</label>
      <input id="rvContact" placeholder="邮箱 / 微信 / 工号，可不填">
      <div class="review-err" id="rvErr"></div>
      <div class="review-hint">
        提交后记为「${REVIEW_STATUS}」，<b>不会自动修改库内结论</b>；反馈只保存在本机浏览器，可导出后交给医学审核人。
        分区与逐区文本由文献 + AI 辅助整理，未经开发者人工标注，也未经影像科医师逐例复核。
      </div>
      <div class="review-actions">
        <button class="btn sm" id="rvMy">我的反馈（${list.length}）</button>
        <span class="spacer"></span>
        <button class="btn sm" id="rvCancel">取消</button>
        <button class="btn sm primary" id="rvSubmit">提交反馈</button>
      </div>`;
  }

  function submitReview() {
    if (!reviewCtx) return;
    const note = ($("#rvNote") && $("#rvNote").value || "").trim();
    const err = $("#rvErr");
    if (note.length < 5) {
      if (err) { err.textContent = "请把问题写清楚（至少 5 个字），便于专家复核时定位。"; err.classList.add("on"); }
      if ($("#rvNote")) $("#rvNote").focus();
      return;
    }
    if (err) err.classList.remove("on");
    const c = currentCase();
    const rec = {
      at: new Date().toISOString(),
      case_id: reviewCtx.caseId,
      case_title: reviewCtx.caseTitle,
      zone_id: reviewCtx.zoneId,
      zone_name: reviewCtx.zoneName,
      kind: reviewCtx.kind,
      type: ($("#rvType") || {}).value || "other",
      role: ($("#rvRole") || {}).value || "",
      contact: (($("#rvContact") || {}).value || "").trim(),
      note,
      status: REVIEW_STATUS,
      page: "clinic",
      quality: c ? c.quality : "",
    };
    const list = loadReviews();
    list.push(rec);
    saveReviews(list);
    toast("已提交，标记为待专家复核");
    reviewView = "list";
    renderReview();
    renderPanel();
  }

  function csvCell(v) {
    const s = String(v == null ? "" : v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }

  function downloadText(name, text, mime) {
    const blob = new Blob([text], { type: mime });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(a.href), 1500);
  }

  function exportReviews(fmt) {
    const list = loadReviews();
    if (!list.length) { toast("还没有反馈可以导出"); return; }
    const stamp = new Date().toISOString().slice(0, 10);
    if (fmt === "csv") {
      const cols = ["at", "case_id", "case_title", "zone_id", "zone_name", "kind", "type", "role", "note", "contact", "status"];
      const head = ["提交时间", "病例编号", "病例标题", "分区编号", "分区名称", "对象", "问题类型", "身份", "说明", "联系方式", "状态"];
      const rows = list.map((r) => cols.map((k) => {
        if (k === "type") return csvCell(reviewTypeLabel(r.type));
        if (k === "kind") return csvCell(r.kind === "zone" ? "分区" : "整例");
        return csvCell(r[k]);
      }).join(","));
      downloadText(`RadioCheck_反馈_${stamp}.csv`, "\ufeff" + head.join(",") + "\n" + rows.join("\n"), "text/csv;charset=utf-8");
    } else {
      const out = {
        exported_at: new Date().toISOString(),
        status: REVIEW_STATUS,
        source: "RadioCheck clinic · 分区与结论反馈",
        count: list.length,
        items: list,
      };
      downloadText(`RadioCheck_反馈_${stamp}.json`, JSON.stringify(out, null, 2), "application/json;charset=utf-8");
    }
    toast(`已导出 ${list.length} 条反馈`);
  }

  function clearReviews() {
    const n = loadReviews().length;
    if (!n) { toast("没有反馈可清空"); return; }
    if (!window.confirm(`确定清空本机保存的 ${n} 条反馈？清空后无法恢复，建议先导出。`)) return;
    saveReviews([]);
    renderReview();
    renderPanel();
    toast("已清空本机反馈");
  }

  /* ---------------- 上传 ---------------- */

  async function sha256Hex(buf) {
    if (!window.crypto || !window.crypto.subtle) return "";
    const d = await window.crypto.subtle.digest("SHA-256", buf);
    return Array.from(new Uint8Array(d)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  function readDataURL(file) {
    return new Promise((resolve) => {
      const fr = new FileReader();
      fr.onload = () => resolve(String(fr.result || ""));
      fr.onerror = () => resolve("");
      fr.readAsDataURL(file);
    });
  }

  async function handleUpload(file) {
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) {
      toast("图片超过 8 MB，未读取；请使用公开教学影像的压缩版");
      return;
    }
    let hash = "";
    try {
      hash = await sha256Hex(await file.arrayBuffer());
    } catch (e) {
      hash = "";
    }
    const url = await readDataURL(file);
    const hit = hash ? enabledCases().find((c) => c.sha256 === hash || c.sha256_source === hash) : null;
    if (hit) {
      S.upload = { ok: true, name: file.name, size: file.size, hash, caseId: hit.id };
      selectCase(hit.id);
      toast(`已匹配知识库病例 ${hit.id}`);
    } else {
      S.upload = {
        ok: false, generic: true, name: file.name, size: file.size, hash, url,
        genericZone: "", vision: null, doc: null, locating: true,
      };
      S.tab = "source";
      render();
      locateUploadVision(S.upload);
      toast("该影像未入库：先做胸片模板定位，不下结论");
    }
  }

  /* ---------- 上传影像：胸片专项视觉定位 → 模板分区 → 双引用 ---------- */

  // 只认胸部 X 线：CT/MR/US/MG 一律不算胸片，避免「胸部 CT 也套胸片分区」。
  const CHEST_MODALITY = /^(CR|DX|XR|DR|RF)$/i;
  const CHEST_PART = /胸|肺|chest|thorax|lung/i;

  function isChestVision(v) {
    const vis = (v && v.vision) || {};
    const mod = String(vis.modality || "").toUpperCase();
    const part = String(vis.body_part || "");
    // 视觉模型明确说了不是胸片 → 拒绝；没说（null）→ 按胸片默认处理，后端会标 assumed_chest。
    if (mod && !CHEST_MODALITY.test(mod)) return false;
    if (part && !CHEST_PART.test(part)) return false;
    return true;
  }

  async function locateUploadVision(u, confirmChest) {
    if (!u || !u.url) return;
    u.locating = true;
    u.vision = null;
    u.doc = null;
    u.notChest = false;
    u.needsConfirm = false;
    render();
    const base = (window.RCKB && RCKB.base) ? RCKB.base() : "";
    const live = !!(window.RCKB && RCKB.isLive && RCKB.isLive());
    // 纯静态站没有 /api：直接给降级提示，不要发 POST 让服务器回 501。
    // 只有显式 ?api= 或同源已探测到动态服务时才发请求。
    if (!live && !base) {
      u.locating = false;
      u.vision = {
        ok: false, reason: "api_unreachable",
        message: "未连接动态服务（静态预览没有 /api）；可先用下方手动分区做解剖定位。",
      };
      render();
      return;
    }
    const payload = { image: u.url, use_center: true };
    // 只有用户点过「我确认这是胸部 X 线片」才补检查类型；
    // 否则不伪造元数据，交给后端标记 assumed_chest，前端据此不输出分区结论。
    if (confirmChest) {
      payload.modality = "CR";
      payload.body_part = "胸部";
      payload.view = "PA";
    }
    try {
      const r = await fetch((base || "") + "/api/vision/region", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      u.vision = await r.json();
    } catch (e) {
      u.vision = {
        ok: false, reason: "api_unreachable",
        message: "未连接动态服务（静态预览没有 /api）；可先用下方手动分区做解剖定位。",
      };
    }
    u.locating = false;
    const v = u.vision || {};
    // 未识别影像类型（assumed_chest）且用户未确认：不给分区结论，先问一句。
    // 这是「胸片专项」的硬边界：离线无视觉模型时不能把任意图片当胸片分区。
    if (v.ok && v.assumed_chest && !confirmChest) {
      u.needsConfirm = true;
      u.zone = "";
      u.bbox = null;
      u.doc = null;
    } else if (v.ok && !isChestVision(v)) {
      u.notChest = true;
    } else if (v.ok) {
      const loc = v.locate || {};
      const reg = (loc.primary && loc.primary.region) || {};
      u.zone = reg.name || "";
      u.bbox = reg.coords || v.bbox || null;
      const findings = ((v.vision || {}).findings || []).join(" ");
      const q = ["胸部", reg.name, findings].filter(Boolean).join(" ");
      let doc = null;
      try {
        const rr = await fetch((base || "") + "/api/kb/search?q=" + encodeURIComponent(q) + "&mode=semantic&limit=12");
        const d = await rr.json();
        doc = (d.items || []).find((x) => x.kind === "guideline") || null;
      } catch (e) { doc = null; }
      if (!doc) {
        const sid = (reg.sign_ids || [])[0];
        if (sid) {
          try {
            const rr = await fetch((base || "") + "/api/kb/sign/" + encodeURIComponent(sid));
            const d = await rr.json();
            const sg = d.sign || {};
            const para = (d.paragraphs || [])[0] || {};
            doc = {
              kind: "sign", id: sg.id || sid, title: sg.name || sid,
              snippet: para.text || sg.appearance || "",
              source_url: para.source_url || "", candidate: true,
            };
          } catch (e) { doc = null; }
        }
      }
      u.doc = doc;
    }
    render();
  }

  function uploadHTML(u) {
    if (!u) return "";
    if (u.ok) {
      return `<div class="src-block"><b>上传匹配成功</b><p>${esc(u.name)} → ${esc(u.caseId)}（文件指纹匹配）。</p></div>`;
    }
    const v = u.vision || {};
    const vis = v.vision || {};
    const loc = v.locate || {};
    const reg = (loc.primary && loc.primary.region) || {};
    let state = "";
    if (u.locating) {
      state = `<div class="src-block"><b>视觉定位中…</b><p>先识别检查类型、部位与投照位，再匹配胸片分区模板。</p></div>`;
    } else if (u.needsConfirm) {
      state = `<div class="upload-alert"><b>未确认影像类型 · 暂不做分区判断</b>
        <p>本产品只做<b>胸片（胸部 X 线，CR/DR）</b>。当前没有视觉模型，无法确认这张是不是胸片，因此不输出分区结论，也不套用任何模板。</p>
        <p class="hint">${v.vision_used ? "" : "当前没有视觉模型，所以无法自动识别检查类型；这一步只能由你确认。"}</p>
        <button class="btn sm primary" data-act="confirm-chest">我确认这是胸部 X 线片，继续定位</button>
        <p class="hint">如果不是胸片，请不要点击；其他影像的拓展计划见《反思与未来拓展方向》。</p>
      </div>`;
    } else if (v.ok && reg.name) {
      const bb = (reg.coords || v.bbox || []).map((n) => Number(n).toFixed(2)).join(", ");
      const doc = u.doc;
      state = `<div class="src-block generic-result">
        <b>胸片模板分区 · ${esc(reg.name)}</b>
        <p>${v.vision_used
          ? `视觉识别 ${esc(vis.modality || "CR")} · ${esc(vis.body_part || "胸部")} · 投照位 ${esc(vis.view || "—")}`
          : "未使用视觉模型 · 按胸片默认模板 CR / 胸部 / PA 定位"} · 定位状态 ${esc(loc.status || "")}</p>
        <p>bbox [${esc(bb)}] · 由 atlas 模板几何推断，<b>不是人工标注</b>；演示或教学前须人工复核。</p>
        ${v.vision_used ? "" : `<p class="hint">没有视觉模型时无法判断检查类型；如果这张不是胸片，请勿使用该分区结果。</p>`}
        ${(vis.findings || []).length ? `<p>视觉所见：${esc((vis.findings || []).join("；"))}</p>` : ""}
        <div class="src-block"><b>影像侧引用</b><p>${esc(reg.name)}（模板推断，非人工；${esc((v.atlas || {}).name || "胸片模板")}）</p></div>
        <div class="src-block"><b>文献侧引用${doc && doc.candidate ? " · 该分区候选征象词条（非本片所见）" : ""}</b>${doc
          ? `<p>${esc(doc.title)} · ${esc(doc.id)}</p><p>${esc(doc.snippet || "")}</p>${doc.source_url && doc.source_url.indexOf("kb://") !== 0 ? `<a href="${esc(doc.source_url)}" target="_blank" rel="noopener">打开出处 ↗</a>` : ""}`
          : `<p>未命中可引用条款；按双引用规则不输出结论。</p>`}</div>
        <p class="hint">上传胸片没有库内分区结论，因此不含「分区结论」引用；只做定位与文献对照，不构成诊断。</p>
      </div>`;
    } else if (v.ok && !reg.name) {
      state = `<div class="src-block"><b>未定位到胸片分区</b><p>${esc(loc.message || "该位置不在胸片模板分区内，按规则不作推断。")}</p></div>`;
    } else if (u.notChest || v.reason === "unsupported_modality" || v.reason === "no_atlas_match") {
      state = `<div class="upload-alert"><b>本产品是胸片专项，暂不支持这张影像</b>
        <p>${v.message ? esc(v.message) : `视觉识别为「${esc(vis.modality || "未知检查")} · ${esc(vis.body_part || "未知部位")}」。`}<b>不套用其他部位的分区模板</b>，避免出现「乳腺片套胸片分区」这类错配。</p>
        <p>其他影像的阅片能力与拓展计划，见《反思与未来拓展方向》。</p></div>`;
    } else {
      state = `<div class="src-block"><b>未连接视觉定位服务</b><p>${esc(v.message || "静态预览没有 /api；演示请启动动态服务。")}</p></div>`;
    }
    const zones = ["右肺上野", "右肺中野", "右肺下野", "左肺上野", "左肺中野", "左肺下野", "纵隔与心影", "膈下"];
    return `<div class="upload-alert">
      <b>上传影像 · 胸片专项</b>
      <p>文件：${esc(u.name)} · ${(u.size / 1024).toFixed(0)} KB<br>
      文件指纹：${esc(u.hash ? "已计算" : "浏览器不支持，未能计算")}<br>
      图片只在当前浏览器内存中显示，不上传服务器、不落盘。请勿上传真实患者影像。</p>
      ${u.url ? `<img class="upload-preview" src="${esc(u.url)}" alt="上传影像预览">` : ""}
      ${state}
      <div class="generic-zones">${zones.map((z) =>
        `<button class="chip ${u.genericZone === z ? "on" : ""}" data-generic-zone="${esc(z)}">${esc(z)}</button>`).join("")}</div>
      ${genericZoneHTML(u.genericZone)}
      <p class="hint">手动分区只帮助定位解剖位置；没有知识库逐区文本时，本工具不对异常 / 正常作判断。</p>
    </div>`;
  }

  function genericZoneHTML(zone) {
    if (!zone) return "";
    return `<div class="src-block generic-result">
      <b>通用解剖分区 · ${esc(zone)}</b>
      <p>这是按胸片比例给出的通用分区，<b>不含该影像的知识库标注</b>；不能据此判断有无异常，也不生成征象结论。</p>
      <p>可对照左侧 21 例知识库影像的同一分区，或换用知识库原图做逐区对照。需要进一步解释时，可用右侧的智能问答；未入库影像不会给出异常判断。</p>
    </div>`;
  }

  /* ---------------- 交互 ---------------- */

  function selectCase(id) {
    const c = S.data.cases.find((x) => x.id === id);
    if (!c || !c.enabled) return;
    S.caseId = id;
    S.zoneId = null;
    S.qa = [];
    S.qaDraft = "";
    S.qaMode = "kb";
    S.agent = { messages: [], draft: "", running: false };
    S.zoom = 1;
    S.upload = null;
    const attempt = taskAttempt(id);
    S.quiz = {
      zoneIds: [],
      zoneNone: false,
      status: "",
      signs: [],
      signsTouched: false,
      result: attempt,
      redo: false,
    };
    S.tab = S.task ? "task" : "zone";
    render();
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function selectZone(id) {
    const c = currentCase();
    if (!c) return;
    const z = c.zones.find((x) => x.id === id);
    if (!z) return;
    if (S.task && !quizSubmitted(c.id)) {
      const set = new Set(S.quiz.zoneIds);
      if (set.has(id)) set.delete(id); else set.add(id);
      S.quiz.zoneIds = Array.from(set);
      S.quiz.zoneNone = false;
      S.quiz.redo = false;
      S.tab = "task";
      renderViewer();
      renderPanel();
      return;
    }
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

  function submitQuiz() {
    const c = currentCase();
    if (!c || !S.task) return;
    if (!(S.quiz.zoneNone || S.quiz.zoneIds.length) || !S.quiz.status || !S.quiz.signsTouched) {
      toast("三题都作答后才能提交");
      return;
    }
    if (!window.RCClass) {
      toast("课堂数据层未载入");
      return;
    }
    const graded = window.RCClass.gradeCase(c, {
      zoneIds: S.quiz.zoneIds,
      zoneNone: S.quiz.zoneNone,
      status: S.quiz.status,
      signs: S.quiz.signs,
    });
    const attempt = window.RCClass.saveAttempt({
      classId: S.task.classId,
      assignmentId: S.task.assignment.id,
      studentId: S.task.student.id,
      caseId: c.id,
      answers: {
        zoneIds: S.quiz.zoneIds,
        zoneNone: S.quiz.zoneNone,
        status: S.quiz.status,
        signs: S.quiz.signs,
      },
      score: graded.score,
      detail: graded.detail,
    });
    if (!attempt) {
      toast("提交失败，请返回课堂重新进入作业");
      return;
    }
    S.quiz.result = attempt;
    S.quiz.redo = false;
    S.task.attempts = window.RCClass.attemptsFor(S.task.classId, S.task.assignment.id, S.task.student.id);
    toast(`已提交：${attempt.score} 分`);
    render();
    const body = $("#panelBody");
    if (body) body.scrollTop = 0;
  }

  function nextTaskCase() {
    if (!S.task) return;
    const a = S.task.assignment;
    const done = new Set((S.task.attempts || []).map((x) => x.caseId));
    const cur = a.caseIds.indexOf(S.caseId);
    const after = a.caseIds.slice(cur + 1).find((id) => !done.has(id));
    const any = a.caseIds.find((id) => !done.has(id));
    const next = after || any;
    if (next) selectCase(next);
    else location.href = "classroom.html?role=student";
  }

  function redoQuiz() {
    S.quiz = {
      zoneIds: [],
      zoneNone: false,
      status: "",
      signs: [],
      signsTouched: false,
      result: null,
      redo: true,
    };
    S.tab = "task";
    render();
  }

  function bind() {
    document.addEventListener("click", (e) => {
      const genericZone = e.target.closest("[data-generic-zone]");
      if (genericZone) {
        if (S.upload && S.upload.generic) {
          S.upload.genericZone = genericZone.dataset.genericZone;
          renderPanel();
        }
        return;
      }
      const confirmChest = e.target.closest('[data-act="confirm-chest"]');
      if (confirmChest) {
        if (S.upload) {
          S.upload.confirmedChest = true;
          locateUploadVision(S.upload, true);
        }
        return;
      }
      const qRow = e.target.closest("[data-case]");
      if (qRow) { selectCase(qRow.dataset.case); return; }

      const quizZone = e.target.closest("[data-quiz-zone]");
      if (quizZone) {
        const id = quizZone.dataset.quizZone;
        if (id === "none") {
          S.quiz.zoneNone = true;
          S.quiz.zoneIds = [];
        } else {
          S.quiz.zoneNone = false;
          const set = new Set(S.quiz.zoneIds);
          if (set.has(id)) set.delete(id); else set.add(id);
          S.quiz.zoneIds = Array.from(set);
        }
        S.quiz.redo = false;
        renderViewer();
        renderPanel();
        return;
      }

      const quizStatus = e.target.closest("[data-quiz-status]");
      if (quizStatus) {
        S.quiz.status = quizStatus.dataset.quizStatus;
        renderPanel();
        return;
      }

      const quizSign = e.target.closest("[data-quiz-sign]");
      if (quizSign) {
        const id = quizSign.dataset.quizSign;
        S.quiz.signsTouched = true;
        if (id === "none") S.quiz.signs = [];
        else {
          const set = new Set(S.quiz.signs);
          if (set.has(id)) set.delete(id); else set.add(id);
          S.quiz.signs = Array.from(set);
        }
        renderPanel();
        return;
      }

      if (e.target && e.target.id === "quizSubmit") { submitQuiz(); return; }
      if (e.target && e.target.closest("[data-quiz-next]")) { nextTaskCase(); return; }
      if (e.target && e.target.closest("[data-quiz-redo]")) { redoQuiz(); return; }
      if (e.target && e.target.id === "taskJumpNext") { nextTaskCase(); return; }
      if (e.target && e.target.id === "taskGoQuiz") {
        const body = $("#panelBody");
        if (body) body.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }

      const f = e.target.closest("[data-f]");
      if (f) {
        S.filter = f.dataset.f;
        $$("#filters button").forEach((b) => b.classList.toggle("on", b === f));
        renderQueue();
        return;
      }

      const tab = e.target.closest("[data-tab]");
      if (tab) { S.tab = tab.dataset.tab; renderPanel(); return; }

      const qaMode = e.target.closest("[data-qa-mode]");
      if (qaMode) { S.qaMode = qaMode.dataset.qaMode === "agent" ? "agent" : "kb"; renderPanel(); return; }

      const zone = e.target.closest("[data-zone]");
      if (zone) { selectZone(zone.dataset.zone); return; }

      const rvBtn = e.target.closest("[data-review]");
      if (rvBtn) { openReview(rvBtn.dataset.review, rvBtn.dataset.reviewId); return; }

      const askBtn = e.target.closest("[data-ask]");
      if (askBtn) {
        if (S.qaMode === "agent") runAgent(askBtn.dataset.ask);
        else ask(askBtn.dataset.ask);
        return;
      }

      if (e.target && e.target.id === "qaAgentSend") {
        const input = $("#qaAgentInput");
        runAgent(input ? input.value : S.agent.draft);
        return;
      }

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
      } else if (res.status === "diffuse" && (res.regions || []).length) {
        // 气胸 / 大量积液这类大范围病变，框本身就大：给"可能累及"而不是拒绝定位
        const names = res.regions.map((x) => x.region.name);
        selectZone(res.regions[0].region.id);
        toast("大范围病变，可能累及：" + names.join("、"));
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

    $("#reviewMask").addEventListener("click", (e) => {
      const t = e.target;
      if (t.id === "reviewMask" || t.id === "reviewClose" || t.id === "rvCancel") { closeReview(); return; }
      if (t.id === "rvSubmit") { submitReview(); return; }
      if (t.id === "rvMy") { reviewView = "list"; renderReview(); return; }
      if (t.id === "rvBack") { reviewView = "form"; renderReview(); return; }
      if (t.id === "rvExportJson") { exportReviews("json"); return; }
      if (t.id === "rvExportCsv") { exportReviews("csv"); return; }
      if (t.id === "rvClear") { clearReviews(); return; }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && S.reportOpen) closeReport();
      if (e.key === "Escape" && !$("#reviewMask").hidden) closeReview();
      if (e.key === "Enter" && e.target && e.target.id === "qaInput") {
        e.preventDefault();
        ask(e.target.value);
      }
      if (e.key === "Enter" && e.target && e.target.id === "qaAgentInput") {
        e.preventDefault();
        runAgent(e.target.value);
      }
    });

    document.addEventListener("input", (e) => {
      if (e.target && e.target.id === "qaInput") S.qaDraft = e.target.value;
      if (e.target && e.target.id === "qaAgentInput") S.agent.draft = e.target.value;
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
      S.data = window.RCKB
        ? await window.RCKB.getJSON("/api/kb/chest", DATA_URL)
        : await (await fetch(DATA_URL, { cache: "no-cache" })).json();
    } catch (e) {
      $("#queueList").innerHTML = `<div class="empty-state"><b>胸片数据载入失败</b><span>请确认知识库服务已启动，或先完成站点构建。</span></div>`;
      $("#stageEmpty").innerHTML = `<b>胸片数据未载入</b><span>${esc(String(e.message || e))}</span>`;
      return;
    }
    let params = null;
    try { params = new URLSearchParams(location.search); } catch (e) { params = null; }
    const taskId = params ? params.get("task") : "";
    const studentId = params ? params.get("student") : "";
    let taskError = "";
    if (taskId && window.RCClass) {
      const ctx = window.RCClass.taskContext(taskId, studentId);
      if (ctx.ok) {
        S.task = ctx;
        document.body.classList.add("task-mode");
      } else {
        taskError = ctx.error || "作业不可用";
      }
    }

    const first = enabledCases()[0];
    const qp = params ? (params.get("case") || "") : "";
    const zq = params ? (params.get("zone") || "") : "";
    const deep = qp ? enabledCases().find((c) => c.id === qp) : null;
    const pending = S.task ? enabledCases().find((c) => !taskAttempt(c.id)) : null;
    if (deep) S.caseId = deep.id;
    else if (pending) S.caseId = pending.id;
    else if (first) S.caseId = first.id;
    const initialAttempt = taskAttempt(S.caseId);
    S.quiz = {
      zoneIds: [],
      zoneNone: false,
      status: "",
      signs: [],
      signsTouched: false,
      result: initialAttempt,
      redo: false,
    };
    S.tab = S.task ? "task" : "zone";
    bind();
    render();
    if (deep && zq) selectZone(zq);
    if (taskError) toast(taskError);
  }

  boot();
})();
