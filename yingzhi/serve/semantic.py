"""本地语义检索：稀疏 TF-IDF 向量空间 + 余弦相似度。

为什么不是 grep：
  * grep 只认字面子串。用户问「毛玻璃结节」而库里写「磨玻璃影」，
    grep 0 命中；本模块把两者映射到共享的字符 n-gram / 别名特征上，
    余弦分数仍然很高。
  * grep 没有排序。这里每个结果都有可解释的分数和命中的特征，
    答辩时可以逐条指出「为什么这条排第一」。

实现边界（不夸大）：
  * 这是稀疏向量检索（TF-IDF + 余弦），不是神经网络 embedding。
    health 里 semantic_search_kind 会如实写明。
  * 不联网、不加载模型权重，纯标准库实现，构建一次约 0.2s。
  * 只读 kb/data，不写库、不改数据。

对外接口：
    idx = get_index()                 # 进程内单例，数据变了自动重建
    idx.search("毛玻璃结节", top_k=5)  # -> {"items": [...], ...}
    idx.stats()                       # -> 文档数、特征数、构建耗时
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
KB_DATA = ROOT / "kb" / "data"

_CJK = re.compile(r"[\u4e00-\u9fa5]+")
_ASCII = re.compile(r"[a-z0-9][a-z0-9\-\.\+]*")
_PUNCT = re.compile(r"[\s，。？！、；：\"'“”‘’（）()\[\]【】·—…/\\]+")

# 不同来源的权重：词条 > 概念 > 指南 > 病例 > 分区描述 > 原文段落。
# 目的不是压制段落，而是让「一个词条」比「一段提到该词的原文」更容易被看到。
KIND_BOOST = {
    "sign": 1.00,
    "concept": 0.96,
    "guideline": 0.92,
    "case": 0.88,
    "claim": 0.80,
    # 原文段落数量最多（546 条），且很多是词条字段的派生切片。
    # 压低它的基础权重，让「词条本身」优先于「提到词条的段落」。
    "paragraph": 0.58,
}

MAX_FEATURES_PER_DOC = 400


def norm(text) -> str:
    """只做归一化，不丢语义：保留中文、英文、数字。"""
    return _PUNCT.sub("", str(text or "")).lower()


def features(text) -> Counter:
    """把文本映射到稀疏特征。

    - 中文：单字（权重 0.45，兜底）+ 相邻二字（权重 1.0，主特征）
    - 英文/数字：整词（权重 1.0）
    单字权重低，是为了让「肺炎」和「肺癌」只在「肺」上弱相关，
    真正决定排序的是「肺炎 / 肺癌」这组二字特征。
    """
    t = norm(text)
    out = Counter()
    for tok in _ASCII.findall(t):
        if len(tok) >= 2 or tok.isdigit():
            out["w:" + tok] += 1.0
    for run in _CJK.findall(t):
        if len(run) == 1:
            out["c:" + run] += 0.45
            continue
        for ch in run:
            out["c:" + ch] += 0.45
        for i in range(len(run) - 1):
            out["b:" + run[i:i + 2]] += 1.0
    if len(out) > MAX_FEATURES_PER_DOC:
        # 超长段落只保留权重最高的特征，避免个别长文档主导倒排表。
        out = Counter(dict(out.most_common(MAX_FEATURES_PER_DOC)))
    return out


def _read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _join(*parts) -> str:
    out = []
    for p in parts:
        if p is None:
            continue
        if isinstance(p, (list, tuple, set)):
            out.extend(str(x) for x in p if x)
        else:
            out.append(str(p))
    return " ".join(x for x in out if x).strip()


def _snippet(text, limit=96) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s[:limit] + ("…" if len(s) > limit else "")


# 口语 → 标准影像描述。grep 对「肺里有点白」无能为力；
# 这里先做一次可解释的规则改写，再走向量检索，属于查询改写，不是模型推理。
COLLOQUIAL = {
    "有点白": "密度增高影 磨玻璃影 实变",
    "发白": "密度增高影",
    "白了": "实变 密度增高影",
    "黑影": "低密度影",
    "积水": "积液",
    "大心脏": "心影增大 心脏增大",
    "纹理多": "肺纹理增多",
    "结节影": "结节",
    "片子上": "",
    "片子里": "",
}


def _bigrams(s: str) -> List[str]:
    return [s[i:i + 2] for i in range(len(s) - 1)]


def dice(a: str, b: str) -> float:
    """字符二元组 Dice 系数，用来判断两个短名是不是同一说法的变体。"""
    A, B = _bigrams(a), _bigrams(b)
    if not A or not B:
        return 0.0
    pool: Counter = Counter(A)
    hit = 0
    for x in B:
        if pool.get(x):
            pool[x] -= 1
            hit += 1
    return 2.0 * hit / (len(A) + len(B))


def _documents(data_dir: Path) -> List[dict]:
    """把 kb/data 的六类数据摊平成可检索文档。"""
    docs: List[dict] = []

    for r in _read_jsonl(data_dir / "signs.jsonl"):
        docs.append({
            "kind": "sign",
            "id": r.get("id") or "",
            "title": r.get("name") or r.get("id") or "",
            "text": r.get("appearance") or "",
            "url": "",
            "aliases": list(r.get("aliases") or []),
            # 词条本名与别名重复一次：一个词条的「名字」应当比一段顺带提到它的
            # 原文更重，否则搜「毛玻璃结节」会先命中指南里的长段落。
            "search_text": _join(r.get("name"), r.get("name"), r.get("aliases"),
                                 r.get("aliases"), r.get("en"),
                                 r.get("appearance"), r.get("body_part"),
                                 r.get("may_see_in"), r.get("pitfalls"), r.get("tags")),
        })

    for r in _read_jsonl(data_dir / "concepts.jsonl"):
        docs.append({
            "kind": "concept",
            "id": r.get("id") or "",
            "title": r.get("name") or r.get("id") or "",
            "text": r.get("note") or "",
            "url": "",
            "aliases": list(r.get("aliases") or []),
            "search_text": _join(r.get("name"), r.get("name"), r.get("aliases"),
                                 r.get("aliases"), r.get("en"), r.get("note")),
        })

    for r in _read_jsonl(data_dir / "guidelines.jsonl"):
        docs.append({
            "kind": "guideline",
            "id": r.get("id") or "",
            "title": " · ".join([x for x in [r.get("standard_name"), r.get("category")] if x])
                     or r.get("id") or "",
            "text": r.get("statement") or "",
            "url": r.get("source_url") or "",
            "search_text": _join(r.get("standard_name"), r.get("category"), r.get("statement"),
                                 r.get("conditions"), r.get("keywords"), r.get("action"),
                                 r.get("body_part")),
        })

    for r in _read_jsonl(data_dir / "cases.jsonl"):
        docs.append({
            "kind": "case",
            "id": r.get("id") or "",
            "title": " · ".join([x for x in [r.get("id"), r.get("title")] if x]),
            "text": r.get("description_public") or r.get("teaching_note") or "",
            "url": r.get("source_page") or "",
            "search_text": _join(r.get("title"), r.get("description_public"),
                                 r.get("teaching_note"), r.get("sign_tags"),
                                 r.get("body_part"), r.get("chapter")),
        })

    for r in _read_jsonl(data_dir / "claims.jsonl"):
        docs.append({
            "kind": "claim",
            "id": r.get("id") or "",
            "title": r.get("id") or "",
            "text": r.get("text") or "",
            "url": "",
            "search_text": _join(r.get("text"), r.get("sign_ids"), r.get("image_id"),
                                 r.get("region_id")),
        })

    for r in _read_jsonl(data_dir / "paragraphs.jsonl"):
        docs.append({
            "kind": "paragraph",
            "id": r.get("para_id") or "",
            "title": " · ".join([x for x in [r.get("title"), r.get("section")] if x]),
            "text": r.get("text") or "",
            "url": r.get("source_url") or "",
            "search_text": _join(r.get("title"), r.get("section"), r.get("text")),
        })

    return [d for d in docs if d["id"] and d["search_text"]]


class SemanticIndex:
    """倒排索引 + TF-IDF 余弦。倒排表保证内存只与「非零特征」成正比。"""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir or KB_DATA)
        self.docs: List[dict] = []
        self.postings: Dict[str, List[Tuple[int, float]]] = {}
        self.norms: List[float] = []
        self.idf: Dict[str, float] = {}
        self.alias_map: Dict[str, List[str]] = {}
        self.built_at = 0.0
        self.build_ms = 0.0
        self._signature: Optional[Tuple] = None
        self._lock = threading.Lock()

    # ---------- 构建 ----------

    def _data_signature(self) -> Tuple:
        names = ("signs.jsonl", "concepts.jsonl", "guidelines.jsonl",
                 "cases.jsonl", "claims.jsonl", "paragraphs.jsonl")
        sig = []
        for name in names:
            p = self.data_dir / name
            try:
                st = p.stat()
                sig.append((name, st.st_mtime_ns, st.st_size))
            except OSError:
                sig.append((name, 0, 0))
        return tuple(sig)

    def build(self) -> "SemanticIndex":
        started = time.time()
        self.docs = _documents(self.data_dir)

        tfs = [features(d["search_text"]) for d in self.docs]
        df: Counter = Counter()
        for tf in tfs:
            for f in tf:
                df[f] += 1
        n = max(1, len(self.docs))
        # 平滑 IDF：出现在所有文档里的特征（如「胸」）权重趋近 1，不归零。
        self.idf = {f: math.log((n + 1.0) / (c + 1.0)) + 1.0 for f, c in df.items()}

        postings: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
        norms: List[float] = []
        for di, tf in enumerate(tfs):
            vec: Dict[str, float] = {}
            for f, c in tf.items():
                # 次线性 TF：长文档重复 10 次不等于相关度 10 倍。
                w = (1.0 + math.log(c)) * self.idf.get(f, 1.0)
                vec[f] = w
            doc_norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
            norms.append(doc_norm)
            for f, w in vec.items():
                postings[f].append((di, w / doc_norm))

        self.postings = dict(postings)
        self.norms = norms

        # 别名扩展表：查询里出现别名时，把实体本名也加进查询特征。
        # 「毛玻璃影」是「磨玻璃影」的别名，grep 命中不了，这里能。
        alias_map: Dict[str, List[str]] = defaultdict(list)
        for d in self.docs:
            if d["kind"] not in ("sign", "concept"):
                continue
            for alias in self._aliases_of(d):
                key = norm(alias)
                if len(key) >= 2:
                    alias_map[key].append(d["title"])
        self.alias_map = dict(alias_map)

        self.built_at = time.time()
        self.build_ms = (self.built_at - started) * 1000.0
        self._signature = self._data_signature()
        return self

    def _aliases_of(self, doc: dict) -> List[str]:
        """从原始数据补别名；文档本身只保留拼接后的 search_text。"""
        # 构建期把 aliases 记进 docs，避免二次读盘。
        return doc.get("aliases") or []

    # ---------- 查询 ----------

    def _query_vector(self, query: str) -> Tuple[Dict[str, float], List[str]]:
        qtf = features(query)
        qn = norm(query)
        expanded: List[str] = []
        for spoken, standard in COLLOQUIAL.items():
            if spoken and spoken in qn and standard:
                for f, c in features(standard).items():
                    qtf[f] += 0.7 * c
                expanded.append(standard.split()[0])
        for alias, titles in self.alias_map.items():
            if len(alias) < 3:
                continue
            # 三种命中都算同一说法的变体：包含、被包含、二元组高度重合。
            # 「毛玻璃结节」与别名「毛玻璃影」dice≈0.57，grep 永远不会命中。
            # 阈值不能太松：两个字的名词（气胸 / 积液）会互相误扩展。
            if not (alias in qn or qn in alias or dice(qn, alias) >= 0.62):
                continue
            if len(expanded) >= 2:
                break
            for title in titles[:1]:
                for f, c in features(title).items():
                    qtf[f] += 0.8 * c
                expanded.append(title)
        vec = {}
        for f, c in qtf.items():
            w = (1.0 + math.log(c)) * self.idf.get(f, 1.0)
            vec[f] = w
        return vec, expanded

    def search(self, query: str, top_k: int = 8, min_score: float = 0.04,
               kinds: Optional[Iterable[str]] = None) -> dict:
        started = time.time()
        q = (query or "").strip()
        if not q or not self.docs:
            return {"ok": True, "query": q, "mode": "semantic", "count": 0,
                    "items": [], "took_ms": 0.0, "expanded": []}

        qvec, expanded = self._query_vector(q)
        qnorm = math.sqrt(sum(w * w for w in qvec.values())) or 1.0
        allow = set(kinds) if kinds else None

        scores: Dict[int, float] = defaultdict(float)
        hits: Dict[int, List[str]] = defaultdict(list)
        for f, qw in qvec.items():
            post = self.postings.get(f)
            if not post:
                continue
            for di, dw in post:
                if allow is not None and self.docs[di]["kind"] not in allow:
                    continue
                scores[di] += (qw / qnorm) * dw
                if len(hits[di]) < 6:
                    hits[di].append(f)

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        limit = max(1, min(int(top_k or 8), 30))
        scored = []
        # 先按 boost 后的分数收集候选，再统一排序：
        # 倒排表只按原始余弦排序，boost 会改变名次，必须重排一次。
        for di, cos in ranked[: max(limit * 6, 60)]:
            doc = self.docs[di]
            score = cos * KIND_BOOST.get(doc["kind"], 0.8)
            # 标题级匹配再加一档：用户问的正是这个词条本身时，
            # 它应该排在「某段原文顺带提到它」之前。
            if doc["kind"] in ("sign", "concept"):
                d = dice(norm(q), norm(doc["title"]))
                if d >= 0.4:
                    score *= 1.0 + 0.6 * d
            # 词条的派生段落（SIGN-xxx#appearance-1 等）只是字段切片，
            # 词条本身已经在结果里时，不该让切片排到前面。
            if doc["kind"] == "paragraph" and str(doc["id"]).startswith(("SIGN-", "CON-")):
                score *= 0.72
            if score < min_score:
                continue
            scored.append({
                "kind": doc["kind"],
                "id": doc["id"],
                "title": doc["title"],
                "snippet": _snippet(doc["text"]),
                "score": round(score, 4),
                "cosine": round(cos, 4),
                "source_url": doc.get("url") or "",
                "matched": [f.split(":", 1)[-1] for f in hits[di][:4]],
            })

        scored.sort(key=lambda x: -x["score"])
        items = scored[:limit]

        return {
            "ok": True,
            "query": q,
            "mode": "semantic",
            "count": len(items),
            "items": items,
            "expanded": expanded[:4],
            "took_ms": round((time.time() - started) * 1000.0, 2),
        }

    # ---------- 自检 ----------

    def stats(self) -> dict:
        kinds: Counter = Counter(d["kind"] for d in self.docs)
        return {
            "docs": len(self.docs),
            "features": len(self.postings),
            "aliases": len(self.alias_map),
            "by_kind": dict(kinds),
            "build_ms": round(self.build_ms, 2),
            "built_at": self.built_at,
            "model": "tfidf-char-ngram-cosine",
        }

    def healthy(self) -> bool:
        return bool(self.docs) and bool(self.postings) and bool(self.norms)


_INDEX: Optional[SemanticIndex] = None
_INDEX_LOCK = threading.Lock()


def get_index(data_dir: Optional[Path] = None, force: bool = False) -> SemanticIndex:
    """进程内单例；kb/data 变更后按 mtime 自动重建。"""
    global _INDEX
    with _INDEX_LOCK:
        if _INDEX is None or force:
            _INDEX = SemanticIndex(data_dir).build()
            return _INDEX
        sig = _INDEX._data_signature()
        if sig != _INDEX._signature:
            _INDEX = SemanticIndex(data_dir or _INDEX.data_dir).build()
        return _INDEX


def search(query: str, top_k: int = 8, kinds: Optional[Iterable[str]] = None) -> dict:
    return get_index().search(query, top_k=top_k, kinds=kinds)


if __name__ == "__main__":
    import sys
    idx = get_index(force=True)
    print(json.dumps(idx.stats(), ensure_ascii=False, indent=1))
    q = " ".join(sys.argv[1:]) or "毛玻璃结节"
    print(json.dumps(idx.search(q, top_k=5), ensure_ascii=False, indent=1))
