#!/usr/bin/env python3
"""知识库最小测试：检索命中、关联约束、越界行为、合规门禁。"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import kbsearch  # noqa: E402
import online_search  # noqa: E402
from dual import assess  # noqa: E402


class TestKB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        kbsearch.build()
        cls.kb = kbsearch.KB()

    def test_document_counts(self):
        s = self.kb.stats()
        self.assertEqual(s["signs"], 60)
        self.assertEqual(s["standards"], 10)
        self.assertEqual(s["cases"], 32)
        self.assertEqual(s["guidelines"], 47)

    def test_ggo_hit(self):
        r = self.kb.search("磨玻璃影")
        self.assertEqual(r["signs"][0]["id"], "SIGN-001")
        self.assertEqual(r["confidence"], "high")

    def test_thyroid_hit_and_case(self):
        r = self.kb.search("甲状腺低回声结节")
        self.assertEqual(r["signs"][0]["id"], "SIGN-058")
        self.assertTrue(any(c["id"] == "CASE-011" for c in r["cases"]))

    def test_standard_not_cross_part(self):
        r = self.kb.search("甲状腺低回声结节")
        names = [s["name"] for s in r["standards"]]
        self.assertIn("ACR TI-RADS", names)
        self.assertNotIn("Fleischner Society 偶发肺结节随访建议", names)

    def test_double_duct(self):
        r = self.kb.search("双管征")
        self.assertEqual(r["signs"][0]["id"], "SIGN-024")

    def test_out_of_scope(self):
        r = self.kb.search("今天天气怎么样")
        self.assertTrue(r["empty"] or r["confidence"] == "low")

    def test_modality_filter(self):
        r = self.kb.search("结节", modality="MR")
        self.assertTrue(all("MR" in (x["modality"] or []) for x in r["signs"]))

    def test_images_filter(self):
        items = self.kb.images(modality="CT")
        self.assertTrue(items)
        self.assertTrue(all("CT" in x["modality"] for x in items))

    def test_license_whitelist(self):
        allowed = {"CC0", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0",
                   "CC BY-SA 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0", "Public domain"}
        for c in self.kb.images():
            self.assertIn(c["license"], allowed, c["id"])

    def test_sources_registered(self):
        for d in self.kb.docs:
            if d["_type"] == "sign":
                for sid in d.get("sources", []):
                    self.assertIn(sid, self.kb.sources, f"{d['id']} -> {sid}")

    def test_no_forbidden_claims(self):
        bad = ["诊断为", "确诊为", "建议手术", "推荐用药", "就是癌"]
        for d in self.kb.docs:
            blob = json.dumps(d, ensure_ascii=False)
            for w in bad:
                self.assertNotIn(w, blob, d["id"])

    def test_dual_aligned_tirads(self):
        r = assess(self.kb, "甲状腺结节 TR4 1.6cm")
        self.assertEqual(r["alignment"]["level"], "aligned")
        self.assertEqual(r["alignment"]["best_id"], "GL-TIRADS-03")
        self.assertIn("最大径 ≥ 1.5 cm", r["alignment"]["matched"])

    def test_dual_partial_missing_category(self):
        r = assess(self.kb, "甲状腺低回声结节")
        self.assertEqual(r["alignment"]["level"], "partial")
        self.assertTrue(any("分类等级" in m for m in r["alignment"]["missing"]))

    def test_dual_fleischner_size(self):
        r = assess(self.kb, "肺实性结节 7mm")
        self.assertEqual(r["alignment"]["level"], "aligned")
        self.assertEqual(r["alignment"]["best_id"], "GL-FLEISCHNER-02")

    def test_dual_out_of_scope(self):
        r = assess(self.kb, "今天天气怎么样")
        self.assertEqual(r["alignment"]["level"], "insufficient")

    def test_dual_imaging_line_scope(self):
        r = assess(self.kb, "甲状腺结节 TR4 1.6cm")
        parts = {s["body_part"] for s in r["imaging"]["signs"]}
        self.assertTrue(parts <= {"甲状腺"}, parts)

    def test_guidelines_registered(self):
        std = {d["id"] for d in self.kb.docs if d["_type"] == "standard"}
        for d in self.kb.docs:
            if d["_type"] == "guideline":
                self.assertIn(d["standard_id"], std, d["id"])
                self.assertTrue(d["source_url"].startswith("http"), d["id"])

    def test_cases_grouped(self):
        groups = {g["id"] for g in self.kb.group_defs}
        for c in self.kb.images():
            self.assertIn(c["group_id"], groups, c["id"])

    def test_group_signs_exist(self):
        sign_ids = {d["id"] for d in self.kb.docs if d["_type"] == "sign"}
        for g in self.kb.group_defs:
            for sid in g.get("sign_ids", []):
                self.assertIn(sid, sign_ids, g["id"])

    def test_groups_have_items(self):
        for g in self.kb.groups():
            self.assertGreaterEqual(g["count"], 1, g["id"])
            self.assertTrue(g["criteria"], g["id"])

    def test_taxonomy_two_levels(self):
        tax = self.kb.taxonomy()
        self.assertEqual(tax["totals"]["regions"], 5)
        self.assertEqual(tax["totals"]["conditions"], 12)
        self.assertEqual(tax["totals"]["images"], 32)
        region_ids = {r["id"] for r in tax["regions"]}
        seen = set()
        for r in tax["regions"]:
            for c in r["conditions"]:
                self.assertIn(c["id"], {g["id"] for g in self.kb.group_defs})
                self.assertNotIn(c["id"], seen, "影像组重复归属部位：" + c["id"])
                seen.add(c["id"])
        self.assertEqual(seen, {g["id"] for g in self.kb.group_defs})

    def test_every_group_has_region_and_query(self):
        for g in self.kb.group_defs:
            self.assertTrue(g.get("region_id"), g["id"])
            self.assertTrue(g.get("search_query"), g["id"])

    def test_images_region_filter(self):
        chest = self.kb.images(region="REG-CHEST")
        self.assertEqual(len(chest), 18)
        for c in chest:
            self.assertEqual(self.kb.group_region[c["group_id"]], "REG-CHEST")
        self.assertEqual(len(self.kb.groups(region="REG-BREAST")), 1)

    def test_online_license_gate(self):
        self.assertTrue(online_search.license_ok("CC BY-SA 4.0")[0])
        self.assertTrue(online_search.license_ok("CC0")[0])
        self.assertFalse(online_search.license_ok("CC BY-NC 4.0")[0])
        self.assertFalse(online_search.license_ok("")[0])

    def test_online_privacy_flags(self):
        flags = online_search.privacy_flags("CT 2021-03-04 病例号 1234567 A.B.")
        self.assertIn("含日期", flags)
        self.assertIn("含编号", flags)
        self.assertIn("疑似姓名缩写", flags)
        self.assertEqual(online_search.privacy_flags("ground-glass opacity"), [])

    def test_online_queue_blocks_nc(self):
        r = online_search.queue_candidate({"page_url": "https://example.org/x", "license": "CC BY-NC 4.0"})
        self.assertFalse(r["queued"])
        self.assertEqual(online_search.queue_candidate({})["queued"], False)

    def test_online_search_switch(self):
        import os
        old = os.environ.get("KB_ONLINE_SEARCH")
        os.environ["KB_ONLINE_SEARCH"] = "0"
        try:
            r = online_search.search("thyroid nodule", use_cache=False)
        finally:
            if old is None:
                os.environ.pop("KB_ONLINE_SEARCH", None)
            else:
                os.environ["KB_ONLINE_SEARCH"] = old
        self.assertFalse(r["enabled"])
        self.assertTrue(r["hint"])

    def test_compliance_script_passes(self):
        import compliance_check
        self.assertEqual(compliance_check.main(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
