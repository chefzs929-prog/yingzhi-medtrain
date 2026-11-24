#!/usr/bin/env python3
"""当前发布数据的定位算法下限自检。

对象：kb/data/chest_reading.json（21 例启用，153 个教学分区）
方法：复刻 kb/app/locate.js 的 coverage / purity 评分与 cross 阈值，
      对每个分区框做原框、内缩、放大、中心偏移四组扰动。
输出：outputs/medtrain/locate_current.md

说明：这是“框基本正确时算法能否落回该分区”的下限测试，
      不是视觉模型框准确率；端到端准确率 = 模型框准确率 × 本结果。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb/data/chest_reading.json"
OUT = ROOT / "outputs/medtrain/locate_current.md"


def area(box: list[float]) -> float:
    return max(0.0, box[2]) * max(0.0, box[3])


def inter(a: list[float], b: list[float]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def clip(box: list[float]) -> list[float]:
    x, y, w, h = box
    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))
    w = min(1.0 - x, max(0.0, w))
    h = min(1.0 - y, max(0.0, h))
    return [x, y, w, h]


def locate(regions: list[dict], box: list[float]) -> tuple[str, dict | None]:
    """与 kb/app/locate.js 保持一致：含 diffuse（大范围病变）分支。"""
    scored = []
    for r in regions:
        a = inter(box, r["coords"])
        cov = a / max(1e-9, area(box))
        pur = a / max(1e-9, area(r["coords"]))
        scored.append((0.7 * cov + 0.3 * pur, cov, pur, r))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return "uncovered", None
    top = scored[0]
    second = scored[1] if len(scored) > 1 else None
    if box[2] < 0.015 or box[3] < 0.015:
        return "too_small", None
    strong = [x for x in scored if x[2] >= 0.75]
    if area(box) > 0.6 or len(strong) >= 2:
        hit = strong or [x for x in scored if x[1] >= 0.2]
        if hit:
            return "diffuse", None
    if top[1] < 0.35 and top[2] < 0.8:
        return "uncovered", None
    if second and top[0] - second[0] < 0.15 and second[1] > 0.25:
        return "cross", None
    return "single", top[3]


def perturb(coords: list[float], scale: float = 1.0, dx: float = 0.0, dy: float = 0.0) -> list[float]:
    x, y, w, h = coords
    nw, nh = w * scale, h * scale
    return clip([x + (w - nw) / 2 + dx, y + (h - nh) / 2 + dy, nw, nh])


CASES = [
    ("原框内缩 50%", lambda c: perturb(c, 0.5)),
    ("原框", lambda c: perturb(c, 1.0)),
    ("放大 1.5 倍", lambda c: perturb(c, 1.5)),
    ("放大 2 倍", lambda c: perturb(c, 2.0)),
    ("中心偏移 0.05", lambda c: perturb(c, 0.5, 0.05, 0.05)),
    ("中心偏移 0.10", lambda c: perturb(c, 0.5, 0.10, 0.10)),
]


def main() -> None:
    payload = json.loads(DATA.read_text(encoding="utf8"))
    cases = [c for c in payload["cases"] if c.get("enabled", True)]
    zones = [z for c in cases for z in c.get("zones", []) if len(z.get("coords") or []) == 4]

    rows = []
    for label, fn in CASES:
        hit = cross = uncovered = wrong = diffuse = 0
        for c in cases:
            regs = [z for z in c.get("zones", []) if len(z.get("coords") or []) == 4]
            for z in regs:
                status, got = locate(regs, fn(z["coords"]))
                if status == "single" and got and got.get("id") == z.get("id"):
                    hit += 1
                elif status == "cross":
                    cross += 1
                elif status == "diffuse":
                    diffuse += 1
                elif status == "uncovered":
                    uncovered += 1
                else:
                    wrong += 1
        total = hit + cross + diffuse + uncovered + wrong
        rows.append((label, total, hit, cross, diffuse, uncovered, wrong))

    lines = [
        "# 当前发布数据 · 定位算法下限自检",
        "",
        f"- 数据：`kb/data/chest_reading.json`",
        f"- 启用病例：{len(cases)} 例；教学分区：{len(zones)} 个",
        "- 方法：复刻 `kb/app/locate.js` 的 coverage / purity 评分与 cross 阈值；"
        "不是视觉模型框准确率。",
        "",
        "| 输入框 | 分区数 | 命中自身 | 跨区 | 大范围（列累及分区） | 未覆盖 | 错认 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, total, hit, cross, diffuse, uncovered, wrong in rows:
        pct = lambda n: f"{100.0 * n / total:.1f}%" if total else "—"
        lines.append(f"| {label} | {total} | {pct(hit)} | {pct(cross)} | {pct(diffuse)} | {pct(uncovered)} | {pct(wrong)} |")
    lines += [
        "",
        "## 怎么读",
        "",
        "- **原框/内缩/偏移 0.05**：算法应稳定落回原分区；这是“框正确”时的下限。",
        "- **放大 2 倍**：多数进入“大范围”分支，按分区被覆盖比例列出可能累及的分区；"
        "这是范围推断，不再直接拒答——气胸、大量积液正是这种大框形态。",
        "- **错认**：返回单一分区但与原分区不符；当前为 0，说明算法不会把框硬塞给错误分区。",
        "- **端到端**：命题要的“多模态证据定位准确率”还需乘上视觉模型框准确率；本表只覆盖算法侧。",
        "",
        "> 旧脚本 `selfcheck_locate.py` 测的是 `regions.jsonl` 的 433 个历史分区，"
        "与当前发布的 153 个分区不同源，不能直接引用为当前产品指标。",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print("\n".join(lines[:14]))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
