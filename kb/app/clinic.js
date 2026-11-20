/* 临床版：队列 → 框选定位 → 空间/文献双锚点 → 审计 */
const S = {
  cases: [], filter: { q: '', level: '' }, current: null,
  detail: null, selected: null, showRegion: true, zoom: 1, tab: 'locate',
  drag: null, audit: null,
  /* /api/health 探测到的模型能力：text 有值才把纯文本问答切到直连模型 */
  models: {}, agentReady: false,
  /* 上传影像问答：image 是 data URL，match 是后端返回的认图结果 */
  chat: {
    q: '', text: '', cites: [], image: null, match: null, state: 'idle', err: '',
    trace: [], tools: [], followups: [], servedBy: null, degraded: false,
    reason: '', runId: null, literature: null, template: null, tmplErr: '',
    atlases: [], matchBBox: null,
  },
  locate: null,
};
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const SIDE = { right: '患者右侧', left: '患者左侧', midline: '中线', unknown: '侧别未知' };

async function api(path, opt) {
  /* 静态托管：/api/* 映射到预生成 JSON（kb/scripts/export_teach_static.py） */
  const mapped = window.YZStatic && path.startsWith('/api/') ? window.YZStatic.path(path) : null;
  if (mapped) {
    const r = await fetch(mapped, opt);
    if (!r.ok) throw new Error(mapped + ' ' + r.status);
    return JSON.parse(window.YZStatic.fixImages(await r.text()));
  }
  const r = await fetch(path, opt);
  if (!r.ok) throw new Error(path + ' ' + r.status);
  return r.json();
}

/* ---------- 初始化 ---------- */
async function init() {
  const [cs, meta] = await Promise.all([api('/api/cases'), api('/api/meta')]);
  S.cases = cs.items;
  $('#gDual').textContent = meta.gate.dual;
  $('#gSingle').textContent = meta.gate.single;
  $('#gBroken').textContent = meta.gate.broken;
  $('#total').textContent = meta.counts.cases;
  $('#locatable').textContent = meta.counts.locatable_cases;
  renderRows();
  const want = (window.YZCommon && window.YZCommon.query('case')) || '';
  const first = S.cases.find((c) => c.id === want) || S.cases[0];
  if (first) selectCase(first.id);
}

/* 探测后端模型能力：有文本模型就把纯文本问答切到直连模型（快），
   没有就继续走 agent，行为与之前一致。失败不影响页面。 */
async function initModels() {
  if (!HAS_BACKEND) return;
  try {
    const h = await api('/api/health');
    S.models = (h && h.llm_route) || {};
    S.agentReady = !!(h && h.agent_ready);
  } catch (e) {
    S.models = {};
  }
}

/* 命题三步：选片 → 定位 → 溯源 */
function setStep(name, on, hint) {
  const map = { case: 'stepCase', locate: 'stepLocate', trace: 'stepTrace' };
  const el = document.getElementById(map[name]);
  if (el) el.classList.toggle('on', !!on);
  if (hint) {
    const h = document.getElementById('flowHint');
    if (h) h.textContent = hint;
  }
}

function renderRows() {
  const { q, level } = S.filter;
  const list = S.cases.filter((c) => {
    const hay = (c.id + c.title + c.body_part + c.modality + (c.chapter || '') + (c.pose_class || '')).toLowerCase();
    return (!q || hay.includes(q)) && (!level || c.evidence_level === level);
  });
  $('#listCount').textContent = list.length;
  $('#rows').innerHTML = list.map((c) => `
    <div class="row ${S.current?.id === c.id ? 'on' : ''}" data-id="${c.id}">
      <span class="id">${esc(c.id.replace('CASE-', ''))}</span>
      <span class="bp" title="${esc(c.title)}">${esc(c.body_part)} · ${esc(c.modality)}</span>
      <span class="n">${c.region_count}</span>
      <span class="n">${c.dual_count}</span>
      <span class="ev ${c.evidence_level}">${c.evidence_level}</span>
    </div>`).join('') || '<div class="empty">无匹配病例</div>';
  $('#rows').querySelectorAll('.row').forEach((el) => {
    el.onclick = () => selectCase(el.dataset.id);
  });
}

/* ---------- 病例 ---------- */
async function selectCase(id) {
  try {
    const d = await api('/api/cases/' + encodeURIComponent(id));
    S.detail = d;
    S.current = d.case;
    S.selected = null;
    $('#title').textContent = d.case.title;
    $('#sub').innerHTML = `
      <span>${esc(d.case.id)}</span><span>${esc(d.case.body_part)}</span>
      <span>${esc(d.case.modality)}</span><span>${d.regions.length} 分区</span>
      <span>${d.claims.length} 结论</span>`;
    $('#posePill').textContent = d.case.pose_class || '—';
    $('#atlasPill').textContent = d.atlas ? d.atlas.name : '—';
    $('#srcLine').textContent = d.case.source_page || '—';
    $('#licLine').textContent = d.case.license ? `${d.case.license} · ${d.case.artist || ''}` : '—';
    $('#evCount').textContent = d.claims.length;
    renderStage();
    renderRows();
    setStep('case', true, '已选影像 · 在图上拖框，或点右侧分区');
    setStep('locate', false);
    setStep('trace', false);
    if (S.tab === 'audit') loadAudit();
    else renderTab();
  } catch (e) { console.error(e); }
}

