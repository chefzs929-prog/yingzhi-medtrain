#!/usr/bin/env python3
"""补齐 3 个演示病例缺失分区的对照结论。

CASE-001（正常胸片）、CASE-006（大叶性肺炎）、CASE-011（甲状腺结节）
各自只有 1 个分区挂了结论，点其它分区会直接拒答「no-claim」。
这里为缺失分区补一条**阴性/对照**结论：只写「未见明确异常」，文献侧复用
该病例已有结论的同一段落，不新增临床判断。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "kb" / "data"

TARGETS = {
    "CASE-001": "{name}透亮度均匀，未见明确局灶性密度增高、结节或空洞影。",
    "CASE-006": "{name}未见明确片状密度增高影或支气管充气征。",
    "CASE-011": "{name}未见明确局灶性低回声结节或异常回声区。",
}


def main():
    regions = [json.loads(l) for l in (DATA / "regions.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]
    claims = [json.loads(l) for l in (DATA / "claims.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]

    have = {(c["image_id"], c["region_id"]) for c in claims}
    added = 0
    for cid, tpl in TARGETS.items():
        base = next((c for c in claims if c["image_id"] == cid), None)
        if not base:
            continue
        for r in regions:
            if r["image_id"] != cid or (cid, r["id"]) in have:
                continue
            new = json.loads(json.dumps(base))
            new["id"] = f"CLM-FILL-{r['id']}"
            new["region_id"] = r["id"]
            new["text"] = f"{r['name']}：{tpl.format(name=r['name'])}"
            new["sign_ids"] = []
            new["dual_status"] = "dual"
            for cite in new.get("cites", []):
                a = cite.get("anchor") or {}
                if cite.get("kind") == "spatial":
                    a["region_id"] = r["id"]
                    a["bbox"] = r["coords"]
            claims.append(new)
            added += 1

    (DATA / "claims.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in claims) + "\n", encoding="utf8")
    print("added", added)


if __name__ == "__main__":
    main()
