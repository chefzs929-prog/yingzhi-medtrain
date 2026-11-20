# Agent 接入指南（实测版 · v3.0）

> 日期：2026-11-16（v3.1 接口更新：2026-11-19）｜ 适用：影知 v3.0 / v3.1 动态服务层
> 结论先行：**入口是 DeepWorks 内置的 opencode server**，不是知识库 API，也不是技能 API。
> 本文所有结论都在本机实测过，含耗时数据与九个真实踩过的坑。
> v3.1 新增：`mode=auto/agent/llm`、有界多轮、`tool`/`followup` 事件、`/api/agent/capabilities`。
> 四页统一接入见 §10；缺口清单见 [功能缺口与补齐清单.md](功能缺口与补齐清单.md)。

---

## 1. 先回答「哪个入口可用」

| 候选 | 实测 | 判断 |
| --- | --- | --- |
| 自定义 agent / 技能 | 请求带 `directory` 后可加载：9 个 agent、37 个技能 | ✅ 可用（见坑 2） |
| 知识库问答 API | 只有 ontology 抽取动作，无问答检索端点 | ❌ 只能建库 |
| **opencode server（DeepWorks 引擎）** | 已跑通，HTTP + SSE | ✅ **选它** |

### 实测证据

| 项 | 结果 |
| --- | --- |
| 地址 | `http://127.0.0.1:<随机端口>`（本次 62665，重启即变） |
| 鉴权 | HTTP Basic Auth，凭证在引擎进程环境变量里 |
| 可用 agent | `build` `plan` `explore` `general` `summary` `title` `compaction` |
| 模型 | `dth/Auto`（同 provider 还有 Kimi-K3、GLM-5.3、DeepSeek-V4 等 10 个） |
| 一次问答 | **7–9 秒**，四段式，带 `SIGN-xxx` / `CLM-xxxx` / `SL-xxx` 可追溯 id |
| 工具事件 | 可观测：`grep` / `bash` / `glob` 的 `pending → running → completed` |

验证命令（不启服务也能跑）：

```bash
python3 yingzhi/tools/probe.py --ask "磨玻璃影在CT上怎么描述？"
```

### 为什么符合赛制

调的是 DeepWorks 自己的引擎进程、自己的配置、自己的模型，不是自建模型调用。
服务层只做转发与记账，核心链路仍在 DeepWorks 内。

---

## 2. 五步接入

### 第 1 步：发现入口

端口、进程名、router 端口每次启动都变，**三级探测**缺一不可：

```python
from discover import discover
info = discover()   # {"url": "...", "auth_header": "Basic ...", "pid": 17207}
```

1. 环境变量 `OPENCODE_SERVER_URL` / `_USERNAME` / `_PASSWORD`
2. `pgrep -f opencode-router` → `lsof` 拿 router 端口 → `GET /health` → 取 `opencode.url`
3. `pgrep -f sidecars/opencode` → `lsof` 拿监听端口 → `ps eww` 拿凭证 → `GET /config` 验活

凭证不落盘、不打印，只存内存，60 秒缓存。

### 第 2 步：建会话

```python
gw = Gateway(info, model_provider="dth", model_id="Auto", agent="yingzhi",
             kb_root="/绝对路径/kb/data", persona=人设, mode="clean")
sid = gw.ensure_session("student", "mobile", force=True)
```

**必须 `force=True`**，原因见坑 4。

### 第 3 步：发消息

```http
POST /session/{sid}/message
{
  "parts": [{"type": "text", "text": "<人设>\n<知识库路径>\n<建议检索命令>\n【用户问题】..."}],
  "model": {"providerID": "dth", "modelID": "Auto"},
  "agent": "build"
}
```

### 第 4 步：订阅事件

**先订阅再发消息**，否则丢首事件。

```http
GET /event          # SSE 全局流，按 properties.sessionID 过滤
```

