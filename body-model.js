/* RadioCheck · 人体模型接口层（首页专用）
 *
 * 目标：首页用人体模型选择解剖部位，点击后进入对应知识分区。
 *
 * 当前状态（必须如实标注）：
 *   mode = "svg-fallback"  —— 内置 SVG 正面人体，5 个部位热点可点击，真实可用
 *   mode = "adapter"       —— 外部 3D 适配器已注入，由适配器渲染
 *
 * 预留 3D 接入方式：在首页加载后、BodyModel.mount() 之前挂上
 *   window.YZ_BODY_MODEL_ADAPTER = {
 *     name: "three-body",
 *     mount(el, opts) -> handle,     // 必须实现
 *   }
 * 适配器 handle 需提供：highlight(id) / reset() / resize() / dispose()
 * 只要 adapter.mount 抛错，自动回落到 SVG，并在 handle.fallbackReason 里留下原因。
 */
(function (YZ) {
  "use strict";

  const CONTRACT = [
    "mount(el, opts) -> handle",
    "handle.highlight(regionId)",
    "handle.reset()",
    "handle.resize()",
    "handle.dispose()",
  ];

  /* viewBox 0 0 250 460：人体在左侧 0–172，标签区在右侧 172–250，避免文字压图形 */
  const VB = { w: 250, h: 418 };

  const SKIN = "#e8eff2";
  const LINE = "#c3d4db";

  /* 每个部位：热区图形 + 标签锚点（右侧竖排） */
  const ART = {
    "REG-HEAD-NECK": {
      hot: '<ellipse cx="86" cy="52" rx="25" ry="30"/><rect x="79" y="80" width="14" height="16" rx="5"/>',
      label: [176, 44],
      anchor: [111, 52],
    },
    "REG-CHEST": {
      hot: '<path d="M60 96 C54 118 54 158 58 196 L114 196 C118 158 118 118 112 96 Z"/>',
      label: [176, 128],
      anchor: [118, 140],
    },
    "REG-BREAST": {
      hot: '<ellipse cx="73" cy="130" rx="14" ry="12"/><ellipse cx="101" cy="130" rx="14" ry="12"/>',
      label: [176, 176],
      anchor: [116, 130],
    },
    "REG-ABDOMEN": {
      hot: '<path d="M58 196 H114 L110 234 H62 Z"/>',
      label: [176, 212],
      anchor: [116, 214],
    },
    "REG-MSK": {
      /* 手臂热区从肩下开始，避免与胸部抢点击；腿从骨盆以下开始 */
      hot: '<path class="bm-limb" d="M46 152 C43 170 42 184 42 196"/><path class="bm-limb" d="M128 152 C131 170 132 184 132 196"/><path class="bm-limb" d="M72 240 C70 276 70 314 70 348"/><path class="bm-limb" d="M100 240 C102 276 102 314 102 348"/>',
      label: [176, 306],
      anchor: [132, 288],
    },
  };

  function adapter() {
    const a = window.YZ_BODY_MODEL_ADAPTER;
    return a && typeof a.mount === "function" ? a : null;
  }

  function status() {
    const a = adapter();
    return {
      contract: "1.0",
      mode: a ? "adapter" : "svg-fallback",
      adapterName: a ? (a.name || "unnamed") : null,
      ready: true,
      note: a
        ? "外部 3D 适配器已接入"
        : "3D 模型接口已预留，当前为 SVG 占位（可点击，非 3D 渲染）",
    };
  }

  /* ---------- 人体轮廓（装饰层，不参与交互） ---------- */
  function silhouette() {
    return `<g class="bm-body">
      <ellipse cx="86" cy="52" rx="25" ry="30"/>
      <rect x="79" y="80" width="14" height="16" rx="5"/>
      <path d="M60 96 C54 118 54 158 58 196 L114 196 C118 158 118 118 112 96 Z"/>
      <path d="M58 196 H114 L110 234 H62 Z"/>
      <path class="bm-limb" d="M58 104 C48 128 43 164 42 196"/>
      <path class="bm-limb" d="M114 104 C124 128 129 164 130 196"/>
      <path class="bm-limb" d="M72 234 C70 272 70 312 70 348"/>
      <path class="bm-limb" d="M100 234 C102 272 102 312 102 348"/>
    </g>`;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /* ---------- SVG 兜底实现 ---------- */
  function svgMount(el, opts) {
    const o = opts || {};
    const regions = o.regions || [];
    const byId = new Map(regions.map((r) => [r.id, r]));
    let active = o.active || null;
    let disposed = false;

    const hot = regions.filter((r) => ART[r.id]).map((r) => {
      const a = ART[r.id];
      const [lx, ly] = a.label;
      const [ax, ay] = a.anchor;
      return `<g class="bm-region" data-region="${r.id}">
        <g class="bm-hot">${a.hot}</g>
        <line class="bm-lead" x1="${ax}" y1="${ay}" x2="${lx - 8}" y2="${ly - 4}"/>
        <text class="bm-label" x="${lx}" y="${ly}">${esc(r.name)}</text>
        <text class="bm-count" x="${lx}" y="${ly + 12}">${r.count != null ? r.count + " 条词条" : ""}</text>
      </g>`;
    }).join("");

    el.innerHTML = `<div class="bm-wrap">
      <svg class="bm-svg" viewBox="0 0 ${VB.w} ${VB.h}" role="img" aria-label="人体部位选择">
        ${silhouette()}
        <g class="bm-hot-layer">${hot}</g>
      </svg>
      <div class="bm-tag" data-bm-tag>${esc(status().note)}</div>
    </div>`;

    const svg = el.querySelector(".bm-svg");
    const tag = el.querySelector("[data-bm-tag]");

    function paint() {
      el.querySelectorAll(".bm-region").forEach((g) => {
        g.classList.toggle("on", g.dataset.region === active);
      });
      const cur = active ? byId.get(active) : null;
      if (tag) {
        tag.textContent = cur
          ? `${cur.name} · ${cur.count != null ? cur.count + " 条词条" : "已选中"}`
          : status().note;
      }
    }

    function onClick(e) {
      const g = e.target.closest(".bm-region");
      if (!g) return;
      const id = g.dataset.region;
      active = active === id ? null : id;
      paint();
      if (typeof o.onSelect === "function") o.onSelect(active, byId.get(active) || null);
    }

    svg.addEventListener("click", onClick);
    paint();

    return {
      mode: "svg-fallback",
      el,
      mount: () => paint(),
      highlight(id) { active = id || null; paint(); },
      reset() { active = null; paint(); },
      resize() { /* SVG 自适应，无需重排 */ },
      dispose() {
        if (disposed) return;
        disposed = true;
        svg.removeEventListener("click", onClick);
        el.innerHTML = "";
      },
      status,
    };
  }

  function mount(el, opts) {
    if (!el) throw new Error("BodyModel.mount 需要一个容器元素");
    const a = adapter();
    if (a) {
      try {
        const h = a.mount(el, opts || {});
        if (h && typeof h.dispose === "function") return h;
        throw new Error("适配器未返回合法 handle");
      } catch (err) {
        const h = svgMount(el, opts);
        h.fallbackReason = String((err && err.message) || err);
        return h;
      }
    }
    return svgMount(el, opts);
  }

  YZ.BodyModel = { VERSION: "1.0", CONTRACT, ART, VB, SKIN, LINE, status, mount, mountSvg: svgMount };
})(window.YZ = window.YZ || {});
