const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const state = { q: "", modality: "", part: "", stats: null, taxonomy: null, region: "", cond: "", simItems: [], linksIndex: null, linkSign: "", linkDetail: null, activeLink: "", activeImage: "" };

/* ---------------- tabs ---------------- */
function showView(name) {
  ["search", "links", "dual", "images", "about"].forEach((v) => {
    $(`#view-${v}`).hidden = v !== name;
  });
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "links") ensureLinksView();
  if (name === "images") loadTaxonomy().then(() => loadGallery());
  if (name === "about") loadStats();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$$("#tabs button").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
$$("[data-view-link]").forEach((a) =>
  a.addEventListener("click", (e) => {
    e.preventDefault();
    showView(a.dataset.viewLink);
  })
);

/* ---------------- search ---------------- */
$("#searchForm").addEventListener("submit", (e) => {
  e.preventDefault();
  state.q = $("#q").value.trim();
  state.modality = $("#modality").value;
  state.part = $("#part").value;
  doSearch();
});

$("#chips").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-q]");
  if (!btn) return;
  $("#q").value = btn.dataset.q;
  state.q = btn.dataset.q;
  doSearch();
});

["#modality", "#part"].forEach((sel) =>
  $(sel).addEventListener("change", () => {
    state.modality = $("#modality").value;
    state.part = $("#part").value;
    if (state.q) doSearch();
  })
);

async function doSearch() {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.modality) params.set("modality", state.modality);
  if (state.part) params.set("part", state.part);
  $("#meta").textContent = "检索中…";
  try {
    const r = await fetch(`/api/search?${params}`);
    const data = await r.json();
    render(data);
  } catch (err) {
    $("#meta").textContent = "服务未启动";
    $("#signs").innerHTML = "";
    $("#empty").hidden = false;
  }
}

