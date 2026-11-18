/* 征象文字 ↔ 影像位置 · v1 离线演示
 * 数据与图片由 build_sign_image_demo.py 注入，页面不发起网络请求。
 */
(() => {
  const D = window.__DATA__ || { signs: [], links: {}, images: {}, gate: {} };
  const IMG = window.__IMG__ || {};
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const BASIS_LABEL = {
    source_label: "来源图内标注",
    source_description: "来源公开描述",
    teaching_estimate: "教学估计",
  };
  const REVIEW_LABEL = {
    single_review: "单次人工标注",
    double_review: "双人复核",
  };

  const state = {
    signId: (D.signs[0] && D.signs[0].id) || "",
    activeLink: "",
    activeImage: "",
  };

  const signById = {};
  D.signs.forEach((s) => (signById[s.id] = s));

  function shortArtist(a) {
    const s = String(a || "").split("\n")[0].trim();
    return s.length > 80 ? s.slice(0, 80) + "…" : s;
  }

  function sideText(r) {
    const p = r.patient_side === "right" ? "患者右侧" : r.patient_side === "left" ? "患者左侧" : "";
    const i = r.image_side === "right" ? "图像右侧" : r.image_side === "left" ? "图像左侧" : "";
    return [p, i].filter(Boolean).join(" · ");
  }

  function gateHtml(g) {
    return (
      [
        [g.quotes, "句文字锚点"],
        [g.links, "条图文关联"],
        [g.images, "张影像"],
        [g.regions, "个标注区域"],
      ]
        .map(([n, label]) => `<span class="gate-item"><b>${n}</b>${label}</span>`)
        .join("") +
      `<span class="gate-item ok"><b>0</b>条缺图</span><span class="gate-item ok"><b>0</b>条缺文</span>`
    );
  }

  function renderPicker() {
    $("#linksPicker").innerHTML = D.signs
      .map(
        (s) =>
          `<button type="button" class="chip${state.signId === s.id ? " on" : ""}" data-sign="${esc(
            s.id
          )}">${esc(s.name)}<em>${s.links.length}</em></button>`
      )
      .join("");
  }

  function selectSign(id) {
    const sign = signById[id];
    if (!sign) return;
    state.signId = id;
    const first = sign.links[0];
    state.activeLink = first || "";
    state.activeImage = (first && D.links[first] && D.links[first].image.id) || (sign.image_ids[0] || "");
    renderPicker();
    renderSign();
  }

  function renderSign() {
    const sign = signById[state.signId];
    if (!sign) return;
    const mods = (sign.modality || []).map((m) => `<span class="tag mod">${esc(m)}</span>`).join("");
    $("#linksSignName").textContent = sign.name;
    $("#linksSignEn").textContent = sign.en;
    $("#linksSignTags").innerHTML =
      mods +
      (sign.body_part ? `<span class="tag">${esc(sign.body_part)}</span>` : "") +
      `<span class="tag">${sign.links.length} 条关联</span>` +
      `<span class="tag">${sign.image_ids.length} 张影像</span>`;

    $("#linksAppearance").innerHTML = sign.segments
      .map((seg) => {
        if (!seg.link_ids.length) return esc(seg.text);
        const first = D.links[seg.link_ids[0]];
        const num = seg.link_ids.length > 1 ? String(seg.link_ids.length) : String(first.n);
        return `<button type="button" class="text-link" data-links="${esc(
          seg.link_ids.join(",")
        )}" title="${seg.link_ids.length} 条图文关联">${esc(seg.text)}<span class="link-num">${num}</span></button>`;
      })
      .join("");

    $("#linksLegend").innerHTML =
      `<b>图例</b><span>下划线文字 = 已锚定</span><span>黄色框 = 标注区域</span><span>红色框 = 当前选中</span>`;
    $("#linksList").innerHTML = sign.links.map((id) => linkRow(D.links[id])).join("");
    $("#linksGate").innerHTML = gateHtml(D.gate);
    $("#linksNote").textContent = D.note;
    renderViewer();
  }

  function linkRow(l) {
    const image = l.image || {};
    const regions = (l.regions || [])
      .map((r) => `${r.label}${r.patient_side && !/患者|图像/.test(r.label) ? `（${sideText(r)}）` : ""}`)
      .join("；");
    return `<article class="link-row" data-link="${esc(l.id)}" role="button" tabindex="0">
      <div class="link-row-head">
        <span class="num">${l.n}</span>
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

  function renderViewer() {
    const sign = signById[state.signId];
    if (!sign) return;
    const link = D.links[state.activeLink] || D.links[sign.links[0]];
    if (!link) return;
    const imageId = state.activeImage || link.image.id;
    const group = D.images[imageId];
    if (!group) return;
    const groupLinks = group.links
      .map((id) => D.links[id])
      .filter((x) => x && x.sign_id === state.signId);

    $("#linksImageTitle").textContent = group.title;
    $("#linksImageMeta").textContent = `${(group.modality || []).join("/")} · ${group.body_part} · ${
      group.license
    } · ${shortArtist(group.artist)}`;
    $("#linksImageBasis").textContent = BASIS_LABEL[link.basis] || link.basis;
    $("#linkImg").src = IMG[imageId] || "";
    $("#linkImg").alt = group.title;
    $("#linkOverlay").innerHTML = groupLinks
      .flatMap((l) => (l.regions || []).map((r) => boxHtml(l, r)))
      .join("");
    $("#linksCaption").textContent = link.caption;
    $("#linksReading").innerHTML = `<b>对照说明</b>${esc(link.reading)}`;
    $("#linksSource").href = group.source_page || "#";
    $("#linksCredit").textContent = `许可：${group.license} · 作者：${shortArtist(
      group.artist
    )} · 已核验无患者标识`;
    $("#linksThumbs").innerHTML = sign.image_ids
      .map((id) => {
        const g = D.images[id];
        const n = g.links.filter((x) => D.links[x] && D.links[x].sign_id === state.signId).length;
        return `<button type="button" class="thumb-btn${
          id === state.activeImage ? " active" : ""
        }" data-image="${esc(id)}"><img src="${esc(IMG[id] || "")}" alt=""><span>${esc(
          id
        )} · ${n} 处</span></button>`;
      })
      .join("");
    renderActive();
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

  function renderActive() {
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

  function focusLinks(ids, preferred) {
    const id = preferred || ids[0];
    const link = D.links[id];
    if (!link) return;
    state.activeLink = id;
    state.activeImage = link.image.id;
    renderViewer();
  }

  $("#linksPicker").addEventListener("click", (e) => {
    const b = e.target.closest("[data-sign]");
    if (!b) return;
    selectSign(b.dataset.sign);
  });

  $("#linksAppearance").addEventListener("click", (e) => {
    const b = e.target.closest(".text-link");
    if (!b) return;
    focusLinks((b.dataset.links || "").split(",").filter(Boolean));
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
    if (!b) return;
    const group = D.images[b.dataset.image];
    if (!group) return;
    const first = group.links.map((id) => D.links[id]).find((l) => l && l.sign_id === state.signId);
    state.activeImage = group.id;
    state.activeLink = (first && first.id) || state.activeLink;
    renderViewer();
  });

  if (state.signId) selectSign(state.signId);
})();
