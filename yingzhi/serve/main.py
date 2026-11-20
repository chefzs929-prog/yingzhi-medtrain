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
import atlas as atlas_mod  # noqa: E402
import litsearch  # noqa: E402
import segment as segment_mod  # noqa: E402
VISION_PROMPT = """你在做影像教学标注，不是诊断。只回答三件事：
1. 这张图属于什么检查类型、什么部位、什么投照位/层面；
2. 病灶或可疑区域的归一化外接框；
3. 可见的影像学表现，用中性描述，不写诊断结论。

没有把握的字段填 null；不要编造病灶。"""

VISION_SCHEMA = """{
  "modality": "CR|CT|MR|US|MG|null",
  "body_part": "胸部|头颈|腹部|骨关节|乳腺|甲状腺|null",
  "view": "PA|AP|LAT|CT-AXIAL|MR|US|MLO|null",
  "bbox": [x, y, w, h],
  "findings": ["中性描述，最多 4 条"],
  "confidence": 0.0
}"""

REPORT_PROMPT = """你在做影像教学报告，不是诊断报告。按影像学描述规范写：
- findings 只写可见表现：位置、密度/信号、形态、边缘、分布、伴随征象；
- impression 写成「影像学印象（非诊断）」，只列鉴别方向，不写确诊、不写治疗；
- 证据不足时明确写「不足以判断」，不要补全。"""

REPORT_SCHEMA = """{
  "findings": ["..."],
  "impression": ["影像学印象（非诊断）：..."],
  "bbox": [x, y, w, h],
  "limitations": ["..."]
}"""


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(ROOT)
RUN_DIR = os.path.join(ROOT, "run")
DATA_DIR = os.path.join(WORKSPACE, "kb", "data")
APP_DIR = os.path.join(ROOT, "app")
IMAGE_DIR = os.path.join(WORKSPACE, "kb", "images")

_IMAGE_INDEX = None
_CASES = None


def ensure_image_index():
    """kb/images 的 md5 索引：上传原图时用来确认是哪一例。"""
    global _IMAGE_INDEX
    if _IMAGE_INDEX is None:
        _IMAGE_INDEX = vision_mod.ImageIndex(IMAGE_DIR)
        _IMAGE_INDEX.build()
    return _IMAGE_INDEX


def ensure_cases():
    global _CASES
    if _CASES is None:
        out = []
        path = os.path.join(DATA_DIR, "cases.jsonl")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        c = json.loads(line)
                    except ValueError:
                        continue
                    if str(c.get("status", "active")) == "inactive":
                        continue
                    out.append(c)
        _CASES = out
    return _CASES


def suggest_cases(per_chapter=3, limit=12):
    """库外影像的下一步。

    刻意不猜这张图属于哪个部位：没有视觉分类依据时，猜错比不猜更糟。
    只按章节给几张库内可练的片子，让用户自己挑。
    """
    by_ch = {}
    for c in ensure_cases():
        by_ch.setdefault(c.get("chapter") or "未分类", []).append(c)
    out = []
    seen = set()
    for ch, arr in sorted(by_ch.items(), key=lambda x: -len(x[1])):
        n = 0
        for c in arr:
            img = c.get("image") or ""
            base = os.path.basename(img)
            if not base or base in seen:
                continue
            seen.add(base)
            out.append({
                "id": c.get("id"),
                "title": c.get("title") or "",
                "image": "/images/" + base,
                "chapter": ch,
                "body_part": c.get("body_part") or "",
            })
            n += 1
            if n >= per_chapter:
                break
    return out[:limit]

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
    # --offline 是断网演练开关：不能被 /api/health 的“自愈”悄悄覆盖。
    # 之前 health 会重建 gateway，导致 offline 启动后仍然真实调用 agent。
    if STATE.get("offline"):
        return None
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


_CITE_INDEX = None
_SIGN_INDEX = None

# 引用语义校验用：问题里的部位词。只做「部位是否对得上」，
# 不做真正的语义相似度——那需要 embedding，当前没有。
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


def ensure_sign_index():
    global _SIGN_INDEX
    if _SIGN_INDEX is None:
        _SIGN_INDEX = {str(r.get("id")): r for r in load_jsonl("signs.jsonl") if r.get("id")}
    return _SIGN_INDEX


