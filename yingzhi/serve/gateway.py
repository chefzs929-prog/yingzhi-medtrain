"""Agent Gateway：把一次提问转发给 DeepWorks 内置的 opencode server。

职责边界（写进注释，答辩时可展示）：
- 本文件只做：建会话、发消息、订阅事件、采集耗时、转发。
- 本文件不做：检索打分、判分规则、prompt 拼接、模型选择策略。
  智能全部在 DeepWorks 的 agent / skill / workflow 里。

事件来源：GET /event（SSE，全局流，按 sessionID 过滤）
关键事件：
  message.part.updated  part.type=tool → tool / state.status / callID
  message.part.delta    → 文本增量（真流式）
  session.idle          → 本轮结束
"""

import json
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

KB_TOOLS = {"read", "glob", "grep", "list", "ls"}
# 严格匹配四段式起点：必须有冒号，避免把英文思考里的「结论」误判为正文
CONCL = re.compile(r"结论\s*[:：]")


class GatewayError(RuntimeError):
    pass


class Gateway:
    def __init__(self, info, model_provider="dth", model_id="Auto", agent="yingzhi",
                 directory=".", timeout=60, kb_root=None, persona=None, mode="clean"):
        self.base = info["url"]
        self.auth = info["auth_header"]
        self.provider = model_provider
        self.model_id = model_id
        self.agent = agent
        self.directory = directory
        self.timeout = timeout
        # 实测：opencode server 会给 session 分配自己的 cwd，创建时的 directory 不一定生效。
        # 因此知识库路径必须显式给出绝对路径，否则 agent 会去全盘 find，既慢又搜不到。
        self.kb_root = kb_root
        # 实测：DeepWorks 部署下 opencode 的 cwd 是 managed-opencode-workdir，
        # 项目级 .opencode/agents/*.md 不会被加载（它从 cwd 向上找项目根）。
        # 所以人设改为随请求注入，来源仍是同一份 yingzhi.md，保证单一事实来源。
        self.persona = persona
        # clean：等生成完成再分片推送，正文干净（默认，演示用）
        # raw  ：直接转发模型增量，首字快但可能混入英文思考
        self.mode = mode
        # 有界多轮：同一 conversation_id 在 TTL 内复用 session。
        # 不做无界复用——实测上下文无限累积会把 7s 拖到 90s。
        self._sessions = {}
        self._lock = threading.Lock()
        self.session_ttl = 600

    # ---------- 基础 HTTP ----------

    def _locate(self, path):
        """给每个请求带上 directory：opencode 按它解析项目级 agent / skill / 配置。

        实测（2026-11-16）：不带 directory 时 /agent 只返回 7 个内置 agent，
        yingzhi 永远不出现；带上项目目录后立即返回 yingzhi。
        这不是可选项，是能否加载项目资产的关键。
        """
        if not self.directory:
            return path
        sep = "&" if "?" in path else "?"
        return "%s%sdirectory=%s" % (path, sep, urllib.parse.quote(self.directory, safe=""))

    def _request(self, method, path, payload=None, timeout=None):
        url = self.base + self._locate(path)
        data = None
        headers = {"Authorization": self.auth}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise GatewayError("HTTP %s %s -> %s" % (exc.code, path, detail))
        except Exception as exc:
            raise GatewayError("%s %s 失败：%s" % (method, path, exc))

    def health(self):
        return self._request("GET", "/config", timeout=5) is not None

    def agents(self):
        return [a.get("name") for a in (self._request("GET", "/agent") or [])]

    def skills(self):
        """当前实例真正加载到的技能 id 列表。"""
        return [s.get("name") for s in (self._request("GET", "/skill") or [])]

    # ---------- 会话 ----------

    def ensure_session(self, role="student", device="desktop", force=False, key=None):
        """取或建会话。

        key 优先用前端传来的 conversation_id：同一页面、同一轮对话复用，
        不同用户/不同页面互不污染。force=True 仍然强制新建（排障用）。
        超过 session_ttl 的会话自动淘汰，避免长期驻留把上下文拖慢。
        """
        key = key or "%s:%s" % (role, device)
        now = time.time()
        with self._lock:
            rec = self._sessions.get(key)
            if rec and not force and now - rec.get("at", 0) < self.session_ttl:
                rec["at"] = now
                return rec["id"]
            # 顺手清理过期会话，避免字典只增不减
            for k in [k for k, v in self._sessions.items()
                      if now - v.get("at", 0) > self.session_ttl]:
                self._sessions.pop(k, None)
        session = self._request("POST", "/session", {
            "title": "RadioCheck·%s·%s" % (role, device),
            "directory": self.directory,
        })
        sid = session["id"]
        with self._lock:
            self._sessions[key] = {"id": sid, "at": now}
        return sid

    # ---------- 主流程 ----------

    def ask(self, session_id, text, emit, context=None, hint=None):
        """emit(kind, payload) 会被逐条调用：trace / delta / done。

        返回汇总 dict，供落盘。
        """
        prompt = text
        head = []
        if self.persona:
            head.append(self.persona.strip())
        if self.kb_root:
            head.append(
                "知识库根目录：%s（只读；检索用 grep/read 指定具体文件，"
                "禁止 find / 或递归全盘搜索）" % self.kb_root
            )
        if context:
            # 页面上下文只做“定位提示”，不替代用户问题，也不当作证据。
            # 截断到 8 个键、每值 300 字，防止前端把整份报告/整张图塞进来。
            ctx = []
            for k, v in list(context.items())[:8]:
                if v in (None, "", [], {}):
                    continue
                ctx.append("%s：%s" % (k, str(v)[:300]))
            if ctx:
                head.append("【页面上下文】以下只用于定位，不是知识库证据：\n" + "\n".join(ctx))
        if hint:
            head.append("执行顺序是强制的，不要跳步，也不要先列目录：\n" + hint)
        if head:
            prompt = "\n\n".join(head + ["【用户问题】\n" + text])
        text = prompt

        q = queue.Queue()
        stop = threading.Event()
        state = {
            "first_token_at": None,
            "last_delta_at": None,
            "delta_chars": 0,
            "tools": {},
            "error": None,
            "final_text": "",
            "pending": "",
            "released": False,
        }

        def listener():
            headers = {"Authorization": self.auth, "Accept": "text/event-stream"}
            req = urllib.request.Request(self.base + self._locate("/event"), headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout + 30) as resp:
                    for raw in resp:
                        if stop.is_set():
                            break
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(line[5:].strip())
                        except Exception:
                            continue
                        props = event.get("properties") or {}
                        if props.get("sessionID") != session_id:
                            continue
                        q.put(event)
            except Exception as exc:
                q.put({"type": "__listener_error__", "error": str(exc)})

        def sender():
            body = {
                "parts": [{"type": "text", "text": text}],
                "model": {"providerID": self.provider, "modelID": self.model_id},
            }
            if self.agent:
                body["agent"] = self.agent
            try:
                result = self._request("POST", "/session/%s/message" % session_id, body)
                q.put({"type": "__message_result__", "result": result})
            except Exception as exc:
                q.put({"type": "__sender_error__", "error": str(exc)})

        threading.Thread(target=listener, daemon=True).start()
        time.sleep(0.25)  # 先订阅再发，避免丢首事件
        threading.Thread(target=sender, daemon=True).start()

        started = time.time()
        deadline = started + self.timeout
        result = None
        finished_at = None

        while time.time() < deadline:
            try:
                # 0.25s 一轮：session.idle 是终态，确认等待从 1.2s 降到 0.6s，
                # 首字延迟能省约 0.6s（实测 6.7s → 6.1s）。更频繁的轮询只多 4 次/秒。
                event = q.get(timeout=0.25)
            except queue.Empty:
                if finished_at and time.time() - finished_at > 0.6:
                    break
                continue

            etype = event.get("type")

            if etype == "__message_result__":
                result = event.get("result")
                finished_at = time.time()
                continue
            if etype in ("__sender_error__", "__listener_error__"):
                state["error"] = event.get("error")
                break

            props = event.get("properties") or {}
            now = time.time()

            if etype == "message.part.delta":
                delta = props.get("delta") or ""
                if not delta:
                    continue
                # 模型可能先输出「Let me search...」这类英文思考。四段式回答以「结论」开头，
                # 因此在首次出现「结论」前先缓冲，避免把检索过程播给观众。
                if self.mode == "clean":
                    state["last_delta_at"] = now
                    continue
                if not state["released"]:
                    state["pending"] += delta
                    match = CONCL.search(state["pending"])
                    if match:
                        state["released"] = True
                        delta = state["pending"][match.start():]
                        state["pending"] = ""
                    elif len(state["pending"]) > 1200:
                        state["released"] = True
                        delta = state["pending"]
                        state["pending"] = ""
                    else:
                        continue
                if state["first_token_at"] is None:
                    state["first_token_at"] = now
                state["last_delta_at"] = now
                state["delta_chars"] += len(delta)
                emit("delta", {"text": delta})
                continue

            if etype == "message.part.updated":
                part = props.get("part") or {}
                if part.get("type") != "tool":
                    continue
                call_id = part.get("callID") or part.get("id")
                status = ((part.get("state") or {}).get("status")) or "unknown"
                tool = part.get("tool") or "unknown"
                inp = (part.get("state") or {}).get("input") or {}
                detail = (inp.get("command") or inp.get("filePath") or inp.get("path")
                          or inp.get("pattern") or "")
                # 工具真实输出：用来判定「检索是否命中」，而不是只看 status=completed。
                # 一条 grep 返回空也照样是 completed，但那是未命中，不能算检索成功。
                out = (part.get("state") or {}).get("output") or ""
                out_lines = 0
                if out.strip():
                    out_lines = out.count("\n") + (0 if out.endswith("\n") else 1)
                # 技能调用的真实形态：opencode 的 skill 工具，input.name 是技能 id
                skill_name = ""
                if tool == "skill":
                    skill_name = str(inp.get("name") or inp.get("skill") or "").strip()
                rec = state["tools"].get(call_id)
                if rec is None:
                    rec = {"tool": tool, "skill": skill_name, "start": now,
                           "end": None, "detail": detail[:200], "out_lines": out_lines,
                           "out_head": out[:300]}
                    state["tools"][call_id] = rec
                elif detail and not rec.get("detail"):
                    rec["detail"] = detail[:200]
                if out_lines:
                    rec["out_lines"] = out_lines
                    rec["out_head"] = out[:300]
                if skill_name:
                    rec["skill"] = skill_name
                if status in ("completed", "error"):
                    rec["end"] = now
                    # 只有 skill 工具才算技能调用；bash/grep/read 是检索工具，
                    # 归入 kb_retrieve。之前把所有非 KB_TOOLS 的调用都标成
                    # skill_invoke，导致一次普通 bash 被显示成「技能调用」。
                    if tool == "skill":
                        stage, label = "skill_invoke", (skill_name or "skill")
                    else:
                        stage, label = "kb_retrieve", tool
                    span_ms = int((rec["end"] - rec["start"]) * 1000)
                    emit("trace", {
                        "stage": stage,
                        "skill": label,
                        "status": status,
                        "ms": span_ms,
                    })
                    # 明细事件只发一次：前端用它显示「查了什么、命中几行」，
                    # 与五段 trace 分开，避免把界面变成日志墙。
                    if not rec.get("emitted"):
                        rec["emitted"] = True
                        emit("tool", {
                            "tool": tool,
                            "skill": skill_name,
                            "detail": (rec.get("detail") or "")[:160],
                            "status": status,
                            "ms": span_ms,
                            "out_lines": int(rec.get("out_lines") or 0),
                        })
                continue

            if etype == "session.idle":
                finished_at = finished_at or now
                continue

        stop.set()

        # 整段都没有「结论」时（例如拒答），把缓冲内容补发出去，避免丢字
        if self.mode != "clean" and not state["released"] and state["pending"]:
            if state["first_token_at"] is None:
                state["first_token_at"] = time.time()
            emit("delta", {"text": state["pending"]})
            state["delta_chars"] += len(state["pending"])

        if result is None and state["error"]:
            raise GatewayError(state["error"])

        for part in ((result or {}).get("parts") or []):
            if part.get("type") == "text":
                state["final_text"] += part.get("text") or ""

        match = CONCL.search(state["final_text"])
        if match and match.start() > 0:
            state["final_text"] = state["final_text"][match.start():]

        if self.mode == "clean" and state["final_text"]:
            for i in range(0, len(state["final_text"]), 40):
                if state["first_token_at"] is None:
                    state["first_token_at"] = time.time()
                piece = state["final_text"][i:i + 40]
                state["delta_chars"] += len(piece)
                emit("delta", {"text": piece})
                time.sleep(0.012)

        total_ms = int((time.time() - started) * 1000)
        first_ms = int((state["first_token_at"] - started) * 1000) if state["first_token_at"] else total_ms
        # generate_ms 语义：模型实际生成耗时（started → 会话空闲）。
        # 不能再用 last_delta_at - first_token_at：clean 模式下 delta 是生成完之后才分片的，
        # 两者相减会得到负数（实测 -2005ms）。
        gen_end = finished_at or time.time()
        gen_ms = max(0, int((gen_end - started) * 1000))

        return {
            "text": state["final_text"],
            "first_token_ms": first_ms,
            "generate_ms": gen_ms,
            "total_ms": total_ms,
            "delta_chars": state["delta_chars"],
            "tools": list(state["tools"].values()),
            "model": "%s/%s" % (self.provider, self.model_id),
            "agent": self.agent,
            "session_id": session_id,
        }
