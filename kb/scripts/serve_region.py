#!/usr/bin/env python3
"""v1.1 影像区域定位工作台 · 独立服务。

与 kb/scripts/serve.py 分开：本服务只提供区域定位与双引用相关的 5 个接口，
前端是 kb/app/ 下的独立界面，不依赖 kb/web 的单页演示。

启动：
    python3 kb/scripts/serve_region.py --port 4191
    open http://127.0.0.1:4191
"""
import argparse
import hashlib
import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
APP = KB / "app"
DATA = KB / "data"
IMAGES = KB / "images"

VERSION = "2.0"

# 模型服务在 8800（yingzhi/serve/main.py）。本服务只做页面与数据，
# 模型调用原样转发过去，避免前端跨端口（SSE 跨端口要处理 CORS 与预检）。
AGENT_BASE = (os.environ.get("YZ_AGENT_BASE") or "http://127.0.0.1:8800").rstrip("/")
CROSS_GAP = 0.15
MIN_COVER = 0.35
SECOND_MIN = 0.25
MIN_SIDE = 0.015
MAX_AREA = 0.60

CHAPTER_ORDER = ["胸部", "四肢", "脊柱", "头颅", "腹部", "乳腺", "超声"]
CHAPTER_DESC = {
    "胸部": "胸片 PA/侧位：肺野分区、纵隔与膈下结构",
    "四肢": "膝、手、足、踝、肩、肘、腕、骨盆的标准投照",
    "脊柱": "颈椎与腰椎侧位：节段划分与椎前软组织",
    "头颅": "头颅侧位与 MR 轴位：颅穹窿、颅底与图像内分区",
    "腹部": "腹部 CT 轴位：图像内相对位置，不推断具体器官",
    "乳腺": "乳腺 MLO：图像内上/下/乳晕后分区",
    "超声": "超声局部视野：只给探头相对位置",
}

SIDE_LABEL = {"right": "患者右侧", "left": "患者左侧", "midline": "中线", "unknown": "侧别未知"}


def read_jsonl(name):
    p = DATA / name
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf8").splitlines() if line.strip()]


def sha8(text):
    return hashlib.sha256(str(text).strip().encode("utf8")).hexdigest()[:8]


def full_hash(text):
    return hashlib.sha256(str(text).strip().encode("utf8")).hexdigest()


def mod_text(v):
    """cases.jsonl 里 modality 有 str 与 list 两种写法，统一成可显示文本。"""
    if isinstance(v, (list, tuple)):
        return "/".join(str(x) for x in v)
    return str(v or "")


def area(b):
    return max(0.0, b[2]) * max(0.0, b[3])


