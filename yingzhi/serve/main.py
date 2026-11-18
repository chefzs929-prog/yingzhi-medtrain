"""影知动态服务层 · 最小可运行版（v3.0 骨架）。

启动：
    python3 yingzhi/serve/main.py --port 8800

接口：
    POST /api/ask        SSE：trace → delta → citation → done
    GET  /api/trace/<id> 回放某次运行
    GET  /api/health     入口体检
    GET  /api/probe      浏览器测试页

边界：本文件不包含检索打分、判分规则、prompt。只做会话、转发、留痕、降级。
"""

import argparse
import glob
import json
import os
import random
import re
import string
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from discover import DiscoverError, discover  # noqa: E402
from gateway import Gateway, GatewayError  # noqa: E402
import llm as llm_route  # noqa: E402
import vision as vision_mod  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(ROOT)
RUN_DIR = os.path.join(ROOT, "run")
DATA_DIR = os.path.join(WORKSPACE, "kb", "data")
APP_DIR = os.path.join(ROOT, "app")
IMAGE_DIR = os.path.join(WORKSPACE, "kb", "images")

_IMAGE_INDEX = None


def ensure_image_index():
    """kb/images 的 md5 索引：上传原图时用来确认是哪一例。"""
    global _IMAGE_INDEX
    if _IMAGE_INDEX is None:
        _IMAGE_INDEX = vision_mod.ImageIndex(IMAGE_DIR)
        _IMAGE_INDEX.build()
    return _IMAGE_INDEX

# 前端只渲染这五段；guard / session 等内部阶段只写进 trace.json，不推给界面。
TRACE_STAGES = {"kb_retrieve", "skill_invoke", "workflow", "agent_generate", "persist"}

# 合规拦截：只拦「求诊断/求治疗」，不拦「影像表现」的正常提问
BLOCK_PATTERNS = [
    "怎么治", "如何治", "治疗方案", "用什么药", "吃什么药", "剂量",
    "手术", "预后", "存活期", "能活多久", "确诊", "是不是癌", "严重吗",
]
BLOCK_REPLY = (
    "结论：该问题超出本平台范围。\n"
    "依据：平台只做影像征象与公开文献的对照，不做疾病判断。\n"
    "缺失：无法提供诊断或治疗相关意见。\n"
    "边界：仅用于教学与研究，不构成诊断意见，请以临床医师意见为准。"
)

STATE = {
    "gateway": None,
    "info": None,
    "agent_ready": False,
    "persona_injected": False,
    "skill_ready": False,
    "skills": [],
    "fallback_reason": None,
    "args": None,
}


def _port_alive(url, timeout=0.5):
    """opencode server 是否还活着。DeepWorks 每次启动端口都会变。"""
    import socket
    import urllib.parse as _up
    try:
        p = _up.urlparse(url or "")
        with socket.create_connection((p.hostname or "127.0.0.1", p.port or 80), timeout):
            return True
    except OSError:
        return False


def _rebuild_gateway():
    """重新发现 opencode 入口并重建网关。

    典型场景：先启动 serve 再重启 DeepWorks，opencode 换了端口，
    旧 gateway 仍指向死端口，整站静默降级成本地模板。
    """
    args = STATE.get("args")
    if not args:
        return None
    try:
        info = discover(force=True)
    except DiscoverError as exc:
        STATE["fallback_reason"] = str(exc)[:200]
        return None
    gw = Gateway(info, model_provider=args.provider, model_id=args.model,
                 agent=args.agent, directory=WORKSPACE, kb_root=DATA_DIR,
                 mode=args.mode)
    try:
        names = gw.agents()
    except GatewayError:
        names = []
    try:
        skills = gw.skills()
    except GatewayError:
        skills = []
    STATE["info"] = info
    STATE["gateway"] = gw
    STATE["agent_ready"] = args.agent in names
    STATE["skills"] = skills
    STATE["skill_ready"] = "retrieve-sign" in skills
    if not STATE["agent_ready"]:
        gw.agent = "build"
        gw.persona = load_persona()
        STATE["persona_injected"] = bool(gw.persona)
        STATE["fallback_reason"] = (
            "agent '%s' not loaded; persona injected into build" % args.agent
        )
    else:
        STATE["persona_injected"] = False
        STATE["fallback_reason"] = None
    return gw


