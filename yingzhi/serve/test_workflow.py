#!/usr/bin/env python3
"""本地五步工作流回归测试。

运行：
    python3 -m unittest yingzhi.serve.test_workflow -v
    python3 yingzhi/serve/test_workflow.py

验收点：
  * 五步齐全且顺序固定（parse/retrieve/locate/compose/audit）；
  * retrieve 真的命中库内词条，不是空跑；
  * 有 case_id + bbox 时 locate 真的落到具体分区；
  * audit 对证据 id 做存在性自证；
  * 整个返回可 JSON 序列化（能直接写进 workflow.json 回放）。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import workflow  # noqa: E402


class WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wf = workflow.get_workflow(force=True)

    def test_five_steps_in_order(self):
        r = self.wf.run("毛玻璃结节是什么")
        names = [s["step"] for s in r["steps"]]
        self.assertEqual(names, list(workflow.STEPS))
        self.assertTrue(r["ok"])

    def test_retrieve_hits_evidence(self):
        r = self.wf.run("毛玻璃结节是什么")
        ret = next(s for s in r["steps"] if s["step"] == "retrieve")
        self.assertEqual(ret["status"], "completed")
        self.assertGreater(ret["detail"]["top"][0]["score"], 0.1)
        self.assertIn("SIGN-001", [it["id"] for it in r["evidence"]])

    def test_locate_skipped_without_bbox(self):
        r = self.wf.run("气胸")
        loc = next(s for s in r["steps"] if s["step"] == "locate")
        self.assertEqual(loc["status"], "skipped")
        self.assertEqual(loc["detail"]["reason"], "no_case_or_bbox")

    def test_locate_with_case_and_bbox(self):
        r = self.wf.run("右肺上野有什么", case_id="CASE-006",
                        bbox=[0.02, 0.05, 0.30, 0.40])
        loc = next(s for s in r["steps"] if s["step"] == "locate")
        self.assertEqual(loc["status"], "completed")
        self.assertEqual(loc["detail"]["source"], "region_kb")
        self.assertEqual(loc["detail"]["primary"], "REG-006-RUL")

    def test_audit_reports_valid_ids(self):
        r = self.wf.run("胸腔积液")
        aud = next(s for s in r["steps"] if s["step"] == "audit")
        self.assertEqual(aud["status"], "completed")
        self.assertEqual(aud["detail"]["invalid"], [])
        self.assertGreaterEqual(aud["detail"]["checked"], 1)

    def test_compose_hint_contains_ids(self):
        r = self.wf.run("磨玻璃影")
        self.assertIn("[SIGN-001]", r["hint"])
        self.assertIn("不要编造", r["hint"])

    def test_payload_is_json_serializable(self):
        r = self.wf.run("甲状腺低回声结节")
        dumped = json.dumps(r, ensure_ascii=False)
        self.assertIn(r["workflow_id"], dumped)
        # 内部临时字段（_items/_hint）不应泄漏到可回放载荷里。
        # 注意加引号：detail 里的 region_hint 含 "_hint" 子串，不能误判。
        self.assertNotIn('"_items"', dumped)
        self.assertNotIn('"_hint"', dumped)

    def test_empty_evidence_still_completes(self):
        r = self.wf.run("qqqqzzzz")
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["evidence"]), 0)
        self.assertIn("证据不足", r["hint"])

    def test_case_zone_pins_current_case(self):
        """当前病例必须置顶，且不能把 CASE-006 的问题引到同源的 CASE-202。"""
        r = self.wf.run("右肺中野有什么问题？", case_id="CASE-006", zone_id="RML")
        self.assertTrue(r["evidence"], "当前病例证据不能为空")
        first = r["evidence"][0]
        self.assertEqual(first.get("case_id"), "CASE-006")
        self.assertEqual(first.get("region_id"), "RML")
        self.assertIn("右肺中野", first.get("title") or "")
        # 其他病例的 claim / case 不应出现在证据区
        for it in r["evidence"]:
            if it.get("kind") == "case":
                self.assertEqual(it["id"], "CASE-006")
            if it.get("kind") == "claim" and str(it["id"]).startswith("CLM-"):
                self.assertTrue(str(it["id"]).startswith("CLM-006-"))
        self.assertIn("E1 必须写当前病例 CASE-006", r["hint"])
        # 当前分区挂载的征象词条也要在证据里，供 L1 使用
        self.assertIn("SIGN-002", [it["id"] for it in r["evidence"]])

    def test_case_zone_uses_claim_when_available(self):
        r = self.wf.run("右肺下野有什么问题？", case_id="CASE-006", zone_id="RLL")
        self.assertEqual(r["evidence"][0]["id"], "CLM-006-RLL")
        self.assertEqual(r["evidence"][0]["region_id"], "RLL")

    def test_locate_with_case_zone_without_bbox(self):
        r = self.wf.run("右肺中野有什么问题？", case_id="CASE-006", zone_id="RML")
        loc = next(s for s in r["steps"] if s["step"] == "locate")
        self.assertEqual(loc["status"], "completed")
        self.assertEqual(loc["detail"]["source"], "case_zone")
        self.assertEqual(loc["detail"]["region_id"], "RML")


if __name__ == "__main__":
    unittest.main(verbosity=2)
