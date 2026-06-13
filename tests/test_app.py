"""Flask 路由单测:用 Mock 后端,验证 /api/ask 闭环与入参校验。"""
from __future__ import annotations

import pytest

import app as app_module
from ai.types import VisionReply
from tests.test_ai_service import PNG_1PX_B64


@pytest.fixture
def client(monkeypatch):
    # 强制走 Mock 路径,测试不依赖任何真实 Key/网络
    svc = app_module.get_service()
    monkeypatch.setattr(svc, "_minimax", None)
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_index_ok(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"SeeTalk" in r.data


def test_health_reports_status(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "vision_live" in r.get_json()


def test_ask_requires_question(client):
    r = client.post("/api/ask", json={"question": "  "})
    assert r.status_code == 400


def test_ask_rejects_bad_base64_image(client):
    r = client.post("/api/ask", json={"question": "x", "image": "data:image/jpeg;base64,@@notb64@@"})
    assert r.status_code == 400


def test_ask_happy_path_with_data_url(client):
    r = client.post("/api/ask", json={
        "question": "这是什么？",
        "image": f"data:image/png;base64,{PNG_1PX_B64}",
    })
    assert r.status_code == 200
    j = r.get_json()
    assert j["source"] == "mock"
    assert j["degraded"] is True
    assert "tokens" in j


def test_ask_works_without_image(client):
    r = client.post("/api/ask", json={"question": "纯文本提问"})
    assert r.status_code == 200
    assert r.get_json()["answer"]


def test_answer_system_adds_asr_hint_only_for_voice():
    assert "语音识别" in app_module._answer_system({"voice": True})
    assert "语音识别" not in app_module._answer_system({"voice": False})
    assert "语音识别" not in app_module._answer_system({})
    # 两种情况都保留基础约束
    assert "实时视觉对话助手" in app_module._answer_system({"voice": True})


def test_ensure_cert_uses_existing_files(monkeypatch, tmp_path):
    c = tmp_path / "c.pem"
    k = tmp_path / "k.pem"
    c.write_text("cert")
    k.write_text("key")
    monkeypatch.setenv("SEETALK_CERT", str(c))
    monkeypatch.setenv("SEETALK_KEY", str(k))
    assert app_module.ensure_cert() == (str(c), str(k))


def test_parse_image_handles_raw_and_dataurl():
    b64, mt = app_module._parse_image(f"data:image/webp;base64,{PNG_1PX_B64}")
    assert b64 == PNG_1PX_B64 and mt == "image/webp"
    b64, mt = app_module._parse_image(PNG_1PX_B64)
    assert b64 == PNG_1PX_B64 and mt == "image/jpeg"
    assert app_module._parse_image(None) == (None, "image/jpeg")
