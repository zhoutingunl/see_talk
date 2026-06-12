"""Dashboard 与缓存/对账集成单测(design.md §15/§22)。"""
from __future__ import annotations

import pytest

import app as app_module
from ai.types import VisionReply
from tests.test_ai_service import PNG_1PX_B64


@pytest.fixture
def client(monkeypatch):
    svc = app_module.get_service()
    monkeypatch.setattr(svc, "_minimax", None)
    monkeypatch.setattr(svc, "_bailian", None)
    app_module._cache = app_module.vision_cache.VisionCache()  # 隔离缓存
    app_module.metrics.get_store().reset()
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_dashboard_page(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert b"Dashboard" in r.data


def test_metrics_endpoint_shape(client):
    j = client.get("/api/metrics").get_json()
    for k in ("turns", "savings_rate", "cache_hit_rate", "baseline_input_tokens",
              "latency_ms", "cost_estimate_cny", "events"):
        assert k in j


def test_ask_records_a_turn(client):
    before = client.get("/api/metrics").get_json()["turns"]
    client.post("/api/ask", json={"question": "你好"})
    after = client.get("/api/metrics").get_json()["turns"]
    assert after == before + 1


def test_cache_hit_on_repeated_image_question(client, monkeypatch):
    """同图同问第二次应命中缓存(真实 M3 路径用 Fake 注入)。"""
    class FakeMM:
        def __init__(self):
            self.calls = 0

        def vision_chat(self, q, **kw):
            self.calls += 1
            return VisionReply(text="缓存测试答案", source="minimax",
                               input_tokens=500, output_tokens=20)

    svc = app_module.get_service()
    fake = FakeMM()
    monkeypatch.setattr(svc, "_minimax", fake)

    body = {"question": "这是什么", "image": f"data:image/png;base64,{PNG_1PX_B64}"}
    r1 = client.post("/api/ask", json=body).get_json()
    r2 = client.post("/api/ask", json=body).get_json()

    assert r1["cache_hit"] is False
    assert r2["cache_hit"] is True          # 第二次命中缓存
    assert fake.calls == 1                   # 云只被调用一次
    assert r2["tokens"]["input"] == 0        # 命中不计 token(体现节省)
    m = client.get("/api/metrics").get_json()
    assert m["cache_hits"] >= 1