| 事件 | 关键字段 | 用途 |
| --- | --- | --- |
| `message.part.delta` | `delta` | 文本增量 |
| `message.part.updated` | `part.type=="tool"`、`part.tool`、`part.state.status` | 生成 trace |
| `session.idle` | — | 本轮结束 |

### 第 5 步：落盘与回放

```
yingzhi/run/{run_id}/request.json   输入（可复现）
yingzhi/run/{run_id}/trace.json     五段 span + 耗时
yingzhi/run/{run_id}/answer.json    回答 + 出处
```

```bash
curl http://127.0.0.1:8800/api/trace/20261116-093616-m6et
```

---

## 3. 九个坑（每个都真实浪费过时间）

### 坑 1：端口、进程名、router 端口全是随机的

重启一次，opencode server 从 `60556` 变成 `62665`，router 从 `61051` 变成 `62673`。
第一版 `discover()` 写死了 router 端口，重启后直接报「找不到入口」。
**解法**：全部靠进程反查，见第 1 步。

### 坑 2：项目级 agent / skill 要靠 `directory` 参数加载（且有冷启动竞态）

第一版直接 `GET /agent`，只返回原生 7 个，`yingzhi` 永远不出现。

**根因不是「opencode 从自己的 cwd 向上找项目根」，而是请求没带 `directory`。**
opencode server 的默认实例 cwd 是

```
/Users/fz/Library/Application Support/com.deepexi.deepworks/managed-opencode-workdir
```

它不在项目里。但只要每个请求都带上项目目录：

```bash
GET /agent?directory=/Users/fz/Desktop/黑客松   → 9 个，含 yingzhi
GET /skill?directory=/Users/fz/Desktop/黑客松   → 37 个，含 retrieve-sign
```

项目级 `.opencode/agents/*.md` 和 `.opencode/skills/*` 都会被加载，**不需要注册到全局技能目录**。

**但存在冷启动竞态**：实例刚建好时，第一次 `/agent` 可能只返回内置项。
实测同一个服务进程重启后，`agent_ready` 有时 `true` 有时 `false`，而隔一秒再查一次就是 `true`。

**解法**：`gw.agents()` 重试 4 次（间隔 0.7s）；仍拿不到才退回「人设注入 build」。
`/api/health` 会如实报 `agent_ready` / `skill_ready`，不再靠猜。

### 坑 3：Agent 的工作目录不在你的项目里

实测让 agent 执行 `pwd`，返回上面那个 `managed-opencode-workdir`。
后果：`grep 磨玻璃影 kb/data/signs.jsonl` 返回 `No files found`，回答直接变成「库内无此内容」。

**解法**：知识库路径必须给**绝对路径**（`Gateway(kb_root=...)` 已内置）。

### 坑 4：复用 session 会让上下文无限累积

第一版按 `role:device` 缓存 session。连续问 4 次后，耗时从 7s 涨到 90s 超时。
**解法（v3.0）**：每次提问 `ensure_session(..., force=True)` 新建会话。
代价是单轮问答，没有多轮记忆——v3.0 不需要多轮。

**v3.1 更新**：已改为**有界多轮**——按 `conversation_id` 复用，10 分钟 TTL，
过期或换 id 即重开；仍不做无界复用。实测同一 id 连问两轮仍为 7.9s，没有回到 90s。
接入方式见 §10。

### 坑 5：不限制检索，agent 会乱搜然后挂死（最致命）

实测：不给精确命令时，agent 先 `find . -name signs.jsonl`，再全盘搜，2 分钟不返回。
表现是「第一次 bash 132ms 完成，然后卡住 70 秒」。

**解法（两层）**：

1. 服务端做**术语归一化**：在词条词典里找出现在问题中的最长名称（如「蜂窝征」→ 无，退回「蜂窝」→ 命中 `SIGN-012`），拼成一条精确命令，并强制先加载技能：

