#!/usr/bin/env python3
"""直连模型冒烟测试：不启动 HTTP 服务，直接验证 .env 配置是否可用。

用法：
    python3 kb/scripts/smoke_llm.py                 # 文本知识问答
    python3 kb/scripts/smoke_llm.py --image x.jpg   # 视觉（需先配 YZ_LLM_VISION_*）

检查项：
1. .env 是否被读到、模型是否 ready
2. 首字/总耗时
3. 四段式（结论/依据/缺失/边界）是否齐全
4. 引用 id 数量（模型编造的 id 会被丢弃，只统计库内真实存在的）
"""
import argparse
import base64
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SERVE = ROOT / "yingzhi/serve"
sys.path.insert(0, str(SERVE))

QUESTIONS = [
    "磨玻璃影在CT上怎么描述？",
    "肾囊肿的影像表现是什么？",
    "肺水肿有哪些征象？",
]


def load_env():
    """start.sh 用 shell 加载 .env；脚本单独跑时自己加载一遍。"""
    p = SERVE / ".env"
    if not p.exists():
        return False
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
    return True


def sections(text):
    need = ["结论", "依据", "缺失", "边界"]
    return {k: (k in text) for k in need}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="可选：图片路径，测视觉分支")
    ap.add_argument("--q", action="append", help="自定义问题，可重复")
    args = ap.parse_args()

    print("读取 .env:", load_env())
    import llm as llm_route  # noqa: E402  (必须在 load_env 之后)

    ans = llm_route.build_from_env()
    if ans is None:
        print("\n[未配置] YZ_LLM_TEXT_KEY / YZ_LLM_VISION_KEY 都为空。")
        print("填好 yingzhi/serve/.env 后重跑。")
        return 2

    print("模型:", ans.router.describe())

    image = None
    if args.image:
        p = Path(args.image)
        if not p.exists():
            print("图片不存在:", p)
            return 2
        image = "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode("ascii")
        if not ans.router.describe().get("vision"):
            print("[注意] 未配置视觉模型，带图会退回文本模型（回答会注明未读取影像）")

    qs = args.q or (["这张影像有什么表现？"] if image else QUESTIONS)
    failed = 0
    for q in qs:
        print("\n" + "=" * 60)
        print("Q:", q)
        t0 = time.time()
        try:
            res = ans.ask(q, lambda kind, payload: None, image=image)
        except Exception as exc:
            failed += 1
            print("  失败:", type(exc).__name__, str(exc)[:200])
            continue
        ms = int((time.time() - t0) * 1000)
        text = res.get("text") or ""
        cites = res.get("cites") or []
        sec = sections(text)
        print("  耗时: %d ms | 引用: %d 条 | 字数: %d" % (ms, len(cites), len(text)))
        print("  四段:", " ".join("%s=%s" % (k, "✓" if v else "✗") for k, v in sec.items()))
        if not all(sec.values()):
            failed += 1
        for c in cites[:5]:
            print("   -", c.get("id"), c.get("title"))
        print("  " + text.replace("\n", "\n  ")[:600])

    print("\n" + "=" * 60)
    print("失败项:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
