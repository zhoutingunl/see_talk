"""会话级多轮上下文(design.md §11)。

按 session_id 维护最近 N 轮文本历史(deque)。**历史只存文本(问题 + 回答),不存图片**——
只有当前轮带图(省 token,见 §14);指代消解("它/那个/这本书")靠这段文本 + 当前帧完成。
N = config.plan.text_history_turns(默认 10),映射 PlanConfig 付费档。

历史在"读(取上文)→ 调模型 → 写(追加本轮)"之间始终成对,故读取时永远以 user 起、成对交替。
"""
from __future__ import annotations

from collections import deque

import config
from ai.types import ChatMessage


class SessionStore:
    def __init__(self, turns: int | None = None):
        self.turns = turns if turns is not None else config.plan.text_history_turns
        self._data: dict[str, deque] = {}

    def _dq(self, sid: str) -> deque:
        dq = self._data.get(sid)
        if dq is None:
            dq = deque(maxlen=self.turns * 2)   # 每轮 = user + assistant 两条
            self._data[sid] = dq
        return dq

    def history(self, sid: str) -> list[ChatMessage]:
        """该会话最近 N 轮的文本历史(供注入到下一次调用)。"""
        return list(self._dq(sid))

    def append(self, sid: str, question: str, answer: str) -> None:
        dq = self._dq(sid)
        dq.append(ChatMessage("user", question))
        dq.append(ChatMessage("assistant", answer))

    def clear(self, sid: str) -> None:
        self._data.pop(sid, None)


_store: SessionStore | None = None


def get_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
