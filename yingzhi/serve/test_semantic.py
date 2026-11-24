#!/usr/bin/env python3
"""语义检索回归测试。

运行：
    python3 -m unittest yingzhi.serve.test_semantic -v
    python3 yingzhi/serve/test_semantic.py

这些用例故意选「grep 会失败、语义检索应命中」的问法：
  * 毛玻璃结节 → 磨玻璃影（别名，字面不同）
  * 甲状腺低回声结节 → 低回声结节（修饰词顺序不同）
  * 肺里有点白 → 磨玻璃影 / 实变（口语改写）

如果哪天有人把 semantic.py 换回 grep，这些用例会先红。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import semantic  # noqa: E402

ROOT = HERE.parents[1]
KB_DATA = ROOT / "kb" / "data"


def _rows(name: str) -> list:
    p = KB_DATA / name
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf8").splitlines() if l.strip()]


class SemanticIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = semantic.get_index(force=True)

    # ---------- 索引完整性 ----------
    def test_stats_match_source_rows(self):
        stats = self.idx.stats()
        expected = sum(len(_rows(n)) for n in (
            "signs.jsonl", "concepts.jsonl", "guidelines.jsonl",
            "cases.jsonl", "claims.jsonl", "paragraphs.jsonl"))
        self.assertEqual(stats["docs"], expected)
        self.assertGreater(stats["features"], 1000)
        self.assertGreater(stats["aliases"], 50)
        self.assertTrue(self.idx.healthy())

    def test_index_is_deterministic(self):
        a = self.idx.search("磨玻璃影", top_k=5)
        b = self.idx.search("磨玻璃影", top_k=5)
        self.assertEqual([x["id"] for x in a["items"]], [x["id"] for x in b["items"]])

    # ---------- 语义命中（grep 会漏） ----------
    def test_alias_variant_hits_sign(self):
        r = self.idx.search("毛玻璃结节", top_k=3)
        ids = [x["id"] for x in r["items"]]
        self.assertIn("SIGN-001", ids)
        self.assertEqual(r["items"][0]["id"], "SIGN-001")
        # 证明这不是子串匹配：库里没有「毛玻璃结节」这个整串。
        self.assertNotIn("毛玻璃结节", (KB_DATA / "signs.jsonl").read_text(encoding="utf8"))

    def test_word_order_variant_hits(self):
        r = self.idx.search("甲状腺低回声结节", top_k=3)
        self.assertEqual(r["items"][0]["id"], "SIGN-058")

    def test_colloquial_query_hits(self):
        r = self.idx.search("肺里有点白", top_k=5)
        ids = {x["id"] for x in r["items"]}
        self.assertTrue(ids & {"SIGN-001", "SIGN-002"}, ids)

    def test_exact_name_ranks_first(self):
        r = self.idx.search("气胸", top_k=3)
        self.assertTrue(r["items"])
        self.assertIn(r["items"][0]["kind"], ("concept", "sign"))

    # ---------- 排序与结构 ----------
    def test_scores_are_sorted_and_bounded(self):
        r = self.idx.search("胸腔积液", top_k=8)
        scores = [x["score"] for x in r["items"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(0.0 <= s <= 1.5 for s in scores))

    def test_empty_query_returns_empty(self):
        r = self.idx.search("   ", top_k=5)
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["items"], [])

    def test_result_has_explainable_fields(self):
        r = self.idx.search("磨玻璃影", top_k=1)
        item = r["items"][0]
        for key in ("kind", "id", "title", "snippet", "score", "matched"):
            self.assertIn(key, item)
        self.assertTrue(item["matched"])

    def test_kind_filter(self):
        r = self.idx.search("磨玻璃影", top_k=10, kinds=["sign"])
        self.assertTrue(r["items"])
        self.assertTrue(all(x["kind"] == "sign" for x in r["items"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
