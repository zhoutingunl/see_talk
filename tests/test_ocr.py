"""OCR 优先路由单测(design.md §14/§18/§22)。

判定逻辑确定性测试 + 一次真实英文 OCR(tesseract 可用时);
app 路由用 Fake OCR 注入,验证文本场景只发文本、非文本发图。
"""
from __future__ import annotations

import base64
import io

import pytest

import app as app_module
import ocr_service
from ocr_service import OcrService


def _text_img(text: str) -> str:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (420, 140), "white")
    d = ImageDraw.Draw(img)
    font = None
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        try:
            font = ImageFont.truetype(p, 48)
            break
        except Exception:
            continue
    d.text((20, 40), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ---------- 判定逻辑(确定性)----------
def test_is_text_scene_thresholds():
    svc = OcrService(min_chars=8, min_conf=60)
    assert svc.is_text_scene("hello world!", 80, 12) is True
    assert svc.is_text_scene("hi", 90, 2) is False        # 太短
    assert svc.is_text_scene("longish text", 40, 12) is False  # 置信度低


def test_disabled_service_returns_empty():
    svc = OcrService()
    svc.enabled = False
    assert svc.extract("anything") == ("", 0.0, 0)


# ---------- 真实英文 OCR ----------
def test_extract_reads_english():
    svc = OcrService(min_chars=1, min_conf=0)
    if not svc.enabled:
        pytest.skip("本机无 tesseract")
    text, conf, n = svc.extract(_text_img("ERROR 404"))
    assert n >= 1
    up = text.upper()
    assert ("ERROR" in up or "ERRO" in up) or ("404" in up or "40" in up)


# ---------- app 路由(Fake 注入,确定性)----------
class FakeOcr:
    def __init__(self, enabled=True, text="", conf=90.0, nchars=0, text_scene=True):
        self.enabled = enabled
        self._text, self._conf, self._n = text, conf, nchars
        self._scene = text_scene

    def extract(self, image_b64):
        return self._text, self._conf, self._n

    def is_text_scene(self, text, conf, nchars):
        return self._scene


def test_route_no_image_is_text(monkeypatch):
    q, img, route = app_module._route_vision("你好", None)
    assert (img, route) == (None, "text")


def test_route_text_scene_sends_text_only(monkeypatch):
    monkeypatch.setattr(ocr_service, "_ocr",
                        FakeOcr(text="ERROR 404 not found", nchars=18, text_scene=True))
    q, img, route = app_module._route_vision("这是什么报错", "imgdata")
    assert route == "ocr"
    assert img is None                       # 不发图
    assert "ERROR 404 not found" in q        # 文本注入问题


def test_route_non_text_sends_image(monkeypatch):
    monkeypatch.setattr(ocr_service, "_ocr",
                        FakeOcr(text="", nchars=0, text_scene=False))
    q, img, route = app_module._route_vision("这是什么颜色", "imgdata")
    assert route == "image"
    assert img == "imgdata"                   # 发图


def test_route_disabled_ocr_sends_image(monkeypatch):
    monkeypatch.setattr(ocr_service, "_ocr", FakeOcr(enabled=False))
    q, img, route = app_module._route_vision("问", "imgdata")
    assert route == "image" and img == "imgdata"
