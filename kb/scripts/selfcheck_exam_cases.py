#!/usr/bin/env python3
"""病例题数据自检：结构、答案、影像、SHA-256、许可、对比对引用。

输出：outputs/medtrain/exam_selfcheck.md
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb/data/exam_cases.json"
OUT = ROOT / "outputs/medtrain/exam_selfcheck.md"
OK_LIC = re.compile(r"^(CC0|CC BY|CC BY-SA|Public domain|PD)", re.I)

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf8"))
    cases = data["cases"]
    pairs = data["pairs"]
    ids = [c["id"] for c in cases]
    by_id = {c["id"]: c for c in cases}

    check("版本号存在", data.get("version") == 1, str(data.get("version")))
    check("病例 10 例", len(cases) == 10, str(len(cases)))
    check("大纲 10 条", len(data["syllabus"]) == 10, str(len(data["syllabus"])))
    check("对比对 8 组", len(pairs) == 8, str(len(pairs)))
    check("病例 id 唯一", len(ids) == len(set(ids)), str(ids))
    check("声明存在", "不构成诊断" in data.get("disclaimer", ""))
    check("题目自编说明存在", "不是官方真题" in data.get("question_basis", ""))

    for item in data["syllabus"]:
        check("大纲条目 %s 指向病例" % item["id"], item["case_id"] in by_id, item["case_id"])

    for c in cases:
        cid = c["id"]
        check("%s 有主诉" % cid, bool(c["vignette"].get("chief")))
        check("%s 有现病史" % cid, len(c["vignette"].get("present", "")) >= 20)
        check("%s 5 个选项" % cid, len(c["options"]) == 5, str(len(c["options"])))
        check("%s 答案下标合法" % cid, 0 <= int(c["answer"]) < 5, str(c["answer"]))
        check("%s 选项唯一" % cid, len(set(c["options"])) == 5)
        check("%s 解析 >= 40 字" % cid, len(c.get("explain", "")) >= 40, str(len(c.get("explain", ""))))
        check("%s 易错点存在" % cid, bool(c.get("pitfall")))
        check("%s 考点存在" % cid, bool(c.get("exam_tip")))
        check("%s 影像文件存在" % cid, (ROOT / "kb" / c["image"]).exists(), c["image"])
        if (ROOT / "kb" / c["image"]).exists():
            check("%s SHA-256 一致" % cid, sha256(ROOT / "kb" / c["image"]) == c["sha256"])
        check("%s 许可为开放许可" % cid, bool(OK_LIC.match(c["source"]["license"])), c["source"]["license"])
        check("%s 来源为 https" % cid, c["source"]["url"].startswith("https://"), c["source"]["url"])
        for other in c.get("compare", []):
            check("%s 对比引用 %s" % (cid, other), other in by_id, other)

    for p in pairs:
        check("%s 左例存在" % p["id"], p["left"] in by_id, p["left"])
        check("%s 右例存在" % p["id"], p["right"] in by_id, p["right"])
        check("%s 有相同点" % p["id"], len(p.get("same", [])) >= 2)
        check("%s 有鉴别轴" % p["id"], len(p.get("diff", [])) >= 3, str(len(p.get("diff", []))))
        check("%s 有易错提示" % p["id"], bool(p.get("trap")))
        check("%s 有带看问题" % p["id"], bool(p.get("question")))
        for d in p.get("diff", []):
            check("%s 鉴别轴字段完整" % p["id"],
                  all(d.get(k) for k in ("axis", "left", "right")), str(d))

    passed = sum(1 for _, ok, _ in rows if ok)
    total = len(rows)
    lines = [
        "# 病例题数据自检",
        "",
        f"> 通过 {passed}/{total}",
        "",
        "| # | 检查 | 结果 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for i, (name, ok, detail) in enumerate(rows, 1):
        lines.append(f"| {i} | {name} | {'通过' if ok else '**未通过**'} | {detail} |")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"{passed}/{total} passed -> {OUT}")
    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