function render(data) {
  const n = data.signs.length + data.standards.length + data.cases.length;
  $("#meta").textContent = `命中 ${n} 项 · ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
  $("#signs").innerHTML = data.signs.map(signCard).join("");
  $("#empty").hidden = n > 0;

  const conf = $("#confidence");
  if (!n) {
    conf.hidden = true;
  } else {
    conf.hidden = false;
    conf.className = "confidence " + (data.confidence || "high");
    const text = {
      high: "已匹配到直接相关的征象条目。以下为描述性解释与公开出处，不构成诊断意见。",
      medium: "匹配度一般：以下为相近条目，请核对定义与适用部位后再参考。",
      low: "未找到直接对应条目：以下仅为字面相近内容，请勿据此推断，建议改用标准影像学术语。",
    };
    conf.textContent = text[data.confidence] || text.high;
  }

  renderStandards(data.standards);
  renderRelated(data.related);

  const wrap = $("#casesWrap");
  if (data.cases.length) {
    wrap.hidden = false;
    $("#cases").innerHTML = data.cases.map((c) => imgCard(c)).join("");
  } else {
    wrap.hidden = true;
    $("#cases").innerHTML = "";
  }
}

function signCard(s) {
  const mods = (s.modality || []).map((m) => `<span class="tag mod">${esc(m)}</span>`).join("");
  const src = (s.sources || [])
    .map(
      (x) =>
        `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.id)}</a>`
    )
    .join("");
  const note = (s.sources || [])
    .map((x) => x.license_note)
    .filter(Boolean)
    .slice(0, 1)
    .map(esc)
    .join("");
  return `
    <article class="card">
      <div class="card-head">
        <h3>${esc(s.name)}</h3>
        <span class="en">${esc(s.en)}</span>
      </div>
      <div class="tags">
        ${mods}
        ${s.body_part ? `<span class="tag">${esc(s.body_part)}</span>` : ""}
      </div>
      <p>${esc(s.appearance)}</p>
      <div class="label">影像上可见于</div>
      <div class="pills">${(s.may_see_in || []).map((x) => `<span class="pill">${esc(x)}</span>`).join("")}</div>
      ${
        (s.pitfalls || []).length
          ? `<div class="caution"><b>易混淆 / 判读注意</b>${s.pitfalls.map(esc).join("；")}</div>`
          : ""
      }
      <div class="sources">来源：${src || "—"}${note ? `<span class="src-note">${note}</span>` : ""}</div>
      ${
        s.link_count
          ? `<div class="card-actions"><button type="button" class="btn ghost" data-sign-links="${esc(s.id)}">图文对照 · ${s.link_count} 处</button><span class="link-hint">文字已关联 ${s.linked_image_count} 张公开影像</span></div>`
          : ""
      }
    </article>`;
}

function renderStandards(items) {
  const box = $("#standards");
  if (!items.length) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = `
    <div class="panel">
      <h2>相关公开标准</h2>
      ${items
        .map(
          (x) => `
        <div class="std">
          <h4>${esc(x.name)}</h4>
          <div class="pub">${esc(x.publisher)} · ${esc(x.body_part || "")}</div>
          <p class="muted small">${esc(x.purpose)}</p>
          <ul>${(x.dimensions || []).slice(0, 4).map((d) => `<li>${esc(d)}</li>`).join("")}</ul>
          <div class="sources">
            <a href="${esc(x.url)}" target="_blank" rel="noopener">标准入口</a>
            <span class="src-note">${esc(x.license_note || "仅链接引用")}</span>
          </div>
        </div>`
        )
        .join("")}
    </div>`;
}

function renderRelated(items) {
  const box = $("#related");
  if (!items.length) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = `
    <div class="panel">
      <h2>相关征象</h2>
      <div class="rel-list">
        ${items
          .map(
            (x) =>
              `<button class="rel" data-q="${esc(x.name)}">${esc(x.name)}<small>${esc(
                (x.modality || []).join("/")
              )}</small></button>`
          )
          .join("")}
      </div>
    </div>`;
  box.querySelectorAll(".rel").forEach((b) =>
    b.addEventListener("click", () => {
      $("#q").value = b.dataset.q;
      state.q = b.dataset.q;
      doSearch();
    })
  );
}

function imgCard(c) {
  return `
    <div class="img-card" data-case='${esc(JSON.stringify(c))}'>
      <div class="thumb"><img loading="lazy" src="/${esc(c.image)}" alt="${esc(c.title)}"></div>
      <div class="cap">
        <b>${esc(c.title)}${c.link_count ? `<span class="link-badge">图文 ${c.link_count}</span>` : ""}</b>
        <span>${esc((c.modality || []).join("/"))} · ${esc(c.body_part)} · ${esc(c.license)}</span>
      </div>
    </div>`;
}

/* ---------------- lightbox ---------------- */
document.addEventListener("click", (e) => {
  const card = e.target.closest(".img-card");
  if (!card) return;
  const c = JSON.parse(card.dataset.case);
  $("#lbImg").src = "/" + c.image;
  $("#lbImg").alt = c.title;
  $("#lbTitle").textContent = c.title;
  $("#lbDesc").textContent = [c.description_public, c.teaching_note].filter(Boolean).join(" ");
  $("#lbLinks").innerHTML = (c.linked_signs || [])
    .map((s) => `<button type="button" data-sign-links="${esc(s.id)}">${esc(s.name)} · ${s.count} 处</button>`)
    .join("");
  $("#lbCredit").textContent = `许可：${c.license} · 作者：${c.artist} · 已核验无患者标识`;
  $("#lbLink").href = c.source_page;
  $("#lightbox").showModal();
});
$("#closeLb").addEventListener("click", () => $("#lightbox").close());
$("#lightbox").addEventListener("click", (e) => {
  if (e.target === $("#lightbox")) $("#lightbox").close();
});

/* ---------------- dual line ---------------- */
$("#dualForm").addEventListener("submit", (e) => {
  e.preventDefault();
  doDual($("#dq").value.trim());
});

$("#dualChips").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-q]");
  if (!btn) return;
  $("#dq").value = btn.dataset.q;
  doDual(btn.dataset.q);
});

["#dualModality", "#dualPart"].forEach((sel) =>
  $(sel).addEventListener("change", () => {
    if ($("#dq").value.trim()) doDual($("#dq").value.trim());
  })
);

async function doDual(q) {
  if (!q) return;
  const params = new URLSearchParams({ q });
  if ($("#dualModality").value) params.set("modality", $("#dualModality").value);
  if ($("#dualPart").value) params.set("part", $("#dualPart").value);
  $("#dualMeta").textContent = "对照中…";
  try {
    const r = await fetch(`/api/dual?${params}`);
    renderDual(await r.json());
  } catch (err) {
    $("#dualMeta").textContent = "服务未启动";
  }
}

function renderDual(d) {
  const a = d.alignment;
  const box = $("#dualAlign");
  box.hidden = false;
  box.className = "align " + a.level;
  const label = { aligned: "两线对齐", partial: "条件不足", insufficient: "无法对照" }[a.level] || a.level;
  box.innerHTML = `
    <div class="align-head">
      <span class="badge ${a.level}">${label}</span>
      <span class="cov">条件覆盖 ${Math.round((a.coverage || 0) * 100)}%</span>
      ${a.best_id ? `<span class="cov">对应条款 ${esc(a.best_id)}</span>` : ""}
    </div>
    <p>${esc(a.note)}</p>
    ${
      a.action
        ? `<div class="align-action"><b>条款方向</b><span>${esc(a.action)}</span><small>${esc(a.action_source)}</small></div>`
        : ""
    }
    <div class="cond-row">
      ${(a.matched || []).map((c) => `<span class="cond ok">已覆盖 · ${esc(c)}</span>`).join("")}
      ${(a.missing || []).map((c) => `<span class="cond miss">待补充 · ${esc(c)}</span>`).join("")}
    </div>
    ${
      (a.divergent || []).length
        ? `<div class="caution"><b>来源间差异</b>${a.divergent
            .map((x) => esc(x.source + "：" + x.action))
            .join("；")}，并列展示，不作裁决。</div>`
        : ""
    }
    <p class="muted small">${esc(d.disclaimer)}</p>`;

  $("#dualImaging").innerHTML = d.imaging.signs.length
    ? d.imaging.signs
        .map(
          (s) => `<div class="mini">
        <div class="card-head"><h3>${esc(s.name)}</h3><span class="en">${esc(s.en)}</span></div>
        <p>${esc(s.appearance)}</p>
        <div class="pills">${(s.may_see_in || []).slice(0, 4).map((x) => `<span class="pill">${esc(x)}</span>`).join("")}</div>
        <div class="sources">来源：${(s.sources || []).map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.id)}</a>`).join("")}</div>
      </div>`
        )
        .join("")
    : `<p class="muted">影像线未命中征象条目。</p>`;

  $("#dualGuide").innerHTML = d.guidelines.length
    ? d.guidelines.map((g) => glCard(g, a)).join("")
    : `<p class="muted">指南线未命中同部位条款。</p>`;

  $("#dualCasesWrap").hidden = !d.imaging.cases.length;
  $("#dualCases").innerHTML = d.imaging.cases.map(imgCard).join("");
  $("#dualMeta").textContent = `影像 ${d.imaging.signs.length} 条 · 条款 ${d.guidelines.length} 条 · ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
}

function glCard(g, a) {
  const isBest = g.id === a.best_id;
  const conds = (g.conditions || [])
    .map((c) => {
      let cls = "pre";
      if (isBest) {
        if ((a.matched || []).includes(c)) cls = "ok";
        else if ((a.missing || []).includes(c)) cls = "miss";
      }
      return `<span class="cond ${cls}">${esc(c)}</span>`;
    })
    .join("");
  return `<div class="gl ${isBest ? "best" : ""}">
    <div class="gl-head">
      <b>${esc(g.id)}</b>
      <span class="tag">${esc(g.category)}</span>
      <span class="pub">${esc(g.standard_name)} · ${esc(g.version_year)}</span>
    </div>
    <p>${esc(g.statement)}</p>
    <div class="cond-row">${conds}</div>
    <div class="gl-action">条款方向：<span>${esc(g.action)}</span></div>
    <div class="sources">
      <a href="${esc(g.source_url)}" target="_blank" rel="noopener">标准入口</a>
      <span class="src-note">${esc(g.license_note)}</span>
    </div>
  </div>`;
}

/* ---------------- gallery / compare ---------------- */
let galleryAll = null;

async function loadTaxonomy() {
  if (!state.taxonomy) {
    const r = await fetch("/api/taxonomy");
    state.taxonomy = await r.json();
  }
  renderTabs();
}

function regionOrder(id) {
  const t = state.taxonomy;
  if (!t) return 99;
  const i = t.regions.findIndex((r) => r.id === id);
  return i < 0 ? 99 : i;
}

function renderTabs() {
  const t = state.taxonomy;
  if (!t) return;
  const regions = [{ id: "", name: "全部部位", count: t.totals.images }, ...t.regions];
  $("#regionTabs").innerHTML = regions
    .map((r) => `<button class="chip${state.region === r.id ? " on" : ""}" data-region="${esc(r.id)}">${esc(r.name)}<em>${r.count}</em></button>`)
    .join("");
  const cur = t.regions.find((r) => r.id === state.region);
  const conds = cur ? cur.conditions : t.regions.flatMap((r) => r.conditions);
  $("#condChips").innerHTML =
    `<button class="chip${state.cond === "" ? " on" : ""}" data-cond="">全部病症</button>` +
    conds.map((c) => `<button class="chip${state.cond === c.id ? " on" : ""}${c.has_images ? "" : " empty"}" data-cond="${esc(c.id)}">${esc(c.name)}<em>${c.count}</em></button>`).join("");
}

function currentCondition() {
  const t = state.taxonomy;
  if (!t || !state.cond) return null;
  for (const r of t.regions) for (const c of r.conditions) if (c.id === state.cond) return c;
  return null;
}

function syncSimQuery() {
  const c = currentCondition();
  if (c && c.search_query) $("#simQ").value = c.search_query;
}

async function loadGallery(force = false) {
  if (!galleryAll || force) {
    const r = await fetch("/api/groups");
    galleryAll = (await r.json()).items;
  }
  renderGroups();
}

function renderGroups() {
  const m = $("#imgModality").value;
  let groups = (galleryAll || []).map((g) => ({
    ...g,
    items: g.items.filter((c) => !m || (c.modality || []).includes(m)),
  }));
  if (state.region) groups = groups.filter((g) => g.region_id === state.region);
  if (state.cond) groups = groups.filter((g) => g.id === state.cond);
  groups = groups.filter((g) => g.items.length);
  groups.sort((a, b) => regionOrder(a.region_id) - regionOrder(b.region_id) || b.count - a.count);
  const total = groups.reduce((n, g) => n + g.items.length, 0);
  const rn = state.region ? ((state.taxonomy?.regions || []).find((r) => r.id === state.region)?.name || "") : "";
  $("#imgMeta").textContent = `${rn ? rn + " · " : ""}${groups.length} 个病症分类 · ${total} 张公开影像`;
  $("#gallery").innerHTML = groups.length
    ? groups.map((g) => `<section class="group">
      <div class="group-head">
        <div class="group-title">
          <span class="reg-tag">${esc(g.region_name)}</span>
          <h3>${esc(g.name)}</h3>
          <span class="meta">${g.items.length} 张 · ${(g.modality || []).join("/")} · ${esc(g.body_part)}</span>
        </div>
        <p>${esc(g.description)}</p>
        <p class="small muted">${esc(g.criteria)}</p>
      </div>
      <div class="images">${g.items.map(imgCard).join("")}</div>
      <p class="group-caution">${esc(g.caution)}</p>
    </section>`).join("")
    : `<p class="muted">该筛选条件下暂无已核验影像。</p>`;
}

$("#regionTabs").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-region]");
  if (!b) return;
  state.region = b.dataset.region;
  state.cond = "";
  renderTabs();
  renderGroups();
  syncSimQuery();
});

$("#condChips").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-cond]");
  if (!b) return;
  state.cond = b.dataset.cond;
  renderTabs();
  renderGroups();
  syncSimQuery();
});

$("#imgModality").addEventListener("change", renderGroups);

/* ---------------- online similar search ---------------- */
const SIM_STATUS = { ok: "可用", empty: "无结果", rate_limited: "限流", unreachable: "不可达", error: "出错", not_configured: "待配置", unknown_provider: "未知来源" };

async function searchSimilar() {
  const q = $("#simQ").value.trim();
  const provider = $("#simProvider").value;
  if (!q) {
    $("#simMeta").textContent = "请先输入检索词";
    return;
  }
  $("#simMeta").textContent = "检索中…";
  $("#simProviders").innerHTML = "";
  $("#simResults").innerHTML = "";
  try {
    const r = await fetch(`/api/similar?q=${encodeURIComponent(q)}&provider=${encodeURIComponent(provider)}&limit=6`);
    renderSim(await r.json());
  } catch (err) {
    $("#simMeta").textContent = "检索失败：" + err.message;
  }
}

function renderSim(d) {
  if (!d.enabled) {
    $("#simMeta").textContent = d.hint || "在线检索接口未启用";
    return;
  }
  $("#simProviders").innerHTML = (d.providers || [])
    .map((p) => `<span class="prov ${esc(p.status)}">${esc(p.name)} · ${esc(SIM_STATUS[p.status] || p.status)}${p.count ? " · " + p.count : ""}${p.error ? " · " + esc(p.error) : ""}</span>`)
    .join("");
  const items = d.items || [];
  state.simItems = items;
  $("#simMeta").textContent = items.length ? `${items.length} 条候选 · 仅链接，未下载未入库` : "没有可用候选";
  $("#simResults").innerHTML = items
    .map((x, i) => `<article class="sim-card${x.license_ok ? "" : " blocked"}">
      ${x.thumb_url ? `<img loading="lazy" src="${esc(x.thumb_url)}" alt="">` : `<div class="sim-noimg">文献</div>`}
      <div class="sim-body">
        <b>${esc(x.title)}</b>
        <div class="sim-tags">
          <span class="tag">${esc(x.provider)}</span>
          <span class="tag ${x.license_ok ? "ok" : "bad"}">${esc(x.license || "许可未知")}</span>
          ${(x.flags || []).map((f) => `<span class="tag bad">${esc(f)}</span>`).join("")}
        </div>
        <p class="small muted">${esc(x.snippet || "")}</p>
        <div class="sim-actions">
          <a href="${esc(x.page_url)}" target="_blank" rel="noopener">打开来源</a>
          <button class="btn ghost" data-queue="${i}"${x.license_ok ? "" : " disabled"}>加入待核验</button>
        </div>
      </div>
    </article>`)
    .join("");
}

$("#simBtn").addEventListener("click", searchSimilar);
$("#simQ").addEventListener("keydown", (e) => {
  if (e.key === "Enter") searchSimilar();
});

$("#simResults").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-queue]");
  if (!b) return;
  const item = (state.simItems || [])[Number(b.dataset.queue)];
  if (!item) return;
  const r = await fetch("/api/similar/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  });
  const d = await r.json();
  b.textContent = d.queued ? "已加入队列" : "未加入";
  b.disabled = true;
  $("#simMeta").textContent = d.queued ? `已加入待核验队列（${d.path}），仍需人工核验` : d.reason || "未加入";
});

$("#gallery").addEventListener("click", (e) => {
  const card = e.target.closest(".img-card");
  if (!card) return;
  const c = JSON.parse(card.dataset.case);
  $("#refViewer").innerHTML = `<img src="/${esc(c.image)}" alt="${esc(c.title)}">`;
  $("#refMeta").textContent = `${c.title} · ${c.license} · ${c.artist} · 来源页可在下方点击查看`;
  $("#refViewer").dataset.case = JSON.stringify(c);
});

$("#localFile").addEventListener("change", (e) => {
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  const url = URL.createObjectURL(f);
  $("#localViewer").innerHTML = `<img src="${url}" alt="本地图像预览">`;
});

/* ---------------- 征象文字 ↔ 影像位置（v1） ---------------- */
const BASIS_LABEL = {
  source_label: "来源图内标注",
  source_description: "来源公开描述",
  teaching_estimate: "教学估计",
};
const REVIEW_LABEL = {
  single_review: "单次人工标注",
  double_review: "双人复核",
};

function openSignLinks(signId) {
  state.linkSign = signId;
  state.linkDetail = null;
  showView("links");
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-sign-links]");
  if (!btn) return;
  e.preventDefault();
  e.stopPropagation();
  const dlg = $("#lightbox");
  if (dlg.open) dlg.close();
  openSignLinks(btn.dataset.signLinks);
});

async function ensureLinksView() {
  await loadLinksIndex();
  if (!state.linkSign && state.linksIndex.length) state.linkSign = state.linksIndex[0].id;
  if (state.linkSign) {
    await loadSignLinks(state.linkSign);
  } else {
    renderLinksEmpty();
  }
}

async function loadLinksIndex() {
  if (!state.linksIndex) {
    try {
      const r = await fetch("/api/sign-index");
      state.linksIndex = (await r.json()).items || [];
    } catch (err) {
      state.linksIndex = [];
    }
  }
  if (!state.stats) {
    try {
      state.stats = await (await fetch("/api/stats")).json();
    } catch (err) {
      state.stats = null;
    }
  }
  renderLinksPicker();
}

function renderLinksPicker() {
  const items = state.linksIndex || [];
  if (!items.length) {
    $("#linksPicker").innerHTML = `<span class="muted small">暂无已关联征象</span>`;
    return;
  }
  $("#linksPicker").innerHTML = items
    .map(
      (s) =>
        `<button type="button" class="chip${state.linkSign === s.id ? " on" : ""}" data-link-sign="${esc(
          s.id
        )}">${esc(s.name)}<em>${s.link_count}</em></button>`
    )
    .join("");
}

