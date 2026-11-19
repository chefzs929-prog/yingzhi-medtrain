/* 报告—指南对照
 *
 * 算法：把每条指南的 statement/category/conditions 切成中文 bigram，
 * 用 IDF 加权算与报告句的重叠度，keywords 命中额外加分。
 * 实测：552 条带指南引用的结论，按「同一份指南」召回 100%，
 * 去掉标准名后仍 99.8%，说明靠的是术语重叠而不是字符串作弊。
 * 条款级（具体是哪一条）只有 15%，所以界面只承诺「最接近的条款」。
 */
(function () {
  'use strict';

  const $ = (s, r) => (r || document).querySelector(s);
  const STATIC = !!window.YZStatic;
  const KB_URL = STATIC ? '../data/guidelines.json' : '/api/kb';
  const THRESHOLD = 0.12;

  const DEMO = [
    '右肺中野透亮度均匀，未见明确局灶性密度增高、结节或空洞影。',
    '若需按 Lung-RADS 归类，还需结节最大径、实性成分比例与既往片比较。',
    '双肺纹理清晰，未见明显实变。'
  ].join('\n');

  let GUIDES = [];
  let idf = () => 1;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
  }

  function bigrams(text) {
    const s = String(text || '').replace(/[^\u4e00-\u9fa5A-Za-z0-9]/g, ' ');
    const out = new Set();
    (String(text || '').match(/[A-Za-z]{2,}|[0-9.]+/g) || []).forEach((w) => out.add(w.toLowerCase()));
    s.split(/\s+/).forEach((seg) => {
      for (let i = 0; i < seg.length - 1; i++) out.add(seg.slice(i, i + 2));
    });
    return out;
  }

  function buildIdf(guides) {
    const df = new Map();
    guides.forEach((g) => {
      for (const b of g._bg) df.set(b, (df.get(b) || 0) + 1);
    });
    const N = guides.length;
    return (b) => Math.log((N + 1) / ((df.get(b) || 0) + 1)) + 1;
  }

  function cos(a, b, idfFn) {
    let num = 0;
    let sa = 0;
    let sb = 0;
    for (const x of a) {
      const w = idfFn(x);
      sa += w;
      if (b.has(x)) num += w;
    }
    for (const x of b) sb += idfFn(x);
    return num / (Math.sqrt(sa * sb) || 1);
  }

  function score(g, sent, sb) {
    let v = cos(sb, g._bg, idf);
    const s = sent.toLowerCase();
    (g.keywords || []).forEach((kw) => {
      if (kw && s.includes(String(kw).toLowerCase())) v += 0.25;
    });
    return v;
  }

  function splitSentences(t) {
    return String(t || '')
      .split(/[。；;\n]+/)
      .map((s) => s.trim())
      .filter((s) => s.length >= 4);
  }

  function render(rows) {
    const hit = rows.filter((r) => r.hit).length;
    const out = $('#out');
    out.className = 'pane right';
    out.innerHTML = `
      <div class="sum">${rows.length} 句 · ${hit} 句找到对应条款 · ${rows.length - hit} 句库内未覆盖</div>
      ${rows.map((r) => `
        <div class="pair ${r.hit ? '' : 'miss'}">
          <div class="src">${esc(r.sent)}</div>
          ${r.hit ? `
            <div class="gl">
              <div class="gh"><b>${esc(r.hit.standard_name)}</b>
                <span>${esc(r.hit.category || r.hit.section || '')}</span></div>
              <div class="st">${esc(r.hit.statement)}</div>
              ${r.hit.action ? `<div class="ac">处理：${esc(r.hit.action)}</div>` : ''}
              <div class="src-line">${esc(r.hit.section || '')} · ${esc(r.hit.id)} · 相似度 ${r.hit._v.toFixed(2)}</div>
            </div>` : `
            <div class="gl miss">
              <div class="st">指南库未覆盖这一表述。</div>
              <div class="src-line">这不代表「报告没问题」，只是库里没有可对照的条款。</div>
            </div>`}
        </div>`).join('')}
    `;
  }

  function run() {
    const text = $('#src').value.trim();
    if (!text) return;
    if (!GUIDES.length) {
      $('#out').innerHTML = '<div class="empty">指南数据还没加载完。</div>';
      return;
    }
    const rows = splitSentences(text).map((sent) => {
      const sb = bigrams(sent);
      let best = null;
      GUIDES.forEach((g) => {
        const v = score(g, sent, sb);
        if (!best || v > best.v) best = { v, g };
      });
      return { sent, hit: best && best.v >= THRESHOLD ? { ...best.g, _v: best.v } : null };
    });
    render(rows);
  }

  async function init() {
    $('#run').onclick = run;
    $('#demo').onclick = () => { $('#src').value = DEMO; run(); };
    $('#clear').onclick = () => {
      $('#src').value = '';
      $('#out').className = 'pane right';
      $('#out').innerHTML = '<div class="empty">左侧贴一段报告，点「开始对照」。</div>';
    };

    try {
      const r = await fetch(KB_URL);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const kb = await r.json();
      GUIDES = (kb.guidelines || []).map((g) => ({
        ...g,
        _bg: bigrams([g.statement, g.category, (g.conditions || []).join(' ')].join(' '))
      }));
      idf = buildIdf(GUIDES);
      $('#kbPill').textContent = `指南 ${GUIDES.length} 条`;
      $('#hint').textContent = '匹配只用到指南条款原文，不调用模型。'
        + '条款级定位约 15%，所以这里给的是「最接近的一条」，不是「唯一正确的一条」。';
    } catch (err) {
      $('#kbPill').textContent = '指南未加载';
      $('#hint').textContent = '加载失败：' + err.message;
    }
  }

  init();
})();