```
执行顺序是强制的，不要跳步，也不要先列目录：
1) 先调用 skill 工具，参数 name 为 retrieve-sign（加载检索规范）
2) 再执行：grep -m 5 "蜂窝影" /abs/kb/data/signs.jsonl
```

不显式要求时，实测 agent 会跳过 `skill` 工具直接 `bash grep`，`skill_invoke` 就只能标 `unavailable`。

2. 人设里写死：**最多执行 2 条命令，未命中就回答「库内暂无」，不要换关键词反复试**。

两层加上后，「胸膜凹陷征」这种库里确实没有的问题，8 秒返回「库内暂无」，不再挂死。

### 坑 6：模型会把英文思考混进正文

同一套配置下，模型有时会先输出 `Let me search the knowledge base...` 再输出四段式。
按「结论」字样截断也不行——它的思考里也会出现「结论」两个字。

**解法**：`mode="clean"`（默认）。
不消费模型的增量，等生成完成、从最终文本里按 `结论\s*[:：]` 提取四段，再按 40 字分片推送。
代价是首字延迟等于总耗时（7–9s），但正文 100% 干净，演示不会露怯。

需要极致首字延迟时用 `--mode raw`，但要接受偶发的思考残留。

### 坑 7：EventSource 不能发 POST

浏览器原生 `EventSource` 只支持 GET。前端必须用 `fetch` + `ReadableStream` 手工解析 SSE。
`yingzhi/app/probe.html` 有完整实现（约 60 行），可直接复制。

### 坑 8：降级文本会拼在已输出的思考后面

超时降级时，如果之前已经推过 delta，fallback 文本会直接接在后面，变成
`Let me search...结论：本地演示态未命中...`。

**解法**：降级前先发一个 `reset` 事件，前端收到后清空正文，再渲染 fallback。

### 坑 9：`ps eww` 在部分环境被限制

读不到进程环境时 `discover()` 会抛 `DiscoverError`。显式设置三个环境变量即可：

```bash
export OPENCODE_SERVER_URL=http://127.0.0.1:62665
export OPENCODE_SERVER_USERNAME=...
export OPENCODE_SERVER_PASSWORD=...
```

---

## 4. 启动与实测结果

```bash
python3 yingzhi/tools/probe.py --ask "磨玻璃影在CT上怎么描述？"   # 体检
python3 yingzhi/serve/main.py --port 8800                        # 启动
open http://127.0.0.1:8800/                                      # 探针页
python3 yingzhi/serve/main.py --port 8801 --offline              # 断网演练
```

### 稳定性实测（2026-11-16 10:10，技能接入后）

| 问题 | 耗时 | 结果 |
| --- | --- | --- |
| 磨玻璃影在CT上怎么描述？ | 6.7s | 四段式，`SIGN-001`，技能真实调用 57ms |
| 铺路石征是什么？ | 9.3s | 四段式，`SIGN-018` |
| 蜂窝征是什么？ | 10.3s | 四段式，诚实指向 `SIGN-012 蜂窝影` |
| 这个病怎么治疗 | 0.0s | 拦截，四段 skipped，`persist` 仍完成 |

### 真实 trace（技能已接入）

```
kb_retrieve    | bash           | completed   |  259 ms
skill_invoke   | retrieve-sign  | completed   |   57 ms
workflow       | None           | unavailable |    0 ms
agent_generate | dth/Auto       | completed   | 5787 ms
persist        | json           | completed   |    0 ms
```

`skill_invoke` 现在来自**真实的 skill 工具调用**：opencode 的 `skill` 工具被调用时，
`input.name` 就是技能 id，网关据此产出 span，不是自己编的耗时。

`workflow` 仍显示 `unavailable` 是**故意的**：工作流还没建。
宁可空着，也不编一段假耗时——这是 trace 可信度的底线。

### 降级链路

```
degraded: true, reason: "offline_mode"
skill_invoke: unavailable（降级时不假装调用了技能）
```

### 越界拦截