def _char_overlap(a, b):
    """字符二元组 Dice：只用来判断「名称是否有实质重叠」。"""
    def grams(t):
        t = "".join(ch for ch in (t or "") if ch.isalnum())
        return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else ({t} if t else set())
    A, B = grams(a), grams(b)
    if not A or not B:
        return 0.0
    return 2.0 * len(A & B) / (len(A) + len(B))


def cite_relevance(cite, query):
    """判断引用与问题的关系：direct / related / off。

    direct  名称/别名直接出现在问题里；
    related 名称不在问题里，但部位一致，属于合理扩展证据；
    off     部位也对不上，前端必须标「弱相关」。

    这只是最低成本校验，不等于语义正确：肾积水和肾囊肿都是「肾脏」，
    会被判 related。真正的语义校验需要 embedding，见 README 未来方向。
    """
    if not cite or cite.get("type") != "sign":
        return "n/a"
    row = ensure_sign_index().get(str(cite.get("id"))) or {}
    q = (query or "").lower()
    name = str(row.get("name") or "").lower()
    if name and name in q:
        return "direct"
    for a in row.get("aliases") or []:
        a = str(a).lower()
        if a and a in q:
            return "direct"
    en = str(row.get("en") or "").lower()
    if en and en in q:
        return "direct"
    bp = str(row.get("body_part") or "")
    if bp == "全身":
        return "related"
    if bp in _PART_HINTS and any(w in q for w in _PART_HINTS[bp]):
        return "related"
    return "off"


def ensure_cite_index():
    """id → 可展示的引用卡片。只用于把 agent 正文里的 id 变成 citation 事件，
    不做任何语义判断；title 直接来自知识库字段。"""
    global _CITE_INDEX
    if _CITE_INDEX is not None:
        return _CITE_INDEX
    idx = {}
    specs = [
        ("signs.jsonl", "sign", lambda r: r.get("name") or ""),
        ("claims.jsonl", "claim", lambda r: (r.get("text") or r.get("claim") or "")[:48]),
        ("guidelines.jsonl", "guideline", lambda r: r.get("standard_name") or r.get("statement") or ""),
        ("regions.jsonl", "region", lambda r: r.get("name") or ""),
        ("cases.jsonl", "case", lambda r: r.get("title") or ""),
    ]
    for name, kind, title_of in specs:
        for row in load_jsonl(name):
            rid = row.get("id")
            if rid and rid not in idx:
                idx[str(rid)] = {
                    "id": str(rid), "type": kind, "title": title_of(row),
                    "source_url": row.get("source_url") or "",
                    "hash_ok": bool(row.get("excerpt_sha256") or row.get("source_url")),
                }
    _CITE_INDEX = idx
    return idx


def cites_from_text(text, query=""):
    """把回答里真实存在的 id 变成 citation 事件。编造 id 不在这里发，
    由 citation_audit 单独标红，避免把不存在的 id 做成可点击卡片。"""
    cited, _ = audit_citations(text)
    idx = ensure_cite_index()
    out = []
    for i in cited:
        if i not in idx:
            continue
        card = dict(idx[i])
        card["relevance"] = cite_relevance(card, query)
        out.append(card)

    # 同部位扩展：问题里没写「肺」，但 direct 引用是胸部征象时，
    # 同部位的伴随征象（反晕征、铺路石征）应算 related，不是 off。
    signs = ensure_sign_index()
    anchors = set()
    for c in out:
        if c["relevance"] != "direct":
            continue
        bp = str((signs.get(str(c.get("id"))) or {}).get("body_part") or "")
        if bp and bp != "全身":
            anchors.add(bp)
    for c in out:
        if c["relevance"] != "off":
            continue
        bp = str((signs.get(str(c.get("id"))) or {}).get("body_part") or "")
        if bp in anchors:
            c["relevance"] = "related"
    return out[:8]


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


