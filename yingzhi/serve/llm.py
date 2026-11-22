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

import vision as _vision
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "kb/data"

_PART_HINTS = {
    "胸部": ["肺", "胸", "气", "纵隔", "心包", "支气管", "膈"],
    "肾脏": ["肾"],
    "乳腺": ["乳腺"],
    "甲状腺": ["甲状腺"],
    "脑": ["脑", "出血", "梗死", "腔隙"],
    "骨关节": ["骨", "膝", "关节", "腕", "踝", "脊柱"],
    "腹部": ["腹", "肝", "胆", "肠", "胰", "脾"],
    "头颈": ["头", "颈", "鼻", "咽"],
}

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


def _no_thinking():
    """YZ_LLM_THINKING=off 时在请求体里带 enable_thinking=false。
    仅对支持该字段的模型（如 qwen3 系列）有效，其他 provider 不要设这个变量。"""
    return _env("YZ_LLM_THINKING", "auto").lower() in ("off", "false", "0", "no")


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


def _bigrams(text):
    t = re.sub(r"[\s，。？、,.;:!?（）()\[\]【】\"'“”‘’]", "", text or "")
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _dice(a, b):
    A, B = _bigrams(a), _bigrams(b)
    if not A or not B:
        return 0.0
    return 2.0 * len(A & B) / (len(A) + len(B))


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
        """词条名/别名精确命中优先，字符二元组 Dice 兜底。

        兜底只解决「磨玻璃密度影 vs 磨玻璃影」这类同义表述，
        不做向量检索；阈值 0.45，低于它宁可不召回。
        """
        q = (query or "").strip().lower()
        scored = []
        for s in self.signs:
            name = str(s.get("name") or "").lower()
            aliases = [str(a).lower() for a in (s.get("aliases") or []) if a]
            en = str(s.get("en") or "").lower()
            score = 0.0
            if name and name in q:
                score = 10.0
            elif any(a and a in q for a in aliases):
                score = 9.0
            elif en and en in q:
                score = 8.0
            else:
                sim = _dice(name, q)
                for a in aliases:
                    sim = max(sim, _dice(a, q))
                if sim >= 0.45:
                    score = 4.0 * sim
            if score <= 0:
                continue
            bp = str(s.get("body_part") or "")
            if bp in _PART_HINTS and any(w in q for w in _PART_HINTS[bp]):
                score += 1.0
            scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        hits = [s for _, s in scored][:limit]
        ids = {s.get("id") for s in hits if s.get("id")}

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

    def chat(self, cfg, messages, temperature=0.2, max_tokens=900,
             response_format=None, retries=1):
        payload = {
            "model": cfg.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        # 部分模型（qwen3 系列）默认带思考，会多花 5-10 倍时间。
        # 用 YZ_LLM_THINKING=off 显式关闭；其他 provider 不认这个字段，默认不加。
        if _no_thinking():
            payload["enable_thinking"] = False
        body = json.dumps(payload).encode("utf8")
        last = None
        for attempt in range(retries + 1):
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
                try:
                    return data["choices"][0]["message"]["content"] or ""
                except Exception:
                    raise RuntimeError("unexpected response: %s" % str(data)[:200])
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf8", "replace")[:200]
                last = RuntimeError("HTTP %s: %s" % (e.code, detail))
                # 429/5xx 重试一次；4xx（除 408）直接失败，重试没意义。
                if e.code in (408, 429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise last
            except Exception as e:
                last = RuntimeError(str(e))
                if attempt < retries:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise last
        raise last


JSON_SYSTEM = """只输出一个 JSON 对象，不要 markdown 代码围栏，不要解释。
字段必须严格按调用方给的 schema；没有把握的字段用 null，不要编造。
医学内容只做教学描述，不给诊断结论，不给治疗建议。"""


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

    def _merge_ctx(self, queries, limit_signs=8, limit_claims=6, limit_concepts=3):
        """多条查询分别检索后按 id 去重合并，先到先得（query 在前，权重天然更高）。"""
        out = {"signs": [], "concepts": [], "claims": []}
        seen = {k: set() for k in out}
        for q in queries:
            if not q:
                continue
            c = self.retriever.search(q)
            for k in out:
                for row in c.get(k) or []:
                    rid = row.get("id")
                    if rid and rid in seen[k]:
                        continue
                    if rid:
                        seen[k].add(rid)
                    out[k].append(row)
        return {
            "signs": out["signs"][:limit_signs],
            "concepts": out["concepts"][:limit_concepts],
            "claims": out["claims"][:limit_claims],
        }

    def ask(self, query, emit, image=None, context=None, percept=None):
        t0 = time.time()
        has_image = bool(image)
        cfg = self.router.pick(has_image)
        if not cfg or not cfg.ready:
            raise RuntimeError("no model configured")

        # 有图但视觉模型未配置时，pick() 会退回文本模型。此时绝不能再发
        # image_url——OpenAI 兼容的纯文本模型会直接 400，而且模型也没看过图。
        use_image = bool(has_image and cfg is self.router.vision and cfg.ready)

        # 视觉所见（findings）参与检索：用户只问「这张片子有什么异常」时，
        # query 里没有任何征象词，单靠 query 检索必然 0 命中。
        # 每条所见单独检索再合并，避免一句长描述被 bigram 稀释掉关键词。
        findings = []
        sign_terms = []
        if percept:
            findings = [str(x).strip() for x in (percept.get("findings") or []) if str(x).strip()]
            sign_terms = [str(x).strip() for x in (percept.get("sign_terms") or []) if str(x).strip()]
        percept_text = "；".join(findings)
        if sign_terms:
            percept_text = ("征象名：" + "、".join(sign_terms)
                            + ("；" + percept_text if percept_text else ""))
        if findings or sign_terms:
            # 库内规范征象名放最前：它们是精确命中，优先级高于自由描述。
            ctx = self._merge_ctx([query] + sign_terms[:3] + findings[:4])
        else:
            ctx = self.retriever.search(query)
        retrieve_ms = int((time.time() - t0) * 1000)
        hits = len(ctx["signs"]) + len(ctx["claims"])
        route = "vision" if use_image else "text"
        # trace 必须与事实一致：这里真实命中了几个词条、几条结论，就报几个。
        emit("trace", {"stage": "kb_retrieve", "skill": "llm_retriever",
                       "status": "completed", "ms": retrieve_ms,
                       "hits": hits, "hit": hits > 0,
                       "route": route, "model": cfg.model,
                       "detail": {"signs": len(ctx["signs"]),
                                  "concepts": len(ctx["concepts"]),
                                  "claims": len(ctx["claims"])}})

        user_text = "检索结果：\n%s\n\n用户问题：%s" % (self._context_text(ctx), query)
        if percept_text:
            # 视觉所见是模型自动识别的，用于把图上的描述接到检索上；
            # 它不是人工标注，也不能当成库内证据。
            user_text = ("视觉所见（模型自动识别，非人工标注）：\n%s\n\n" % percept_text) + user_text
        if context:
            # 页面上下文只帮助定位（哪一例、哪个分区、哪道题），
            # 不参与检索打分，也不能被模型当作库内证据引用。
            lines = []
            for k, v in list(context.items())[:8]:
                if v in (None, "", [], {}):
                    continue
                lines.append("%s：%s" % (k, str(v)[:300]))
            if lines:
                user_text = ("页面上下文（只用于定位，不是知识库证据）：\n"
                             + "\n".join(lines) + "\n\n" + user_text)
        if has_image and not use_image:
            user_text += ("\n\n（本次未配置视觉模型，未读取影像。"
                          "不要声称看过图，也不要编造病灶位置。）")
        if use_image:
            user_text += ("\n\n（附影像，请结合上面的视觉所见作答；"
                          "不要输出 JSON、bbox 或坐标，定位已单独完成）")
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
        generate_ms = int((time.time() - t0) * 1000) - retrieve_ms

        dropped = [i for i in ID_RE.findall(text) if i not in self.valid_ids]
        cites = self._cites(ctx, text)
        return {
            "text": text,
            "cites": cites,
            "route": route,
            "model": cfg.model,
            "dropped_ids": dropped,
            "ms": int((time.time() - t0) * 1000),
            # 给 main.py 的 build_trace 用：没有工具调用，命中数只能由检索层自己报
            "trace_detail": {
                "hits": hits,
                "signs": len(ctx["signs"]),
                "claims": len(ctx["claims"]),
                "concepts": len(ctx["concepts"]),
                "retrieve_ms": retrieve_ms,
                "generate_ms": max(generate_ms, 0),
                "model": cfg.model,
            },
        }

    def structured(self, prompt, schema_hint, image=None, max_tokens=700):
        """要求模型输出 JSON，解析失败重试一次（第二次去掉 response_format）。

        返回 (obj, raw_text)。两次都失败抛 RuntimeError，由上层显式降级。
        """
        cfg = self.router.vision if (image and self.router.vision.ready) else self.router.text
        if not cfg or not cfg.ready:
            raise RuntimeError("no model configured")

        user_text = prompt + "\n\nJSON 结构：\n" + schema_hint
        if image and cfg is self.router.vision:
            content = [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": _data_url(image)}},
            ]
        else:
            content = user_text

        messages = [
            {"role": "system", "content": JSON_SYSTEM},
            {"role": "user", "content": content},
        ]
        last = None
        for attempt in range(2):
            try:
                raw = self.client.chat(
                    cfg, messages, temperature=0, max_tokens=max_tokens,
                    response_format={"type": "json_object"} if attempt == 0 else None)
                obj = _vision.extract_json(raw)
                if isinstance(obj, dict):
                    return obj, raw
                last = RuntimeError("output is not a json object")
            except Exception as exc:
                last = exc
        raise RuntimeError("structured failed: %s" % str(last)[:200])

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
