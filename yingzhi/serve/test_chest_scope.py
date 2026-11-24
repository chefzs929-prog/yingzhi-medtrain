"""胸片专项门控的单测。

背景：反馈里最严重的问题是把乳腺 MLO、腰椎 MRI 套上胸片分区模板。
产品定位收窄为「只做胸部 X 线」后，门控必须在后端生效，不能只靠前端文案。
"""

import sys
import unittest
from pathlib import Path

# 既支持 python3 -m unittest yingzhi.serve.test_chest_scope，
# 也支持直接 python3 yingzhi/serve/test_chest_scope.py（verify_all.sh 的用法）。
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yingzhi.serve import atlas as atlas_mod  # noqa: E402


class ChestGateTest(unittest.TestCase):
    def test_chest_xray_passes(self):
        for args in (("CR", "胸部", "PA"), ("DX", "胸", "PA"),
                     ("XR", "chest", "AP"), ("CR", None, "PA"),
                     (None, "胸部", "LAT")):
            with self.subTest(args=args):
                self.assertEqual(atlas_mod.chest_gate(*args)[0], "chest")

    def test_unknown_is_not_rejected(self):
        state, why = atlas_mod.chest_gate(None, None, None)
        self.assertEqual(state, "unknown")
        self.assertIn("按胸片默认处理", why)

    def test_other_modalities_rejected(self):
        for mod in ("CT", "MR", "US", "MG", "PET"):
            with self.subTest(mod=mod):
                state, why = atlas_mod.chest_gate(mod, "胸部", "PA")
                self.assertEqual(state, "not_chest")
                self.assertIn("不是胸片", why)

    def test_other_body_parts_rejected(self):
        for part in ("乳腺", "腰椎", "头颅", "甲状腺", "腹部", "膝关节"):
            with self.subTest(part=part):
                self.assertEqual(atlas_mod.chest_gate("CR", part, "LAT")[0],
                                 "not_chest")

    def test_non_chest_view_rejected(self):
        for view in ("CT-AXIAL", "MR", "US", "MLO"):
            with self.subTest(view=view):
                self.assertEqual(atlas_mod.chest_gate("CR", "胸部", view)[0],
                                 "not_chest")


class ChestAtlasScopeTest(unittest.TestCase):
    def setUp(self):
        self.t = atlas_mod.AtlasTemplates()

    def test_only_chest_templates_listed(self):
        ids = [a["id"] for a in self.t.list_atlases(only=atlas_mod.CHEST_ATLAS_IDS)]
        self.assertEqual(sorted(ids), sorted(atlas_mod.CHEST_ATLAS_IDS))
        for a in self.t.list_atlases(only=atlas_mod.CHEST_ATLAS_IDS):
            self.assertEqual(a["body_part"], "胸部")

    def test_match_never_returns_other_parts(self):
        for mod, part, view in (("MG", "乳腺", "MLO"), ("MR", "腰椎", "MR"),
                                ("US", "甲状腺", "US"), ("CR", "头颅", "LAT")):
            with self.subTest(part=part):
                got = self.t.match(mod, part, view,
                                   allow_ids=atlas_mod.CHEST_ATLAS_IDS)
                self.assertIsNone(got)

    def test_match_returns_chest_pa(self):
        got = self.t.match("CR", "胸部", "PA", allow_ids=atlas_mod.CHEST_ATLAS_IDS)
        self.assertIsNotNone(got)
        self.assertEqual(got["atlas"]["id"], "ATLAS-CHEST-PA-6")


if __name__ == "__main__":
    unittest.main()