function fitFrame() {
  const img = $('#img');
  const st = $('#stage');
  if (!img.naturalWidth || !st) return;
  const W = st.clientWidth - 6, H = st.clientHeight - 6;
  const sc = Math.min(W / img.naturalWidth, H / img.naturalHeight, 1.4);
  const f = $('#frame');
  f.style.width = Math.round(img.naturalWidth * sc) + 'px';
  f.style.height = Math.round(img.naturalHeight * sc) + 'px';
  img.style.width = '100%';
  img.style.height = '100%';
}

function renderStage() {
  const d = S.detail;
  const img = $('#img');
  img.onload = fitFrame;
  img.src = d.case.image;
  $('#stageEmpty').style.display = 'none';
  const ov = $('#overlay');
  ov.innerHTML = d.regions.map((r) => {
    const [x, y, w, h] = r.coords;
    return `<div class="region ${d.case.level === 'local' ? 'local' : ''} ${S.showRegion ? '' : 'hide'}"
      data-rid="${r.id}" style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%">
      <span class="tag">${esc(r.name)}</span></div>`;
  }).join('');
  ov.querySelectorAll('.region').forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      const r = d.regions.find((x) => x.id === el.dataset.rid);
      pickRegion(r);
    };
  });
  applyZoom();
  if (S.selected) {
    const el = ov.querySelector(`[data-rid="${S.selected.id}"]`);
    if (el) el.classList.add('on');
  }
}

function pickRegion(r) {
  S.selected = r;
  document.querySelectorAll('.region').forEach((x) => x.classList.remove('on', 'hit', 'cand'));
  const el = document.querySelector(`.region[data-rid="${r.id}"]`);
  if (el) el.classList.add('on');
  const claim = (S.detail?.claims || []).find((c) => c.region_id === r.id);
  setStep('locate', true);
  setStep('trace', !!claim, claim ? '已命中分区 · 右侧给出空间 + 文献双锚点' : '已命中分区 · 该分区暂无绑定结论');
  S.tab = 'evidence';
  document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('on', b.dataset.t === 'evidence'));
  renderTab();
}

/* ---------- 框选 ---------- */
const frame = $('#frame');
frame.addEventListener('mousedown', (e) => {
  if (!S.detail && !(S.chat && S.chat.image)) return;
  if (e.shiftKey) return;
  const rect = frame.getBoundingClientRect();
  S.drag = {
    x0: (e.clientX - rect.left) / rect.width,
    y0: (e.clientY - rect.top) / rect.height,
    rect,
  };
  const b = $('#selbox');
  b.style.display = 'block';
  b.style.left = S.drag.x0 * 100 + '%';
  b.style.top = S.drag.y0 * 100 + '%';
  b.style.width = '0';
  b.style.height = '0';
  e.preventDefault();
});
window.addEventListener('mousemove', (e) => {
  if (!S.drag) return;
  const { rect, x0, y0 } = S.drag;
  const x1 = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const y1 = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
  const b = $('#selbox');
  b.style.left = Math.min(x0, x1) * 100 + '%';
  b.style.top = Math.min(y0, y1) * 100 + '%';
  b.style.width = Math.abs(x1 - x0) * 100 + '%';
  b.style.height = Math.abs(y1 - y0) * 100 + '%';
});
window.addEventListener('mouseup', async (e) => {
  if (!S.drag) return;
  const { rect, x0, y0 } = S.drag;
  const x1 = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const y1 = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
  S.drag = null;
  $('#selbox').style.display = 'none';
  const bbox = [Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0)];
  if (bbox[2] < 0.01 || bbox[3] < 0.01) return;
  $('#bboxMeta').textContent = bbox.map((v) => v.toFixed(3)).join(' , ');
  if (!S.current || !S.detail) {
    // 陌生影像没有逐病例标注：记录框，让用户选模板后走 /api/vision/region。
    S.chat.match = S.chat.match || { case_id: null };
    S.chat.matchBBox = bbox;
    S.chat.template = null;
    S.tab = 'chat';
    document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('on', b.dataset.t === 'chat'));
    await loadAtlases();
    renderTab();
    toast('陌生影像：选一个分区模板后点「推断」');
    return;
  }
  try {
    const res = window.YZLocate
      ? window.YZLocate.locate(S.detail.regions, bbox)
      : await api('/api/locate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_id: S.current.id, bbox }),
      });
    handleLocate(res);
  } catch (err) { toast('定位请求失败'); }
});

