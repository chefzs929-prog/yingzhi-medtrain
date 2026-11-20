/* RadioCheck · 产品首页逻辑
 * 只做三件事：把知识库计数填进页面、挂载人体模型、把选中的部位渲染成右侧面板。
 * 不发起网络请求，不计算知识内容，所有数字都来自 data/kb.js。
 */
(function () {
  "use strict";

  const KB = window.__KB__;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  if (!KB) {
    const host = $("#bmHost");
    if (host) host.innerHTML = '<div class="bp-empty"><b>知识数据未载入</b><span>请先运行 <code>python3 medtrain/build_data.py</code>。</span></div>';
    return;
  }

  const META = KB.meta || {};
  const COUNTS = META.counts || {};
  const REGIONS = META.regions || [];
  const SIGNS = KB.signs || [];
  const CASES = KB.cases || [];

  const signCount = {};
  SIGNS.forEach((s) => { signCount[s.region_id] = (signCount[s.region_id] || 0) + 1; });
  const caseCount = {};
  CASES.forEach((c) => { caseCount[c.region_id] = (caseCount[c.region_id] || 0) + 1; });

  const REGION_DESC = {
    "REG-CHEST": "胸片与胸部 CT 的主要分区：肺野、纵隔、膈下。",
    "REG-HEAD-NECK": "头颅与颈部：脑实质、脑室、颈部间隙。",
    "REG-BREAST": "乳腺超声与钼靶：腺体层、导管、腋窝淋巴结。",
    "REG-ABDOMEN": "腹部实质脏器与空腔脏器：肝胆胰脾、肾、肠道。",
    "REG-MSK": "骨骼、关节与脊柱：骨折、退变、椎管与软组织。",
  };

  /* ---------- 统计条 ---------- */
  function renderStats() {
    const el = $("#statRow");
    if (!el) return;
    const items = [
      [COUNTS.signs, "征象词条"],
      [COUNTS.guidelines, "指南条款"],
      [COUNTS.cases, "公开病例"],
      [COUNTS.drills, "病例演练"],
      [COUNTS.quiz, "考点题"],
      [COUNTS.dual, "双引用结论"],
    ];
    el.innerHTML = items.map(([n, label]) =>
      `<div><b>${n != null ? n : "—"}</b><span>${label}</span></div>`).join("");
  }

  /* ---------- 右侧面板 ---------- */
  function renderPanel(regionId) {
    const panel = $("#bmPanel");
    if (!panel) return;

    if (!regionId) {
      const hot = SIGNS.slice(0, 5);
      panel.innerHTML = `
        <div class="bp-h"><b>按部位进入</b><span>${REGIONS.length} 个部位</span></div>
        <div class="bp-regions">
          ${REGIONS.map((r) => `<button class="bp-region-btn" type="button" data-pick-region="${esc(r.id)}">
            <b>${esc(r.name)}</b>
            <span>${signCount[r.id] || 0} 词条 · ${caseCount[r.id] || 0} 病例</span>
          </button>`).join("")}
        </div>
        <div class="bp-h" style="margin-top:16px"><b>高频征象</b><span>全库前 5 条</span></div>
        <div class="bp-list">
          ${hot.map((s) => `<a class="bp-item" href="app.html?role=student#/learn/${s.id}">
            <span>${esc(s.name)}</span><em>${esc((s.modality || []).join("/"))}</em>
          </a>`).join("")}
        </div>
        <p style="margin:12px 0 0;font-size:11.5px;color:var(--faint)">也可以直接点左侧人体模型。模型接口状态：${esc((window.YZ.BodyModel.status() || {}).note || "")}</p>
        <div class="bp-acts">
          <a class="btn primary" href="app.html?role=student">以学生身份进入</a>
          <a class="btn" href="app.html?role=doctor#/apply">以医生身份进入</a>
        </div>`;
      return;
    }

    const region = REGIONS.find((r) => r.id === regionId) || { id: regionId, name: regionId };
    const signs = SIGNS.filter((s) => s.region_id === regionId);
    const cases = CASES.filter((c) => c.region_id === regionId);
    const top = signs.slice(0, 5);
    const pics = cases.filter((c) => c.image).slice(0, 4);

    panel.innerHTML = `
      <div class="bp-h">
        <b>${esc(region.name)}</b>
        <span>${esc(region.id)}</span>
      </div>
      <div class="bp-nums">
        <div><b>${signs.length}</b><span>征象词条</span></div>
        <div><b>${cases.length}</b><span>公开病例</span></div>
        <div><b>${signs.filter((s) => (s.modality || []).length).length}</b><span>带模态标注</span></div>
      </div>
      <p style="margin:0 0 10px;font-size:12.5px;color:var(--muted)">${esc(REGION_DESC[regionId] || "")}</p>
      ${pics.length ? `
      <p class="bp-shots-h">该部位公开影像 · 点击查看</p>
      <div class="bp-shots">
        ${pics.map((c) => `<button class="bp-shot" type="button" data-img="${esc(c.image)}"
            data-title="${esc(c.title)}" data-license="${esc(c.license || "")}" data-artist="${esc(c.artist || "")}">
            <img src="${esc(c.image)}" alt="${esc(c.title)}" loading="lazy">
            <span>${esc(c.title)}</span>
          </button>`).join("")}
      </div>` : `<p class="bp-shots-h" style="color:var(--faint)">该部位暂无公开影像</p>`}
      <div class="bp-list">
        ${top.length
          ? top.map((s) => `<a class="bp-item" href="app.html?role=student#/learn/${s.id}">
              <span>${esc(s.name)}</span><em>${esc(s.id)}</em>
            </a>`).join("")
          : `<div class="bp-item" style="justify-content:center;color:var(--faint)">该部位暂无词条</div>`}
      </div>
      <div class="bp-acts">
        <a class="btn primary" href="app.html?role=student#/learn">以学生身份进入</a>
        <a class="btn" href="app.html?role=doctor#/apply">以医生身份进入</a>
      </div>`;
  }

  /* ---------- 影像灯箱 ---------- */
  let lb = null;

  function ensureLightbox() {
    if (lb) return lb;
    lb = document.createElement("div");
    lb.className = "bp-lightbox";
    lb.hidden = true;
    lb.innerHTML = `<figure>
        <img alt="">
        <figcaption><b data-lb-title></b><span data-lb-meta></span></figcaption>
        <button type="button" class="bp-lb-close" data-lb-close aria-label="关闭">关闭</button>
      </figure>`;
    document.body.appendChild(lb);
    lb.addEventListener("click", (e) => {
      if (e.target === lb || e.target.closest("[data-lb-close]")) closeLightbox();
    });
    return lb;
  }

  function openLightbox(src, title, license, artist) {
    const box = ensureLightbox();
    const img = box.querySelector("img");
    img.src = src;
    img.alt = title || "";
    box.querySelector("[data-lb-title]").textContent = title || "";
    box.querySelector("[data-lb-meta]").textContent = [license, artist].filter(Boolean).join(" · ");
    box.hidden = false;
  }

  function closeLightbox() {
    if (lb) lb.hidden = true;
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeLightbox();
  });

  document.addEventListener("click", (e) => {
    const pick = e.target.closest("[data-pick-region]");
    if (pick) { renderPanel(pick.dataset.pickRegion); return; }
    const shot = e.target.closest(".bp-shot");
    if (!shot) return;
    openLightbox(shot.dataset.img, shot.dataset.title, shot.dataset.license, shot.dataset.artist);
  });

  /* ---------- 模型状态 ---------- */
  function renderStatus(handle) {
    const el = $("#bmStatus");
    if (!el) return;
    const st = (handle && handle.status ? handle.status() : window.YZ.BodyModel.status()) || {};
    const isAdapter = st.mode === "adapter";
    el.className = "bm-status" + (isAdapter ? " adapter" : "");
    el.textContent = isAdapter ? `3D 适配器 · ${st.adapterName || "已接入"}` : "SVG 占位 · 3D 接口已预留";
    el.title = st.note || "";
  }

  /* ---------- 启动 ---------- */
  function boot() {
    renderStats();
    renderPanel(null);

    const host = $("#bmHost");
    if (!host || !window.YZ || !window.YZ.BodyModel) {
      renderStatus(null);
      return;
    }

    const regions = REGIONS.map((r) => ({
      id: r.id,
      name: r.name,
      count: signCount[r.id] || 0,
    }));

    const handle = window.YZ.BodyModel.mount(host, {
      regions,
      onSelect: (id) => renderPanel(id),
    });

    if (handle && handle.fallbackReason) {
      const tag = host.querySelector("[data-bm-tag]");
      if (tag) tag.textContent = "3D 适配器加载失败，已回落 SVG：" + handle.fallbackReason;
    }

    renderStatus(handle);
    window.__BM_HANDLE__ = handle;
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