```
guard(内部) | blocked
五段: kb_retrieve / skill_invoke / workflow / agent_generate = skipped, persist = completed
done: {blocked: true, reason: "out_of_scope"}
```

---

## 5. 人设是怎么生效的

[yingzhi.md](../.opencode/agents/yingzhi.md) 是唯一事实来源，内容：

- 只读知识库，禁止 write / edit
- 固定四段（结论 / 依据 / 缺失 / 边界），首行必须是「结论：」
- 依据必须带 id，给不出就写「未命中」
- 不回答诊断、治疗、用药、手术、预后
- 最多 2 条检索命令，未命中即停
- 禁止输出检索过程与英文思考

opencode 按请求里的 `directory` 加载它（见坑 2），因此**人设由 agent 自己读**，
网关不再注入。`/api/health` 里可以看到当前状态：

```json
{"agent_ready": true, "persona_injected": false,
 "skill_ready": true, "skills": ["...", "retrieve-sign", "..."],
 "fallback_reason": null}
```

只有当冷启动重试 4 次后仍拿不到 `yingzhi`，才退回 `build` + 人设注入，
此时 `persona_injected` 变 `true`、`fallback_reason` 说明原因。两条路都不静默。

---

## 6. 前端怎么接

```js
const resp = await fetch('/api/ask', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({query, role, chain: 'kb_qa'})
});

for await (const {kind, payload} of parseSSE(resp.body)) {
  if (kind === 'trace')   setStage(payload.stage, payload);
  if (kind === 'reset')   clearAnswer();          // 降级时清空
  if (kind === 'delta')   append(payload.text);
  if (kind === 'citation') addCitation(payload);
  if (kind === 'done')    showRunId(payload.run_id);
}
```

`done` 之后把 `run_id` 存进记录，答辩时可直接 replay。

---

## 7. 能力边界（别夸大）

| 已经真实具备 | 还不具备 |
| --- | --- |
| 回答来自 DeepWorks 引擎 | 工作流编排（工作流没建） |
| 技能真实调用（`retrieve-sign`，skill 工具） | 多轮上下文（刻意不复用 session） |
| 工具调用可观测、可计时 | 班级级聚合（v3.2） |
| 每次运行可回放 | 引用 hash 校验（待 `citation_audit`） |
| 断网降级可见 | 语义检索（当前是词典 + 关键词） |
| 越界问题拦截 | |
| 未命中时诚实说「库内暂无」 | |

**最重要的一条**：接入 Agent 不会自动提升检索准确率。
第一次调用时 agent 没查库、凭记忆写了一大段，看着专业但**没有一条可追溯的 id**。
加上术语归一化与检索约束后，回答才带上 `SIGN-001`。

所以 v3.1 的重点不是接更多模型，而是「让每次回答都必须落到具体 id」。

---

## 8. 与 v3.0 验收的对应

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| SSE 事件顺序 | 通过 | `trace → delta+ → citation* → done`，无 session/guard 脏事件 |
| trace 五段 | 通过 | 检索/技能/生成/落盘真实；仅工作流 unavailable |
| 技能真实调用 | 通过 | `skill_invoke · retrieve-sign · 57ms` |
| 可回放 | 通过 | `GET /api/trace/{run_id}` |
| 降级可见 | 通过 | `--offline` 返回 `degraded=true` + `reset` |
| 越界拦截 | 通过 | `blocked=true`，四段 skipped，persist 完成 |
| 稳定性 | 通过 | 连续多问 6–10s，无降级 |
| 判分一致 | 未开始 | 依赖 `drill_score` 技能 |
| 引用 hash | 部分 | id 回查已实现；hash 校验未做 |

---

## 9. 诚实边界清单

这一节不是文案，是**能被机器验证的约束**。每条都写明代码位置与自证方式。

### 9.1 七条硬约束

