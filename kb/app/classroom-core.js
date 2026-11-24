/* RadioCheck · 课堂数据层
 * 教师建班 / 学生加入 / 布置作业 / 三题作答 / 本地评分 / 学情统计。
 *
 * 边界：
 *   - 纯静态，数据只存在当前浏览器的 localStorage，不做账号与服务端同步。
 *   - 评分只对照 chest_reading.json 的逐区状态与征象标注，不做诊断推断。
 *   - 同一浏览器可切换教师/学生角色，用于课堂演示与单机试做。
 */
(function (global) {
  "use strict";

  const KEY = "radiocheck.classroom.v1";
  const VERSION = 1;
  const STATUS = {
    abnormal: "异常",
    normal: "未见异常",
    unmentioned: "来源未提及",
    limited: "判读受限",
  };
  const CHEST_SIGNS = [
    "SIGN-001", "SIGN-002", "SIGN-003", "SIGN-004", "SIGN-005",
    "SIGN-006", "SIGN-007", "SIGN-008", "SIGN-009", "SIGN-010",
    "SIGN-011", "SIGN-012", "SIGN-013", "SIGN-014", "SIGN-015",
    "SIGN-016", "SIGN-017", "SIGN-018", "SIGN-019", "SIGN-020",
  ];
  const DEMO_CASES = [
    "CASE-001", "CASE-006", "CASE-036", "CASE-017", "CASE-204", "CASE-203",
  ];

  function uid(prefix) {
    return prefix + "-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }

  function now() {
    return new Date().toISOString();
  }

  function today() {
    return now().slice(0, 10);
  }

  function plusDays(n) {
    const d = new Date();
    d.setDate(d.getDate() + n);
    return d.toISOString().slice(0, 10);
  }

  function clamp(n, a, b) {
    return Math.max(a, Math.min(b, n));
  }

  function mean(nums) {
    const list = (nums || []).filter((n) => typeof n === "number" && !Number.isNaN(n));
    if (!list.length) return null;
    return Math.round((list.reduce((a, b) => a + b, 0) / list.length) * 10) / 10;
  }

  function hash(text) {
    let h = 2166136261;
    const s = String(text);
    for (let i = 0; i < s.length; i += 1) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function blank() {
    return {
      version: VERSION,
      teacher: { name: "", createdAt: "" },
      classes: [],
      activeRole: "",
      activeClassId: "",
      activeStudentId: "",
      attempts: [],
      posts: [],
    };
  }

  function normalize(db) {
    if (!db || typeof db !== "object" || db.version !== VERSION) return blank();
    if (!Array.isArray(db.classes)) db.classes = [];
    if (!Array.isArray(db.attempts)) db.attempts = [];
    if (!Array.isArray(db.posts)) db.posts = [];
    if (!db.teacher || typeof db.teacher !== "object") db.teacher = { name: "", createdAt: "" };
    db.classes.forEach((c) => {
      if (!Array.isArray(c.students)) c.students = [];
      if (!Array.isArray(c.assignments)) c.assignments = [];
      if (!Array.isArray(c.groups)) c.groups = [];
      c.assignments.forEach((a) => {
        if (!Array.isArray(a.caseIds)) a.caseIds = [];
        if (typeof a.passScore !== "number") a.passScore = 60;
      });
      c.groups.forEach((g) => {
        if (!Array.isArray(g.memberIds)) g.memberIds = [];
      });
    });
    db.posts.forEach((p) => {
      if (!Array.isArray(p.replies)) p.replies = [];
      if (p.status !== "resolved") p.status = "open";
    });
    return db;
  }

  function read() {
    try {
      const raw = global.localStorage.getItem(KEY);
      if (!raw) return blank();
      return normalize(JSON.parse(raw));
    } catch (e) {
      return blank();
    }
  }

  function write(db) {
    try {
      global.localStorage.setItem(KEY, JSON.stringify(normalize(db)));
      if (global.RCSync && global.RCSync.afterWrite) global.RCSync.afterWrite();
      return true;
    } catch (e) {
      return false;
    }
  }

  function reset() {
    try { global.localStorage.removeItem(KEY); } catch (e) { /* ignore */ }
    return blank();
  }

  function setRole(role) {
    const db = read();
    db.activeRole = role === "student" ? "student" : (role === "teacher" ? "teacher" : "");
    write(db);
    return db.activeRole;
  }

  function getRole() {
    return read().activeRole || "";
  }

  function classByCode(code) {
    const key = String(code || "").trim().toUpperCase();
    if (!key) return null;
    return read().classes.find((c) => String(c.code || "").toUpperCase() === key) || null;
  }

  function activeClass() {
    const db = read();
    return db.classes.find((c) => c.id === db.activeClassId) || null;
  }

  function activeStudent() {
    const db = read();
    const cls = db.classes.find((c) => c.id === db.activeClassId);
    if (!cls) return null;
    return cls.students.find((s) => s.id === db.activeStudentId) || null;
  }

  function uniqueCode(db) {
    const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    for (let attempt = 0; attempt < 40; attempt += 1) {
      let body = "";
      for (let i = 0; i < 4; i += 1) body += alphabet[Math.floor(Math.random() * alphabet.length)];
      const code = "RC-" + body;
      if (!db.classes.some((c) => c.code === code)) return code;
    }
    return "RC-" + Date.now().toString(36).slice(-4).toUpperCase();
  }

  function createClass(name, teacher) {
    const db = read();
    const cls = {
      id: uid("CLS"),
      code: uniqueCode(db),
      name: String(name || "未命名班级").trim().slice(0, 40) || "未命名班级",
      teacher: String(teacher || "带教老师").trim().slice(0, 30) || "带教老师",
      createdAt: now(),
      students: [],
      assignments: [],
    };
    db.classes.push(cls);
    db.activeClassId = cls.id;
    db.activeStudentId = "";
    db.teacher.name = cls.teacher;
    db.teacher.createdAt = cls.createdAt;
    db.activeRole = "teacher";
    write(db);
    return cls;
  }

  function addStudent(classId, name) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return { ok: false, error: "班级不存在" };
    const clean = String(name || "").trim().slice(0, 20);
    if (!clean) return { ok: false, error: "请填写学生姓名" };
    const exists = cls.students.find((s) => s.name === clean);
    if (exists) return { ok: true, student: exists, exists: true };
    const student = { id: uid("STU"), name: clean, joinedAt: now() };
    cls.students.push(student);
    write(db);
    return { ok: true, student, exists: false };
  }

  function removeStudent(classId, studentId) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return false;
    const before = cls.students.length;
    cls.students = cls.students.filter((s) => s.id !== studentId);
    db.attempts = db.attempts.filter((a) => !(a.classId === classId && a.studentId === studentId));
    if (db.activeStudentId === studentId) db.activeStudentId = "";
    write(db);
    return cls.students.length !== before;
  }

  function ensureStudent(classId, name) {
    const clean = String(name || "试做学生").trim().slice(0, 20) || "试做学生";
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return null;
    let student = cls.students.find((s) => s.name === clean);
    if (!student) {
      student = { id: uid("STU"), name: clean, joinedAt: now() };
      cls.students.push(student);
    }
    db.activeClassId = cls.id;
    db.activeStudentId = student.id;
    write(db);
    return student;
  }

  function setActiveStudent(classId, studentId) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls || !cls.students.some((s) => s.id === studentId)) return false;
    db.activeClassId = classId;
    db.activeStudentId = studentId;
    write(db);
    return true;
  }

  function joinClass(code, name) {
    const db = read();
    const key = String(code || "").trim().toUpperCase();
    const cls = db.classes.find((c) => String(c.code || "").toUpperCase() === key);
    if (!cls) return { ok: false, error: "班级码不存在，请向教师确认" };
    const clean = String(name || "").trim().slice(0, 20);
    if (!clean) return { ok: false, error: "请填写姓名" };
    let student = cls.students.find((s) => s.name === clean);
    if (!student) {
      student = { id: uid("STU"), name: clean, joinedAt: now() };
      cls.students.push(student);
    }
    db.activeClassId = cls.id;
    db.activeStudentId = student.id;
    db.activeRole = "student";
    write(db);
    return { ok: true, class: cls, student };
  }

  function leaveClass() {
    const db = read();
    // 保留 activeClassId：同一浏览器切回教师端时仍能回到该班；
    // 只清掉学生身份，学生端会回到“加入班级”表单。
    db.activeStudentId = "";
    write(db);
  }

  function createAssignment(input) {
    const db = read();
    const cls = db.classes.find((c) => c.id === input.classId);
    if (!cls) return { ok: false, error: "班级不存在" };
    const caseIds = Array.from(new Set((input.caseIds || []).map(String).filter(Boolean)));
    if (!caseIds.length) return { ok: false, error: "至少选择 1 个病例" };
    const title = String(input.title || "").trim().slice(0, 60);
    if (!title) return { ok: false, error: "请填写作业标题" };
    const assignment = {
      id: uid("ASG"),
      title,
      note: String(input.note || "").trim().slice(0, 200),
      due: String(input.due || "").slice(0, 10),
      caseIds,
      passScore: clamp(Number(input.passScore) || 60, 1, 100),
      createdAt: now(),
    };
    cls.assignments.unshift(assignment);
    write(db);
    return { ok: true, assignment, class: cls };
  }

  /* ---------------- 互助小组与组内论坛 ---------------- */

  function findGroup(classId, groupId) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return null;
    const group = (cls.groups || []).find((g) => g.id === groupId);
    return group ? { db, cls, group } : null;
  }

  function postView(db, cls, p) {
    const studentName = (id) => {
      const s = (cls.students || []).find((x) => x.id === id);
      return s ? s.name : "已移除学生";
    };
    const group = (cls.groups || []).find((g) => g.id === p.groupId);
    const replies = (p.replies || []).map((r) => ({
      ...r,
      authorName: studentName(r.studentId),
    }));
    return {
      ...p,
      authorName: studentName(p.studentId),
      groupName: group ? group.name : "已删除小组",
      replyCount: replies.length,
      replies,
    };
  }

  function groupsFor(classId, studentId) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return [];
    return (cls.groups || []).map((g) => {
      const posts = db.posts.filter((p) => p.classId === classId && p.groupId === g.id);
      const lastAt = posts.reduce((m, p) => {
        const t = String(p.updatedAt || p.createdAt || "");
        return t > m ? t : m;
      }, "");
      return {
        ...g,
        joined: !!(studentId && (g.memberIds || []).includes(studentId)),
        stats: {
          members: (g.memberIds || []).length,
          posts: posts.length,
          unresolved: posts.filter((p) => p.status !== "resolved").length,
          lastAt,
        },
      };
    }).sort((a, b) => String(b.createdAt || "").localeCompare(String(a.createdAt || "")));
  }

  function createGroup(classId, input) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return { ok: false, error: "班级不存在" };
    const name = String((input || {}).name || "").trim().slice(0, 24);
    if (!name) return { ok: false, error: "请填写小组名称" };
    if ((cls.groups || []).some((g) => g.name === name)) {
      return { ok: false, error: "同名小组已存在" };
    }
    const group = {
      id: uid("GRP"),
      name,
      topic: String((input || {}).topic || "").trim().slice(0, 40),
      note: String((input || {}).note || "").trim().slice(0, 160),
      createdBy: String((input || {}).createdBy || "teacher"),
      createdAt: now(),
      memberIds: [],
    };
    if (input && input.studentId && (cls.students || []).some((s) => s.id === input.studentId)) {
      group.memberIds.push(input.studentId);
    }
    cls.groups.unshift(group);
    write(db);
    return { ok: true, group };
  }

  function joinGroup(classId, groupId, studentId) {
    const found = findGroup(classId, groupId);
    if (!found) return { ok: false, error: "小组不存在" };
    if (!(found.cls.students || []).some((s) => s.id === studentId)) {
      return { ok: false, error: "学生身份不存在" };
    }
    if (!found.group.memberIds.includes(studentId)) {
      found.group.memberIds.push(studentId);
      write(found.db);
    }
    return { ok: true, group: found.group };
  }

  function leaveGroup(classId, groupId, studentId) {
    const found = findGroup(classId, groupId);
    if (!found) return false;
    const before = found.group.memberIds.length;
    found.group.memberIds = found.group.memberIds.filter((id) => id !== studentId);
    write(found.db);
    return found.group.memberIds.length !== before;
  }

  function deleteGroup(classId, groupId) {
    const found = findGroup(classId, groupId);
    if (!found) return false;
    found.cls.groups = found.cls.groups.filter((g) => g.id !== groupId);
    found.db.posts = found.db.posts.filter((p) => !(p.classId === classId && p.groupId === groupId));
    write(found.db);
    return true;
  }

  function createPost(input) {
    const found = findGroup(input.classId, input.groupId);
    if (!found) return { ok: false, error: "小组不存在" };
    if (!found.group.memberIds.includes(input.studentId)) {
      return { ok: false, error: "请先加入小组再发帖" };
    }
    const title = String(input.title || "").trim().slice(0, 60);
    const body = String(input.body || "").trim().slice(0, 1200);
    if (!title) return { ok: false, error: "请填写问题标题" };
    if (!body) return { ok: false, error: "请填写问题描述" };
    const at = input.at || now();
    const post = {
      id: uid("POST"),
      classId: input.classId,
      groupId: input.groupId,
      studentId: input.studentId,
      title,
      body,
      caseId: String(input.caseId || "").slice(0, 24),
      zoneId: String(input.zoneId || "").slice(0, 24),
      zoneName: String(input.zoneName || "").slice(0, 40),
      signId: String(input.signId || "").slice(0, 24),
      signName: String(input.signName || "").slice(0, 40),
      status: "open",
      createdAt: at,
      updatedAt: at,
      replies: [],
    };
    found.db.posts.push(post);
    write(found.db);
    return { ok: true, post: postView(found.db, found.cls, post) };
  }

  function replyPost(input) {
    const db = read();
    const cls = db.classes.find((c) => c.id === input.classId);
    if (!cls) return { ok: false, error: "班级不存在" };
    const post = db.posts.find((p) => p.id === input.postId && p.classId === input.classId);
    if (!post) return { ok: false, error: "帖子不存在" };
    const group = (cls.groups || []).find((g) => g.id === post.groupId);
    if (!group || !group.memberIds.includes(input.studentId)) {
      return { ok: false, error: "请先加入小组再回复" };
    }
    const body = String(input.body || "").trim().slice(0, 600);
    if (!body) return { ok: false, error: "请填写回复内容" };
    const at = input.at || now();
    post.replies.push({
      id: uid("REP"),
      studentId: input.studentId,
      body,
      at,
    });
    post.updatedAt = at;
    write(db);
    return { ok: true, post: postView(db, cls, post) };
  }

  function setPostStatus(classId, postId, status) {
    const db = read();
    const post = db.posts.find((p) => p.id === postId && p.classId === classId);
    if (!post) return false;
    post.status = status === "resolved" ? "resolved" : "open";
    post.updatedAt = now();
    write(db);
    return true;
  }

  function deletePost(classId, postId) {
    const db = read();
    const before = db.posts.length;
    db.posts = db.posts.filter((p) => !(p.classId === classId && p.id === postId));
    write(db);
    return db.posts.length !== before;
  }

  function postsFor(classId, groupId, filter, studentId) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return [];
    let rows = db.posts.filter((p) => p.classId === classId && (!groupId || p.groupId === groupId));
    if (filter === "open") rows = rows.filter((p) => p.status !== "resolved");
    else if (filter === "resolved") rows = rows.filter((p) => p.status === "resolved");
    else if (filter === "mine" && studentId) {
      rows = rows.filter((p) => p.studentId === studentId ||
        (p.replies || []).some((r) => r.studentId === studentId));
    }
    return rows
      .map((p) => postView(db, cls, p))
      .sort((a, b) => String(b.updatedAt || b.createdAt || "").localeCompare(String(a.updatedAt || a.createdAt || "")));
  }

  function seedDemoGroups(classId) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return { ok: false, error: "班级不存在" };
    if ((cls.groups || []).length) return { ok: true, exists: true, created: 0 };
    if (!(cls.students || []).length) return { ok: false, error: "请先添加学生" };
    const names = [
      ["肺野读片互助组", "气腔影与正常对照", "先定位，再描述密度与边界；不确定时把分区框发到帖子里。"],
      ["胸膜与心影小组", "气胸、积液、心影增大", "重点讨论肋膈角、胸膜线和心影轮廓。"],
      ["影像出处核对组", "双引用与文献溯源", "每个结论至少附一条病例出处和一条文献出处。"],
    ];
    const groups = names.map(([name, topic, note]) => createGroup(classId, { name, topic, note }).group);
    const students = cls.students;
    groups.forEach((g) => students.forEach((s) => joinGroup(classId, g.id, s.id)));
    const seeds = [
      {
        gi: 0, si: 0, caseId: "CASE-007",
        title: "双侧下肺野密度增高，怎么区分实变和积液？",
        body: "我在 CASE-007 看到双侧下肺野密度增高，但肋膈角还能看见。应该先选实变还是胸腔积液？看空气支气管征就够吗？",
        replies: [
          [1, "我会先看肋膈角是否变钝，再看有没有空气支气管征；但最后还是要回到该区库内标注，不能只凭一个征象。"],
          [2, "建议把分区框和出处一起贴出来，这样别人能复现你的观察。"],
        ],
      },
      {
        gi: 0, si: 1, caseId: "CASE-016",
        title: "粟粒样结节和普通结节在胸片上怎么描述？",
        body: "CASE-016 的标题是双肺弥漫粟粒样结节，但库内只挂了 SIGN-003 结节。写阅片记录时可以直接写粟粒样吗？",
        replies: [
          [0, "库内只对 SIGN-003 负责；粟粒样是分布描述，建议写成“弥漫分布的小结节”，并注明是教学描述，不是诊断。"],
        ],
      },
      {
        gi: 1, si: 3, caseId: "CASE-036",
        title: "气胸病例的分区框为什么只框了外侧？",
        body: "CASE-036 选异常区时，我点了外侧带。胸膜线本身算一个分区吗？还是应该选整个患侧肺野？",
        replies: [
          [4, "按库内分区框选，不要自己画新的解剖区；如果边界跨区，选最贴近胸膜线的那个异常区，并在帖子中说明。"],
        ],
      },
      {
        gi: 2, si: 2, caseId: "CASE-203",
        title: "肺结核的文献引用应该引哪一条？",
        body: "CASE-203 同时有实变和结节。问答里给的是 SIGN-002 和 SIGN-003 的来源，但我想引用结核相关的概念，应该怎么标？",
        replies: [
          [5, "概念命中时要标“关联”，不能把 related_sign_ids 当成原文依据；文献引用只引 signs.jsonl 里实际挂载的来源。"],
        ],
      },
    ];
    let created = 0;
    seeds.forEach((seed, idx) => {
      const at = new Date(Date.now() - (seeds.length - idx) * 3600 * 1000).toISOString();
      const res = createPost({
        classId,
        groupId: groups[seed.gi].id,
        studentId: students[seed.si % students.length].id,
        title: seed.title,
        body: seed.body,
        caseId: seed.caseId,
        at,
      });
      if (!res.ok) return;
      created += 1;
      seed.replies.forEach(([si, body], ri) => {
        replyPost({
          classId,
          postId: res.post.id,
          studentId: students[si % students.length].id,
          body,
          at: new Date(Date.now() - (seeds.length - idx) * 3600 * 1000 + (ri + 1) * 600 * 1000).toISOString(),
        });
      });
    });
    return { ok: true, created, groups: groups.length };
  }

  function deleteAssignment(classId, assignmentId) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return false;
    const before = cls.assignments.length;
    cls.assignments = cls.assignments.filter((a) => a.id !== assignmentId);
    db.attempts = db.attempts.filter((a) => a.assignmentId !== assignmentId);
    write(db);
    return cls.assignments.length !== before;
  }

  function attemptsFor(classId, assignmentId, studentId) {
    const rows = read().attempts
      .filter((a) => a.classId === classId && a.assignmentId === assignmentId && a.studentId === studentId)
      .sort((a, b) => String(a.at).localeCompare(String(b.at)));
    const map = new Map();
    rows.forEach((row) => map.set(row.caseId, row));
    return Array.from(map.values()).sort((a, b) => String(a.at).localeCompare(String(b.at)));
  }

  function latestAttempt(classId, assignmentId, studentId, caseId) {
    return attemptsFor(classId, assignmentId, studentId).find((a) => a.caseId === caseId) || null;
  }

  function saveAttempt(input) {
    const db = read();
    const cls = db.classes.find((c) => c.id === input.classId);
    if (!cls) return null;
    const assignment = cls.assignments.find((a) => a.id === input.assignmentId);
    if (!assignment) return null;
    if (!cls.students.some((s) => s.id === input.studentId)) return null;
    if (!assignment.caseIds.includes(input.caseId)) return null;
    const rawAnswers = input.answers || {};
    const zoneIds = Array.isArray(rawAnswers.zoneIds)
      ? rawAnswers.zoneIds.map((id) => String(id || "")).filter((id) => id && id !== "none")
      : (rawAnswers.zoneId && rawAnswers.zoneId !== "none" ? [String(rawAnswers.zoneId)] : []);
    const attempt = {
      id: uid("ATT"),
      classId: input.classId,
      assignmentId: input.assignmentId,
      studentId: input.studentId,
      caseId: input.caseId,
      answers: {
        zoneId: String(rawAnswers.zoneId || zoneIds[0] || (rawAnswers.zoneNone ? "none" : "")),
        zoneIds,
        zoneNone: !!rawAnswers.zoneNone,
        status: String(rawAnswers.status || ""),
        signs: Array.isArray(rawAnswers.signs) ? rawAnswers.signs.slice() : [],
      },
      score: clamp(Number(input.score) || 0, 0, 100),
      detail: input.detail || {},
      at: input.at || now(),
    };
    db.attempts.push(attempt);
    write(db);
    return attempt;
  }

  function caseAnswer(c) {
    const ab = c.zones.filter((z) => z.status === "abnormal");
    let status = "normal";
    if (ab.length) status = "abnormal";
    else if (c.zones.some((z) => z.status === "normal")) status = "normal";
    else if (c.zones.some((z) => z.status === "limited")) status = "limited";
    else if (c.zones.some((z) => z.status === "unmentioned")) status = "unmentioned";
    return {
      zoneId: ab.length ? ab[0].id : "none",
      zoneIds: ab.map((z) => z.id),
      abnormalZoneIds: ab.map((z) => z.id),
      status,
      signs: (c.signs || []).slice(),
    };
  }

  function signOptions(c) {
    const correct = (c.signs || []).slice();
    const pool = CHEST_SIGNS.filter((id) => !correct.includes(id));
    const seed = hash(c.id);
    const picked = [];
    for (let i = 0; picked.length < 4 && i < pool.length * 2; i += 1) {
      const id = pool[(seed + i * 3) % pool.length];
      if (!picked.includes(id) && !correct.includes(id)) picked.push(id);
    }
    const all = correct.concat(picked);
    all.sort((a, b) => (hash(a + "|" + c.id) % 997) - (hash(b + "|" + c.id) % 997));
    return { correct, options: all };
  }

  function signScore(correct, picked) {
    const cset = new Set(correct || []);
    const pset = new Set(picked || []);
    if (!cset.size) return pset.size ? 0 : 1;
    let hit = 0;
    let wrong = 0;
    pset.forEach((id) => {
      if (cset.has(id)) hit += 1;
      else wrong += 1;
    });
    return clamp((hit - wrong * 0.5) / cset.size, 0, 1);
  }

  function gradeCase(c, answers) {
    const expected = caseAnswer(c);
    const raw = answers || {};
    const legacyId = String(raw.zoneId || "");
    const rawIds = Array.isArray(raw.zoneIds) ? raw.zoneIds : (legacyId ? [legacyId] : []);
    const zoneIds = rawIds.map((id) => String(id || "")).filter((id) => id && id !== "none");
    const zoneNone = !!raw.zoneNone || (!zoneIds.length && (legacyId === "none" || rawIds.includes("none")));
    const ans = {
      zoneIds,
      zoneNone,
      status: String(raw.status || ""),
      signs: Array.isArray(raw.signs) ? raw.signs.slice() : [],
    };
    const selected = zoneIds
      .map((id) => c.zones.find((z) => z.id === id))
      .filter(Boolean);
    const expectedIds = expected.abnormalZoneIds;
    const hits = zoneIds.filter((id) => expectedIds.includes(id)).length;
    const wrong = zoneIds.filter((id) => !expectedIds.includes(id)).length;
    const zoneRatio = expectedIds.length
      ? clamp((hits - wrong * 0.5) / expectedIds.length, 0, 1)
      : (zoneNone ? 1 : 0);
    const zoneOk = expectedIds.length ? (hits === expectedIds.length && wrong === 0) : zoneNone;
    const expectedZones = expectedIds
      .map((id) => c.zones.find((z) => z.id === id))
      .filter(Boolean);
    const expectedStatus = expectedZones.length
      && expectedZones.every((z) => z.status === expectedZones[0].status)
      ? expectedZones[0].status
      : expected.status;
    const statusOk = selected.length
      ? selected.every((z) => z.status === ans.status)
      : ans.status === expectedStatus;
    const signRatio = signScore(expected.signs, ans.signs);
    const score = Math.round(zoneRatio * 40 + statusOk * 30 + signRatio * 30);
    return {
      score,
      detail: {
        zoneOk,
        zoneRatio: Math.round(zoneRatio * 100) / 100,
        statusOk,
        signRatio: Math.round(signRatio * 100) / 100,
        zonePoints: Math.round(zoneRatio * 40),
        statusPoints: statusOk ? 30 : 0,
        signPoints: Math.round(signRatio * 30),
        answeredZoneId: zoneIds[0] || (zoneNone ? "none" : ""),
        answeredZoneIds: zoneIds,
        answeredZoneNone: zoneNone,
        answeredStatus: ans.status,
        answeredSigns: ans.signs,
        correctZoneIds: expectedIds,
        expectedZoneId: expected.zoneId,
        expectedStatus,
        expectedSigns: expected.signs,
      },
    };
  }

  function assignmentStats(classId, assignmentId) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return null;
    const assignment = cls.assignments.find((a) => a.id === assignmentId);
    if (!assignment) return null;
    const perStudent = cls.students.map((s) => {
      const rows = attemptsFor(classId, assignmentId, s.id);
      const last = rows.length ? rows[rows.length - 1].at : "";
      return {
        id: s.id,
        name: s.name,
        completed: rows.length,
        total: assignment.caseIds.length,
        avg: mean(rows.map((r) => r.score)),
        lastAt: last,
      };
    });
    const latest = [];
    perStudent.forEach((s) => {
      latest.push.apply(latest, attemptsFor(classId, assignmentId, s.id));
    });
    const perCase = assignment.caseIds.map((caseId) => {
      const rows = latest.filter((r) => r.caseId === caseId);
      return {
        caseId,
        attempts: rows.length,
        avg: mean(rows.map((r) => r.score)),
        zoneRate: mean(rows.map((r) => (r.detail && r.detail.zoneOk ? 100 : 0))),
        statusRate: mean(rows.map((r) => (r.detail && r.detail.statusOk ? 100 : 0))),
        signRate: mean(rows.map((r) => (r.detail ? r.detail.signRatio * 100 : 0))),
        passRate: mean(rows.map((r) => (r.score >= assignment.passScore ? 100 : 0))),
      };
    });
    const cells = perStudent.reduce((n, s) => n + s.total, 0);
    const submitted = latest.length;
    const errors = latest
      .filter((r) => r.score < assignment.passScore)
      .sort((a, b) => a.score - b.score)
      .map((r) => {
        const student = cls.students.find((s) => s.id === r.studentId);
        return {
          id: r.id,
          studentId: r.studentId,
          studentName: student ? student.name : "已移除学生",
          caseId: r.caseId,
          score: r.score,
          detail: r.detail,
          at: r.at,
        };
      });
    return {
      class: cls,
      assignment,
      students: perStudent,
      cases: perCase,
      latest,
      errors,
      totals: {
        students: cls.students.length,
        cells,
        submitted,
        rate: cells ? Math.round((submitted / cells) * 1000) / 10 : 0,
        avg: mean(latest.map((r) => r.score)),
        passRate: submitted
          ? Math.round((latest.filter((r) => r.score >= assignment.passScore).length / submitted) * 1000) / 10
          : 0,
        zoneRate: mean(latest.map((r) => (r.detail && r.detail.zoneOk ? 100 : 0))),
        statusRate: mean(latest.map((r) => (r.detail && r.detail.statusOk ? 100 : 0))),
        signRate: mean(latest.map((r) => (r.detail ? r.detail.signRatio * 100 : 0))),
      },
    };
  }

  function classStats(classId) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return null;
    let cells = 0;
    let submitted = 0;
    const scores = [];
    const passes = [];
    cls.assignments.forEach((a) => {
      cls.students.forEach((s) => {
        cells += a.caseIds.length;
        const rows = attemptsFor(classId, a.id, s.id);
        submitted += rows.length;
        rows.forEach((r) => {
          scores.push(r.score);
          passes.push(r.score >= a.passScore ? 1 : 0);
        });
      });
    });
    return {
      class: cls,
      students: cls.students.length,
      assignments: cls.assignments.length,
      cells,
      submitted,
      rate: cells ? Math.round((submitted / cells) * 1000) / 10 : 0,
      avg: mean(scores),
      passRate: passes.length ? Math.round((passes.reduce((a, b) => a + b, 0) / passes.length) * 1000) / 10 : null,
    };
  }

  function studentStats(classId, studentId) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return null;
    const student = cls.students.find((s) => s.id === studentId);
    if (!student) return null;
    const assignments = cls.assignments.map((a) => {
      const rows = attemptsFor(classId, a.id, studentId);
      return {
        assignment: a,
        completed: rows.length,
        total: a.caseIds.length,
        avg: mean(rows.map((r) => r.score)),
        lastAt: rows.length ? rows[rows.length - 1].at : "",
        attempts: rows,
      };
    });
    const all = [];
    assignments.forEach((x) => all.push.apply(all, x.attempts));
    const errors = all
      .filter((r) => r.score < 80)
      .sort((a, b) => a.score - b.score);
    return {
      class: cls,
      student,
      assignments,
      attempts: all,
      submitted: all.length,
      cells: assignments.reduce((n, x) => n + x.total, 0),
      avg: mean(all.map((r) => r.score)),
      errors,
    };
  }

  function taskContext(taskId, studentId) {
    const db = read();
    for (const cls of db.classes) {
      const assignment = cls.assignments.find((a) => a.id === taskId);
      if (!assignment) continue;
      const student = cls.students.find((s) => s.id === studentId) || null;
      if (!student) {
        return { ok: false, error: "没有找到学生身份，请返回课堂重新加入班级" };
      }
      return {
        ok: true,
        classId: cls.id,
        classInfo: cls,
        assignment,
        student,
        attempts: attemptsFor(cls.id, assignment.id, student.id),
      };
    }
    return { ok: false, error: "作业不存在或已被删除" };
  }

  function seedDemoClass() {
    const cls = createClass("2026 春季影像规培班", "演示带教");
    ["张同学", "李同学", "王同学", "赵同学", "陈同学", "周同学"].forEach((name) => {
      addStudent(cls.id, name);
    });
    createAssignment({
      classId: cls.id,
      title: "胸片基础：定位与征象",
      note: "先定位异常分区，再判断状态与征象；提交后可对照分区所见与出处。",
      due: plusDays(7),
      caseIds: DEMO_CASES.slice(),
    });
    const db = read();
    db.activeClassId = cls.id;
    db.activeRole = "teacher";
    write(db);
    return cls;
  }

  function seedDemoAttempts(classId, assignmentId, cases) {
    const db = read();
    const cls = db.classes.find((c) => c.id === classId);
    if (!cls) return { ok: false, error: "班级不存在" };
    const assignment = cls.assignments.find((a) => a.id === assignmentId);
    if (!assignment) return { ok: false, error: "作业不存在" };
    if (!Array.isArray(cases) || !cases.length) return { ok: false, error: "缺少病例数据" };
    const byId = new Map(cases.map((c) => [c.id, c]));
    const patterns = [
      { zone: 1, status: 1, sign: 1 },
      { zone: 0, status: 1, sign: 1 },
      { zone: 1, status: 0, sign: 0.5 },
      { zone: 1, status: 1, sign: 0.5 },
      { zone: 0, status: 0, sign: 0 },
      { zone: 1, status: 1, sign: 1 },
    ];
    let created = 0;
    cls.students.forEach((student, si) => {
      assignment.caseIds.forEach((caseId, ci) => {
        const c = byId.get(caseId);
        if (!c) return;
        if (latestAttempt(classId, assignmentId, student.id, caseId)) return;
        const expected = caseAnswer(c);
        const pattern = patterns[(si + ci) % patterns.length];
        let zoneIds = expected.abnormalZoneIds.slice();
        if (!pattern.zone) {
          if (!zoneIds.length) zoneIds = c.zones[0] ? [c.zones[0].id] : [];
          else {
            const other = c.zones.find((z) => z.status !== "abnormal");
            zoneIds = other ? [other.id] : [];
          }
        }
        const zone = c.zones.find((z) => z.id === zoneIds[0]) || null;
        const rightStatus = zone ? zone.status : expected.status;
        let status = rightStatus;
        if (!pattern.status) {
          status = rightStatus === "abnormal" ? "normal" : "abnormal";
        }
        let signs = expected.signs.slice();
        if (pattern.sign === 0.5) signs = signs.slice(0, Math.max(1, Math.ceil(signs.length / 2)));
        if (pattern.sign === 0) signs = expected.signs.length ? [] : [CHEST_SIGNS[(si + ci) % CHEST_SIGNS.length]];
        const graded = gradeCase(c, { zoneIds, zoneNone: zoneIds.length === 0, status, signs });
        const at = new Date(Date.now() - (6 - si) * 3600 * 1000 - ci * 60 * 1000).toISOString();
        saveAttempt({
          classId,
          assignmentId,
          studentId: student.id,
          caseId,
          answers: { zoneIds, zoneNone: zoneIds.length === 0, status, signs },
          score: graded.score,
          detail: graded.detail,
          at,
        });
        created += 1;
      });
    });
    return { ok: true, created };
  }

  function statusLabel(status) {
    return STATUS[status] || status || "未标注";
  }

  global.RCClass = {
    KEY,
    VERSION,
    STATUS,
    CHEST_SIGNS,
    DEMO_CASES,
    read,
    write,
    reset,
    setRole,
    getRole,
    classByCode,
    activeClass,
    activeStudent,
    createClass,
    seedDemoClass,
    addStudent,
    removeStudent,
    ensureStudent,
    setActiveStudent,
    joinClass,
    leaveClass,
    createAssignment,
    deleteAssignment,
    attemptsFor,
    latestAttempt,
    saveAttempt,
    caseAnswer,
    signOptions,
    signScore,
    gradeCase,
    assignmentStats,
    classStats,
    studentStats,
    taskContext,
    seedDemoAttempts,
    groupsFor,
    createGroup,
    joinGroup,
    leaveGroup,
    deleteGroup,
    createPost,
    replyPost,
    setPostStatus,
    deletePost,
    postsFor,
    seedDemoGroups,
    statusLabel,
    mean,
    today,
    plusDays,
    uid,
  };
})(window);
