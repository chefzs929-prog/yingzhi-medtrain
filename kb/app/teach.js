/* 教学版：章节树 → 病例 → 分区 → 讲解卡 → 自测 */
const S = {
  chapters: [], cases: [], chapter: null, current: null,
  lesson: null, activeRegion: null, learned: new Set(),
  showRegion: true, quiz: null, quizIdx: 0,
};

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + ' ' + r.status);
  return r.json();
}

/* ---------- 初始化 ---------- */
async function init() {
  const saved = localStorage.getItem('teach.learned');
  if (saved) JSON.parse(saved).forEach((x) => S.learned.add(x));
  const [ch, cs] = await Promise.all([api('/api/chapters'), api('/api/cases')]);
  S.chapters = ch.chapters;
  S.cases = cs.items;
  S.chapter = S.chapters[0]?.name || null;
  renderChapters();
  renderCases();
  renderProgress();
  if (S.cases.length) {
    const first = S.cases.find((c) => c.chapter === S.chapter) || S.cases[0];
    selectCase(first.id);
  }
}

function renderProgress() {
  const total = S.cases.length || 1;
  $('#pfill').style.width = (S.learned.size / total * 100).toFixed(1) + '%';
  $('#ptext').textContent = `${S.learned.size} / ${total}`;
}

function renderChapters() {
  $('#chCount').textContent = S.chapters.length + ' 章';
  $('#chapters').innerHTML = S.chapters.map((c) => `
    <div class="ch ${c.name === S.chapter ? 'on' : ''}" data-ch="${esc(c.name)}">
      <i class="dot"></i><span class="nm">${esc(c.name)}</span>
      <span class="ct">${c.count}</span>
    </div>`).join('');
  $('#chapters').querySelectorAll('.ch').forEach((el) => {
    el.onclick = () => {
      S.chapter = el.dataset.ch;
      renderChapters();
      renderCases();
      const first = S.cases.find((c) => c.chapter === S.chapter);
      if (first) selectCase(first.id);
    };
  });
}

function renderCases() {
  const q = ($('#q').value || '').trim().toLowerCase();
  const list = S.cases.filter((c) =>
    (!S.chapter || c.chapter === S.chapter) &&
    (!q || (c.title + c.id + c.body_part + c.modality).toLowerCase().includes(q)));
  $('#caseHead').textContent = `${S.chapter || '病例'} · ${list.length}`;
  $('#cases').innerHTML = list.map((c) => `
    <button class="case ${S.current?.case?.id === c.id ? 'on' : ''}" data-id="${c.id}">
      <span class="t">${esc(c.title)}</span>
      <span class="m">
        <span class="lv ${c.level === 'local' ? 'local' : ''}">${c.level === 'local' ? '图像内' : '解剖分区'}</span>
        <span>${esc(c.body_part)} · ${esc(c.modality)}</span>
        ${S.learned.has(c.id) ? '<span class="learned">✓ 已学</span>' : ''}
      </span>
    </button>`).join('') || '<div class="loading">该章节暂无病例</div>';
  $('#cases').querySelectorAll('.case').forEach((el) => {
    el.onclick = () => selectCase(el.dataset.id);
  });
}

/* ---------- 病例 ---------- */
async function selectCase(id) {
  try {
    const d = await api('/api/lesson/' + encodeURIComponent(id));
    S.lesson = d;
    S.current = d;
    S.activeRegion = null;
    S.quiz = null;
    renderStage();
    renderHead();
    const first = d.cards.find((c) => c.claim_status === 'dual') || d.cards[0] || null;
    S.activeRegion = first;
    renderLesson(first);
    if (first) {
      const el = document.querySelector(`.region[data-rid="${first.region_id}"]`);
      if (el) el.classList.add('on');
    }
    renderCases();
    $('#learnBtn').textContent = S.learned.has(id) ? '已标记已学' : '标记已学';
  } catch (e) {
    console.error(e);
  }
}

