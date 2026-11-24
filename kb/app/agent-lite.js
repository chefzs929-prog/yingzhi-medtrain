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

  const LOCAL_DEFAULT = "http://127.0.0.1:8800";
  const LS_BASE = "radiocheck.agent.base";
  const LS_BASE_LEGACY = "yzApiBase";
  const localHost = /^(127\.0\.0\.1|localhost|\[::1\])$/i.test(location.hostname);
  const hostedStatic = /(^|\.)github\.io$|(^|\.)githubusercontent\.com$/i.test(location.hostname);
  // main.py 托管时注入；有它就直接同源，不再猜 8800。
  const dynamicHint = (() => {
    try {
      const m = document.querySelector('meta[name="rc-api"]');
      return !!(m && m.getAttribute("content") === "same-origin");
    } catch (e) { return false; }
  })();
  const CONV_KEY = "radiocheck.agent.conversation.";
  let healthCache = null;
  let healthAt = 0;

  function normBase(v) {
    return String(v == null ? "" : v).trim().replace(/\/+$/, "");
  }

  /* 地址优先级：window 注入 > URL 参数 > 用户保存 > 同源/本地默认。
   * 线上页面若没有同源后端，用户可在“连接设置”里填云端 Agent 地址并持久化。 */
  function readSavedBase() {
    try {
      return normBase(localStorage.getItem(LS_BASE) || localStorage.getItem(LS_BASE_LEGACY) || "");
    } catch (e) { return ""; }
  }

  function readQueryBase() {
    try {
      const p = new URLSearchParams(location.search);
      return normBase(p.get("agent") || p.get("api") || "");
    } catch (e) { return ""; }
  }

  function defaultBase() {
    // file:// 没有同源可用，只能连本机 8800；
    // main.py 托管（有 meta）直接同源；其余本地静态页退回 8800。
    if (location.protocol === "file:") return LOCAL_DEFAULT;
    if (dynamicHint) return "";
    if (localHost && !hostedStatic) return LOCAL_DEFAULT;
    return "";
  }

  function candidateBases() {
    if (BASE) return [BASE];
    const list = [];
    if (dynamicHint || !localHost) list.push(""); // 同源优先
    if (localHost && !hostedStatic) list.push(LOCAL_DEFAULT);
    return Array.from(new Set(list));
  }

  let BASE = normBase(window.RC_AGENT_BASE) || readQueryBase() || readSavedBase() || defaultBase();

  function setBase(url) {
    const v = normBase(url);
    try {
      if (v) localStorage.setItem(LS_BASE, v);
      else localStorage.removeItem(LS_BASE);
      localStorage.removeItem(LS_BASE_LEGACY);
    } catch (e) { /* 隐私模式忽略 */ }
    BASE = v || defaultBase();
    healthCache = null;
    healthAt = 0;
    return BASE;
  }

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

  function classifyProbeError(e, base) {
    const msg = String((e && e.message) || e || "");
    const b = base == null ? BASE : base;
    if (!b && location.protocol === "file:") return "unconfigured";
    if (location.protocol === "https:" && /^http:\/\//i.test(b)) return "mixed-content";
    if (e && e.name === "AbortError") return "timeout";
    if (/failed to fetch|networkerror|load failed|http/i.test(msg)) return "network";
    return "unknown";
  }

  const REASON_TEXT = {
    unconfigured: "当前页面没有配置 Agent 服务地址。线上版本需要填写已部署的 HTTPS Agent 地址。",
    "mixed-content": "HTTPS 页面不能直接连接 http:// 地址，浏览器会拦截。请填写 HTTPS 的 Agent 地址。",
    timeout: "连接 Agent 超时，服务可能未启动或网络不通。",
    network: "连不上 Agent 服务，请检查地址是否可访问。",
    unknown: "Agent 服务探测失败。",
    static: "当前为纯静态页面，未探测同源服务。",
  };

  async function probe(force) {
    const now = Date.now();
    if (!force && healthCache && now - healthAt < 30000) return healthCache;
    if (!BASE && (location.protocol === "file:" || hostedStatic)) {
      healthCache = { ok: false, base: BASE, reason: "unconfigured", error: REASON_TEXT.unconfigured };
      healthAt = Date.now();
      return healthCache;
    }
    const tried = candidateBases();
    let last = null;
    for (const base of tried) {
      const t = timeoutSignal(base ? 1800 : 900);
      try {
        const r = await fetch(base + "/api/health", { signal: t.signal, cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const j = await r.json();
        // 同源命中就固定同源；否则记住退回的地址，后续 /api/ask 才不会再猜。
        BASE = base;
        healthCache = {
          ok: !!j.ok,
          base: BASE,
          agent: !!j.agent_ready,
          llm: !!(j.llm_route && j.llm_route.ready),
          reason: j.ok ? "" : (j.fallback_reason || "degraded"),
          raw: j,
        };
        healthAt = Date.now();
        return healthCache;
      } catch (e) {
        last = { e, base };
      } finally {
        t.clear();
      }
    }
    const reason = classifyProbeError(last && last.e, last && last.base);
    healthCache = {
      ok: false,
      base: BASE,
      reason,
      error: String((last && last.e && last.e.message) || last && last.e || ""),
      text: REASON_TEXT[reason] || REASON_TEXT.unknown,
    };
    healthAt = Date.now();
    return healthCache;
  }

  async function ask(payload, handlers) {
    handlers = handlers || {};
    // BASE 为空是合法的“同源”；只有 file:// 或 GitHub Pages 且没有显式地址才算未配置。
    if (!BASE && (location.protocol === "file:" || hostedStatic)) {
      const err = new Error(REASON_TEXT.unconfigured);
      err.code = "unconfigured";
      throw err;
    }
    if (location.protocol === "https:" && /^http:\/\//i.test(BASE)) {
      const err = new Error(REASON_TEXT["mixed-content"]);
      err.code = "mixed-content";
      throw err;
    }
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
      const err = new Error(e && e.name === "AbortError"
        ? "Agent 请求超时（45s）；首次生成可能较慢，可重试或打开 trace"
        : "无法连接 Agent 服务（" + BASE + "）");
      err.code = e && e.name === "AbortError" ? "timeout" : "network";
      throw err;
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
  const DROP_LINE = /^(依据|参考(文献|来源)?|引用(来源)?|证据(来源)?|缺失|边界(说明)?|后台说明|免责声明|注)\s*[:：]|^以上(内容)?仅供/;

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
    panel.innerHTML = `<div class="agent-head"><b>智能解释</b><span class="agent-badge">生成中</span></div>
      <div class="agent-text"></div>
      <div class="agent-foot">
        <button class="agent-toggle" type="button" aria-expanded="false">查看依据</button>
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
    const label = { sign: "文献来源", case: "病例来源", guideline: "指南条款", region: "影像位置", claim: "结论条目" }[c.type] || "知识库条目";
    return `<div class="agent-cite ${bad ? "bad" : ""}">
      <b>${esc(label)}${c.title ? " · " + esc(c.title) : ""}</b>
      ${c.source_url ? `<a href="${esc(c.source_url)}" target="_blank" rel="noopener">查看来源 ↗</a>` : ""}
      ${c.id ? `<code class="agent-cite-id">${esc(c.id)}</code>` : ""}
      ${bad ? `<em>未在知识库中校验</em>` : ""}
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
      ui.badge.textContent = "未连接";
      ui.text.innerHTML = `智能解释暂时不可用。你仍然可以使用知识库检索查看标注与出处。
        <div class="agent-conn-row">${connButtonHTML()}</div>
        <details class="agent-tech"><summary>技术信息</summary>
          <p>${esc(h.text || REASON_TEXT[h.reason] || "服务探测失败")}</p>
          <p>当前地址：<code>${esc(BASE || "同源 /api")}</code></p>
          ${localPage ? "需要本地服务时，运行：<code>python3 yingzhi/serve/main.py --port 8800</code>，然后刷新本页。" : ""}
        </details>`;
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
        `${evidence ? `以下要点为准：${evidence}。` : ""}${q}`
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
      const served = out.done && out.done.degraded ? "简化回答" : (out.done && out.done.served_by === "agent" ? "已完成" : "已完成");
      ui.badge.className = "agent-badge " + (out.done && out.done.degraded ? "warn" : "ok");
      ui.badge.textContent = served;
      const seconds = done.total_ms != null ? (done.total_ms / 1000).toFixed(1) + " 秒" : "";
      ui.meta.innerHTML = `<details class="agent-tech"><summary>技术信息</summary>
        <p>${esc([seconds, done.reason || ""].filter(Boolean).join(" · ") || "已完成")}</p>
        ${done.run_id ? `<p><a href="${BASE}/api/trace/${encodeURIComponent(done.run_id)}" target="_blank" rel="noopener">查看运行记录</a></p>` : ""}
      </details>`;
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

  /* ---------- 连接设置：线上页面必须能指向已部署的 Agent ---------- */
  const CONN_CSS = `
.rc-conn-mask{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;padding:20px;
  background:rgba(9,20,26,.56);backdrop-filter:blur(2px)}
.rc-conn-mask[hidden]{display:none}
.rc-conn{width:min(460px,100%);background:#fff;color:#0f2029;border-radius:16px;
  padding:20px 22px 18px;box-shadow:0 30px 80px -30px rgba(0,0,0,.65);
  font:14px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
.rc-conn-head{display:flex;align-items:center;justify-content:space-between;gap:12px}
.rc-conn-head b{font-size:15.5px}
.rc-conn-x{width:28px;height:28px;border:0;background:#f1f6f5;border-radius:8px;
  font-size:17px;line-height:1;color:#5f7784;cursor:pointer}
.rc-conn-x:hover{background:#e6efed;color:#0b4f55}
.rc-conn-desc{margin:10px 0 14px;font-size:12.5px;line-height:1.75;color:#5f7784}
.rc-conn-desc code{font-family:"SFMono-Regular",Menlo,Consolas,monospace;font-size:11.5px;
  background:#f2f8f6;padding:1px 5px;border-radius:4px;color:#0b4f55}
.rc-conn-label{display:block;font-size:11px;letter-spacing:.1em;color:#8ba0ab;margin-bottom:5px}
.rc-conn-input{width:100%;height:40px;padding:0 12px;border:1px solid #dbe8e4;border-radius:10px;
  font:13px/1.4 "SFMono-Regular",Menlo,Consolas,monospace;color:#0f2029;background:#fbfefd}
.rc-conn-input:focus{outline:2px solid rgba(14,124,123,.28);border-color:#0e7c7b}
.rc-conn-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.rc-conn-btn{height:36px;padding:0 14px;border-radius:9px;border:1px solid #dbe8e4;background:#fff;
  color:#2a4350;font-size:12.5px;font-weight:600;cursor:pointer}
.rc-conn-btn:hover{border-color:#0e7c7b;color:#0e7c7b}
.rc-conn-btn.primary{background:#0b4f55;border-color:#0b4f55;color:#fff}
.rc-conn-btn.primary:hover{background:#083f44;color:#fff}
.rc-conn-status{margin:11px 0 0;font-size:12px;line-height:1.6;min-height:18px;color:#5f7784}
.rc-conn-status.ok{color:#147a5b}
.rc-conn-status.err{color:#b23b3b}
.agent-conn-link{margin-top:8px;display:inline-flex;align-items:center;gap:5px;
  border:1px solid #dbe8e4;background:#fff;color:#0b4f55;border-radius:8px;
  padding:4px 10px;font-size:11.5px;font-weight:600;cursor:pointer}
.agent-conn-link:hover{background:#f2f8f6}
`;

  function ensureConnStyles() {
    if (document.getElementById("rcAgentConnStyle")) return;
    const s = document.createElement("style");
    s.id = "rcAgentConnStyle";
    s.textContent = CONN_CSS;
    document.head.appendChild(s);
  }

  let connMask = null;

  function closeConn() {
    if (connMask) connMask.hidden = true;
  }

  function openConn() {
    ensureConnStyles();
    if (!connMask) {
      connMask = document.createElement("div");
      connMask.id = "rcAgentConn";
      connMask.className = "rc-conn-mask";
      connMask.hidden = true;
      connMask.innerHTML = [
        '<div class="rc-conn" role="dialog" aria-modal="true" aria-labelledby="rcConnTitle">',
        '<div class="rc-conn-head"><b id="rcConnTitle">连接智能解释服务</b>',
        '<button type="button" class="rc-conn-x" data-conn-close aria-label="关闭">×</button></div>',
        '<p class="rc-conn-desc">线上页面需要填写已部署的 Agent 地址（需 HTTPS）。本地演示可直接用 <code>http://127.0.0.1:8800</code>。</p>',
        '<label class="rc-conn-label" for="rcConnInput">服务地址</label>',
        '<input id="rcConnInput" class="rc-conn-input" type="url" placeholder="https://your-agent.example.com" autocomplete="off" spellcheck="false">',
        '<div class="rc-conn-actions">',
        '<button type="button" class="rc-conn-btn primary" data-conn-test>测试并保存</button>',
        '<button type="button" class="rc-conn-btn" data-conn-local>用本地 8800</button>',
        '<button type="button" class="rc-conn-btn" data-conn-clear>清除配置</button>',
        "</div>",
        '<p class="rc-conn-status" data-conn-status></p>',
        "</div>",
      ].join("");
      document.body.appendChild(connMask);

      connMask.addEventListener("click", (e) => {
        if (e.target === connMask) closeConn();
        if (e.target.closest("[data-conn-close]")) closeConn();
        const input = connMask.querySelector("#rcConnInput");
        const status = connMask.querySelector("[data-conn-status]");
        if (e.target.closest("[data-conn-local]")) {
          input.value = LOCAL_DEFAULT;
          testAndSave();
        }
        if (e.target.closest("[data-conn-clear]")) {
          setBase("");
          input.value = BASE;
          status.className = "rc-conn-status";
          status.textContent = "已清除，当前使用默认地址：" + (BASE || "同源");
        }
        if (e.target.closest("[data-conn-test]")) testAndSave();
      });

      connMask.querySelector("#rcConnInput").addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          testAndSave();
        }
        if (e.key === "Escape") closeConn();
      });

      async function testAndSave() {
        const input = connMask.querySelector("#rcConnInput");
        const status = connMask.querySelector("[data-conn-status]");
        const url = normBase(input.value);
        if (!url) {
          status.className = "rc-conn-status err";
          status.textContent = "请填写服务地址，例如 https://your-agent.example.com";
          return;
        }
        setBase(url);
        status.className = "rc-conn-status";
        status.textContent = "正在测试 " + BASE + "/api/health …";
        const h = await probe(true);
        if (h.ok) {
          status.className = "rc-conn-status ok";
          status.textContent = "已连接" + (h.agent ? "（Agent 就绪）" : (h.llm ? "（模型直连就绪）" : "（服务可用，Agent 未就绪）")) + "。现在可以重新提问。";
          setTimeout(closeConn, 900);
        } else {
          status.className = "rc-conn-status err";
          status.textContent = (h.text || REASON_TEXT[h.reason] || "连接失败") + " 已保存，可稍后重试。";
        }
      }
    }
    const input = connMask.querySelector("#rcConnInput");
    const status = connMask.querySelector("[data-conn-status]");
    input.value = BASE || (staticHost ? LOCAL_DEFAULT : "");
    status.className = "rc-conn-status";
    status.textContent = BASE ? "当前：" + BASE : "当前未配置，将走同源 /api。";
    connMask.hidden = false;
    setTimeout(() => input.focus(), 30);
  }

  /* 失败面板里的“连接设置”按钮：任何页面都可复用。 */
  function connButtonHTML() {
    ensureConnStyles();
    return '<button type="button" class="agent-conn-link" data-agent-conn>连接设置</button>';
  }

  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-agent-conn]")) {
      e.preventDefault();
      openConn();
    }
  });

  window.RCAgent = {
    probe,
    ask,
    configure: openConn,
    setBase,
    base: () => BASE,
    localDefault: LOCAL_DEFAULT,
    connButtonHTML,
  };
})();
