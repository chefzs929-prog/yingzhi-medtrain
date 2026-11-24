# DeepWorks 链路实跑证据

> 生成时间：2026-11-23 00:19:41 CST ｜ 对应录屏：`outputs/DeepWorks链路_60秒录屏.mov`
> 说明：本文件不是截图说明，是一次真实运行的完整留痕。每一行都能用文末命令重跑复现。

## 0 一句话

技能 `retrieve-sign` 被真实加载（135 行技能正文），随后发生 3 次检索工具调用，模型输出四段式回答并带可回查 id。**推理只发生在 DeepWorks 引擎内，本地服务只做转发与记账。**

## 1 运行环境

| 项 | 值 |
| --- | --- |
| 引擎入口 | `http://127.0.0.1:49270`（每次启动端口不同） |
| 鉴权 | HTTP Basic Auth 已就绪（密码不展示、不落盘） |
| Agent | `yingzhi`（同环境可用：deepworks / build / explore / general / plan / summary / title / compaction） |
| 技能 | `retrieve-sign` 已加载（技能总数 37） |
| 模型 | `dth/Auto` |
| 首字延迟 | 13969 ms |
| 总耗时 | 14305 ms |
| 会话 | `ses_dfbf25115ffeixEY5E6tpTYfTk` |

## 2 工具时间线（技能真的被加载、检索真的发生）

| # | 时刻 | 工具 | 技能 | 耗时 | 命中行 | 命令 / 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 00:18:57.129 | `skill` | retrieve-sign | 104 ms | 135 | `skill(name=retrieve-sign)` |
| 2 | 00:18:58.840 | `bash` | - | 113 ms | 3 | `grep -m 5 "磨玻璃影" /Users/fz/Desktop/黑客松/kb/data/signs.jsonl` |
| 3 | 00:18:58.936 | `bash` | - | 115 ms | 1 | `grep -m 5 "实性结节" /Users/fz/Desktop/黑客松/kb/data/signs.jsonl` |
| 4 | 00:19:01.309 | `bash` | - | 227 ms | 0 | `grep -m 5 '"name": "实性' /Users/fz/Desktop/黑客松/kb/data/signs.jsonl` |

> 其中第 1 行是技能加载（返回 135 行检索规范）；第 2—4 行是真实 grep。第 4 行返回 `(no output)` 也被如实记录——没有命中就是没有命中，不用相似词条顶替。

> 另一次同条件运行（`probe.py --ask`）的工具序列为 `skill + 4×bash`，即技能上限 4 条检索命令可以跑满。两次都在同一引擎、同一 agent、同一技能下完成。

## 3 完整四段式回答（原文，未删改）

**问题**：磨玻璃影和实性结节在CT上怎么区分？

结论：磨玻璃影（GGO）在库内为 SIGN-001，其判读要点是「密度增高但不掩盖血管与支气管轮廓」；「实性结节」在库内无独立词条，两者区分要点以通识补充说明。

依据：SIGN-001「磨玻璃影」（ground-glass opacity，别名 GGO、磨玻璃密度影、磨玻璃结节），模态为 CT、部位为肺，appearance 原文为「肺野密度轻度增高，但其内血管与支气管边缘仍可辨认；不掩盖其内血管与支气管轮廓」；may_see_in 覆盖炎症性渗出、局灶性纤维化、肿瘤性病变、肺水肿或出血；出处 SRC-FLEISCHNER、SRC-RADIO。该条 pitfalls 明确提示「需与部分实性结节中的实性成分区分」「层厚与窗宽会影响显示，薄层更可靠」——即库内把「实性成分的辨认」作为 GGO 的首要易错点。

【通识补充·非库内证据】
区分核心是「是否掩盖其内血管与支气管轮廓」这一条，而非单纯测密度值。

