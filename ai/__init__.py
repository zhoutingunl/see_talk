"""AI 接入层:业务代码只依赖 AIService(design.md §9)。"""
from .service import AIService, get_service
from .types import ChatMessage, VisionReply

__all__ = ["AIService", "get_service", "ChatMessage", "VisionReply"]
