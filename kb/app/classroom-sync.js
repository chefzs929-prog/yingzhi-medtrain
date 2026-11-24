(function () {
  "use strict";

  const URL_KEY = "radiocheck.sync.url";
  const TOKEN_KEY = "radiocheck.sync.token";
  const LAST_KEY = "radiocheck.sync.last";
  let base = "";
  let token = "";
  let suppress = false;
  let timer = null;
  let busy = false;

  const $ = (s) => document.querySelector(s);

  function readBase() {
    try {
      const qp = new URLSearchParams(location.search);
      let q = (qp.get("sync") || "").trim();
      const t = (qp.get("syncToken") || "").trim();
      if (t) {
        localStorage.setItem(TOKEN_KEY, t);
        token = t;
      }
      if (q === "off") {
        localStorage.removeItem(URL_KEY);
        localStorage.removeItem(TOKEN_KEY);
        token = "";
        return "";
      }
      if (q) {
        // 支持「地址#口令」：直接写在 prompt 里，或 URL 上 ?sync=地址#口令
        const hash = q.indexOf("#");
        if (hash > 0) {
          localStorage.setItem(TOKEN_KEY, q.slice(hash + 1));
          q = q.slice(0, hash);
        } else if (!t) {
          // URL 里的 # 会被浏览器当作锚点，需要单独取
          const frag = (location.hash || "").replace(/^#/, "").trim();
          if (frag && frag.indexOf("=") < 0 && frag.indexOf("/") < 0) {
            localStorage.setItem(TOKEN_KEY, frag);
          }
        }
        q = q.replace(/\/+$/, "");
        localStorage.setItem(URL_KEY, q);
        token = (localStorage.getItem(TOKEN_KEY) || "").trim();
        return q;
      }
      token = (localStorage.getItem(TOKEN_KEY) || "").trim();
      return (localStorage.getItem(URL_KEY) || "").replace(/\/+$/, "");
    } catch (e) {
      return "";
    }
  }

  function syncHeaders() {
    return token ? { "X-Sync-Token": token } : {};
  }

  function status(text, kind) {
    const el = $("#syncStatus");
    if (!el) return;
    el.textContent = text;
    el.dataset.kind = kind || "local";
    el.title = base ? `同步服务：${base}` : "当前只存在本机浏览器";
  }

  function mergeInto(local, remote) {
    if (!local || !remote) return local;
    (remote.classes || []).forEach((rc) => {
      let lc = (local.classes || []).find((c) => c.code === rc.code);
      if (!lc) { local.classes.push(rc); return; }
      (rc.students || []).forEach((s) => {
        if (!(lc.students || []).some((x) => x.name === s.name)) lc.students.push(s);
      });
      (rc.assignments || []).forEach((a) => {
        const i = (lc.assignments || []).findIndex((x) => x.id === a.id);
        if (i < 0) { lc.assignments.push(a); return; }
        const old = lc.assignments[i];
        if (String(a.updatedAt || a.createdAt || "") >= String(old.updatedAt || old.createdAt || "")) {
          lc.assignments[i] = a;
        }
      });
      (rc.groups || []).forEach((g) => {
        const lg = (lc.groups || []).find((x) => x.name === g.name);
        if (!lg) { lc.groups.push(g); return; }
        lg.memberIds = Array.from(new Set([].concat(lg.memberIds || [], g.memberIds || [])));
      });
    });
    (remote.attempts || []).forEach((a) => {
      if (!(local.attempts || []).some((x) => x.id === a.id)) local.attempts.push(a);
    });
    (remote.posts || []).forEach((p) => {
      const lp = (local.posts || []).find((x) => x.id === p.id);
      if (!lp) { local.posts.push(p); return; }
      (p.replies || []).forEach((r) => {
        if (!(lp.replies || []).some((x) => x.id === r.id)) lp.replies.push(r);
      });
    });
    if (!local.teacher || !local.teacher.name) local.teacher = remote.teacher || local.teacher;
    return local;
  }

  function writeLocal(db) {
    suppress = true;
    try { window.RCClass.write(db); } finally { suppress = false; }
  }

  async function pull() {
    if (!base || !window.RCClass) return false;
    status("同步中…", "busy");
    try {
      const r = await fetch(base + "/api/snapshot", { cache: "no-store", headers: syncHeaders() });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const j = await r.json();
      const local = window.RCClass.read();
      const merged = mergeInto(local, j.data || {});
      writeLocal(merged);
      try { localStorage.setItem(LAST_KEY, new Date().toISOString()); } catch (e) { /* ignore */ }
      status("已同步 " + new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }), "ok");
      if (window.RCRender) window.RCRender();
      return true;
    } catch (e) {
      status("离线 · 本机模式", "offline");
      return false;
    }
  }

  async function push() {
    if (!base || suppress || busy || !window.RCClass) return false;
    busy = true;
    status("同步中…", "busy");
    try {
      const r = await fetch(base + "/api/merge", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, syncHeaders()),
        body: JSON.stringify({ data: window.RCClass.read() }),
      });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const j = await r.json();
      if (j.data) writeLocal(j.data);
      try { localStorage.setItem(LAST_KEY, new Date().toISOString()); } catch (e) { /* ignore */ }
      status("已同步 " + new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }), "ok");
      if (window.RCRender) window.RCRender();
      return true;
    } catch (e) {
      status("离线 · 本机模式", "offline");
      return false;
    } finally {
      busy = false;
    }
  }

  function afterWrite() {
    if (suppress || !base) return;
    clearTimeout(timer);
    timer = setTimeout(push, 900);
  }

  function setup() {
    const cur = base;
    const next = window.prompt(
      "输入同步服务地址（例如 http://127.0.0.1:8820）。\n若服务端设了口令，写成 地址#口令。\n留空则关闭同步，回到本机模式。",
      cur
    );
    if (next === null) return;
    let v = next.trim();
    let tok = "";
    const hash = v.indexOf("#");
    if (hash > 0) {
      tok = v.slice(hash + 1).trim();
      v = v.slice(0, hash);
    }
    v = v.replace(/\/+$/, "");
    try {
      if (v) localStorage.setItem(URL_KEY, v); else localStorage.removeItem(URL_KEY);
      if (tok) localStorage.setItem(TOKEN_KEY, tok); else if (!v) localStorage.removeItem(TOKEN_KEY);
    } catch (e) { /* ignore */ }
    location.reload();
  }

  function bind() {
    const btn = $("#syncSetup");
    if (btn) btn.addEventListener("click", setup);
  }

  function boot() {
    base = readBase();
    bind();
    if (!base) {
      status("本机模式", "local");
      return;
    }
    status("连接中…", "busy");
    pull();
    // 页面从后台回到前台时拉一次，避免两台设备互相看不到。
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) pull();
    });
  }

  window.RCSync = { boot, pull, push, afterWrite, base: () => base };

  if (document.readyState === "complete") setTimeout(boot, 300);
  else window.addEventListener("load", () => setTimeout(boot, 300));
})();
