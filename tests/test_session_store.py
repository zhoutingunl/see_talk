"""多轮上下文单测(design.md §11/§22):SessionStore + app 真正注入 history。"""
from __future__ import annotations

import pytest

import app as app_module
import session_store
from ai.types import ChatMessage, VisionReply
from session_store import SessionStore


# ---------- 存储逻辑 ----------
def test_append_and_history_pairs():
    s = SessionStore(turns=10)
    s.append("u", "问1", "答1")
    h = s.history("u")
    assert [(m.role, m.content) for m in h] == [
        ("user", "问1"), ("assistant", "答1")]
    assert all(isinstance(m, ChatMessage) for m in h)


def test_history_capped_to_n_turns():
    s = SessionStore(turns=2)          # 最多 2 轮 = 4 条
    for i in range(4):
        s.append("u", f"q{i}", f"a{i}")
    h = s.history("u")
    assert len(h) == 4                 # 只剩最近 2 轮
    assert h[0].content == "q2"        # 最旧的 q0/q1 被淘汰
    assert h[-1].content == "a3"


def test_sessions_isolated_and_clear():
    s = SessionStore(turns=5)
    s.append("a", "qa", "aa")
    s.append("b", "qb", "ab")
    assert len(s.history("a")) == 2 and len(s.history("b")) == 2
    s.clear("a")
    assert s.history("a") == [] and len(s.history("b")) == 2


# ---------- app 真正注入 history(核心:证明多轮不是声明) ----------
@pytest.fixture
def client(monkeypatch):
    svc = app_module.get_service()
    monkeypatch.setattr(svc, "_minimax", None)
    monkeypatch.setattr(svc, "_bailian", None)
    app_module._cache = app_module.vision_cache.VisionCache()
    session_store._store = SessionStore(turns=10)    # 隔离
    app_module.metrics.get_store().reset()
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_second_turn_receives_prior_history(client, monkeypatch):
    """第二轮调用 vision_chat 时,history 必须包含第一轮的问与答。"""
    captured = {"history": None}

    class FakeMM:
        def __init__(self):
            self.n = 0

        def vision_chat(self, q, *, history=None, **kw):
            self.n += 1
            captured["history"] = history
            return VisionReply(text=f"回答{self.n}", source="minimax",
                               input_tokens=10, output_tokens=5)

    svc = app_module.get_service()
    monkeypatch.setattr(svc, "_minimax", FakeMM())

    client.post("/api/ask", json={"question": "这本书讲什么", "session_id": "s1"})
    # 第一轮:history 为空
    assert captured["history"] == []

    client.post("/api/ask", json={"question": "适合初学者吗", "session_id": "s1"})
    # 第二轮:history 含第一轮的问与答
    h = [(m.role, m.content) for m in captured["history"]]
    assert h == [("user", "这本书讲什么"), ("assistant", "回答1")]


def test_clear_endpoint_resets_history(client):
    client.post("/api/ask", json={"question": "记住这句", "session_id": "s2"})
    client.post("/api/observe/clear", json={"session_id": "s2"})
    assert session_store.get_store().history("s2") == []