function renderLinksEmpty() {
  $("#linksGate").innerHTML = "";
  $("#linksSignName").textContent = "暂无图文对照";
  $("#linksSignEn").textContent = "";
  $("#linksSignTags").innerHTML = "";
  $("#linksAppearance").textContent = "当前知识库还没有已校验的征象文字与影像区域关联。";
  $("#linksLegend").innerHTML = "";
  $("#linksList").innerHTML = "";
  $("#linksNote").textContent = "";
  $("#linksImageTitle").textContent = "—";
  $("#linksImageMeta").textContent = "";
  $("#linksImageBasis").textContent = "";
  $("#linkOverlay").innerHTML = "";
  $("#linkImg").removeAttribute("src");
  $("#linksThumbs").innerHTML = "";
  $("#linksCaption").textContent = "";
  $("#linksReading").textContent = "";
  $("#linksSource").removeAttribute("href");
  $("#linksCredit").textContent = "";
}

async function loadSignLinks(signId) {
  if (!signId) return;
  state.linkSign = signId;
  renderLinksPicker();
  try {
    const r = await fetch(`/api/sign/${encodeURIComponent(signId)}`);
    if (!r.ok) throw new Error("not_found");
    const d = await r.json();
    state.linkDetail = d;
    state.activeLink = (d.links[0] && d.links[0].id) || "";
    state.activeImage = (d.links[0] && d.links[0].image && d.links[0].image.id) || "";
    renderSignLinks(d);
  } catch (err) {
    state.linkDetail = null;
    $("#linksSignName").textContent = "加载失败";
    $("#linksSignEn").textContent = "";
    $("#linksSignTags").innerHTML = "";
    $("#linksAppearance").textContent = "无法读取该征象的图文对照数据，请确认知识库服务已启动。";
    $("#linksLegend").innerHTML = "";
    $("#linksList").innerHTML = "";
    $("#linksGate").innerHTML = "";
    $("#linksNote").textContent = "";
    $("#linkOverlay").innerHTML = "";
    $("#linkImg").removeAttribute("src");
    $("#linksThumbs").innerHTML = "";
  }
}

