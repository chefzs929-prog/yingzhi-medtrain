# yingzhi/serve · 职责边界说明

> 一句话：**本目录是只读转发层与记账层，不含推理。**
> 推理全部发生在 DeepWorks 内置引擎（agent / skill / 模型）里。

---

## 0. 知识库数据 API（只读）

`kb_api.py` 把 `kb/data` 与构建产物里的知识库数据暴露为只读接口，按文件 mtime 缓存，数据更新后无需重启。默认同时托管 `outputs/medtrain` 前端：

```bash
python3 yingzhi/serve/main.py --port 8800
# 前端：http://127.0.0.1:8800/read/clinic.html
```

| 接口 | 说明 |
| --- | --- |
| `GET /api/kb/health` | 版本、数据规模、可用接口 |
| `GET /api/kb/chest` | 胸片逐区数据 |
| `GET /api/kb/exam` | 病例题与对比对 |
| `GET /api/kb/lab` | 学生实验室索引与规则题 |
| `GET /api/kb/search?q=气胸` | 跨征象 / 疾病 / 指南 / 病例 / 分区的关键词检索 |
| `GET /api/kb/signs?q=气胸` | 征象列表与关键词筛选 |
| `GET /api/kb/concepts?q=肺水肿` | 疾病 / 概念列表 |
| `GET /api/kb/guidelines?q=结节` | 指南条款列表 |
| `GET /api/kb/claims?image_id=CASE-001` | 按病例取 claims |
| `GET /api/kb/regions?image_id=CASE-001` | 按病例取分区 |
| `GET /api/kb/sign/SIGN-001` | 征象详情、原文段落、相关病例 |
| `GET /api/kb/case/CASE-001` | 病例详情、分区与 claims |
| `GET /api/kb/audit/review` | 质控复核队列 |
| `GET /api/kb/image/<name>` | 影像文件 |

前端 `read/kb-api.js` 优先同源 `/api/kb/*`，失败时回退构建期静态 JSON；纯静态托管可用 `?api=http://127.0.0.1:8800` 显式指定后端。

---

## 1. 默认部署下的调用链

```
浏览器（静态页面）
   │  POST /api/ask（SSE）
   ▼
本目录 main.py（本地转发 + 记账）
   │  只做：建会话、发消息、订阅事件、采集耗时、落 trace.json、提取 id
   ▼
gateway.py  ──转发──▶  DeepWorks 内置 opencode server（127.0.0.1:随机端口）
                          │  yingzhi agent + retrieve-sign skill
                          │  grep / read 工具调用（工具事件回传）
                          ▼
                       DeepWorks 内置模型（dth/Auto）
   │
   ▼
浏览器渲染结构化结果（结论 / 依据 / 缺失 / 边界 + 可核对 id）
```

**本目录不参与的位置**：检索打分、判分规则、prompt 拼接、模型选择、回答口径约束。
这些全部写在 `.opencode/agents/yingzhi.md` 与 `.opencode/skills/retrieve-sign/SKILL.md` 里。

---

## 2. 三个文件的职责

| 文件 | 做什么 | 明确不做 |
| --- | --- | --- |
| `gateway.py` | 建会话、发消息、订阅 SSE、采集耗时与工具事件、转发 | 检索打分、prompt 拼接、模型选择 |
| `vision.py` | `match_image`（md5 精确比对）、`extract_bbox`（解析模型已给出的框） | 认图、推断病灶、生成框 |
| `main.py` | HTTP 路由、SSE 封装、trace 落盘、合规拦截、降级标记 | 生成医学内容 |

`vision.py` 是确定性判断：库里没有这张图就返回 `None`，由上层走"未落到已标注分区就不下结论"，不挑一张最像的顶上去。

---

## 3. 默认配置下 `served_by` 只可能是两个值

| 值 | 含义 |
| --- | --- |
| `agent` | 正常链路：回答由 DeepWorks 引擎产出 |
| `fallback` | DeepWorks 不可用：返回本地规则模板，并在 `trace` 里标 `degraded` |

不会出现 `llm`，除非显式开启实验分支（见第 4 节）。

---

## 4. 实验分支：直连模型（默认关闭）

`llm.py` 保留了一条直连外部模型（DeepSeek / DashScope）的对照路径，用于 A/B 与离线演示。
它**不属于默认部署链路**：

- `ensure_llm()` 在未设置 `YZ_ENABLE_DIRECT_LLM=1` 时直接返回 `None`；
- 默认 `mode=agent`，`llm` 分支不会被选中；
- 启动时会在 stderr 打印一行：`[llm] 直连分支未启用（YZ_ENABLE_DIRECT_LLM 未设为 1）：推理仅经 DeepWorks 引擎`。

答辩与验收使用默认配置，即关闭该分支。

---

## 5. 怎么当场验证（30 秒）

```bash
# 1) 起服务（不配任何 key）
python3 yingzhi/serve/main.py --port 8800 &

# 2) 看能力探测：direct_llm_enabled 必须是 false
curl -s http://127.0.0.1:8800/api/agent/capabilities | python3 -m json.tool | \
  grep -E 'default_mode|inference_location|direct_llm_enabled'

# 3) 起服务时的第一行日志应包含：
#    [llm] 直连分支未启用（YZ_ENABLE_DIRECT_LLM 未设为 1）：推理仅经 DeepWorks 引擎

# 4) 真实链路体检（需要 DeepWorks 在跑）
python3 yingzhi/tools/probe.py --ask "磨玻璃影和实性结节在CT上怎么区分？"
```

预期输出：`direct_llm_enabled: false`、`default_mode: "agent"`、`inference_location: "deepworks_engine"`，
并且 probe 的工具列表为 `['skill', 'bash', 'bash', 'bash', 'bash']`（1 次技能加载 + 4 条检索）。
