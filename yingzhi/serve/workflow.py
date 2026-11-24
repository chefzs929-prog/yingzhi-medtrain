"""RadioCheck 本地工作流：把一次问答拆成五步可回放的编排。

为什么要有它：
  之前 trace 里的 workflow 永远标 unavailable —— 不是没做，是根本没这一步。
  现在每次 /api/ask 都真的跑一遍：
    parse → retrieve → locate → compose → audit

每一步都产出可落盘的证据（输入、输出、耗时、状态），
trace.json 里能看到同一份 steps，答辩时可以逐步回放。

边界：
  * 工作流本身不生成自然语言答案；它负责「先把证据找齐、把定位做对」，
    再把证据交给 agent / 直连模型。
  * 不联网；语义检索是本地的 TF-IDF 向量（见 semantic.py）。
  * 任何一步失败都不阻断后续：标 error/skipped，继续往下走，最后由 audit 汇总。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KB_SCRIPTS = ROOT / "kb" / "scripts"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(KB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(KB_SCRIPTS))

import semantic  # noqa: E402

WORKFLOW_VERSION = "1.0"
STEPS = ("parse", "retrieve", "locate", "compose", "audit")

# 只把「能直接当证据引用」的条目写进提示；段落太多会挤爆上下文。
# claim 必须在内：病例逐区原文就在 claims 里，排除它会让 agent 引到别的病例。
EVIDENCE_KINDS = ("claim", "sign", "concept", "guideline", "case")


class _Timer:
    def __init__(self):
        self.t0 = time.time()

    def ms(self) -> int:
        return int((time.time() - self.t0) * 1000)


def _region_kb():
    """懒加载 RegionKB：只读 kb/data，加载约 10ms，失败时返回 None。"""
    try:
        from serve_region import RegionKB  # type: ignore
        return RegionKB()
    except Exception:
        return None


def _atlas():
    try:
        import atlas  # type: ignore
        return atlas.load()
    except Exception:
        return None


class CaseEvidence:
    """当前病例的逐区原文：E1 的权威来源。

    语义索引里 CASE-006 与 CASE-202 同源，检索很容易把当前病例挤掉；
    所以只要请求带了 case_id，就先从 chest_reading / claims 直接取当前病例，
    再把这条证据置顶，保证 agent 的 E1 不会指向别的病例。
    """

    def __init__(self):
        self._cases = None
        self._claims = None
        self._loaded_at = 0.0

    def _load(self):
        import json
        data_dir = ROOT / "kb" / "data"
        if self._cases is None:
            try:
                raw = json.loads((data_dir / "chest_reading.json").read_text(encoding="utf8"))
                self._cases = {c["id"]: c for c in raw.get("cases") or [] if c.get("id")}
            except Exception:
                self._cases = {}
        if self._claims is None:
            claims = {}
            try:
                for line in (data_dir / "claims.jsonl").read_text(encoding="utf8").splitlines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    claims.setdefault(str(row.get("image_id")), []).append(row)
            except Exception:
                claims = {}
            self._claims = claims
        self._loaded_at = time.time()

    def for_case(self, case_id, zone_id=None):
        if not case_id:
            return []
        self._load()
        case = (self._cases or {}).get(case_id)
        if not case:
            return []
        zones = case.get("zones") or []
        zone = None
        if zone_id:
            zone = next((z for z in zones if z.get("id") == zone_id), None)
        if zone is None:
            # 没指定分区时，优先取第一个异常区；没有异常区就取全片。
            zone = next((z for z in zones if z.get("status") == "abnormal"), None)
        if zone is None:
            zone = next((z for z in zones if z.get("id") == "WHOLE"), None)
        if zone is None:
            return []

        claims = (self._claims or {}).get(case_id) or []
        claim = next((c for c in claims if c.get("region_id") == "REG-%s-%s" % (case_id.replace("CASE-", ""), zone.get("id"))), None)
        if claim is None:
            claim = next((c for c in claims if zone.get("id") and str(c.get("region_id") or "").endswith("-" + str(zone.get("id")))), None)

        zone_text = (zone.get("text") or "").strip()
        claim_text = (claim or {}).get("text") or ""
        text = zone_text or claim_text
        if not text:
            return []
        title = "%s · %s（%s）" % (case_id, zone.get("name") or zone.get("id"), zone.get("id"))
        item = {
            "kind": "claim",
            # 有 claim 用 claim id；没有就用病例 id，保证 audit 能在索引里查到。
            "id": (claim or {}).get("id") or case_id,
            "title": title,
            "snippet": text,
            "score": 1.0,
            "case_id": case_id,
            "region_id": zone.get("id"),
            "region_name": zone.get("name"),
            "status": zone.get("status"),
            "bbox": zone.get("coords"),
            "image": case.get("image"),
            "source_url": case.get("source_page") or "",
            "sign_ids": (claim or {}).get("sign_ids") or zone.get("sign_ids") or [],
        }
        return [item]


class Workflow:
    def __init__(self, index=None):
        self.index = index or semantic.get_index()
        self._region_kb = None
        self._atlas = None
        self._cases = CaseEvidence()

    # ---------- 单步 ----------

    def _parse(self, query: str) -> dict:
        t = _Timer()
        region = ""
        try:
            import ask_engine  # type: ignore
            region = ask_engine.parse_region(ask_engine.norm(query)) or ""
        except Exception:
            region = ""
        detail = {"query": query, "region_hint": region}
        return {"step": "parse", "status": "completed", "ms": t.ms(), "detail": detail}

    def _retrieve(self, query: str, top_k: int) -> dict:
        t = _Timer()
        try:
            res = self.index.search(query, top_k=top_k)
            items = res.get("items") or []
            detail = {
                "engine": "semantic.tfidf-cosine",
                "expanded": res.get("expanded") or [],
                "took_ms": res.get("took_ms"),
                "top": [
                    {"kind": it["kind"], "id": it["id"],
                     "score": it["score"], "title": it["title"]}
                    for it in items[:top_k]
                ],
            }
            status = "completed" if items else "empty"
            return {"step": "retrieve", "status": status, "ms": t.ms(),
                    "detail": detail, "_items": items}
        except Exception as exc:
            return {"step": "retrieve", "status": "error", "ms": t.ms(),
                    "detail": {"error": str(exc)[:160]}, "_items": []}

    def _locate(self, case_id: Optional[str], bbox: Optional[List[float]],
                modality: Optional[str], body_part: Optional[str],
                view: Optional[str], zone_id: Optional[str] = None) -> dict:
        t = _Timer()
        # 只有 case_id + zone_id 时也要能定位：E1 靠的是病例分区，不一定要用户拖框。
        if case_id and zone_id:
            items = self._cases.for_case(case_id, zone_id)
            if items:
                it = items[0]
                return {"step": "locate", "status": "completed", "ms": t.ms(),
                        "detail": {"source": "case_zone", "case_id": case_id,
                                   "region_id": it.get("region_id"),
                                   "region_name": it.get("region_name"),
                                   "status": it.get("status"),
                                   "bbox": it.get("bbox")}}
        if case_id and bbox and len(bbox) == 4:
            kb = self._region_kb or _region_kb()
            self._region_kb = kb
            if kb is None:
                return {"step": "locate", "status": "unavailable", "ms": t.ms(),
                        "detail": {"reason": "region_kb_not_loaded"}}
            try:
                r = kb.locate(case_id, bbox)
                return {"step": "locate", "status": "completed", "ms": t.ms(),
                        "detail": {"source": "region_kb", "case_id": case_id,
                                   "status": r.get("status"),
                                   "primary": (r.get("primary") or {}).get("region", {}).get("id")
                                   if r.get("primary") else None,
                                   "candidates": [c.get("region", {}).get("id")
                                                  for c in (r.get("candidates") or [])][:4]},
                        "_result": r}
            except Exception as exc:
                return {"step": "locate", "status": "error", "ms": t.ms(),
                        "detail": {"error": str(exc)[:160]}}

        if bbox and len(bbox) == 4:
            T = self._atlas or _atlas()
            self._atlas = T
            if T is None:
                return {"step": "locate", "status": "unavailable", "ms": t.ms(),
                        "detail": {"reason": "atlas_not_loaded"}}
            try:
                matched = T.match(modality, body_part, view)
                if not matched:
                    return {"step": "locate", "status": "skipped", "ms": t.ms(),
                            "detail": {"reason": "no_atlas_match"}}
                r = T.locate(matched["atlas"]["id"], bbox)
                return {"step": "locate", "status": "completed", "ms": t.ms(),
                        "detail": {"source": "atlas_template",
                                   "atlas": matched["atlas"]["id"],
                                   "status": r.get("status"),
                                   "region": (r.get("region") or {}).get("id")},
                        "_result": r}
            except Exception as exc:
                return {"step": "locate", "status": "error", "ms": t.ms(),
                        "detail": {"error": str(exc)[:160]}}

        return {"step": "locate", "status": "skipped", "ms": t.ms(),
                "detail": {"reason": "no_case_or_bbox"}}

    def _compose(self, items: List[dict], locate: dict,
                 case_evidence: Optional[List[dict]] = None) -> dict:
        t = _Timer()
        # 低于阈值的命中只是共享了个别单字，不能当证据交给模型，
        # 否则「证据不足」会被噪声命中掩盖。
        retrieved = [it for it in items
                     if it["kind"] in EVIDENCE_KINDS and it["score"] >= 0.12][:8]
        # 当前病例证据必须置顶：它是 E1 的唯一权威来源，不能被别的病例挤掉。
        pinned = list(case_evidence or [])
        pinned_ids = {it.get("id") for it in pinned}
        current_case = (pinned[0].get("case_id") if pinned else None)
        if current_case:
            # 有当前病例时，其他病例的 claim / case 不进证据区，
            # 否则 agent 会像实测那样把 CASE-006 的问题引到 CASE-202。
            def same_case(it):
                if it.get("kind") == "case":
                    return it.get("id") == current_case
                if it.get("kind") == "claim":
                    cid = str(it.get("id") or "").replace("CLM-", "CASE-").split("-")[0:2]
                    return "-".join(cid) == current_case
                return True
            retrieved = [it for it in retrieved if same_case(it)]
        # 当前分区挂载的征象词条也补进来：E1 之外还要有 L1 的定义原文。
        sign_extra = []
        if pinned:
            known = {d["id"]: d for d in self.index.docs}
            for sid in (pinned[0].get("sign_ids") or [])[:3]:
                d = known.get(sid)
                if d:
                    sign_extra.append({
                        "kind": "sign", "id": d["id"], "title": d["title"],
                        "snippet": (d.get("text") or "")[:220],
                        "score": 0.9, "source_url": d.get("url") or "",
                    })
        evidence = pinned + sign_extra + [it for it in retrieved
                                         if it.get("id") not in pinned_ids
                                         and it.get("id") not in {x["id"] for x in sign_extra}]
        evidence = evidence[:6]

        lines = ["【本地工作流已检索到的库内证据】（语义向量检索，不是关键词 grep）"]
        if pinned:
            lines.append("【当前病例证据 · E1 必须用它】")
            for it in pinned:
                lines.append("- [%s] %s / 状态 %s / bbox %s / 原文：%s" % (
                    it["id"], it["title"], it.get("status") or "—",
                    it.get("bbox") or "—", it.get("snippet") or ""))
            lines.append("引用要求：E1 必须写当前病例 %s 的分区；不要引用其他病例的 id。" %
                         (pinned[0].get("case_id") or "当前病例"))
        if sign_extra:
            lines.append("【当前分区挂载的征象词条 · L1 优先用它】")
            for it in sign_extra:
                lines.append("- [%s] %s：%s" % (it["id"], it["title"], it["snippet"]))
        if retrieved:
            lines.append("【库内其他证据】")
            for it in retrieved:
                lines.append("- [%s] %s（相似度 %.3f）：%s" % (
                    it["id"], it["title"], it["score"], it["snippet"]))
        if not evidence:
            lines.append("- 未命中：库内没有与该问题直接对应的词条，请明确说明证据不足。")
        lines.append(
            "作答要求：\n"
            "1) 只用上面出现过的 id 作为引用，不要编造新 id；\n"
            "2) 每个关键结论后用 [id] 标注来源；\n"
            "3) 有当前病例证据时，先回答这张片子的分区所见，再讲通用鉴别；\n"
            "4) 证据不足时直接说「库内证据不足」，不要用通识补全成确定结论。"
        )
        hint = "\n".join(lines)
        context = {}
        if pinned:
            it = pinned[0]
            context["病例证据"] = "%s %s / %s / 原文：%s" % (
                it.get("case_id"), it.get("region_name") or it.get("region_id"),
                it.get("status") or "—", it.get("snippet") or "")
        if evidence:
            context["本地检索证据"] = "；".join(
                "%s %s" % (it["id"], it["title"]) for it in evidence[:4])
        if sign_extra:
            context["分区征象"] = "；".join(
                "%s %s" % (it["id"], it["title"]) for it in sign_extra)
        if locate.get("status") == "completed":
            d = locate.get("detail") or {}
            if d.get("region_id"):
                context["分区定位"] = "%s / %s" % (d.get("case_id") or "", d.get("region_id"))
            elif d.get("primary") or d.get("region"):
                context["分区定位"] = str(d.get("primary") or d.get("region"))
        return {"step": "compose", "status": "completed", "ms": t.ms(),
                "detail": {"evidence": len(evidence), "pinned": len(pinned),
                           "hint_chars": len(hint)},
                "_hint": hint, "_context": context, "_evidence": evidence}

    def _audit(self, evidence: List[dict]) -> dict:
        """引用自证：证据里的 id 必须真的能在索引里找到。"""
        t = _Timer()
        known = {d["id"] for d in self.index.docs}
        checked = [it["id"] for it in evidence]
        invalid = [i for i in checked if i not in known]
        return {"step": "audit", "status": "completed" if not invalid else "warning",
                "ms": t.ms(),
                "detail": {"checked": len(checked), "valid": len(checked) - len(invalid),
                           "invalid": invalid[:5]}}

    # ---------- 编排 ----------

    def run(self, query: str, *, case_id: Optional[str] = None,
            zone_id: Optional[str] = None,
            bbox: Optional[List[float]] = None, modality: Optional[str] = None,
            body_part: Optional[str] = None, view: Optional[str] = None,
            top_k: int = 6) -> dict:
        started = time.time()
        wf_id = "wf-%d" % int(started * 1000)

        parse = self._parse(query)
        retrieve = self._retrieve(query, top_k=top_k)
        locate = self._locate(case_id, bbox, modality, body_part, view, zone_id=zone_id)
        case_evidence = self._cases.for_case(case_id, zone_id) if case_id else []
        compose = self._compose(retrieve.get("_items") or [], locate, case_evidence)
        audit = self._audit(compose.get("_evidence") or [])

        raw_steps = [parse, retrieve, locate, compose, audit]
        steps = []
        for s in raw_steps:
            clean = {k: v for k, v in s.items() if not k.startswith("_")}
            steps.append(clean)

        ok = all(s["status"] in ("completed", "empty", "skipped", "warning")
                 for s in steps)
        return {
            "workflow_id": wf_id,
            "version": WORKFLOW_VERSION,
            "ok": ok,
            "query": query,
            "steps": steps,
            "evidence": compose.get("_evidence") or [],
            "hint": compose.get("_hint") or "",
            "context": compose.get("_context") or {},
            "total_ms": int((time.time() - started) * 1000),
        }


_WF: Optional[Workflow] = None


def get_workflow(force: bool = False) -> Workflow:
    global _WF
    if _WF is None or force:
        _WF = Workflow()
    return _WF


def run(query: str, **kwargs) -> dict:
    return get_workflow().run(query, **kwargs)


if __name__ == "__main__":
    import json
    q = sys.argv[1] if len(sys.argv) > 1 else "毛玻璃结节"
    print(json.dumps(run(q), ensure_ascii=False, indent=1))
