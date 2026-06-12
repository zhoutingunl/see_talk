"""评估框架单测(design.md §17/§22)。打分函数确定性 + 流程用 Fake 注入。"""
from __future__ import annotations

import pytest

import evaluation
from ai.types import VisionReply


# ---------- 打分函数 ----------
def test_char_accuracy():
    assert evaluation.char_accuracy("ERROR 404", "ERROR 404") == 1.0
    assert evaluation.char_accuracy("ERROR 404", "ERROR404") == 1.0   # 忽略空白
    assert evaluation.char_accuracy("abc", "xyz") == 0.0
    assert 0 < evaluation.char_accuracy("ERROR 404", "ERROR 4") < 1
    assert evaluation.char_accuracy("", "") == 1.0
    assert evaluation.char_accuracy("", "x") == 0.0


def test_keyword_score():
    assert evaluation.keyword_score("the code is 404", ["404"]) == 1.0
    assert evaluation.keyword_score("nothing here", ["404"]) == 0.0
    assert evaluation.keyword_score("has TypeError", ["TypeError", "missing"]) == 0.5
    assert evaluation.keyword_score("anything", []) == 1.0
    assert evaluation.keyword_score("CASE insensitive", ["case"]) == 1.0


# ---------- 流程(Fake 注入,render=identity)----------
IDENT = lambda text: text  # noqa: E731


class FakeOcr:
    def extract(self, b64):
        return b64, 95.0, len(b64)   # 完美 OCR:返回原文


def test_evaluate_ocr_perfect():
    r = evaluation.evaluate_ocr(FakeOcr(), render=IDENT)
    assert r["metric"] == "ocr_accuracy"
    assert r["avg"] == 1.0
    assert r["n"] == len(evaluation.OCR_CASES)


def test_evaluate_qa_hits_keywords():
    class FakeSvc:
        def vision_chat(self, q, *, image_b64=None, **kw):
            return VisionReply(text=f"答案参考:{image_b64}", source="minimax")

    r = evaluation.evaluate_qa(FakeSvc(), render=IDENT)
    assert r["metric"] == "conversation_success"
    assert r["avg"] == 1.0          # 答案里含 image_text,覆盖全部关键词


def test_evaluate_qa_miss():
    class BlankSvc:
        def vision_chat(self, q, *, image_b64=None, **kw):
            return VisionReply(text="无关回答", source="minimax")

    r = evaluation.evaluate_qa(BlankSvc(), render=IDENT)
    assert r["avg"] == 0.0


def test_run_all_shape():
    class FakeSvc:
        def vision_chat(self, q, *, image_b64=None, **kw):
            return VisionReply(text=image_b64 or "", source="minimax")

    out = evaluation.run_all(FakeSvc(), FakeOcr(), render=IDENT)
    assert set(out) == {"ocr", "qa"}
    assert out["ocr"]["avg"] == 1.0
