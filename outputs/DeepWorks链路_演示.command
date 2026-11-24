#!/usr/bin/env bash
# 链路演示（在终端窗口里执行，供录屏使用）
# 由 DeepWorks链路_60秒录屏.sh 自动打开；也可直接双击运行。
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

clear
echo "=============================================================="
echo "  RadioCheck × DeepWorks · 主体链路实跑"
echo "  技能加载 → 4 条检索 → 四段式回答 → 回查 id 与分区"
echo "=============================================================="
echo

echo "### 1/4  入口体检：引擎 / 鉴权 / Agent / 技能"
echo
python3 yingzhi/tools/probe.py
sleep 2

echo
echo "### 2/4  真实链路：先加载技能，再检索，最后四段式回答"
echo
python3 yingzhi/tools/probe.py --ask "磨玻璃影和实性结节在CT上怎么区分？"
sleep 3

echo
echo "### 3/4  回查：回答里的 id 在知识库里真实存在"
echo
grep -o '"id": "SIGN-001"' kb/data/signs.jsonl | head -1
python3 - <<'PY'
import json
for ln in open('kb/data/signs.jsonl', encoding='utf-8'):
    r = json.loads(ln)
    if r.get('id') == 'SIGN-001':
        print('SIGN-001 name      =', r.get('name'))
        print('appearance         =', (r.get('appearance') or '')[:60])
        print('modality/body_part =', r.get('modality'), '/', r.get('body_part'))
        print('sources            =', r.get('sources'))
        break
PY
sleep 2

echo
echo "### 4/4  回查：影像分区四态与可核对坐标"
echo
python3 - <<'PY'
import json, collections
d = json.load(open('outputs/medtrain/data/chest/chest_reading.json', encoding='utf-8'))
cs = d.get('cases') or d
cs = list(cs.values()) if isinstance(cs, dict) else cs
st = collections.Counter(z['status'] for c in cs for z in (c.get('zones') or []))
print('分区四态：', dict(st), '共', sum(st.values()))
for c in cs:
    zs = c.get('zones') or []
    if zs:
        z = zs[0]
        print('case =', c.get('id'), '| zone =', z.get('name'),
              '| status =', z.get('status'), '| coords =', z.get('coords'))
        break
PY

echo
echo "=============================================================="
echo "  站外页面不含任何模型调用；推理只发生在 DeepWorks 引擎内。"
echo "  本地服务只做转发与记账（yingzhi/serve/README.md）。"
echo "=============================================================="
echo
sleep 8
