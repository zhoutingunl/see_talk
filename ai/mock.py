"""Mock 接入:无 key 也能把项目跑起来(design.md §9)。

产出明确标注为示例/降级,绝不冒充真实结果(诚实性)。
"""
from __future__ import annotations

from collections.abc import Iterator

from .types import ChatMessage, VisionReply


class MockClient:
    def _mock_text(self, question: str, image_b64: str | None) -> str:
        saw = "（已收到一帧画面）" if image_b64 else "（本轮无画面）"
        return (f"[mock 示例回复] 我听到你问:{question!r}。{saw} "
                f"配置 MINIMAX_API_KEY 后即接入 M3 真实多模态理解。")

    def vision_chat(self, question: str, *, image_b64: str | None = None,
                    media_type: str = "image/jpeg",
                    history: list[ChatMessage] | None = None,
                    system: str | None = None,
                    max_tokens: int = 1024) -> VisionReply:
        return VisionReply(text=self._mock_text(question, image_b64),
                           source="mock", degraded=True)

    def vision_chat_stream(self, question: str, *, image_b64: str | None = None,
                           media_type: str = "image/jpeg",
                           history: list[ChatMessage] | None = None,
                           system: str | None = None,
                           max_tokens: int = 1024) -> Iterator[dict]:
        text = self._mock_text(question, image_b64)
        # 按标点切片,保留"流式分片"形状供前端首句优先联调
        buf = ""
        for ch in text:
            buf += ch
            if ch in "。！？!?,， ":
                yield {"type": "delta", "text": buf}
                buf = ""
        if buf:
            yield {"type": "delta", "text": buf}
        yield {"type": "done", "source": "mock", "degraded": True,
               "input_tokens": 0, "output_tokens": 0}
