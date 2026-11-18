#!/usr/bin/env python3
"""低频补下缺失的候选图（仅腹部与肌骨组），避免触发限流。"""
import json
import time
import urllib.request
from pathlib import Path

CAND = Path(__file__).resolve().parent.parent / "_candidates2"
UA = "DeepWorksKB/1.0 (hackathon teaching demo)"
TARGETS = set(range(45, 60))

m = json.loads((CAND / "manifest.json").read_text(encoding="utf8"))
for i, it in enumerate(m, 1):
    if i not in TARGETS or it.get("file") or not it.get("thumb"):
        continue
    ext = ".jpg" if it["mime"] == "image/jpeg" else ".png"
    out = CAND / f"cand-{i:03d}{ext}"
    for attempt in range(2):
        try:
            req = urllib.request.Request(it["thumb"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                out.write_bytes(r.read())
            it["file"] = out.name
            print("ok", out.name, flush=True)
            break
        except Exception as e:
            print("retry", out.name, str(e)[:40], flush=True)
            time.sleep(45)
    (CAND / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf8")
    time.sleep(15)
print("done", sum(1 for x in m if x.get("file")))
