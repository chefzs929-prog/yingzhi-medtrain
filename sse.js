/* Agent 流式通道：POST /api/ask（SSE over fetch）
 *
 * 为什么不用 EventSource：
 *   EventSource 只支持 GET，无法带 JSON body，也无法设置 Content-Type。
 *   所以用 fetch + ReadableStream 手工解析 SSE 帧。
 *
 * 为什么要跨域：
 *   medtrain 是静态站（outputs/medtrain/），动态层在 127.0.0.1:8800。
 *   动态层已返回 Access-Control-Allow-Origin: *，并处理了 OPTIONS 预检。
 */
(function (YZ) {
  "use strict";

  /* 同源部署（动态层直接托管前端）时走相对路径，否则指向本地动态层 */
  function defaultBase() {
    const p = location.protocol;
    if (p === "http:" || p === "https:") {
      if (location.port === "8800") return "";
      const h = location.hostname;
      const local = h === "localhost" || h === "127.0.0.1" || h === "[::1]" || h === "";
      /* 线上静态托管：不向访客本机 127.0.0.1 发请求，改走同源；
         同源 /api/health 不存在会快速失败，前端按既有逻辑降级到本地规则引擎。 */
      if (!local) return "";
    }
    return "http://127.0.0.1:8800";
  }

  function apiBase() {
    try {
      const saved = localStorage.getItem("yzApiBase");
      if (saved) return saved.replace(/\/+$/, "");
    } catch (e) { /* 隐私模式下 localStorage 可能不可用 */ }
    return defaultBase();
  }

  function setApiBase(url) {
    try {
      if (url) localStorage.setItem("yzApiBase", url);
      else localStorage.removeItem("yzApiBase");
    } catch (e) { /* ignore */ }
  }

  async function agentHealth() {
    try {
      const r = await fetch(apiBase() + "/api/health", { cache: "no-store" });
      const d = await r.json();
      return d;
    } catch (e) {
      return { ok: false, reason: String((e && e.message) || e) };
    }
  }

  /* handlers: { trace, delta, citation, reset, done, error, close, timeout, role, device, chain }
   * 返回 { abort() } 供「停止」按钮使用。
   */
  function askStream(query, handlers) {
    const h = handlers || {};
    const ctrl = new AbortController();
    let finished = false;
    let gotDone = false;
    let closedByUser = false;

    /* 同时接受 trace / onTrace 两种写法。
     * 早期版本 learn.js 用的是 onTrace，而这里只查 h.trace，
     * 结果所有流事件都被静默丢弃，界面永远停在「运行中」。
     * 两种都支持，避免调用方再踩一次。 */
    const handlerOf = (name) => {
      if (typeof h[name] === "function") return h[name];
      const camel = "on" + name.charAt(0).toUpperCase() + name.slice(1);
      if (typeof h[camel] === "function") return h[camel];
      return null;
    };

    const emit = (name, payload) => {
      const fn = handlerOf(name);
      if (!fn) return;
      try { fn(payload); } catch (e) { console.warn("[yz:sse] handler " + name, e); }
    };

    const timer = setTimeout(() => {
      if (!finished) { ctrl.abort(); }
    }, h.timeout || 90000);

    (async () => {
      try {
        const resp = await fetch(apiBase() + "/api/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: query,
            role: h.role || "student",
            device: h.device || "desktop",
            chain: h.chain || "kb_qa",
            client_kb_version: h.kbVersion || "medtrain",
            context: h.context || {},
          }),
          signal: ctrl.signal,
        });

        if (!resp.ok) {
          emit("error", { reason: "HTTP " + resp.status });
          return;
        }
        if (!resp.body || !resp.body.getReader) {
          emit("error", { reason: "stream_unsupported" });
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });

          let idx;
          while ((idx = buf.indexOf("\n\n")) >= 0) {
            const block = buf.slice(0, idx);
            buf = buf.slice(idx + 2);

            let kind = "";
            let data = "";
            block.split("\n").forEach((line) => {
              if (line.startsWith("event:")) kind = line.slice(6).trim();
              else if (line.startsWith("data:")) data += line.slice(5).trim();
            });
            if (!data) continue;

            let payload;
            try { payload = JSON.parse(data); } catch (e) { continue; }

            if (kind === "trace") emit("trace", payload);
            else if (kind === "delta") emit("delta", payload);
            else if (kind === "citation") emit("citation", payload);
            else if (kind === "reset") emit("reset", payload);
            else if (kind === "done") { gotDone = true; emit("done", payload); }
            else if (kind === "error") { gotDone = true; emit("error", payload); }
          }
        }

        /* 兼容没有以空行结尾的最后一帧 */
        if (buf.trim()) {
          let kind = "";
          let data = "";
          buf.split("\n").forEach((line) => {
            if (line.startsWith("event:")) kind = line.slice(6).trim();
            else if (line.startsWith("data:")) data += line.slice(5).trim();
          });
          if (data) {
            let payload = null;
            try { payload = JSON.parse(data); } catch (e) { payload = null; }
            if (payload && kind === "done") { gotDone = true; emit("done", payload); }
            else if (payload && kind === "error") { gotDone = true; emit("error", payload); }
          }
        }

        /* 兜底：流正常结束却没收到 done/error（服务端中途崩溃、代理截断等），
         * 不能让界面永远停在「运行中」。 */
        if (!gotDone && !closedByUser) {
          emit("error", { reason: "stream_closed_without_done" });
        }
      } catch (e) {
        if (e && e.name === "AbortError") {
          if (!closedByUser) emit("error", { reason: "timeout_or_abort" });
        } else {
          emit("error", { reason: String((e && e.message) || e) });
        }
      } finally {
        finished = true;
        clearTimeout(timer);
        emit("close", {});
      }
    })();

    return {
      abort() {
        /* 主动停止（用户点「停止」或被下一次提问顶掉）：不当作错误事件，
         * 由调用方自己决定界面文案，也避免旧流污染新请求。 */
        closedByUser = true;
        try { ctrl.abort(); } catch (e) { /* ignore */ }
      },
    };
  }

  Object.assign(YZ, { askStream, agentHealth, apiBase, setApiBase });
})(window.YZ = window.YZ || {});