| # | 约束 | 代码位置 | 怎么自证 |
| --- | --- | --- | --- |
| 1 | `completed` 不等于成功：检索命中 0 行必须标 `hit=false` | `main.py` `hit_lines()` | `GET /api/trace/{run_id}` 看 `hits` 字段 |
| 2 | `skill` 工具的正文不能被算成检索命中 | `main.py` `hit_lines()` 开头排除 `tool=="skill"` | 同上，技能 87 行不进 `hits` |
| 3 | 报错输出（`No such file` / `(no output)`）不算命中 | `main.py` `ERROR_MARKS` | 用错误路径检索，`hits` 仍为 0 |
| 4 | 宽泛扩展检索命中别的词条，不算本次命中 | `main.py` 按 `keyword in command` 过滤 | 问「胸膜凹陷征」，`hits=0` |
| 5 | 回答里的每个 id 必须回查知识库 | `main.py` `audit_citations()` | `citation_audit.unverified` 非空即编造 |
| 6 | 降级时技能段必须是 `unavailable`，不许装 | `main.py` `build_trace()` degraded 分支 | `--offline` 启动后看 trace |
| 7 | 非真实数据必须带徽章 | `core.js` `dataBadge()` | 班级人数/平均分上的 `演示数据`/`本地记录` |

### 9.2 引用自证的实际行为

id 格式必须照抄知识库真实结构，否则要么漏检、要么误报：

| 前缀 | 真实格式 | 说明 |
| --- | --- | --- |
| SIGN / CASE / CLM / SL | `SIGN-001` | 三段 |
| REG | `REG-001-RUL` | 带肺叶后缀 |
| GL | `GL-TIRADS-01` | 中缀是缩写，不是数字 |
| GRP | `GRP-LUNG-GGO` | 无数字 |
| STD | `STD-TIRADS` | 无数字 |
| ATLAS | `ATLAS-CHEST-PA-6` | 多段 + 末尾数字 |

```python
>>> audit_citations("结论：磨玻璃影（SIGN-001）。参见 SIGN-018、SIGN-016。")
(['SIGN-001', 'SIGN-018', 'SIGN-016'], [])

>>> audit_citations("SIGN-999 CLM-9999 GL-FAKE-99 REG-999-XXX")
([...], ['SIGN-999', 'CLM-9999', 'GL-FAKE-99', 'REG-999-XXX'])
```

`known_ids()` 扫 `kb/data/*.jsonl` 全部文件（1459 个 id），不写死文件名——
写死会把 `slices / groups / standards / atlas` 里的 id 全部误判成编造。

编造时前端会显示红色警示条：

```
引用校验未通过：SIGN-999、CLM-9999 不在知识库中，本回答不可作为依据。
```

**这条比降级警示优先级更高**——降级是能力不足且已标注，编造 id 是"看起来可信但错误"。

### 9.3 答辩口径：能说 / 不能说

| 可以当场证明 | 不要这样说 |
| --- | --- |
| 「回答来自 DeepWorks 引擎的 Agent 调用」 | 「我们做了语义检索」（实际是词典 + grep） |
| 「技能 `retrieve-sign` 被真实调用，耗时来自工具事件」 | 「我们编排了多技能工作流」（工作流没建） |
| 「每个 id 都回查过知识库，编造会被标红」 | 「引用 100% 准确」（只校验 id 存在，不校验语义） |
| 「未命中时如实回答库内暂无」 | 「覆盖率 90%」（没做过全量统计） |
| 「断网会降级并明确标注」 | 「离线也能正常回答」（离线只是关键词兜底） |
| 「每次运行可回放 trace.json」 | 「我们做了可观测平台」（只有单机 JSON） |

### 9.4 `/api/health` 的 honesty 块

答辩时不用口头解释，直接读：

```json
"honesty": {
  "real_llm": true,
  "real_skill": true,
  "real_workflow": false,
  "semantic_search": false,
  "multiturn_memory": false,
  "citation_audit": true,
  "trace_evidence": true
}
```

`false` 的每一项都有 note 说明原因，不隐藏。

---

---

## 10. v3.1 统一 Agent 接口（四页共用）

