#!/usr/bin/env python3
"""图文关联 v1 测试：数据完整性、文字分段、侧别映射、接口行为与门禁。"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import kbsearch  # noqa: E402
import sign_links  # noqa: E402


class TestSignLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        kbsearch.build()
        cls.kb = kbsearch.KB()

    def test_counts(self):
        s = self.kb.stats()
        self.assertEqual(s["sign_links"], 12)
        self.assertEqual(s["linked_signs"], 9)
        self.assertEqual(s["linked_images"], 9)
        self.assertEqual(s["linked_regions"], 14)
        self.assertEqual(s["linked_quotes"], 9)

    def test_index_sorted_by_link_count(self):
        items = self.kb.sign_index()
        self.assertEqual(items[0]["id"], "SIGN-002")
        self.assertEqual(items[0]["link_count"], 3)
        self.assertEqual(items[0]["image_count"], 3)

    def test_segments_reconstruct_appearance(self):
        for sign_id in self.kb.links_by_sign:
            detail = self.kb.sign_detail(sign_id)
            rebuilt = "".join(seg["text"] for seg in detail["segments"])
            self.assertEqual(rebuilt, detail["appearance"], sign_id)
            linked = [seg for seg in detail["segments"] if seg["link_ids"]]
            self.assertTrue(linked, sign_id)

    def test_every_link_has_text_and_image_anchor(self):
        signs = {s["id"]: s for s in self.kb.docs if s["_type"] == "sign"}
        for link in self.kb.link_rows:
            self.assertIn(link["quote"], signs[link["sign_id"]]["appearance"], link["id"])
            self.assertTrue(link.get("regions"), link["id"])
            for region in link["regions"]:
                x, y, w, h = region["bbox"]
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertGreater(w, 0)
                self.assertGreater(h, 0)
                self.assertLessEqual(x + w, 1.000001)
                self.assertLessEqual(y + h, 1.000001)
                self.assertTrue(region.get("label"), link["id"])

    def test_laterality_is_explicit(self):
        for link in self.kb.link_rows:
            for region in link["regions"]:
                key = sign_links.rule_key(region["laterality_rule"])
                spec = sign_links.LATERALITY_RULES[key]
                self.assertEqual(region["atlas_level"], spec["atlas"], link["id"])
                mode = spec["mode"]
                if mode == "mirror":
                    self.assertIn(region["image_side"], ("left", "right"), link["id"])
                    self.assertIn(region["patient_side"], ("left", "right"), link["id"])
                    self.assertNotEqual(region["image_side"], region["patient_side"], link["id"])
                else:
                    self.assertIsNone(region["image_side"], link["id"])
                    self.assertIsNone(region["patient_side"], link["id"])

    def test_consolidation_detail(self):
        d = self.kb.sign_detail("SIGN-002")
        self.assertEqual(d["sign"]["name"], "实变")
        self.assertEqual(d["stats"]["links"], 3)
        self.assertEqual(d["stats"]["images"], 3)
        self.assertEqual(d["stats"]["quotes"], 1)
        self.assertEqual(d["stats"]["missing_image"], 0)
        self.assertEqual(d["stats"]["missing_text"], 0)
        self.assertEqual([x["image"]["id"] for x in d["links"]], ["CASE-006", "CASE-015", "CASE-005"])

    def test_unknown_sign(self):
        self.assertIsNone(self.kb.sign_detail("SIGN-999"))

    def test_filter_by_image(self):
        r = self.kb.sign_links(image_id="CASE-020")
        self.assertEqual(r["stats"]["links"], 2)
        self.assertEqual(r["stats"]["signs"], 2)
        self.assertEqual({x["sign_id"] for x in r["items"]}, {"SIGN-001", "SIGN-008"})

    def test_filter_by_sign(self):
        r = self.kb.sign_links(sign_id="SIGN-007")
        self.assertEqual(r["stats"]["links"], 2)
        self.assertEqual(r["stats"]["regions"], 3)

    def test_search_exposes_link_count(self):
        r = self.kb.search("实变")
        top = next(x for x in r["signs"] if x["id"] == "SIGN-002")
        self.assertEqual(top["link_count"], 3)
        self.assertEqual(top["linked_image_count"], 3)

    def test_case_exposes_linked_signs(self):
        case = next(x for x in self.kb.images() if x["id"] == "CASE-020")
        self.assertEqual(case["link_count"], 2)
        self.assertEqual({x["id"] for x in case["linked_signs"]}, {"SIGN-001", "SIGN-008"})

    def test_validation_rejects_bad_quote(self):
        bad = copy.deepcopy(self.kb.link_rows)
        bad[0]["quote"] = "这段文字不在征象原文里"
        errors = sign_links.validate(bad, self.kb.sign_by_id, self.kb.case_by_id, self.kb.sources)
        self.assertTrue(any("quote 不是" in e for e in errors), errors)

    def test_validation_rejects_side_flip(self):
        bad = copy.deepcopy(self.kb.link_rows)
        bad[0]["regions"][0]["patient_side"] = bad[0]["regions"][0]["image_side"]
        errors = sign_links.validate(bad, self.kb.sign_by_id, self.kb.case_by_id, self.kb.sources)
        self.assertTrue(any("不能相同" in e for e in errors), errors)

    def test_segments_reject_overlap(self):
        with self.assertRaises(ValueError):
            sign_links.segments_for(
                "abcdef",
                [{"id": "SL-001", "quote": "abc"}, {"id": "SL-002", "quote": "bcd"}],
            )

    def test_demo_data_shape(self):
        import build_sign_image_demo as demo

        data = demo.build_data(self.kb)
        self.assertEqual(len(data["signs"]), 9)
        self.assertEqual(len(data["links"]), 12)
        self.assertEqual(len(data["images"]), 9)
        self.assertEqual(data["gate"]["quotes"], 9)
        self.assertEqual(data["gate"]["regions"], 14)
        for sign in data["signs"]:
            self.assertEqual("".join(seg["text"] for seg in sign["segments"]), sign["appearance"])
            self.assertTrue(sign["links"])
            self.assertTrue(sign["image_ids"])

    def test_no_forbidden_claims(self):
        bad = ["诊断为", "确诊为", "建议手术", "推荐用药", "就是癌"]
        for link in self.kb.link_rows:
            blob = str(link)
            for word in bad:
                self.assertNotIn(word, blob, link["id"])


if __name__ == "__main__":
    unittest.main()