function handleLocate(res, opt) {
  const switchTab = !opt || opt.switchTab !== false;
  document.querySelectorAll('.region').forEach((x) => x.classList.remove('on', 'hit', 'cand'));
  $('#selbox').classList.remove('model');
  if (res.status === 'single' && res.primary) {
    const r = res.primary.region;
    S.selected = r;
    const el = document.querySelector(`.region[data-rid="${r.id}"]`);
    if (el) el.classList.add('hit');
    if (switchTab) {
      S.tab = 'evidence';
      document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('on', b.dataset.t === 'evidence'));
      renderTab();
    }
    setStep('locate', true);
    setStep('trace', true, '框选命中 · 右侧为空间 + 文献双锚点');
    toast(`命中 ${r.name} · 覆盖 ${(res.primary.coverage * 100).toFixed(0)}%`);
  } else if (res.status === 'cross' && res.candidates) {
    res.candidates.forEach((c) => {
      const el = document.querySelector(`.region[data-rid="${c.region.id}"]`);
      if (el) el.classList.add('cand');
    });
    toast(res.message);
  } else {
    toast(res.message || '未命中分区');
  }
}

/* ---------- 右侧 Tab ---------- */
function renderTab() {
  const body = $('#tabBody');
  if (S.tab === 'locate') return renderLocate(body);
  if (S.tab === 'chat') return renderChat(body);
  if (S.tab === 'evidence') return renderEvidence(body);
  if (S.tab === 'audit') return loadAudit();
}

function renderLocate(body) {
  const d = S.detail;
  if (!d) { body.innerHTML = '<div class="empty">选择病例开始</div>'; return; }
  const ev = d.case.evidence_level;
  body.innerHTML = `
    <div class="status dual"><i></i><span>本病例双引用 ${d.gate.dual} · 单引用 ${d.gate.single} · 拦截 ${d.gate.broken}</span><b>${ev}</b></div>
    <div class="sect">病例</div>
    <dl class="kv">
      <dt>编号</dt><dd class="mono">${esc(d.case.id)}</dd>
      <dt>部位</dt><dd>${esc(d.case.body_part)}</dd>
      <dt>体位</dt><dd class="mono">${esc(d.case.pose_class || '—')}</dd>
      <dt>定位级</dt><dd>${d.case.level === 'local' ? '图像内相对位置' : '解剖分区'}</dd>
      <dt>证据等级</dt><dd>${ev}${ev === 'C' ? ' · 自动定位待复核' : ' · 人工复核'}</dd>
      <dt>许可</dt><dd>${esc(d.case.license || '—')}</dd>
    </dl>
    <div class="sect">分区（${d.regions.length}）</div>
    ${d.regions.map((r) => `
      <div class="rcard" data-rid="${r.id}" style="cursor:pointer">
        <div class="h"><b>${esc(r.name)}</b><span class="side">${esc(SIDE[r.patient_side] || r.patient_side || '—')}</span></div>
        <div class="n">${esc(r.note)}</div>
        <div class="sig">${(r.signs || []).map((s) => `<span>${esc(s.name)}</span>`).join('')}</div>
      </div>`).join('')}`;
  body.querySelectorAll('.rcard').forEach((el) => {
    el.onclick = () => {
      const r = d.regions.find((x) => x.id === el.dataset.rid);
      pickRegion(r);
    };
  });
}

function renderEvidence(body) {
  const d = S.detail;
  let r = S.selected;
  if (!d) { body.innerHTML = '<div class="empty">选择病例开始</div>'; return; }
  if (!r && d.claims.length) {
    const c0 = d.claims[0];
    r = d.regions.find((x) => x.id === c0.region_id) || null;
    if (r) {
      S.selected = r;
      const el = document.querySelector(`.region[data-rid="${r.id}"]`);
      if (el) el.classList.add('on');
    }
  }
  if (!r) {
    body.innerHTML = `<div class="empty"><b>尚未选择分区</b>
      在影像上拖框，或点右侧分区列表，系统会给出空间锚点与文献锚点，并逐项校验。</div>`;
    return;
  }
  const claim = d.claims.find((c) => c.region_id === r.id);
  if (!claim) {
    body.innerHTML = `<div class="empty"><b>${esc(r.name)}</b>该分区暂无绑定结论。</div>`;
    return;
  }
  const sp = claim.spatial, dc = claim.doc;
  const st = claim.status;
  const stTxt = st === 'dual' ? '双引用成立' : st === 'single' ? '单引用（缺一侧锚点）' : '校验未通过';
  body.innerHTML = `
    <div class="status ${st}"><i></i><span>${stTxt}</span><b>${esc(claim.id)}</b></div>
    <div class="sect">结论</div>
    <div class="cite">${esc(claim.text)}
      <span class="hash">${esc(claim.disclaimer || '')}</span></div>

    <div class="sect">空间锚点</div>
    ${sp ? `<div class="cite sp">
      <span class="lab">SPATIAL · ${esc(sp.cite_id)}</span>
      ${esc(sp.anchor.image_id)} · ${esc(sp.anchor.region_id)}<br>
      bbox ${sp.anchor.bbox.map((v) => v.toFixed(3)).join(' , ')}<br>
      atlas ${esc(sp.anchor.atlas_id)} · ${esc(sp.anchor.annotator || '')}
    </div>` : '<div class="prob">缺少空间锚点</div>'}

    <div class="sect">文献锚点</div>
    ${dc ? `<div class="cite dc">
      <span class="lab">DOC · ${esc(dc.cite_id)}</span>
      ${esc(dc.anchor.doc_title)} · ${esc(dc.anchor.version)}<br>
      <span style="color:var(--muted)">${esc(dc.anchor.locator)}</span><br><br>
      ${esc(dc.anchor.excerpt)}<br>
      <a href="${esc(dc.anchor.url)}" target="_blank" rel="noopener">打开来源 ↗</a>
      <div class="hash"><span>sha256</span><span>${esc(dc.anchor.excerpt_sha256)}</span>
        <span class="${(claim.gate.problems || []).some((p) => p.code === 'excerpt_mismatch') ? 'bad' : 'ok'}">
        ${(claim.gate.problems || []).some((p) => p.code === 'excerpt_mismatch') ? '✗ 不一致' : '✓ 一致'}</span></div>
    </div>` : '<div class="prob">缺少文献锚点</div>'}

    ${(claim.gate.problems || []).length ? `<div class="sect">门禁问题</div>
      ${claim.gate.problems.map((p) => `<div class="prob">${esc(p.code)} · ${esc(p.message)}</div>`).join('')}` : ''}

    <div class="sect">该分区关联征象</div>
    <div class="rcard"><div class="sig">${(r.signs || []).map((s) => `<span>${esc(s.name)}</span>`).join('')}</div></div>`;
}