### 10.1 三步接入

```bash
# 1) 起服务：8800 是 Agent 服务，4191 是同源页面 + 代理
python3 yingzhi/serve/main.py --port 8800
python3 kb/scripts/serve_region.py --port 4191

# 2) 探测能力：先看 agent 是否真的加载，不要盲接
curl -s http://127.0.0.1:4191/api/agent/capabilities | python3 -m json.tool

# 3) 发一问：mode=auto 会先走 agent，失败且未产出内容才降级
curl -sN -X POST http://127.0.0.1:4191/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"磨玻璃影在CT上怎么描述？","surface":"clinic","mode":"auto"}'
```

`capabilities.agent.ready=false` 时不要假装接了 agent：页面会显示降级徽标，
`done.served_by` 会写 `llm` 或 `fallback`。

### 10.2 请求字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `query` | 是 | 用户问题 |
| `surface` | 否 | `clinic / teach / paper / compare`，用于会话隔离 |
| `conversation_id` | 否 | 同一 id 在 10 分钟内复用 session；不传则按 surface 生成 |
| `mode` | 否 | `auto`（默认）/ `agent` / `llm` |
| `context` | 否 | 页面上下文，最多 8 键、每值 300 字；只用于定位，不是证据 |
| `image` | 否 | data URL；视觉只负责定位，解释与引用仍由 agent 做 |

### 10.3 事件

```text
trace    五段步骤：kb_retrieve / skill_invoke / workflow / agent_generate / persist
tool     工具明细：tool / skill / detail / ms / out_lines（只发一次）
delta    正文增量
citation 真实 id → 引用卡片
followup 规则生成的追问 chips（source=rules）
reset    降级/重答前清空
done     served_by / degraded / reason / run_id / trace_url / followups
```

完整字段见 [功能缺口与补齐清单.md](功能缺口与补齐清单.md) 的“事件契约”。

### 10.4 前端两种接法

**A. 直接使用四页共用客户端（推荐）**

```js
const res = await window.YZAgent.ask({
  query: '这个征象怎么描述？',
  surface: 'clinic',
  context: { 病例: 'CASE-001', 分区: 'REG-001-RUL' },
}, {
  onEvent(kind, data) {
    if (kind === 'trace')    paintStep(data);     // 五段
    if (kind === 'tool')     appendTool(data);    // 查了什么
    if (kind === 'delta')    appendText(data.text);
    if (kind === 'citation') addCite(data);       // 真实 id
    if (kind === 'reset')    clearText();
  },
});
// res.done.served_by / res.done.reason / res.followups
```

**B. 需要不打断页面的追问抽屉**

```js
window.YZAgent.open({
  surface: 'teach',
  title: '问 Agent · 这个分区怎么讲',
  context: { 病例: 'CASE-001', 分区: 'REG-001-RUL' },
  seed: '请讲清这个分区的解剖边界和库内依据。',
});
```

抽屉已处理：SSE 解析、五段步骤条、工具明细、引用卡片、追问 chips、
降级徽标、trace 链接、Esc 关闭。不要在每个页面再复制一份。

### 10.5 四页入口

| 页面 | 入口 | 文件 |
| --- | --- | --- |
| 读片工作台 | 问答 tab（含步骤条/工具/引用/追问） | `kb/app/clinic.js` |
| 分区图谱 | 讲解卡底部“问 Agent” | `kb/app/teach.js` |
| 组卷自测 | 作答解析、错题卡“问 Agent” | `kb/app/paper.js` |
| 报告对照 | 每句下方“问 Agent” | `kb/app/compare.js` |

### 10.6 降级与排障

