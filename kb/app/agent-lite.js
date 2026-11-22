/* RadioCheck · 轻量 Agent 桥
 *
 * 只做三件事：
 *   1. 探测本地 yingzhi/serve 是否可用（GET /api/health）；
 *   2. 把 /api/ask 的 SSE 解析成 delta / citation / done；
 *   3. 在“分区讲解”“错题追问”两个高可行场景里渲染解释与引用。
 *
 * 硬规则：
 *   - Agent 只解释库内证据，不判分、不诊断、不给治疗建议；
 *   - 引用只展示服务端 citation 事件；未验证 id 标红；
 *   - 服务不可用时明确提示启动命令，不伪装成已接入。
 */
(function () {
  "use strict";

  const BASE = (window.RC_AGENT_BASE || "http://127.0.0.1:8800").replace(/\/$/, "");
  const CONV_KEY = "radiocheck.agent.conversation.";
  let healthCache = null;
  let healthAt = 0;

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  function conversationId(surface) {
    const key = CONV_KEY + (surface || "general");
    try {
      let v = sessionStorage.getItem(key);
      if (!v) {
        v = "c-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
        sessionStorage.setItem(key, v);
      }
      return v;
    } catch (e) {
      return "c-" + Date.now().toString(36);
    }
  }

  function timeoutSignal(ms) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ms);
    return { signal: ctrl.signal, clear: () => clearTimeout(timer) };
  }

  async function probe(force) {
    const now = Date.now();
    if (!force && healthCache && now - healthAt < 30000) return healthCache;
    const t = timeoutSignal(1800);
    try {
      const r = await fetch(BASE + "/api/health", { signal: t.signal });
      const j = await r.json();
      healthCache = {
        ok: !!j.ok,
        agent: !!j.agent_ready,
        llm: !!(j.llm_route && j.llm_route.ready),
        raw: j,
      };
    } catch (e) {
      healthCache = { ok: false, error: String(e && e.message || e) };
    } finally {
      t.clear();
    }
    healthAt = Date.now();
    return healthCache;
  }

  async function ask(payload, handlers) {
    handlers = handlers || {};
    const surface = payload.surface || "general";
    const body = Object.assign({
      role: "student",
      device: "desktop",
      chain: "kb_qa",
      mode: "auto",
      conversation_id: conversationId(surface),
    }, payload);
    const t = timeoutSignal(handlers.timeout || 45000);
    let r;
    try {
      r = await fetch(BASE + "/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: t.signal,
      });
    } catch (e) {
      t.clear();
      throw new Error(e && e.name === "AbortError" ? "Agent 请求超时（45s）；首次生成可能较慢，可重试或打开 trace" : "无法连接本地 Agent");
    }
    if (!r.ok) {
      t.clear();
      let msg = "HTTP " + r.status;
      try {
        const j = await r.json();
        if (j && (j.hint || j.detail || j.error)) msg = j.hint || j.detail || j.error;
      } catch (e) { /* 非 JSON */ }
      throw new Error(msg);
    }
    if (!r.body) {
      t.clear();
      throw new Error("浏览器不支持流式响应");
    }

    const out = { text: "", cites: [], done: null, trace: [], tools: [] };
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    const dispatch = (kind, data) => {
      if (kind === "delta") out.text += (data && data.text) || "";
      else if (kind === "citation") out.cites.push(data || {});
      else if (kind === "trace") out.trace.push(data || {});
      else if (kind === "tool") out.tools.push(data || {});
      else if (kind === "reset") out.text = "";
      else if (kind === "done") out.done = data || {};
      if (typeof handlers.onEvent === "function") handlers.onEvent(kind, data, out);
    };

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true }).replace(/\r\n/g, "\n");
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, i);
          buf = buf.slice(i + 2);
          let kind = "message";
          let data = "";
          chunk.split("\n").forEach((line) => {
            if (line.startsWith("event:")) kind = line.slice(6).trim();
            else if (line.startsWith("data:")) data += line.slice(5).trim();
          });
          if (!data) continue;
          try { dispatch(kind, JSON.parse(data)); } catch (e) { /* 坏帧跳过 */ }
          if (out.done) {
            try { await reader.cancel(); } catch (e) { /* 已关闭 */ }
            return out;
          }
        }
      }
      return out;
    } finally {
      t.clear();
    }
  }

  /* 只留结论：去掉“依据/参考/边界/免责声明”等后台说明行；全被过滤时回退原文。 */
  const DROP_LINE = /^(依据|参考(文献|来源)?|引用(来源)?|证据(来源)?|边界(说明)?|后台说明|免责声明|注)\s*[:：]|^以上(内容)?仅供/;

  function compactAnswer(text) {
    const raw = String(text == null ? "" : text).trim();
    if (!raw) return "";
    const kept = raw.split("\n").filter((line) => {
      const probe = line.trim().replace(/^[>#*\-\s]+/, "");
      return !DROP_LINE.test(probe);
    });
    const out = kept.join("\n").replace(/\n{3,}/g, "\n\n").trim();
    return out || raw;
  }

  function renderPanel(panel) {
    panel.innerHTML = `<div class="agent-head"><b>Agent 解释</b><span class="agent-badge">生成中</span></div>
      <div class="agent-text"></div>
      <div class="agent-foot">
        <button class="agent-toggle" type="button" aria-expanded="false">查看依据</button>
        <span class="agent-note">仅供教学，不构成诊断</span>
      </div>
      <div class="agent-detail" hidden>
        <div class="agent-cites"></div>
        <div class="agent-meta"></div>
        <p class="agent-disclaimer">仅用于医学影像教学与研究，不构成诊断意见，不替代临床决策。</p>
      </div>`;
    return {
      text: panel.querySelector(".agent-text"),
      cites: panel.querySelector(".agent-cites"),
      meta: panel.querySelector(".agent-meta"),
      badge: panel.querySelector(".agent-badge"),
      detail: panel.querySelector(".agent-detail"),
      toggle: panel.querySelector(".agent-toggle"),
      foot: panel.querySelector(".agent-foot"),
    };
  }

  function citationHTML(c, unverified) {
    const bad = unverified.has(c.id);
    return `<div class="agent-cite ${bad ? "bad" : ""}">
      <b>${esc(c.id || "未命名引用")}</b>
      <span>${esc(c.title || c.kind || "")}</span>
      ${c.source_url ? `<a href="${esc(c.source_url)}" target="_blank" rel="noopener">来源 ↗</a>` : ""}
      ${bad ? `<em>未在库内校验</em>` : ""}
      ${c.hash_ok === false ? `<em>来源 hash 未校验</em>` : ""}
    </div>`;
  }

  async function run(btn, panel) {
    const q = (btn.dataset.agentQuery || "").trim();
    if (!q) return;
    if (btn.disabled) return;
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Agent 生成中…";
    const surface = btn.dataset.agentSurface || "clinic";
    const caseId = btn.dataset.agentCase || "";
    const zoneId = btn.dataset.agentZone || "";
    const signIds = (btn.dataset.agentSigns || "").split(",").filter(Boolean);

    panel.hidden = false;
    const ui = renderPanel(panel);
    ui.toggle.addEventListener("click", () => {
      const open = ui.detail.hidden;
      ui.detail.hidden = !open;
      ui.toggle.setAttribute("aria-expanded", String(open));
      ui.toggle.textContent = open ? "收起依据" : (ui.toggle.dataset.label || "查看依据");
    });
    const h = await probe(true);
    if (!h.ok) {
      ui.badge.className = "agent-badge err";
      ui.badge.textContent = "未启动";
      ui.text.innerHTML = `本地 Agent 服务不可用。先在仓库根目录运行：<br>
        <code>python3 yingzhi/serve/main.py --port 8800</code><br>
        然后刷新本页重试。静态站本身不调用大模型。`;
      ui.toggle.hidden = true;
      btn.disabled = false;
      btn.textContent = label;
      return;
    }

    const scoped = [
      caseId ? `病例 ${caseId}` : "",
      zoneId ? `分区 ${zoneId}` : "",
      signIds.length ? `征象 ${signIds.join("、")}` : "",
    ].filter(Boolean).join("；");
    const evidence = (btn.dataset.agentEvidence || "").trim();
    const concise = "回答要求：只给 2–4 句结论，直接回答；不要罗列依据、边界、免责声明或工具过程。";
    const finalQuery = (scoped
      ? `【${surface === "lab" ? "错题追问" : "分区讲解"}】${scoped}。` +
        `${evidence ? `以下库内证据为准：${evidence}。` : ""}${q}`
      : q) + " " + concise;

    try {
      const out = await ask({
        query: finalQuery,
        surface,
        context: {
          case_id: caseId,
          zone_id: zoneId,
          sign_ids: signIds,
        },
      }, {
        onEvent: (kind, data) => {
          if (kind === "delta") {
            ui.text.textContent = compactAnswer(out.text);
            panel.scrollTop = panel.scrollHeight;
          }
        },
      });
      ui.text.textContent = compactAnswer(out.text) || "本轮没有返回结论。";
      const unverified = new Set(((out.done && out.done.citation_audit) || {}).unverified || []);
      ui.cites.innerHTML = out.cites.length
        ? out.cites.map((c) => citationHTML(c, unverified)).join("")
        : `<div class="agent-empty">本轮未返回可核验引用。</div>`;
      const done = out.done || {};
      const served = out.done && out.done.degraded ? "降级" : (out.done && out.done.served_by) || "完成";
      ui.badge.className = "agent-badge " + (out.done && out.done.degraded ? "warn" : "ok");
      ui.badge.textContent = served;
      ui.meta.innerHTML = `${done.total_ms != null ? done.total_ms + "ms" : ""}
        ${done.run_id ? `<a href="${BASE}/api/trace/${encodeURIComponent(done.run_id)}" target="_blank" rel="noopener">trace ↗</a>` : ""}
        ${done.reason ? `<span>${esc(done.reason)}</span>` : ""}`;
      ui.toggle.dataset.label = out.cites.length ? `查看依据（${out.cites.length}）` : "查看依据";
      ui.toggle.textContent = ui.toggle.dataset.label;
    } catch (e) {
      ui.badge.className = "agent-badge err";
      ui.badge.textContent = "失败";
      ui.text.textContent = String(e && e.message || e);
      ui.cites.innerHTML = "";
      ui.toggle.hidden = true;
    } finally {
      btn.disabled = false;
      btn.textContent = label;
    }
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-agent-ask]");
    if (!btn) return;
    e.preventDefault();
    let panel = btn.parentElement.querySelector(".agent-panel");
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "agent-panel";
      panel.hidden = true;
      btn.parentElement.appendChild(panel);
    }
    run(btn, panel);
  });

  window.RCAgent = { probe, ask, base: BASE };
})();
