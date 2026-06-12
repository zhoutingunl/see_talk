"""AIService 的 ASR(移动端=百炼)单测:就绪判断与降级语义(design.md §13/§22)。"""
from __future__ import annotations

import pytest

from ai.service import AIService, ASRUnavailable, TTSUnavailable


def test_asr_unavailable_when_no_bailian():
    svc = AIService()
    svc._bailian = None
    assert svc.asr_live is False
    with pytest.raises(ASRUnavailable):
        svc.transcribe(b"\x00" * 1000)


def test_transcribe_delegates_to_bailian():
    class FakeBailian:
        def __init__(self):
            self.got = None

        def transcribe(self, pcm):
            self.got = pcm
            return "识别结果"

    svc = AIService()
    svc._bailian = FakeBailian()
    assert svc.asr_live is True
    assert svc.transcribe(b"abc") == "识别结果"
    assert svc._bailian.got == b"abc"


def test_tts_unavailable_when_no_bailian():
    svc = AIService()
    svc._bailian_tts = None
    assert svc.tts_live is False
    with pytest.raises(TTSUnavailable):
        svc.synthesize("你好")


def test_synthesize_delegates_to_bailian_tts():
    class FakeTTS:
        def synthesize(self, text):
            return b"AUDIO:" + text.encode()

    svc = AIService()
    svc._bailian_tts = FakeTTS()
    assert svc.tts_live is True
    assert svc.synthesize("hi") == b"AUDIO:hi"
