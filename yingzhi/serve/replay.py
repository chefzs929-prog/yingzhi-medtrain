#!/usr/bin/env python3
"""历史提问回放：拿 yingzhi/run/ 里已有的真实提问，打一遍当前的 /api/ask。

用途：换了模型、改了 prompt、动了检索之后，用同一批问题做前后对比，
而不是临时想几个「看起来能过」的问题来自我验证。

    python3 yingzhi/serve/replay.py --limit 5
    python3 yingzhi/serve/replay.py --only 磨玻璃
    python3 yingzhi/serve/replay.py --base http://127.0.0.1:8800 --out yingzhi/replay

只用标准库。输出：
    yingzhi/replay/<时间戳>/report.md     人看的报告
    yingzhi/replay/<时间戳>/results.jsonl 机器看的明细（每行一条）
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "run"

SECTIONS = ("结论", "依据", "缺失", "边界")


def collect_queries(run_dir, only=None, limit=None):
    """读历史 run 的 request.json，去重后返回 [(query, run_id)]。"""
    items, seen = [], set()
    for req_path in sorted(run_dir.glob("*/request.json")):
        try:
            req = json.loads(req_path.read_text(encoding="utf8"))
        except Exception:
            continue
        if req.get("chain") == "replay":
            continue  # 跳过回放自己产生的记录，否则越跑越多
        query = (req.get("query") or "").strip()
        if not query or query in seen:
            continue
        if only and only not in query:
            continue
        seen.add(query)
        items.append((query, req_path.parent.name))
    if limit:
        items = items[:limit]
    return items


def ask(base, query, timeout=120):
    """POST /api/ask，解析 SSE，返回结构化结果。"""
    body = json.dumps({"query": query, "role": "student",
                       "device": "desktop", "chain": "replay"}).encode("utf8")
    req = urllib.request.Request(
        base.rstrip("/") + "/api/ask",
        data=body,
        headers={"Content-Type": "application/json",
                 "Accept": "text/event-stream"},
        method="POST",
    )
    t0 = time.time()
    parts, cites, done, traces = [], [], {}, []
    event = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf8", "replace").rstrip("\n")
                if line.startswith("event:"):
                    event = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                try:
                    payload = json.loads(line[5:].strip())
                except Exception:
                    continue
                if event == "delta":
                    parts.append(payload.get("text") or "")
                elif event == "citation":
                    cites.append(payload)
                elif event == "trace":
                    traces.append(payload)
                elif event == "done":
                    done = payload
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": "HTTP %s: %s" % (
            exc.code, exc.read().decode("utf8", "replace")[:200]),
            "ms": int((time.time() - t0) * 1000)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200],
                "ms": int((time.time() - t0) * 1000)}

    text = "".join(parts).strip()
    missing = [s for s in SECTIONS if (s + "：") not in text and (s + ":") not in text]
    return {
        "ok": bool(text),
        "text": text,
        "chars": len(text),
        "sections_missing": missing,
        "sections_ok": not missing,
        "cites": len(cites),
        "degraded": bool(done.get("degraded")),
        "blocked": bool(done.get("blocked")),
        "reason": done.get("reason"),
        "total_ms": done.get("total_ms") or int((time.time() - t0) * 1000),
        "unverified": done.get("unverified_citations") or [],
        "grounding": done.get("grounding"),
        "run_id": done.get("run_id"),
        "stages": [t.get("stage") for t in traces],
    }


def summarize(rows):
    ok = [r for r in rows if r.get("ok") and not r.get("blocked")]
    blocked = [r for r in rows if r.get("blocked")]
    ms = [r["total_ms"] for r in ok if r.get("total_ms")]
    return {
        "total": len(rows),
        "ok": len(ok),
        "failed": len(rows) - len(ok),
        "degraded": sum(1 for r in rows if r.get("degraded")),
        "blocked": len(blocked),
        "four_section_ok": sum(1 for r in ok if r.get("sections_ok")),
        "with_cites": sum(1 for r in ok if r.get("cites")),
        "avg_ms": int(statistics.mean(ms)) if ms else 0,
        "p50_ms": int(statistics.median(ms)) if ms else 0,
        "max_ms": max(ms) if ms else 0,
    }


def write_report(out_dir, rows, stat, base):
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 回放报告",
        "",
        "- 时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "- 服务：%s" % base,
        "- 用例：%d 条（成功 %d / 失败 %d）" % (
            stat["total"], stat["ok"], stat["failed"]),
        "",
        "## 汇总",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
        "| 四段式齐全 | %d / %d |" % (stat["four_section_ok"], stat["ok"]),
        "| 带引用 | %d / %d |" % (stat["with_cites"], stat["ok"]),
        "| 走降级 | %d |" % stat["degraded"],
        "| 合规拦截 | %d（不计入四段率） |" % stat["blocked"],
        "| 平均耗时 | %d ms |" % stat["avg_ms"],
        "| 中位耗时 | %d ms |" % stat["p50_ms"],
        "| 最慢 | %d ms |" % stat["max_ms"],
        "",
        "## 明细",
        "",
        "| # | 问题 | 耗时 | 四段 | 引用 | 降级 | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for i, r in enumerate(rows, 1):
        if not r.get("ok"):
            lines.append("| %d | %s | %s | - | - | - | %s |" % (
                i, _cell(r["query"]), r.get("ms", "-"), _cell(r.get("error", ""))))
            continue
        note = ""
        if r.get("blocked"):
            note = "合规拦截"
        elif r["sections_missing"]:
            note = "缺 " + "/".join(r["sections_missing"])
        elif r.get("unverified"):
            note = "未验证引用 %d" % len(r["unverified"])
        lines.append("| %d | %s | %d ms | %s | %d | %s | %s |" % (
            i, _cell(r["query"]), r["total_ms"],
            "齐" if r["sections_ok"] else "缺",
            r["cites"], "是" if r["degraded"] else "否", _cell(note)))
    lines += ["", "## 正文", ""]
    for i, r in enumerate(rows, 1):
        lines.append("### %d. %s" % (i, r["query"]))
        lines.append("")
        if r.get("ok"):
            lines.append("```")
            lines.append(r["text"][:1200])
            lines.append("```")
        else:
            lines.append("失败：%s" % r.get("error"))
        lines.append("")
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf8")


def _cell(s):
    return str(s or "").replace("|", "\\|").replace("\n", " ")[:40]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8800")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条，0 = 全部")
    ap.add_argument("--only", default="", help="只跑包含该关键词的问题")
    ap.add_argument("--out", default=str(ROOT / "replay"))
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    items = collect_queries(RUN_DIR, args.only or None, args.limit or None)
    if not items:
        print("没有找到历史提问（%s）" % RUN_DIR)
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = out_dir / "results.jsonl"

    print("回放 %d 条 → %s" % (len(items), out_dir))
    rows = []
    with rows_path.open("w", encoding="utf8") as fh:
        for i, (query, origin) in enumerate(items, 1):
            print("  [%d/%d] %s" % (i, len(items), query[:40]), end="", flush=True)
            res = ask(args.base, query, args.timeout)
            res["query"] = query
            res["origin_run"] = origin
            rows.append(res)
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            fh.flush()
            if res.get("ok"):
                print("  %dms %s" % (res["total_ms"],
                                     "四段齐" if res["sections_ok"] else "缺" +
                                     "/".join(res["sections_missing"])))
            else:
                print("  失败: %s" % res.get("error"))

    stat = summarize(rows)
    write_report(out_dir, rows, stat, args.base)

    print("\n汇总：共 %d 条，成功 %d，拦截 %d，失败 %d；四段齐 %d，带引用 %d，降级 %d，均 %dms" % (
        stat["total"], stat["ok"], stat["blocked"], stat["failed"],
        stat["four_section_ok"], stat["with_cites"], stat["degraded"], stat["avg_ms"]))
    print("报告：%s" % (out_dir / "report.md"))
    return 0 if stat["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