async function loadAudit() {
  const body = $('#tabBody');
  body.innerHTML = '<div class="empty">加载审计…</div>';
  try {
    const d = await api('/api/audit');
    S.audit = d;
    const rows = d.items.slice(0, 400);
    body.innerHTML = `
      <div class="status dual"><i></i><span>全量 ${d.items.length} 条 · 双引用 ${d.gate.dual} · 单引用 ${d.gate.single} · 拦截 ${d.gate.broken}</span></div>
      <table class="audit">
        <thead><tr><th>ID</th><th>图</th><th>状态</th><th>文献</th><th>问题</th></tr></thead>
        <tbody>${rows.map((x) => `<tr>
          <td>${esc(x.claim_id)}</td>
          <td>${esc(x.image_id.replace('CASE-', ''))}</td>
          <td><span class="st ${x.status}">${x.status}</span></td>
          <td>${esc((x.doc_anchor || '—').slice(0, 22))}</td>
          <td>${x.problems.length ? esc(x.problems.map((p) => p.code).join(',')) : '—'}</td>
        </tr>`).join('')}</tbody>
      </table>`;
  } catch (e) { body.innerHTML = '<div class="empty">审计加载失败</div>'; }
}

/* ---------- 工具 ---------- */
function applyZoom() {
  const f = $('#frame');
  f.style.transform = `scale(${S.zoom})`;
  f.style.transformOrigin = 'center center';
  $('#zoomBadge').textContent = Math.round(S.zoom * 100) + '%';
}
$('#zoomIn').onclick = () => { S.zoom = Math.min(3, S.zoom + 0.25); applyZoom(); };
$('#zoomOut').onclick = () => { S.zoom = Math.max(0.5, S.zoom - 0.25); applyZoom(); };
$('#zoomReset').onclick = () => { S.zoom = 1; applyZoom(); };
$('#fit').onclick = () => { S.zoom = 1; applyZoom(); };
$('#regionToggle').onclick = (e) => {
  S.showRegion = !S.showRegion;
  e.currentTarget.classList.toggle('on', S.showRegion);
  document.querySelectorAll('.region').forEach((x) => x.classList.toggle('hide', !S.showRegion));
};
$('#clear').onclick = () => {
  S.selected = null;
  document.querySelectorAll('.region').forEach((x) => x.classList.remove('on', 'hit', 'cand'));
  $('#bboxMeta').textContent = '—';
  S.tab = 'locate';
  document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('on', b.dataset.t === 'locate'));
  renderTab();
};

let toastTimer;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

/* ---------- 事件 ---------- */
$('#q').addEventListener('input', (e) => { S.filter.q = e.target.value.trim().toLowerCase(); renderRows(); });
$('#levelSeg').querySelectorAll('button').forEach((b) => {
  b.onclick = () => {
    $('#levelSeg').querySelectorAll('button').forEach((x) => x.classList.remove('on'));
    b.classList.add('on');
    S.filter.level = b.dataset.l;
    renderRows();
  };
});
document.querySelectorAll('.tabs button').forEach((b) => {
  b.onclick = () => {
    S.tab = b.dataset.t;
    document.querySelectorAll('.tabs button').forEach((x) => x.classList.toggle('on', x === b));
    renderTab();
  };
});


/* ---------- 上传影像问答 ---------- */
/* 静态托管版没有模型服务。上传按钮给出明确提示，而不是假装能用。 */
const HAS_BACKEND = !window.YZStatic;

function readAsDataURL(file) {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result || ''));
    fr.onerror = () => rej(new Error('读取文件失败'));
    fr.readAsDataURL(file);
  });
}

