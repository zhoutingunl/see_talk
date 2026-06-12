"""本地 OCR(Tesseract)——OCR 优先路由的判定(design.md §14)。

纯文本场景(报错/英文/代码/文档)→ 本地 OCR 出文本 → 只发文本给 M3,省掉整图 token。
非文本场景 → 仍发降分整图。

无 tesseract 时 enabled=False,路由自动退化为"始终发图",不影响功能。
免费、本地运行,不产生云成本。
"""
from __future__ import annotations

import base64
import io
import logging
import os

log = logging.getLogger("seetalk.ocr")


class OcrService:
    def __init__(self, min_chars: int = 8, min_conf: float = 60.0,
                 lang: str | None = None):
        self.min_chars = min_chars
        self.min_conf = min_conf
        self.enabled = self._detect()
        self.lang = lang or self._pick_lang()

    @staticmethod
    def _detect() -> bool:
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            return True
        except Exception as e:  # pragma: no cover - 环境相关
            log.info("Tesseract 不可用,OCR 优先路由退化为始终发图:%s", e)
            return False

    @staticmethod
    def _pick_lang() -> str:
        """优先 中文+英文;缺中文包则退英文。装 chi_sim.traineddata 即自动启用。"""
        try:
            import pytesseract

            langs = set(pytesseract.get_languages(config=""))
            parts = [x for x in ("chi_sim", "eng") if x in langs]
            return "+".join(parts) or "eng"
        except Exception:  # pragma: no cover - 环境相关
            return "eng"

    def extract(self, image_b64: str) -> tuple[str, float, int]:
        """返回 (文本, 平均置信度, 字符数)。失败/未启用返回空。"""
        if not self.enabled:
            return "", 0.0, 0
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(base64.b64decode(image_b64)))
            data = pytesseract.image_to_data(
                img, lang=self.lang, output_type=pytesseract.Output.DICT)
            words, confs = [], []
            for t, c in zip(data["text"], data["conf"]):
                t = t.strip()
                try:
                    c = float(c)
                except (TypeError, ValueError):
                    c = -1.0
                if t and c >= 0:
                    words.append(t)
                    confs.append(c)
            text = " ".join(words)
            conf = sum(confs) / len(confs) if confs else 0.0
            return text, round(conf, 1), len(text)
        except Exception as e:  # pragma: no cover - 环境相关
            log.warning("OCR 失败:%s", e)
            return "", 0.0, 0

    def is_text_scene(self, text: str, conf: float, nchars: int) -> bool:
        """够长且够清晰才判为文本场景(可路由成只发文本)。"""
        return nchars >= self.min_chars and conf >= self.min_conf


_ocr: OcrService | None = None


def get_ocr() -> OcrService:
    global _ocr
    if _ocr is None:
        _ocr = OcrService(lang=os.getenv("OCR_LANG") or None)
    return _ocr