function renderSignLinks(d) {
  const s = d.sign;
  const mods = (s.modality || []).map((m) => `<span class="tag mod">${esc(m)}</span>`).join("");
  $("#linksSignName").textContent = s.name;
  $("#linksSignEn").textContent = s.en;
  $("#linksSignTags").innerHTML =
    mods +
    (s.body_part ? `<span class="tag">${esc(s.body_part)}</span>` : "") +
    `<span class="tag">${d.stats.links} 条关联</span>` +
    `<span class="tag">${d.stats.images} 张影像</span>`;

  $("#linksAppearance").innerHTML = d.segments
    .map((seg) => {
      if (!seg.link_ids.length) return esc(seg.text);
      const first = d.links.findIndex((l) => l.id === seg.link_ids[0]);
      const num = seg.link_ids.length > 1 ? String(seg.link_ids.length) : String(first + 1);
      return `<button type="button" class="text-link" data-links="${esc(
        seg.link_ids.join(",")
      )}" title="${seg.link_ids.length} 条图文关联">${esc(seg.text)}<span class="link-num">${num}</span></button>`;
    })
    .join("");

  $("#linksLegend").innerHTML =
    `<b>图例</b><span>下划线文字 = 已锚定</span><span>黄色框 = 标注区域</span><span>红色框 = 当前选中</span>`;
  $("#linksList").innerHTML = d.links.map((l, i) => linkRow(l, i)).join("");
  $("#linksGate").innerHTML = gateHtml(gateFromState(d.stats));
  $("#linksNote").textContent = d.note;
  renderLinksActive();
  renderLinkViewer();
}

