#!/usr/bin/env python3
"""范围拒答回归：治疗/预后/操作/非胸部/过宽问句必须拒答。

提问页（ask-core.js）、DeepWorks 技能（ask_engine.py）、课堂影像问答
（student-lab.js）必须共用同一套边界。本测试锁住 Python 侧，
JS 侧由 kb/scripts/crosscheck.py 在安装 Node 后逐条比对。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kb" / "scripts"))

import ask_engine  # noqa: E402


class ScopeReasonTest(unittest.TestCase):
    def test_treatment_questions_are_out_of_scope(self):
        for q in [
            "这个气胸需要做胸腔闭式引流吗",
            "气胸怎么治疗",
            "需要吃什么药",
            "要不要手术",
            "需要住院吗",
            "能不能做穿刺抽液",
        ]:
            with self.subTest(q=q):
                self.assertEqual(ask_engine.scope_reason(q), "治疗 / 预后 / 操作建议")

    def test_prognosis_is_out_of_scope(self):
        for q in ["肺癌能活多久", "这个病人预后怎么样", "严重吗", "会死吗"]:
            with self.subTest(q=q):
                self.assertTrue(ask_engine.scope_reason(q))

    def test_non_chest_is_out_of_scope(self):
        for q in ["乳腺癌筛查", "头颅 CT 有没有出血", "膝关节退变"]:
            with self.subTest(q=q):
                self.assertTrue(ask_engine.non_chest_reason(q) or ask_engine.scope_reason(q))

    def test_too_broad_is_out_of_scope(self):
        for q in ["胸片", "片子", "这个"]:
            with self.subTest(q=q):
                self.assertEqual(ask_engine.too_broad_reason(q), "问句过于宽泛")

    def test_definition_questions_stay_in_scope(self):
        for q in [
            "气胸在胸片上怎么找",
            "气胸和胸腔积液怎么区分",
            "磨玻璃影是什么",
            "诊断标准是什么",
        ]:
            with self.subTest(q=q):
                self.assertEqual(ask_engine.scope_reason(q), "")


class BankScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = ask_engine.Bank(ROOT / "kb" / "data" / "ask_bank.json")

    def test_treatment_refused_not_answered(self):
        for q in ["这个气胸需要做胸腔闭式引流吗", "气胸怎么治疗"]:
            with self.subTest(q=q):
                r = self.bank.answer(q, "CASE-006")
                self.assertEqual(r["status"], "refusal")
                self.assertIn("不能回答", r["markdown"])
                self.assertIn("治疗 / 预后 / 操作建议", r["markdown"])
                # 不能出现病例级“本片没有……”的答案
                self.assertNotIn("本片没有", r["markdown"])

    def test_normal_zone_question_still_answers(self):
        r = self.bank.answer("右肺中野有什么问题", "CASE-006")
        self.assertEqual(r["status"], "answer")
        self.assertIn("右肺中野", r["markdown"])

    def test_refusal_has_alternatives(self):
        r = self.bank.answer("气胸怎么治疗", "CASE-006")
        self.assertIn("你可以问", r["markdown"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
