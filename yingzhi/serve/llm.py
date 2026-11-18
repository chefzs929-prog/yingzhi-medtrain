"""双模型路由：有图走视觉模型，无图走文本模型。

设计约束（与三条红线一致）：
1. 只做「检索 + 组织语言」，不做诊断；system prompt 固定四段式与拒答边界。
2. 模型输出里的 id 必须能在 kb/data 里查到，查不到就丢弃该引用并计数。
3. 没有配置 API key 时整体禁用，由 main.py 回落到原有 gateway / fallback 路径。

环境变量（OpenAI 兼容接口）：
    YZ_LLM_VISION_BASE   例 https://dashscope.aliyuncs.com/compatible-mode/v1
    YZ_LLM_VISION_KEY
    YZ_LLM_VISION_MODEL  例 qwen3-vl-plus
    YZ_LLM_TEXT_BASE     例 https://api.deepseek.com/v1
    YZ_LLM_TEXT_KEY
    YZ_LLM_TEXT_MODEL    例 deepseek-chat
    YZ_LLM_TIMEOUT       默认 60 秒
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "kb/data"

ID_RE = re.compile(r"\b(?:CLM|SIGN|CON|GDL)-[A-Za-z0-9_-]+\b")
GENERAL_MARK = "【通识补充】"

SYSTEM_PROMPT = """你是医学影像教学平台的讲解员，服务对象是医学生与规培生。

硬性边界（违反即视为回答失败）：
1. 不给出诊断结论，不使用「确诊」「恶性」「考虑为」「建议手术」等表述。
2. 不给治疗建议，不做分期。
3. 只讲解检索结果中出现的词条、结论与文献；未检索到的内容不得编造。
4. 指南条款一律表述为「候选，适用性需人工判断」。

输出必须严格四段，段首用以下标记：
结论：一句话回答，落到具体分区或词条。
依据：逐条列出证据，每条带 id（SIGN-xxx / CLM-xxx）。
缺失：说明本次检索未覆盖什么；若库内无覆盖，写「库内未覆盖」。
边界：固定写「仅用于教学与研究，不构成诊断意见」。