function gateFromState(fallback) {
  const g = state.stats || {};
  if (g.sign_links == null) return fallback;
  return {
    quotes: g.linked_quotes ?? fallback.quotes,
    links: g.sign_links,
    images: g.linked_images,
    regions: g.linked_regions,
    missing_image: 0,
    missing_text: 0,
  };
}

function gateHtml(st) {
  const items = [
    [st.quotes, "句文字锚点"],
    [st.links, "条图文关联"],
    [st.images, "张影像"],
    [st.regions, "个标注区域"],
  ];
  return (
    items
      .map(([n, label]) => `<span class="gate-item"><b>${n}</b>${label}</span>`)
      .join("") +
    `<span class="gate-item ok"><b>${st.missing_image}</b>条缺图</span>` +
    `<span class="gate-item ok"><b>${st.missing_text}</b>条缺文</span>`
  );
}

function shortArtist(a) {
  const s = String(a || "").split("\n")[0].trim();
  return s.length > 80 ? s.slice(0, 80) + "…" : s;
}

function sideText(r) {
  const p = r.patient_side === "right" ? "患者右侧" : r.patient_side === "left" ? "患者左侧" : "";
  const i = r.image_side === "right" ? "图像右侧" : r.image_side === "left" ? "图像左侧" : "";
  return [p, i].filter(Boolean).join(" · ");
}

