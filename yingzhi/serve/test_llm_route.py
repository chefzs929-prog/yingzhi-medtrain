#!/usr/bin/env python3
"""llm.py 的离线自检：不联网、不消耗 token。

覆盖：配置缺失禁用、路由选择、引用过滤、检索命中。
    python3 yingzhi/serve/test_llm_route.py
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm  # noqa: E402


def cfg(kind, model):
    return llm.ModelConfig(kind, "https://example.invalid/v1", "k", model)


class FakeClient:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def chat(self, cfg_, messages):
        self.calls.append((cfg_.model, messages))
        return self.text


class RouterTest(unittest.TestCase):
    def test_no_key_disables(self):
        for k in list(os.environ):
            if k.startswith("YZ_LLM_"):
                os.environ.pop(k)
        self.assertIsNone(llm.build_from_env())

    def test_route_by_image(self):
        r = llm.Router(cfg("vision", "qwen3-vl-plus"), cfg("text", "deepseek-chat"))
        self.assertEqual(r.pick(True).model, "qwen3-vl-plus")
        self.assertEqual(r.pick(False).model, "deepseek-chat")

    def test_fallback_when_vision_missing(self):
        r = llm.Router(llm.ModelConfig("vision", "", "", ""), cfg("text", "deepseek-chat"))
        self.assertEqual(r.pick(True).model, "deepseek-chat")

    def test_fallback_when_text_missing(self):
        r = llm.Router(cfg("vision", "qwen3-vl-plus"), llm.ModelConfig("text", "", "", ""))
        self.assertEqual(r.pick(False).model, "qwen3-vl-plus")


class AnswerTest(unittest.TestCase):
    def setUp(self):
        self.retriever = llm.Retriever()

    def test_retrieve_hits_sign(self):
        ctx = self.retriever.search("磨玻璃影")
        self.assertTrue(ctx["signs"], "应命中磨玻璃影词条")

    def test_drops_unknown_ids(self):
        text = "结论：SIGN-001 与 CLM-999 同时出现。\n依据：SIGN-001。\n缺失：无。\n边界：教学用。"
        client = FakeClient(text)
        ans = llm.Answerer(
            llm.Router(cfg("vision", "v"), cfg("text", "t")),
            self.retriever, client)
        ctx = self.retriever.search("磨玻璃影")
        cites = ans._cites(ctx, text)
        self.assertTrue(all(c["id"] != "CLM-999" for c in cites))

    def test_route_uses_vision_with_image(self):
        client = FakeClient("结论：X\n依据：Y\n缺失：Z\n边界：教学用。")
        ans = llm.Answerer(
            llm.Router(cfg("vision", "qwen3-vl-plus"), cfg("text", "deepseek-chat")),
            self.retriever, client)
        events = []
        res = ans.ask("这张图是什么部位", lambda k, p: events.append((k, p)),
                      image=b"\xff\xd8\xff\xd9")
        self.assertEqual(res["route"], "vision")
        self.assertEqual(res["model"], "qwen3-vl-plus")
        self.assertEqual(client.calls[0][0], "qwen3-vl-plus")
        kinds = [e[0] for e in events]
        self.assertIn("trace", kinds)

    def test_route_uses_text_without_image(self):
        client = FakeClient("结论：X\n依据：Y\n缺失：Z\n边界：教学用。")
        ans = llm.Answerer(
            llm.Router(cfg("vision", "qwen3-vl-plus"), cfg("text", "deepseek-chat")),
            self.retriever, client)
        res = ans.ask("磨玻璃影是什么", lambda *a: None)
        self.assertEqual(res["route"], "text")
        self.assertEqual(res["model"], "deepseek-chat")

    def test_dropped_ids_reported(self):
        client = FakeClient("结论：见 CLM-999。\n依据：无。\n缺失：无。\n边界：教学用。")
        ans = llm.Answerer(
            llm.Router(cfg("vision", "v"), cfg("text", "t")),
            self.retriever, client)
        res = ans.ask("磨玻璃影", lambda *a: None)
        self.assertIn("CLM-999", res["dropped_ids"])

    def test_trace_detail_reports_real_hits(self):
        """trace 必须报真实命中数：曾出现「检索命中 9 条，trace 记 0 条」的假记录。"""
        client = FakeClient("结论：X\n依据：SIGN-001。\n缺失：无。\n边界：教学用。")
        ans = llm.Answerer(
            llm.Router(cfg("vision", "v"), cfg("text", "t")),
            self.retriever, client)
        events = []
        res = ans.ask("磨玻璃影", lambda k, p: events.append((k, p)))
        td = res["trace_detail"]
        self.assertGreater(td["hits"], 0)
        self.assertEqual(td["hits"], td["signs"] + td["claims"])
        spans = [p for k, p in events if k == "trace"]
        self.assertTrue(spans, "必须发 trace 事件")
        self.assertEqual(spans[0]["stage"], "kb_retrieve")
        self.assertEqual(spans[0]["hits"], td["hits"])
        self.assertTrue(spans[0]["hit"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
