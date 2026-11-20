/* 静态模式：把 /api/* 映射到预生成的 JSON，供 GitHub Pages 等纯静态托管使用。
 * 生成端见 kb/scripts/export_teach_static.py。
 */
(function () {
  const FIXED = {
    "/api/chapters": "../data/teach/chapters.json",
    "/api/cases": "../data/teach/cases.json",
    "/api/meta": "../data/teach/meta.json",
    "/api/audit": "../data/teach/audit.json",
  };

  function path(p) {
    if (FIXED[p]) return FIXED[p];
    let m = p.match(/^\/api\/lesson\/(.+)$/);
    if (m) return "../data/teach/lesson-" + decodeURIComponent(m[1]) + ".json";
    m = p.match(/^\/api\/cases\/(.+)$/);
    if (m) return "../data/teach/case-" + decodeURIComponent(m[1]) + ".json";
    return null;
  }

  /* 病例图片在静态站里位于 ../images/，这里统一改写，避免每个调用点单独处理 */
  function fixImages(text) {
    return text.replace(/"\/images\//g, '"../images/');
  }

  window.YZStatic = { path, fixImages, enabled: true };
})();
