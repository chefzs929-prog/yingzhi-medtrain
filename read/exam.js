/* RadioCheck · 病例题
 * 数据：../data/exam/exam_cases.json
 * 记录：localStorage（本机，不上传）
 */
(function () {
  'use strict';

  const DATA_URL = '../data/exam/exam_cases.json';
  const STORE_KEY = 'radiocheck.exam.v1';
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);

  let DATA = null;
  let CASES = [];
  let BY_ID = {};
  let PAIRS = [];
  let answers = {};
  let current = 0;
  let wrongOnly = false;
  let zoom = { s: 1, x: 0, y: 0 };
  let panning = null;

  function loadStore() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      const obj = raw ? JSON.parse(raw) : {};
      answers = obj && typeof obj.answers === 'object' ? obj.answers : {};
    } catch (e) { answers = {}; }
  }

  function saveStore() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify({ answers, savedAt: Date.now() })); }
    catch (e) { /* 隐私模式忽略 */ }
  }

  function submitted(id) { return Object.prototype.hasOwnProperty.call(answers, id); }
  function isRight(id) { return submitted(id) && Number(answers[id]) === Number(BY_ID[id].answer); }

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

  function visibleCases() {
    if (!wrongOnly) return CASES;
    return CASES.filter((c) => submitted(c.id) && !isRight(c.id));
  }

  function indexOf(id) { return CASES.findIndex((c) => c.id === id); }

  function renderSyllabus() {
    const list = $('#sylList');
    const groups = [];
    DATA.syllabus.forEach((item) => {
      let g = groups.find((x) => x.name === item.group);
      if (!g) { g = { name: item.group, items: [] }; groups.push(g); }
      g.items.push(item);
    });
    list.innerHTML = groups.map((g) => `
      <div class="syl-group">${esc(g.name)}</div>
      ${g.items.map((it) => {
        const c = BY_ID[it.case_id];
        const idx = CASES.indexOf(c);
        const st = submitted(c.id) ? (isRight(c.id) ? 'right' : 'wrong') : '';
        return `<button class="syl-item ${idx === current ? 'on' : ''}" data-case="${c.id}">
          <span class="n">${String(idx + 1).padStart(2, '0')}</span>
          <span class="t">${esc(it.label)}</span>
          <span class="st ${st}"></span>
        </button>`;
      }).join('')}
    `).join('');
    $$('.syl-item', list).forEach((b) => {
      b.onclick = () => go(b.dataset.case);
    });
    const done = CASES.filter((c) => submitted(c.id)).length;
    $('#sylCount').textContent = `${done}/${CASES.length}`;
    $('#sylBar').style.width = (done / CASES.length * 100) + '%';
  }

  function renderSheet() {
    const grid = $('#sheetGrid');
    grid.innerHTML = CASES.map((c, i) => {
      const st = submitted(c.id) ? (isRight(c.id) ? 'right' : 'wrong') : '';
      const dim = wrongOnly && st !== 'wrong' ? 'dim' : '';
      return `<button class="sheet-cell ${st} ${i === current ? 'on' : ''} ${dim}" data-case="${c.id}"
        title="${esc(c.topic)}">${String(i + 1).padStart(2, '0')}</button>`;
    }).join('');
    $$('.sheet-cell', grid).forEach((b) => {
      b.onclick = () => go(b.dataset.case);
    });
    const done = CASES.filter((c) => submitted(c.id)).length;
    const right = CASES.filter((c) => isRight(c.id)).length;
    $('#sheetScore').textContent = `${right} / ${done}`;
    $('#sheetSub').textContent = done ? `正确 ${right} / 已答 ${done} · 本机记录` : '正确 / 已答 · 本机记录';
  }

  function renderSources() {
    const box = $('#sourceBox');
    box.innerHTML = DATA.sources.map((s) => `
      <a href="${esc(s.url)}" target="_blank" rel="noopener">
        <b>${esc(s.title)}</b>${esc(s.publisher)} · ${esc(s.note)}
      </a>`).join('') + `<a href="compare.html"><b>对比阅片</b>把相似病放在一起看 →</a>`;
  }

  function resetZoom() {
    zoom = { s: 1, x: 0, y: 0 };
    applyZoom();
  }

  function applyZoom() {
    const img = $('#img');
    if (!img) return;
    img.style.transform = `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.s})`;
    $('#zoomBadge').textContent = Math.round(zoom.s * 100) + '%';
  }

  function setZoom(next) {
    zoom.s = Math.max(1, Math.min(3.2, next));
    if (zoom.s === 1) { zoom.x = 0; zoom.y = 0; }
    applyZoom();
  }

  function renderCase() {
    const c = CASES[current];
    if (!c) return;
    const idx = current;
    $('#caseNo').textContent = `${c.id} · 病例 ${String(idx + 1).padStart(2, '0')}/${CASES.length}`;
    $('#caseTopic').textContent = c.topic;
    $('#caseDiff').textContent = c.difficulty;
    $('#caseDiff').className = 'badge ' + (c.difficulty === '基础' ? 'ok' : 'info');
    $('#caseChief').textContent = c.vignette.chief;
    $('#caseMeta').textContent = `${c.pose} · 胸部 X 线 · ${c.group}`;

    const v = c.vignette;
    $('#vignette').innerHTML = `
      <div class="vg-chief">${esc(v.chief)}</div>
      <dl>
        <div class="vg-row"><dt>现病史</dt><dd>${esc(v.present)}</dd></div>
        <div class="vg-row"><dt>既往史</dt><dd>${esc(v.history)}</dd></div>
        <div class="vg-row"><dt>查体</dt><dd>${esc(v.exam)}</dd></div>
        <div class="vg-row"><dt>辅助检查</dt><dd>${esc(v.labs)}</dd></div>
      </dl>`;

    $('#imgPose').textContent = c.pose + ' · ' + c.image_width + '×' + c.image_height;
    $('#img').src = window.RCKB ? window.RCKB.imageUrl(c.image) : '../' + c.image;
    $('#img').alt = c.image_alt;
    $('#imgEmpty').hidden = true;
    $('#imgNote').textContent = c.image_note || '';
    $('#imgNote').hidden = true;
    $('#noteBtn').textContent = '标注说明';
    const annot = /原图|红箭头|白线|Old fractures/.test(c.image_note || '');
    $('#imgSource').textContent = `${c.source.artist} · ${c.source.license}${annot ? ' · 原图带标注' : ''}`;
    resetZoom();

    $('#qNo').textContent = String(idx + 1);
    $('#qStem').textContent = c.question;
    $('#qState').className = 'q-state';
    $('#qState').textContent = submitted(c.id) ? (isRight(c.id) ? '已答对' : '已答错') : '未作答';
    if (submitted(c.id)) $('#qState').classList.add(isRight(c.id) ? 'right' : 'wrong');
    else if (c.id in pending) {
      $('#qState').textContent = '已选择 · 待提交';
      $('#qState').className = 'q-state';
    }

    renderOptions(c);
    renderFeedback(c);
    renderSyllabus();
    renderSheet();

    $('#compareBtn').href = compareHref(c.id);
    $('#prevBtn').disabled = visibleCases().length < 2;
    $('#nextBtn').disabled = visibleCases().length < 2;
    $('#retryBtn').hidden = !submitted(c.id);

    history.replaceState(null, '', '#' + c.id);
    $('#img').onload = () => { $('#imgEmpty').hidden = true; };
    $('#img').onerror = () => {
      $('#imgEmpty').hidden = false;
      $('#imgEmpty').textContent = '影像载入失败，请稍后重试。';
    };
  }

  function compareHref(id) {
    const c = BY_ID[id];
    const other = (c.compare || []).find((x) => BY_ID[x]) || (CASES.find((x) => x.id !== id) || {}).id;
    return `compare.html?left=${encodeURIComponent(id)}&right=${encodeURIComponent(other || '')}`;
  }

  function renderOptions(c) {
    const box = $('#options');
    const done = submitted(c.id);
    const chosen = done ? Number(answers[c.id]) : (c.id in pending ? Number(pending[c.id]) : -1);
    box.innerHTML = c.options.map((opt, i) => {
      let cls = 'opt';
      if (!done && i === chosen) cls += ' on';
      if (done) {
        if (i === Number(c.answer)) cls += ' right';
        else if (i === chosen) cls += ' wrong';
      }
      return `<button class="${cls}" data-i="${i}" ${done ? 'disabled' : ''}>
        <span class="k">${'ABCDE'[i]}</span><span>${esc(opt)}</span>
      </button>`;
    }).join('');
    $$('.opt', box).forEach((b) => {
      b.onclick = () => {
        if (submitted(c.id)) return;
        pending[c.id] = Number(b.dataset.i);
        renderOptions(c);
        $('#qState').textContent = '已选择 · 待提交';
        $('#qState').className = 'q-state';
      };
    });
    $('#submitBtn').disabled = done || !(c.id in pending);
    $('#submitBtn').textContent = done ? '已提交' : '提交答案';
  }

  const pending = {};

  function renderFeedback(c) {
    const box = $('#feedback');
    if (!submitted(c.id)) {
      box.hidden = true;
      box.innerHTML = '';
      return;
    }
    const chosen = Number(answers[c.id]);
    const right = chosen === Number(c.answer);
    const signs = (c.signs || []).map((s) => `<div class="fb-sign"><b>${esc(s.label)}</b><span>${esc(s.detail)}</span></div>`).join('');
    const cmp = (c.compare || []).filter((id) => BY_ID[id]).map((id) => {
      const o = BY_ID[id];
      return `<a class="btn sm" href="compare.html?left=${encodeURIComponent(c.id)}&right=${encodeURIComponent(id)}">对比：${esc(o.topic)}</a>`;
    }).join('');
    box.hidden = false;
    box.innerHTML = `
      <div class="fb-banner ${right ? 'right' : 'wrong'}">
        <div class="ico">${right ? '✓' : '!'}</div>
        <div>
          <b>${right ? '回答正确' : '回答错误'}</b>
          <span>正确答案：${'ABCDE'[Number(c.answer)]} · ${esc(c.options[Number(c.answer)])}${right ? '' : '；你选的是 ' + 'ABCDE'[chosen] + ' · ' + esc(c.options[chosen])}</span>
        </div>
      </div>
      <div class="fb-sec"><h3>影像所见</h3><p>${esc(c.explain)}</p></div>
      <div class="fb-sec"><h3>阅片要点</h3><div class="fb-signs">${signs}</div></div>
      <div class="fb-sec"><div class="fb-two">
        <div class="pit"><b>易错点</b>${esc(c.pitfall)}</div>
        <div class="tip"><b>考点</b>${esc(c.exam_tip)}</div>
      </div></div>
      <div class="fb-src">影像：${esc(c.source.title)} · ${esc(c.source.artist)} · ${esc(c.source.license)} ·
        <a href="${esc(c.source.url)}" target="_blank" rel="noopener">原始页面 ↗</a><br>
        题目为自编，非官方真题；不构成诊断。</div>
      <div class="fb-compare">${cmp}</div>`;
    $('#qState').className = 'q-state ' + (right ? 'right' : 'wrong');
    $('#qState').textContent = right ? '已答对' : '已答错';
  }

  function submit() {
    const c = CASES[current];
    if (!c || submitted(c.id)) return;
    if (!(c.id in pending)) { toast('先选一个选项'); return; }
    answers[c.id] = Number(pending[c.id]);
    delete pending[c.id];
    saveStore();
    renderOptions(c);
    renderFeedback(c);
    renderSyllabus();
    renderSheet();
    $('#retryBtn').hidden = false;
    $('#submitBtn').disabled = true;
    $('#submitBtn').textContent = '已提交';
    const fb = $('#feedback');
    if (fb) setTimeout(() => fb.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 60);
    toast(isRight(c.id) ? '回答正确' : '已记录，看看解析');
  }

  function go(id) {
    const i = indexOf(id);
    if (i < 0) return;
    if (wrongOnly) {
      const vis = visibleCases();
      if (!vis.includes(CASES[i])) {
        toast('当前是“只看错题”，这题不在错题里');
        return;
      }
    }
    current = i;
    renderCase();
    $('.exam-main').scrollTop = 0;
  }

  function step(dir) {
    const vis = visibleCases();
    if (!vis.length) { toast('还没有错题'); return; }
    let idx = vis.indexOf(CASES[current]);
    if (idx < 0) idx = 0;
    idx = (idx + dir + vis.length) % vis.length;
    go(vis[idx].id);
  }

  function randomCase() {
    const vis = visibleCases().filter((c) => c.id !== CASES[current].id);
    if (!vis.length) return;
    go(vis[Math.floor(Math.random() * vis.length)].id);
  }

  function bind() {
    $('#submitBtn').onclick = submit;
    $('#retryBtn').onclick = () => {
      const c = CASES[current];
      delete answers[c.id];
      delete pending[c.id];
      saveStore();
      renderCase();
      toast('已清空本题，可重做');
    };
    $('#prevBtn').onclick = () => step(-1);
    $('#nextBtn').onclick = () => step(1);
    $('#randomBtn').onclick = randomCase;
    $('#wrongOnly').onclick = () => {
      wrongOnly = !wrongOnly;
      $('#wrongOnly').classList.toggle('solid', wrongOnly);
      $('#wrongOnly').textContent = wrongOnly ? '显示全部' : '只看错题';
      if (wrongOnly) {
        const vis = visibleCases();
        if (!vis.length) { toast('还没有错题'); }
        else if (!vis.includes(CASES[current])) go(vis[0].id);
      }
      renderSyllabus();
      renderSheet();
    };
    $('#resetBtn').onclick = () => {
      if (!confirm('清空本机的答题记录？影像与题目不会删除。')) return;
      answers = {};
      Object.keys(pending).forEach((k) => delete pending[k]);
      saveStore();
      current = 0;
      wrongOnly = false;
      $('#wrongOnly').classList.remove('solid');
      $('#wrongOnly').textContent = '只看错题';
      renderCase();
      toast('已清空本机记录');
    };
    $('#noteBtn').onclick = () => {
      const el = $('#imgNote');
      el.hidden = !el.hidden;
      $('#noteBtn').textContent = el.hidden ? '标注说明' : '收起说明';
    };
    $('#zoomIn').onclick = () => setZoom(zoom.s + 0.2);
    $('#zoomOut').onclick = () => setZoom(zoom.s - 0.2);
    $('#fitBtn').onclick = resetZoom;

    const stage = $('#stage');
    stage.addEventListener('wheel', (e) => {
      e.preventDefault();
      setZoom(zoom.s + (e.deltaY < 0 ? 0.12 : -0.12));
    }, { passive: false });
    stage.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      panning = { x: e.clientX, y: e.clientY, ox: zoom.x, oy: zoom.y };
      stage.classList.add('dragging');
      stage.setPointerCapture(e.pointerId);
    });
    stage.addEventListener('pointermove', (e) => {
      if (!panning) return;
      zoom.x = panning.ox + (e.clientX - panning.x);
      zoom.y = panning.oy + (e.clientY - panning.y);
      applyZoom();
    });
    const endPan = () => { panning = null; stage.classList.remove('dragging'); };
    stage.addEventListener('pointerup', endPan);
    stage.addEventListener('pointercancel', endPan);
    stage.addEventListener('dblclick', resetZoom);

    document.addEventListener('keydown', (e) => {
      if (/input|textarea|select/i.test((e.target.tagName || ''))) return;
      if (e.key === 'ArrowLeft') { step(-1); }
      else if (e.key === 'ArrowRight') { step(1); }
      else if (e.key === 'Enter') { submit(); }
      else if (/^[1-5]$/.test(e.key)) {
        const c = CASES[current];
        if (!c || submitted(c.id)) return;
        const b = $(`.opt[data-i="${Number(e.key) - 1}"]`);
        if (b) b.click();
      }
    });
  }

  async function init() {
    loadStore();
    try {
      DATA = window.RCKB
        ? await window.RCKB.getJSON('/api/kb/exam', DATA_URL)
        : await (await fetch(DATA_URL, { cache: 'no-cache' })).json();
      CASES = DATA.cases || [];
      BY_ID = Object.fromEntries(CASES.map((c) => [c.id, c]));
      PAIRS = DATA.pairs || [];
      if (!CASES.length) throw new Error('没有病例');
    } catch (err) {
      $('#vignette').innerHTML = `<div class="empty-state"><b>病例数据载入失败</b><span>请确认知识库服务已启动，或先完成站点构建。</span></div>`;
      return;
    }
    renderSources();
    const hash = decodeURIComponent((location.hash || '').replace(/^#/, ''));
    current = Math.max(0, indexOf(hash));
    bind();
    renderCase();
  }

  init();
})();