def ensure_gateway():
    gw = STATE.get("gateway")
    if gw is not None and _port_alive(gw.base):
        return gw
    return _rebuild_gateway()


_LLM = {"obj": None, "checked": False}


def ensure_llm():
    """双模型路由（有图走视觉、无图走文本）。未配置 key 时返回 None，
    调用方回落到原有 gateway / fallback 路径。"""
    if not _LLM["checked"]:
        _LLM["checked"] = True
        try:
            _LLM["obj"] = llm_route.build_from_env()
        except Exception as exc:
            print("[llm] disabled:", exc, file=sys.stderr)
            _LLM["obj"] = None
    return _LLM["obj"]


def load_persona():
    """人设的单一事实来源：.opencode/agents/yingzhi.md 的正文。

    DeepWorks 部署下该文件不会被 opencode 自动加载（server cwd 不在项目内），
    所以由网关随请求注入；若未来 agent 被正确加载，则不再注入，避免重复。
    """
    path = os.path.join(WORKSPACE, ".opencode", "agents", "yingzhi.md")
    if not os.path.exists(path):
        return None
    raw = open(path, encoding="utf-8").read()
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            raw = parts[2]
    return raw.strip() or None


def new_run_id():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tail = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return "%s-%s" % (stamp, tail)


def save_run(run_id, name, payload):
    path = os.path.join(RUN_DIR, run_id)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, name), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


def load_jsonl(name):
    path = os.path.join(DATA_DIR, name)
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


_SIGNS = None
_CONCEPTS = None
_KNOWN_IDS = None

# 回答里允许出现的引用形态。任何命中这个正则的 id 都必须能在知识库里查到，
# 查不到就是编造——这是最容易发生、也最容易糊弄过去的一类幻觉。
#
# 前缀与分段必须照抄 kb/data 里的真实格式（实测样本）：
#   SIGN-001 / CASE-001 / CLM-0582 / SL-001
#   REG-001-RUL            （三段）
#   GL-TIRADS-01           （中缀是缩写，不是数字）
#   GRP-LUNG-GGO           （无数字）
#   STD-TIRADS             （无数字）
#   ATLAS-CHEST-PA-6       （多段 + 末尾数字）
# 写错格式的后果是双向的：漏检（编造不报）或误报（真实引用被标红）。
# 不要用 \b：Python 的 \w 包含中文，中文紧跟 id 时 \b 不成立，会漏检。
CITE_RE = re.compile(
    r"(?:SIGN|CASE|CLM|SL)-\d{2,4}"
    r"|REG-\d{3}(?:-[A-Z]{2,4})?"
    r"|GL-[A-Z]{2,10}-\d{2}"
    r"|GRP-[A-Z]{2,10}(?:-[A-Z]{2,10})*"
    r"|STD-[A-Z]{2,10}"
    r"|ATLAS-[A-Z]{2,10}(?:-[A-Z]{2,10})*-\d+"
)


def known_ids():
    """知识库里真实存在的 id 集合。

    扫 kb/data 下全部 *.jsonl，而不是写死文件名：库里还有
    slices / groups / standards / atlas 等文件，写死会把这些前缀
    全部误判成「编造」。
    """
    global _KNOWN_IDS
    if _KNOWN_IDS is None:
        ids = set()
        for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.jsonl"))):
            for row in load_jsonl(os.path.basename(path)):
                if row.get("id"):
                    ids.add(str(row["id"]))
        _KNOWN_IDS = ids
    return _KNOWN_IDS


def audit_citations(text):
    """返回 (引用到的 id 列表, 库内不存在的 id 列表)。"""
    known = known_ids()
    cited, unverified = [], []
    for match in CITE_RE.finditer(text or ""):
        cid = match.group(0)
        if cid not in cited:
            cited.append(cid)
        if cid not in known and cid not in unverified:
            unverified.append(cid)
    return cited, unverified


