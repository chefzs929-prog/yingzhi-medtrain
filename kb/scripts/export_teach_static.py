#!/usr/bin/env python3
"""把 kb/app 依赖的 6 个接口导出成静态 JSON，供 GitHub Pages 纯静态托管。

用法：
    python3 kb/scripts/export_teach_static.py [输出目录]
默认输出到 outputs/medtrain/data/teach/。

对应关系（前端 kb/app/static.js）：
    /api/meta       -> meta.json
    /api/cases      -> cases.json
    /api/chapters   -> chapters.json
    /api/audit      -> audit.json
    /api/lesson/:id -> lesson-<id>.json
    /api/cases/:id  -> case-<id>.json
    /api/locate     -> 前端 kb/app/locate.js 本地计算，无需导出
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from serve_region import RegionKB  # noqa: E402

ROOT = HERE.parent.parent
DEFAULT_OUT = ROOT / "outputs/medtrain/data/teach"


def dump(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf8")


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    kb = RegionKB()

    dump(out / "meta.json", kb.meta())
    dump(out / "chapters.json", kb.chapters())
    dump(out / "cases.json", {"items": kb.case_list()})
    dump(out / "audit.json", kb.audit())

    ids = [c["id"] for c in kb.cases if c.get("status") == "active"]
    lessons = details = 0
    for cid in ids:
        d = kb.case_detail(cid)
        if d:
            dump(out / ("case-%s.json" % cid), d)
            details += 1
        l = kb.lesson(cid)
        if l:
            dump(out / ("lesson-%s.json" % cid), l)
            lessons += 1

    total = sum(1 for _ in out.glob("*.json"))
    size = sum(p.stat().st_size for p in out.glob("*.json"))
    print(json.dumps({
        "out": str(out),
        "cases": len(ids),
        "case_detail": details,
        "lesson": lessons,
        "json_files": total,
        "size_mb": round(size / 1048576, 2),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