/* 五段 trace 的固定顺序；运行期与收尾会各发一次，按 stage 覆盖而不是追加。 */
const TRACE_ORDER = [
  ['kb_retrieve', '检索'], ['skill_invoke', '技能'], ['workflow', '工作流'],
  ['agent_generate', '生成'], ['persist', '落盘'],
];

function traceMap(c) {
  const m = {};
  (c.trace || []).forEach((s) => { if (s && s.stage) m[s.stage] = s; });
  return m;
}

function traceHTML(c) {
  const m = traceMap(c);
  return TRACE_ORDER.map(([k, label]) => {
    const s = m[k] || {};
    const cls = s.status === 'completed' ? 'done'
      : s.status === 'error' ? 'err'
        : s.status === 'degraded' ? 'warn'
          : s.status === 'unavailable' || s.status === 'skipped' ? 'off' : '';
    const text = s.skill && s.skill !== 'none' ? s.skill : label;
    return `<span class="yz-step ${cls}">${esc(text)}${s.ms ? `<i>${s.ms}ms</i>` : ''}</span>`;
  }).join('<span class="yz-step-sep">›</span>');
}

function toolsHTML(c) {
  const rows = c.tools || [];
  if (!rows.length) return '';
  return `<div class="yz-tools">${rows.map((t) => `
    <div class="yz-tool ${t.status === 'error' ? 'err' : ''}">
      <b>${esc(t.skill || t.tool || 'tool')}</b>
      <span>${esc(t.detail || '')}</span>
      <i>${t.out_lines ? t.out_lines + ' 行 · ' : ''}${t.ms || 0}ms</i>
    </div>`).join('')}</div>`;
}

function paintTrace(c) {
  const el = document.querySelector('#askTrace');
  if (el) el.innerHTML = traceHTML(c);
  const tools = document.querySelector('#askTools');
  if (tools) tools.innerHTML = toolsHTML(c);
}

/* 把当前定位结果作为「页面上下文」带给 agent：
   只帮助定位（哪一例、哪个分区、视觉看到了什么），
   服务端明确把它当定位信息、不当库内证据，也不参与引用打分。 */
function askContext(prevMatch) {
  const c = S.chat || {};
  const t = c.template || null;
  const m = prevMatch || c.match || null;
  const ctx = {};
  if (m && m.case_id) ctx.case_id = m.case_id;
  if (t && t.atlas) {
    ctx.atlas = t.atlas.name || t.atlas.id || '';
    ctx.region_source = 'atlas_template';
    const p = (t.locate && t.locate.primary) || null;
    if (p && p.region) ctx.region = p.region.name;
  }
  if (t && t.vision) {
    const v = t.vision;
    if (v.modality) ctx.modality = v.modality;
    if (v.body_part) ctx.body_part = v.body_part;
    if (v.view) ctx.view = v.view;
    if (Array.isArray(v.findings) && v.findings.length) {
      ctx.vision_findings = v.findings.slice(0, 4).join('；');
    }
  }
  return Object.keys(ctx).length ? ctx : undefined;
}

async function sendAsk(q, opts) {
  q = (q || '').trim();
  if (!q) return;
  if (!HAS_BACKEND) { toast('公网版不含 Agent 服务，请在本地运行后使用'); return; }
  const forceAgent = !!(opts && opts.forceAgent);
  const c = S.chat;
  const prevMatch = c.match;   // 重置会清掉 match，但定位信息仍要带给本轮
  Object.assign(c, {
    q, text: '', cites: [], match: null, err: '', state: 'run',
    trace: [], tools: [], followups: [], servedBy: null,
    degraded: false, reason: '', runId: null,
  });
  S.locate = null;
  S.tab = 'chat';
  document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('on', b.dataset.t === 'chat'));
  renderTab();
  try {
    // 纯文本且有文本模型 → 直连模型，省掉 agent 的十几秒；
    // 带图或没有模型 → 交给 auto（视觉定位 + agent 解释）。
    // 有对应模型就走直连：纯文本看 text 模型，带图看 vision 模型。
    // 两者都没有才退回 auto（agent）。
    const direct = !forceAgent && S.models
      && (c.image ? S.models.vision : S.models.text);
    const res = await window.YZAgent.ask({
      query: q,
      image: c.image || undefined,
      role: 'student',
      device: 'desktop',
      chain: 'clinic_upload',
      surface: 'clinic',
      research: true,
      mode: direct ? 'llm' : 'auto',
      context: askContext(prevMatch),
    }, {
      onEvent(ev, d) {
        if (ev === 'delta') {
          c.text += d.text || '';
          // 增量只改文字节点，不重建 DOM，否则输入框每帧失焦
          const out = document.querySelector('#askOut');
          if (out) out.textContent = c.text;
        } else if (ev === 'trace') {
          c.trace.push(d);
          paintTrace(c);
        } else if (ev === 'tool') {
          c.tools.push(d);
          paintTrace(c);
        } else if (ev === 'reset') {
          c.text = '';
          const out = document.querySelector('#askOut');
          if (out) out.textContent = '';
        }
      },
    });
    c.text = res.text || c.text;
    c.cites = res.cites || [];
    c.literature = (res.done && res.done.literature) || null;
    c.ungrounded = !!(res.done && res.done.ungrounded);
    c.trace = res.trace || c.trace;
    c.tools = res.tools || c.tools;
    c.followups = res.followups || [];
    c.servedBy = res.servedBy;
    c.degraded = res.degraded;
    c.reason = (res.done && res.done.reason) || '';
    c.runId = (res.done && res.done.run_id) || null;
    c.match = (res.done && res.done.image_match) || null;
    c.state = 'done';
    // 直连模型失败（余额不足 / 网络 / 超时）会落到本地模板，质量明显下降。
    // 此时自动用 agent 重答一次；只重试一次，避免来回打转。
    if (direct && c.servedBy === 'fallback' && S.agentReady) {
      const why = (c.reason || '').slice(0, 80);
      toast('直连模型不可用，改用 Agent 重答' + (why ? '：' + why : ''));
      return sendAsk(q, { forceAgent: true });
    }
  } catch (e) {
    c.state = 'error';
    c.err = (e && e.message) || String(e);
  }
  if (S.tab === 'chat') renderTab();
  await applyImageMatch();
}