def fallback_answer(query):
    """离线兜底：只用本地词条做关键词命中，明确标记 degraded。"""
    global _SIGNS
    if _SIGNS is None:
        _SIGNS = load_jsonl("signs.jsonl")
    q = query.strip().lower()
    hits = []
    for row in _SIGNS:
        name = str(row.get("name", "")).strip().lower()
        aliases = [str(a).strip().lower() for a in (row.get("aliases") or []) if a]
        # 用「词条名是否出现在问题里」判定，比「整句是否出现在词条里」更接近真实提问
        if (name and name in q) or any(a and a in q for a in aliases):
            hits.append(row)
    if not hits:
        return (
            "结论：本地演示态未命中「%s」。\n"
            "依据：离线词条库仅支持关键词直接命中。\n"
            "缺失：Agent 未连接，无法做语义检索与双线判断。\n"
            "边界：仅用于教学与研究，不构成诊断意见。" % query
        ), []
    top = hits[0]
    cites = [{
        "id": top.get("id", ""),
        "type": "sign",
        "title": top.get("name", ""),
        "source_url": top.get("source_url") or "",
        "hash_ok": True,
    }]
    text = (
        "结论：%s（本地演示态）\n"
        "依据：词条 %s，共命中 %d 条。\n"
        "缺失：Agent 未连接，未做指南线对照。\n"
        "边界：仅用于教学与研究，不构成诊断意见。"
        % (top.get("name", query), top.get("id", ""), len(hits))
    )
    return text, cites


def suggest_term(query):
    """术语归一化：在词条词典里找出现在问题中的最长名称。

    只做「把口语问题映射到库内词条名」，不排序、不打分、不生成证据。
    真正的检索与引用仍由 Agent 完成。
    """
    global _SIGNS
    if _SIGNS is None:
        _SIGNS = load_jsonl("signs.jsonl")
    q = query.lower()
    best = None
    for row in _SIGNS:
        names = [row.get("name")] + list(row.get("aliases") or [])
        for name in names:
            if not name:
                continue
            name = str(name)
            if name.lower() in q and (best is None or len(name) > len(best[0])):
                best = (name, row.get("id"))
    return best


def suggest_concept(query):
    """疾病/病理归一化：把「肺水肿」这类疾病名映射到概念条目。

    返回 (命中的别名, 概念行)。概念行里的 sign_ids 是库内 may_see_in 直接支持，
    related_sign_ids 是人工补充的关联，两者在回答里必须区分。
    """
    global _CONCEPTS
    if _CONCEPTS is None:
        _CONCEPTS = load_jsonl("concepts.jsonl")
    q = query.lower()
    best = None
    for row in _CONCEPTS:
        names = [row.get("name"), row.get("en")] + list(row.get("aliases") or [])
        for name in names:
            if not name:
                continue
            name = str(name)
            if name.lower() in q and (best is None or len(name) > len(best[0])):
                best = (name, row)
    return best


# 通识段落标记：模型必须用它把「库外知识」与「库内证据」隔开。
GENERAL_MARK = "【通识补充·非库内证据】"


def general_section_ids(text):
    """通识段落里出现的 id。

    通识段落按规则不允许带 id；带了就是拿库外内容冒充可核验证据，
    即使 id 真实存在也要报出来，不能因为「能查到」就放过。
    """
    text = text or ""
    if GENERAL_MARK not in text:
        return []
    section = text.split(GENERAL_MARK, 1)[1]
    # 到下一个四段式段落头为止
    for stop in ("\n缺失：", "\n边界："):
        if stop in section:
            section = section.split(stop, 1)[0]
    return sorted({m.group(0) for m in CITE_RE.finditer(section)})


def detect_grounding(text, kb_hits):
    """回答的证据强度：grounded 全库内 / mixed 库内+通识 / general 纯通识。

    marker_ok 单独返回：未命中却没用通识标记，说明模型绕过了分层规则。
    """
    text = text or ""
    has_mark = GENERAL_MARK in text
    if has_mark:
        return ("mixed" if kb_hits > 0 else "general"), True
    return ("grounded" if kb_hits > 0 else "general"), kb_hits > 0


