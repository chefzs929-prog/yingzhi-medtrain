/* RadioCheck · 对比阅片
 * 数据：../data/exam/exam_cases.json
 * 交互：胶片条拖拽 / 点击分配 / 中间分隔条 / 并排与叠加擦除 / 两侧同高对齐 + 同步缩放平移
 */
(function () {
  'use strict';

  const DATA_URL = '../data/exam/exam_cases.json';
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);

  let DATA = null;
  let CASES = [];
  let BY_ID = {};
  let PAIRS = [];
  const sides = { left: null, right: null };
  /* 两侧共用一套视图：同高对齐后，同一屏幕位移就等于同一解剖位移，
   * 不会出现“左边拖 100px、右边也拖 100px 但走到的位置不同”的错位。 */
  const view = { z: 1, x: 0, y: 0 };
  const base = { left: { w: 0, h: 0 }, right: { w: 0, h: 0 } };
  let active = 'left';
  let mode = 'side';
  let align = true;
  let reveal = true;
  let split = 50;
  let panning = null;
  let dragging = null;

  function toast(msg) {
    const el = $('#yzToast');
    if (!el) return;
    el.textContent = msg;
    el.style.opacity = '1';
    el.style.transform = 'translateX(-50%) translateY(0)';
    clearTimeout(el._t);
    el._t = setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateX(-50%) translateY(8px)';
    }, 2000);
  }

  function caseOf(id) { return id ? BY_ID[id] : null; }

  function labelOf(id) {
    const c = caseOf(id);
    if (!c) return '未选择';
    return reveal ? c.topic : '病例 ' + c.id;
  }

  function diagOf(id) {
    const c = caseOf(id);
    if (!c) return '';
    return reveal ? c.diagnosis : '诊断已隐藏 · 点“显示诊断”揭晓';
  }

  const imgOf = (side) => (side === 'left' ? $('#leftImg') : $('#rightImg'));
  const canvasOf = (side) => (side === 'left'
    ? $('#paneLeft .pane-canvas') : $('#paneRight .pane-canvas'));

  function applyView() {
    const t = `translate(${view.x}px, ${view.y}px) scale(${view.z})`;
    ['left', 'right'].forEach((side) => {
      const img = imgOf(side);
      if (img) img.style.transform = t;
    });
  }

  /* 单侧的“等比铺满”尺寸：宽高都不裁切。 */
  function fitBox(side) {
    const canvas = canvasOf(side);
    const img = imgOf(side);
    if (!canvas || !img) return null;
    const cw = canvas.clientWidth;
    const ch = canvas.clientHeight;
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    if (!cw || !ch || !nw || !nh) return null;
    const k = Math.min(cw / nw, ch / nh);
    return { w: nw * k, h: nh * k };
  }

  /* 对齐：两侧取同一个显示高度，并把中心放在同一水平线上。
   * 高度取两侧“能完整放下”的较小值，所以对齐后谁都不会被裁切。 */
  function layout() {
    const boxes = { left: fitBox('left'), right: fitBox('right') };
    const heights = ['left', 'right'].map((s) => boxes[s] && boxes[s].h).filter(Boolean);
    const commonH = heights.length ? Math.min.apply(null, heights) : 0;
    ['left', 'right'].forEach((side) => {
      const box = boxes[side];
      const img = imgOf(side);
      if (!box || !img) { base[side] = { w: 0, h: 0 }; return; }
      const ratio = box.w / box.h;
      const h = align && commonH ? commonH : box.h;
      base[side] = { w: h * ratio, h };
      img.style.width = base[side].w.toFixed(2) + 'px';
      img.style.height = base[side].h.toFixed(2) + 'px';
    });
    applyView();
    const stage = $('#stage');
    if (stage) stage.dataset.align = align ? 'on' : 'off';
  }

  function resetView() {
    view.z = 1;
    view.x = 0;
    view.y = 0;
    applyView();
  }

  function setSplit(pct) {
    split = Math.max(15, Math.min(85, pct));
    const stage = $('#stage');
    stage.style.setProperty('--split', split.toFixed(2) + '%');
    $('#splitPct').textContent = Math.round(split) + '%';
  }

  /* ---------- 底部布局：高度与右侧鉴别区宽度都可拖拽 ---------- */
  const LAYOUT_KEY = 'radiocheck.compare.layout';
  const LAYOUT = { bottomH: 266, diffW: 392 };
  const BOTTOM_MIN = 150;
  const DIFF_MIN = 220;
  const FILM_MIN = 300;

  function readLayout() {
    try {
      const v = JSON.parse(localStorage.getItem(LAYOUT_KEY) || 'null');
      if (v && Number.isFinite(v.bottomH)) LAYOUT.bottomH = v.bottomH;
      if (v && Number.isFinite(v.diffW)) LAYOUT.diffW = v.diffW;
    } catch (e) { /* 坏数据忽略，用默认 */ }
  }

  function saveLayout() {
    try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(LAYOUT)); } catch (e) { /* 隐私模式忽略 */ }
  }

  function clampBottom(h) {
    const shell = $('.cmp-shell');
    const max = Math.max(BOTTOM_MIN, (shell ? shell.clientHeight : window.innerHeight) - 220);
    return Math.max(BOTTOM_MIN, Math.min(max, h));
  }

  function clampDiff(w) {
    const bottom = $('#cmpBottom');
    const total = bottom ? bottom.clientWidth : window.innerWidth;
    const max = Math.max(DIFF_MIN, total - FILM_MIN - 9);
    return Math.max(DIFF_MIN, Math.min(max, w));
  }

  function applyLayout() {
    const shell = $('.cmp-shell');
    const bottom = $('#cmpBottom');
    if (shell) shell.style.setProperty('--bottom-h', Math.round(LAYOUT.bottomH) + 'px');
    if (bottom) bottom.style.setProperty('--diff-w', Math.round(LAYOUT.diffW) + 'px');
    syncWideBtn();
  }

  function resetLayout() {
    LAYOUT.bottomH = 266;
    LAYOUT.diffW = 392;
    applyLayout();
    saveLayout();
    syncWideBtn();
    toast('布局已复位');
  }

  function syncWideBtn() {
    const btn = $('#diffWideBtn');
    if (!btn) return;
    const wide = LAYOUT.diffW >= 520;
    btn.textContent = wide ? '还原 ⤡' : '加宽 ⤢';
    btn.title = wide ? '还原鉴别区宽度' : '把鉴别区加宽到 560px';
  }

  function bindLayout() {
    readLayout();
    applyLayout();

    const hsplit = $('#hsplit');
    const vsplit = $('#vsplit');

    const wideBtn = $('#diffWideBtn');
    if (wideBtn) {
      wideBtn.addEventListener('click', () => {
        LAYOUT.diffW = LAYOUT.diffW >= 520 ? 392 : clampDiff(560);
        applyLayout();
        saveLayout();
      });
    }

    if (hsplit) {
      hsplit.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        const startY = e.clientY;
        const startH = LAYOUT.bottomH;
        const move = (ev) => {
          LAYOUT.bottomH = clampBottom(startH - (ev.clientY - startY));
          applyLayout();
        };
        const up = () => {
          window.removeEventListener('pointermove', move);
          window.removeEventListener('pointerup', up);
          saveLayout();
        };
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', up);
      });
      hsplit.addEventListener('dblclick', resetLayout);
      hsplit.addEventListener('keydown', (e) => {
        if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
        e.preventDefault();
        LAYOUT.bottomH = clampBottom(LAYOUT.bottomH + (e.key === 'ArrowUp' ? 16 : -16));
        applyLayout();
        saveLayout();
      });
    }

    if (vsplit) {
      vsplit.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        const startX = e.clientX;
        const startW = LAYOUT.diffW;
        const move = (ev) => {
          LAYOUT.diffW = clampDiff(startW - (ev.clientX - startX));
          applyLayout();
        };
        const up = () => {
          window.removeEventListener('pointermove', move);
          window.removeEventListener('pointerup', up);
          saveLayout();
        };
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', up);
      });
      vsplit.addEventListener('dblclick', resetLayout);
      vsplit.addEventListener('keydown', (e) => {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        e.preventDefault();
        LAYOUT.diffW = clampDiff(LAYOUT.diffW + (e.key === 'ArrowLeft' ? 16 : -16));
        applyLayout();
        saveLayout();
      });
    }

    window.addEventListener('resize', () => {
      LAYOUT.bottomH = clampBottom(LAYOUT.bottomH);
      LAYOUT.diffW = clampDiff(LAYOUT.diffW);
      applyLayout();
    });
  }

  function renderPane(side) {
    const id = sides[side];
    const c = caseOf(id);
    const pane = side === 'left' ? $('#paneLeft') : $('#paneRight');
    const img = side === 'left' ? $('#leftImg') : $('#rightImg');
    const empty = side === 'left' ? $('#leftEmpty') : $('#rightEmpty');
    const diag = side === 'left' ? $('#leftDiag') : $('#rightDiag');
    const foot = side === 'left' ? $('#leftFoot') : $('#rightFoot');
    const topic = side === 'left' ? $('#leftTopic') : $('#rightTopic');
    const cid = side === 'left' ? $('#leftId') : $('#rightId');

    if (!c) {
      topic.textContent = '拖入一张影像';
      cid.textContent = '—';
      img.removeAttribute('src');
      img.alt = '';
      empty.hidden = false;
      diag.hidden = true;
      foot.textContent = '—';
      pane.classList.remove('filled');
      resetView();
      layout();
      return;
    }

    topic.textContent = labelOf(id);
    cid.textContent = c.id;
    img.src = window.RCKB ? window.RCKB.imageUrl(c.image) : '../' + c.image;
    img.alt = c.image_alt || c.topic;
    empty.hidden = true;
    diag.hidden = false;
    diag.textContent = diagOf(id);
    const annot = /原图|红箭头|白线|Old fractures/.test(c.image_note || '');
    foot.textContent = `${c.pose} · ${c.source.artist} · ${c.source.license}${annot ? ' · 原图带标注' : ''}`;
    pane.classList.add('filled');
    resetView();
    layout();
    updateUsed();
    updateHint();
  }

  function updateUsed() {
    $$('.film-card').forEach((card) => {
      const id = card.dataset.case;
      card.classList.toggle('used', sides.left === id || sides.right === id);
    });
  }

  function updateHint() {
    const both = sides.left && sides.right;
    const tip = both
      ? '拖中间条调宽度 · 拖底部分隔条调高度'
      : (sides.left || sides.right ? '再放一张到另一侧' : '');
    $('#tbHint').textContent = [align ? '同高对齐' : '未对齐', tip].filter(Boolean).join(' · ');
    const pair = pairFor(sides.left, sides.right);
    $('#openCase').hidden = !sides.left;
    if (sides.left) $('#openCase').dataset.case = sides.left;
    if (pair) {
      $$('.pair-chip').forEach((b) => b.classList.toggle('on', b.dataset.pair === pair.pair.id));
    } else {
      $$('.pair-chip').forEach((b) => b.classList.remove('on'));
    }
    renderDiff();
    updateUrl();
  }

  function pairFor(l, r) {
    if (!l || !r) return null;
    for (const p of PAIRS) {
      if (p.left === l && p.right === r) return { pair: p, flipped: false };
      if (p.left === r && p.right === l) return { pair: p, flipped: true };
    }
    return null;
  }

  function renderFilm() {
    const strip = $('#filmStrip');
    strip.innerHTML = CASES.map((c) => `
      <div class="film-card" draggable="true" data-case="${c.id}" title="${esc(c.topic)} · 拖到左侧或右侧">
        <span class="drag-dot">⠿</span>
        <div class="thumb"><img src="${esc(window.RCKB ? window.RCKB.imageUrl(c.image) : "../" + c.image)}" alt="${esc(c.topic)}" loading="lazy"></div>
        <div class="fc-b"><b>${esc(c.topic)}</b><span>${esc(c.id)}</span></div>
      </div>`).join('');
    $$('.film-card', strip).forEach((card) => {
      const id = card.dataset.case;
      card.addEventListener('dragstart', (e) => {
        dragging = id;
        e.dataTransfer.effectAllowed = 'copy';
        try { e.dataTransfer.setData('text/plain', id); } catch (err) {}
        card.classList.add('dragging');
      });
      card.addEventListener('dragend', () => {
        dragging = null;
        card.classList.remove('dragging');
        $$('.pane-canvas').forEach((p) => p.classList.remove('drop-hot'));
      });
      card.addEventListener('click', () => {
        assign(active, id);
        // 分配后自动切到另一侧，连续拖两张更顺。
        const other = active === 'left' ? 'right' : 'left';
        if (!sides[other]) setActive(other);
      });
    });
  }

  function renderPairs() {
    const row = $('#pairRow');
    row.innerHTML = PAIRS.map((p) => `
      <button class="pair-chip" data-pair="${p.id}" title="${esc(p.tag)}">${esc(p.title)}</button>`).join('');
    $$('.pair-chip', row).forEach((b) => {
      b.onclick = () => {
        const p = PAIRS.find((x) => x.id === b.dataset.pair);
        if (!p) return;
        sides.left = p.left;
        sides.right = p.right;
        setActive('left');
        renderPane('left');
        renderPane('right');
        updateHint();
        toast('已载入：' + p.title);
      };
    });
  }

  function setActive(side) {
    active = side;
    $$('.assign .btn').forEach((b) => b.classList.toggle('on', b.dataset.active === side));
    $$('.cmp-pane').forEach((p) => p.classList.toggle('active', p.dataset.side === side));
  }

  function assign(side, id) {
    if (!BY_ID[id]) return;
    sides[side] = id;
    renderPane(side);
    updateHint();
  }

  function clear(side) {
    sides[side] = null;
    renderPane(side);
    updateHint();
  }

  function swap() {
    const l = sides.left;
    sides.left = sides.right;
    sides.right = l;
    renderPane('left');
    renderPane('right');
    updateHint();
    toast('已交换左右');
  }

  function renderDiff() {
    const body = $('#diffBody');
    const title = $('#diffTitle');
    const tag = $('#diffTag');
    const l = caseOf(sides.left);
    const r = caseOf(sides.right);

    if (!l || !r) {
      title.textContent = '选一对，开始对比';
      tag.textContent = '相同点 / 鉴别点 / 一句话记忆';
      body.innerHTML = `<div class="empty-state"><div class="ico">⇄</div>
        <b>把两张影像放到两侧</b></div>`;
      return;
    }

    const found = pairFor(sides.left, sides.right);
    if (found) {
      const p = found.pair;
      const leftCase = found.flipped ? r : l;
      const rightCase = found.flipped ? l : r;
      title.textContent = p.title;
      tag.textContent = p.tag + ' · 相同点 / 鉴别点 / 一句话记忆';
      const rows = p.diff.map((d) => `
        <div class="diff-row">
          <div class="ax">${esc(d.axis)}</div>
          <div class="l">${esc(found.flipped ? d.right : d.left)}</div>
          <div class="r">${esc(found.flipped ? d.left : d.right)}</div>
        </div>`).join('');
      body.innerHTML = `
        <div class="diff-same"><b>相同点</b>${p.same.map(esc).join(' ')}<br><span class="muted">两侧按同高对齐显示，可直接比较同一高度的结构；未按患者体位做像素级配准，病灶大小仍以测量为准。</span></div>
        <div class="diff-table">
          <div class="diff-row">
            <div class="ax">鉴别轴</div>
            <div class="l">${esc(leftCase.topic)}</div>
            <div class="r">${esc(rightCase.topic)}</div>
          </div>
          ${rows}
        </div>
        <div class="diff-trap"><b>最容易错</b>${esc(p.trap)}</div>
        <div class="diff-q"><b>带着问题看</b>${esc(p.question)}</div>
        <div class="diff-case">
          <div><b>左侧</b><span>${esc(leftCase.diagnosis)}</span></div>
          <div><b>右侧</b><span>${esc(rightCase.diagnosis)}</span></div>
        </div>`;
      return;
    }

    title.textContent = '自由对比 · ' + l.topic + ' vs ' + r.topic;
    tag.textContent = '没有预置鉴别卡，先看两侧各自的阅片要点';
    const rows = [
      ['诊断', l.diagnosis, r.diagnosis],
      ['关键征象', (l.signs[0] || {}).detail || '—', (r.signs[0] || {}).detail || '—'],
      ['易错点', l.pitfall, r.pitfall],
      ['考点', l.exam_tip, r.exam_tip]
    ].map(([ax, a, b]) => `
      <div class="diff-row"><div class="ax">${esc(ax)}</div><div class="l">${esc(a)}</div><div class="r">${esc(b)}</div></div>`).join('');
    body.innerHTML = `
      <div class="diff-same"><b>相同点</b>同为胸部 X 线平片；都按“气道 → 肺野 → 肺门 → 心影 → 膈与肋膈角 → 骨骼”顺序扫读，再回到主诉与查体。<br><span class="muted">两侧按同高对齐显示，可直接比较同一高度的结构；未按患者体位做像素级配准，病灶大小仍以测量为准。</span></div>
      <div class="diff-table">
        <div class="diff-row"><div class="ax">对比项</div><div class="l">${esc(l.topic)}</div><div class="r">${esc(r.topic)}</div></div>
        ${rows}
      </div>
      <div class="diff-trap"><b>提示</b>自由对比没有预置答案，请用两侧所见自行归纳。</div>`;
  }

  function updateUrl() {
    const q = new URLSearchParams();
    if (sides.left) q.set('left', sides.left);
    if (sides.right) q.set('right', sides.right);
    const pair = pairFor(sides.left, sides.right);
    if (pair) q.set('pair', pair.pair.id);
    const s = q.toString();
    history.replaceState(null, '', s ? '?' + s : location.pathname);
  }

  function setMode(next) {
    mode = next;
    $('#stage').dataset.mode = next;
    $$('.seg button').forEach((b) => b.classList.toggle('on', b.dataset.mode === next));
    // 叠加模式下画布铺满整个舞台，尺寸变了必须重新对齐。
    layout();
    if (next === 'overlay') {
      toast('叠加擦除：拖动中间手柄看同一位置');
    }
  }

  function bind() {
    $$('.seg button').forEach((b) => {
      b.onclick = () => setMode(b.dataset.mode);
    });
    $('#swapBtn').onclick = swap;
    $('#fitBtn').onclick = () => { resetView(); layout(); toast('视图已复位'); };
    $('#alignBtn').onclick = () => {
      align = !align;
      $('#alignBtn').classList.toggle('on', align);
      layout();
      updateHint();
      toast(align ? '已按同高对齐两侧' : '已取消对齐，两侧各自铺满');
    };
    $('#revealBtn').onclick = () => {
      reveal = !reveal;
      $('#revealBtn').textContent = reveal ? '隐藏诊断' : '显示诊断';
      renderPane('left');
      renderPane('right');
      updateHint();
    };
    $('#randomBtn').onclick = () => {
      if (!PAIRS.length) return;
      const p = PAIRS[Math.floor(Math.random() * PAIRS.length)];
      sides.left = p.left;
      sides.right = p.right;
      renderPane('left');
      renderPane('right');
      updateHint();
      toast('随机：' + p.title);
    };
    $$('.assign .btn').forEach((b) => {
      b.onclick = () => setActive(b.dataset.active);
    });
    $$('[data-clear]').forEach((b) => {
      b.onclick = () => clear(b.dataset.clear);
    });
    $('#openCase').onclick = () => {
      const id = $('#openCase').dataset.case;
      if (id) location.href = 'exam.html#' + encodeURIComponent(id);
    };

    // 胶片条拖到两侧
    $$('.pane-canvas').forEach((pane) => {
      const side = pane.dataset.side;
      pane.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        pane.classList.add('drop-hot');
      });
      pane.addEventListener('dragleave', () => pane.classList.remove('drop-hot'));
      pane.addEventListener('drop', (e) => {
        e.preventDefault();
        pane.classList.remove('drop-hot');
        let id = '';
        try { id = e.dataTransfer.getData('text/plain'); } catch (err) {}
        if (!id && dragging) id = dragging;
        if (id) {
          assign(side, id);
          setActive(side === 'left' ? 'right' : 'left');
        }
      });
    });

    // 分隔条
    const splitEl = $('#split');
    splitEl.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      const stage = $('#stage');
      const rect = stage.getBoundingClientRect();
      const move = (ev) => setSplit((ev.clientX - rect.left) / rect.width * 100);
      const up = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
      move(e);
    });
    splitEl.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') { e.preventDefault(); e.stopPropagation(); setSplit(split - 2); }
      if (e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); setSplit(split + 2); }
    });

    ['left', 'right'].forEach((side) => {
      const img = imgOf(side);
      if (img) img.addEventListener('load', layout);
    });
    if (window.ResizeObserver) {
      // 观察两个画布而不是舞台：拖动分隔条时舞台尺寸不变，只有画布宽度变。
      const ro = new ResizeObserver(() => layout());
      ['left', 'right'].forEach((side) => {
        const canvas = canvasOf(side);
        if (canvas) ro.observe(canvas);
      });
    } else {
      window.addEventListener('resize', layout);
    }

    // 缩放与平移
    ['left', 'right'].forEach((side) => {
      const pane = side === 'left' ? $('#paneLeft') : $('#paneRight');
      const canvas = $('.pane-canvas', pane);
      canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        const next = Math.max(1, Math.min(4, view.z + (e.deltaY < 0 ? 0.12 : -0.12)));
        view.z = next;
        if (next === 1) { view.x = 0; view.y = 0; }
        // 两侧共用一套视图，缩放天然同步，不存在只放大一侧的情况。
        applyView();
      }, { passive: false });
      canvas.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        if (e.target.closest('.ph-clear')) return;
        panning = { side, x: e.clientX, y: e.clientY, ox: view.x, oy: view.y };
        canvas.classList.add('dragging');
        canvas.setPointerCapture(e.pointerId);
      });
      canvas.addEventListener('pointermove', (e) => {
        if (!panning || panning.side !== side) return;
        view.x = panning.ox + (e.clientX - panning.x);
        view.y = panning.oy + (e.clientY - panning.y);
        applyView();
      });
      const end = () => {
        panning = null;
        canvas.classList.remove('dragging');
      };
      canvas.addEventListener('pointerup', end);
      canvas.addEventListener('pointercancel', end);
      canvas.addEventListener('dblclick', () => resetView());
    });

    document.addEventListener('keydown', (e) => {
      if (/input|textarea|select/i.test((e.target.tagName || ''))) return;
      if (e.key === 'ArrowLeft' && !e.shiftKey) setSplit(split - 2);
      if (e.key === 'ArrowRight' && !e.shiftKey) setSplit(split + 2);
      if (e.key.toLowerCase() === 's') swap();
      if (e.key.toLowerCase() === 'r') { resetView(); layout(); }
    });
  }

  async function init() {
    try {
      DATA = window.RCKB
        ? await window.RCKB.getJSON('/api/kb/exam', DATA_URL)
        : await (await fetch(DATA_URL, { cache: 'no-cache' })).json();
      CASES = DATA.cases || [];
      BY_ID = Object.fromEntries(CASES.map((c) => [c.id, c]));
      PAIRS = DATA.pairs || [];
      if (!CASES.length) throw new Error('没有病例');
    } catch (err) {
      $('#filmStrip').innerHTML = `<div class="empty-state"><b>数据载入失败</b><span>请确认知识库服务已启动，或先完成站点构建。</span></div>`;
      return;
    }
    renderFilm();
    renderPairs();
    bind();
    bindLayout();
    setSplit(50);

    const q = new URLSearchParams(location.search);
    const l = q.get('left');
    const r = q.get('right');
    if (l && BY_ID[l] && r && BY_ID[r]) {
      sides.left = l;
      sides.right = r;
    } else if (PAIRS.length) {
      sides.left = PAIRS[0].left;
      sides.right = PAIRS[0].right;
    } else {
      sides.left = CASES[0].id;
      sides.right = CASES[1] ? CASES[1].id : null;
    }
    setActive('left');
    renderPane('left');
    renderPane('right');
    layout();
    updateHint();
  }

  init();
})();
