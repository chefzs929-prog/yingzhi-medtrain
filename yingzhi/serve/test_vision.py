"""影像入口的离线测试：认图与取框，不联网。"""
import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vision  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(HERE))
IMAGES = os.path.join(WORKSPACE, "kb", "images")


class BBoxTest(unittest.TestCase):
    def test_plain_json(self):
        text = '结论：右上肺见斑片影。\n依据：SIGN-001。\n缺失：无。\n边界：教学用。\n{"bbox":[0.2,0.3,0.5,0.6]}'
        bbox, raw, stripped = vision.extract_bbox(text)
        self.assertEqual(bbox, [0.2, 0.3, 0.3, 0.3])
        self.assertEqual(raw, [0.2, 0.3, 0.5, 0.6])
        self.assertNotIn("bbox", stripped)
        self.assertTrue(stripped.endswith("教学用。"))

    def test_fenced_json(self):
        text = '结论：X\n```json\n{"bbox": [100, 200, 300, 400]}\n```'
        bbox, _, stripped = vision.extract_bbox(text)
        self.assertEqual(bbox, [0.1, 0.2, 0.2, 0.2])
        self.assertNotIn("```", stripped)

    def test_swapped_corners(self):
        text = '{"bbox":[0.6,0.7,0.2,0.3]}'
        bbox, _, _ = vision.extract_bbox(text)
        self.assertEqual(bbox, [0.2, 0.3, 0.4, 0.4])

    def test_no_bbox(self):
        bbox, raw, stripped = vision.extract_bbox("结论：无框。")
        self.assertIsNone(bbox)
        self.assertIsNone(raw)
        self.assertEqual(stripped, "结论：无框。")

    def test_degenerate_box_rejected(self):
        bbox, _, _ = vision.extract_bbox('{"bbox":[0.3,0.3,0.3,0.5]}')
        self.assertIsNone(bbox, "零宽框不能当成定位结果")

    def test_last_box_wins(self):
        text = '{"bbox":[0.1,0.1,0.2,0.2]}\n结论：以最后为准\n{"bbox":[0.4,0.4,0.6,0.6]}'
        bbox, _, _ = vision.extract_bbox(text)
        self.assertEqual(bbox, [0.4, 0.4, 0.2, 0.2])


class ImageIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = vision.ImageIndex(IMAGES)
        cls.idx.build()

    def test_index_built(self):
        # 209 个文件里只有 89 张唯一图像：共享视角会让多例指向同一张图
        self.assertGreater(len(self.idx), 50, "kb/images 应能建出索引")

    def test_match_library_image(self):
        path = os.path.join(IMAGES, "case-001.jpg")
        with open(path, "rb") as fh:
            data = fh.read()
        url = "data:image/jpeg;base64," + base64.b64encode(data).decode()
        self.assertIn("CASE-001", self.idx.match_all(url))

    def test_match_bytes(self):
        path = os.path.join(IMAGES, "case-002.jpg")
        with open(path, "rb") as fh:
            self.assertIn("CASE-002", self.idx.match_all(fh.read()))

    def test_unknown_image(self):
        self.assertEqual(self.idx.match_all(b"\x89PNG\r\n\x1a\n not a library image"), [])

    def test_bad_input_is_none(self):
        self.assertEqual(self.idx.match_all("http://example.com/a.jpg"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