def inter(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2 = min(a[0] + a[2], b[0] + b[2])
    y2 = min(a[1] + a[3], b[1] + b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


class RegionKB:
    def __init__(self):
        self.atlases = {a["id"]: a for a in read_jsonl("atlases.jsonl")}
        self.regions = read_jsonl("regions.jsonl")
        self.regions_by_id = {r["id"]: r for r in self.regions}
        self.claims = read_jsonl("claims.jsonl")
        self.cases = read_jsonl("cases.jsonl")
        self.signs = {s["id"]: s for s in read_jsonl("signs.jsonl")}
        self.guidelines = {g["id"]: g for g in read_jsonl("guidelines.jsonl")}
        self._evaluated = None
        self._stats = None
        self._region_count = None

    def claim_stats(self):
        if self._stats is None:
            st = {}
            for c in self.evaluated_claims():
                d = st.setdefault(c["image_id"], {"dual": 0, "single": 0, "broken": 0})
                d[c["status"]] = d.get(c["status"], 0) + 1
            self._stats = st
        return self._stats

    def region_counts(self):
        if self._region_count is None:
            cnt = {}
            for r in self.regions:
                cnt[r["image_id"]] = cnt.get(r["image_id"], 0) + 1
            self._region_count = cnt
        return self._region_count

    # ---------- 引用门禁 ----------
    def evaluate(self, claim):
        cites = claim.get("cites") or []
        spatial = next((c for c in cites if c.get("kind") == "spatial"), None)
        docs = [c for c in cites if c.get("kind") == "doc"]
        problems = []

        if spatial is None:
            problems.append({
                "code": "missing_spatial",
                "message": claim.get("gate_reason") or "缺少空间锚点",
            })
        else:
            b = spatial["anchor"].get("bbox") or []
            bad_geom = (
                len(b) != 4 or b[2] <= 0 or b[3] <= 0
                or b[0] < 0 or b[1] < 0
                or b[0] + b[2] > 1.0001 or b[1] + b[3] > 1.0001
            )
            if bad_geom:
                problems.append({"code": "anchor_invalid", "message": "空间锚点超出图像范围"})
            if spatial["anchor"].get("region_id") not in self.regions_by_id:
                problems.append({"code": "anchor_invalid", "message": "空间锚点指向不存在的分区"})

        if not docs:
            problems.append({"code": "missing_doc", "message": "缺少文献锚点"})
        for d in docs:
            a = d.get("anchor") or {}
            if not a.get("locator"):
                problems.append({"code": "anchor_invalid", "message": "文献锚点缺少定位符或链接",
                                 "cite_id": d.get("cite_id")})
            expected = a.get("excerpt_sha256") or ""
            actual = full_hash(a.get("excerpt", "")) if len(expected) == 64 else sha8(a.get("excerpt", ""))
            if not expected or actual != expected:
                problems.append({
                    "code": "excerpt_mismatch",
                    "message": "摘录与库内原文不一致",
                    "cite_id": d.get("cite_id"),
                    "expected": a.get("excerpt_sha256"),
                    "actual": actual,
                })

        if any(p["code"] in ("excerpt_mismatch", "anchor_invalid") for p in problems):
            status = "broken"
        elif problems:
            status = "single"
        else:
            status = "dual"
        return status, problems

    def evaluated_claims(self):
        if self._evaluated is None:
            out = []
            for c in self.claims:
                status, problems = self.evaluate(c)
                item = dict(c)
                item["status"] = status
                item["gate"] = {"problems": problems}
                item["spatial"] = next((x for x in c["cites"] if x["kind"] == "spatial"), None)
                item["doc"] = next((x for x in c["cites"] if x["kind"] == "doc"), None)
                out.append(item)
            self._evaluated = out
        return self._evaluated

    # ---------- 定位 ----------
    def locate(self, image_id, bbox):
        b = [float(v) for v in bbox]
        b = [max(0.0, min(1.0, b[0])), max(0.0, min(1.0, b[1])),
             max(0.0, min(1.0 - b[0], b[2])), max(0.0, min(1.0 - b[1], b[3]))]
        regions = [r for r in self.regions if r["image_id"] == image_id and r.get("status") == "active"]
        if not regions:
            return {"status": "no_atlas", "message": "该影像未标注分区，无法区域定位", "bbox": b}

        scored = []
        for r in regions:
            a = inter(b, r["coords"])
            coverage = a / max(1e-9, area(b))
            purity = a / max(1e-9, area(r["coords"]))
            scored.append({
                "region": r, "overlap": a, "coverage": coverage, "purity": purity,
                "score": 0.7 * coverage + 0.3 * purity,
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[0]
        second = scored[1] if len(scored) > 1 else None

        if area(b) > MAX_AREA:
            return {"status": "too_large", "message": "选区过大，请缩小到单一分区后再定位", "bbox": b}
        if b[2] < MIN_SIDE or b[3] < MIN_SIDE:
            return {"status": "too_small", "message": "选区过小，请扩大后再定位", "bbox": b}
        if top["coverage"] < MIN_COVER:
            return {"status": "uncovered", "message": "该图未标注此区域，本工具不对未标注区域作推断", "bbox": b}
        if second and (top["score"] - second["score"]) < CROSS_GAP and second["coverage"] > SECOND_MIN:
            return {
                "status": "cross",
                "message": "选区同时落在两个分区，请缩小范围或直接点选分区",
                "bbox": b,
                "candidates": [self._region_card(top), self._region_card(second)],
                "gap": top["score"] - second["score"],
            }
        return {
            "status": "single",
            "bbox": b,
            "primary": self._region_card(top),
            "secondary": self._region_card(second) if second and second["coverage"] > 0.12 else None,
            "mode": "box",
        }

    def _region_card(self, s):
        r = s["region"]
        atlas = self.atlases.get(r["atlas_id"], {})
        return {
            "region": r,
            "coverage": round(s["coverage"], 4),
            "purity": round(s["purity"], 4),
            "score": round(s["score"], 4),
            "side_label": SIDE_LABEL.get(r["patient_side"], r["patient_side"]),
            "atlas": {
                "id": atlas.get("id"),
                "name": atlas.get("name"),
                "level": atlas.get("level"),
                "method": atlas.get("method"),
                "note": atlas.get("note"),
                "laterality_rule": atlas.get("laterality_rule"),
                "annotator": atlas.get("annotator"),
                "annotated_at": atlas.get("annotated_at"),
            },
            "signs": [{"id": sid, "name": self.signs.get(sid, {}).get("name", sid)}
                      for sid in r.get("sign_ids", [])],
            "claims": [c for c in self.evaluated_claims() if c["region_id"] == r["id"]],
        }

    # ---------- 病例 ----------
    def case_list(self, filt="all", q=""):
        q = (q or "").strip().lower()
        region_count = self.region_counts()
        claim_count = {}
        for c in self.claims:
            claim_count[c["image_id"]] = claim_count.get(c["image_id"], 0) + 1
        stats = self.claim_stats()

        items = []
        for c in self.cases:
            if c.get("status") != "active":
                continue
            has = c["id"] in region_count
            if filt == "locatable" and not has:
                continue
            if filt == "pending" and has:
                continue
            mods = c["modality"] if isinstance(c["modality"], list) else [c["modality"]]
            hay = c["id"] + " " + c["title"] + " " + " ".join(mods) + " " + c["body_part"] + \
                  " " + str(c.get("chapter", "")) + " " + str(c.get("pose_class", ""))
            if q and q not in hay.lower():
                continue
            st = stats.get(c["id"], {})
            items.append({
                "id": c["id"],
                "title": c["title"],
                "modality": mod_text(c.get("modality")),
                "body_part": c["body_part"],
                "image": "/images/" + Path(c["image"]).name,
                "group_id": c.get("group_id"),
                "has_atlas": has,
                "region_count": region_count.get(c["id"], 0),
                "claim_count": claim_count.get(c["id"], 0),
                "dual_count": st.get("dual", 0),
                "single_count": st.get("single", 0),
                "broken_count": st.get("broken", 0),
                "license": c.get("license"),
                "artist": c.get("artist"),
                "source_page": c.get("source_page"),
                "chapter": c.get("chapter", "胸部"),
                "pose_class": c.get("pose_class", ""),
                "level": c.get("level", "global"),
                "evidence_level": c.get("evidence_level", "C"),
            })
        return items

    def chapters(self):
        stats = self.claim_stats()
        rc = self.region_counts()
        bucket = {}
        for c in self.cases:
            if c.get("status") != "active":
                continue
            ch = c.get("chapter") or "胸部"
            d = bucket.setdefault(ch, {"name": ch, "desc": CHAPTER_DESC.get(ch, ""),
                                       "count": 0, "parts": set(), "regions": 0, "dual": 0})
            d["count"] += 1
            d["parts"].add(c["body_part"])
            d["regions"] += rc.get(c["id"], 0)
            d["dual"] += stats.get(c["id"], {}).get("dual", 0)
        out = []
        for ch in CHAPTER_ORDER + [x for x in bucket if x not in CHAPTER_ORDER]:
            if ch in bucket:
                d = bucket[ch]
                d["parts"] = sorted(d["parts"])
                out.append(d)
        return {"chapters": out}

    def case_detail(self, image_id):
        c = next((x for x in self.cases if x["id"] == image_id), None)
        if not c:
            return None
        atlas = next((a for a in self.atlases.values() if image_id in a.get("images", [])), None)
        regions = [r for r in self.regions if r["image_id"] == image_id]
        for r in regions:
            r["signs"] = [{"id": sid, "name": self.signs.get(sid, {}).get("name", sid)}
                          for sid in r.get("sign_ids", [])]
        claims = [x for x in self.evaluated_claims() if x["image_id"] == image_id]
        st = self.claim_stats().get(image_id, {})
        return {
            "case": {
                "id": c["id"], "title": c["title"], "modality": mod_text(c.get("modality")),
                "body_part": c["body_part"], "image": "/images/" + Path(c["image"]).name,
                "license": c.get("license"), "artist": c.get("artist"),
                "source_page": c.get("source_page"), "group_id": c.get("group_id"),
                "privacy_check": c.get("privacy_check"),
                "chapter": c.get("chapter", "胸部"),
                "pose_class": c.get("pose_class", ""),
                "level": c.get("level", "global"),
                "evidence_level": c.get("evidence_level", "C"),
                "teaching_note": c.get("teaching_note", ""),
                "description_public": c.get("description_public", ""),
            },
            "atlas": atlas,
            "regions": regions,
            "claims": claims,
            "gate": self._gate(claims),
            "stats": {"dual": st.get("dual", 0), "single": st.get("single", 0),
                      "broken": st.get("broken", 0)},
        }

    def lesson(self, image_id):
        d = self.case_detail(image_id)
        if not d:
            return None
        case, regions, claims = d["case"], d["regions"], d["claims"]
        cards = []
        for r in regions:
            cl = next((c for c in claims if c["region_id"] == r["id"]), None)
            doc = (cl or {}).get("doc") or {}
            anchor = doc.get("anchor") or {}
            cards.append({
                "region_id": r["id"],
                "name": r["name"],
                "note": r.get("note", ""),
                "patient_side": r.get("patient_side"),
                "coords": r.get("coords"),
                "signs": r.get("signs", []),
                "claim_text": (cl or {}).get("text", ""),
                "claim_status": (cl or {}).get("status", "single"),
                "excerpt": anchor.get("excerpt", ""),
                "doc_title": anchor.get("doc_title", ""),
                "locator": anchor.get("locator", ""),
                "url": anchor.get("url", ""),
            })
        return {
            "case": case,
            "atlas": d["atlas"],
            "objective": f"认识{case['body_part']}的 {len(regions)} 个教学分区，"
                         f"并能把每个分区与库内征象词条对应起来。",
            "cards": cards,
            "quiz": self._quiz(case, regions, claims),
            "gate": d["gate"],
        }

    def _quiz(self, case, regions, claims):
        import random
        if len(regions) < 2:
            return []
        rnd = random.Random(int(sha8(case["id"]), 16))
        out = []
        r = rnd.choice(regions)
        others = [x["name"] for x in regions if x["id"] != r["id"]]
        opts = [r["name"]] + rnd.sample(others, min(3, len(others)))
        rnd.shuffle(opts)
        out.append({
            "type": "locate",
            "prompt": f"「{r.get('note', '')}」描述的是哪个分区？",
            "options": opts, "answer": r["name"], "region_id": r["id"],
            "explain": f"{r['name']}：{r.get('note', '')}",
        })
        pool = [s for s in r.get("signs", [])]
        if pool:
            right = rnd.choice(pool)["name"]
            wrong = [s["name"] for s in self.signs.values()
                     if s["name"] != right and s.get("body_part") == case["body_part"]]
            if len(wrong) < 3:
                wrong = [s["name"] for s in self.signs.values() if s["name"] != right]
            opts2 = [right] + rnd.sample(wrong, 3)
            rnd.shuffle(opts2)
            out.append({
                "type": "sign",
                "prompt": f"{r['name']}在库内关联的征象中，下列哪一项属于本区？",
                "options": opts2, "answer": right, "region_id": r["id"],
                "explain": "以库内 signs.jsonl 的 body_part 归属为准，不代表本例一定出现该征象。",
            })
        return out

    def _gate(self, claims):
        g = {"dual": 0, "single": 0, "broken": 0}
        for c in claims:
            g[c["status"]] = g.get(c["status"], 0) + 1
        return g

    def audit(self):
        items = []
        for c in self.evaluated_claims():
            sp = c.get("spatial")
            dc = c.get("doc")
            items.append({
                "claim_id": c["id"],
                "image_id": c["image_id"],
                "region_id": c["region_id"],
                "text": c["text"],
                "status": c["status"],
                "spatial_cite": sp.get("cite_id") if sp else None,
                "spatial_anchor": ("%s · %s · %s" % (
                    sp["anchor"]["image_id"], sp["anchor"]["region_id"],
                    ",".join("%.3f" % v for v in sp["anchor"]["bbox"]))) if sp else None,
                "doc_cite": dc.get("cite_id") if dc else None,
                "doc_anchor": ("%s · %s · %s" % (
                    dc["anchor"]["doc_title"], dc["anchor"]["version"],
                    dc["anchor"]["locator"])) if dc else None,
                "doc_hash": dc["anchor"]["excerpt_sha256"] if dc else None,
                "problems": c["gate"]["problems"],
            })
        return {"items": items, "gate": self._gate(self.evaluated_claims())}

    def meta(self):
        ev = {}
        for c in self.cases:
            if c.get("status") == "active":
                k = c.get("evidence_level", "C")
                ev[k] = ev.get(k, 0) + 1
        return {
            "version": VERSION,
            "counts": {
                "cases": len([c for c in self.cases if c.get("status") == "active"]),
                "locatable_cases": len({r["image_id"] for r in self.regions}),
                "atlases": len(self.atlases),
                "regions": len(self.regions),
                "claims": len(self.claims),
                "chapters": len(self.chapters()["chapters"]),
            },
            "evidence": ev,
            "gate": self._gate(self.evaluated_claims()),
            "thresholds": {
                "cross_gap": CROSS_GAP, "min_coverage": MIN_COVER,
                "second_min": SECOND_MIN, "min_side": MIN_SIDE, "max_area": MAX_AREA,
            },
        }


K = RegionKB()


def send_json(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def send_file(handler, path, cache=False):
    if not path.exists() or not path.is_file():
        send_json(handler, {"error": "not_found", "path": str(path.name)}, 404)
        return
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "public, max-age=3600" if cache else "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def proxy_stream(handler, url, payload):
    """把 SSE 逐块转发给浏览器。必须边读边写，攒完再发就失去流式意义。"""
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        upstream = urllib.request.urlopen(req, timeout=300)
    except urllib.error.HTTPError as e:
        send_json(handler, {"error": "agent_http", "status": e.code,
                            "detail": e.read().decode("utf8", "replace")[:200]}, 502)
        return
    except (urllib.error.URLError, OSError) as e:
        send_json(handler, {"error": "agent_unavailable",
                            "detail": str(e)[:160],
                            "hint": "模型服务未启动：python3 yingzhi/serve/start.sh"}, 502)
        return

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()
    try:
        while True:
            chunk = upstream.read(512)
            if not chunk:
                break
            handler.wfile.write(chunk)
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        upstream.close()


def proxy_json(handler, url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            body = r.read()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
    except (urllib.error.URLError, OSError) as e:
        send_json(handler, {"error": "agent_unavailable", "detail": str(e)[:160]}, 502)


class Handler(BaseHTTPRequestHandler):
    server_version = "RegionLocate/1.1"

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        one = lambda k: (qs.get(k) or [None])[0]
        try:
            if u.path == "/api/meta":
                send_json(self, K.meta())
            elif u.path == "/api/cases":
                items = K.case_list(one("filter") or "all", one("q") or "")
                send_json(self, {"items": items, "total": len(items)})
            elif u.path.startswith("/api/cases/"):
                cid = urllib.parse.unquote(u.path.rsplit("/", 1)[-1])
                doc = K.case_detail(cid)
                send_json(self, doc or {"error": "not_found"}, 200 if doc else 404)
            elif u.path == "/api/chapters":
                send_json(self, K.chapters())
            elif u.path.startswith("/api/lesson/"):
                cid = urllib.parse.unquote(u.path.rsplit("/", 1)[-1])
                doc = K.lesson(cid)
                send_json(self, doc or {"error": "not_found"}, 200 if doc else 404)
            elif u.path == "/api/health":
                proxy_json(self, AGENT_BASE + "/api/health")
            elif u.path == "/api/audit":
                send_json(self, K.audit())
            elif u.path == "/data/quiz_bank.json":
                target = DATA / "quiz_bank.json"
                if not target.exists():
                    send_json(self, {"error": "not_built",
                                     "hint": "python3 kb/scripts/build_quiz_bank.py"}, 404)
                    return
                send_file(self, target, cache=True)
            elif u.path.startswith("/images/"):
                name = urllib.parse.unquote(u.path.split("/", 2)[-1])
                target = (IMAGES / name).resolve()
                if IMAGES.resolve() not in target.parents:
                    send_json(self, {"error": "forbidden"}, 403)
                    return
                send_file(self, target, cache=True)
            elif u.path in ("/", "/index.html"):
                send_file(self, APP / "index.html")
            elif u.path in ("/teach", "/teach.html"):
                send_file(self, APP / "teach.html")
            elif u.path in ("/clinic", "/clinic.html"):
                send_file(self, APP / "clinic.html")
            elif u.path in ("/paper", "/paper.html"):
                send_file(self, APP / "paper.html")
            else:
                name = urllib.parse.unquote(u.path.lstrip("/"))
                target = (APP / name).resolve()
                if APP.resolve() not in target.parents:
                    send_json(self, {"error": "forbidden"}, 403)
                    return
                send_file(self, target)
        except BrokenPipeError:
            pass
        except Exception as e:
            send_json(self, {"error": "server_error", "detail": str(e)[:200]}, 500)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            body = json.loads(raw or b"{}")
        except Exception:
            send_json(self, {"error": "bad_json"}, 400)
            return
        try:
            if u.path == "/api/ask":
                proxy_stream(self, AGENT_BASE + "/api/ask", raw)
            elif u.path == "/api/locate":
                image_id = body.get("image_id")
                bbox = body.get("bbox")
                if not image_id or not isinstance(bbox, list) or len(bbox) != 4:
                    send_json(self, {"error": "bad_request", "detail": "需要 image_id 与 bbox[4]"}, 400)
                    return
                send_json(self, K.locate(image_id, bbox))
            else:
                send_json(self, {"error": "not_found"}, 404)
        except (TypeError, ValueError) as e:
            send_json(self, {"error": "bad_request", "detail": str(e)[:120]}, 400)
        except BrokenPipeError:
            pass
        except Exception as e:
            send_json(self, {"error": "server_error", "detail": str(e)[:200]}, 500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4191)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Region Locate v{VERSION}  http://{args.host}:{args.port}")
    print(f"  cases={len(K.cases)}  locatable={len({r['image_id'] for r in K.regions})}  "
          f"regions={len(K.regions)}  claims={len(K.claims)}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
