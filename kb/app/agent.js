/* RadioCheck · 四页共用的 Agent 客户端
 *
 * 职责只有三件：
 *   1. 把 /api/ask 的 SSE 解析成稳定事件（trace/tool/delta/citation/followup/reset/done）
 *   2. 按 surface 维护 conversation_id（有界多轮，刷新页面仍在，关标签页即失效）
 *   3. 给 teach / paper / compare 提供一个不打断页面的右侧抽屉
 *
 * 不在前端做检索、判分、引用校验：这些必须留在 DeepWorks agent 侧，
 * 否则前端会变成第二个“看起来像 agent”的假实现。
 */
(function () {
  'use strict';

  // 静态构建里 static.js 可能晚于本文件执行，所以不要在加载时把结果写死；
  // 真正调用时再判断，避免静态版误以为有后端。
  function hasBackend() { return !window.YZStatic; }
  const KEY = 'yz.agent.conversation.';
  const STAGES = [
    ['kb_retrieve', '检索'],
    ['skill_invoke', '技能'],
    ['workflow', '工作流'],
    ['agent_generate', '生成'],
    ['persist', '落盘'],
  ];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }

  function uid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'c-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
  }

  function conversationId(surface) {
    const k = KEY + (surface || 'general');
    let v = '';
    try { v = sessionStorage.getItem(k) || ''; } catch (e) { /* 隐私模式 */ }
    if (!v) {
      v = uid();
      try { sessionStorage.setItem(k, v); } catch (e) { /* 隐私模式 */ }
    }
    return v;
  }

  function resetConversation(surface) {
    try { sessionStorage.removeItem(KEY + (surface || 'general')); } catch (e) { /* ignore */ }
  }

  /* ---------- SSE ---------- */

  async function ask(payload, handlers) {
    handlers = handlers || {};
    if (!hasBackend()) {
      throw new Error('公网静态版不含 Agent 服务，请在本地启动 yingzhi/serve 后使用');
    }
    const surface = payload.surface || 'general';
    const body = Object.assign({
      role: 'student',
      device: 'desktop',
      surface,
      conversation_id: conversationId(surface),
    }, payload);
    delete body.signal;

    const r = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: handlers.signal,
    });
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try {
        const j = await r.json();
        if (j && (j.hint || j.detail || j.error)) msg = j.hint || j.detail || j.error;
      } catch (e) { /* 非 JSON 就用状态码 */ }
      throw new Error(msg);
    }
    if (!r.body) throw new Error('浏览器不支持流式响应');

    const out = {
      text: '', cites: [], trace: [], tools: [], followups: [],
      done: null, degraded: false, servedBy: null, conversationId: body.conversation_id,
    };
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = '';

    const dispatch = (kind, data) => {
      if (kind === 'delta') out.text += (data && data.text) || '';
      else if (kind === 'citation') out.cites.push(data);
      else if (kind === 'trace') out.trace.push(data);
      else if (kind === 'tool') out.tools.push(data);
      else if (kind === 'followup') out.followups = (data && data.items) || out.followups;
      else if (kind === 'reset') out.text = '';
      else if (kind === 'done') {
        out.done = data || {};
        out.degraded = !!(data && data.degraded);
        out.servedBy = (data && data.served_by) || null;
        out.followups = (data && data.followups) || out.followups;
      }
      if (typeof handlers.onEvent === 'function') handlers.onEvent(kind, data, out);
      if (typeof handlers[kind] === 'function') handlers[kind](data, out);
    };

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, i);
        buf = buf.slice(i + 2);
        let kind = 'message';
        let data = '';
        chunk.split('\n').forEach((line) => {
          if (line.startsWith('event:')) kind = line.slice(6).trim();
          else if (line.startsWith('data:')) data += line.slice(5).trim();
        });
        if (!data) continue;
        try { dispatch(kind, JSON.parse(data)); }
        catch (e) { /* 坏帧跳过，不影响整段 */ }
        // done 是终止事件：主动取消读取，不依赖服务器立刻关闭连接。
        // 实测某些浏览器会在 done 之后继续等 EOF，导致 UI 永远停在“生成中”。
        if (out.done) {
          try { await reader.cancel(); } catch (e) { /* 已关闭 */ }
          return out;
        }
      }
    }
    return out;
  }

  /* ---------- 抽屉 ---------- */

  function stageMap() {
    const m = {};
    STAGES.forEach(([k, label]) => { m[k] = { label, status: 'idle', ms: 0 }; });
    return m;
  }

  function stepHTML(stages) {
    return STAGES.map(([k]) => {
      const s = stages[k] || {};
      const cls = s.status === 'completed' ? 'done'
        : s.status === 'error' ? 'err'
          : s.status === 'degraded' ? 'warn'
            : s.status === 'unavailable' || s.status === 'skipped' ? 'off' : '';
      const ms = s.ms ? `<i>${s.ms}ms</i>` : '';
      return `<span class="yz-step ${cls}" data-stage="${k}">${esc(s.label || k)}${ms}</span>`;
    }).join('<span class="yz-step-sep">›</span>');
  }

  function open(opts) {
    opts = opts || {};
    if (!hasBackend()) {
      if (window.YZCommon && YZCommon.toast) YZCommon.toast('公网静态版不含 Agent 服务，请在本地启动后使用');
      return null;
    }
    const old = document.getElementById('yzAgent');
    if (old) old.remove();

    const surface = opts.surface || 'general';
    const ctx = opts.context || {};
    const ctxChips = Object.entries(ctx)
      .filter(([, v]) => v != null && String(v).trim() !== '')
      .slice(0, 4)
      .map(([k, v]) => `<span class="yz-ctx" title="${esc(v)}">${esc(k)}：${esc(String(v).slice(0, 46))}</span>`)
      .join('');

    const root = document.createElement('div');
    root.id = 'yzAgent';
    root.className = 'yz-agent-root';
    root.innerHTML = `
      <div class="yz-agent-mask" data-close="1"></div>
      <aside class="yz-agent" role="dialog" aria-label="Agent 问答">
        <header class="yz-agent-head">
          <div>
            <b>${esc(opts.title || '问 Agent')}</b>
            <span>${esc(opts.subtitle || '回答附可核对出处；降级会明确标注')}</span>
          </div>
          <button class="yz-agent-x" data-close="1" aria-label="关闭">×</button>
        </header>
        ${ctxChips ? `<div class="yz-agent-ctx">${ctxChips}</div>` : ''}
        <div class="yz-agent-body"></div>
        <footer class="yz-agent-foot">
          <input id="yzAgentInput" placeholder="${esc(opts.placeholder || '追问一句…')}" autocomplete="off">
          <button id="yzAgentSend">提问</button>
        </footer>
      </aside>`;
    document.body.appendChild(root);
    document.body.classList.add('yz-agent-open');

    const body = root.querySelector('.yz-agent-body');
    const input = root.querySelector('#yzAgentInput');
    const sendBtn = root.querySelector('#yzAgentSend');
    let busy = false;

    function onKey(e) {
      // 旧抽屉的监听可能还在；root 已移除时不要重复触发 onClose。
      if (e.key === 'Escape' && document.body.contains(root)) close();
    }
    function close() {
      document.removeEventListener('keydown', onKey);
      root.remove();
      document.body.classList.remove('yz-agent-open');
      if (typeof opts.onClose === 'function') opts.onClose();
    }
    root.querySelectorAll('[data-close]').forEach((el) => { el.onclick = close; });
    document.addEventListener('keydown', onKey);

    function turnShell(q) {
      const el = document.createElement('section');
      el.className = 'yz-turn';
      el.innerHTML = `
        <div class="yz-q">${esc(q)}</div>
        <div class="yz-steps">${stepHTML(stageMap())}</div>
        <div class="yz-tools" hidden></div>
        <div class="yz-answer"></div>
        <div class="yz-cites"></div>
        <div class="yz-follow"></div>
        <div class="yz-meta"></div>`;
      body.appendChild(el);
      body.scrollTop = body.scrollHeight;
      return el;
    }

    async function send(q) {
      q = (q || '').trim();
      if (!q || busy) return;
      busy = true;
      input.value = '';
      input.disabled = true;
      sendBtn.disabled = true;
      sendBtn.textContent = '生成中';

      const turn = turnShell(q);
      const stepsEl = turn.querySelector('.yz-steps');
      const toolsEl = turn.querySelector('.yz-tools');
      const answerEl = turn.querySelector('.yz-answer');
      const citesEl = turn.querySelector('.yz-cites');
      const followEl = turn.querySelector('.yz-follow');
      const metaEl = turn.querySelector('.yz-meta');
      const stages = stageMap();
      let answer = '';
      const tools = [];

      const paintSteps = () => { stepsEl.innerHTML = stepHTML(stages); };
      const paintTools = () => {
        toolsEl.hidden = !tools.length;
        toolsEl.innerHTML = tools.map((t) => `
          <div class="yz-tool ${t.status === 'error' ? 'err' : ''}">
            <b>${esc(t.skill || t.tool || 'tool')}</b>
            <span>${esc(t.detail || '')}</span>
            <i>${t.out_lines ? t.out_lines + ' 行 · ' : ''}${t.ms || 0}ms</i>
          </div>`).join('');
      };

      try {
        const result = await ask(Object.assign({}, opts.payload, {
          query: q, surface, context: ctx,
        }), {
          onEvent(kind, d) {
            if (kind === 'trace') {
              const s = stages[d.stage];
              if (s) {
                s.status = d.status || 'completed';
                s.ms = d.ms || 0;
                if (d.skill && d.skill !== 'none') s.label = d.skill;
                paintSteps();
              }
            } else if (kind === 'tool') {
              tools.push(d);
              paintTools();
            } else if (kind === 'delta') {
              answer += (d && d.text) || '';
              answerEl.textContent = answer;
              body.scrollTop = body.scrollHeight;
            } else if (kind === 'reset') {
              answer = '';
              answerEl.textContent = '';
            } else if (kind === 'citation') {
              citesEl.insertAdjacentHTML('beforeend', `
                <div class="yz-cite">
                  <b>${esc(d.id || '')}</b>
                  <span>${esc(d.title || '')}</span>
                  ${d.source_url ? `<a href="${esc(d.source_url)}" target="_blank" rel="noopener">来源 ↗</a>` : ''}
                </div>`);
            }
          },
        });

        // done 之后才渲染追问和徽标：它们是本轮结论，不是流式过程
        const done = result.done || {};
        const badge = result.degraded ? '降级' : (result.servedBy === 'agent' ? 'Agent' : (result.servedBy || '完成'));
        metaEl.innerHTML = `
          <span class="yz-badge ${result.degraded ? 'warn' : ''}">${esc(badge)}</span>
          <span>${done.total_ms != null ? done.total_ms + 'ms' : ''}</span>
          ${done.run_id ? `<a href="${esc(done.trace_url || ('/api/trace/' + done.run_id))}" target="_blank" rel="noopener">trace ↗</a>` : ''}
          ${done.reason ? `<span class="yz-reason">${esc(done.reason)}</span>` : ''}`;
        if (result.followups && result.followups.length) {
          followEl.innerHTML = result.followups.map((x) =>
            `<button data-follow="${esc(x)}">${esc(x)}</button>`).join('');
          followEl.querySelectorAll('[data-follow]').forEach((b) => {
            b.onclick = () => send(b.dataset.follow);
          });
        }
        if (!answer && done.blocked) answerEl.textContent = '该问题超出平台范围，已拦截。';
        if (!answer && !done.blocked) answerEl.textContent = '本轮没有返回正文，请打开 trace 查看工具链。';
      } catch (e) {
        metaEl.innerHTML = `<span class="yz-badge err">失败</span><span class="yz-reason">${esc(e.message || e)}</span>`;
      } finally {
        busy = false;
        input.disabled = false;
        sendBtn.disabled = false;
        sendBtn.textContent = '提问';
        input.focus();
      }
    }

    sendBtn.onclick = () => send(input.value);
    input.onkeydown = (e) => { if (e.key === 'Enter' && !e.isComposing) send(input.value); };
    input.focus();
    if (opts.seed) send(opts.seed);

    return { close, send, reset: () => resetConversation(surface) };
  }

  window.YZAgent = {
    get HAS_BACKEND() { return hasBackend(); },
    conversationId,
    resetConversation,
    ask,
    open,
  };
})();