| 现象 | 先看 | 处理 |
| --- | --- | --- |
| `served_by=fallback` | `done.reason`、`/api/health.fallback_reason` | agent 未加载或 offline；不要把它当 agent 结果 |
| `skill_invoke=unavailable` | `capabilities.agent.skills` | 技能未加载；检查 `directory` 与 `retrieve-sign` |
| 4191 下 trace 404 | 是否重启过 `serve_region.py` | 新代理路由需要重启 |
| 第二轮明显变慢 | 是否复用同一个 `conversation_id` | 超过 TTL 会重开；不要无界复用 |
| 静态版按钮无反应 | `window.YZStatic` 是否存在 | 静态版没有 Agent 服务，只保留入口与提示 |
| `--offline` 仍在调 agent | `/api/health.agent_ready` | v3.1 已修；若仍为 true，说明跑的是旧进程 |


## 11. v3.2：陌生影像模板分区 + 网络文献双引用

### 11.1 两个新端点

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/vision/atlases` | 列出通用分区模板（26 个） |
| POST | `/api/vision/region` | 陌生影像按模板定位分区 |
| POST | `/api/lit/search` | PubMed 文献检索 |

`/api/ask` 增加 `research: true`，回答后自动追加文献引用。

### 11.2 陌生影像

```bash
curl -s -X POST http://127.0.0.1:4191/api/vision/region \
  -H 'Content-Type: application/json' \
  -d '{"modality":"CR","body_part":"胸部","view":"PA","bbox":[0.13,0.11,0.14,0.13]}'
```

返回的关键字段：

```json
{
  "ok": true,
  "source": "atlas_template",
  "atlas": { "id": "ATLAS-CHEST-PA-6", "n_cases": 74, "n_regions": 476 },
  "locate": {
    "status": "single",
    "primary": {
      "region": { "name": "右肺上野", "id": null },
      "coverage": 1.0,
      "template_n": 74,
      "agreement": 0.843,
      "source": "atlas_template"
    }
  },
  "honesty": { "template_inference": true, "human_annotated": false }
}
```

接入时注意：

- `region.id` 为 `null`：模板没有 `REG-xxx`，不要伪造；
- `agreement` 是模板一致度，不是模型置信度；
- `n_cases < 3` 的模板会带 `warning`，前端必须显示。

没有 bbox 时：

- 配了 `YZ_LLM_VISION_*`：服务端让视觉模型出框，再走模板；
- 没配：返回 `reason=needs_bbox`，要求前端框选，不猜。

### 11.3 双引用

```bash
curl -s -X POST http://127.0.0.1:4191/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"磨玻璃影在CT上怎么描述？","research":true,"modality":"CT"}'
```

`citation` 事件按 `kind` 分两组：

```json
{"id":"SIGN-001","kind":"local","title":"磨玻璃影"}
{"id":"PMID:33729289","kind":"literature","title":"Differential diagnoses of acute ground-glass opacity...",
 "journal":"Einstein (Sao Paulo)","year":"2021","url":"https://pubmed.ncbi.nlm.nih.gov/33729289/"}
```

`done` 汇总：

```json
{"citations":{"local":3,"literature":4},
 "literature":{"ok":true,"reason":null,"query":"(...) AND ("computed tomography") AND (...)","source":"PubMed"}}
```

前端必须把两组分开渲染。不要把“引用 7 条”混成一个数字，评委无法判断哪条来自库、哪条来自网络。

### 11.4 排障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `reason=no_english_term` | 问题/引用里没有英文术语 | 正常降级；不要让模型编文献 |
| `reason=needs_bbox` | 没配视觉模型且没给框 | 前端框选，或配置 `YZ_LLM_VISION_*` |
| `reason=no_atlas_match` | 没给 atlas_id 且 modality/body_part/view 不匹配 | 先 `GET /api/vision/atlases` 让用户选 |
| 文献 0 条但 `ok=true` | PubMed 无命中 | 显示“未检索到”，不要补假条目 |
| 4191 下 POST 卡住 | 旧代理用 SSE 转发 JSON | v3.2 已改为 `proxy_json_post`，需重启 4191 |

> 本指南仅用于医学影像教学与研究的技术接入，不构成诊断意见。病例影像均为公开许可素材。
