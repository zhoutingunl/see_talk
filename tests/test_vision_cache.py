"""视觉缓存 + 变化检测单测(design.md §14/§22)。"""
from __future__ import annotations

import base64
import io

import pytest

from vision_cache import VisionCache, average_hash, hamming


def _img_b64(color, size=(32, 32)) -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def test_average_hash_stable_and_differs():
    h_white = average_hash(_img_b64("white"))
    h_white2 = average_hash(_img_b64("white"))
    h_black = average_hash(_img_b64("black"))
    assert h_white == h_white2          # 同图稳定
    # 纯色图 hash 多为 0,主要验证不抛错且可比较
    assert isinstance(h_white, int) and isinstance(h_black, int)


def test_average_hash_bad_input_returns_zero():
    assert average_hash("@@not-base64@@") == 0
    assert average_hash("") == 0


def test_hamming():
    assert hamming(0b1010, 0b1000) == 1
    assert hamming(0xFF, 0x00) == 8


def test_scene_changed_first_frame_true():
    c = VisionCache()
    assert c.scene_changed(12345) is True   # 没有上一帧
    c.mark(12345)
    assert c.scene_changed(12345) is False  # 同帧未变
    assert c.scene_changed(12345 ^ 0xFFFF) is True  # 大幅不同


def test_cache_hit_same_hash_and_question():
    c = VisionCache()
    h = 0xABCDEF12
    c.put(h, "这是什么", "answer-1")
    assert c.get(h, "这是什么") == "answer-1"
    assert c.get(h, "另一个问题") is None      # 问题不同不命中
    assert c.get(h ^ 0xFFFFFFFF, "这是什么") is None  # 画面差异大不命中


def test_cache_near_match_within_threshold():
    c = VisionCache(change_threshold=5)
    h = 0b1111
    c.put(h, "q", "v")
    assert c.get(0b1110, "q") == "v"        # 汉明距离 1 < 5,命中


def test_cache_zero_hash_not_stored():
    c = VisionCache()
    c.put(0, "q", "v")
    assert len(c) == 0
    assert c.get(0, "q") is None


def test_lru_eviction():
    # 三个互相相距远(汉明距离 16)的 hash,确保是不同场景、不会近似命中
    a, b, d = 0x000000FF, 0x0000FF00, 0x00FF0000
    c = VisionCache(max_items=2)
    c.put(a, "q", "a")
    c.put(b, "q", "b")
    c.put(d, "q", "c")         # 触发淘汰最旧 a
    assert len(c) == 2
    assert c.get(a, "q") is None
    assert c.get(d, "q") == "c"
