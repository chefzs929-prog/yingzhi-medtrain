#!/usr/bin/env python3
"""RadHearing 问答技能入口。

用法：
    python3 ask.py "右肺中野有什么问题" --case CASE-006
    python3 ask.py "有没有肺炎"
    python3 ask.py "这张片子是不是肺癌" --json

退出码：
    0 = 正常（status 可能是 answer / refusal / unknown）
    2 = 环境或数据缺失
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import project_root  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="RadHearing 双引用问答")
    ap.add_argument("question", help="用户的自然语言问题")
    ap.add_argument("--case", default=None, help="病例 ID，例如 CASE-006；不填则按问题实体自动定位")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON 而不是 Markdown")
    args = ap.parse_args()

    try:
        root = project_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    sys.path.insert(0, os.path.join(root, "kb", "scripts"))
    try:
        import ask_engine  # noqa: E402
    except Exception as e:  # pragma: no cover
        print(f"无法导入 ask_engine: {e}", file=sys.stderr)
        return 2

    bank_path = os.path.join(root, "kb", "data", "ask_bank.json")
    bank = ask_engine.Bank(bank_path)
    res = bank.answer(args.question, args.case)

    if args.json:
        payload = {
            "status": res["status"],
            "question": res["question"],
            "case_id": res["case_id"],
            "score": res["score"],
            "markdown": res["markdown"],
        }
        item = res.get("item")
        if item:
            payload["qid"] = item.get("qid")
            payload["kind"] = item.get("kind")
            if item.get("region"):
                payload["region"] = item["region"]
            if item.get("citation"):
                payload["citation"] = item["citation"]
            if item.get("refusal"):
                payload["refusal"] = item["refusal"]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(res["markdown"])

    print(
        "\n---\n非诊断用途 · 答案来自公开教学数据集的逐区标注，指南为要点转述（非逐字引用）"
        " · 不提供诊断、分期、治疗与预后建议",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
