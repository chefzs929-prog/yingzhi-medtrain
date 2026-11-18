/* 影像区域定位工作台 v1.1 */
(() => {
"use strict";

const SIDE_LABEL = { right: "患者右侧", left: "患者左侧", midline: "中线", unknown: "侧别未知" };
const SIDE_CLS = { right: "side-r", left: "side-l", midline: "side-m", unknown: "side-m" };
const IMG_SIDE = { right: "图像右侧", left: "图像左侧", midline: "图像中线", unknown: "—" };
const DOC_KIND = { guideline: "条款", sign: "词条", group: "影像组" };

const S = {
  meta: null, cases: [], filter: "all", q: "",
  cur: null, tab: "locate",
  locate: null, hot: null,
  zoom: 1, tx: 0, ty: 0,
  sync: false, showRegions: true,
  history: [], audit: null,
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (v) => (v * 100).toFixed(2) + "%";
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const area = (b) => Math.max(0, b[2]) * Math.max(0, b[3]);

function toast(msg, kind) {
  const t = $("#stageToast");
  t.textContent = msg;
  t.className = "stage-toast show" + (kind ? " " + kind : "");
  clearTimeout(t._h);
  t._h = setTimeout(() => { t.className = "stage-toast" + (kind ? " " + kind : ""); }, 3200);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

/* ================= 启动 ================= */
async function boot() {
  try {
    const [meta, list] = await Promise.all([api("/api/meta"), api("/api/cases")]);
    S.meta = meta;
    S.cases = list.items;
    paintGate(meta.gate);
    renderCases();
    const first = S.cases.find(c => c.has_atlas) || S.cases[0];
    if (first) await selectCase(first.id);
  } catch (e) {
    $("#caseList").innerHTML =
      '<div class="q-empty">无法连接服务<br><br>请用<br><b>python3 kb/scripts/serve_region.py</b><br>启动后访问<br><b>http://127.0.0.1:4191</b></div>';
    toast("接口不可用，请通过本地服务打开", "bad");
  }
}

function paintGate(g) {
  $("#gmDual").textContent = g.dual || 0;
  $("#gmSingle").textContent = g.single || 0;
  $("#gmBroken").textContent = g.broken || 0;
}

/* ================= 病例队列 ================= */
function renderCases() {
  const box = $("#caseList");
  box.innerHTML = "";
  const q = S.q.trim().toLowerCase();
  const items = S.cases.filter(c => {
    if (S.filter === "locatable" && !c.has_atlas) return false;
    if (S.filter === "pending" && c.has_atlas) return false;
    if (q && !(c.id + " " + c.title + " " + c.modality + " " + c.body_part).toLowerCase().includes(q)) return false;
    return true;
  });
  $("#queueCount").textContent = items.length;
  if (!items.length) {
    box.innerHTML = '<div class="q-empty">没有匹配的病例</div>';
    return;
  }
  items.forEach(c => {
    const n = el("div", "case" + (S.cur && S.cur.case.id === c.id ? " on" : ""));
    n.dataset.id = c.id;
    n.innerHTML =
      '<img class="thumb" loading="lazy" src="' + esc(c.image) + '" alt="">' +
      '<div class="ci">' +
        '<div class="cid">' + esc(c.id) + '</div>' +
        '<div class="cti">' + esc(c.title) + '</div>' +
        '<div class="cmeta2">' +
          '<span class="mini-chip">' + esc(c.modality) + '</span>' +
          '<span class="mini-chip">' + esc(c.body_part) + '</span>' +
          (c.has_atlas
            ? '<span class="mini-chip n">' + c.region_count + ' 区</span>'
            : '<span class="mini-chip">待标注</span>') +
        '</div>' +
      '</div>' +
      '<span class="dot-st ' + (c.has_atlas ? "ok" : "no") + '"></span>';
    n.addEventListener("click", () => selectCase(c.id));
    box.appendChild(n);
  });
}

/* ================= 选择病例 ================= */
async function selectCase(id) {
  if (S.cur && S.cur.case.id === id && S.locate) return;
  let d;
  try {
    d = await api("/api/cases/" + encodeURIComponent(id));
  } catch (e) {
    toast("病例加载失败：" + id, "bad");
    return;
  }
  S.cur = d;
  S.locate = null;
  S.hot = null;
  S.zoom = 1; S.tx = 0; S.ty = 0;

  const c = d.case;
  $("#caseTitle").textContent = c.title;
  $("#caseChips").innerHTML =
    '<span class="chip">' + esc(c.id) + '</span>' +
    '<span class="chip">' + esc(c.modality) + '</span>' +
    '<span class="chip">' + esc(c.body_part) + '</span>' +
    (d.atlas ? '<span class="chip g">已标注 ' + d.regions.length + ' 区</span>' : '<span class="chip a">待标注</span>');

  const ac = $("#atlasChip");
  if (d.atlas) {
    ac.textContent = d.atlas.id;
    ac.className = "atlas-chip " + d.atlas.level;
    ac.title = d.atlas.note || "";
  } else {
    ac.textContent = "未标注分区";
    ac.className = "atlas-chip none";
    ac.title = "该影像尚无人工分区标注，无法区域定位";
  }

  $("#srcLine").innerHTML = '来源：<a href="' + esc(c.source_page) + '" target="_blank" rel="noopener">' + esc((c.source_page || "").split("/").pop()) + '</a>';
  $("#licLine").textContent = "许可：" + (c.license || "—") + " · " + (c.artist || "—");

  const img = $("#img");
  img.src = c.image;
  $("#stageEmpty").classList.add("hide");
  $("#overlay").classList.toggle("disabled", !d.atlas);
  $("#modeHint").textContent = d.atlas
    ? (d.atlas.level === "local" ? "局部视野：只给图像内相对位置 · Shift+拖动平移" : "拖框定位 · Shift+拖动平移 · 滚轮缩放")
    : "该影像未标注分区，仅可浏览";

  applyTransform();
  drawRegions();
  clearOverlays();
  $("#bboxMeta").textContent = "—";

  $("#cntEvidence").textContent = d.claims.length;
  renderCases();
  renderTab();

  if (!d.atlas) toast("该影像未标注分区，无法区域定位", "warn");
  else if (d.atlas.level === "local") toast("局部视野：不推断解剖侧别", "warn");
}

/* ================= 分区绘制 ================= */
function drawRegions() {
  const ov = $("#overlay");
  ov.innerHTML = "";
  if (!S.cur || !S.cur.regions) return;
  S.cur.regions.forEach(r => {
    const n = el("div", "region");
    n.dataset.id = r.id;
    n.style.left = pct(r.coords[0]);
    n.style.top = pct(r.coords[1]);
    n.style.width = pct(r.coords[2]);
    n.style.height = pct(r.coords[3]);
    n.appendChild(el("span", "rlabel", esc(r.name)));
    ov.appendChild(n);
  });
  $("#frame").classList.toggle("regions-off", !S.showRegions);
}

function markHot(id) {
  if (S.hot === id) return;
  S.hot = id;
  $$("#overlay .region").forEach(n => n.classList.toggle("hot", n.dataset.id === id));
}
function markHit(ids) {
  const set = new Set(ids || []);
  $$("#overlay .region").forEach(n => n.classList.toggle("hit", set.has(n.dataset.id)));
}
function clearOverlays() {
  $("#overlay").querySelectorAll(".selbox,.highlight").forEach(n => n.remove());
  markHit([]);
}

function paintSel(b) {
  $("#overlay").querySelectorAll(".selbox").forEach(n => n.remove());
  const n = el("div", "selbox");
  n.style.left = pct(b[0]); n.style.top = pct(b[1]);
  n.style.width = pct(b[2]); n.style.height = pct(b[3]);
  n.appendChild(el("span", "sz", (b[2] * 100).toFixed(0) + "×" + (b[3] * 100).toFixed(0) + "%"));
  $("#overlay").appendChild(n);
}

/* ================= 变换 ================= */
function applyTransform() {
  $("#frame").style.transform = "translate(" + S.tx + "px," + S.ty + "px) scale(" + S.zoom + ")";
  const z = Math.round(S.zoom * 100) + "%";
  $("#zoomBadge").textContent = z;
  $("#zoomReset").textContent = z;
}
function zoomBy(f) {
  S.zoom = clamp(S.zoom * f, 0.5, 5);
  applyTransform();
}
function resetView() {
  S.zoom = 1; S.tx = 0; S.ty = 0;
  applyTransform();
}

/* ================= 交互 ================= */
const ov = $("#overlay");
let drag = null;

function relPos(e) {
  const r = ov.getBoundingClientRect();
  return [clamp((e.clientX - r.left) / r.width, 0, 1), clamp((e.clientY - r.top) / r.height, 0, 1)];
}

ov.addEventListener("mousedown", (e) => {
  if (!S.cur) return;
  if (e.shiftKey || e.button === 1) {
    e.preventDefault();
    drag = { mode: "pan", x: e.clientX, y: e.clientY, tx: S.tx, ty: S.ty };
    ov.classList.add("panning");
    return;
  }
  if (e.button !== 0) return;
  if (!S.cur.atlas) { toast("该影像未标注分区，无法区域定位", "warn"); return; }
  e.preventDefault();
  drag = { mode: "box", start: relPos(e), box: null, moved: false };
  clearOverlays();
});

window.addEventListener("mousemove", (e) => {
  if (!drag) {
    if (!S.cur || !S.cur.atlas) return;
    const [x, y] = relPos(e);
    const r = pointHit(x, y);
    markHot(r ? r.id : null);
    return;
  }
  if (drag.mode === "pan") {
    S.tx = drag.tx + (e.clientX - drag.x);
    S.ty = drag.ty + (e.clientY - drag.y);
    applyTransform();
    return;
  }
  const [x, y] = relPos(e);
  const x0 = drag.start[0], y0 = drag.start[1];
  const b = [Math.min(x0, x), Math.min(y0, y), Math.abs(x - x0), Math.abs(y - y0)];
  if (b[2] > 0.006 || b[3] > 0.006) drag.moved = true;
  drag.box = b;
  paintSel(b);
  $("#bboxMeta").textContent = "[" + b.map(v => v.toFixed(3)).join(", ") + "]";
});

window.addEventListener("mouseup", () => {
  if (!drag) return;
  const d = drag;
  drag = null;
  ov.classList.remove("panning");
  if (d.mode === "pan") return;
  if (!d.moved) {
    const r = pointHit(d.start[0], d.start[1]);
    if (r) selectRegionLocal(r);
    else toast("点落在已标注分区之外", "warn");
    return;
  }
  doLocate(d.box);
});

function pointHit(x, y) {
  if (!S.cur || !S.cur.regions) return null;
  const hits = S.cur.regions.filter(r => {
    const c = r.coords;
    return x >= c[0] && x <= c[0] + c[2] && y >= c[1] && y <= c[1] + c[3];
  }).sort((a, b) => area(a.coords) - area(b.coords));
  return hits[0] || null;
}

/* ================= 定位 ================= */
async function doLocate(bbox) {
  try {
    const res = await api("/api/locate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_id: S.cur.case.id, bbox }),
    });
    S.locate = res;
    if (res.status === "single" && res.primary) {
      pushHistory(res.primary.region, "box");
      markHit([res.primary.region.id]);
      paintSel(bbox);
    } else if (res.status === "cross") {
      markHit((res.candidates || []).map(c => c.region.id));
      paintSel(bbox);
    } else {
      clearOverlays();
      if (res.status !== "single") markHit([]);
    }
    renderTab();
    if (res.message) {
      const kind = ["uncovered", "too_small", "too_large", "no_atlas"].includes(res.status) ? "warn" : "";
      toast(res.message, kind);
    }
  } catch (e) {
    toast("定位请求失败", "bad");
  }
}

function regionCardLocal(r) {
  const a = S.cur.atlas || {};
  return {
    region: r, coverage: 1, purity: 1, score: 1,
    side_label: SIDE_LABEL[r.patient_side] || r.patient_side,
    atlas: {
      id: a.id, name: a.name, level: a.level, method: a.method,
      note: a.note, laterality_rule: a.laterality_rule,
      annotator: a.annotator, annotated_at: a.annotated_at,
    },
    signs: r.signs || [],
    claims: (S.cur.claims || []).filter(c => c.region_id === r.id),
  };
}

function selectRegionLocal(r) {
  S.locate = { status: "point", primary: regionCardLocal(r), mode: "point", bbox: r.coords.slice() };
  paintSel(r.coords);
  markHit([r.id]);
  pushHistory(r, "point");
  renderTab();
}

function pushHistory(region, mode) {
  S.history.unshift({ id: region.id, name: region.name, mode, t: new Date() });
  S.history = S.history.slice(0, 6);
}

/* ================= 右栏渲染 ================= */
function renderTab() {
  $$("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === S.tab));
  const body = $("#tabBody");
  body.innerHTML = "";
  if (S.tab === "locate") renderLocate(body);
  else if (S.tab === "evidence") renderEvidence(body);
  else renderAudit(body);
}

/* ---------- 定位 ---------- */
function renderLocate(body) {
  if (!S.cur) { body.appendChild(el("div", "empty", "<b>未选择病例</b>从左侧队列选择一例开始")); return; }
  if (!S.cur.atlas) {
    body.appendChild(el("div", "empty", "<b>该影像未标注分区</b>未标注即不推断。可浏览影像与来源，或选择带绿点的可定位病例。"));
    return;
  }
  if (!S.locate) {
    body.appendChild(el("div", "empty", "<b>等待框选</b>在影像上拖出一个矩形，或单击图上任一点；<br>也可在下方直接点选分区。"));
    body.appendChild(regionPicker());
    body.appendChild(historyBlk());
    return;
  }

  const st = S.locate.status;

  if (st === "uncovered" || st === "too_small" || st === "too_large" || st === "no_atlas") {
    const w = el("div", "blk");
    w.appendChild(el("div", "warnline red", '<div class="wl-h">未产生定位</div>' + esc(S.locate.message || "")));
    body.appendChild(w);
    body.appendChild(regionPicker());
    body.appendChild(historyBlk());
    return;
  }

  if (st === "cross") {
    const w = el("div", "blk");
    w.appendChild(el("div", "warnline",
      '<div class="wl-h">跨区：选区同时落在两个分区</div>' +
      esc(S.locate.message || "") + "<br>分差 " + ((S.locate.gap || 0) * 100).toFixed(1) + " 分，低于阈值 15。"));
    (S.locate.candidates || []).forEach(c => {
      const row = el("div", "cand");
      row.innerHTML = '<div class="cn"><b>' + esc(c.region.name) + '</b>' +
        '<div class="cp">框内 ' + (c.coverage * 100).toFixed(0) + '% · 该区 ' + (c.purity * 100).toFixed(0) + '%</div></div>';
      const b = el("button", "tag btn", "定位到此");
      b.addEventListener("click", () => selectRegionLocal(c.region));
      row.appendChild(b);
      w.appendChild(row);
    });
    body.appendChild(w);
    body.appendChild(regionPicker());
    return;
  }

  // single / point
  const p = S.locate.primary;
  const r = p.region;
  const a = p.atlas || {};

  const box = el("div", "blk");
  const head = el("div", "blk-h", "定位结果<span class='spacer'></span><span style='text-transform:none;letter-spacing:0'>" +
    (S.locate.mode === "point" ? "点定位" : "框选") + "</span>");
  box.appendChild(head);

  const rows = [];
  rows.push(["解剖分区", "<b>" + esc(r.name) + '</b><span class="side-badge ' + (SIDE_CLS[r.patient_side] || "side-m") + '">' + esc(p.side_label) + "</span>"]);
  rows.push(["侧别映射", esc(IMG_SIDE[r.image_side] || "—") + " · " + esc(a.laterality_rule || "—")]);
  rows.push(["定位依据", esc((a.name || "—") + " · " + (a.method || "人工标注") + " · " + (a.annotated_at || ""))]);

  if (S.locate.mode === "point") {
    rows.push(["定位方式", "点定位（取点所在最小分区）"]);
  } else {
    rows.push(["覆盖度", "框内 <b>" + (p.coverage * 100).toFixed(0) + "%</b> 落在该区 · 该区被框住 <b>" +
      (p.purity * 100).toFixed(0) + '%</b><div class="meter"><i style="width:' + (p.coverage * 100).toFixed(1) + '%"></i></div>']);
  }
  if (S.locate.secondary) {
    rows.push(["边界提示", "与「" + esc(S.locate.secondary.region.name) + "」重叠 " +
      (S.locate.secondary.coverage * 100).toFixed(0) + "%，需精确请缩小范围"]);
  }
  rows.forEach(([k, v]) => {
    const row = el("div", "lrow");
    row.appendChild(el("span", "k", k));
    const vv = el("span", "v", v);
    row.appendChild(vv);
    box.appendChild(row);
  });

  const signRow = el("div", "lrow");
  signRow.appendChild(el("span", "k", "可对照征象"));
  const sv = el("div", "v");
  const tags = el("div", "tagrow");
  (p.signs || []).forEach(s => tags.appendChild(el("span", "tag", esc(s.name || s.id))));
  sv.appendChild(tags);
  signRow.appendChild(sv);
  box.appendChild(signRow);

  if (a.level === "local") {
    box.appendChild(el("div", "warnline", '<div class="wl-h">局部视野</div>只给图像内相对位置，不推断解剖左叶/右叶。'));
  }
  body.appendChild(box);

  const cb = el("div", "blk");
  const ch = el("div", "blk-h", "该分区结论<span class='spacer'></span>" +
    (p.claims || []).length + " 条");
  cb.appendChild(ch);
  if (!(p.claims || []).length) {
    cb.appendChild(el("div", "cnote", "该分区暂无可对照条目，库内未绑定征象或条款，不作推断。"));
  } else {
    const g = { dual: 0, single: 0, broken: 0 };
    p.claims.forEach(c => g[c.status]++);
    cb.appendChild(el("div", "cnote", "双引用 " + g.dual + " · 单引用 " + g.single + " · 拦截 " + g.broken));
  }
  body.appendChild(cb);
  body.appendChild(regionPicker());
  body.appendChild(historyBlk());
}

function regionPicker() {
  const b = el("div", "blk");
  b.appendChild(el("div", "blk-h", "直接选择分区"));
  const row = el("div", "tagrow");
  (S.cur.regions || []).forEach(r => {
    const t = el("button", "tag btn", esc(r.name));
    t.title = r.patient_side === "unknown" ? "图像内相对位置" : SIDE_LABEL[r.patient_side];
    t.addEventListener("click", () => selectRegionLocal(r));
    row.appendChild(t);
  });
  b.appendChild(row);
  return b;
}

function historyBlk() {
  const b = el("div", "blk");
  b.appendChild(el("div", "blk-h", "本次会话定位记录"));
  if (!S.history.length) {
    b.appendChild(el("div", "cnote", "尚无记录。"));
    return b;
  }
  S.history.forEach(h => {
    const row = el("div", "lrow");
    row.appendChild(el("span", "k", h.mode === "point" ? "点选" : "框选"));
    row.appendChild(el("span", "v", esc(h.name)));
    b.appendChild(row);
  });
  return b;
}

/* ---------- 证据 ---------- */
function claimCard(c, regionName) {
  const n = el("div", "claim" + (c.status === "broken" ? " blocked" : ""));
  n.appendChild(el("div", "ctext", esc(c.text)));

  const meta = el("div", "cmeta");
  meta.appendChild(el("span", "st " + c.status, { dual: "双引用", single: "单引用", broken: "已拦截" }[c.status]));

  const sp = c.spatial && c.spatial.anchor;
  if (sp) {
    const b = el("button", "cite sp", '<span>▣</span><span class="lbl">影像 ' + esc(regionName || sp.region_id) + "</span>");
    b.title = "在图上高亮空间锚点";
    b.addEventListener("click", (e) => { e.stopPropagation(); highlightClaim(c); });
    meta.appendChild(b);
  } else {
    meta.appendChild(el("span", "cite sp off", '<span>▣</span><span class="lbl">无空间锚点</span>'));
  }

  const dc = c.doc && c.doc.anchor;
  if (dc) {
    const segs = (dc.locator || "").split("·").map(x => x.trim()).filter(Boolean);
    const lbl = (segs[0] === "通用" && segs[1]) ? segs[1] : (segs[0] || "原文");
    const b = el("button", "cite dc", '<span>▤</span><span class="lbl">' +
      (DOC_KIND[dc.doc_kind] || "文献") + " " + esc(lbl) + "</span>");
    b.title = "查看原文摘录与校验";
    b.addEventListener("click", (e) => { e.stopPropagation(); openDoc(c); });
    meta.appendChild(b);
  }
  n.appendChild(meta);

  if (c.status === "single") {
    const p = (c.gate.problems || [])[0];
    n.appendChild(el("div", "cnote amber", "△ " + esc((p && p.message) || "缺少一侧锚点，已降级为单引用。")));
  }
  if (c.status === "broken") {
    const p = (c.gate.problems || []).find(x => x.code === "excerpt_mismatch") || (c.gate.problems || [])[0] || {};
    n.appendChild(el("div", "cnote red", "✕ " + esc(p.message || "引用未通过校验") +
      (p.expected ? '<br><span class="mono" style="font-size:9.5px">expected ' + esc(p.expected) + " / actual " + esc(p.actual) + "</span>" : "")));
  }
  if (c.note && c.status !== "broken") n.appendChild(el("div", "cnote", esc(c.note)));

  n.addEventListener("click", (e) => {
    if (e.target.closest("button")) return;
    highlightClaim(c);
    if (S.sync) openDoc(c);
  });
  return n;
}

function renderEvidence(body) {
  if (!S.cur) { body.appendChild(el("div", "empty", "<b>未选择病例</b>")); return; }

  const region = S.locate && S.locate.primary ? S.locate.primary.region : null;
  const all = S.cur.claims || [];
  const list = region ? all.filter(c => c.region_id === region.id) : all;
  const g = { dual: 0, single: 0, broken: 0 };
  list.forEach(c => g[c.status]++);

  const bar = el("div", "gate-bar");
  bar.innerHTML =
    '<span class="g"><i class="d dual"></i>双引用 <b>' + g.dual + '</b></span>' +
    '<span class="g"><i class="d single"></i>单引用 <b>' + g.single + '</b></span>' +
    '<span class="g"><i class="d broken"></i>已拦截 <b>' + g.broken + "</b></span>" +
    '<span class="spacer" style="flex:1"></span>' +
    '<span style="color:#5d6e80">' + (region ? esc(region.name) : "全部") + "</span>";
  body.appendChild(bar);

  if (!list.length) {
    body.appendChild(el("div", "empty", "<b>该分区暂无可对照条目</b>库内未为此分区绑定征象或条款，不作推断。"));
    return;
  }

  const wrap = el("div", "claims");
  list.forEach(c => wrap.appendChild(claimCard(c, region ? region.name : null)));
  body.appendChild(wrap);

  const foot = el("div", "blk");
  foot.appendChild(el("div", "cnote",
    "每条结论必须同时具备空间锚点（图上哪一块）与文献锚点（哪份文献哪一条）。" +
    "缺一侧降级为单引用；摘录与库内原文不一致则整条拦截。"));
  body.appendChild(foot);
}

function highlightClaim(c) {
  const sp = c.spatial && c.spatial.anchor;
  if (!sp) { toast("该条没有空间锚点，无法在图上定位", "warn"); return; }
  $("#overlay").querySelectorAll(".highlight").forEach(n => n.remove());
  const b = sp.bbox;
  const n = el("div", "highlight");
  n.style.left = pct(b[0]); n.style.top = pct(b[1]);
  n.style.width = pct(b[2]); n.style.height = pct(b[3]);
  $("#overlay").appendChild(n);
  $("#bboxMeta").textContent = "spatial " + (sp.bbox ? sp.bbox.map(v => v.toFixed(3)).join(", ") : "");
}

/* ---------- 审计 ---------- */
async function renderAudit(body) {
  if (!S.audit) {
    try { S.audit = await api("/api/audit"); }
    catch (e) { body.appendChild(el("div", "empty", "<b>审计数据加载失败</b>")); return; }
  }
  const d = S.audit;
  const sum = el("div", "audit-sum");
  sum.innerHTML =
    "共 " + d.items.length + " 条引用记录 · " +
    '<span style="color:#6fd88a">双引用 ' + d.gate.dual + "</span> · " +
    '<span style="color:#f0c674">单引用 ' + d.gate.single + "</span> · " +
    '<span style="color:#ff9b9e">拦截 ' + d.gate.broken + "</span>";
  body.appendChild(sum);

  const wrap = el("div", "audit-wrap");
  d.items.forEach(it => {
    const row = el("div", "audit-row");
    const left = el("div");
    left.appendChild(el("div", "ar-t", esc(it.text)));
    const m = el("div", "ar-m");
    m.innerHTML =
      "<span>" + esc(it.claim_id) + "</span>" +
      "<span>" + esc(it.image_id) + "</span>" +
      "<span>" + esc(it.region_id) + "</span>" +
      (it.doc_hash ? "<span>hash " + esc(it.doc_hash) + "</span>" : "");
    left.appendChild(m);
    if (it.problems && it.problems.length) {
      it.problems.forEach(p => {
        const pr = el("div", "prob" + (it.status === "single" ? " warn" : ""));
        pr.innerHTML = "<div>" + esc(p.message) + "</div>" +
          (p.expected ? '<div class="ph">expected ' + esc(p.expected) + " / actual " + esc(p.actual) + "</div>" : "");
        left.appendChild(pr);
      });
    }
    row.appendChild(left);

    const right = el("div", "ar-s");
    right.appendChild(el("span", "st " + it.status, { dual: "双引用", single: "单引用", broken: "已拦截" }[it.status]));
    const go = el("button", "tag btn", "定位");
    go.addEventListener("click", async (e) => {
      e.stopPropagation();
      await selectCase(it.image_id);
      const r = (S.cur.regions || []).find(x => x.id === it.region_id);
      if (r) { selectRegionLocal(r); S.tab = "evidence"; renderTab(); }
    });
    right.appendChild(go);
    row.appendChild(right);

    row.addEventListener("click", () => {
      const c = (S.cur && S.cur.claims || []).find(x => x.id === it.claim_id);
      if (c) openDoc(c);
    });
    wrap.appendChild(row);
  });
  body.appendChild(wrap);
}

/* ================= 文献抽屉 ================= */
function openDoc(c) {
  const dc = c.doc && c.doc.anchor;
  if (!dc) return;
  $("#dTitle").textContent = dc.doc_title;
  $("#dSub").textContent = dc.locator + " · " + dc.version + " · " + (c.doc.cite_id || "");

  const body = $("#dBody");
  body.innerHTML = "";

  const legs = el("div", "legs");
  const sp = c.spatial && c.spatial.anchor;
  legs.innerHTML =
    '<div class="leg sp"><div class="lh">空间锚点</div><div class="lv">' +
      (sp ? esc(sp.image_id + " · " + sp.region_id) : "缺失") + "</div></div>" +
    '<div class="leg"><div class="lh">文献锚点</div><div class="lv">' +
      esc(dc.doc_title + " · " + dc.version) + "</div></div>";
  body.appendChild(legs);

  const ver = el("div", "ver " + (c.status === "broken" ? "bad" : c.status === "single" ? "warn" : "ok"));
  const p0 = (c.gate.problems || [])[0];
  ver.textContent = c.status === "broken"
    ? "✕ 校验未通过 · " + ((p0 && p0.message) || "引用不完整") + "，已拦截"
    : c.status === "single"
      ? "△ 单引用 · " + ((p0 && p0.message) || "缺少空间锚点")
      : "✓ 双引用完整 · 空间锚点与文献锚点均已校验";
  body.appendChild(ver);

  const s1 = el("div", "dsec");
  s1.appendChild(el("div", "k", "原文摘录（excerpt）"));
  s1.appendChild(el("div", "excerpt" + (c.status === "broken" ? " bad" : ""), esc(dc.excerpt)));
  body.appendChild(s1);

  const s2 = el("div", "dsec");
  s2.appendChild(el("div", "k", "引用元数据"));
  const kv = el("div", "kv");
  const rows = [
    ["文献类型", DOC_KIND[dc.doc_kind] || dc.doc_kind],
    ["库内 id", dc.doc_id],
    ["版本", dc.version],
    ["定位符", dc.locator],
    ["抓取时间", dc.retrieved_at],
    ["摘录 hash", dc.excerpt_sha256],
  ];
  if (sp) {
    rows.push(["空间锚点", sp.atlas_id + " · " + sp.image_id]);
    rows.push(["标注", sp.annotator + " · " + sp.annotated_at]);
  }
  rows.forEach(([k, v]) => {
    kv.appendChild(el("div", "k", esc(k)));
    kv.appendChild(el("div", "v mono", esc(v)));
  });
  s2.appendChild(kv);
  body.appendChild(s2);

  const s3 = el("div", "dsec");
  s3.appendChild(el("div", "k", "原文入口"));
  const a = el("a", "dlink", esc(dc.url));
  a.href = dc.url; a.target = "_blank"; a.rel = "noopener";
  s3.appendChild(a);
  s3.appendChild(el("div", "cnote", "外部链接仅作来源指引；条款阈值以官方当前版本为准。"));
  body.appendChild(s3);

  $("#drawer").classList.add("open");
  $("#scrim").classList.add("on");
}
function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#scrim").classList.remove("on");
}

/* ================= 事件绑定 ================= */
$("#q").addEventListener("input", (e) => { S.q = e.target.value; renderCases(); });

$("#filters").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  S.filter = b.dataset.f;
  $$("#filters button").forEach(x => x.classList.toggle("on", x === b));
  renderCases();
});

$("#tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  S.tab = b.dataset.t;
  renderTab();
});

