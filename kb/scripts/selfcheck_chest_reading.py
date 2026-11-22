#!/usr/bin/env python3
"""胸片阅片数据集自检。

检查的不是“模型准不准”，而是这次重做最容易被质疑的几条数据规则：
  - 只收 CR 胸部；多图拼接移出队列；
  - 每个分区有独立状态与文本；
  - 未提及不写成正常；
  - 局灶病例只有病灶区异常；
  - 来源、许可、SHA-256 齐全。

用法：
  python3 kb/scripts/selfcheck_chest_reading.py
输出：
  outputs/medtrain/chest_selfcheck.md
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / "kb/data/chest_reading.json").read_text(encoding="utf8"))
OUT = ROOT / "outputs/medtrain/chest_selfcheck.md"
ALLOWED = {"abnormal", "normal", "unmentioned", "limited"}
GENERIC_UNMENTIONED = "公开来源未逐区描述该分区；本工具不作正常或异常的推断。"

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, ok, detail))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


cases = DATA["cases"]
enabled = [c for c in cases if c["enabled"]]
disabled = [c for c in cases if not c["enabled"]]

check("总数 23 例 CR 胸部", len(cases) == 23, f"actual={len(cases)}")
check("启用 21 例", len(enabled) == 21, f"actual={len(enabled)}")
check("移出 2 例多图/拼接", len(disabled) == 2, "、".join(c["id"] for c in disabled))

for c in enabled:
    cid = c["id"]
    expected = 3 if c["pose"] == "LAT" else 8
    check(f"{cid} 分区数 {expected}", len(c["zones"]) == expected, f"actual={len(c['zones'])}")
    check(f"{cid} 状态合法", all(z["status"] in ALLOWED for z in c["zones"]),
          "、".join(sorted({z["status"] for z in c["zones"]})))
    check(f"{cid} 文本非空", all(z["text"].strip() for z in c["zones"]))
    check(f"{cid} 来源/许可/SHA", bool(c["source_page"]) and bool(c["license"]) and bool(c["sha256"]))
    check(f"{cid} 征象 id 可查", all(s in DATA["sign_index"] for s in c["signs"]),
          "、".join(s for s in c["signs"] if s not in DATA["sign_index"]))

    ab = [z for z in c["zones"] if z["status"] == "abnormal"]
    un = [z for z in c["zones"] if z["status"] == "unmentioned"]
    if ab and un:
        ab_text = {z["text"] for z in ab}
        un_text = {z["text"] for z in un}
        check(f"{cid} 异常区与未提及区文本不同", not (ab_text & un_text))
    if ab:
        check(f"{cid} 异常区有征象或依据", bool(c["signs"]) or all(z["basis"] for z in ab))
    if c["pose"] == "PA":
        check(f"{cid} PA 患者侧别正确",
              all(z["side"] == "right" for z in c["zones"] if z["id"].startswith("R")) and
              all(z["side"] == "left" for z in c["zones"] if z["id"].startswith("L")))

    # 影像哈希：优先校验构建产物，其次校验源图
    served = ROOT / "outputs/medtrain" / c["image"]
    source = ROOT / "kb" / c["image"]
    if served.exists():
        check(f"{cid} 构建影像 SHA-256", sha256(served) == c["sha256"])
    elif source.exists():
        check(f"{cid} 源影像 SHA-256", sha256(source) == c["sha256_source"])

# 关键病例的定点检查
by_id = {c["id"]: c for c in cases}
c1 = by_id["CASE-001"]
check("CASE-001 全部分区 normal", all(z["status"] == "normal" for z in c1["zones"]))
c6 = by_id["CASE-006"]
check("CASE-006 右肺中野/下野 abnormal",
      [z["id"] for z in c6["zones"] if z["status"] == "abnormal"] == ["RML", "RLL"])
check("CASE-006 右肺上野 unmentioned",
      next(z for z in c6["zones"] if z["id"] == "RUL")["status"] == "unmentioned")
c202 = by_id["CASE-202"]
check("CASE-202 右肺中野/下野 abnormal",
      [z["id"] for z in c202["zones"] if z["status"] == "abnormal"] == ["RML", "RLL"])
c36 = by_id["CASE-036"]
check("CASE-036 右侧三区 abnormal",
      [z["id"] for z in c36["zones"] if z["status"] == "abnormal"] == ["RUL", "RML", "RLL"])
check("CASE-036 左侧三区 unmentioned",
      all(z["status"] == "unmentioned" for z in c36["zones"] if z["id"] in ("LUL", "LML", "LLL")))
c3 = by_id["CASE-003"]
check("CASE-003 至少一个 limited 分区", any(z["status"] == "limited" for z in c3["zones"]))
check("数据不挂指南条款（避免误用）", all("guideline" not in json.dumps(c, ensure_ascii=False) for c in cases))

passed = sum(1 for _, ok, _ in rows if ok)
total = len(rows)
lines = [
    "# 胸片阅片数据集自检",
    "",
    f"> 生成时间：2026-11-20 ｜ 通过 {passed}/{total}",
    "",
    "| # | 检查 | 结果 | 说明 |",
    "| --- | --- | --- | --- |",
]
for i, (name, ok, detail) in enumerate(rows, 1):
    lines.append(f"| {i} | {name} | {'通过' if ok else '**未通过**'} | {detail} |")
lines += [
    "",
    "> 这是数据规则自检，不是影像诊断准确率；正式教学前须由医学人员逐条审核。",
]
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
print(f"{passed}/{total} passed -> {OUT}")
for name, ok, detail in rows:
    if not ok:
        print("FAIL", name, detail)
