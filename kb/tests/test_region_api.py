#!/usr/bin/env python3
"""v1.1 区域定位后端测试：定位分支、侧别映射、引用门禁、数据完整性。

运行：cd kb && python3 -m unittest tests.test_region_api -v
"""
import sys
import unittest
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "scripts"))

from serve_region import RegionKB  # noqa: E402


class RegionLocateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = RegionKB()

    # ---------- 元数据 ----------
    def test_meta_counts(self):
        m = self.kb.meta()
        self.assertEqual(m["version"], "1.1")
        self.assertEqual(m["counts"]["cases"], 32)
        self.assertEqual(m["counts"]["locatable_cases"], 3)
        self.assertEqual(m["counts"]["atlases"], 2)
        self.assertEqual(m["counts"]["regions"], 21)
        self.assertEqual(m["counts"]["claims"], 7)

    # ---------- 定位四分支 ----------
    def test_locate_single(self):
        r = self.kb.locate("CASE-006", [0.14, 0.40, 0.26, 0.16])
        self.assertEqual(r["status"], "single")
        self.assertEqual(r["primary"]["region"]["id"], "REG-006-RML")
        self.assertGreater(r["primary"]["coverage"], 0.9)
        self.assertGreaterEqual(len(r["primary"]["claims"]), 3)

    def test_locate_cross(self):
        r = self.kb.locate("CASE-006", [0.12, 0.50, 0.30, 0.12])
        self.assertEqual(r["status"], "cross")
        ids = [c["region"]["id"] for c in r["candidates"]]
        self.assertEqual(set(ids), {"REG-006-RML", "REG-006-RLL"})
        self.assertLess(r["gap"], 0.15)
        self.assertNotIn("primary", r, "跨区不得给出唯一主分区")

    def test_locate_uncovered(self):
        r = self.kb.locate("CASE-006", [0.96, 0.02, 0.03, 0.03])
        self.assertEqual(r["status"], "uncovered")
        self.assertIn("未标注", r["message"])

    def test_locate_too_small(self):
        r = self.kb.locate("CASE-006", [0.30, 0.30, 0.010, 0.010])
        self.assertEqual(r["status"], "too_small")

    def test_locate_too_large(self):
        r = self.kb.locate("CASE-006", [0.0, 0.0, 1.0, 1.0])
        self.assertEqual(r["status"], "too_large")

    def test_locate_no_atlas(self):
        r = self.kb.locate("CASE-002", [0.2, 0.2, 0.2, 0.2])
        self.assertEqual(r["status"], "no_atlas")
        self.assertIn("未标注", r["message"])

    def test_locate_clamps_out_of_bounds(self):
        r = self.kb.locate("CASE-006", [-0.2, -0.2, 0.4, 0.4])
        b = r["bbox"]
        self.assertGreaterEqual(b[0], 0.0)
        self.assertGreaterEqual(b[1], 0.0)
        self.assertLessEqual(b[0] + b[2], 1.0001)

    def test_thyroid_is_local_and_has_no_laterality(self):
        r = self.kb.locate("CASE-011", [0.35, 0.32, 0.30, 0.28])
        self.assertEqual(r["status"], "single")
        self.assertEqual(r["primary"]["region"]["id"], "REG-011-CENTER")
        self.assertEqual(r["primary"]["atlas"]["level"], "local")
        self.assertEqual(r["primary"]["region"]["patient_side"], "unknown")
        self.assertEqual(r["primary"]["side_label"], "侧别未知")

    # ---------- 侧别安全 ----------
    def test_laterality_mapping(self):
        expect = {"left": "right", "right": "left", "midline": "midline", "unknown": "unknown"}
        for r in self.kb.regions:
            self.assertEqual(
                expect[r["image_side"]], r["patient_side"],
                "%s: image_side=%s patient_side=%s" % (r["id"], r["image_side"], r["patient_side"]),
            )

    def test_pa_chest_left_is_patient_right(self):
        rml = self.kb.regions_by_id["REG-001-RML"]
        self.assertEqual(rml["image_side"], "left")
        self.assertEqual(rml["patient_side"], "right")
        self.assertIn("image_left = patient_right", rml["laterality_rule"])

    # ---------- 引用门禁 ----------
    def test_gate_counts(self):
        g = self.kb.meta()["gate"]
        self.assertEqual(g, {"dual": 5, "single": 1, "broken": 1})

    def test_dual_claims_have_both_anchors(self):
        for c in self.kb.evaluated_claims():
            if c["status"] != "dual":
                continue
            self.assertIsNotNone(c["spatial"], c["id"])
            self.assertIsNotNone(c["doc"], c["id"])
            self.assertTrue(c["spatial"]["anchor"]["bbox"], c["id"])
            self.assertTrue(c["doc"]["anchor"]["url"], c["id"])

    def test_single_claim_missing_spatial(self):
        c = next(x for x in self.kb.evaluated_claims() if x["id"] == "CLM-004")
        self.assertEqual(c["status"], "single")
        self.assertIsNone(c["spatial"])
        codes = [p["code"] for p in c["gate"]["problems"]]
        self.assertIn("missing_spatial", codes)

    def test_broken_claim_detects_rewritten_excerpt(self):
        c = next(x for x in self.kb.evaluated_claims() if x["id"] == "CLM-007")
        self.assertEqual(c["status"], "broken")
        p = next(p for p in c["gate"]["problems"] if p["code"] == "excerpt_mismatch")
        self.assertNotEqual(p["expected"], p["actual"])
        # 摘录确实被改成了 1.0 cm，而原文是 1.5 cm
        self.assertIn("1.0 cm", c["doc"]["anchor"]["excerpt"])
        self.assertNotIn("1.5 cm 时可考虑", c["doc"]["anchor"]["excerpt"])

    def test_every_claim_points_to_existing_region(self):
        for c in self.kb.claims:
            self.assertIn(c["region_id"], self.kb.regions_by_id, c["id"])
            self.assertEqual(self.kb.regions_by_id[c["region_id"]]["image_id"], c["image_id"], c["id"])

    def test_every_cite_id_unique(self):
        ids = [x["cite_id"] for c in self.kb.claims for x in c["cites"]]
        self.assertEqual(len(ids), len(set(ids)))

    # ---------- 几何与数据完整性 ----------
    def test_bboxes_normalized_and_valid(self):
        for r in self.kb.regions:
            b = r["coords"]
            self.assertEqual(len(b), 4, r["id"])
            self.assertGreater(b[2], 0, r["id"])
            self.assertGreater(b[3], 0, r["id"])
            self.assertGreaterEqual(b[0], 0, r["id"])
            self.assertGreaterEqual(b[1], 0, r["id"])
            self.assertLessEqual(b[0] + b[2], 1.0001, r["id"])
            self.assertLessEqual(b[1] + b[3], 1.0001, r["id"])

    def test_regions_have_signs(self):
        for r in self.kb.regions:
            self.assertTrue(r.get("sign_ids"), r["id"])
            for sid in r["sign_ids"]:
                self.assertIn(sid, self.kb.signs, "%s 引用了不存在的征象 %s" % (r["id"], sid))

    def test_atlas_metadata_complete(self):
        for a in self.kb.atlases.values():
            for k in ("id", "name", "level", "laterality_rule", "annotator", "annotated_at", "method"):
                self.assertTrue(a.get(k), "%s 缺少 %s" % (a["id"], k))
            self.assertIn(a["level"], ("global", "local", "none"))

    # ---------- 病例列表 ----------
    def test_case_filters(self):
        self.assertEqual(len(self.kb.case_list("all")), 32)
        locatable = self.kb.case_list("locatable")
        self.assertEqual(len(locatable), 3)
        self.assertTrue(all(c["has_atlas"] for c in locatable))
        pending = self.kb.case_list("pending")
        self.assertEqual(len(pending), 29)
        self.assertFalse(any(c["has_atlas"] for c in pending))

    def test_case_search(self):
        r = self.kb.case_list("all", q="甲状腺")
        self.assertTrue(r)
        self.assertTrue(all("甲状腺" in (c["body_part"] + c["title"]) for c in r))

    def test_case_detail(self):
        d = self.kb.case_detail("CASE-006")
        self.assertIsNotNone(d)
        self.assertEqual(len(d["regions"]), 8)
        self.assertEqual(len(d["claims"]), 3)
        self.assertEqual(d["gate"], {"dual": 2, "single": 1, "broken": 0})

    def test_case_detail_missing(self):
        self.assertIsNone(self.kb.case_detail("CASE-999"))

    # ---------- 审计 ----------
    def test_audit_rows_match_claims(self):
        a = self.kb.audit()
        self.assertEqual(len(a["items"]), 7)
        self.assertEqual(a["gate"]["broken"], 1)
        broken = [x for x in a["items"] if x["status"] == "broken"]
        self.assertEqual(broken[0]["claim_id"], "CLM-007")
        self.assertTrue(broken[0]["problems"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