function renderHead() {
  const c = S.lesson.case;
  $('#caseTitle').textContent = c.title;
  $('#caseMeta').innerHTML = `
    <span>${esc(c.id)}</span>
    <span>${esc(c.body_part)}</span>
    <span>${esc(c.modality)}</span>
    <span>${S.lesson.cards.length} 个分区</span>
    <span>${esc(c.pose_class || '')}</span>`;
  const ev = c.evidence_level || 'C';
  $('#caseBadges').innerHTML = `
    <span class="bdg ${ev === 'B' ? 'b' : 'c'}">证据 ${ev}${ev === 'C' ? ' · 待复核' : ''}</span>
    <span class="bdg">${c.level === 'local' ? '图像内分区' : '解剖分区'}</span>
    <span class="bdg">双引用 ${S.lesson.gate.dual}</span>`;
  $('#srcLine').textContent = c.license ? `${c.license} · ${c.artist || ''}` : '';
  $('#srcLine').title = c.source_page || '';
}

function fitFrame() {
  const img = $('#img');
  const cv = $('#canvas');
  if (!img.naturalWidth || !cv) return;
  const W = cv.clientWidth - 6, H = cv.clientHeight - 6;
  const sc = Math.min(W / img.naturalWidth, H / img.naturalHeight, 1.4);
  const f = $('#frame');
  f.style.width = Math.round(img.naturalWidth * sc) + 'px';
  f.style.height = Math.round(img.naturalHeight * sc) + 'px';
  img.style.width = '100%';
  img.style.height = '100%';
}

function renderStage() {
  const c = S.lesson.case;
  const img = $('#img');
  img.onload = fitFrame;
  img.src = c.image;
  $('#empty').style.display = 'none';
  const ov = $('#overlay');
  ov.innerHTML = S.lesson.cards.map((r) => {
    const [x, y, w, h] = r.coords;
    const local = S.lesson.case.level === 'local';
    return `<div class="region ${local ? 'local' : ''} ${S.showRegion ? '' : 'hide'}"
      data-rid="${r.region_id}" data-name="${esc(r.name)}"
      style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%">
      <span class="tag">${esc(r.name)}</span></div>`;
  }).join('');
  ov.querySelectorAll('.region').forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      const card = S.lesson.cards.find((x) => x.region_id === el.dataset.rid);
      S.activeRegion = card;
      ov.querySelectorAll('.region').forEach((x) => x.classList.remove('on'));
      el.classList.add('on');
      renderLesson(card);
    };
  });
  if (S.activeRegion) {
    const el = ov.querySelector(`[data-rid="${S.activeRegion.region_id}"]`);
    if (el) el.classList.add('on');
  }
}

function renderLesson(card) {
  const body = $('#lessonBody');
  if (!card) {
    body.innerHTML = `<div class="placeholder">
      <b>选择一个分区</b>
      <p>分区不是病灶检测结果，而是教学用的解剖范围。每条讲解都带来源摘录。</p>
      <p style="margin-top:12px">本病例共 ${S.lesson.cards.length} 个分区，点影像上的彩色框即可展开。</p>
    </div>`;
    $('#sideTag').textContent = '—';
    return;
  }
  const sideMap = { right: '患者右侧', left: '患者左侧', midline: '中线', unknown: '侧别未知' };
  $('#sideTag').textContent = sideMap[card.patient_side] || '—';
  const st = card.claim_status;
  const stTxt = st === 'dual' ? '双引用成立' : st === 'single' ? '单引用（缺一侧锚点）' : '校验未通过';
  body.innerHTML = `
    <div class="lcard">
      <h3>${esc(card.name)}</h3>
      <div class="en">${esc(card.region_id)}</div>
      <div class="note">${esc(card.note)}</div>
    </div>

    <div class="sec">
      <div class="sec-t">库内关联征象</div>
      <div class="chips">${card.signs.map((s) => `<span class="chip">${esc(s.name)}</span>`).join('') || '<span class="chip">暂无</span>'}</div>
    </div>

    <div class="sec">
      <div class="sec-t">分区结论</div>
      <div class="quote plain">${esc(card.claim_text || '该分区暂无绑定结论。')}
        ${card.excerpt ? `<span class="who">${esc(card.doc_title)} · ${esc(card.locator)}</span>` : ''}
      </div>
    </div>

    ${card.excerpt ? `<div class="sec">
      <div class="sec-t">文献摘录（可核对）</div>
      <div class="quote">${esc(card.excerpt)}
        <span class="who"><a href="${esc(card.url)}" target="_blank" rel="noopener">打开来源 ↗</a></span>
      </div>
    </div>` : ''}

    <div class="state ${st}">
      <i></i><span class="txt">${stTxt}</span>
      <b>${st === 'dual' ? '空间 + 文献' : st === 'single' ? '仅一侧' : '已拦截'}</b>
    </div>`;
}

