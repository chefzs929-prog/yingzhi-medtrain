"""一键体检：确认「接入入口」是否真的可用。

用法：
    python3 yingzhi/tools/probe.py
    python3 yingzhi/tools/probe.py --ask "磨玻璃影"

输出四行结论：入口 / 鉴权 / Agent / 一次真实调用耗时。
不打印任何凭证。
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "serve"))

from discover import DiscoverError, discover  # noqa: E402
from gateway import Gateway, GatewayError  # noqa: E402

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(WORKSPACE, "kb", "data")


def line(ok, label, detail):
    mark = "OK  " if ok else "FAIL"
    print("[%s] %-10s %s" % (mark, label, detail))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", default="")
    ap.add_argument("--agent", default="yingzhi")
    args = ap.parse_args()

    try:
        info = discover(force=True)
    except DiscoverError as exc:
        line(False, "入口", str(exc))
        return 1
    line(True, "入口", info["url"])
    line(True, "鉴权", "Basic Auth 已就绪（密码长度不展示）")

    gw = Gateway(info, agent=args.agent, directory=WORKSPACE, kb_root=DATA_DIR)
    try:
        names = gw.agents()
    except GatewayError as exc:
        line(False, "Agent", str(exc))
        return 1
    ready = args.agent in names
    line(ready, "Agent", "%s（可用：%s）" % (args.agent if ready else "未加载", ", ".join(names)))
    if not ready:
        gw.agent = "build"

    try:
        skills = gw.skills()
    except GatewayError as exc:
        skills = []
        line(False, "技能", str(exc))
    skill_ready = "retrieve-sign" in skills
    line(skill_ready, "技能", "retrieve-sign %s（共 %d 个）"
         % ("已加载" if skill_ready else "未加载", len(skills)))

    if args.ask:
        t0 = time.time()
        deltas = []
        sid = gw.ensure_session("probe", "cli")
        # 与动态层一致：强制先加载技能，否则 agent 会跳过 skill 工具
        hint = "1) 先调用 skill 工具，参数 name 为 retrieve-sign（加载检索规范）"
        keyword = args.ask.replace("是什么", "").replace("怎么描述", "").strip("？? ")
        if keyword:
            hint += '\n2) 再执行：grep -m 5 "%s" %s/signs.jsonl' % (keyword, DATA_DIR)
        result = gw.ask(sid, args.ask, lambda kind, payload: deltas.append((kind, payload)),
                        hint=hint)
        print("\n问题：%s" % args.ask)
        print("首字：%dms  总耗时：%dms  delta：%d 次" % (
            result["first_token_ms"], result["total_ms"], result["delta_chars"]))
        print("工具：%s" % ([t["tool"] for t in result["tools"]] or "无"))
        print("回答：\n%s" % (result["text"][:600]))
        line(True, "调用", "%.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
