"""PR2 语音端点单测:/api/ask_stream(SSE)与 /api/asr(移动端)。"""
from __future__ import annotations

import json

import pytest

import app as app_module
from tests.test_ai_service import PNG_1PX_B64


@pytest.fixture
def client(monkeypatch):
    svc = app_module.get_service()
    monkeypatch.setattr(svc, "_minimax", None)  # 强制 Mock 流
    monkeypatch.setattr(svc, "_bailian", None)
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def _sse_events(raw: bytes) -> list[dict]:
    out = []
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def test_health_includes_asr_live(client):
    j = client.get("/api/health").get_json()
    assert "asr_live" in j and j["asr_live"] is False


def test_ask_stream_requires_question(client):
    assert client.post("/api/ask_stream", json={"question": ""}).status_code == 400


def test_ask_stream_rejects_bad_image(client):
    r = client.post("/api/ask_stream",
                    json={"question": "x", "image": "data:image/png;base64,@@bad@@"})
    assert r.status_code == 400


def test_ask_stream_emits_delta_then_done(client):
    r = client.post("/api/ask_stream", json={
        "question": "这是什么", "image": f"data:image/png;base64,{PNG_1PX_B64}"})
    assert r.status_code == 200
    assert r.mimetype == "text/event-stream"
    evs = _sse_events(r.data)
    assert any(e["type"] == "delta" for e in evs)
    assert evs[-1]["type"] == "done"
    assert evs[-1]["source"] == "mock"


def test_asr_unconfigured_returns_503(client):
    r = client.post("/api/asr", data=b"\x00" * 2000,
                    content_type="application/octet-stream")
    assert r.status_code == 503


def test_asr_rejects_tiny_audio(client):
    r = client.post("/api/asr", data=b"\x00" * 10,
                    content_type="application/octet-stream")
    assert r.status_code == 400


def test_asr_happy_path_with_fake_bailian(client, monkeypatch):
    class FakeBailian:
        def transcribe(self, pcm):
            return "你好世界"

    svc = app_module.get_service()
    monkeypatch.setattr(svc, "_bailian", FakeBailian())
    r = client.post("/api/asr", data=b"\x00" * 2000,
                    content_type="application/octet-stream")
    assert r.status_code == 200
    assert r.get_json()["text"] == "你好世界"