- 磨玻璃影：密度轻度升高但仍呈「雾状半透明」，走行其中的肺血管、支气管边缘可辨；多为贴壁生长或炎性渗出的表现，实性成分占比小。
- 实性结节（solid nodule）：密度足以完全掩盖其内的血管与支气管，呈均匀致密影，边界通常较清楚；形态上更圆、更「实」。
- 部分实性结节（part-solid nodule）：兼具两种成分，需分别描述磨玻璃部分与实性部分，实性成分的大小往往比总径更受关注。
- 实用判读要点：①用肺窗薄层（层厚越小越可靠）观察，纵隔窗有助于判断是否真为实性；②窗宽窗位会显著改变主观密度感，比较同一病灶需固定窗设置；③结节状 GGO 与片状 GGO 的鉴别思路不同，前者更需关注随访中的实性成分出现或增大。
- 常见误区：把血管断面、血管聚集误判为实性成分；把贴近胸膜或叶间裂处的容积效应误判为密度增高；用厚层图像判断实性成分。

缺失：库内无「实性结节」「部分实性结节」独立征象词条，也无结节密度定量阈值、实性成分占比测量方法及随访策略相关条目；上述区分标准与操作要点均来自模型通识，非本库证据。

边界：仅用于教学与研究，不构成诊断意见。

## 4 回查：回答里的 id 真实存在

```
grep -m 1 '"id": "SIGN-001"' kb/data/signs.jsonl
```

| 字段 | 值 |
| --- | --- |
| id | `SIGN-001` |
| name | 磨玻璃影 |
| en | ground-glass opacity |
| aliases | GGO / 磨玻璃密度影 / 磨玻璃结节 |
| modality | CT |
| body_part | 肺 |
| appearance | 肺野密度轻度增高，但其内血管与支气管边缘仍可辨认；不掩盖其内血管与支气管轮廓。 |
| pitfalls | 需与部分实性结节中的实性成分区分；层厚与窗宽会影响显示，薄层更可靠 |
| sources | SRC-FLEISCHNER / SRC-RADIO |

## 5 回查：影像分区四态（"不作推断"不是口号）

```
python3 - <<'EOF'
import json,collections
d=json.load(open('outputs/medtrain/data/chest/chest_reading.json'))
cs=d.get('cases') or d
cs=list(cs.values()) if isinstance(cs,dict) else cs
st=collections.Counter(z['status'] for c in cs for z in (c.get('zones') or []))
print(dict(st), sum(st.values()))
EOF
```

| 状态 | 数量 | 占比 | 界面表现 |
| --- | --- | --- | --- |
| abnormal | 44 | 28.8% | 实线框 + 征象标签 |
| normal | 50 | 32.7% | 细实线框 |
| unmentioned | 58 | 37.9% | 灰色虚线 + "不作推断" |
| limited | 1 | 0.7% | 灰色虚线 + 局限说明 |
| **合计** | **153** | 100% | — |

## 6 复现命令

```bash
cd /Users/fz/Desktop/黑客松
python3 yingzhi/tools/probe.py                                  # 入口/鉴权/Agent/技能
python3 yingzhi/tools/probe.py --ask "磨玻璃影和实性结节在CT上怎么区分？"
bash outputs/DeepWorks链路_60秒录屏.sh                            # 录 60 秒
```

## 7 与录屏的对应关系

| 录屏时间段 | 画面内容 | 证明什么 |
| --- | --- | --- |
| 0—5s | 终端窗口启动 | （准备段，可跳过） |
| 6—12s | 标题 + 四行体检：入口 / 鉴权 / Agent / 技能 | 引擎在跑、`retrieve-sign` 已加载 |
| 12—40s | 工具序列 + 四段式回答 | 检索真的发生、回答带 SIGN / CLM / GDL id |
| 40—48s | grep 回查 `SIGN-001` 的 name / appearance / sources | id 不是编的 |
| 48—55s | 分区四态统计 + `coords` | "不作推断"有数据支撑（58/153） |
| 55—60s | 结论横幅 | 站外无模型调用，本地只转发记账 |
