/* 练 · 真实病例演练 */
(function (YZ) {
  "use strict";
  const { esc, icon, DB, state, progress, save, today, scoreOf, avgScore, drillDone, currentDrill, traceLocal, dataBadge } = YZ;

  function startDrill(id) {
    if (!DB.drills.find((d) => d.id === id)) return;
    state.drillId = id;
    state.drillStep = 1;
    state.drillAnswers = {};
    state.drillResult = null;
    progress.last = Object.assign({}, progress.last, { drillId: id });
    save();
    YZ.go("drill");
  }

  /* ---------- 题库切换：病例演练 / 考点练习 ---------- */
  function drillTabs() {
    const caseDone = Object.keys(progress.drills).length;
    const quizDone = Object.keys(progress.quiz || {}).length;
    const total = (DB.quiz || []).length;
    return `<div class="drill-tabs">
      <button class="drill-tab ${state.drillTab !== "quiz" ? "on" : ""}" data-act="drill-tab" data-tab="case">
        病例演练 <em>${caseDone}/${DB.drills.length}</em>
      </button>
      <button class="drill-tab ${state.drillTab === "quiz" ? "on" : ""}" data-act="drill-tab" data-tab="quiz">
        考点练习 <em>${quizDone}/${total}</em>
      </button>
    </div>`;
  }

  function drillView() {
    if (state.drillId && currentDrill()) return drillActive(currentDrill());
    if (state.quizId) return quizActive();
    return state.drillTab === "quiz" ? quizList() : caseList();
  }

  function caseList() {
    const arr = DB.drills.filter((d) => !state.drillFilter || d.regionId === state.drillFilter);
    const done = arr.filter((d) => progress.drills[d.id]).length;
    const copy = state.role === "teacher"
      ? { h: "练 · 组卷与课堂演练", p: "从 29 例病例与 179 道考点题按部位/题型组卷、预览、投屏讲评；学生记录回到班级，错题自动聚合。" }
      : state.role === "doctor"
        ? { h: "练 · 读片演练", p: "在公开病例上做定位—描述—征象—依据四步读片；用于读片会、规培带教与自我校准。" }
        : { h: "练 · 真实病例演练", p: "四步：先定位，再说描述，再认征象，最后选依据。每一步都给反馈，错因会进入错题本。" };
    const actions = state.role === "teacher"
      ? `<button class="btn" data-act="teacher-go" data-tab="assign">${icon("clipboard", 15)} 去组卷</button><button class="btn" data-act="teacher-go" data-tab="projection">${icon("monitor", 15)} 课堂投屏</button><button class="btn primary" data-act="teacher-go" data-tab="overview">${icon("users", 15)} 看班级</button>`
      : state.role === "doctor"
        ? `<button class="btn" data-act="drill-random">${icon("refresh", 15)} 随机一例</button><button class="btn primary" data-act="nav" data-view="apply">${icon("stethoscope", 15)} 去工作台核验</button>`
        : `<button class="btn" data-act="drill-random">${icon("refresh", 15)} 随机一例</button><button class="btn primary" data-act="nav" data-view="apply">${icon("chart", 15)} 看记录</button>`;
    return `<div class="page-head">
      <div><div class="eyebrow">CHAIN 03 · DELIBERATE PRACTICE</div><h1>${copy.h}</h1><p>${copy.p}</p></div>
      <div class="page-actions">${actions}</div>
    </div>
    ${drillTabs()}
    <div class="stat-strip" style="margin-bottom:14px">
      <div class="stat"><b>${done}/${arr.length}</b><span>已完成</span><i>当前筛选</i></div>
      <div class="stat"><b>${avgScore()}</b><span>平均分</span>${dataBadge("local")}</div>
      <div class="stat"><b>${Object.keys(progress.drills).length}</b><span>累计演练</span><i>含重复</i></div>
      <div class="stat"><b>${DB.meta.counts.regions}</b><span>可定位分区</span><i>人工标注</i></div>
      <div class="stat"><b>${DB.meta.counts.dual}</b><span>双引用结论</span><i>可回溯</i></div>
    </div>
    <div class="filters">
      <span class="lbl">部位</span>
      <button class="chip ${!state.drillFilter ? "on" : ""}" data-act="drill-filter" data-part="">全部</button>
      ${DB.meta.regions.map((r) => `<button class="chip ${state.drillFilter === r.id ? "on" : ""}" data-act="drill-filter" data-part="${r.id}">${r.name}</button>`).join("")}
      <span class="lbl" style="margin-left:auto">${arr.length} 例可练</span>
    </div>
    <div class="case-grid">
      ${arr.map((d) => {
        const sc = scoreOf(d.id);
        return `<button class="case-card" data-act="drill-start" data-id="${d.id}">
          <img src="${d.image}" alt="">
          <div class="cc"><b>${esc(d.title)}</b><span>${d.modality.join("/")} · ${esc(d.bodyPart)} · ${d.mode === "normal" ? "正常对照" : "征象匹配"}</span>
          <div class="row"><span class="chip ${d.locateMode === "finding" ? "solid" : ""}">${d.locateMode === "finding" ? "描述定位" : "解剖定位"}</span>${sc != null ? `<span class="chip ok">${sc} 分</span>` : '<span class="chip">未练</span>'}</div></div>
        </button>`;
      }).join("")}
    </div>`;
  }

  /* ---------- 考点练习 ---------- */
  const QUIZ_TYPES = [["", "全部"], ["define", "定义辨析"], ["modality", "检查选择"], ["pitfall", "易错辨析"]];

  function quizStat() {
    const vals = Object.values(progress.quiz || {});
    const right = vals.filter((x) => x.lastCorrect).length;
    return { done: vals.length, right, rate: vals.length ? Math.round((right / vals.length) * 100) : 0 };
  }

  /* 错题 → 易错点聚合：把做错的题挂载的 pitfalls 去重列出 */
  function weakPitfalls(limit) {
    const wrongIds = Object.entries(progress.quiz || {}).filter(([, v]) => !v.lastCorrect).map(([k]) => k);
    const out = [];
    (DB.quiz || []).forEach((q) => {
      if (!wrongIds.includes(q.id)) return;
      (q.pitfalls || []).forEach((p) => { if (!out.includes(p)) out.push(p); });
    });
    return out.slice(0, limit || 5);
  }

  function quizPool() {
    const wrong = progress.quiz || {};
    return (DB.quiz || []).filter((q) => {
      if (state.quizFilter && q.type !== state.quizFilter) return false;
      if (state.quizWrongOnly && !(wrong[q.id] && !wrong[q.id].lastCorrect)) return false;
      return true;
    });
  }

  function quizList() {
    const arr = quizPool();
    const st = quizStat();
    const pits = weakPitfalls(5);
    return `<div class="page-head">
      <div><div class="eyebrow">CHAIN 03 · EXAM-STYLE DRILL</div><h1>练 · 考点练习</h1>
        <p>题型参考影像学考试常见考法：定义辨析、检查选择、易错辨析。题目内容全部来自知识库原文，
           判分按知识库标注，不声称是任何考试的真题。</p></div>
      <div class="page-actions"><button class="btn" data-act="quiz-random">${icon("refresh", 15)} 随机一题</button></div>
    </div>
    ${drillTabs()}
    <div class="stat-strip" style="margin-bottom:14px">
      <div class="stat"><b>${st.done}/${(DB.quiz || []).length}</b><span>已做</span><i>去重</i></div>
      <div class="stat"><b>${st.rate}%</b><span>正确率</span>${dataBadge("local")}</div>
      <div class="stat"><b>${st.done - st.right}</b><span>错题</span><i>进入易错点</i></div>
      <div class="stat"><b>${pits.length}</b><span>待巩固易错点</span><i>按错题聚合</i></div>
      <div class="stat"><b>60</b><span>覆盖征象</span><i>全部词条</i></div>
    </div>
    ${pits.length ? `<div class="quiz-pit" style="margin-bottom:14px">
      <b>你的高频易错点</b>
      <ul>${pits.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
    </div>` : ""}
    <div class="filters">
      <span class="lbl">题型</span>
      ${QUIZ_TYPES.map(([k, label]) => `<button class="chip ${state.quizFilter === k ? "on" : ""}" data-act="quiz-filter" data-type="${k}">${label}</button>`).join("")}
      <button class="chip ${state.quizWrongOnly ? "danger" : ""}" data-act="quiz-wrong" style="margin-left:10px">
        只练错题${st.done - st.right ? ` ${st.done - st.right}` : ""}
      </button>
      <span class="lbl" style="margin-left:auto">${arr.length} 题</span>
    </div>
    <div class="quiz-grid">
      ${arr.map((q) => {
        const p = (progress.quiz || {})[q.id];
        const chip = !p ? '<span class="chip">未做</span>'
          : p.lastCorrect ? `<span class="chip ok">对 ${p.done} 次</span>`
          : `<span class="chip danger">错 ${p.wrong} 次</span>`;
        return `<button class="quiz-card" data-act="quiz-start" data-id="${q.id}">
          <div class="row" style="gap:6px"><span class="chip solid">${esc(q.typeName)}</span>${chip}</div>
          <b>${esc(q.signName)}</b>
          <span>${esc(q.prompt)}</span>
        </button>`;
      }).join("")}
    </div>`;
  }

  function currentQuiz() { return (DB.quiz || []).find((q) => q.id === state.quizId) || null; }

  function startQuiz(id) {
    if (!(DB.quiz || []).find((q) => q.id === id)) return;
    state.quizId = id;
    state.quizPicks = [];
    state.quizDone = false;
    state.quizResult = null;
    YZ.go("drill");
  }

  function quizPick(i) {
    if (state.quizDone) return;
    const q = currentQuiz();
    if (q && !q.multi) {
      // 单选题：再次点同一个选项才取消，点别的直接替换
      state.quizPicks = (state.quizPicks || [])[0] === i ? [] : [i];
    } else {
      const cur = (state.quizPicks || []).slice();
      const k = cur.indexOf(i);
      if (k >= 0) cur.splice(k, 1); else cur.push(i);
      state.quizPicks = cur;
    }
    YZ.render();
  }

  function quizSubmit() {
    const q = currentQuiz();
    if (!q || state.quizDone || !(state.quizPicks || []).length) return;
    const right = q.options.map((o, i) => (o.correct ? i : -1)).filter((i) => i >= 0);
    const picked = state.quizPicks.slice().sort((a, b) => a - b);
    const ok = picked.length === right.length && picked.every((x) => right.includes(x));
    const prev = (progress.quiz || {})[q.id] || { done: 0, wrong: 0 };
    progress.quiz[q.id] = {
      done: (prev.done || 0) + 1,
      wrong: (prev.wrong || 0) + (ok ? 0 : 1),
      lastCorrect: ok,
      date: today(),
    };
    save();
    state.quizDone = true;
    state.quizResult = ok;
    YZ.render();
  }

  function quizNext() {
    const arr = quizPool();
    const idx = arr.findIndex((q) => q.id === state.quizId);
    const next = arr[(idx + 1) % arr.length];
    if (next) startQuiz(next.id);
  }

  function quizRandom() {
    const arr = quizPool();
    const q = arr[Math.floor(Math.random() * arr.length)];
    if (q) startQuiz(q.id);
  }

  function exitQuiz() {
    state.quizId = null;
    state.quizPicks = [];
    state.quizDone = false;
    state.quizResult = null;
    YZ.render();
  }

  function quizActive() {
    const q = currentQuiz();
    if (!q) return "";
    const done = state.quizDone;
    const ok = state.quizResult;
    const letters = "ABCDE";
    const picks = state.quizPicks || [];
    return `<div class="page-head">
      <div><div class="eyebrow">CHAIN 03 · ${esc(q.typeName)}</div><h1>${esc(q.signName)}</h1>
        <p>题目与判分依据均来自知识库原文；不是考试真题，用于考点自测与易错点定位。</p></div>
      <div class="page-actions"><button class="btn" data-act="quiz-exit">${icon("left", 14)} 返回题库</button></div>
    </div>
    <div class="qcard" style="max-width:840px">
      <div class="qh"><span class="qn">Q</span><h4>${esc(q.prompt)}</h4>
        <span class="chip ${q.multi ? "solid" : ""}">${q.multi ? "多选" : "单选"}</span></div>
      ${q.stem ? `<p style="font-size:13px;color:var(--ink-2);background:var(--surface-2);padding:10px 12px;border-radius:9px;border:1px solid var(--line-2)">${esc(q.stem)}</p>` : ""}
      <div class="quiz-opts">
        ${q.options.map((o, i) => {
          const picked = picks.includes(i);
          const cls = done ? (o.correct ? "ok" : picked ? "bad" : "") : picked ? "on" : "";
          const mark = done ? (o.correct ? "✓" : picked ? "✕" : letters[i]) : letters[i];
          return `<button class="quiz-opt ${cls}" data-act="quiz-pick" data-i="${i}" ${done ? "disabled" : ""}>
            <span class="oi">${mark}</span><span>${esc(o.text)}</span>
          </button>`;
        }).join("")}
      </div>
      ${!done ? `<button class="btn primary" style="width:100%;margin-top:12px" data-act="quiz-submit" ${picks.length ? "" : "disabled"}>提交答案</button>` : ""}
      ${done ? `<div class="feedback ${ok ? "ok" : "no"}"><b>${ok ? "回答正确" : "回答有误"}</b>${esc(q.explain)}</div>` : ""}
      ${done && (q.pitfalls || []).length ? `<div class="quiz-pit">
        <b>本题易错点</b>
        <ul>${q.pitfalls.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
      </div>` : ""}
      ${done ? `<div class="row wrap" style="margin-top:12px">
        <button class="btn primary" data-act="quiz-next">下一题 ${icon("right", 14)}</button>
        <button class="btn" data-act="quiz-again" data-id="${q.id}">再做一次</button>
        <button class="btn" data-act="sign" data-id="${q.signId}">${icon("book", 14)} 去看词条</button>
      </div>` : ""}
      ${q.source ? `<p class="tiny muted" style="margin-top:10px">出处：${esc(q.source)}${q.sourceUrl ? ` · <a href="${esc(q.sourceUrl)}" target="_blank" rel="noopener">原文</a>` : ""}</p>` : ""}
    </div>`;
  }

  function drillActive(d) {
    const step = state.drillStep;
    const ans = state.drillAnswers;
    return `<div class="drill-top">
      <div class="row"><button class="btn sm" data-act="drill-exit">${icon("left", 14)} 退出</button><span class="chip">${esc(d.title)}</span><span class="chip solid">${d.modality.join("/")}</span></div>
      <div class="steps">${[1, 2, 3, 4].map((i) => `<i class="${i < step ? "done" : i === step ? "on" : ""}"></i>`).join("")}<span class="small muted">${step} / 4</span></div>
    </div>
    <div class="drill-grid">
      <div>
        <div class="stage-wrap">
          <div class="stage">
            <div class="frame">
              <img src="${d.image}" alt="${esc(d.title)}">
              <div class="overlay">${drillBoxes(d, ans)}</div>
            </div>
          </div>
          <div class="stage-note"><span>${ans.loc ? `<b>${esc(d.region.name)}</b> · ${esc((d.region.note || "").slice(0, 42))}` : "点击分区后显示答案与解剖范围"}</span><span>框为人工标注解剖区，不是病灶分割</span></div>
        </div>
        <div class="row wrap" style="margin-top:10px"><span class="chip">${esc(d.bodyPart)}</span><span class="chip">${d.mode === "normal" ? "正常对照" : "来源标签"}</span><span class="chip">${d.locateMode === "finding" ? "描述定位" : "解剖定位"}</span><span class="chip">${d.regionOptions.length} 个分区</span></div>
      </div>
      <div class="card drill-panel">${drillPanel(d, ans)}</div>
    </div>`;
  }

  function drillBoxes(d, ans) {
    const answered = ans.loc != null;
    return d.regionOptions.map((r, i) => {
      const letter = String.fromCharCode(65 + i);
      const [x, y, w, h] = r.coords;
      let cls = "bbox";
      if (ans.loc != null) {
        if (r.id === d.region.id) cls += " correct labeled";
        else if (r.id === ans.loc.regionId && !ans.loc.correct) cls += " wrong labeled";
        else cls += " dim";
      } else if (state.drillStep === 1) cls += " pick";
      return `<button class="${cls}" style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%" ${state.drillStep === 1 && !answered ? `data-act="drill-loc" data-region="${r.id}"` : ""} title="${answered ? esc(r.name) : ""}">
        <span>${letter}</span>
      </button>`;
    }).join("");
  }

  function feedback(ok, title, body) {
    return `<div class="feedback ${ok ? "ok" : "no"}"><b>${ok ? "✓ " : "× "}${esc(title)}</b>${body ? esc(body) : ""}</div>`;
  }

  function drillPanel(d, ans) {
    if (state.drillResult) return drillResult(d, state.drillResult);
    const step = state.drillStep;
    if (step === 1) {
      const done = ans.loc != null;
      return `<div class="row spread"><span class="chip solid">第 1 步 · 定位</span><span class="tiny muted">25 分</span></div>
        <div class="drill-q" style="margin-top:10px">${esc(d.stem)}</div>
        <div class="drill-sub">在影像上点击对应分区；看不清时可用下方分区名。${d.locateMode === "finding" ? "题干已隐去分区名。" : "这是解剖范围题，先判断分区。"}</div>
        ${done ? feedback(ans.loc.correct, ans.loc.correct ? "定位正确。" : `定位不对。正确分区是「${d.region.name}」。`, d.region.note) : ""}
        <div class="region-pills">${d.regionOptions.map((r, i) => `<button data-act="drill-loc" data-region="${r.id}" ${done ? "disabled" : ""}>${String.fromCharCode(65 + i)} · ${esc(r.name)}</button>`).join("")}</div>
        ${done ? `<button class="btn primary" style="width:100%;margin-top:12px" data-act="drill-next">下一步 ${icon("right", 14)}</button>` : ""}`;
    }
    if (step === 2) {
      const done = ans.desc != null && ans.desc.confirmed;
      return `<div class="row spread"><span class="chip solid">第 2 步 · 描述</span><span class="tiny muted">25 分</span></div>
        <div class="drill-q" style="margin-top:10px">哪一条描述与这张影像/这个分区最匹配？</div>
        <div class="drill-sub">只看描述本身，不急着下诊断。</div>
        ${d.descOptions.map((o, i) => {
          let cls = "opt";
          if (done) {
            if (o.correct) cls += " correct";
            else if (ans.desc.id === o.id) cls += " wrong";
          } else if (ans.desc && ans.desc.id === o.id && !done) cls += " sel";
          return `<button class="${cls}" data-act="drill-opt" data-step="desc" data-id="${o.id}" ${done ? "disabled" : ""}><span class="oi">${String.fromCharCode(65 + i)}</span><span>${esc(o.text)}</span></button>`;
        }).join("")}
        ${done ? feedback(ans.desc.correct, ans.desc.correct ? "描述匹配。" : "这条描述对应的是另一个征象。", d.teachingNote) : ""}
        ${!done && ans.desc ? '<button class="btn primary" style="width:100%;margin-top:6px" data-act="drill-confirm" data-step="desc">确认选择</button>' : ""}
        ${done ? `<button class="btn primary" style="width:100%;margin-top:12px" data-act="drill-next">下一步 ${icon("right", 14)}</button>` : ""}`;
    }
    if (step === 3) {
      const done = ans.signs != null && ans.signs.confirmed;
      return `<div class="row spread"><span class="chip solid">第 3 步 · 征象</span><span class="tiny muted">25 分</span></div>
        <div class="drill-q" style="margin-top:10px">${esc(d.signPrompt)}</div>
        <div class="drill-sub">可以多选；选错会扣分。</div>
        ${d.signOptions.map((o, i) => {
          let cls = "opt";
          if (done) {
            if (o.correct) cls += " correct";
            else if (ans.signs.ids.includes(o.id)) cls += " wrong";
          } else if (ans.signs && ans.signs.ids.includes(o.id) && !done) cls += " sel";
          return `<button class="${cls}" data-act="drill-pick-sign" data-id="${o.id}" ${done ? "disabled" : ""}><span class="oi">${done && o.correct ? "✓" : String.fromCharCode(65 + i)}</span><span>${esc(o.name)}</span></button>`;
        }).join("")}
        ${done ? feedback(ans.signs.score >= 25, `本步得分 ${ans.signs.score} / 25。`, `正确项：${d.signOptions.filter((o) => o.correct).map((o) => o.name).join("、")}`) : ""}
        ${!done && ans.signs ? '<button class="btn primary" style="width:100%;margin-top:6px" data-act="drill-confirm" data-step="signs">确认选择</button>' : ""}
        ${done ? `<button class="btn primary" style="width:100%;margin-top:12px" data-act="drill-next">下一步 ${icon("right", 14)}</button>` : ""}`;
    }
    const done = ans.ev != null && ans.ev.confirmed;
    return `<div class="row spread"><span class="chip solid">第 4 步 · 依据</span><span class="tiny muted">25 分</span></div>
      <div class="drill-q" style="margin-top:10px">哪一条依据最能支撑上面的描述？</div>
      <div class="drill-sub">依据要能回到具体文献/词条，而不是“看起来像”。</div>
      ${d.evOptions.map((o, i) => {
        let cls = "opt";
        if (done) {
          if (o.correct) cls += " correct";
          else if (ans.ev.docId === o.docId) cls += " wrong";
        } else if (ans.ev && ans.ev.docId === o.docId && !done) cls += " sel";
        return `<button class="${cls}" data-act="drill-opt" data-step="ev" data-id="${esc(o.docId)}" ${done ? "disabled" : ""}><span class="oi">${String.fromCharCode(65 + i)}</span><span><b>${esc(o.title)}</b><span class="why">${esc(o.excerpt).slice(0, 96)}…</span></span></button>`;
      }).join("")}
      ${done ? feedback(ans.ev.correct, ans.ev.correct ? "依据正确。" : "这条依据对应的是另一个词条。", `正确依据：${esc(d.evOptions.find((o) => o.correct).title)}`) : ""}
      ${!done && ans.ev ? '<button class="btn primary" style="width:100%;margin-top:6px" data-act="drill-confirm" data-step="ev">确认选择</button>' : ""}
      ${done ? `<button class="btn primary" style="width:100%;margin-top:12px" data-act="drill-finish">查看结果 ${icon("right", 14)}</button>` : ""}`;
  }

  function drillResult(d, r) {
    const level = r.score >= 85 ? "掌握较好" : r.score >= 60 ? "基本达成" : "需要复习";
    return `<div style="text-align:center;padding:6px 0 10px">
      <div class="score-ring" style="--p:${r.score}"><div class="in"><b>${r.score}</b><span>${level}</span></div></div>
      <p class="small muted" style="margin-top:10px">${esc(d.title)}</p>
    </div>
    <div class="result-list">${r.parts.map((p) => `<div class="result-row"><span>${esc(p.label)}</span><b>${p.score} / ${p.max}</b></div>`).join("")}</div>
    ${traceLocal("本次判分的计算过程", r.parts.map((p) => ({ label: p.label, value: `${p.score} / ${p.max}`, state: p.score === p.max ? "ok" : p.score > 0 ? "warn" : "bad" })))}
    ${r.wrong.length ? `<div class="feedback no" style="margin-top:10px"><b>错因记录</b>${r.wrong.map(esc).join("；")}</div>` : '<div class="feedback ok" style="margin-top:10px"><b>四步全对</b>定位、描述、征象、依据都能对上。</div>'}
    ${(d.pitfalls || []).length ? `<div class="quiz-pit"><b>本例易错点${r.wrong.length ? "（错题已归入）" : ""}</b><ul>${d.pitfalls.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
    <div class="row wrap" style="margin-top:12px"><button class="btn primary" data-act="drill-again" data-id="${d.id}">${icon("refresh", 14)} 再练一次</button><button class="btn" data-act="drill-next-case">下一例</button><button class="btn" data-act="drill-explain">${icon("eye", 14)} 看解析</button>${state.role === "doctor" ? `<button class="btn" data-act="case" data-id="${d.caseId}">${icon("stethoscope", 14)} 去工作台核验</button>` : ""}</div>
    ${r.explain ? `<div class="qcard" style="margin-top:12px;text-align:left"><div class="qh"><span class="qn">i</span><h4>解析与出处</h4></div><p>${esc(d.teachingNote)}</p>${d.guideline ? `<div class="divider"></div><b class="small">${esc(d.guideline.standard)} · ${esc(d.guideline.category)}</b><p style="margin-top:4px">${esc(d.guideline.statement)}</p><p class="tiny muted">条件：${esc((d.guideline.conditions || []).join("；"))}（只作条款对照，不判断个体是否满足）</p>` : ""}<p class="tiny muted" style="margin-top:8px">影像：${esc(d.license)} · ${esc(d.artist)} · <a href="${esc(d.sourcePage)}" target="_blank" rel="noopener">来源页</a></p></div>` : ""}`;
  }

  function answerLoc(regionId) {
    const d = currentDrill();
    if (!d || state.drillAnswers.loc) return;
    state.drillAnswers.loc = { regionId, correct: regionId === d.region.id };
    YZ.render();
  }

  function selectOpt(step, id) {
    const d = currentDrill();
    if (!d || state.drillResult) return;
    if (step === "desc") {
      if (state.drillAnswers.desc) return;
      const o = d.descOptions.find((x) => x.id === id);
      state.drillAnswers.desc = { id, correct: !!o && o.correct, confirmed: false };
    } else if (step === "ev") {
      if (state.drillAnswers.ev) return;
      const o = d.evOptions.find((x) => x.docId === id);
      state.drillAnswers.ev = { docId: id, correct: !!o && o.correct, confirmed: false };
    }
    YZ.render();
  }

  function toggleSign(id) {
    const d = currentDrill();
    if (!d || state.drillAnswers.signs) return;
    const cur = state.drillAnswers.signs ? state.drillAnswers.signs.ids.slice() : [];
    const i = cur.indexOf(id);
    if (i >= 0) cur.splice(i, 1); else cur.push(id);
    state.drillAnswers.signs = { ids: cur, confirmed: false };
    YZ.render();
  }

  function confirmStep(step) {
    const d = currentDrill();
    if (!d) return;
    if (step === "desc" && state.drillAnswers.desc) {
      state.drillAnswers.desc = Object.assign({}, state.drillAnswers.desc, { confirmed: true });
    }
    if (step === "signs" && state.drillAnswers.signs) {
      const correctSet = new Set(d.signOptions.filter((o) => o.correct).map((o) => o.id));
      const chosen = new Set(state.drillAnswers.signs.ids);
      const hits = Array.from(chosen).filter((x) => correctSet.has(x)).length;
      const misses = Array.from(chosen).filter((x) => !correctSet.has(x)).length;
      const score = clamp(Math.round(25 * Math.max(0, hits - misses * 0.5) / Math.max(1, correctSet.size)), 0, 25);
      state.drillAnswers.signs = { ids: Array.from(chosen), score, correct: hits === correctSet.size && misses === 0, confirmed: true };
    }
    if (step === "ev" && state.drillAnswers.ev) {
      state.drillAnswers.ev = Object.assign({}, state.drillAnswers.ev, { confirmed: true });
    }
    YZ.render();
  }

  function clamp(n, a, b) { return Math.max(a, Math.min(b, n)); }

  function nextStep() {
    if (state.drillStep < 4) state.drillStep += 1;
    YZ.render();
  }

  function finishDrill() {
    const d = currentDrill();
    if (!d) return;
    const a = state.drillAnswers;
    const parts = [
      { label: "定位", score: a.loc && a.loc.correct ? 25 : 0, max: 25 },
      { label: "描述", score: a.desc && a.desc.correct ? 25 : 0, max: 25 },
      { label: "征象", score: a.signs ? a.signs.score : 0, max: 25 },
      { label: "依据", score: a.ev && a.ev.correct ? 25 : 0, max: 25 },
    ];
    const score = parts.reduce((n, p) => n + p.score, 0);
    const wrong = [];
    if (!a.loc || !a.loc.correct) wrong.push(`定位：正确分区是「${d.region.name}」`);
    if (!a.desc || !a.desc.correct) {
      const o = d.descOptions.find((x) => x.correct);
      wrong.push(`描述：应选「${(o && o.text || "").slice(0, 26)}…」`);
    }
    if (!a.signs || !a.signs.correct) {
      const miss = d.signOptions.filter((o) => o.correct && !(a.signs && a.signs.ids.includes(o.id))).map((o) => o.name);
      if (miss.length) wrong.push(`征象：漏选 ${miss.join("、")}`);
    }
    if (!a.ev || !a.ev.correct) {
      const o = d.evOptions.find((x) => x.correct);
      wrong.push(`依据：应选「${o ? o.title : ""}」`);
    }
    const prev = progress.drills[d.id];
    progress.drills[d.id] = {
      score: prev ? Math.max(prev.score, score) : score,
      last: score,
      date: today(),
      wrong,
    };
    save();
    state.drillResult = { score, parts, wrong, explain: false };
    YZ.render();
  }

  function exitDrill() {
    state.drillId = null;
    state.drillStep = 1;
    state.drillAnswers = {};
    state.drillResult = null;
    YZ.go("drill");
  }

  function randomDrill() {
    const pool = DB.drills.filter((d) => !state.drillFilter || d.regionId === state.drillFilter);
    const next = pool[Math.floor(Math.random() * pool.length)];
    if (next) startDrill(next.id);
  }

  function nextCase() {
    const d = currentDrill();
    const idx = DB.drills.findIndex((x) => x.id === (d && d.id));
    const next = DB.drills[(idx + 1) % DB.drills.length];
    startDrill(next.id);
  }

  function drillBySign(signId) {
    const s = YZ.sign(signId);
    const match = DB.drills.find((d) => d.correctSigns.includes(signId)) || DB.drills.find((d) => d.bodyPart === (s && s.body_part)) || DB.drills[0];
    startDrill(match.id);
  }

  Object.assign(YZ, {
    drillView, startDrill, answerLoc, selectOpt, toggleSign, confirmStep, nextStep, finishDrill,
    exitDrill, randomDrill, nextCase, drillBySign,
    startQuiz, quizPick, quizSubmit, quizNext, quizRandom, exitQuiz,
  });
})(window.YZ);
