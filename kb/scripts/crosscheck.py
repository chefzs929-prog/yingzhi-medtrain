"""交叉验证：网页 JS 匹配（kb/app/ask-core.js）与 Python 引擎（kb/scripts/ask_engine.py）结果是否一致。

同一批 69 条问法，两边各跑一遍，逐条比对 kind（answer 子类 / refusal / unknown）。
不一致即失败，退出码 1。

用法：python3 kb/scripts/crosscheck.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CORE = ROOT / "kb/app/ask-core.js"
BANK = ROOT / "kb/data/ask_bank.json"
CASES = ROOT / "kb/data/eval_cases.json"

sys.path.insert(0, str(ROOT / "kb/scripts"))
import ask_engine  # noqa: E402


def collect_rows():
    ev = json.loads(CASES.read_text(encoding="utf8"))
    rows = []
    for key in ("variants", "holdout", "final"):
        for v in ev.get(key, []):
            rows.append({"q": v["q"], "case": ev["case"], "set": key,
                         "accept": v["accept"]})
    return rows


JS_DRIVER = """
const fs = require('fs');
const path = require('path');
const core = require(process.argv[2]);
const bank = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const rows = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const out = rows.map(r => {
  const res = core.classify(r.q, r.case, bank.items);
  return { q: r.q, kind: res.kind, score: Math.round(res.score * 1000) / 1000 };
});
process.stdout.write(JSON.stringify(out));
"""


def run_js(rows):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf8") as f:
        f.write(JS_DRIVER)
        driver = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf8") as f:
        json.dump(rows, f, ensure_ascii=False)
        rowsf = f.name
    try:
        out = subprocess.run(
            ["node", driver, str(CORE), str(BANK), rowsf],
            capture_output=True, text=True, timeout=120,
        )
        if out.returncode != 0:
            raise RuntimeError("node 执行失败: " + out.stderr[:500])
        return json.loads(out.stdout)
    finally:
        Path(driver).unlink(missing_ok=True)
        Path(rowsf).unlink(missing_ok=True)


def main():
    rows = collect_rows()
    bank = ask_engine.Bank(BANK)

    js = run_js(rows)
    mismatches = []
    for r, j in zip(rows, js):
        kind, score, _ = ask_engine.classify(r["q"], r["case"], bank.items)
        if kind != j["kind"] or abs(round(score, 3) - j["score"]) > 0.002:
            mismatches.append({
                "q": r["q"], "set": r["set"],
                "py_kind": kind, "js_kind": j["kind"],
                "py_score": round(score, 3), "js_score": j["score"],
            })

    total = len(rows)
    print(f"用例 {total} 条 · JavaScript 与 Python 结果比对")
    if not mismatches:
        print(f"PASS  两端完全一致（{total}/{total}）")
        return 0

    print(f"FAIL  {len(mismatches)} 条不一致：")
    for m in mismatches[:20]:
        print(f"  [{m['set']}] {m['q']}  py={m['py_kind']}({m['py_score']})  js={m['js_kind']}({m['js_score']})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
