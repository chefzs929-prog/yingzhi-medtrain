"""定位 yingzhi-medtrain 项目根目录（含 kb/data/ask_bank.json）。

优先级：
  1. 环境变量 MEDTRAIN_HOME（显式指定，换机器/演示时用）
  2. 从本技能位置向上推导（技能随仓库分发时为 <repo>/.opencode/skills/radhearing-ask/scripts/）
  3. 当前工作目录下的 yingzhi-medtrain
不做任何作者机器路径兜底——找不到就明确报错，由调用者设置 MEDTRAIN_HOME。
"""

from __future__ import annotations

import os
from pathlib import Path

_HERE = Path(__file__).resolve()


def _candidates() -> list[str]:
    out = [os.environ.get("MEDTRAIN_HOME", "")]
    # <repo>/.opencode/skills/radhearing-ask/scripts/_paths.py → parents[4] = <repo>
    for depth in (4, 3, 2):
        try:
            out.append(str(_HERE.parents[depth]))
        except IndexError:
            pass
    out.append(os.path.join(os.getcwd(), "yingzhi-medtrain"))
    out.append(os.getcwd())
    return out


def project_root() -> str:
    for c in _candidates():
        if c and os.path.isfile(os.path.join(c, "kb", "data", "ask_bank.json")):
            return str(Path(c).resolve())
    raise RuntimeError(
        "找不到 yingzhi-medtrain 项目（需要 kb/data/ask_bank.json）。\n"
        "请在项目根目录运行，或设置环境变量 MEDTRAIN_HOME=/path/to/yingzhi-medtrain。"
    )
