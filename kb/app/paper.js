/* 组卷与自测：教师选题出卷，学生看图作答，交卷即出成绩。
 * 卷子与成绩都用文件交换，不依赖后端，纯静态托管也能跑通。 */
(function () {
  'use strict';

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  const STATIC = !!window.YZStatic;
  const IMG_BASE = STATIC ? '../' : '/';
  const BANK_URL = STATIC ? '../data/quiz_bank.json' : '/data/quiz_bank.json';

  const LS_PAPER = 'yz.paper.current';
  const LS_RESULTS = 'yz.paper.results';

  const TYPE_NAME = {
    locate: '分区定位',
    sign: '征象对应',
    laterality: '体位规则',
    doc: '文献溯源'
  };

  const S = {
    bank: null,
    chapters: new Set(),
    types: new Set(['locate', 'sign', 'doc']),
    count: 10,
    paper: null,
    idx: 0,
    answers: [],
    startedAt: 0,
    qStartAt: 0,
    mode: 'build',
    results: []
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
  }

  function shuffle(a) {
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function fmtDur(ms) {
    const s = Math.round(ms / 1000);
    return s < 60 ? s + ' 秒' : Math.floor(s / 60) + ' 分 ' + (s % 60) + ' 秒';
  }

  /* ---------------- 题库与选题 ---------------- */

  function buildPicks() {
    const chCount = {};
    const typeCount = {};
    S.bank.questions.forEach((q) => {
      const ch = q.chapter || '未分类';
      chCount[ch] = (chCount[ch] || 0) + 1;
      typeCount[q.type] = (typeCount[q.type] || 0) + 1;
    });
    const chs = Object.entries(chCount).sort((a, b) => b[1] - a[1]);
    if (!S.chapters.size && chs.length) S.chapters.add(chs[0][0]);

    $('#chapterPick').innerHTML = chs.map(([k, n]) =>
      `<button data-ch="${esc(k)}" class="${S.chapters.has(k) ? 'on' : ''}">${esc(k)}<b>${n}</b></button>`
    ).join('');

    $('#typePick').innerHTML = Object.keys(TYPE_NAME).map((k) =>
      `<button data-ty="${k}" class="${S.types.has(k) ? 'on' : ''}">${TYPE_NAME[k]}<b>${typeCount[k] || 0}</b></button>`
    ).join('');

    $('#chapterPick').onclick = (e) => {
      const b = e.target.closest('button[data-ch]');
      if (!b) return;
      const k = b.dataset.ch;
      if (S.chapters.has(k)) S.chapters.delete(k); else S.chapters.add(k);
      b.classList.toggle('on', S.chapters.has(k));
      updateNote();
    };
    $('#typePick').onclick = (e) => {
      const b = e.target.closest('button[data-ty]');
      if (!b) return;
      const k = b.dataset.ty;
      if (S.types.has(k)) S.types.delete(k); else S.types.add(k);
      b.classList.toggle('on', S.types.has(k));
      updateNote();
    };
    $('#countPick').onclick = (e) => {
      const b = e.target.closest('button[data-n]');
      if (!b) return;
      S.count = parseInt(b.dataset.n, 10);
      $$('#countPick button').forEach((x) => x.classList.toggle('on', x === b));
      updateNote();
    };
    updateNote();
  }

  function poolNow() {
    if (!S.bank) return [];
    return S.bank.questions.filter((q) =>
      S.chapters.has(q.chapter || '未分类') && S.types.has(q.type));
  }

  function updateNote() {
    const n = poolNow().length;
    $('#pickNote').textContent = n
      ? `当前可选 ${n} 题` + (n < S.count ? `，少于题量，将按 ${n} 题出卷` : '')
      : '当前条件没有题目，换章节或题型';
    $('#makeBtn').disabled = !n;
  }

  /* 抽样：按题型池大小成比例分配，并尽量让病例分散。
   * 简单轮转会让小池题型（doc 只有 9 题）在前几轮被抽空，
   * 结果 10 题里有 4 道文献溯源题，比例失真。 */
  function sample(pool, n) {
    const byType = {};
    pool.forEach((q) => (byType[q.type] = byType[q.type] || []).push(q));
    const types = Object.keys(byType);
    Object.values(byType).forEach(shuffle);
    const taken = {};
    types.forEach((t) => (taken[t] = 0));
    const out = [];
    const usedCase = new Set();
    while (out.length < n) {
      let best = null;
      let bestRatio = Infinity;
      for (const t of types) {
        const arr = byType[t];
        if (!arr.length) continue;
        const ratio = taken[t] / (taken[t] + arr.length);
        if (ratio < bestRatio) { bestRatio = ratio; best = t; }
      }
      if (!best) break;
      const arr = byType[best];
      let k = arr.findIndex((q) => !usedCase.has(q.case_id));
      if (k < 0) k = 0;
      const q = arr.splice(k, 1)[0];
      out.push(q);
      usedCase.add(q.case_id);
      taken[best]++;
    }
    return out;
  }

  function makePaper() {
    const pool = poolNow();
    if (!pool.length) return;
    const qs = sample(pool, Math.min(S.count, pool.length));
    const title = ($('#paperTitle').value || '').trim()
      || `${[...S.chapters].join('·')} 自测 ${new Date().toLocaleDateString('zh-CN')}`;
    S.paper = {
      v: 1,
      id: 'P-' + Date.now().toString(36).toUpperCase(),
      title,
      createdAt: new Date().toISOString(),
      config: { chapters: [...S.chapters], types: [...S.types], count: qs.length },
      questions: qs.map((q) => ({
        qid: q.qid, type: q.type, case_id: q.case_id, image: q.image,
        coords: q.coords, chapter: q.chapter, body_part: q.body_part,
        prompt: q.prompt, options: q.options, answer: q.answer, explain: q.explain
      }))
    };
    try { localStorage.setItem(LS_PAPER, JSON.stringify(S.paper)); } catch (e) {}
    renderPreview();
  }

  function renderPreview() {
    const p = S.paper;
    $('#startBtn').disabled = !p;
    $('#dlPaper').disabled = !p;
    if (!p) {
      $('#pvCount').textContent = '';
      $('#preview').className = 'empty';
      $('#preview').innerHTML = '还没生成卷子。<br>左侧选章节、题型和题量，再点「生成卷子」。';
      return;
    }
    $('#pvCount').textContent = `${p.questions.length} 题 · ${p.id}`;
    $('#preview').className = '';
    $('#preview').innerHTML = p.questions.map((q, i) => `
      <div class="pv">
        <i>${String(i + 1).padStart(2, '0')}</i>
        <div class="t">${esc(q.prompt)}
          <small>${esc(TYPE_NAME[q.type] || q.type)} · ${esc(q.case_id)} · ${esc(q.chapter || '')}</small>
        </div>
      </div>`).join('');
  }

  /* ---------------- 作答 ---------------- */

  function startExam() {
    if (!S.paper) return;
    S.idx = 0;
    S.answers = new Array(S.paper.questions.length).fill(null);
    S.startedAt = Date.now();
    S.qStartAt = Date.now();
    setMode('exam');
    renderQuestion();
  }

  function fitFrame() {
    const img = $('#exImg');
    const wrap = $('#exImgWrap');
    if (!img.naturalWidth || !wrap.clientWidth) return;
    const W = Math.max(120, wrap.clientWidth - 36);
    const H = Math.max(120, wrap.clientHeight - 36);
    const sc = Math.min(W / img.naturalWidth, H / img.naturalHeight);
    const f = $('#exFrame');
    f.style.width = Math.round(img.naturalWidth * sc) + 'px';
    f.style.height = Math.round(img.naturalHeight * sc) + 'px';
  }

  function drawBox(q) {
    const el = $('#exBox');
    if (!q.coords || q.coords.length !== 4) { el.hidden = true; return; }
    el.hidden = false;
    const [x, y, w, h] = q.coords;
    el.style.left = (x * 100) + '%';
    el.style.top = (y * 100) + '%';
    el.style.width = (w * 100) + '%';
    el.style.height = (h * 100) + '%';
  }

  function renderQuestion() {
    const p = S.paper;
    const q = p.questions[S.idx];
    if (!q) return;
    S.qStartAt = Date.now();

    $('#exTitle').textContent = p.title;
    $('#exProgress').textContent = `${S.idx + 1} / ${p.questions.length}`;
    $('#exType').textContent = TYPE_NAME[q.type] || q.type;
    $('#exCase').textContent = `${q.case_id} · ${q.body_part || ''}`;
    $('#exPrompt').textContent = q.prompt;

    const hasImg = !!q.image;
    $('#exNoImg').hidden = hasImg;
    $('#exFrame').style.display = hasImg ? '' : 'none';
    if (hasImg) {
      const img = $('#exImg');
      img.onload = () => { fitFrame(); drawBox(q); };
      img.src = IMG_BASE + q.image;
      if (img.complete && img.naturalWidth) { fitFrame(); drawBox(q); }
    }

    const a = S.answers[S.idx];
    $('#exOpts').innerHTML = q.options.map((o, i) =>
      `<button data-i="${i}">${esc(o)}</button>`).join('');
    $$('#exOpts button').forEach((b) => {
      b.onclick = () => choose(parseInt(b.dataset.i, 10));
    });
    $('#exExp').hidden = true;
    if (a && a.choice != null) paintAnswer(q, a);

    $('#exPrev').disabled = S.idx === 0;
    const last = S.idx === p.questions.length - 1;
    $('#exNext').hidden = last;
    $('#exSubmit').hidden = !last;
    updateLive();
  }

  function paintAnswer(q, a) {
    $$('#exOpts button').forEach((b) => {
      const t = b.textContent;
      b.disabled = true;
      if (t === q.answer) b.classList.add('right');
      else if (t === a.choice) b.classList.add('wrong');
    });
    const exp = $('#exExp');
    exp.hidden = false;
    exp.innerHTML = `<b>${a.correct ? '✓ 正确' : '✗ 再想想'}</b> · ${esc(q.explain)}`;
  }

  function choose(i) {
    const q = S.paper.questions[S.idx];
    if (S.answers[S.idx]) return;
    const choice = q.options[i];
    const rec = { choice, correct: choice === q.answer, ms: Date.now() - S.qStartAt };
    S.answers[S.idx] = rec;
    paintAnswer(q, rec);
    updateLive();
  }

  function updateLive() {
    const done = S.answers.filter((x) => x && x.choice != null).length;
    const right = S.answers.filter((x) => x && x.correct).length;
    $('#exLive').textContent = done
      ? `已答 ${done}/${S.paper.questions.length} · 正确 ${right}`
      : '选一个答案，立刻知道对错';
  }

  /* ---------------- 成绩 ---------------- */

  function groupBy(items, key) {
    const m = {};
    items.forEach((x) => {
      const k = x[key] || '未分类';
      m[k] = m[k] || { right: 0, total: 0 };
      m[k].total++;
      if (x.correct) m[k].right++;
    });
    return m;
  }

  function submit() {
    const p = S.paper;
    const items = p.questions.map((q, i) => {
      const a = S.answers[i] || {};
      return {
        qid: q.qid, type: q.type, chapter: q.chapter, prompt: q.prompt,
        answer: q.answer, choice: a.choice == null ? null : a.choice,
        correct: !!a.correct, ms: a.ms || 0
      };
    });
    const right = items.filter((x) => x.correct).length;
    const total = items.length;
    const rec = {
      paperId: p.id,
      title: p.title,
      submittedAt: new Date().toISOString(),
      total, right,
      pct: total ? Math.round((right / total) * 100) : 0,
      elapsed: Date.now() - S.startedAt,
      byType: groupBy(items, 'type'),
      byChapter: groupBy(items, 'chapter'),
      items
    };
    S.results.unshift(rec);
    saveResults();
    setMode('report');
  }

  function saveResults() {
    S.results = S.results.slice(0, 50);
    try { localStorage.setItem(LS_RESULTS, JSON.stringify(S.results)); } catch (e) {}
  }

  function bars(map, names) {
    const rows = Object.entries(map).sort((a, b) => b[1].total - a[1].total);
    if (!rows.length) return '<span class="muted">无数据</span>';
    return rows.map(([k, v]) => {
      const pct = v.total ? Math.round((v.right / v.total) * 100) : 0;
      const cls = pct >= 80 ? '' : pct >= 60 ? 'mid' : 'low';
      return `<div class="bar">
        <span>${esc((names && names[k]) || k)}</span>
        <span class="track"><span class="fill ${cls}" style="width:${pct}%"></span></span>
        <span class="num">${v.right}/${v.total}</span>
      </div>`;
    }).join('');
  }

  function wrongHtml(x) {
    return `<div class="wrong">
      <span class="tag">${esc(TYPE_NAME[x.type] || x.type)}</span>
      <div class="q">${esc(x.prompt)}
        <div class="a">你的答案：<s>${esc(x.choice || '未作答')}</s> · 正确：<b>${esc(x.answer)}</b></div>
      </div>
    </div>`;
  }

  function renderReport() {
    const box = $('#repBox');
    if (!S.results.length) {
      box.className = 'empty';
      box.innerHTML = '还没有成绩。<br>先组卷并完成一次作答。';
      return;
    }
    box.className = '';
    const r = S.results[0];
    const wrongs = r.items.filter((x) => !x.correct);
    box.innerHTML = `
      <div class="card">
        <div class="rephead">
          <div class="big">${r.pct}<small>%</small></div>
          <div class="meta">
            <b>${esc(r.title)}</b><br>
            答对 ${r.right} / ${r.total} · 用时 ${fmtDur(r.elapsed)}<br>
            ${esc(r.paperId)} · ${new Date(r.submittedAt).toLocaleString('zh-CN')}
          </div>
          <div class="spacer"></div>
          <div class="row">
            <button id="dlResult">导出成绩</button>
            <label class="filebtn">导入成绩<input id="importResult" type="file" accept=".json,application/json" hidden></label>
            <button id="newPaper">再组一份</button>
          </div>
        </div>
      </div>
      <div class="card">
        <h2>按题型</h2>
        <div class="bars">${bars(r.byType, TYPE_NAME)}</div>
      </div>
      <div class="card">
        <h2>按章节</h2>
        <div class="bars">${bars(r.byChapter)}</div>
      </div>
      ${wrongs.length ? `<div class="card">
        <h2>错题 ${wrongs.length}</h2>
        ${wrongs.map(wrongHtml).join('')}
      </div>` : `<div class="card"><h2>全对</h2><p class="note">这一份没有错题。可以加题量或换章节再试。</p></div>`}
      ${S.results.length > 1 ? `<div class="card">
        <h2>历史 ${S.results.length} 次</h2>
        <div class="bars">${S.results.slice(1, 11).map((x) => `
          <div class="bar">
            <span>${esc(x.title.slice(0, 12))}</span>
            <span class="track"><span class="fill ${x.pct >= 80 ? '' : x.pct >= 60 ? 'mid' : 'low'}" style="width:${x.pct}%"></span></span>
            <span class="num">${x.pct}%</span>
          </div>`).join('')}</div>
      </div>` : ''}
    `;
    bindReport();
  }

  function bindReport() {
    const dl = $('#dlResult');
    if (dl) dl.onclick = () => download(`result-${S.results[0].paperId}.json`, S.results[0]);
    const np = $('#newPaper');
    if (np) np.onclick = () => setMode('build');
    const imp = $('#importResult');
    if (imp) imp.onchange = async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      try {
        const rec = JSON.parse(await f.text());
        if (!rec.items || !rec.items.length) throw new Error('不是有效的成绩文件');
        S.results.unshift(rec);
        saveResults();
        renderReport();
      } catch (err) { alert('导入失败：' + err.message); }
      e.target.value = '';
    };
  }

  function download(name, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1500);
  }

  /* ---------------- 模式切换 ---------------- */

  function setMode(m) {
    S.mode = m;
    $$('#modeTabs button').forEach((b) => b.classList.toggle('on', b.dataset.m === m));
    $('#viewBuild').hidden = m !== 'build';
    $('#viewExam').hidden = m !== 'exam';
    $('#viewReport').hidden = m !== 'report';
    if (m === 'report') renderReport();
    if (m === 'exam') requestAnimationFrame(() => { fitFrame(); const q = S.paper && S.paper.questions[S.idx]; if (q) drawBox(q); });
  }

  /* ---------------- 初始化 ---------------- */

  async function init() {
    $('#modeTabs').onclick = (e) => {
      const b = e.target.closest('button[data-m]');
      if (!b) return;
      if (b.dataset.m === 'exam') {
        if (!S.paper) {
          alert('先生成一份卷子，或导入学生交回的卷子。');
          return;
        }
        // 直接点标签切到作答时，如果还没开考就初始化一次，
        // 否则会看到一个空的答题区。
        if (S.answers.length !== S.paper.questions.length) { startExam(); return; }
      }
      setMode(b.dataset.m);
    };
    $('#makeBtn').onclick = makePaper;
    $('#startBtn').onclick = startExam;
    $('#dlPaper').onclick = () => download(`paper-${S.paper.id}.json`, S.paper);
    $('#exQuit').onclick = () => { if (confirm('退出作答？已答内容不会保存。')) setMode('build'); };
    $('#exPrev').onclick = () => { if (S.idx > 0) { S.idx--; renderQuestion(); } };
    $('#exNext').onclick = () => { if (S.idx < S.paper.questions.length - 1) { S.idx++; renderQuestion(); } };
    $('#exSubmit').onclick = () => {
      const left = S.answers.filter((x) => !x || x.choice == null).length;
      if (left && !confirm(`还有 ${left} 题没答，未答按错误计。确定交卷？`)) return;
      submit();
    };
    window.addEventListener('resize', () => { if (S.mode === 'exam') fitFrame(); });

    $('#importPaper').onchange = async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      try {
        const p = JSON.parse(await f.text());
        if (!p.questions || !p.questions.length) throw new Error('不是有效的卷子文件');
        S.paper = p;
        try { localStorage.setItem(LS_PAPER, JSON.stringify(p)); } catch (err) {}
        renderPreview();
        startExam();
      } catch (err) { alert('导入失败：' + err.message); }
      e.target.value = '';
    };

    try {
      const r = await fetch(BANK_URL);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      S.bank = await r.json();
      $('#bankPill').textContent = `题库 ${S.bank.questions.length} 题`;
      buildPicks();
    } catch (err) {
      $('#bankPill').textContent = '题库未就绪';
      $('#preview').className = 'empty';
      $('#preview').innerHTML = `题库加载失败：${esc(err.message)}<br>`
        + '先运行 <code>python3 kb/scripts/build_quiz_bank.py</code> 生成题库。';
    }

    try {
      const raw = localStorage.getItem(LS_PAPER);
      if (raw) { S.paper = JSON.parse(raw); renderPreview(); }
    } catch (e) {}
    try {
      const raw = localStorage.getItem(LS_RESULTS);
      if (raw) S.results = JSON.parse(raw) || [];
    } catch (e) {}

    setMode('build');
  }

  init();
})();