$("#gateMini").addEventListener("click", () => { S.tab = "audit"; renderTab(); });

$("#zoomIn").addEventListener("click", () => zoomBy(1.25));
$("#zoomOut").addEventListener("click", () => zoomBy(1 / 1.25));
$("#zoomReset").addEventListener("click", resetView);
$("#fitBtn").addEventListener("click", resetView);
$("#clearBtn").addEventListener("click", () => { clearOverlays(); S.locate = null; renderTab(); });

$("#regionToggle").addEventListener("click", () => {
  S.showRegions = !S.showRegions;
  $("#frame").classList.toggle("regions-off", !S.showRegions);
  $("#regionToggle").classList.toggle("on", S.showRegions);
});

$("#syncMode").addEventListener("change", (e) => { S.sync = e.target.checked; });
$("#dClose").addEventListener("click", closeDrawer);
$("#scrim").addEventListener("click", closeDrawer);

$("#helpBtn").addEventListener("click", () => $("#helpModal").classList.add("open"));
$("#helpClose").addEventListener("click", () => $("#helpModal").classList.remove("open"));
$("#helpModal").addEventListener("click", (e) => { if (e.target.id === "helpModal") $("#helpModal").classList.remove("open"); });

$("#stage").addEventListener("wheel", (e) => {
  if (!S.cur) return;
  e.preventDefault();
  zoomBy(e.deltaY < 0 ? 1.12 : 1 / 1.12);
}, { passive: false });

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  const k = e.key.toLowerCase();
  if (k === "escape") {
    if ($("#helpModal").classList.contains("open")) $("#helpModal").classList.remove("open");
    else if ($("#drawer").classList.contains("open")) closeDrawer();
    else { clearOverlays(); S.locate = null; renderTab(); }
    return;
  }
  if (k === "r" || k === "f") { resetView(); return; }
  if (k === "g") { $("#regionToggle").click(); return; }
  if (k === "s") { $("#syncMode").checked = !$("#syncMode").checked; S.sync = $("#syncMode").checked; return; }
  if (k === "+" || k === "=") { zoomBy(1.25); return; }
  if (k === "-") { zoomBy(1 / 1.25); return; }
  if (k === "1") { S.tab = "locate"; renderTab(); }
  if (k === "2") { S.tab = "evidence"; renderTab(); }
  if (k === "3") { S.tab = "audit"; renderTab(); }
});

$("#img").addEventListener("load", () => applyTransform());

boot();
})();