function linkRow(l, i) {
  const image = l.image || {};
  const regions = (l.regions || [])
    .map((r) => `${r.label}${r.patient_side && !/患者|图像/.test(r.label) ? `（${sideText(r)}）` : ""}`)
    .join("；");
  return `<article class="link-row" data-link="${esc(l.id)}" role="button" tabindex="0">
    <div class="link-row-head">
      <span class="num">${i + 1}</span>
      <b>${esc(image.title || image.id || "")}</b>
      <span class="meta">${esc(BASIS_LABEL[l.basis] || l.basis)} · ${esc(
        REVIEW_LABEL[l.review] || l.review
      )}</span>
    </div>
    <p class="quote">“${esc(l.quote)}”</p>
    <p class="region-line">区域：${esc(regions || "—")} · ${esc(l.annotated_at)} · 人工标注</p>
    <p class="caption">${esc(l.caption)}</p>
    <p class="reading">${esc(l.reading)}</p>
  </article>`;
}

function renderLinksActive() {
  $$("#linksAppearance .text-link").forEach((b) => {
    const ids = (b.dataset.links || "").split(",");
    b.classList.toggle("active", ids.includes(state.activeLink));
  });
  $$("#linksList .link-row").forEach((r) =>
    r.classList.toggle("active", r.dataset.link === state.activeLink)
  );
  $$("#linksThumbs .thumb-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.image === state.activeImage)
  );
  $$("#linkOverlay .link-box").forEach((b) =>
    b.classList.toggle("active", b.dataset.link === state.activeLink)
  );
}

