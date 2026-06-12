"""流式多模态单测:MiniMax SSE 解析 + AIService 流式降级(design.md §16/§22)。"""
from __future__ import annotations

import json

import pytest

import ai.minimax as mm
from ai.minimax import MiniMaxClient, MiniMaxError
from ai.service import AIService
from config import MiniMaxConfig

CFG = MiniMaxConfig(api_key="test-key", llm_model="MiniMax-M3")

SSE_LINES = [
    'data: {"type":"message_start","message":{"usage":{"input_tokens":210}}}',
    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"你好"}}',
    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"世界"}}',
    'data: {"type":"message_delta","usage":{"output_tokens":12}}',
    "data: [DONE]",
]


class FakeStreamResp:
    def __init__(self, lines, status=200):
        self._lines = lines
        self.status_code = status
        self.text = "err"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self, decode_unicode=False):
        yield from self._lines


def test_minimax_stream_parses_deltas_and_usage(monkeypatch):
    monkeypatch.setattr(mm.requests, "post",
                        lambda *a, **k: FakeStreamResp(SSE_LINES))
    evs = list(MiniMaxClient(CFG).vision_chat_stream("问", image_b64="x"))
    deltas = [e["text"] for e in evs if e["type"] == "delta"]
    done = [e for e in evs if e["type"] == "done"][0]
    assert deltas == ["你好", "世界"]
    assert (done["input_tokens"], done["output_tokens"]) == (210, 12)
    assert done["source"] == "minimax"


def test_minimax_stream_sets_stream_flag(monkeypatch):
    cap = {}

    def fake_post(url, headers=None, json=None, timeout=None, stream=None):
        cap["json"] = json
        cap["stream"] = stream
        return FakeStreamResp(SSE_LINES)

    monkeypatch.setattr(mm.requests, "post", fake_post)
    list(MiniMaxClient(CFG).vision_chat_stream("问"))
    assert cap["json"]["stream"] is True
    assert cap["stream"] is True


def test_minimax_stream_non_200_raises(monkeypatch):
    monkeypatch.setattr(mm.requests, "post",
                        lambda *a, **k: FakeStreamResp([], status=500))
    with pytest.raises(MiniMaxError):
        list(MiniMaxClient(CFG).vision_chat_stream("问"))


def test_service_stream_passes_through_real():
    class FakeMM:
        def vision_chat_stream(self, q, **kw):
            yield {"type": "delta", "text": "片段"}
            yield {"type": "done", "source": "minimax",
                   "input_tokens": 1, "output_tokens": 2}

    svc = AIService()
    svc._minimax = FakeMM()
    evs = list(svc.vision_chat_stream("问"))
    assert evs[0]["text"] == "片段"
    assert evs[-1]["source"] == "minimax"


def test_service_stream_falls_back_to_mock():
    svc = AIService()
    svc._minimax = None
    evs = list(svc.vision_chat_stream("看到什么", image_b64="x"))
    assert evs[-1]["type"] == "done"
    assert evs[-1]["source"] == "mock"
    joined = "".join(e["text"] for e in evs if e["type"] == "delta")
    assert "已收到一帧画面" in joined


def test_service_stream_no_mock_after_partial():
    """真实流已吐内容后中途异常,不再追加 Mock(避免混入)。"""
    class HalfThenBoom:
        def vision_chat_stream(self, q, **kw):
            yield {"type": "delta", "text": "半句"}
            raise RuntimeError("断流")

    svc = AIService()
    svc._minimax = HalfThenBoom()
    evs = list(svc.vision_chat_stream("问"))
    assert evs == [{"type": "delta", "text": "半句"}]
