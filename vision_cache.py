"""视觉缓存 + 变化检测(design.md §14 省钱核心)。

感知哈希(average hash):
- 变化检测:与上一帧汉明距离 < 阈值 → 画面没变。
- 视觉缓存:同画面(同问题)命中缓存,不再调用云,直接复用结果。

纯标准库 + Pillow,无外部服务,便于单测。
"""
from __future__ import annotations

import base64
import io
from collections import OrderedDict


def average_hash(image_b64: str, size: int = 8) -> int:
    """图片(base64)→ 64 位 average hash。失败返回 0(视作无法比较)。"""
    try:
        from PIL import Image

        raw = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(raw)).convert("L").resize((size, size))
        px = list(img.getdata())
    except Exception:
        return 0
    avg = sum(px) / len(px)
    bits = 0
    for i, p in enumerate(px):
        if p >= avg:
            bits |= (1 << i)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class VisionCache:
    """LRU 视觉缓存 + 变化检测。key = (画面 hash 近似, 问题)。"""

    def __init__(self, max_items: int = 128, change_threshold: int = 5):
        self.max_items = max_items
        self.change_threshold = change_threshold
        self._store: OrderedDict[tuple[int, str], object] = OrderedDict()
        self._last_hash: int | None = None

    def scene_changed(self, image_hash: int) -> bool:
        """与上一帧比较:画面是否发生变化(用于跳过重复分析)。"""
        if image_hash == 0:
            return True  # 无法比较,保守视为已变化
        if self._last_hash is None:
            return True
        return hamming(image_hash, self._last_hash) >= self.change_threshold

    def mark(self, image_hash: int) -> None:
        if image_hash:
            self._last_hash = image_hash

    def _match_key(self, image_hash: int, question: str) -> tuple[int, str] | None:
        """找一个"画面足够相似 + 问题相同"的缓存键。"""
        if image_hash == 0:
            return None
        for (h, q) in self._store:
            if q == question and hamming(h, image_hash) < self.change_threshold:
                return (h, q)
        return None

    def get(self, image_hash: int, question: str):
        key = self._match_key(image_hash, question)
        if key is None:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, image_hash: int, question: str, value) -> None:
        if image_hash == 0:
            return  # 不缓存无法比较的画面
        key = (image_hash, question)
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self.max_items:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        return len(self._store)
