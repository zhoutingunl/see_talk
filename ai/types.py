"""AI 接入层数据结构。保持纯数据,便于序列化与测试。"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    """文本历史消息。历史只留文本(含视觉摘要),不回传旧图(design.md §11)。"""

    role: Role
    content: str

    def to_api(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class VisionReply:
    """一次多模态问答的结果。

    source 标明来源:minimax(真实) / mock(降级示例),诚实性见 design.md §9。
    token 计数用于成本对账 Dashboard(design.md §14/§15)。
    """

    text: str
    source: Literal["minimax", "mock"] = "minimax"
    input_tokens: int = 0
    output_tokens: int = 0
    degraded: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
