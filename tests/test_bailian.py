"""BailianASRClient 单测:Mock WebSocket,验证 run-task 协议与结果解析(design.md §22)。

不打真实网络;用脚本化的 FakeWS 回放服务端事件。
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from ai.bailian import BailianASRClient, BailianError
from config import BailianConfig

CFG = BailianConfig(api_key="test-key", asr_model="paraformer-realtime-v2")


class FakeWS:
    def __init__(self, script: list[str]):
        self.script = list(script)
        self.sent: list[str] = []
        self.binary: list[bytes] = []
        self.closed = False

    def send(self, msg):
        self.sent.append(msg)

    def send_binary(self, b):
        self.binary.append(b)

    def recv(self):
        if not self.script:
            raise RuntimeError("脚本耗尽")
        return self.script.pop(0)

    def close(self):
        self.closed = True


def _patch_ws(monkeypatch, ws: FakeWS):
    monkeypatch.setitem(sys.modules, "websocket",
                        types.SimpleNamespace(create_connection=lambda *a, **k: ws))


def _ev(event, **payload_output):
    body = {"header": {"event": event}}
    if payload_output:
        body["payload"] = {"output": {"sentence": payload_output}}
    return json.dumps(body)


def test_requires_key():
    with pytest.raises(BailianError):
        BailianASRClient(BailianConfig(api_key=""))


def test_transcribe_happy_path(monkeypatch):
    ws = FakeWS([
        _ev("task-started"),
        _ev("result-generated", text="你好", sentence_end=False),
        _ev("result-generated", text="你好世界", sentence_end=True),
        _ev("task-finished"),
    ])
    _patch_ws(monkeypatch, ws)

    client = BailianASRClient(CFG, chunk_bytes=4)
    text = client.transcribe(b"\x01\x02\x03\x04\x05\x06\x07")

    # run-task 报文正确
    run = json.loads(ws.sent[0])
    assert run["header"]["action"] == "run-task"
    assert run["payload"]["model"] == "paraformer-realtime-v2"
    assert run["payload"]["parameters"] == {"format": "pcm", "sample_rate": 16000}
    # 音频按 chunk_bytes 分帧发送(7 字节 / 4 → 2 帧)
    assert ws.binary == [b"\x01\x02\x03\x04", b"\x05\x06\x07"]
    # finish-task 报文
    assert json.loads(ws.sent[1])["header"]["action"] == "finish-task"
    # 多句拼接结果
    assert text == "你好世界"
    assert ws.closed is True


def test_multi_sentence_accumulates(monkeypatch):
    ws = FakeWS([
        _ev("task-started"),
        _ev("result-generated", text="第一句", sentence_end=True),
        _ev("result-generated", text="第二句", sentence_end=True),
        _ev("task-finished"),
    ])
    _patch_ws(monkeypatch, ws)
    assert BailianASRClient(CFG).transcribe(b"\x00" * 100) == "第一句第二句"


def test_unfinished_sentence_flushed_on_finish(monkeypatch):
    ws = FakeWS([
        _ev("task-started"),
        _ev("result-generated", text="没结束就收尾", sentence_end=False),
        _ev("task-finished"),
    ])
    _patch_ws(monkeypatch, ws)
    assert BailianASRClient(CFG).transcribe(b"\x00" * 50) == "没结束就收尾"


def test_task_failed_raises(monkeypatch):
    ws = FakeWS([json.dumps({"header": {"event": "task-failed",
                                        "error_message": "rate limited"}})])
    _patch_ws(monkeypatch, ws)
    with pytest.raises(BailianError, match="rate limited"):
        BailianASRClient(CFG).transcribe(b"\x00" * 50)


def test_binary_server_frames_ignored(monkeypatch):
    """服务端偶发二进制帧应被跳过,不影响解析。"""
    ws = FakeWS([
        b"\x00\x01",                       # 杂二进制帧
        _ev("task-started"),
        _ev("result-generated", text="ok", sentence_end=True),
        _ev("task-finished"),
    ])
    _patch_ws(monkeypatch, ws)
    assert BailianASRClient(CFG).transcribe(b"\x00" * 50) == "ok"
