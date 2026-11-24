"""ask_bank 引用一致性回归。

检查：
  - 正常 / 受限 / 未提及分区不挂指南锚点（避免“未见异常”引“正常报告怎么写”）；
  - 异常分区引该区逐区原文（source=claim）；
  - “不是 / 有”结论不引正常报告条款；
  - claim 引用的病例号与条目病例号一致，quote 非空。
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BANK = ROOT / "kb/data/ask_bank.json"


class AskCitationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = json.loads(BANK.read_text(encoding="utf8"))
        cls.items = cls.bank["items"]

    def test_zone_citations(self):
        bad = []
        for it in self.items:
            if it.get("kind") != "zone":
                continue
            status = (it.get("region") or {}).get("status")
            cit = it.get("citation")
            if status in ("normal", "limited", "unmentioned"):
                if cit is not None:
                    bad.append(f"{it['qid']} {status} 不应有 citation")
            elif status == "abnormal":
                ok = cit and (
                    cit.get("source") == "claim"
                    or (cit.get("kp_id") and cit.get("relevance") == "strong")
                )
                if not ok:
                    bad.append(f"{it['qid']} abnormal 应引强相关条款或 claim，实际 {cit}")
        self.assertFalse(bad, "\n".join(bad[:10]))

    def test_topic_conclusion_matches_citation(self):
        bad = []
        for it in self.items:
            if it.get("kind") != "topic":
                continue
            ans = it.get("answer") or ""
            cit = it.get("citation")
            if ans.startswith(("不是", "有。")):
                if not cit or cit.get("source") != "claim":
                    bad.append(f"{it['qid']} 结论={ans[:8]} citation={cit}")
        self.assertFalse(bad, "\n".join(bad[:10]))

    def test_claim_citation_identity(self):
        bad = []
        for it in self.items:
            cit = it.get("citation")
            if not cit or cit.get("source") != "claim":
                continue
            if cit.get("case_id") != it.get("case_id"):
                bad.append(f"{it['qid']} citation case={cit.get('case_id')} item case={it.get('case_id')}")
            if not (cit.get("quote") or "").strip():
                bad.append(f"{it['qid']} claim quote 为空")
            reg = it.get("region") or {}
            if reg.get("status") == "abnormal" and reg.get("zone_id") != cit.get("zone_id"):
                bad.append(f"{it['qid']} 区域 {reg.get('zone_id')} 与引用分区 {cit.get('zone_id')} 不一致")
        self.assertFalse(bad, "\n".join(bad[:10]))

    def test_no_normal_guideline_on_negative_answer(self):
        bad = []
        for it in self.items:
            cit = it.get("citation") or {}
            if cit.get("kp_id") == "GL-NOR-01" and (it.get("answer") or "").startswith(("不是", "有。")):
                bad.append(it["qid"])
        self.assertFalse(bad, f"负/异常结论引了正常报告条款：{bad[:10]}")


if __name__ == "__main__":
    unittest.main()