/* 后端只负责认图和给框，落到哪个分区由前端 locate 算，和拖框走同一套算法。 */
async function applyImageMatch() {
  const m = S.chat.match;
  if (!m) return;
  if (!m.case_id) {
    // 认不出不等于死路：先给出库内可练的片子；有候选框时再让用户选模板做推断。
    S.chat.suggest = m.suggest || [];
    // 保留用户先前手动框选的框：模型没给框时不该把用户的框清掉。
    S.chat.matchBBox = m.bbox || S.chat.matchBBox || null;
    S.chat.template = null;
    S.chat.tmplErr = '';
    if (S.chat.matchBBox) {
      await loadAtlases();
    } else {
      toast('该影像不在标注库内，模型也未给出候选框；请手动框选后按模板推断');
    }
    if (S.tab === 'chat') renderTab();
    return;
  }
  if (!m.bbox) { toast('模型未给出候选框，无法落到分区'); return; }
  if (!S.current || S.current.id !== m.case_id) await selectCase(m.case_id);
  if (!S.detail) return;
  drawBBox(m.bbox);
  let res;
  try {
    res = window.YZLocate
      ? window.YZLocate.locate(S.detail.regions, m.bbox)
      : await api('/api/locate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_id: m.case_id, bbox: m.bbox }),
      });
  } catch (e) { toast('定位失败'); return; }
  S.locate = res;
  handleLocate(res, { switchTab: false });
  if (S.tab === 'chat') renderTab();
}

async function loadAtlases() {
  if ((S.chat.atlases || []).length) return;
  try {
    const r = await fetch('/api/vision/atlases');
    const j = await r.json();
    S.chat.atlases = (j && j.atlases) || [];
  } catch (e) {
    S.chat.tmplErr = '模板列表加载失败';
  }
  if (S.tab === 'chat') renderTab();
}

async function runTemplate() {
  const sel = document.querySelector('#atlasPick');
  const atlasId = sel && sel.value;
  if (!atlasId) { toast('请先选一个分区模板'); return; }
  const bbox = S.chat.matchBBox;
  if (!bbox) { toast('没有候选框，无法按模板推断'); return; }
  try {
    const r = await fetch('/api/vision/region', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ atlas_id: atlasId, bbox }),
    });
    const j = await r.json();
    if (!j || !j.ok) {
      S.chat.tmplErr = (j && j.message) || '模板推断失败';
    } else {
      S.chat.template = j;
      S.chat.tmplErr = '';
    }
  } catch (e) {
    S.chat.tmplErr = (e && e.message) || String(e);
  }
  if (S.tab === 'chat') renderTab();
}

function drawBBox(b) {
  const el = $('#selbox');
  el.style.display = 'block';
  el.style.left = b[0] * 100 + '%';
  el.style.top = b[1] * 100 + '%';
  el.style.width = b[2] * 100 + '%';
  el.style.height = b[3] * 100 + '%';
  el.classList.add('model');
}

function showUploaded(dataUrl) {
  S.detail = null; S.current = null; S.selected = null; S.locate = null;
  const img = $('#img');
  img.onload = fitFrame;
  img.src = dataUrl;
  $('#overlay').innerHTML = '';
  $('#selbox').style.display = 'none';
  $('#selbox').classList.remove('model');
  $('#stageEmpty').style.display = 'none';
  $('#title').textContent = '上传影像';
  $('#sub').textContent = '待模型返回候选框后再匹配分区';
  $('#posePill').textContent = '—';
  $('#atlasPill').textContent = '—';
  $('#srcLine').textContent = '本地影像 · 未入库';
  $('#licLine').textContent = '—';
  $('#bboxMeta').textContent = '—';
  renderRows();
  applyZoom();
}

