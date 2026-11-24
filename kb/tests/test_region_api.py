#!/usr/bin/env python3
"""区域定位后端测试（v2.0 数据口径）：定位分支、侧别映射、引用门禁、数据完整性。

运行：python3 -m unittest kb.tests.test_region_api -v

设计原则：
  * 结构性断言一律从当前数据推导（数量、样本 id 现查），不写死某次快照，
    否则数据一升级测试就成片变红，红的是测试不是产品。
  * 行为断言（定位四分支、侧别映射、门禁）保留，样本换成 v2.0 真实存在的案例。
  * bbox 在库内的存储格式是 [x1, y1, x2, y2]，locate() 的入参是 [left, top, w, h]，
    两者不同，测试分别校验。
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
        self.assertEqual(m["version"], "2.0")
        self.assertEqual(m["counts"]["regions"], len(self.kb.regions))
        self.assertEqual(m["counts"]["claims"], len(self.kb.claims))
        self.assertEqual(
            m["counts"]["cases"],
            len({r["image_id"] for r in self.kb.regions}),
        )

    # ---------- 定位五分支 ----------
    def test_locate_single(self):
        r = self.kb.locate("CASE-006", [0.02, 0.05, 0.30, 0.40])
        self.assertEqual(r["status"], "single")
        self.assertEqual(r["primary"]["region"]["id"], "REG-006-RUL")
        self.assertGreater(r["primary"]["coverage"], 0.9)

    def test_locate_cross(self):
        r = self.kb.locate("CASE-006", [0.05, 0.38, 0.28, 0.16])
        self.assertEqual(r["status"], "cross")
        ids = {c["region"]["id"] for c in r["candidates"]}
        self.assertEqual(ids, {"REG-006-RUL", "REG-006-RLL"})
        self.assertNotIn("primary", r, "跨区不得给出唯一主分区")

    def test_locate_uncovered(self):
        r = self.kb.locate("CASE-006", [0.96, 0.02, 0.03, 0.03])
        self.assertEqual(r["status"], "uncovered")
        self.assertIn("未标注", r["message"])

    def test_locate_too_small(self):
        r = self.kb.locate("CASE-006", [0.30, 0.30, 0.010, 0.010])
        self.assertEqual(r["status"], "too_small")

    def test_locate_diffuse_for_large_lesion(self):
        # 气胸 / 大量积液这类大框不应被拒答，而应给出可能累及的分区
        r = self.kb.locate("CASE-006", [0.0, 0.0, 0.9, 0.95])
        self.assertEqual(r["status"], "diffuse")
        ids = {x["region"]["id"] for x in r["regions"]}
        self.assertIn("REG-006-RUL", ids)
        self.assertIn("REG-006-RLL", ids)
        self.assertGreaterEqual(len(ids), 4)

    @unittest.skip("v2.0 起 120 例全部带 atlas，no_atlas 分支只为防御保留，无样本可测")
    def test_locate_no_atlas(self):
        pass

    def test_locate_clamps_out_of_bounds(self):
        r = self.kb.locate("CASE-006", [-0.2, -0.2, 0.4, 0.4])
        b = r["bbox"]
        self.assertGreaterEqual(b[0], 0.0)
        self.assertGreaterEqual(b[1], 0.0)
        self.assertLessEqual(b[0] + b[2], 1.0001)

    def test_local_atlas_has_no_laterality(self):
        # CASE-011 是局部 atlas（腺体实质 / 病灶区 / 邻近结构），无侧别可言
        r = self.kb.locate("CASE-011", [0.35, 0.32, 0.30, 0.28])
        self.assertEqual(r["status"], "single")
        self.assertEqual(r["primary"]["region"]["id"], "REG-011-LES")
        self.assertEqual(r["primary"]["atlas"]["level"], "local")
        self.assertEqual(r["primary"]["region"]["patient_side"], "mid")
        self.assertEqual(r["primary"]["side_label"], "侧别未知")

    # ---------- 侧别安全 ----------
    def test_laterality_mapping(self):
        expect = {"left": "right", "right": "left", "mid": "mid", "unknown": "unknown"}
        for r in self.kb.regions:
            self.assertIn(r["image_side"], expect, r["id"])
            self.assertEqual(
                expect[r["image_side"]], r["patient_side"],
                "%s: image_side=%s patient_side=%s" % (r["id"], r["image_side"], r["patient_side"]),
            )

    def test_pa_chest_left_is_patient_right(self):
        rul = self.kb.regions_by_id["REG-001-RUL"]
        self.assertEqual(rul["image_side"], "left")
        self.assertEqual(rul["patient_side"], "right")
        self.assertIn("patient_right", rul["laterality_rule"])

    # ---------- 引用门禁 ----------
    def test_gate_counts_consistent(self):
        g = self.kb.meta()["gate"]
        evaluated = self.kb.evaluated_claims()
        self.assertEqual(g["dual"], sum(1 for c in evaluated if c["status"] == "dual"))
        self.assertEqual(g["broken"], sum(1 for c in evaluated if c["status"] == "broken"))
        self.assertEqual(g["single"], sum(1 for c in evaluated if c["status"] == "single"))

    def test_dual_claims_have_both_anchors(self):
        duals = [c for c in self.kb.evaluated_claims() if c["status"] == "dual"]
        self.assertGreater(len(duals), 0)
        for c in duals:
            self.assertIsNotNone(c["spatial"], c["id"])
            self.assertIsNotNone(c["doc"], c["id"])
            self.assertTrue(c["spatial"]["anchor"]["bbox"], c["id"])
            self.assertTrue(c["doc"]["anchor"]["url"], c["id"])

    def test_single_claim_missing_doc(self):
        c = next(x for x in self.kb.evaluated_claims() if x["status"] == "single")
        self.assertEqual(c["status"], "single")
        codes = [p["code"] for p in c["gate"]["problems"]]
        self.assertIn("missing_doc", codes)

    def test_broken_claim_detects_rewritten_excerpt(self):
        c = next(x for x in self.kb.evaluated_claims() if x["status"] == "broken")
        codes = {p["code"] for p in c["gate"]["problems"]}
        self.assertIn("excerpt_mismatch", codes)
        p = next(p for p in c["gate"]["problems"] if p["code"] == "excerpt_mismatch")
        self.assertNotEqual(p["expected"], p["actual"])

    def test_every_claim_points_to_existing_region(self):
        for c in self.kb.claims:
            self.assertIn(c["region_id"], self.kb.regions_by_id, c["id"])
            self.assertEqual(self.kb.regions_by_id[c["region_id"]]["image_id"], c["image_id"], c["id"])

    def test_every_cite_id_present_and_unique(self):
        ids = [x.get("cite_id") for c in self.kb.claims for x in c["cites"]]
        self.assertTrue(all(ids), "存在缺 cite_id 的引用")
        self.assertEqual(len(ids), len(set(ids)), "cite_id 必须全局唯一")

    # ---------- 几何与数据完整性 ----------
    def test_bboxes_normalized_and_valid(self):
        # 库内格式：[x1, y1, x2, y2]，全部落在 [0,1] 且非退化
        for r in self.kb.regions:
            b = r["coords"]
            self.assertEqual(len(b), 4, r["id"])
            x1, y1, x2, y2 = b
            self.assertLess(x1, x2, r["id"])
            self.assertLess(y1, y2, r["id"])
            self.assertGreaterEqual(x1, 0, r["id"])
            self.assertGreaterEqual(y1, 0, r["id"])
            self.assertLessEqual(x2, 1.0001, r["id"])
            self.assertLessEqual(y2, 1.0001, r["id"])

    def test_regions_have_signs(self):
        sign_ids = set(self.kb.signs)
        with_signs = [r for r in self.kb.regions if r.get("sign_ids")]
        self.assertGreaterEqual(len(with_signs), len(self.kb.regions) * 0.25,
                                "带征象的分区比例异常偏低")
        for r in with_signs:
            for sid in r["sign_ids"]:
                self.assertIn(sid, sign_ids, "%s 引用了不存在的征象 %s" % (r["id"], sid))

    def test_atlas_metadata_complete(self):
        for a in self.kb.atlases.values():
            for k in ("id", "name", "level", "laterality_rule", "annotator", "annotated_at", "method"):
                self.assertTrue(a.get(k), "%s 缺少 %s" % (a["id"], k))
            self.assertIn(a["level"], ("global", "local", "none"))

    # ---------- 病例列表 ----------
    def test_case_filters(self):
        all_cases = self.kb.case_list("all")
        locatable = self.kb.case_list("locatable")
        pending = self.kb.case_list("pending")
        self.assertEqual(len(all_cases), len({r["image_id"] for r in self.kb.regions}))
        self.assertEqual(len(all_cases), len(locatable) + len(pending))
        self.assertTrue(all(c["has_atlas"] for c in locatable))
        self.assertFalse(any(c["has_atlas"] for c in pending))

    def test_case_search(self):
        r = self.kb.case_list("all", q="甲状腺")
        self.assertTrue(r)
        self.assertTrue(all("甲状腺" in (c["body_part"] + c["title"]) for c in r))

    def test_case_detail(self):
        d = self.kb.case_detail("CASE-006")
        self.assertIsNotNone(d)
        expected_regions = [r for r in self.kb.regions if r["image_id"] == "CASE-006"]
        expected_claims = [c for c in self.kb.claims if c["image_id"] == "CASE-006"]
        self.assertEqual(len(d["regions"]), len(expected_regions))
        self.assertEqual(len(d["claims"]), len(expected_claims))
        self.assertEqual(sum(d["gate"].values()), len(expected_claims))

    def test_case_detail_missing(self):
        self.assertIsNone(self.kb.case_detail("CASE-999"))

    # ---------- 审计 ----------
    def test_audit_rows_match_claims(self):
        a = self.kb.audit()
        self.assertEqual(len(a["items"]), len(self.kb.claims))
        broken = [x for x in a["items"] if x["status"] == "broken"]
        self.assertEqual(a["gate"]["broken"], len(broken))
        for b in broken:
            self.assertTrue(b["problems"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
