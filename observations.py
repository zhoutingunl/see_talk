"""连续分析模式(design.md §5 Story5 会议辅助 / §12 连续模式)。

开启后前端每 3~5 秒抓一帧 → /api/observe 客观描述并累积;
/api/summary 把累积观察交给 M3 汇总成会议纪要。

成本对齐 §14:每会话做变化检测,画面没变就跳过(不重复分析、不调云)。
内存存储(Demo 量级足够);多用户可平滑换 DB。
"""
from __future__ import annotations

from vision_cache import hamming


class ObservationStore:
    def __init__(self, max_per_session: int = 60, change_threshold: int = 5):
        self.max = max_per_session
        self.change_threshold = change_threshold
        self._obs: dict[str, list[str]] = {}
        self._last_hash: dict[str, int] = {}

    def scene_changed(self, session_id: str, image_hash: int) -> bool:
        """画面相对该会话上一帧是否变化(变化才值得分析)。"""
        if image_hash == 0:
            return True
        prev = self._last_hash.get(session_id)
        if prev is None:
            return True
        return hamming(image_hash, prev) >= self.change_threshold

    def mark(self, session_id: str, image_hash: int) -> None:
        if image_hash:
            self._last_hash[session_id] = image_hash

    def add(self, session_id: str, text: str) -> None:
        lst = self._obs.setdefault(session_id, [])
        lst.append(text)
        while len(lst) > self.max:
            lst.pop(0)

    def get(self, session_id: str) -> list[str]:
        return list(self._obs.get(session_id, []))

    def clear(self, session_id: str) -> None:
        self._obs.pop(session_id, None)
        self._last_hash.pop(session_id, None)


_store: ObservationStore | None = None


def get_store() -> ObservationStore:
    global _store
    if _store is None:
        _store = ObservationStore()
    return _store


SUMMARY_PROMPT = (
    "以下是按时间顺序对画面的连续观察记录,请汇总成简洁的会议/场景纪要,"
    "提炼要点与变化,不要逐条复述:\n\n"
)


def summarize(svc, observations: list[str]) -> str:
    """把观察记录交给 LLM 汇总(纯文本,不带图,省 token)。"""
    if not observations:
        return "（暂无观察记录）"
    joined = "\n".join(f"- {o}" for o in observations)
    reply = svc.vision_chat(SUMMARY_PROMPT + joined)
    return reply.text