STOP_WORDS = ["是什么", "怎么样", "怎么", "如何", "描述", "提示", "什么", "的区别",
              "区别", "在ct上", "在CT上", "的", "吗", "？", "?", "请", "说说", "介绍"]


def extract_keyword(query):
    """从口语问题里剥出最可能的核心词，用于给出精确检索命令。

    只做字符串清洗，不理解语义，也不产生证据。
    """
    s = query
    for word in STOP_WORDS:
        s = s.replace(word, "")
    runs = re.findall(r"[\u4e00-\u9fa5]{2,}", s)
    if not runs:
        return None
    return max(runs, key=len)


def build_trace(run_id, request, result, degraded, reason):
    result = result or {}
    spans = []
    tools = []
    if degraded:
        spans = [
            {"stage": "guard", "skill": "local_rules", "status": "degraded", "ms": 0},
            # 降级分支里这一段的检索是本地关键词匹配，必须如实标 degraded；
            # 标 completed 会让前端把降级链路显示成正常链路。
            {"stage": "kb_retrieve", "skill": "local_keyword", "status": "degraded", "ms": 1},
            {"stage": "skill_invoke", "skill": None, "status": "unavailable", "ms": 0},
            {"stage": "workflow", "skill": None, "status": "unavailable", "ms": 0},
            {"stage": "agent_generate", "skill": "local_template", "status": "degraded", "ms": 0},
        ]
    else:
        tools = result.get("tools") or []
        # 技能调用只认 skill 工具（input.name 为技能 id）；其余工具都是检索/读文件。
        skill_calls = [t for t in tools if t.get("tool") == "skill"]
        kb_tools = {"read", "glob", "grep", "list", "ls", "bash"}
        kb_files = ("kb/data", "signs.jsonl", "guidelines.jsonl", "cases.jsonl",
                    "regions.jsonl", "claims.jsonl")

        def is_kb(t):
            if t.get("tool") == "skill":
                return False
            if t["tool"] in kb_tools:
                return True
            detail = (t.get("detail") or "").lower()
            return any(name in detail for name in kb_files)

        kb_ms = sum(int(((t.get("end") or t["start"]) - t["start"]) * 1000) for t in tools if is_kb(t))
        skill_ms = sum(int(((t.get("end") or t["start"]) - t["start"]) * 1000) for t in skill_calls)
        kb_names = sorted({t["tool"] for t in tools if is_kb(t)})
        skill_names = sorted({(t.get("skill") or t.get("tool")) for t in skill_calls})

        # 「命中」必须同时满足：命令确实指向知识库文件、命令里含本次查询的核心词、
        # 且输出不是错误信息或空输出。只看 status=completed 会把
        # 「grep 打错路径返回 No such file」「skill 工具返回 87 行技能正文」
        # 都算成检索命中。
        ERROR_MARKS = ("no such file", "not found", "no matches", "no match",
                       "cannot access", "is a directory", "(no output)")
        keyword = extract_keyword(request.get("query") or "") or ""

        def hit_lines(t):
            if t.get("tool") == "skill" or not is_kb(t):
                return 0
            head = (t.get("out_head") or "").lower()
            if any(mark in head for mark in ERROR_MARKS):
                return 0
            detail = t.get("detail") or ""
            # 概念检索按概念名命中，命令里不会出现用户原句的核心词，不能套用关键词规则。
            if "concepts.jsonl" in detail:
                return int(t.get("out_lines") or 0)
            # 按 sign_ids 回查词条时，命令里是 id 而不是关键词，同样放行。
            if re.search(r"SIGN-\d{2,4}", detail):
                return int(t.get("out_lines") or 0)
            if not any(name in detail.lower() for name in kb_files) and t["tool"] != "read":
                return 0
            # 宽泛扩展检索（如 grep -E '胸膜|pleural'）命中别的词条，不算本次命中
            if keyword and keyword not in detail:
                return 0
            return int(t.get("out_lines") or 0)

        kb_hits = sum(hit_lines(t) for t in tools)
        commands = [t.get("detail") for t in tools if is_kb(t) and t.get("detail")]
        spans = [
            {"stage": "kb_retrieve", "skill": ",".join(kb_names) or "none",
             "status": "completed" if kb_names else "unavailable", "ms": kb_ms,
             "hits": kb_hits, "hit": kb_hits > 0,
             "command": (commands[0][:160] if commands else None)},
            {"stage": "skill_invoke", "skill": ",".join(skill_names) or "none",
             "status": "completed" if skill_names else "unavailable", "ms": skill_ms},
            {"stage": "workflow", "skill": None, "status": "unavailable", "ms": 0},
            {"stage": "agent_generate", "skill": result.get("model"),
             "status": "completed", "ms": result.get("generate_ms", 0)},
        ]
        # 直连模型没有工具调用，tools 为空，上面那套判定只会得出「全未运行」。
        # 必须用模型层自己报告的检索命中与耗时覆盖，否则 trace 与事实相反。
        td = result.get("trace_detail") or {}
        if td:
            kb_hits = int(td.get("hits") or 0)
            spans = [
                {"stage": "kb_retrieve", "skill": "llm_retriever",
                 "status": "completed", "ms": td.get("retrieve_ms", 0),
                 "hits": kb_hits, "hit": kb_hits > 0,
                 "command": "in-memory: signs / concepts / claims"},
                {"stage": "skill_invoke", "skill": None, "status": "skipped", "ms": 0},
                {"stage": "workflow", "skill": None, "status": "skipped", "ms": 0},
                {"stage": "agent_generate", "skill": td.get("model") or result.get("model"),
                 "status": "completed", "ms": td.get("generate_ms", 0)},
            ]
    cited, unverified = audit_citations((result or {}).get("text"))
    if degraded:
        grounding, marker_ok = "degraded", False
    else:
        grounding, marker_ok = detect_grounding((result or {}).get("text"), kb_hits)
    general_ids = general_section_ids((result or {}).get("text"))
    return {
        "run_id": run_id,
        "request": request,
        "spans": spans,
        "summary": {
            "first_token_ms": (result or {}).get("first_token_ms"),
            "total_ms": (result or {}).get("total_ms", 0),
            "delta_chars": (result or {}).get("delta_chars", 0),
            "model": (result or {}).get("model"),
            "agent": (result or {}).get("agent"),
            "grounding": grounding,
        },
        # 引用自证：回答里每个 id 都回查知识库。unverified 非空说明模型编了 id。
        # general_section_ids 单独列：通识段按规则不许带 id，带了就是冒充证据。
        "citation_audit": {"cited": cited, "unverified": unverified,
                           "general_section_ids": general_ids,
                           "grounding": grounding, "marker_ok": marker_ok,
                           "ok": not unverified and not general_ids},
        # 工具原始证据：答辩时点开 trace.json 能看到真实命令与输出前 160 字
        "tools": [
            {"tool": t.get("tool"), "skill": t.get("skill"),
             "ms": int(((t.get("end") or t["start"]) - t["start"]) * 1000),
             "command": (t.get("detail") or "")[:160],
             "out_lines": t.get("out_lines"),
             "out_head": (t.get("out_head") or "")[:160]}
            for t in tools
        ],
        "degraded": degraded,
        "degraded_reason": reason,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "yingzhi-serve/3.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # ---------- 输出工具 ----------

    def send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def sse_start(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.close_connection = True

    def sse_send(self, kind, payload):
        if getattr(self, "client_gone", False):
            return
        chunk = "event: %s\ndata: %s\n\n" % (kind, json.dumps(payload, ensure_ascii=False))
        try:
            self.wfile.write(chunk.encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # 浏览器提前关闭（重复点击、切页、停止）：不能让写失败中断后续落盘，
            # 否则会留下只有 request.json 的孤儿运行记录。
            self.client_gone = True
            self.close_connection = True

    # ---------- 路由 ----------

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            ensure_gateway()  # DeepWorks 重启后端口会变，健康检查时顺便自愈
            return self.send_json(200, {
                "ok": STATE["gateway"] is not None,
                "entry": "deepworks-opencode-server",
                "url": (STATE["info"] or {}).get("url"),
                "agent_ready": STATE["agent_ready"],
                "persona_injected": STATE["persona_injected"],
                "skill_ready": STATE.get("skill_ready", False),
                "skills": STATE.get("skills") or [],
                "fallback_reason": STATE["fallback_reason"],
                "llm_route": (ensure_llm().router.describe() if ensure_llm() else None),
                "models": ["dth/Auto"],
                # 诚实边界：答辩时可直接读这段，不用靠口头解释。
                # 每一项都对应代码里能指认的实现，或明确为 false。
                "honesty": {
                    "real_llm": bool(STATE["agent_ready"] or STATE["persona_injected"]),
                    "real_skill": bool(STATE.get("skill_ready")),
                    "real_workflow": False,
                    "semantic_search": False,
                    "multiturn_memory": False,
                    "citation_audit": True,
                    "trace_evidence": True,
                    "notes": [
                        "semantic_search=false：当前是词典归一化 + 关键词 grep，不是向量检索",
                        "multiturn_memory=false：每次提问新建会话，避免上下文污染",
                        "real_workflow=false：工作流未创建，trace 里标 unavailable",
                        "citation_audit=true：回答中的 id 会回查知识库，编造会被标出",
                    ],
                },
            })

        if path.startswith("/api/trace/"):
            run_id = path.rsplit("/", 1)[-1]
            target = os.path.join(RUN_DIR, run_id, "trace.json")
            if not os.path.exists(target):
                return self.send_json(404, {"error": "run not found", "run_id": run_id})
            with open(target, encoding="utf-8") as fh:
                return self.send_json(200, json.load(fh))

        if path in ("/", "/probe"):
            page = os.path.join(APP_DIR, "probe.html")
            if os.path.exists(page):
                with open(page, "rb") as fh:
                    body = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            return self.send_json(200, {"ok": True, "hint": "POST /api/ask"})

        return self.send_json(404, {"error": "not found", "path": path})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/ask":
            return self.send_json(404, {"error": "not found"})

        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:
            return self.send_json(400, {"error": "bad json: %s" % exc})

        query = (body.get("query") or "").strip()
        if not query:
            return self.send_json(400, {"error": "query required"})

        role = body.get("role") or "student"
        device = body.get("device") or "desktop"
        chain = body.get("chain") or "kb_qa"
        run_id = new_run_id()
        request = {
            "run_id": run_id, "query": query, "role": role,
            "device": device, "chain": chain,
            "filters": body.get("filters") or {},
            "context": body.get("context") or {},
            "kb_version": body.get("client_kb_version") or "local",
        }
        save_run(run_id, "request.json", request)

        # 合规拦截：先于任何模型调用
        if any(p in query for p in BLOCK_PATTERNS):
            trace = build_trace(run_id, request, None, False, None)
            trace["spans"] = [
                {"stage": "guard", "skill": "compliance", "status": "blocked", "ms": 0},
                {"stage": "kb_retrieve", "skill": None, "status": "skipped", "ms": 0},
                {"stage": "skill_invoke", "skill": None, "status": "skipped", "ms": 0},
                {"stage": "workflow", "skill": None, "status": "skipped", "ms": 0},
                {"stage": "agent_generate", "skill": None, "status": "skipped", "ms": 0},
                # trace.json 仍会落盘，所以 persist 是真实完成的，不能留空
                {"stage": "persist", "skill": "json", "status": "completed", "ms": 1},
            ]
            save_run(run_id, "trace.json", trace)
            self.sse_start()
            for span in trace["spans"]:
                if span.get("stage") in TRACE_STAGES:
                    self.sse_send("trace", span)
            self.sse_send("delta", {"text": BLOCK_REPLY})
            self.sse_send("done", {"run_id": run_id, "degraded": False,
                                   "blocked": True, "reason": "out_of_scope"})
            return

        llm_ans = ensure_llm()
        gateway = None if llm_ans is not None else ensure_gateway()
        degraded = llm_ans is None and gateway is None
        reason = STATE["fallback_reason"] if degraded else None
        result = None
        image_match = None

        self.sse_start()

        try:
            if llm_ans is not None:
                # 双模型路由：body.image 为 data URL 时走视觉模型，否则走文本模型
                image = body.get("image")
                result = llm_ans.ask(query, self.sse_send, image=image)
                text = result.get("text") or ""
                if image:
                    # 模型给的框要从正文里剥掉再发 delta，不能让用户看到 JSON
                    bbox, raw, cleaned = vision_mod.extract_bbox(text)
                    if bbox:
                        text = cleaned
                        result["text"] = text
                    found = ensure_image_index().match_all(image)
                    image_match = {
                        "case_id": found[0] if found else None,
                        "case_ids": found,
                        "bbox": bbox,
                        "raw_bbox": raw,
                    }
                cites = result.get("cites") or []
                # 直连模型是一次性返回，没有「首字」时间，留空而不是填 0 假装有
                result["total_ms"] = result.get("ms")
                result["delta_chars"] = len(text)
                result["first_token_ms"] = None
                self.sse_send("delta", {"text": text})
            elif gateway is not None:
                # 每次提问新建会话：复用同一 session 会让上下文无限累积，
                # 实测同一 session 连续提问会从 7s 涨到 90s 超时。
                session_id = gateway.ensure_session(role, device, force=True)
                # 会话建立不属于链路五段，不再发 trace（前端只认五段，多发会变脏事件）
                # 技能必须真实调用，否则 trace 里的 skill_invoke 只能标 unavailable。
                # 实测：不显式要求时 agent 会直接 bash grep，跳过 skill 工具。
                hint = "1) 先调用 skill 工具，参数 name 为 retrieve-sign（加载检索规范）"
                concept = suggest_concept(query)
                term = suggest_term(query)
                if concept:
                    # 疾病名不是征象名：先查概念拿到 sign_ids，再回查词条。
                    # 少了这一步，「肺水肿的征象」会直接判未命中。
                    row = concept[1]
                    sign_ids = list(row.get("sign_ids") or [])
                    related = list(row.get("related_sign_ids") or [])
                    hint += ('\n2) 概念检索：grep -m 3 \'"name": "%s"\' %s/concepts.jsonl'
                             % (row.get("name"), DATA_DIR))
                    if sign_ids:
                        hint += ('\n3) 回查征象（库内直接证据）：grep -m 8 -E \'%s\' %s/signs.jsonl'
                                 % ("|".join(sign_ids), DATA_DIR))
                    if related:
                        hint += ('\n4) 关联征象（人工补充，回答须标「关联」）：grep -m 8 -E \'%s\' %s/signs.jsonl'
                                 % ("|".join(related), DATA_DIR))
                    hint += ("\n概念命中的 sign_ids 必须逐条列出并带 id；"
                             "related_sign_ids 标「关联」；库内未覆盖的维度再走通识补充段。")
                else:
                    keyword = term[0] if term else extract_keyword(query)
                    if keyword:
                        hint += '\n2) 再执行：grep -m 5 "%s" %s/signs.jsonl' % (keyword, DATA_DIR)
                    hint += ("\n3) 若词条未命中，再查概念：grep -m 3 '\"name\": \"%s\"' %s/concepts.jsonl"
                             % (keyword or "", DATA_DIR))
                    hint += ("\n四步都未命中才进入通识分支：通识段以 %s 单独成段，段内禁止出现任何 id。"
                             % GENERAL_MARK)
                result = gateway.ask(session_id, query, self.sse_send, hint=hint)
                text = result.get("text") or ""
                cites = []
            else:
                text, cites = fallback_answer(query)
                self.sse_send("trace", {"stage": "kb_retrieve", "skill": "local_keyword",
                                        "status": "degraded", "ms": 1})
                self.sse_send("delta", {"text": text})
        except (GatewayError, Exception) as exc:
            degraded = True
            reason = str(exc)[:200]
            text, cites = fallback_answer(query)
            self.sse_send("trace", {"stage": "agent_generate", "skill": "fallback",
                                    "status": "error", "ms": 0})
            self.sse_send("reset", {"reason": "agent_failed"})
            self.sse_send("delta", {"text": text})

        for cite in cites:
            self.sse_send("citation", cite)

        t_persist = time.time()
        persist_ms = 0
        trace = build_trace(run_id, request, result, degraded, reason)
        save_run(run_id, "trace.json", trace)
        save_run(run_id, "answer.json", {"run_id": run_id, "text": text,
                                         "citations": cites, "degraded": degraded})
        persist_ms = int((time.time() - t_persist) * 1000)
        trace["spans"].append({"stage": "persist", "skill": "json", "status": "completed",
                               "ms": persist_ms})
        save_run(run_id, "trace.json", trace)

        # 运行期只能发增量事件，收尾才有全貌：把完整 span 统一补发一遍。
        # 前端按 stage 覆盖，运行期的粗粒度 span 会被这里的精确值替换。
        for span in trace["spans"]:
            if span.get("stage") in TRACE_STAGES:
                self.sse_send("trace", span)

        self.sse_send("done", {
            "run_id": run_id,
            "degraded": degraded,
            "reason": reason,
            "first_token_ms": trace["summary"]["first_token_ms"],
            "total_ms": trace["summary"]["total_ms"],
            "trace_url": "/api/trace/%s" % run_id,
            # 引用自证结果直接带给前端：非空就必须显示警示，不允许静默通过
            "cited": trace["citation_audit"]["cited"],
            "unverified_citations": trace["citation_audit"]["unverified"],
            # 证据强度与通识段越界 id：前端据此显示三色标签
            "grounding": trace["citation_audit"]["grounding"],
            "marker_ok": trace["citation_audit"]["marker_ok"],
            "general_section_ids": trace["citation_audit"]["general_section_ids"],
            # 上传影像时才有：命中的库内病例 + 模型给的框（已转成 [x,y,w,h]）
            "image_match": image_match,
        })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--model", default="Auto")
    ap.add_argument("--provider", default="dth")
    ap.add_argument("--agent", default="yingzhi")
    ap.add_argument("--offline", action="store_true", help="强制本地降级，用于断网演练")
    ap.add_argument("--mode", default="clean", choices=("clean", "raw"),
                    help="clean=生成完再分片推送（正文干净）；raw=直接转发增量")
    args = ap.parse_args()
    STATE["args"] = args

    os.makedirs(RUN_DIR, exist_ok=True)

    if args.offline:
        STATE["fallback_reason"] = "offline_mode"
    else:
        try:
            info = discover()
            STATE["info"] = info
            gw = Gateway(info, model_provider=args.provider, model_id=args.model,
                         agent=args.agent, directory=WORKSPACE, kb_root=DATA_DIR,
                         mode=args.mode)
            # 冷启动竞态：opencode 首次按 directory 建实例时，项目级 agent/skill
            # 可能还没加载完，第一次 /agent 只返回内置项（实测 agent_ready=false，
            # 重启服务后又变 true）。这里重试几次，避免把「还没加载完」误判成
            # 「自定义 agent 不存在」。
            names = []
            for attempt in range(4):
                try:
                    names = gw.agents()
                except GatewayError:
                    names = []
                if args.agent in names:
                    break
                time.sleep(0.7)
            STATE["agent_ready"] = args.agent in names
            skills = gw.skills()
            STATE["skills"] = skills
            STATE["skill_ready"] = "retrieve-sign" in skills
            if not STATE["agent_ready"]:
                # 自定义 agent 未加载：退回 build，并把同一份人设注入请求
                gw.agent = "build"
                gw.persona = load_persona()
                STATE["persona_injected"] = bool(gw.persona)
                STATE["fallback_reason"] = (
                    "agent '%s' not loaded; persona injected into build" % args.agent
                )
            STATE["gateway"] = gw
            print("入口：%s  agent=%s  可用 agent=%s  技能数=%d  retrieve-sign=%s"
                  % (info["url"], gw.agent, names, len(skills), STATE["skill_ready"]))
        except (DiscoverError, GatewayError) as exc:
            STATE["fallback_reason"] = str(exc)[:200]
            print("入口不可用，进入本地演示态：%s" % exc)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    print("影知动态层已启动：http://127.0.0.1:%d/" % args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
