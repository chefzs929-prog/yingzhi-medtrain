/* 交互绑定与启动 */
(function (YZ) {
  "use strict";
  const { state, progress, save, go, render, setRole, setDevice, sign, caseOf, claimsOf, toast, DB } = YZ;

  function bind() {
    const app = YZ.app;

    app.addEventListener("click", (e) => {
      const el = e.target.closest("[data-act]");
      if (!el) {
        if (state.roleMenu) { state.roleMenu = false; render(); }
        return;
      }
      if (el.classList.contains("modal-mask") && e.target.closest(".modal")) return;
      const act = el.dataset.act;
      const id = el.dataset.id;
      const tab = el.dataset.tab;
      const part = el.dataset.part;
      const roleKey = el.dataset.role;

      switch (act) {
        case "nav": go(el.dataset.view); break;
        case "role-menu": state.roleMenu = !state.roleMenu; render(); break;
        case "evidence": state.evidence = !state.evidence; render(); break;
        case "role": setRole(roleKey); break;
        case "device": setDevice(YZ.isMobile() ? "auto" : "mobile"); break;
        case "device-set": setDevice(el.dataset.device); break;

        case "sign-back": state.mobileSignOpen = false; render(); break;
        case "sign": {
          state.signId = id;
          state.mobileSignOpen = true;
          state.compareId = null;
          state.dualQuery = "";
          if (!progress.learned.includes(id)) progress.learned.push(id);
          progress.last.signId = id;
          save();
          go("learn");
          break;
        }
        case "part": state.part = part || ""; render(); break;
        case "compare": state.compareId = id; render(); break;
        case "transfer-sign": {
          state.transferId = id;
          state.signId = id;
          state.compareId = null;
          go("transfer");
          break;
        }
        case "dual": state.dualQuery = el.dataset.q; render(); break;
        case "bookmark": {
          const i = progress.bookmarks.indexOf(id);
          if (i >= 0) progress.bookmarks.splice(i, 1); else progress.bookmarks.push(id);
          save();
          toast(i >= 0 ? "已取消收藏" : "已收藏");
          break;
        }
        case "learn-search": {
          const q = YZ.$("#learnQ");
          state.query = q ? q.value : "";
          render();
          break;
        }
        case "learn-ask": {
          const q = YZ.$("#learnQ");
          state.query = q ? q.value : "";
          render();
          YZ.startAgentAsk(state.query);
          break;
        }
        case "learn-ask-sign": {
          const s = sign(id);
          if (!s) break;
          state.query = s.name;
          YZ.startAgentAsk("请解释影像征象「" + s.name + "」：定义、怎么看、容易错在哪。");
          break;
        }
        case "learn-ask-stop": YZ.stopAgentAsk(); break;

        case "drill-random": YZ.randomDrill(); break;
        case "drill-sign": YZ.drillBySign(id); break;
        case "drill-filter": state.drillFilter = part || ""; render(); break;
        case "drill-start": YZ.startDrill(id); break;
        case "drill-loc": YZ.answerLoc(el.dataset.region); break;
        case "drill-opt": YZ.selectOpt(el.dataset.step, id); break;
        case "drill-pick-sign": YZ.toggleSign(id); break;
        case "drill-confirm": YZ.confirmStep(el.dataset.step); break;
        case "drill-next": YZ.nextStep(); break;
        case "drill-finish": YZ.finishDrill(); break;
        case "drill-exit": YZ.exitDrill(); break;
        case "drill-again": YZ.startDrill(id); break;
        case "drill-next-case": YZ.nextCase(); break;
        case "drill-explain": if (state.drillResult) { state.drillResult.explain = true; render(); } break;
        case "drill-tab": state.drillTab = el.dataset.tab || "case"; state.drillId = null; state.quizId = null; render(); break;
        case "quiz-start": YZ.startQuiz(id); break;
        case "quiz-pick": YZ.quizPick(Number(el.dataset.i)); break;
        case "quiz-submit": YZ.quizSubmit(); break;
        case "quiz-next": YZ.quizNext(); break;
        case "quiz-again": YZ.startQuiz(id); break;
        case "quiz-random": YZ.quizRandom(); break;
        case "quiz-exit": YZ.exitQuiz(); break;
        case "quiz-filter": state.quizFilter = el.dataset.type || ""; render(); break;
        case "quiz-wrong": state.quizWrongOnly = !state.quizWrongOnly; render(); break;

        case "case-prev":
        case "case-next": {
          const arr = DB.cases;
          const i = arr.findIndex((x) => x.id === state.caseId);
          const next = el.dataset.act === "case-next" ? (i + 1 + arr.length) % arr.length : (i - 1 + arr.length) % arr.length;
          state.caseId = arr[next].id;
          state.regionId = null;
          state.claimId = null;
          YZ.ensureCase(state.caseId).then(render);
          break;
        }
        case "verify-case": {
          YZ.ensureCase(state.caseId).then(() => {
          const ids = claimsOf(state.caseId).map((x) => x.id);
          let n = 0;
          ids.forEach((id) => { if (!progress.reviewed.includes(id)) { progress.reviewed.push(id); n += 1; } });
          save();
          toast(n ? `已核验 ${n} 条结论，写入本机记录` : "该病例结论均已核验");
          render();
          });
          break;
        }
        case "case": {
          state.caseId = id;
          state.regionId = null;
          state.claimId = null;
          state.applyTab = "workbench";
          YZ.ensureCase(id).then(() => { if (state.view !== "apply") go("apply"); else render(); });
          break;
        }
        case "case-open": {
          if (state.role === "doctor") {
            state.caseId = id; state.regionId = null; state.claimId = null; state.applyTab = "workbench";
            YZ.ensureCase(id).then(() => go("apply"));
          } else {
            state.modal = { type: "case", id };
            render();
          }
          break;
        }
        case "region": {
          state.regionId = id;
          state.claimId = null;
          render();
          break;
        }
        case "claim": {
          const cl = claimsOf(state.caseId).find((x) => x.id === id);
          state.claimId = id;
          if (cl && state.sync) state.regionId = cl.region_id;
          render();
          break;
        }
        case "claim-close": state.claimId = null; render(); break;
        case "sync": state.sync = !state.sync; render(); break;
        case "regions": state.showRegions = state.showRegions === false; render(); break;
        case "apply-tab": {
          state.applyTab = tab; state.teacherTab = tab;
          if (tab === "audit") YZ.loadAllParts().then(render); else render();
          break;
        }
        case "audit-filter": state.auditBrokenOnly = !state.auditBrokenOnly; render(); break;
        case "copy-claim": YZ.copyClaim(id); break;
        case "copy-summary": {
          const t = YZ.$("#summaryBox");
          YZ.copyText(t ? t.value : "", "交班摘要已复制");
          break;
        }
        case "download-summary": {
          const t = YZ.$("#summaryBox");
          YZ.download("交班摘要.md", t ? t.value : "");
          break;
        }

        case "teacher-tab": state.teacherTab = tab; render(); break;
        case "teacher-go": {
          state.teacherTab = tab; state.applyTab = tab;
          if (tab === "audit") YZ.loadAllParts().then(() => go("apply")); else go("apply");
          break;
        }
        case "verify-claim": {
          const i = progress.reviewed.indexOf(id);
          if (i >= 0) progress.reviewed.splice(i, 1); else progress.reviewed.push(id);
          save();
          toast(i >= 0 ? "已取消核验" : "已标记核验，写入本机记录");
          render();
          break;
        }
        case "assign-start": YZ.startAssignment(id); break;
        case "assign-del": YZ.deleteAssignment(id); break;
        case "copy-errors": {
          const text = ["# 讲评清单", "", ...YZ.topErrors().map((e, i) => `${i + 1}. ${e.name}：${e.count} 人次错选；建议用一例对照 + 一条条款条件讲评。`)].join("\n");
          YZ.copyText(text, "讲评清单已复制");
          break;
        }
        case "teacher-report": state.modal = { type: "report", title: "班级学习报告", text: YZ.teacherReportText() }; render(); break;
        case "report": state.modal = { type: "report", title: "学习报告", text: YZ.studentReportText() }; render(); break;

        case "projection": state.projection = { drillId: id, showAnswer: false }; render(); break;
        case "projection-toggle": if (state.projection) { state.projection.showAnswer = !state.projection.showAnswer; render(); } break;
        case "projection-exit": state.projection = null; render(); break;

        case "card-open": {
          state.modal = { type: "card", title: (sign(state.transferId) || {}).name || "", text: YZ.transferCardText() };
          render();
          break;
        }
        case "card-view": {
          const card = progress.cards.find((x) => x.id === id);
          if (card) { state.modal = { type: "card", title: card.title, text: card.text, existing: card.id }; render(); }
          break;
        }
        case "save-card": {
          const ta = YZ.$("#modalText");
          const text = ta ? ta.value : "";
          const s = sign(state.transferId) || DB.signs[0];
          progress.cards.unshift({ id: "C-" + Date.now().toString(36), title: `迁移卡 · ${s.name}`, text, date: YZ.today() });
          save();
          state.modal = null;
          toast("迁移卡已保存");
          render();
          break;
        }
        case "copy-modal": {
          const ta = YZ.$("#modalText");
          YZ.copyText(ta ? ta.value : "", "已复制");
          break;
        }
        case "download-modal": {
          const ta = YZ.$("#modalText");
          YZ.download((state.modal && state.modal.title ? state.modal.title : "RadioCheck 导出") + ".md", ta ? ta.value : "");
          break;
        }
        case "modal-close": state.modal = null; render(); break;

        case "export-json": YZ.download("RadioCheck 学习记录.json", JSON.stringify(progress, null, 2), "application/json"); break;
        case "reset": state.modal = { type: "confirm", title: "清空本地记录？", text: "将删除收藏、迁移卡、演练记录与自建任务；知识库数据不受影响。" }; render(); break;
        case "confirm-reset": {
          progress.learned = []; progress.bookmarks = []; progress.cards = []; progress.drills = {}; progress.checks = {}; progress.last = {}; progress.reviewed = [];
          progress.assignments = [];
          save();
          state.modal = null;
          toast("本地记录已清空");
          render();
          break;
        }
        case "check": break;
        default: break;
      }
    });

    app.addEventListener("input", (e) => {
      if (e.target.id === "learnQ") {
        state.query = e.target.value;
        const list = YZ.$("#signList");
        if (list) list.innerHTML = `<div class="sign-list-h"><b>征象词条</b><span>${YZ.filteredSigns().length} / ${DB.meta.counts.signs}</span></div>` + YZ.signListHTML();
      }
      if (e.target.id === "caseQ") {
        state.caseQuery = e.target.value;
        const list = YZ.$("#queueList");
        if (list) list.innerHTML = YZ.queueHTML();
      }
    });

    app.addEventListener("change", (e) => {
      if (e.target.id === "modSel") { state.modality = e.target.value; render(); }
      if (e.target.id === "transferSel") {
        state.transferId = e.target.value;
        state.signId = e.target.value;
        state.compareId = null;
        render();
      }
    });

    app.addEventListener("keydown", (e) => {
      if (e.target.id === "topQ" && e.key === "Enter") {
        const q = e.target.value.trim();
        if (state.view === "ask" && q && YZ.ASK) {
          YZ.ASK.AS.question = q;
          YZ.ASK.AS.result = YZ.ASK.run(YZ.ASK.AS);
          render();
          return;
        }
        state.query = q;
        go("learn");
      }
      if (e.target.id === "learnQ" && e.key === "Enter") {
        state.query = e.target.value;
        render();
      }
    });

    app.addEventListener("submit", (e) => {
      if (e.target.id === "assignForm") {
        e.preventDefault();
        YZ.addAssignment(e.target);
      }
    });
  }

  function keyboard() {
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (state.modal) { state.modal = null; render(); }
        else if (state.projection) { state.projection = null; render(); }
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        const q = YZ.$("#topQ");
        if (q) { e.preventDefault(); q.focus(); q.select(); }
        return;
      }
      if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
        const q = YZ.$("#topQ") || YZ.$("#learnQ");
        if (q) { e.preventDefault(); q.focus(); }
      }
      /* 学习页搜索框：Enter 直接问 Agent（Shift+Enter 走本地检索） */
      if (e.key === "Enter" && e.target && e.target.id === "learnQ") {
        e.preventDefault();
        const q = e.target.value;
        if (e.shiftKey) {
          state.query = q;
          render();
        } else {
          state.query = q;
          render();
          YZ.startAgentAsk(q);
        }
      }
    });
  }

  function init() {
    YZ.parseHash();
    bind();
    keyboard();
    window.addEventListener("popstate", () => { YZ.parseHash(); render(); });
    window.addEventListener("hashchange", () => { YZ.parseHash(); render(); });
    const boot = state.caseId ? YZ.ensureCase(state.caseId) : Promise.resolve();
    boot.then(render);
    // 页面加载后把首屏搜索框聚焦留给用户，不自动抢焦点
    console.info("[RadioCheck] 数据版本", DB.meta.version, DB.meta.counts);
  }

  init();
})(window.YZ);
