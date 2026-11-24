# LLM 分层回答方案（库内证据 + 模型通识）

> 版本：v1.0 · 2026-11-18
> 对应实现：`kb/data/concepts.jsonl`、`yingzhi/scripts/build_concepts.py`、
> `yingzhi/serve/main.py`、`.opencode/skills/retrieve-sign/SKILL.md`、
> `.opencode/agents/yingzhi.md`、`outputs/medtrain/learn.js`

## 1. 问题

截图里的提问「肺水肿的征象」返回「库内暂无该征象」。模型本身是通的（`dth/Auto`，单次生成约 10 秒），
但三层提示词把它约束成了纯检索器：

| 位置 | 原约束 |
|---|---|
| `yingzhi.md` 规则 8 | 库内没有就写「库内暂无」，**不补常识** |
| `yingzhi.md` 规则 9 | 未命中就直接回答，不要继续搜索 |
| `retrieve-sign/SKILL.md` | 三步都无命中，直接回答「库内暂无该词条」 |
| `main.py` 检索提示 | 只指向 `signs.jsonl`，只按词条名匹配 |

更深一层是**索引维度错位**：「肺水肿」是疾病/病理，不是征象。60 条征象词条里没有它，
但 SIGN-001 磨玻璃影、SIGN-002 实变、SIGN-014 空气支气管征的 `may_see_in` 都写了「肺水肿」。
知识在库里，只是只能按征象名查，不能按疾病查。

## 2. 三层设计

### 第 1 层：疾病 → 征象概念索引

新增 `kb/data/concepts.jsonl`，由 `yingzhi/scripts/build_concepts.py` 生成：

- 扫 `signs.jsonl` 的 `may_see_in`，拆「A或B」，聚合成概念候选；
- 人工种子补英文名、别名、关联征象与提示；
- 两层口径严格分开：
  - `sign_ids`：`may_see_in` 原文直接支持，属于库内证据；
  - `related_sign_ids`：人工补充的病理关联，回答时必须标「关联」。

当前规模：60 条征象 → 136 个概念。「肺水肿」落到 CON-012：

```json
{"id":"CON-012","name":"肺水肿","sign_ids":["SIGN-001","SIGN-002","SIGN-014"],
 "related_sign_ids":["SIGN-007","SIGN-010"]}
```

重新生成：

```bash
python3 yingzhi/scripts/build_concepts.py          # 写入 kb/data/concepts.jsonl
python3 yingzhi/scripts/build_concepts.py --check  # 只校验不写
```

> **2026-11-23 调整**：面向学生的正文不再出现「库内 / 公开说明 / 通识补充 / 缺失 / 边界」这类元信息。
> 回答直接给专业讲解（首句结论 → 影像表现与机制 → 鉴别 → 易错点），出处只放末行「依据：…」。
> 审计仍按「检索命中数 + 正文 id 是否真实存在」判断，`grounding` / `marker_ok` / `general_section_ids` 字段保留兼容。

### 第 2 层：回答三态

| 状态 | 触发 | 输出要求 |
|---|---|---|
| `grounded` | 库内命中且证据完整 | 事实断言必须挂 `SIGN/CLM/SL` id |
| `mixed` | 概念命中 + 通识补充 | 库内段落带 id；补充段以 `【通识补充·非库内证据】` 开头 |
| `general` | 库内完全未覆盖 | 允许模型通识回答，但通识段**禁止出现任何 id** |

检索顺序从三步扩到四步：`signs 精确名 → signs 别名/英文 → concepts 概念 → 概念下 sign_ids 回查`，
最多 4 条命令，命中即停。

合规边界不变：不回答诊断、治疗、用药、手术、预后。

### 第 3 层：审计与展示

`yingzhi/serve/main.py`：

- `suggest_concept()`：把疾病名映射到概念条目；
- `general_section_ids()`：抓通识段里越界出现的 id。即使 id 真实存在也要报，
  因为那是拿库外内容冒充可核验证据；
- `detect_grounding()`：返回 `grounding` 与 `marker_ok`；未命中却没用通识标记，
  `marker_ok=false`，前端按最严重处理；
- `done` 事件新增 `grounding` / `marker_ok` / `general_section_ids`；
- `trace.json` 的 `citation_audit` 同步落盘。

前端（`outputs/medtrain/learn.js` 与 `yingzhi/app/probe.html`）：

- 绿：库内证据；
- 黄：库内证据 + 通识补充；
- 红：纯通识 / 通识段越界 id / 未标注通识来源；
- `general` 时额外显示「库外问题」横幅。

## 3. 实测

### 3.1 库内可答：肺水肿

```
结论：肺水肿（CON-012）在库内对应的直接征象为 SIGN-001 磨玻璃影、SIGN-002 实变、
SIGN-014 空气支气管征；另标注关联征象 SIGN-007 胸腔积液、SIGN-010 心影增大（关联）。
```

- `grounding=grounded`，`unverified_citations=[]`，`general_section_ids=[]`
- 关联征象带【关联】标记，缺失段如实写「库内无小叶间隔增厚、支气管周围袖套征、蝶翼征」
- 总耗时 11.8 秒

### 3.2 库外问题：肺隔离症

- `grounding=general`，`marker_ok=true`，`general_section_ids=[]`
- 通识段以 `【通识补充·非库内证据】` 开头，段内零 id
- 依据段明确写「未命中（signs.jsonl 与 concepts.jsonl 中均无该名称条目）」

### 3.3 审计反例

在通识段写入 `SIGN-018` 后，`general_section_ids` 正确返回 `["SIGN-018"]`，
即使该 id 在库内真实存在。

## 4. 复现

```bash
# 1. 重建概念索引
python3 yingzhi/scripts/build_concepts.py

# 2. 启动动态层（需要 DeepWorks 引擎在跑）
python3 yingzhi/serve/main.py --port 8800

# 3. 体检
curl -s http://127.0.0.1:8800/api/health

# 4. 实测
curl -N -X POST http://127.0.0.1:8800/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"肺水肿的征象","role":"student","chain":"kb_qa"}'

# 5. 主站
cd outputs/medtrain && python3 -m http.server 8080 --bind 127.0.0.1
# 打开 http://127.0.0.1:8080/app.html#/ask
```

## 5. 风险与边界

- 放开通识会削弱「零幻觉」叙事。答辩时必须主动说明三色标签的含义，
  不能把 `general` 回答当作库内证据展示。
- 通识内容的医学准确性由模型负责，本库不做二次核验；因此 `general` 回答
  不进入引用自证链路，`cited` 为空。
- `related_sign_ids` 是人工判断，不是 `may_see_in` 原文。回答里必须保留「关联」字样，
  否则会重蹈「把推断写成原文」的覆辙。
- 概念索引目前 136 条，长尾概念（如「石棉相关病变」）证据很薄，检索命中后
  仍应如实写缺失。
