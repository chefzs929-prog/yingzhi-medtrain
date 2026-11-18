# 云端 Agent 部署方案：可行性与改造清单

> 结论先行：**能上云，但不能直接搬**。现有 `yingzhi/serve` 是本地 DeepWorks 的转发代理，
> 智能不在这个仓库里。真正云原生化需要把「检索」从 agent 的 grep 行为固化成代码，
> 再把「生成」换成直连模型 API。预计 1.5–2 人日，月成本 ¥0–50 加模型 token 费。

- 编写日期：2026-11-18
- 适用版本：`main` 分支 `731be3d` 之后
- 状态：方案，未实施

---

## 1. 现状：三层结构，只有一层能上云

```
浏览器（GitHub Pages，已上线）
    │  POST /api/ask  (SSE)
    ▼
yingzhi/serve/main.py         ← 能上云：纯标准库，无第三方依赖
    │  转发
    ▼
gateway.py → DeepWorks 内置 opencode server   ← 不能上云：桌面进程，凭据在进程环境里
    │
    ▼
kb/data/*.jsonl               ← 能上云：约 6 MB，可直接打进镜像
```

证据：

| 位置 | 事实 |
| --- | --- |
| [gateway.py](yingzhi/serve/gateway.py#L1-L14) | 文件自述只做「建会话、发消息、订阅事件、转发」，「智能全部在 DeepWorks 的 agent / skill / workflow 里」 |
| [discover.py](yingzhi/serve/discover.py#L1-L12) | 用 `lsof` 扫本机 opencode 端口、`ps eww` 读进程环境拿 Basic Auth；端口每次启动随机 |
| [main.py](yingzhi/serve/main.py#L651-L690) | 检索策略写在 `hint` 里，直接拼 `grep -m 5 "关键词" kb/data/signs.jsonl` 交给 agent 执行 |
| [main.py](yingzhi/serve/main.py#L231) | 连不上 agent 时退到 `fallback_answer()`，只做「词条名是否出现在问题里」的字符串包含 |

**关键结论**：所谓「检索」目前不是算法，是**把 grep 命令写给 agent**。这反而是好消息——
把它翻译成 Python 函数，行为可以和现在高度一致，不需要引入向量库。

---

## 2. 直接打包上云会发生什么

| 失败点 | 现象 |
| --- | --- |
| `discover()` 找不到进程 | `agent_ready=False`，`/api/health` 返回 `fallback_reason` |
| 降级路径生效 | 每条回答都是关键词命中，未命中就回「本地演示态未命中」 |
| 界面无异常 | 前端正常渲染，用户看不出差别——**这是最危险的部分** |

所以「能跑」不等于「能用」。上线前必须有机制让降级可见（现在前端已有「本地计算 · 未调用 Agent」标识，需确认公网也显示）。

---

## 3. 三条路线

### A. 隧道（今天可用，非云原生）

```bash
cloudflared tunnel --url http://127.0.0.1:8800
```

前端**零改动**：[sse.js](medtrain/app/sse.js#L28-L36) 的 `apiBase()` 优先读 `localStorage.yzApiBase`。
在页面控制台执行 `localStorage.setItem("yzApiBase","https://xxx.trycloudflare.com")` 即可切换。

| 项 | 值 |
| --- | --- |
| 改造量 | 0.5 小时 |
| 成本 | 0 |
| 硬限制 | 这台 Mac 必须开机、不休眠、DeepWorks 在前台；域名每次重启变化 |
| 适用 | 黑客松现场演示、评审临时访问 |

**建议保留作为兜底**：正式方案上线前，现场用它保证「真 Agent」可演示。

### B. 云原生重写（推荐）

把 gateway 换成模型 API 客户端，把 hint 里的 grep 逻辑变成 Python 检索模块。

| 项 | 值 |
| --- | --- |
| 改造量 | 1.5–2 人日 |
| 成本 | 服务器 ¥0–50/月 + token（1000 次问答约 ¥5） |
| 硬限制 | 需要模型 API key；检索质量要自己做回归 |
| 适用 | 长期对外、不想依赖个人电脑 |

### C. 混合（静态站 + 云函数只跑问答）

与 B 技术核心相同，区别是部署形态（Serverless 而非常驻容器）。

| 项 | 值 |
| --- | --- |
| 改造量 | 1–1.5 人日 |
| 风险 | 冷启动 1–3 秒；部分平台 SSE 有时长上限（如 Cloudflare Workers 需注意） |
| 适用 | 访问量低、想按次计费 |

---

## 4. 推荐方案 B 的实施清单

### P0 · 检索固化（0.5 天，可离线验证）

目标：不接模型，也能对同一问题产出与 agent 相近的候选集。

新增 `yingzhi/serve/retrieve.py`：

```python
def retrieve(query, kb_dir, top_k=8):
    """返回 {signs:[], concepts:[], claims:[], paragraphs:[]}"""
    # 1) 词条名/别名直接命中（等价于现有 grep signs.jsonl）
    # 2) 概念命中 → sign_ids → 回查 signs（等价于现有 hint 第 2-3 步）
    # 3) 关联征象 related_sign_ids，标记 relation="related"
    # 4) 指南/文献：claims 按 body_part + sign 名做 AND 过滤，取 top_k
```

要点：

- 数据量小（signs 60、concepts 136、claims 967、paragraphs 546），全量载入内存即可，**不需要 BM25 或向量库**。
- 打分用「命中字段权重」：词条名 3 分、别名 2 分、正文 1 分；同分按 `evidence_level` 排序。
- 必须保留现有的**候选标记**：指南条款一律 `match=candidate`，不得升级为确定结论。
- 输出结构对齐 `claims.jsonl` 现有字段（`excerpt_sha256`、`span`、`page_status`），前端不用改。

验收：用 `yingzhi/run/` 里已有的 74 次真实提问做回放，对比新旧候选集重合率，目标 ≥80%。

### P1 · 生成层替换（0.5 天）

新增 `yingzhi/serve/llm.py`，替换 `Gateway.ask`：

```python
def answer(query, ctx, stream_cb):
    # 输入：query + retrieve() 结果（压缩成结构化文本，约 3–4k tokens）
    # 输出：四段式正文（结论 / 依据 / 缺失 / 边界）+ citations
```

约束（沿用现有规则，不能放宽）：

- 合规拦截 `BLOCK_PATTERNS` 保持在模型调用**之前**（[main.py](yingzhi/serve/main.py#L615)）。
- 正文必须四段式，且「边界」段固定写明非诊断。
- 引用只能来自 `retrieve()` 返回的条目，模型不得自造 id 或 URL。
- 未命中时走通识段，段内禁止出现任何 id（现有 `GENERAL_MARK` 机制）。
- 温度 0.2 以下，`max_tokens` 800，避免长篇发挥。

`main.py` 的改动很小：把 `ensure_gateway()` / `gateway.ask()` 换成 `llm.answer()`，
SSE 事件（`trace` / `delta` / `citation` / `done`）格式完全不变，前端零改动。

### P1.1 · 双模型路由（已实现）

有图走视觉、无图走文本，一个 `if` 决定，不引入额外编排框架。

| 请求 | 模型 | 说明 |
| --- | --- | --- |
| 带 `image`（data URL） | `qwen3-vl-plus` | 支持 grounding，可返回 bbox 交给 `locate.js` 匹配已有分区 |
| 纯文本 | `deepseek-chat` | 医学问答扎实、成本低 |

选择 Qwen-VL 而不是 GPT-4o 的唯一理由是 **bbox**：只有能输出坐标，模型的描述才能被约束到 981 个已有分区上；否则只能「看图说话」，落不到证据。

环境变量（OpenAI 兼容，纯标准库实现，无 SDK 依赖）：

```
YZ_LLM_VISION_BASE / YZ_LLM_VISION_KEY / YZ_LLM_VISION_MODEL
YZ_LLM_TEXT_BASE   / YZ_LLM_TEXT_KEY   / YZ_LLM_TEXT_MODEL
YZ_LLM_TIMEOUT     # 默认 60
```

实现文件：

| 文件 | 职责 |
| --- | --- |
| `yingzhi/serve/llm.py` | `Router` 选模型、`Retriever` 轻量检索、`Answerer` 组装与校验 |
| `yingzhi/serve/test_llm_route.py` | 9 项离线测试（不联网、不耗 token） |
| `yingzhi/serve/main.py` | `ensure_llm()`；`/api/ask` 新增分支；`/api/health` 暴露 `llm_route` |

三条保护：

1. **未配置 key 整体禁用**，自动回落原有 gateway / fallback，不影响现有演示。
2. **引用校验**：模型输出中的 `SIGN-` / `CLM-` id 必须存在于 `kb/data`，否则计入 `dropped_ids` 且不进 `cites`。
3. **调用失败降级**：任何网络或解析错误都走 `fallback_answer`，并向前端发 `reset`，不会静默返回半截答案。

已验证（本地、无 key 与假 key 两种配置）：

```
llm_route: {'vision': 'qwen3-vl-plus', 'text': 'deepseek-chat'}
trace: {"stage":"kb_retrieve","skill":"llm_route","detail":{"route":"text","model":"deepseek-chat","signs":1,"claims":8}}
上游不可达 -> trace: agent_generate/fallback -> reset -> 本地兜底回答
```

前端传图方式（尚未接入 UI）：`POST /api/ask` 增加 `"image": "data:image/jpeg;base64,..."` 即可，后端自动切到视觉模型。

### P2 · 打包与部署（0.5 天）

Dockerfile（无 pip 依赖，镜像约 120 MB）：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY yingzhi/serve/ ./yingzhi/serve/
COPY kb/data/*.jsonl ./kb/data/
ENV PORT=8080
EXPOSE 8080
CMD ["python3","yingzhi/serve/main.py","--port","8080"]
```

平台选择：

| 平台 | 免费额度 | SSE | 备注 |
| --- | --- | --- | --- |
| Fly.io | 无（小机约 $3/月） | 支持 | Docker 原生，延迟低，推荐 |
| Render | 有，15 分钟无流量休眠 | 支持 | 冷启动约 30 秒，演示前需预热 |
| Railway | 试用额度 | 支持 | 上手最快 |
| 阿里云 FC / 腾讯云 SCF | 有 | 需确认超时上限 | 国内访问快，但绑定域名需备案 |

环境变量（不落盘、不进镜像）：

```
LLM_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL=...
```

部署后前端切换：设置 `localStorage.yzApiBase` 为服务地址，或给 `sse.js` 加一个 `?api=` 查询参数（10 行以内）。

---

## 5. 成本估算

单次问答：输入约 3.5k tokens（检索结果 + 系统提示），输出约 500 tokens。

| 模型档位 | 1000 次问答 | 说明 |
| --- | --- | --- |
| 国产中档（如 DeepSeek） | 约 ¥5 | 性价比最高，中文医学表述可接受 |
| 国际小模型（如 4o-mini 级） | 约 $0.8 | 需网络可达 |
| 国际旗舰 | 约 $15–25 | 演示效果好，成本高 |

服务器：Fly 小机 $3/月 ≈ ¥22；Render 免费层可用但会休眠。

---

## 6. 验收标准

上线前必须全部通过，否则不上：

1. `/api/health` 返回 `agent_ready=true` 且 `degraded=false`
2. 合规拦截：问「怎么治」「是不是癌」返回固定拒答，且**不产生模型调用**（查 trace）
3. 双引用：每条回答至少 1 个影像锚点 + 1 个文献锚点，`excerpt_sha256` 与库内一致
4. 未命中：问库外疾病，回答进入通识段且**不出现任何 id**
5. 候选标记：指南条款文案含「候选，适用性需人工判断」
6. 降级可见：断掉模型 API 后，前端显示「未调用 Agent」，不静默降级
7. 回放：`yingzhi/run/` 74 条历史提问，人工抽检 20 条，结论无诊断性措辞
8. 时延：P95 首字 < 3 秒，完整回答 < 20 秒

---

## 7. 风险清单

| 风险 | 影响 | 处置 |
| --- | --- | --- |
| 检索质量不如 agent | 回答变差，用户流失 | P0 阶段先做离线回放对比，不达标不进入 P1 |
| 模型幻觉造引用 | 违反三条红线 | 只允许从检索结果选 id；返回后做 hash 校验，不匹配则丢弃该引用 |
| 公网暴露 API key | 被盗刷 | key 只放服务端环境变量；前端永远不接触 |
| 免费层休眠 | 演示时首问 30 秒 | 演示前 10 分钟预热；或直接用隧道方案兜底 |
| 国内访问 Pages 慢 | 打开就卡 | 静态站迁国内对象存储（需备案），与 agent 部署分开决策 |
| 51 张待核验影像公开 | 合规风险 | 已在 `ATTRIBUTION.md` 标注；正式对外前替换或人工确认 |

---

## 8. 建议落地顺序

1. **本周**：保留隧道方案，确保任何场合都能演示真 Agent（0.5 小时）。
2. **下一步**：做 P0 检索固化 + 离线回放（0.5 天），先证明「不用 agent 也能找到同样的证据」。
3. **再决定**：P0 达标后再投入 P1/P2；不达标就说明现在的价值确实依赖 agent 的探索能力，应重新评估而不是硬搬。
4. **长期**：静态站与 agent 服务分开部署、分开扩容；不要把 46 MB 站点和问答服务绑在一个容器里。

---

## 9. 明确不做的事

- 不把 DeepWorks 桌面引擎塞进容器（无 Linux 服务端形态，且凭据机制依赖进程环境）。
- 不为了上云引入向量数据库（数据量太小，收益低于维护成本）。
- 不在前端做模型调用（key 会泄露）。
- 不因为「云上有 agent」就放宽三条红线（不诊断、不生成文献摘录、配准失败不下结论）。
