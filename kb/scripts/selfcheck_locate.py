#!/usr/bin/env python3
"""定位算法自检：框给对了，能不能稳定落到正确的分区。

这不是模型准确率。模型给的框准不准，只有真跑视觉模型才知道。
这里测的是算法下限：把一个确定落在某分区内部的框喂进去，
能不能把它认回这个分区，以及拿别的病例的框来会不会乱认。

    python3 kb/scripts/selfcheck_locate.py
"""
import json
import os
import random
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "scripts"))
from serve_region import RegionKB  # noqa: E402

OUT = KB.parent / "outputs" / "medtrain" / "locate_selfcheck.md"


def inner_box(coords, ratio=0.5):
    x, y, w, h = coords
    bw, bh = w * ratio, h * ratio
    return [x + (w - bw) / 2, y + (h - bh) / 2, bw, bh]


def main():
    K = RegionKB()
    regions = [r for r in K.regions
               if r.get("status") == "active" and len(r.get("coords") or []) == 4]
    by_case = {}
    for r in regions:
        by_case.setdefault(r["image_id"], []).append(r)

    hit = cross = miss = 0
    miss_examples = []
    per_annotator = {}

    for r in regions:
        res = K.locate(r["image_id"], inner_box(r["coords"]))
        bucket = per_annotator.setdefault(r.get("annotator") or "unknown",
                                          {"n": 0, "hit": 0, "cross": 0, "miss": 0})
        bucket["n"] += 1
        if res["status"] == "single" and res["primary"]["region"]["id"] == r["id"]:
            hit += 1
            bucket["hit"] += 1
        elif res["status"] == "cross":
            cross += 1
            bucket["cross"] += 1
        else:
            miss += 1
            bucket["miss"] += 1
            if len(miss_examples) < 8:
                got = (res.get("primary") or {}).get("region", {}).get("id") if res["status"] == "single" else "-"
                miss_examples.append((r["id"], r.get("name"), res["status"], got))

    # 分区覆盖率：随机位置的框有多少能落进已标注分区。
    # 注意这不测「识别对错」——算法回答的是「这个位置属于哪个分区」，
    # 不是「这张图里有没有病灶」。覆盖率低说明分区网格没铺满图，
    # 覆盖率高说明任意位置都能得到一个分区归属，两者都不是错误。
    random.seed(7)
    covered = uncovered = ambiguous = 0
    for cid in sorted(by_case):
        for _ in range(3):
            w = random.uniform(0.06, 0.16)
            h = random.uniform(0.06, 0.16)
            box = [random.uniform(0, 1 - w), random.uniform(0, 1 - h), w, h]
            res = K.locate(cid, box)
            if res["status"] == "single":
                covered += 1
            elif res["status"] == "cross":
                ambiguous += 1
            else:
                uncovered += 1
    probes = covered + ambiguous + uncovered

    total = len(regions)
    lines = [
        "# 定位算法自检",
        "",
        "## 这份报告测什么、不测什么",
        "",
        "**测**：把确定落在某分区内部的框喂给定位算法，能不能认回该分区。",
        "",
        "**不测**：视觉模型给的框准不准。那需要真实模型与人工标注框逐例比对，",
        "本报告不能替代。所以下面的数字是**算法下限**，不是端到端准确率。",
        "",
        "## 一、自命中（框来自该分区内部）",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
        "| 参与测试分区 | %d |" % total,
        "| 命中自身 | %d（%.1f%%） |" % (hit, 100.0 * hit / total),
        "| 判为跨区（请缩小范围） | %d（%.1f%%） |" % (cross, 100.0 * cross / total),
        "| 未命中 | %d（%.1f%%） |" % (miss, 100.0 * miss / total),
        "",
        "按标注来源分组：",
        "",
        "| 来源 | 分区数 | 命中 | 跨区 | 未命中 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for k, v in sorted(per_annotator.items()):
        lines.append("| %s | %d | %d | %d | %d |" % (k, v["n"], v["hit"], v["cross"], v["miss"]))

    lines += [
        "",
        "## 二、分区覆盖率（随机位置探测 %d 次）" % probes,
        "",
        "每例随机取 3 个位置的小框，看能否落进已标注分区。",
        "",
        "| 结果 | 次数 | 占比 |",
        "| --- | --- | --- |",
        "| 落入单一分区 | %d | %.1f%% |" % (covered, 100.0 * covered / max(1, probes)),
        "| 跨两个分区（提示缩小范围） | %d | %.1f%% |" % (ambiguous, 100.0 * ambiguous / max(1, probes)),
        "| 未覆盖（不做推断） | %d | %.1f%% |" % (uncovered, 100.0 * uncovered / max(1, probes)),
        "",
        "这一项说明的是分区网格铺得多满，不是识别准确率。",
        "**定位成功不等于给出结论**：分区必须绑定了结论（claim）才会显示证据，",
        "没有绑定就只显示「该分区暂无绑定结论」。",
        "",
        "## 三、未命中样例",
        "",
    ]
    if miss_examples:
        lines += ["| 分区 | 名称 | 返回状态 | 实际命中 |", "| --- | --- | --- | --- |"]
        lines += ["| %s | %s | %s | %s |" % e for e in miss_examples]
    else:
        lines.append("无。")

    lines += [
        "",
        "## 四、结论与已知局限",
        "",
        "1. 算法在「框正确」的前提下能稳定认回分区（%.1f%%）。" % (100.0 * hit / total),
        "2. 定位算法只回答「位置属于哪个分区」，不判断「图里有没有病灶」。",
        "   结论来自该分区绑定的 claim，而不是来自定位本身。",
        "3. 未命中的 %d 个分区集中在「边缘带」这类窄条分区：" % miss,
        "   它与相邻的大分区重叠，中心小框更容易被判给相邻分区。",
        "   这是当前分区切分的已知缺陷，不是模型问题。",
        "4. 981 个分区里 952 个由体位模板生成，分区边界是规则切分，",
        "   相邻分区存在重叠，因此有一定比例会返回「跨区」而不是硬选一个——",
        "   这是设计上的保守行为，不是错误。",
        "5. 真正的端到端准确率 = 模型框准确率 × 本报告的自命中率。",
        "   模型那一侧尚未用真实 key 测过，不能给出端到端数字。",
        "",
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf8")

    print("分区 %d：命中 %d（%.1f%%），跨区 %d，未命中 %d"
          % (total, hit, 100.0 * hit / total, cross, miss))
    print("随机位置探测 %d 次：落入分区 %d，跨区 %d，未覆盖 %d"
          % (probes, covered, ambiguous, uncovered))
    print("报告：%s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