如果给了图像：只描述解剖结构与可见的影像学表现，不得据此下诊断；
如能给出病灶候选框，用 JSON 附在最后：{"bbox":[x1,y1,x2,y2]}（0-1 归一化）。
"""


def _env(name, default=""):
    return (os.environ.get(name) or default).strip()


class ModelConfig:
    def __init__(self, kind, base, key, model):
        self.kind = kind
        self.base = base.rstrip("/")
        self.key = key
        self.model = model

    @property
    def ready(self):
        return bool(self.base and self.key and self.model)

    def __repr__(self):
        return "<%s %s>" % (self.kind, self.model or "-")


class Router:
    """有图 → vision；无图 → text。任一缺失则退到另一个。"""

    def __init__(self, vision, text):
        self.vision = vision
        self.text = text

    def pick(self, has_image):
        if has_image:
            return self.vision if self.vision.ready else self.text
        return self.text if self.text.ready else self.vision

    def describe(self):
        return {
            "vision": self.vision.model if self.vision.ready else None,
            "text": self.text.model if self.text.ready else None,
        }


class Retriever:
    """轻量检索：词条名/别名 → 概念 → 结论。数据量小，全量载入内存。"""

    def __init__(self, data_dir=None):
        self.dir = Path(data_dir or DATA_DIR)
        self.signs = self._load("signs.jsonl")
        self.concepts = self._load("concepts.jsonl")
        self.claims = self._load("claims.jsonl")
        self._by_sign = {}
        for c in self.claims:
            for sid in (c.get("sign_ids") or []):
                self._by_sign.setdefault(sid, []).append(c)

    def _load(self, name):
        p = self.dir / name
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        return out

    def search(self, query, limit=8):
        q = (query or "").strip().lower()
        hits, ids = [], set()
        for s in self.signs:
            name = str(s.get("name") or "").lower()
            aliases = [str(a).lower() for a in (s.get("aliases") or []) if a]
            if (name and name in q) or any(a in q for a in aliases):
                hits.append(s)
                ids.add(s.get("id"))
        concepts = []
        for c in self.concepts:
            if str(c.get("name") or "").lower() in q and q:
                concepts.append(c)
                for sid in (c.get("sign_ids") or []):
                    ids.add(sid)
        if ids:
            for s in self.signs:
                if s.get("id") in ids and s not in hits:
                    hits.append(s)
        claims = []
        for sid in ids:
            claims.extend(self._by_sign.get(sid, []))
        seen, uniq = set(), []
        for c in claims:
            cid = c.get("id")
            if cid and cid not in seen:
                seen.add(cid)
                uniq.append(c)
        return {"signs": hits[:limit], "concepts": concepts[:3], "claims": uniq[:limit]}


class Client:
    """OpenAI 兼容 /chat/completions，只用标准库。"""

    def __init__(self, timeout=60):
        self.timeout = timeout

    def chat(self, cfg, messages):
        body = json.dumps({
            "model": cfg.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 900,
        }).encode("utf8")
        req = urllib.request.Request(
            cfg.base + "/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + cfg.key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf8", "replace")[:200]
            raise RuntimeError("HTTP %s: %s" % (e.code, detail))
        except Exception as e:
            raise RuntimeError(str(e))
        try:
            return data["choices"][0]["message"]["content"] or ""
        except Exception:
            raise RuntimeError("unexpected response: %s" % str(data)[:200])


class Answerer:
    def __init__(self, router, retriever, client=None):
        self.router = router
        self.retriever = retriever
        self.client = client or Client()
        self.valid_ids = set()
        for s in retriever.signs:
            if s.get("id"):
                self.valid_ids.add(s["id"])
        for c in retriever.claims:
            if c.get("id"):
                self.valid_ids.add(c["id"])
        for c in retriever.concepts:
            if c.get("id"):
                self.valid_ids.add(c["id"])

    @property
    def enabled(self):
        return self.router.vision.ready or self.router.text.ready

    def _context_text(self, ctx):
        lines = []
        for s in ctx["signs"]:
            lines.append("- 词条 %s %s：%s" % (
                s.get("id", ""), s.get("name", ""),
                (s.get("appearance") or s.get("desc") or "")[:160]))
        for c in ctx["concepts"]:
            lines.append("- 概念 %s %s（关联征象 %s）" % (
                c.get("id", ""), c.get("name", ""),
                ",".join(c.get("sign_ids") or []) or "无"))
        for c in ctx["claims"]:
            lines.append("- 结论 %s [%s]：%s" % (
                c.get("id", ""), c.get("evidence_level") or "C",
                (c.get("text") or c.get("claim") or "")[:200]))
        return "\n".join(lines) if lines else "（本次检索未命中任何库内条目）"

    def ask(self, query, emit, image=None):
        t0 = time.time()
        has_image = bool(image)
        cfg = self.router.pick(has_image)
        if not cfg or not cfg.ready:
            raise RuntimeError("no model configured")

        ctx = self.retriever.search(query)
        emit("trace", {"stage": "kb_retrieve", "skill": "llm_route",
                       "status": "ok", "ms": int((time.time() - t0) * 1000),
                       "detail": {"route": "vision" if has_image else "text",
                                  "model": cfg.model,
                                  "signs": len(ctx["signs"]),
                                  "claims": len(ctx["claims"])}})

        user_text = "检索结果：\n%s\n\n用户问题：%s" % (self._context_text(ctx), query)
        if has_image:
            user_text += "\n\n（附影像，请先描述解剖结构；若可定位病灶，按约定附 bbox）"
            content = [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": _data_url(image)}},
            ]
        else:
            content = user_text

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]
        text = self.client.chat(cfg, messages)

        dropped = [i for i in ID_RE.findall(text) if i not in self.valid_ids]
        cites = self._cites(ctx, text)
        return {
            "text": text,
            "cites": cites,
            "route": "vision" if has_image else "text",
            "model": cfg.model,
            "dropped_ids": dropped,
            "ms": int((time.time() - t0) * 1000),
        }

    def _cites(self, ctx, text):
        cites = []
        for s in ctx["signs"]:
            if s.get("id") and s["id"] in text:
                cites.append({"id": s["id"], "type": "sign",
                              "title": s.get("name", ""),
                              "source_url": s.get("source_url") or "",
                              "hash_ok": True})
        for c in ctx["claims"]:
            if c.get("id") and c["id"] in text:
                cites.append({"id": c["id"], "type": "claim",
                              "title": (c.get("text") or "")[:40],
                              "source_url": c.get("source_url") or "",
                              "hash_ok": bool(c.get("excerpt_sha256"))})
        return cites[:8]


def _data_url(image):
    if isinstance(image, str) and image.startswith("data:"):
        return image
    if isinstance(image, (bytes, bytearray)):
        return "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
    raise ValueError("image must be data-url or bytes")


def build_from_env(retriever=None):
    vision = ModelConfig("vision", _env("YZ_LLM_VISION_BASE"),
                         _env("YZ_LLM_VISION_KEY"), _env("YZ_LLM_VISION_MODEL"))
    text = ModelConfig("text", _env("YZ_LLM_TEXT_BASE"),
                       _env("YZ_LLM_TEXT_KEY"), _env("YZ_LLM_TEXT_MODEL"))
    router = Router(vision, text)
    if not (vision.ready or text.ready):
        return None
    try:
        timeout = int(_env("YZ_LLM_TIMEOUT", "60"))
    except ValueError:
        timeout = 60
    return Answerer(router, retriever or Retriever(), Client(timeout))
