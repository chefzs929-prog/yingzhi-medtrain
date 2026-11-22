#!/usr/bin/env python3
"""知识问答评测：跑一组固定问题，统计引用、拒答与耗时。

只测「库内依据」这一层：research=false，不触发 PubMed。
判定口径：
- grounded   有本地引用，且不是纯兜底；
- refused    没有本地引用，但正文明确说库内未覆盖；
- ungrounded 没有本地引用，也没拒答 —— 这是风险项。

    python3 kb/scripts/eval_kb.py
    python3 kb/scripts/eval_kb.py --limit 5 --json .deepworks/tmp/eval_kb.json
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

QUESTIONS = [
    "磨玻璃影在CT上怎么描述？",
    "实变和磨玻璃影怎么区分？",
    "胸腔积液在立位胸片上的典型表现是什么？",
    "气胸有哪些影像学征象？",
    "肺结节的边缘毛刺征提示什么？",
    "支气管扩张的CT表现有哪些？",
    "肝血管瘤的强化特点是什么？",
    "胆囊结石的超声表现是什么？",
    "脑梗死和脑出血在CT上怎么区分？",
    "乳腺肿块BI-RADS分级的依据是什么？",
    "甲状腺结节TI-RADS怎么分级？",
    "膝关节骨关节炎的X线表现有哪些？",
    "肺门增大常见于哪些情况？",
    "纵隔淋巴结肿大的判断标准是什么？",
    "肾囊肿和肾癌在CT上怎么区分？",
    "肠梗阻的腹部平片表现有哪些？",
    "骨折愈合过程中的骨痂怎么描述？",
    "乳腺钙化灶的形态怎么分类？",
    "肺间质纤维化的HRCT表现是什么？",
    "心包积液的影像学表现是什么？",
]

REFUSE_MARKS = ("库内未覆盖", "未覆盖", "没有检索到", "证据不足", "不足以判断")


def ask(base, query, timeout=120, mode="auto"):
    body = json.dumps({"query": query, "mode": mode, "research": False,
                       "surface": "eval"}, ensure_ascii=False).encode("utf8")
    req = urllib.request.Request(base.rstrip("/") + "/api/ask", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    cites, done, text, kind = [], None, [], None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf8", "replace").strip()
            if line.startswith("event: "):
                kind = line[7:].strip()
            elif line.startswith("data: "):
                try:
                    ev = json.loads(line[6:])
                except Exception:
                    continue
                if kind == "citation":
                    cites.append(ev)
                elif kind == "delta":
                    text.append(ev.get("text") or "")
                elif kind == "done":
                    done = ev
    return {
        "ms": int((time.time() - t0) * 1000),
        "cites": cites,
        "text": "".join(text),
        "done": done or {},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8800")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--json", default="")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--mode", default="auto", choices=["auto", "agent", "llm"])
    args = ap.parse_args()

    qs = QUESTIONS[:args.limit] if args.limit else QUESTIONS
    rows = []
    stat = {"grounded": 0, "refused": 0, "ungrounded": 0, "error": 0}
    for i, q in enumerate(qs, 1):
        try:
            r = ask(args.base, q, args.timeout, args.mode)
            local = [c for c in r["cites"] if c.get("kind") != "literature"]
            body = r["text"]
            if local:
                verdict = "grounded"
            elif any(m in body for m in REFUSE_MARKS):
                verdict = "refused"
            else:
                verdict = "ungrounded"
            stat[verdict] += 1
            row = {
                "q": q, "verdict": verdict, "local": len(local),
                "off": (r["done"].get("citations") or {}).get("off", 0),
                "served_by": r["done"].get("served_by"),
                "degraded": r["done"].get("degraded"),
                "ms": r["ms"], "chars": len(body),
                "ids": [c.get("id") for c in local],
            }
        except Exception as exc:
            stat["error"] += 1
            row = {"q": q, "verdict": "error", "error": str(exc)[:160]}
        rows.append(row)
        print("%2d. %-30s %-10s local=%s off=%s %sms %s"
              % (i, q[:30], row["verdict"], row.get("local", "-"),
                 row.get("off", "-"), row.get("ms", "-"),
                 ",".join(row.get("ids") or [])[:46]))

    n = len(rows)
    summary = {
        "base": args.base, "n": n, "stat": stat,
        "grounded_rate": round(stat["grounded"] / n, 4) if n else 0,
        "refused_rate": round(stat["refused"] / n, 4) if n else 0,
        "ungrounded_rate": round(stat["ungrounded"] / n, 4) if n else 0,
        "off_total": sum(r.get("off", 0) for r in rows),
        "avg_ms": int(sum(r.get("ms", 0) for r in rows) / n) if n else 0,
        "rows": rows,
    }
    print("\ngrounded=%d refused=%d ungrounded=%d error=%d off_cites=%d  avg=%sms"
          % (stat["grounded"], stat["refused"], stat["ungrounded"],
             stat["error"], summary["off_total"], summary["avg_ms"]))
    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf8")
        print("wrote", p)


if __name__ == "__main__":
    main()
