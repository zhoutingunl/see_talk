"""BailianTTSClient 单测:Mock WebSocket,验证 CosyVoice run-task 协议(design.md §22)。"""
from __future__ import annotations

import json
import sys
import types

import pytest

from ai.bailian_tts import BailianTTSClient, BailianTTSError
from config import BailianConfig

CFG = BailianConfig(api_key="test-key", tts_model="cosyvoice-v2",
                    tts_voice="longxiaochun_v2")


class FakeWS:
    def __init__(self, script):
        self.script = list(script)
        self.sent = []
        self.closed = False

    def send(self, msg):
        self.sent.append(msg)

    def recv(self):
        if not self.script:
            raise RuntimeError("脚本耗尽")
        return self.script.pop(0)

    def close(self):
        self.closed = True


def _patch_ws(monkeypatch, ws):
    monkeypatch.setitem(sys.modules, "websocket",
                        types.SimpleNamespace(create_connection=lambda *a, **k: ws))


def _started():
    return json.dumps({"header": {"event": "task-started"}})


def _finished():
    return json.dumps({"header": {"event": "task-finished"}})


def test_requires_key():
    with pytest.raises(BailianTTSError):
        BailianTTSClient(BailianConfig(api_key=""))


def test_synthesize_protocol_and_audio(monkeypatch):
    ws = FakeWS([_started(), b"\x11\x22", b"\x33", _finished()])
    _patch_ws(monkeypatch, ws)

    audio = BailianTTSClient(CFG).synthesize("你好世界")

    run = json.loads(ws.sent[0])
    assert run["header"]["action"] == "run-task"
    assert run["payload"]["task"] == "tts"
    assert run["payload"]["function"] == "SpeechSynthesizer"
    assert run["payload"]["model"] == "cosyvoice-v2"
    assert run["payload"]["parameters"]["voice"] == "longxiaochun_v2"

    cont = json.loads(ws.sent[1])
    assert cont["header"]["action"] == "continue-task"
    assert cont["payload"]["input"]["text"] == "你好世界"
    assert json.loads(ws.sent[2])["header"]["action"] == "finish-task"

    assert audio == b"\x11\x22\x33"      # 二进制音频帧按序拼接
    assert ws.closed is True


def test_task_failed_raises(monkeypatch):
    ws = FakeWS([json.dumps({"header": {"event": "task-failed",
                                        "error_message": "voice not found"}})])
    _patch_ws(monkeypatch, ws)
    with pytest.raises(BailianTTSError, match="voice not found"):
        BailianTTSClient(CFG).synthesize("x")


def test_failed_during_audio(monkeypatch):
    ws = FakeWS([_started(), b"\x01",
                 json.dumps({"header": {"event": "task-failed",
                                        "error_message": "boom"}})])
    _patch_ws(monkeypatch, ws)
    with pytest.raises(BailianTTSError):
        BailianTTSClient(CFG).synthesize("x")
