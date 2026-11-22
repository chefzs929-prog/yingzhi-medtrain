#!/usr/bin/env python3
"""重试下载失败的候选图（低频率，避免 429）。"""
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAND = ROOT / "_candidates"
UA = "DeepWorksKB/1.0 (hackathon teaching demo)"
m = json.loads((CAND / "manifest.json").read_text(encoding="utf8"))
for i, it in enumerate(m, 1):
    if it.get("file"):
        continue
    if not it.get("thumb"):
        continue
    ext = ".jpg" if it["mime"] == "image/jpeg" else ".png"
    out = CAND / f"cand-{i:03d}{ext}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(it["thumb"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                out.write_bytes(r.read())
            it["file"] = out.name
            print("ok", out.name, it["title"][:50], flush=True)
            break
        except Exception as e:
            print("retry", out.name, str(e)[:60], flush=True)
            time.sleep(15)
    time.sleep(8)
    (CAND / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf8")
print("done", sum(1 for x in m if x.get("file")), "/", len(m))