function chatLocateLine(c) {
  const m = c.match;
  if (!m) return '';
  if (!m.case_id) {
    if (c.template) return '';
    return '<div class="sect">区域定位</div><div class="prob">该影像不在标注库内，未做逐病例标注；可在上方选模板做「模板推断」，结果不冒充人工标注</div>';
  }
  const id = m.case_id.replace('CASE-', '');
  const ids = (m.case_ids && m.case_ids.length) ? m.case_ids : [m.case_id];
  const others = ids.filter((x) => x !== m.case_id).map((x) => x.replace('CASE-', ''));
  // 同一张图被多例共用时必须说明，否则用户会以为「这张图只属于这一例」
  const shared = others.length
    ? `<br><span style="color:var(--muted)">同图另有 ${others.length} 例共用：${esc(others.join(' / '))}（当前按 ${esc(id)} 的分区展示）</span>`
    : '';
  if (!m.bbox) {
    return `<div class="sect">区域定位</div><div class="prob">识别为病例 ${esc(id)}，但模型未给出候选框${shared}</div>`;
  }
  const lr = S.locate;
  const tail = lr && lr.status === 'single'
    ? `命中 ${esc(lr.primary.region.name)} · 覆盖 ${(lr.primary.coverage * 100).toFixed(0)}%`
    : (lr ? esc(lr.message || '未命中分区') : '已识别');
  return `<div class="sect">区域定位</div>
    <div class="cite"><span class="lab">MATCH</span>病例 ${esc(id)}<br>
    bbox ${m.bbox.map((v) => v.toFixed(3)).join(' , ')}<br>${tail}${shared}</div>`;
}

function templateCard(t) {
  const l = t.locate || {};
  const atlas = t.atlas || {};
  const p = (l.primary && l.primary.region) || null;
  const cands = l.candidates || [];
  const head = p ? p.name : (cands[0] && cands[0].region && cands[0].region.name) || '未命中分区';
  const detail = p
    ? `覆盖 ${(p.coverage === undefined ? l.primary.coverage * 100 : p.coverage * 100).toFixed(0)}% · 模板一致度 ${l.primary.agreement} · 样本 ${l.primary.template_n} 例`
    : (l.message || '');
  return `<div class="yz-tmplcard">
    <b>${esc(head)}</b> · ${esc(atlas.name || '')}<br>
    ${esc(detail)}<br>
    <span class="yz-src">模板推断 · 非人工标注</span>
  </div>`;
}