/* ---------- 自测 ---------- */
function startQuiz() {
  if (!S.lesson?.quiz?.length) return;
  S.quiz = S.lesson.quiz;
  S.quizIdx = 0;
  $('#quiz').classList.add('show');
  renderQuiz();
}

function renderQuiz() {
  const q = S.quiz[S.quizIdx];
  const body = $('#qBody');
  if (!q) {
    body.innerHTML = `<div class="q">本轮完成。</div>
      <p class="qexp">自测只检验分区与征象的对应关系，不代表临床判读能力。</p>
      <button class="solid qnext" onclick="closeQuiz()">关闭</button>`;
    return;
  }
  body.innerHTML = `
    <div class="q">${esc(q.prompt)}</div>
    <div id="opts">${q.options.map((o) => `<button class="opt" data-o="${esc(o)}">${esc(o)}</button>`).join('')}</div>
    <div class="qexp" id="qexp" style="display:none"></div>`;
  const target = document.querySelector(`.region[data-rid="${q.region_id}"]`);
  document.querySelectorAll('.region').forEach((x) => x.classList.remove('q-target'));
  if (target) target.classList.add('q-target');
  body.querySelectorAll('.opt').forEach((b) => {
    b.onclick = () => {
      const ok = b.dataset.o === q.answer;
      body.querySelectorAll('.opt').forEach((x) => {
        x.disabled = true;
        if (x.dataset.o === q.answer) x.classList.add('right');
      });
      if (!ok) b.classList.add('wrong');
      const exp = $('#qexp');
      exp.style.display = 'block';
      exp.innerHTML = `${ok ? '✓ 正确' : '✗ 再想想'} · ${esc(q.explain)}
        <div><button class="solid qnext" onclick="nextQuiz()">${S.quizIdx + 1 < S.quiz.length ? '下一题' : '完成'}</button></div>`;
    };
  });
}

function nextQuiz() {
  S.quizIdx += 1;
  renderQuiz();
}

function closeQuiz() {
  $('#quiz').classList.remove('show');
  document.querySelectorAll('.region').forEach((x) => x.classList.remove('q-target'));
}

/* ---------- 交互 ---------- */
$('#q').addEventListener('input', renderCases);
$('#prev').onclick = () => step(-1);
$('#next').onclick = () => step(1);
$('#toggleRegion').onclick = (e) => {
  S.showRegion = !S.showRegion;
  e.currentTarget.classList.toggle('on', S.showRegion);
  document.querySelectorAll('.region').forEach((x) => x.classList.toggle('hide', !S.showRegion));
};
$('#quizBtn').onclick = startQuiz;
$('#learnBtn').onclick = () => {
  const id = S.current?.case?.id;
  if (!id) return;
  if (S.learned.has(id)) S.learned.delete(id); else S.learned.add(id);
  localStorage.setItem('teach.learned', JSON.stringify([...S.learned]));
  renderProgress();
  renderCases();
  $('#learnBtn').textContent = S.learned.has(id) ? '已标记已学' : '标记已学';
};
$('#qClose').onclick = closeQuiz;
$('#quiz').addEventListener('click', (e) => { if (e.target.id === 'quiz') closeQuiz(); });

function step(d) {
  const list = S.cases.filter((c) => c.chapter === S.chapter);
  const i = list.findIndex((c) => c.id === S.current?.case?.id);
  const n = list[i + d];
  if (n) selectCase(n.id);
}

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'ArrowLeft') step(-1);
  if (e.key === 'ArrowRight') step(1);
  if (e.key === 'Escape') closeQuiz();
  if (e.key === 'g' || e.key === 'G') $('#toggleRegion').click();
});

window.addEventListener('resize', fitFrame);
init();
