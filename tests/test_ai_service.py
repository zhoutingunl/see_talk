"""AIService 单测:Mock 两个云,只测确定性逻辑(design.md §22)。

不测 AI 答案本身(非确定性),只测"给定 mock 响应,管线行为正确"。
"""
from __future__ import annotations

import base64

import pytest

from ai.service import AIService
from ai.types import ChatMessage, VisionReply

PNG_1PX_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_no_key_falls_back_to_mock():
    """未配置 Key → vision_live 为假,走 Mock 且明确标降级。"""
    svc = AIService()
    svc._minimax = None  # 模拟未就绪
    reply = svc.vision_chat("这是什么？", image_b64=PNG_1PX_B64)
    assert reply.source == "mock"
    assert reply.degraded is True
    assert "这是什么" in reply.text


def test_mock_distinguishes_image_presence():
    svc = AIService()
    svc._minimax = None
    with_img = svc.vision_chat("看到了吗", image_b64=PNG_1PX_B64)
    without = svc.vision_chat("看到了吗")
    assert "已收到一帧画面" in with_img.text
    assert "本轮无画面" in without.text


def test_uses_minimax_when_live():
    """注入伪 MiniMax → 走真实路径并透传 token 计数。"""
    class FakeMiniMax:
        def vision_chat(self, question, **kw):
            return VisionReply(text="书名是《计算机网络》", source="minimax",
                               input_tokens=1300, output_tokens=20)

    svc = AIService()
    svc._minimax = FakeMiniMax()
    reply = svc.vision_chat("这本书叫什么", image_b64=PNG_1PX_B64)
    assert reply.source == "minimax"
    assert reply.input_tokens == 1300
    assert reply.output_tokens == 20


def test_minimax_failure_degrades_to_mock():
    """真实接入抛错 → 不向上抛,降级 Mock(design.md §16)。"""
    class BoomMiniMax:
        def vision_chat(self, question, **kw):
            raise RuntimeError("429 限流")

    svc = AIService()
    svc._minimax = BoomMiniMax()
    reply = svc.vision_chat("随便问问")
    assert reply.source == "mock"


def test_history_is_text_only_passed_through():
    """历史以 ChatMessage(纯文本)透传,不携带图片(design.md §11)。"""
    captured = {}

    class CaptureMiniMax:
        def vision_chat(self, question, **kw):
            captured.update(kw)
            return VisionReply(text="ok", source="minimax")

    svc = AIService()
    svc._minimax = CaptureMiniMax()
    history = [ChatMessage("user", "上一句"), ChatMessage("assistant", "上一答")]
    svc.vision_chat("接着问", history=history)
    assert captured["history"] is history
    assert all(isinstance(m, ChatMessage) for m in captured["history"])


def test_png_fixture_is_valid_base64():
    # 守护测试夹具本身合法,避免假阳性
    assert base64.b64decode(PNG_1PX_B64, validate=True)
