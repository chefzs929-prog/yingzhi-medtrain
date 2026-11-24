/* RadioCheck · 知识库取数适配层
 *
 * 页面优先从本地动态服务（同源 /api/kb/*）读取知识库与数据；
 * 服务不可用时回退到构建期静态 JSON，保证离线/静态托管仍能演示。
 *
 * 只做取数、探测与图片地址，不在前端做检索打分或诊断。
 */
(function () {
  "use strict";

  const params = (() => {
    try { return new URLSearchParams(location.search); } catch (e) { return null; }
  })();
  const explicit = String(
    (window.RC_API_BASE != null ? window.RC_API_BASE : (params ? params.get("api") : "")) || ""
  ).replace(/\/$/, "");
  const CACHE_KEY = "radiocheck.kbapi.v1";
  const SKIP_PORTS = new Set(["8811", "8899", "8080", "8000", "3000", "4173", "5500", "5501"]);
  const SKIP_HOSTS = /(^|\.)github\.io$|(^|\.)githubusercontent\.com$/i;
  let resolved = null;
  let probing = null;

  // 纯静态托管（验收用的 8811、GitHub Pages、file://）不探测后端，
  // 避免每个页面都产生一条 404 控制台错误；需要时用 ?api=... 显式指定。
  function canProbe() {
    if (explicit) return true;
    if (location.protocol === "file:") return false;
    if (SKIP_HOSTS.test(location.hostname)) return false;
    if (SKIP_PORTS.has(location.port)) return false;
    return true;
  }

  function readCache() {
    try { return JSON.parse(sessionStorage.getItem(CACHE_KEY) || "null"); }
    catch (e) { return null; }
  }

  function writeCache(value) {
    try { sessionStorage.setItem(CACHE_KEY, JSON.stringify(value)); }
    catch (e) { /* 隐私模式忽略 */ }
  }

  async function fetchJSON(url, timeout) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout || 2500);
    try {
      const r = await fetch(url, { cache: "no-cache", signal: ctrl.signal });
      if (!r.ok) throw new Error("HTTP " + r.status);
      return await r.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async function probe(force) {
    if (!canProbe()) {
      resolved = { ok: false, base: explicit, at: Date.now(), reason: "static" };
      return resolved;
    }
    if (!force) {
      if (resolved) return resolved;
      const cached = readCache();
      if (cached && Date.now() - (cached.at || 0) < 60000) {
        resolved = cached;
        return cached;
      }
    }
    if (probing) return probing;
    probing = (async () => {
      const bases = explicit ? [explicit] : [""];
      for (const base of bases) {
        try {
          const j = await fetchJSON(base + "/api/kb/health", 1200);
          if (j && j.ok) {
            resolved = {
              ok: true,
              base,
              at: Date.now(),
              version: j.version || "",
              counts: j.counts || {},
            };
            writeCache(resolved);
            return resolved;
          }
        } catch (e) { /* 试下一个地址 */ }
      }
      resolved = { ok: false, base: explicit, at: Date.now(), reason: "unavailable" };
      writeCache(resolved);
      return resolved;
    })();
    try { return await probing; } finally { probing = null; }
  }

  async function getJSON(path, fallbackUrl) {
    const p = await probe();
    if (p.ok) {
      try { return await fetchJSON(p.base + path, 9000); }
      catch (e) { /* 后端有异常时回退静态数据 */ }
    }
    if (!fallbackUrl) throw new Error("知识库服务不可用");
    return fetchJSON(fallbackUrl, 9000);
  }

  function imageUrl(path) {
    const raw = String(path == null ? "" : path).replace(/^\.\.\//, "").replace(/^\/+/, "");
    if (resolved && resolved.ok) {
      const rel = raw.replace(/^images\//, "");
      return resolved.base + "/api/kb/image/" + rel.split("/").map(encodeURIComponent).join("/");
    }
    return "../" + raw;
  }

  window.RCKB = {
    probe,
    getJSON,
    imageUrl,
    base: () => (resolved ? resolved.base : explicit),
    isLive: () => !!(resolved && resolved.ok),
  };
})();
