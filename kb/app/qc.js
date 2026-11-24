(function () {
  "use strict";

  const KEY = "radiocheck.qc.v1";
  const REVIEWER_KEY = "radiocheck.qc.reviewer";
  const DATA_URL = "../data/audit/review_queue.json";

  const LABEL = {
    mentioned_abnormal: "来源已提及异常",
    mentioned_normal: "来源已提及正常",
    not_mentioned: "来源未逐区提及",
    mentioned_other: "来源提及但无法分类",
    uncertain: "存疑",
  };
  const SUPPORT = {
    supported: "支持当前状态",
    not_supported: "不支持当前状态",
    uncertain: "不确定",
  };
  const STATUS = {
    abnormal: "异常",
    normal: "正常",
    unmentioned: "未提及",
    limited: "受限",
  };
  const OPTIONS = {
    unmentioned: [
      ["not_mentioned", "来源未逐区提及"],
      ["mentioned_abnormal", "来源已提及异常"],
      ["mentioned_normal", "来源已提及正常"],
      ["uncertain", "存疑/需查原文"],
    ],
    dual_label: [
      ["supported", "来源支持当前状态"],
      ["not_supported", "来源不支持当前状态"],
      ["uncertain", "存疑/需查原文"],
    ],
  };

  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

  let DATA = null;
  let STATE = {};
  let FILTER = "all";

  function readState() {
    try {
      const raw = localStorage.getItem(KEY);
      STATE = raw ? JSON.parse(raw) : {};
      if (!STATE || typeof STATE !== "object") STATE = {};
    } catch (e) { STATE = {}; }
  }

  function writeState() {
    try { localStorage.setItem(KEY, JSON.stringify(STATE)); return true; }
    catch (e) { return false; }
  }

  function reviewer() {
    const el = $("#reviewer");
    return (el && el.value || "").trim() || "未署名";
  }

  function toast(msg) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), 1800);
  }

  function itemState(it) {
    return STATE[it.id] || null;
  }

  function filtered() {
    const items = (DATA && DATA.items) || [];
    return items.filter((it) => {
      const st = itemState(it);
      if (FILTER === "conflict") return !it.agree;
      if (FILTER === "unmentioned") return it.kind === "unmentioned";
      if (FILTER === "dual_label") return it.kind === "dual_label";
      if (FILTER === "pending") return !st;
      if (FILTER === "reviewed") return !!st;
      return true;
    }).sort((a, b) => {
      const sa = itemState(a) ? 1 : 0;
      const sb = itemState(b) ? 1 : 0;
      if (sa !== sb) return sa - sb;
      if (a.agree !== b.agree) return a.agree ? 1 : -1;
      return a.id.localeCompare(b.id);
    });
  }

  function stats() {
    const items = (DATA && DATA.items) || [];
    const reviewed = items.filter((it) => itemState(it)).length;
    const conflict = items.filter((it) => !it.agree).length;
    const agree = items.length - conflict;
    return {
      total: items.length,
      reviewed,
      pending: items.length - reviewed,
      conflict,
      agree,
      rate: items.length ? Math.round(agree / items.length * 100) : 0,
    };
  }

  function renderStats() {
    const s = stats();
    $("#qcStats").innerHTML = [
      ["总数", s.total],
      ["已复核", s.reviewed],
      ["待复核", s.pending],
      ["AI 冲突", s.conflict],
    ].map(([k, v]) => `<div class="qc-stat"><b>${v}</b><span>${k}</span></div>`).join("")
      + `<div class="qc-stat" style="grid-column:1/-1"><b>${s.rate}%</b><span>AI 一致率（${s.agree}/${s.total}；一致≠金标准）</span></div>`;
  }

  function aiBox(name, ai) {
    const sup = ai.supported || "uncertain";
    const cls = sup === "supported" ? "sup" : (sup === "not_supported" ? "unsup" : "unc");
    return `<div class="qc-ai-box ${cls}">
      <h4><span>${esc(name)}</span><span>${esc(SUPPORT[sup] || sup)}</span></h4>
      <div class="verdict">${esc(LABEL[ai.label] || ai.label)}</div>
      <div class="reason">${esc(ai.reason || "")}</div>
    </div>`;
  }

  function expertOptions(it, current) {
    const list = OPTIONS[it.kind] || OPTIONS.dual_label;
    return list.map(([v, label]) =>
      `<option value="${v}" ${current === v ? "selected" : ""}>${label}</option>`).join("");
  }

  function card(it) {
    const st = itemState(it);
    const reviewed = !!st;
    const cls = reviewed ? "reviewed" : (it.agree ? "agree" : "conflict");
    const statusCls = it.status === "abnormal" ? "ab" : (it.status === "normal" ? "nm" : "um");
    const kind = it.kind === "unmentioned" ? "第四态抽检" : "双 AI 标注";
    const agreeBadge = it.agree
      ? `<span class="qc-badge agree">AI 一致</span>`
      : `<span class="qc-badge conflict">AI 冲突</span>`;
    const reviewedBadge = reviewed
      ? `<span class="qc-badge reviewed">已复核 · ${esc(st.label || "")}</span>`
      : `<span class="qc-badge">待复核</span>`;

    return `<article class="qc-card ${cls}" data-item="${esc(it.id)}">
      <div class="qc-card-h">
        <span class="qc-id">${esc(it.id)}</span>
        <span class="qc-title">${esc(it.case_id)} · ${esc(it.zone_name)}</span>
        <span class="qc-badge ${statusCls}">${esc(STATUS[it.status] || it.status)}</span>
        <span class="qc-badge">${kind}</span>
        ${agreeBadge}${reviewedBadge}
      </div>
      <div class="qc-source">
        <div class="qc-quote"><b>来源描述</b>${esc(it.description || "（无病例级描述）")}</div>
        <div class="qc-quote"><b>claim 文本</b>${esc(it.claim_text || "（该分区无 claim）")}</div>
      </div>
      <div class="qc-ai">
        ${aiBox("AI-A · 报告视角", it.ai_a || {})}
        ${aiBox("AI-B · 结构化视角", it.ai_b || {})}
      </div>
      <div class="qc-review">
        <label>专家结论
          <select data-qc-label="${esc(it.id)}">
            <option value="">请选择</option>
            ${expertOptions(it, st && st.label)}
          </select>
        </label>
        <label>备注
          <input data-qc-note="${esc(it.id)}" maxlength="120" value="${esc(st && st.note || "")}" placeholder="例如：原文只写“双肺”，未逐区">
        </label>
        <div class="full qc-actions">
          <button class="btn sm" data-qc-save="${esc(it.id)}">${reviewed ? "更新复核" : "保存复核"}</button>
          ${reviewed ? `<button class="btn sm ghost" data-qc-clear="${esc(it.id)}">撤销</button>` : ""}
        </div>
      </div>
    </article>`;
  }

  function render() {
    renderStats();
    const rows = filtered();
    $("#qcList").innerHTML = rows.length
      ? rows.map(card).join("")
      : `<div class="qc-empty"><b>没有符合条件的条目</b>切换筛选，或先完成剩余复核。</div>`;
  }

  function save(id) {
    const it = (DATA.items || []).find((x) => x.id === id);
    if (!it) return;
    const labelEl = document.querySelector(`[data-qc-label="${id}"]`);
    const noteEl = document.querySelector(`[data-qc-note="${id}"]`);
    const label = labelEl ? labelEl.value : "";
    if (!label) { toast("请先选择专家结论"); return; }
    STATE[id] = {
      status: "reviewed",
      label,
      note: (noteEl && noteEl.value || "").trim().slice(0, 120),
      reviewer: reviewer(),
      at: new Date().toISOString(),
    };
    writeState();
    toast("已保存专家复核");
    render();
  }

  function clear(id) {
    delete STATE[id];
    writeState();
    toast("已撤销复核");
    render();
  }

  function exportQc() {
    const items = (DATA.items || []).map((it) => Object.assign({}, it, {
      expert: STATE[it.id] || { status: "pending", label: "", reviewer: "", note: "", at: "" },
    }));
    const s = stats();
    const payload = {
      app: "RadioCheck",
      kind: "qc-review-export",
      version: 1,
      exported_at: new Date().toISOString(),
      reviewer: reviewer(),
      summary: {
        total: s.total,
        reviewed: s.reviewed,
        pending: s.pending,
        ai_conflict: s.conflict,
        ai_agree_rate: s.rate,
      },
      policy: DATA.policy,
      items,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `RadioCheck_质控复核_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast("已导出复核结果 JSON");
  }

  function bind() {
    $("#qcFilters").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-filter]");
      if (!btn) return;
      FILTER = btn.dataset.filter;
      document.querySelectorAll("#qcFilters button").forEach((b) => b.classList.toggle("on", b === btn));
      render();
    });
    $("#qcList").addEventListener("click", (e) => {
      const saveBtn = e.target.closest("[data-qc-save]");
      if (saveBtn) { save(saveBtn.dataset.qcSave); return; }
      const clearBtn = e.target.closest("[data-qc-clear]");
      if (clearBtn) { clear(clearBtn.dataset.qcClear); return; }
    });
    $("#exportQc").addEventListener("click", exportQc);
    const rev = $("#reviewer");
    if (rev) {
      try { rev.value = localStorage.getItem(REVIEWER_KEY) || ""; } catch (e) { /* ignore */ }
      rev.addEventListener("input", () => {
        try { localStorage.setItem(REVIEWER_KEY, rev.value); } catch (e) { /* ignore */ }
      });
    }
  }

  async function boot() {
    readState();
    bind();
    try {
      DATA = window.RCKB
        ? await window.RCKB.getJSON("/api/kb/audit/review", DATA_URL)
        : await (await fetch(DATA_URL, { cache: "no-cache" })).json();
      render();
    } catch (e) {
      $("#qcList").innerHTML = `<div class="qc-empty"><b>复核队列载入失败</b>请确认知识库服务已启动，或先完成站点构建。</div>`;
    }
  }

  boot();
})();
