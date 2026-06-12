"""AIService:接入层统一入口(design.md §9)。

业务代码只依赖本类。内部按配置就绪情况选择真实接入或 Mock,并实现降级:
MiniMax 就绪则用 M3 多模态,否则 Mock;429/超时/网络异常一律降级,绝不向上抛。
"""
from __future__ import annotations

import logging

import config
from .mock import MockClient
from .types import ChatMessage, VisionReply

log = logging.getLogger("seetalk.ai")


class AIService:
    def __init__(self) -> None:
        self._mock = MockClient()
        self._minimax = None
        self._setup_providers()

    def _setup_providers(self) -> None:
        self._minimax = None
        if config.minimax.ready:
            try:
                from .minimax import MiniMaxClient

                self._minimax = MiniMaxClient(config.minimax)
            except Exception as e:  # pragma: no cover - 环境相关
                log.warning("MiniMax 初始化失败,退回 Mock:%s", e)

    def reload(self) -> None:
        """配置变更后热重载接入(无需重启进程)。"""
        self._setup_providers()

    @property
    def vision_live(self) -> bool:
        return self._minimax is not None

    def vision_chat(self, question: str, *, image_b64: str | None = None,
                    media_type: str = "image/jpeg",
                    history: list[ChatMessage] | None = None,
                    system: str | None = None,
                    max_tokens: int = 1024) -> VisionReply:
        """多模态问答:当前帧(可选) + 文本历史 → 回答。失败降级 Mock。"""
        if self._minimax is not None:
            try:
                return self._minimax.vision_chat(
                    question, image_b64=image_b64, media_type=media_type,
                    history=history, system=system, max_tokens=max_tokens)
            except Exception as e:  # 降级,不向上抛(design.md §16)
                log.warning("MiniMax vision_chat 失败,降级 Mock:%s", e)
        return self._mock.vision_chat(
            question, image_b64=image_b64, media_type=media_type,
            history=history, system=system, max_tokens=max_tokens)


_singleton: AIService | None = None


def get_service() -> AIService:
    global _singleton
    if _singleton is None:
        _singleton = AIService()
    return _singleton
