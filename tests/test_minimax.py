"""MiniMaxClient 单测:Mock requests,测载荷构造 + 响应解析(design.md §22)。

不打真实网络;验证多模态 block 顺序、历史透传、token 解析、错误处理。
"""
from __future__ import annotations

import pytest

import ai.minimax as mm
from ai.minimax import MiniMaxClient, MiniMaxError
from ai.types import ChatMessage
from config import MiniMaxConfig
from tests.test_ai_service import PNG_1PX_B64

CFG = MiniMaxConfig(api_key="test-key", llm_model="MiniMax-M3")


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _patch_post(monkeypatch, status=200, payload=None):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json
        return FakeResp(status, payload or {
            "content": [{"type": "text", "text": "回答正文"}],
            "usage": {"input_tokens": 1311, "output_tokens": 17},
        })

    monkeypatch.setattr(mm.requests, "post", fake_post)
    return captured


def test_requires_key():
    with pytest.raises(MiniMaxError):
        MiniMaxClient(MiniMaxConfig(api_key=""))


def test_vision_chat_builds_image_then_text_block(monkeypatch):
    cap = _patch_post(monkeypatch)
    reply = MiniMaxClient(CFG).vision_chat("这是什么", image_b64=PNG_1PX_B64)

    assert cap["url"].endswith("/v1/messages")
    assert cap["headers"]["x-api-key"] == "test-key"
    content = cap["body"]["messages"][-1]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["data"] == PNG_1PX_B64
    assert content[1] == {"type": "text", "text": "这是什么"}
    assert reply.source == "minimax"
    assert (reply.input_tokens, reply.output_tokens) == (1311, 17)
    assert reply.text == "回答正文"


def test_vision_chat_text_only_has_no_image_block(monkeypatch):
    cap = _patch_post(monkeypatch)
    MiniMaxClient(CFG).vision_chat("纯文本")
    content = cap["body"]["messages"][-1]["content"]
    assert [b["type"] for b in content] == ["text"]


def test_history_and_system_passed(monkeypatch):
    cap = _patch_post(monkeypatch)
    hist = [ChatMessage("user", "前问"), ChatMessage("assistant", "前答")]
    MiniMaxClient(CFG).vision_chat("续问", history=hist, system="你是助手")
    msgs = cap["body"]["messages"]
    assert msgs[0] == {"role": "user", "content": "前问"}
    assert msgs[1] == {"role": "assistant", "content": "前答"}
    assert cap["body"]["system"] == "你是助手"


def test_non_200_raises(monkeypatch):
    _patch_post(monkeypatch, status=429, payload={"error": "rate limited"})
    with pytest.raises(MiniMaxError):
        MiniMaxClient(CFG).vision_chat("x")