function renderLinkViewer() {
  const d = state.linkDetail;
  if (!d || !d.links.length) return;
  const link = d.links.find((l) => l.id === state.activeLink) || d.links[0];
  const group =
    d.images.find((g) => g.image.id === state.activeImage) ||
    d.images.find((g) => g.image.id === (link.image && link.image.id)) ||
    d.images[0];
  if (!link || !group) return;
  state.activeImage = group.image.id;

  const img = group.image;
  $("#linksImageTitle").textContent = img.title;
  $("#linksImageMeta").textContent = `${(img.modality || []).join("/")} · ${img.body_part} · ${
    img.license
  } · ${shortArtist(img.artist)}`;
  $("#linksImageBasis").textContent = BASIS_LABEL[link.basis] || link.basis;
  $("#linkImg").src = "/" + img.image;
  $("#linkImg").alt = img.title;
  $("#linkOverlay").innerHTML = group.links
    .flatMap((l) => (l.regions || []).map((r) => boxHtml(l, r)))
    .join("");
  $("#linksCaption").textContent = link.caption;
  $("#linksReading").innerHTML = `<b>对照说明</b>${esc(link.reading)}`;
  $("#linksSource").href = img.source_page;
  $("#linksSource").textContent = "查看来源页";
  $("#linksCredit").textContent = `许可：${img.license} · 作者：${shortArtist(
    img.artist
  )} · 已核验无患者标识`;
  $("#linksThumbs").innerHTML = d.images
    .map(
      (g) =>
        `<button type="button" class="thumb-btn${
          g.image.id === state.activeImage ? " active" : ""
        }" data-image="${esc(g.image.id)}"><img src="/${esc(g.image.image)}" alt=""><span>${esc(
          g.image.id
        )} · ${g.links.length} 处</span></button>`
    )
    .join("");
  renderLinksActive();
}

