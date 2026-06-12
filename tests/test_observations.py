"""连续分析模式单测(design.md §5/§12/§22):观察存储 + 变化检测 + 汇总 + 端点。"""
from __future__ import annotations

import pytest

import app as app_module
import observations
from ai.types import VisionReply
from observations import ObservationStore
from tests.test_ai_service import PNG_1PX_B64


# ---------- 存储 + 变化检测 ----------
def test_add_get_clear_and_cap():
    s = ObservationStore(max_per_session=3)
    for i in range(5):
        s.add("u1", f"obs{i}")
    assert s.get("u1") == ["obs2", "obs3", "obs4"]   # 超出上限丢最旧
    s.clear("u1")
    assert s.get("u1") == []


def test_scene_changed():
    s = ObservationStore(change_threshold=5)
    assert s.scene_changed("u1", 0) is True          # 无法比较保守为变化
    assert s.scene_changed("u1", 123) is True         # 首帧
    s.mark("u1", 0b1111)
    assert s.scene_changed("u1", 0b1111) is False     # 同帧
    assert s.scene_changed("u1", 0b1111 ^ 0xFFFF) is True
    assert s.scene_changed("u2", 0b1111) is True       # 另一会话独立


def test_summarize_empty_and_nonempty():
    class FakeSvc:
        def __init__(self):
            self.got = None

        def vision_chat(self, q, **kw):
            self.got = q
            return VisionReply(text="纪要:有人在讲话", source="minimax")

    assert "暂无" in observations.summarize(FakeSvc(), [])
    svc = FakeSvc()
    out = observations.summarize(svc, ["甲讲话", "乙点头"])
    assert out == "纪要:有人在讲话"
    assert "甲讲话" in svc.got and "乙点头" in svc.got    # 观察拼进了提示


# ---------- 端点 ----------
@pytest.fixture
def client(monkeypatch):
    svc = app_module.get_service()
    monkeypatch.setattr(svc, "_minimax", None)   # 走 Mock
    observations._store = ObservationStore()      # 隔离
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_observe_requires_image(client):
    assert client.post("/api/observe", json={"session_id": "u"}).status_code == 400


def test_observe_then_skip_on_static_scene(client):
    body = {"session_id": "u", "image": f"data:image/png;base64,{PNG_1PX_B64}"}
    r1 = client.post("/api/observe", json=body).get_json()
    assert r1["skipped"] is False and r1["count"] == 1
    r2 = client.post("/api/observe", json=body).get_json()
    assert r2["skipped"] is True                   # 画面未变,跳过省钱


def test_summary_endpoint(client):
    client.post("/api/observe",
                json={"session_id": "u", "image": f"data:image/png;base64,{PNG_1PX_B64}"})
    j = client.post("/api/summary", json={"session_id": "u"}).get_json()
    assert "summary" in j and j["n"] >= 1


def test_summary_empty_session(client):
    j = client.post("/api/summary", json={"session_id": "nobody"}).get_json()
    assert j["n"] == 0


def test_clear_endpoint(client):
    body = {"session_id": "u", "image": f"data:image/png;base64,{PNG_1PX_B64}"}
    client.post("/api/observe", json=body)
    client.post("/api/observe/clear", json={"session_id": "u"})
    assert client.post("/api/summary", json={"session_id": "u"}).get_json()["n"] == 0