function renderChat(body) {
  const c = S.chat || {};
  const run = c.state === 'run';
  const localCites = (c.cites || []).filter((x) => x.kind !== 'literature');
  const litCites = (c.cites || []).filter((x) => x.kind === 'literature');
  const lit = c.literature || null;
  const badge = c.servedBy === 'agent' ? 'Agent'
    : c.servedBy === 'llm' ? '直连模型'
      : c.servedBy === 'fallback' ? '本地兜底' : '';
  body.innerHTML = `
    <div class="sect">影像</div>
    <div class="askmeta">${c.image
      ? '已载入 · 先视觉定位，再由 Agent 解释与引用'
      : '未载入 · 文本问答（可先点工具栏「上传影像」）'}</div>
    <div class="sect">提问</div>
    <div class="askbar">
      <input id="askInput" placeholder="问这张影像，或问某个征象…" value="${esc(c.q || '')}" ${run ? 'disabled' : ''}>
      <button id="askSend" ${run ? 'disabled' : ''}>${run ? '生成中' : '提问'}</button>
    </div>
    ${c.err ? `<div class="prob">${esc(c.err)}</div>` : ''}
    <div class="yz-steps" id="askTrace" ${((c.trace || []).length || run) ? '' : 'hidden'}>${traceHTML(c)}</div>
    <div id="askTools">${toolsHTML(c)}</div>
    ${c.degraded ? `<div class="prob">本轮已降级：${esc(c.reason || 'Agent 不可用')}。回答来自${esc(badge || '兜底链路')}，不是 Agent 结果。</div>` : ''}
    ${c.servedBy ? `<div class="askmeta">
      <span class="yz-badge ${c.degraded ? 'warn' : ''}">${esc(badge)}</span>
      ${c.runId ? `<a href="/api/trace/${esc(c.runId)}" target="_blank" rel="noopener">trace ↗</a>` : ''}
      <button class="linkbtn" id="askReset">重置会话</button>
    </div>` : ''}
    ${c.match && !c.match.case_id && c.matchBBox ? `
      <div class="sect">按模板推断分区</div>
      <div class="askmeta">这张图不在标注库内。选一个分区模板，系统按模板几何推断分区；结果是模板推断，不是人工标注。</div>
      <div class="yz-template">
        <select id="atlasPick">
          <option value="">选择检查类型 / 部位</option>
          ${(c.atlases || []).map((a) => `<option value="${esc(a.id)}">${esc(a.name)} · ${esc(a.view || (a.modality || []).join('/'))} · ${a.n_cases} 例</option>`).join('')}
        </select>
        <button id="atlasGo">推断</button>
      </div>
      ${c.template ? templateCard(c.template) : ''}
      ${c.tmplErr ? `<div class="prob">${esc(c.tmplErr)}</div>` : ''}
    ` : ''}
    ${(c.suggest || []).length ? `
      <div class="sect">库内可练的片子</div>
      <div class="askmeta">这张图不在标注库内，所以没有区域定位。下面是库里已标注的病例，可以直接切过去。</div>
      <div class="suggrid">${c.suggest.map((s) => `
        <button class="sug" data-id="${esc(s.id)}">
          <img src="${esc(s.image)}" alt="" loading="lazy">
          <span>${esc(s.id)}<i>${esc(s.chapter)}</i></span>
        </button>`).join('')}</div>` : ''}
    <div class="sect">回答</div>
    <div class="cite answer" id="askOut">${esc(c.text)}</div>
    ${c.ungrounded ? '<div class="prob">本次回答没有库内引用，内容未与知识库核对，请谨慎使用</div>' : ''}
    ${localCites.length ? `<div class="sect">库内证据 ${localCites.length}</div><div class="yz-cites">${localCites.map((x) => `
      <button class="yz-cite" data-cite="${esc(x.id)}">
        <b>${esc(x.id)}</b><span>${esc(x.title || '')}</span>
        ${x.relevance === 'off' ? '<i class="yz-weak">弱相关</i>' : ''}
      </button>`).join('')}</div>` : ''}
    ${litCites.length ? `<div class="sect">网络文献 ${litCites.length}<span class="yz-src">PubMed 检索</span></div>
      <div class="yz-lit">${litCites.map((x) => `
        <a class="yz-litcard" href="${esc(x.url || '#')}" target="_blank" rel="noopener">
          <b>${esc(x.id)}</b>
          <span class="t">${esc(x.title || '')}</span>
          <span class="m">${esc([x.journal, x.year].filter(Boolean).join(' · '))}</span>
        </a>`).join('')}</div>` : ''}
    ${lit && lit.ok === false && lit.reason && lit.reason !== 'not_requested'
      ? `<div class="prob">文献检索未完成：${esc(lit.reason === 'no_english_term' ? '没有匹配到库内英文术语，无法检索 PubMed' : lit.reason)}</div>`
      : ''}
    ${(c.followups || []).length ? `<div class="sect">继续问</div><div class="yz-follow">${c.followups.map((x) => `
      <button data-follow="${esc(x)}">${esc(x)}</button>`).join('')}</div>` : ''}
    ${chatLocateLine(c)}
  `;
  const inp = body.querySelector('#askInput');
  const btn = body.querySelector('#askSend');
  if (btn) btn.onclick = () => sendAsk(inp.value);
  if (inp) inp.onkeydown = (e) => { if (e.key === 'Enter' && !e.isComposing) sendAsk(inp.value); };
  body.querySelectorAll('.sug').forEach((b) => {
    b.onclick = () => {
      S.chat.suggest = [];
      selectCase(b.dataset.id).catch(() => toast('加载该病例失败'));
    };
  });
  body.querySelectorAll('[data-follow]').forEach((b) => {
    b.onclick = () => sendAsk(b.dataset.follow);
  });
  body.querySelectorAll('[data-cite]').forEach((b) => {
    b.onclick = () => {
      S.tab = 'evidence';
      document.querySelectorAll('.tabs button').forEach((x) => x.classList.toggle('on', x.dataset.t === 'evidence'));
      renderTab();
      toast('已切到双引用：' + b.dataset.cite);
    };
  });
  const atlasGo = body.querySelector('#atlasGo');
  if (atlasGo) atlasGo.onclick = () => runTemplate();
  const reset = body.querySelector('#askReset');
  if (reset) reset.onclick = () => {
    if (window.YZAgent) window.YZAgent.resetConversation('clinic');
    S.chat = {
      q: '', text: '', cites: [], image: S.chat.image, match: null,
      state: 'ready', err: '', trace: [], tools: [], followups: [],
      servedBy: null, degraded: false, reason: '', runId: null,
      literature: null, template: null, tmplErr: '', atlases: [], matchBBox: null,
    };
    renderTab();
    toast('已重置会话，下一问从新上下文开始');
  };
}

$('#uploadBtn').onclick = () => {
  if (!HAS_BACKEND) { toast('公网版不含模型服务，请在本地运行后使用'); return; }
  $('#fileInput').click();
};
$('#fileInput').onchange = async (e) => {
  const f = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!f) return;
  if (!/^image\//.test(f.type)) { toast('请选择图片文件'); return; }
  if (f.size > 8 * 1024 * 1024) { toast('图片超过 8MB，请压缩后再试'); return; }
  try {
    const url = await readAsDataURL(f);
    S.chat = {
      q: '', text: '', cites: [], image: url, match: null, state: 'ready', err: '',
      trace: [], tools: [], followups: [], servedBy: null, degraded: false,
      reason: '', runId: null, literature: null, template: null, tmplErr: '',
      atlases: [], matchBBox: null,
    };
    showUploaded(url);
    setStep('case', true, '已载入本地影像 · 输入问题开始；库内影像可拖框定位');
    S.tab = 'chat';
    document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('on', b.dataset.t === 'chat'));
    renderTab();
    toast('已载入影像，输入问题开始');
  } catch (err) { toast('读取失败'); }
};

window.addEventListener('resize', fitFrame);
init();
initModels();
