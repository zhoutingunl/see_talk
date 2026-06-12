"""Mock 接入:无 key 也能把项目跑起来(design.md §9)。

产出明确标注为示例/降级,绝不冒充真实结果(诚实性)。
"""
from __future__ import annotations

from .types import ChatMessage, VisionReply


class MockClient:
    def vision_chat(self, question: str, *, image_b64: str | None = None,
                    media_type: str = "image/jpeg",
                    history: list[ChatMessage] | None = None,
                    system: str | None = None,
                    max_tokens: int = 1024) -> VisionReply:
        saw = "（已收到一帧画面）" if image_b64 else "（本轮无画面）"
        text = (f"[mock 示例回复] 我听到你问:{question!r}。{saw} "
                f"配置 MINIMAX_API_KEY 后即接入 M3 真实多模态理解。")
        return VisionReply(text=text, source="mock", degraded=True)