def make_followups(cites, grounding, image_match):
    """给前端三个可点的追问。

    这是规则生成的“下一步入口”，不是模型输出；done 里会标 source=rules，
    避免把模板问题伪装成 agent 的主动追问。
    """
    out = []
    if image_match and image_match.get("case_id"):
        out.append("这个分区的解剖边界怎么划？")
        out.append("库内还有哪些相似病例？")
    if cites:
        out.append("把 %s 这条依据展开说说" % cites[0].get("id"))
    if grounding in ("general", "degraded"):
        out.append("库内有没有能直接支撑这个说法的词条？")
    else:
        out.append("这个征象还需要和什么鉴别？")
    seen = []
    for item in out:
        if item not in seen:
            seen.append(item)
    return seen[:3]


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
                "models": ["%s/%s" % (STATE["args"].provider, STATE["args"].model)]
                if STATE.get("args") else ["dth/Auto"],
                # 诚实边界：答辩时可直接读这段，不用靠口头解释。
                # 每一项都对应代码里能指认的实现，或明确为 false。
                "honesty": {
                    "real_llm": bool(STATE["agent_ready"] or STATE["persona_injected"]),
                    "real_skill": bool(STATE.get("skill_ready")),
                    "real_workflow": False,
                    "semantic_search": False,
                    "multiturn_memory": False,
                    "bounded_multiturn": True,
                    "agent_interface": True,
                    "citation_audit": True,
                    "trace_evidence": True,
                    "notes": [
                        "semantic_search=false：当前是词典归一化 + 关键词 grep，不是向量检索",
                        "multiturn_memory=false：没有跨会话长期记忆；仅在 10 分钟 TTL 内按 conversation_id 复用 session",
                        "bounded_multiturn=true：有界多轮，超时或换 conversation_id 即重开，避免上下文无限累积",
                        "agent_interface=true：POST /api/ask 支持 mode=auto|agent|llm，GET /api/agent/capabilities 可探测",
                        "real_workflow=false：工作流未创建，trace 里标 unavailable",
                        "citation_audit=true：回答中的 id 会回查知识库，编造会被标出",
                    ],
                },
            })

        if path == "/api/agent/capabilities":
            # 给前端/外部接入方的“能力探测”端点：先看这里，再决定用 agent 还是降级。
            gw = ensure_gateway()
            ans = ensure_llm()
            return self.send_json(200, {
                "version": "1.0",
                "ok": gw is not None or ans is not None,
                "transport": {
                    "ask": "POST /api/ask (SSE)",
                    "trace": "GET /api/trace/{run_id}",
                    "health": "GET /api/health",
                    "literature": "POST /api/lit/search",
                    "region_template": "POST /api/vision/region",
                    "vision_report": "POST /api/vision/report",
                    "vision_segment": "POST /api/vision/segment",
                },
                "events": ["trace", "tool", "delta", "citation",
                           "followup", "reset", "done"],
                "modes": ["auto", "agent", "llm"],
                "citation_kinds": ["local", "literature"],
                "research": {
                    "enabled": True,
                    "source": "PubMed E-utilities",
                    "trigger": "body.research=true 或 surface=literature",
                    "needs_english_term": True,
                },
                "region_template": {
                    "enabled": bool(atlas_mod.load().atlases),
                    "atlases": len(atlas_mod.load().atlases),
                    "source": "atlas_template",
                    "note": "陌生影像用通用模板推断，不是人工标注",
                },
                "agent": {
                    "name": (STATE.get("args").agent if STATE.get("args") else None),
                    "ready": bool(STATE.get("agent_ready")),
                    "persona_injected": bool(STATE.get("persona_injected")),
                    "skills": STATE.get("skills") or [],
                    "skill_ready": bool(STATE.get("skill_ready")),
                },
                "llm": (ans.router.describe() if ans else None),
                "limits": {
                    "image_max_mb": 8,
                    "context_keys": 8,
                    "context_value_chars": 300,
                    "conversation_ttl_s": 600,
                },
                "surfaces": ["clinic", "teach", "paper", "compare"],
                "notes": [
                    "auto 先走 agent，失败且未产出内容时才降级 llm",
                    "done.served_by 会如实标注 agent / llm / fallback",
                    "followups 是规则生成的下一步入口，不是模型输出",
                ],
            })

        if path == "/api/vision/atlases":
            T = atlas_mod.load()
            return self.send_json(200, {
                "ok": True,
                "source": "atlas_template",
                "note": "陌生影像用通用模板推断，不是人工标注",
                "atlases": T.list_atlases(),
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


    def api_lit_search(self, body):
        """网络文献检索。只返回检索结果，不生成结论。"""
        if STATE["offline"]:
            return self.send_json(200, {
                "ok": False, "reason": "offline_mode", "items": [],
                "query": body.get("query"), "source": "PubMed",
            })
        sign_ids = [s for s in (body.get("sign_ids") or []) if s]
        extra = [t for t in (body.get("terms") or []) if t]
        modality = body.get("modality")
        parts = body.get("body_parts") or []
        try:
            limit = max(1, min(int(body.get("limit") or 5), 10))
        except Exception:
            limit = 5

        raw_q = (body.get("query") or "").strip()
        if raw_q and not sign_ids:
            # 只有全 ASCII 的查询才直接送 PubMed；中文查询明确拒绝，不返回假结果。
            if all(ord(ch) < 128 for ch in raw_q):
                res = litsearch.search(raw_q, limit)
            else:
                res = {"ok": False, "reason": "no_english_term", "items": [],
                       "query": raw_q, "source": "PubMed"}
        else:
            res = litsearch.search_signs(sign_ids, extra, modality, parts, limit)
        return self.send_json(200, res)

    def api_vision_region(self, body):
        """陌生影像的分区定位。

        顺序：视觉模型出 {bbox, modality, body_part, view} → 匹配 atlas 模板
        → 模板几何定位。任何一步失败都显式降级，不猜。
        """
        T = atlas_mod.load()
        atlas_id = (body.get("atlas_id") or "").strip()
        bbox = body.get("bbox")
        image = body.get("image")
        vision = None
        vision_error = None

        ans = ensure_llm()
        vision_ready = bool(ans and ans.router.vision.ready)

        # 只有需要自动出框/自动分类时才调视觉，用户已给 atlas+bbox 就不浪费一次请求。
        if image and vision_ready and (not bbox or not atlas_id):
            try:
                vision, _raw = ans.structured(VISION_PROMPT, VISION_SCHEMA,
                                              image=image, max_tokens=600)
                if not bbox and vision.get("bbox"):
                    bbox = vision_mod.extract_bbox(
                        json.dumps({"bbox": vision["bbox"]}))[0]
            except Exception as exc:
                vision_error = str(exc)[:160]

        atlas = T.atlases.get(atlas_id) if atlas_id else None
        matched = None
        if atlas is None:
            src = vision or {}
            matched = T.match(
                src.get("modality") or body.get("modality"),
                src.get("body_part") or body.get("body_part"),
                src.get("view") or body.get("view"),
            )
            if matched:
                atlas = matched["atlas"]

        if atlas is None:
            return self.send_json(200, {
                "ok": False,
                "reason": "no_atlas_match",
                "message": "没有匹配到分区模板：请指定 atlas_id，或提供检查类型/部位/投照位",
                "vision": vision,
                "vision_error": vision_error,
                "atlases": T.list_atlases(),
            })

        atlas_card = {
            "id": atlas.get("id"),
            "name": atlas.get("name"),
            "modality": atlas.get("modality") or [],
            "body_part": atlas.get("body_part") or "",
            "view": atlas.get("view") or "",
            "n_cases": atlas.get("n_cases") or 0,
            "n_regions": atlas.get("n_regions") or 0,
            "match_score": (matched or {}).get("score"),
        }

        if not bbox:
            return self.send_json(200, {
                "ok": False,
                "reason": "needs_bbox",
                "atlas": atlas_card,
                "vision": vision,
                "vision_ready": vision_ready,
                "vision_error": vision_error,
                "message": ("未配置视觉模型或模型未给出可用框：请框选病灶后重试"
                            if not vision_error else "视觉定位失败，请手动框选"),
            })

        try:
            located = T.locate(atlas["id"], bbox)
        except Exception as exc:
            return self.send_json(400, {"ok": False, "reason": "bad_bbox",
                                        "message": str(exc)[:160]})

        return self.send_json(200, {
            "ok": True,
            "source": "atlas_template",
            "atlas": atlas_card,
            "locate": located,
            "vision": vision,
            "vision_error": vision_error,
            "honesty": {
                "template_inference": True,
                "human_annotated": False,
                "note": "陌生影像没有人工标注，这里是模板推断；结论需人工复核",
            },
        })

    def api_vision_segment(self, body):
        """bbox → mask。未装模型时明确 unavailable，不返回假轮廓。"""
        st = segment_mod.status()
        if not st["available"]:
            return self.send_json(200, {
                "ok": False, "reason": "segment_unavailable",
                "segment": st,
                "message": "未安装分割模型；当前只提供 bbox，不提供 mask",
            })
        try:
            mask = segment_mod.segment(body.get("image"), body.get("bbox"))
        except Exception as exc:
            return self.send_json(200, {"ok": False, "reason": "segment_failed",
                                        "message": str(exc)[:200], "segment": st})
        return self.send_json(200, {"ok": True, "mask": mask, "segment": st})

    def api_vision_report(self, body):
        """结构化影像教学报告。只做描述与鉴别方向，不下诊断。"""
        image = body.get("image")
        if not image:
            return self.send_json(400, {"error": "image required"})

        ans = ensure_llm()
        if not ans or not ans.router.vision.ready:
            return self.send_json(200, {
                "ok": False, "reason": "vision_unavailable",
                "message": "未配置视觉模型：无法生成影像报告",
            })

        try:
            report, _raw = ans.structured(REPORT_PROMPT, REPORT_SCHEMA,
                                          image=image, max_tokens=900)
        except Exception as exc:
            return self.send_json(200, {
                "ok": False, "reason": "vision_failed",
                "message": str(exc)[:200],
            })

        # 报告里的描述回查库内征象，能匹配就带上 id；匹配不到不硬塞。
        text = " ".join([str(x) for x in (report.get("findings") or [])])
        citations = []
        try:
            ctx = ans.retriever.search(text, limit=6)
            for s in ctx.get("signs") or []:
                if s.get("id"):
                    citations.append({"id": s["id"], "kind": "local",
                                      "type": "sign", "title": s.get("name") or ""})
        except Exception:
            pass

        region = None
        bbox = body.get("bbox") or report.get("bbox")
        atlas_id = (body.get("atlas_id") or "").strip()
        if bbox:
            T = atlas_mod.load()
            atlas = T.atlases.get(atlas_id) if atlas_id else None
            if atlas is None:
                m = T.match(body.get("modality"), body.get("body_part"), body.get("view"))
                atlas = (m or {}).get("atlas")
            if atlas:
                try:
                    region = {"atlas_id": atlas.get("id"),
                              "locate": T.locate(atlas["id"], bbox)}
                except Exception:
                    region = None

        return self.send_json(200, {
            "ok": True,
            "source": "vision_structured",
            "report": {
                "findings": report.get("findings") or [],
                "impression": report.get("impression") or [],
                "limitations": report.get("limitations") or [],
            },
            "region": region,
            "citations": citations,
            "disclaimer": "影像教学描述，不构成诊断意见；结论需人工复核。",
        })

    def api_lit_search(self, body):
        """网络文献检索。只返回检索结果，不生成结论。"""
        if STATE["offline"]:
            return self.send_json(200, {
                "ok": False, "reason": "offline_mode", "items": [],
                "query": body.get("query"), "source": "PubMed",
            })
        sign_ids = [s for s in (body.get("sign_ids") or []) if s]
        extra = [t for t in (body.get("terms") or []) if t]
        modality = body.get("modality")
        parts = body.get("body_parts") or []
        try:
            limit = max(1, min(int(body.get("limit") or 5), 10))
        except Exception:
            limit = 5

        raw_q = (body.get("query") or "").strip()
        if raw_q and not sign_ids:
            # 只有全 ASCII 的查询才直接送 PubMed；中文查询明确拒绝，不返回假结果。
            if all(ord(ch) < 128 for ch in raw_q):
                res = litsearch.search(raw_q, limit)
            else:
                res = {"ok": False, "reason": "no_english_term", "items": [],
                       "query": raw_q, "source": "PubMed"}
        else:
            res = litsearch.search_signs(sign_ids, extra, modality, parts, limit)
        return self.send_json(200, res)

    def api_vision_region(self, body):
        """陌生影像的分区定位。

        有 bbox：直接用通用 atlas 模板做确定性定位。
        无 bbox：视觉模型可用就自动出框，否则明确要求框选，不猜。
        """
        T = atlas_mod.load()
        atlas_id = (body.get("atlas_id") or "").strip()
        atlas = T.atlases.get(atlas_id) if atlas_id else None
        matched = None
        if atlas is None:
            matched = T.match(body.get("modality"), body.get("body_part"), body.get("view"))
            if matched:
                atlas = matched["atlas"]

        if atlas is None:
            return self.send_json(200, {
                "ok": False,
                "reason": "no_atlas_match",
                "message": "没有匹配到分区模板：请指定 atlas_id，或提供检查类型/部位/投照位",
                "atlases": T.list_atlases(),
            })

        atlas_card = {
            "id": atlas.get("id"),
            "name": atlas.get("name"),
            "modality": atlas.get("modality") or [],
            "body_part": atlas.get("body_part") or "",
            "view": atlas.get("view") or "",
            "n_cases": atlas.get("n_cases") or 0,
            "n_regions": atlas.get("n_regions") or 0,
            "match_score": (matched or {}).get("score"),
        }

        bbox = body.get("bbox")
        vision_note = None
        if not bbox:
            ans = ensure_llm()
            vision_ready = bool(ans and ans.router.vision.ready)
            if not vision_ready or not body.get("image"):
                return self.send_json(200, {
                    "ok": False,
                    "reason": "needs_bbox",
                    "atlas": atlas_card,
                    "vision_ready": vision_ready,
                    "message": "未配置视觉模型或未提供影像：请框选病灶后重试",
                })
            try:
                prompt = (
                    "只做一件事：给出病灶在图像中的归一化外接框。"
                    "不要解释，不要下诊断。只输出 JSON："
                    '{"bbox":[x,y,w,h]}，x/y/w/h 都是 0-1 之间的小数。'
                )
                _, text, _ = ans.ask(prompt, lambda *a, **k: None, image=body.get("image"))
                found_bbox, _raw, _cleaned = vision_mod.extract_bbox(text)
                if not found_bbox:
                    return self.send_json(200, {
                        "ok": False, "reason": "vision_no_bbox",
                        "atlas": atlas_card,
                        "message": "视觉模型没有给出可用的框，请手动框选",
                    })
                bbox = found_bbox
                vision_note = "bbox 由视觉模型给出，分区由模板推断"
            except Exception as exc:
                return self.send_json(200, {
                    "ok": False, "reason": "vision_failed",
                    "atlas": atlas_card,
                    "message": "视觉定位失败：%s" % str(exc)[:160],
                })

        try:
            located = T.locate(atlas["id"], bbox)
        except Exception as exc:
            return self.send_json(400, {"ok": False, "reason": "bad_bbox",
                                        "message": str(exc)[:160]})

        return self.send_json(200, {
            "ok": True,
            "source": "atlas_template",
            "atlas": atlas_card,
            "locate": located,
            "vision_note": vision_note,
            "honesty": {
                "template_inference": True,
                "human_annotated": False,
                "note": "陌生影像没有人工标注，这里是模板推断；结论需人工复核",
            },
        })

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:
            return self.send_json(400, {"error": "bad json: %s" % exc})

        if path == "/api/lit/search":
            return self.api_lit_search(body)
        if path == "/api/vision/region":
            return self.api_vision_region(body)
        if path == "/api/vision/report":
            return self.api_vision_report(body)
        if path == "/api/vision/segment":
            return self.api_vision_segment(body)
        if path != "/api/ask":
            return self.send_json(404, {"error": "not found", "path": path})

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
            "surface": body.get("surface") or chain,
            "conversation_id": (body.get("conversation_id") or "").strip()[:80] or None,
            "mode": (body.get("mode") or os.environ.get("YZ_ASK_MODE") or "auto").lower(),
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

        # 路由：auto = agent 优先、失败降级直连模型；agent = 只用 agent；
        # llm = 只用直连模型。前端可用 mode 显式指定，服务端可用 YZ_ASK_MODE 设默认。
        mode = (body.get("mode") or os.environ.get("YZ_ASK_MODE") or "auto").lower()
        if mode not in ("auto", "agent", "llm"):
            mode = "auto"
        conversation_id = (body.get("conversation_id") or "").strip()[:80]
        context = body.get("context") or {}
        gateway = ensure_gateway() if mode in ("auto", "agent") else None
        llm_ans = ensure_llm() if mode in ("auto", "llm") else None
        degraded = gateway is None and llm_ans is None
        reason = STATE["fallback_reason"] if degraded else None
        if mode == "auto" and gateway is None and llm_ans is not None:
            # agent 不可用但直连模型可用：这不是正常 agent 链路，必须标降级。
            degraded = True
            reason = STATE["fallback_reason"] or "agent_unavailable"
        served_by = None
        session_id = None
        result = None
        image_match = None
        emitted = {"delta": False}

        self.sse_start()

        def emit(kind, payload):
            if kind == "delta" and (payload or {}).get("text"):
                emitted["delta"] = True
            self.sse_send(kind, payload)

        def run_llm():
            """直连模型分支：文本/视觉二选一，返回 (result, text, cites)。"""
            nonlocal image_match
            image = body.get("image")
            res = llm_ans.ask(query, emit, image=image, context=context)
            out = res.get("text") or ""
            if image:
                # 模型给的框要从正文里剥掉再发 delta，不能让用户看到 JSON
                bbox, raw, cleaned = vision_mod.extract_bbox(out)
                if bbox:
                    out = cleaned
                    res["text"] = out
                found = ensure_image_index().match_all(image)
                image_match = {
                    "case_id": found[0] if found else None,
                    "case_ids": found,
                    "bbox": bbox,
                    "raw_bbox": raw,
                }
                if not found:
                    # 认不出就明说，并给一条可走的路，而不是让用户卡在这里
                    image_match["suggest"] = suggest_cases()
            cs = res.get("cites") or []
            # 直连模型是一次性返回，没有「首字」时间，留空而不是填 0 假装有
            res["total_ms"] = res.get("ms")
            res["delta_chars"] = len(out)
            res["first_token_ms"] = None
            emit("delta", {"text": out})
            return res, out, cs

        try:
            if gateway is not None:
                # 影像问答拆成两段：视觉只负责“这是哪一例、框在哪”，
                # agent 负责解释与引用。不能让 agent 直接吃 base64，
                # 也不能因为走 agent 就把视觉定位丢掉。
                if body.get("image") and llm_ans is not None and mode == "auto":
                    try:
                        vres = llm_ans.ask(
                            query, lambda kind, payload: None,
                            image=body.get("image"), context=context)
                        vtext = vres.get("text") or ""
                        bbox, raw, _cleaned = vision_mod.extract_bbox(vtext)
                        found = ensure_image_index().match_all(body.get("image"))
                        image_match = {
                            "case_id": found[0] if found else None,
                            "case_ids": found,
                            "bbox": bbox,
                            "raw_bbox": raw,
                        }
                        if not found:
                            image_match["suggest"] = suggest_cases()
                        ctx2 = dict(context or {})
                        ctx2["图像定位"] = "病例 %s；bbox %s" % (
                            image_match["case_id"] or "未入库",
                            bbox or "未给出")
                        context = ctx2
                        emit("trace", {"stage": "vision_locate", "status": "completed",
                                       "ms": vres.get("ms", 0)})
                    except Exception as exc:
                        # 视觉失败不阻断 agent：仍可用文本回答，只是没有定位
                        emit("trace", {"stage": "vision_locate", "status": "error",
                                       "ms": 0, "detail": str(exc)[:120]})
                # 同一 conversation_id 在 TTL 内复用；不再每次 force=True。
                session_id = gateway.ensure_session(
                    role, device, key=conversation_id or None)
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
                result = gateway.ask(session_id, query, emit, context=context, hint=hint)
                text = result.get("text") or ""
                # agent 的引用写在正文里；这里把真实存在的 id 提成 citation 事件，
                # 前端才能显示可核对的卡片，而不是让用户自己在长文里找 id。
                cites = cites_from_text(text, query)
                served_by = "agent"
            elif llm_ans is not None:
                # 双模型路由：body.image 为 data URL 时走视觉模型，否则走文本模型
                result, text, cites = run_llm()
                served_by = "llm"
            else:
                text, cites = fallback_answer(query)
                emit("trace", {"stage": "kb_retrieve", "skill": "local_keyword",
                               "status": "degraded", "ms": 1})
                emit("delta", {"text": text})
                served_by = "fallback"
        except Exception as exc:
            agent_error = str(exc)[:200]
            had_delta = emitted["delta"]
            # 已经吐出部分内容时先清空，避免 fallback 拼在思考后面。
            if had_delta:
                emit("reset", {"reason": "agent_failed"})
                emitted["delta"] = False
            emit("trace", {"stage": "agent_generate", "skill": "fallback",
                           "status": "error", "ms": 0})
            degraded = True
            reason = agent_error
            # 只有 auto 且 agent 还没产出内容时才降级到直连模型；
            # 已产出内容说明用户已经看到一部分，再答一遍会重复。
            if mode == "auto" and llm_ans is not None and not had_delta:
                try:
                    result, text, cites = run_llm()
                    served_by = "llm"
                except Exception as exc2:
                    text, cites = fallback_answer(query)
                    served_by = "fallback"
                    reason = (agent_error + " / " + str(exc2))[:200]
                    emit("delta", {"text": text})
            else:
                text, cites = fallback_answer(query)
                served_by = "fallback"
                emit("delta", {"text": text})

        # 本地引用先发；每条都标 kind=local，前端才能和文献引用分组。
        for cite in cites:
            if isinstance(cite, dict) and not cite.get("kind"):
                cite["kind"] = "local"
            self.sse_send("citation", cite)

        # 网络文献：显式开关，失败不阻断主回答，但必须在 done 里说清楚。
        research = bool(body.get("research")) or (body.get("surface") == "literature")
        literature = {"ok": False, "reason": "not_requested", "items": [],
                      "query": None, "source": "PubMed"}
        lit_items = []
        if research and STATE["offline"]:
            # 离线演练必须真的离线：不能一边说降级，一边偷偷打 PubMed。
            literature = {"ok": False, "reason": "offline_mode", "items": [],
                          "query": None, "source": "PubMed"}
        elif research:
            sign_ids = []
            for c in cites:
                cid = (c.get("id") or "") if isinstance(c, dict) else ""
                if cid.startswith("SIGN-") and cid not in sign_ids:
                    sign_ids.append(cid)
                for sid in (c.get("sign_ids") or []) if isinstance(c, dict) else []:
                    if str(sid).startswith("SIGN-") and sid not in sign_ids:
                        sign_ids.append(sid)
            for sid in body.get("sign_ids") or []:
                if sid not in sign_ids:
                    sign_ids.append(sid)
            modality = (body.get("modality")
                        or (context or {}).get("检查类型")
                        or (context or {}).get("modality"))
            t_lit = time.time()
            try:
                literature = litsearch.search_signs(
                    sign_ids[:3], extra=body.get("terms"),
                    modality=modality, limit=int(body.get("lit_limit") or 4))
            except Exception as exc:
                literature = {"ok": False,
                              "reason": "%s: %s" % (type(exc).__name__, exc),
                              "items": [], "query": None, "source": "PubMed"}
            lit_items = literature.get("items") or []
            for item in lit_items:
                self.sse_send("citation", item)
            self.sse_send("trace", {
                "stage": "literature_search", "skill": "pubmed",
                "status": "completed" if literature.get("ok") else "error",
                "ms": int((time.time() - t_lit) * 1000),
                "hits": len(lit_items),
                "detail": {"query": literature.get("query"),
                           "reason": literature.get("reason")},
            })

        t_persist = time.time()
        persist_ms = 0
        trace = build_trace(run_id, request, result, degraded, reason)
        save_run(run_id, "trace.json", trace)
        save_run(run_id, "answer.json", {"run_id": run_id, "text": text,
                                         "citations": cites, "literature": lit_items,
                                         "degraded": degraded})
        persist_ms = int((time.time() - t_persist) * 1000)
        trace["spans"].append({"stage": "persist", "skill": "json", "status": "completed",
                               "ms": persist_ms})
        save_run(run_id, "trace.json", trace)

        # 运行期只能发增量事件，收尾才有全貌：把完整 span 统一补发一遍。
        # 前端按 stage 覆盖，运行期的粗粒度 span 会被这里的精确值替换。
        for span in trace["spans"]:
            if span.get("stage") in TRACE_STAGES:
                self.sse_send("trace", span)

        grounding = trace["citation_audit"]["grounding"]
        followups = make_followups(cites, grounding, image_match)
        # 先发 followup，再发 done：前端可以先渲染可点的下一步，再收本轮汇总。
        self.sse_send("followup", {"items": followups, "source": "rules"})
        self.sse_send("done", {
            "run_id": run_id,
            "degraded": degraded,
            "reason": reason,
            # 实际是谁回答的：agent / llm / fallback。前端据此显示链路徽标，
            # 不允许把降级回答包装成 agent 回答。
            "served_by": served_by or ("fallback" if degraded else "agent"),
            "mode": mode,
            "conversation_id": conversation_id or None,
            "session_id": session_id,
            "followups": followups,
            "followups_source": "rules",
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
            # 双引用：本地库引用 + 网络文献引用，分开计数，前端分组渲染
            # 有回答但没有任何库内引用：不篡改正文，只如实标记，前端必须提示
            "ungrounded": bool(not cites and not degraded),
            "citations": {
                "local": len(cites),
                "literature": len(lit_items),
                "direct": len([c for c in cites if c.get("relevance") == "direct"]),
                "related": len([c for c in cites if c.get("relevance") == "related"]),
                "off": len([c for c in cites if c.get("relevance") == "off"]),
            },
            "literature": {
                "ok": bool(literature.get("ok")),
                "reason": literature.get("reason"),
                "query": literature.get("query"),
                "source": literature.get("source"),
                "hit_count": literature.get("hit_count"),
            },
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
    STATE["offline"] = bool(args.offline)

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