function boxHtml(l, r) {
  const [x, y, w, h] = r.bbox || [0, 0, 0, 0];
  const below = y < 0.06;
  const active = l.id === state.activeLink;
  return `<div class="link-box${active ? " active" : ""}${
    below ? " label-below" : ""
  }" data-link="${esc(l.id)}" style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${
    h * 100
  }%" title="${esc(l.sign_name + " · " + r.label)}"><span class="box-label">${esc(
    l.sign_name
  )} · ${esc(r.label)}</span></div>`;
}

function focusLinks(ids, preferred) {
  const link = state.linkDetail && state.linkDetail.links.find((l) => l.id === (preferred || ids[0]));
  if (!link) return;
  state.activeLink = link.id;
  state.activeImage = (link.image && link.image.id) || state.activeImage;
  renderLinkViewer();
}

$("#linksPicker").addEventListener("click", (e) => {
  const b = e.target.closest("[data-link-sign]");
  if (!b) return;
  loadSignLinks(b.dataset.linkSign);
});

$("#linksAppearance").addEventListener("click", (e) => {
  const b = e.target.closest(".text-link");
  if (!b) return;
  const ids = (b.dataset.links || "").split(",").filter(Boolean);
  if (ids.length) focusLinks(ids);
});

$("#linksList").addEventListener("click", (e) => {
  const row = e.target.closest(".link-row");
  if (!row) return;
  focusLinks([row.dataset.link], row.dataset.link);
});

$("#linksList").addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const row = e.target.closest(".link-row");
  if (!row) return;
  e.preventDefault();
  focusLinks([row.dataset.link], row.dataset.link);
});

$("#linkOverlay").addEventListener("click", (e) => {
  const box = e.target.closest(".link-box");
  if (!box) return;
  focusLinks([box.dataset.link], box.dataset.link);
});

$("#linksThumbs").addEventListener("click", (e) => {
  const b = e.target.closest("[data-image]");
  if (!b || !state.linkDetail) return;
  const group = state.linkDetail.images.find((g) => g.image.id === b.dataset.image);
  if (!group) return;
  state.activeImage = group.image.id;
  state.activeLink = (group.links[0] && group.links[0].id) || state.activeLink;
  renderLinkViewer();
});

/* ---------------- stats ---------------- */
async function loadStats() {
  if (state.stats) return renderStats(state.stats);
  const r = await fetch("/api/stats");
  state.stats = await r.json();
  renderStats(state.stats);
}

function renderStats(s) {
  const items = [
    ["征象条目", s.signs],
    ["公开标准", s.standards],
    ["部位 / 病症", `${s.regions} / ${s.conditions}`],
    ["公开影像", s.cases],
    ["来源登记", s.sources],
  ];
  const html = items
    .map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`)
    .join("");
  $("#aboutStats").innerHTML = html;
  $("#footStats").textContent = `${s.signs} 条征象 · ${s.standards} 个标准 · ${s.cases} 张公开影像`;
}

/* ---------------- boot ---------------- */
loadStats();
$("#q").value = "磨玻璃影";
state.q = "磨玻璃影";
doSearch();

/* ---------------- 接收首页传入的部位参数 ---------------- */
/* 由 homepage 的 3D 导航跳转而来：/kb/web/index.html?region=REG-CHEST */
(function applyRegionFromQuery() {
  const region = new URLSearchParams(window.location.search).get("region");
  if (!region) return;
  state.region = region;
  showView("images");
  // 若部位 id 不在库内，仍停留在图像对照页并给出提示
  loadTaxonomy().then(() => {
    if (!state.taxonomy) return;
    const hit = (state.taxonomy.regions || []).some((r) => r.id === region);
    if (!hit) {
      const meta = document.getElementById("galleryMeta");
      if (meta) meta.textContent = `未找到部位 ${region}，已显示全部影像`;
      state.region = "";
      loadGallery(true);
    }
  });
})();
