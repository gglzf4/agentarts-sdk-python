"""Unit tests for the FastAPI server routes (server/app.py).

Uses FastAPI TestClient with a mock AgentArtsMemoryClient injected via
reset_client(). No network or cloud SDK required.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agentarts.toolkit.plugins.memory.server import app as app_module
from agentarts.toolkit.plugins.memory.server.app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_SDK_AK", "ak")
    monkeypatch.setenv("HUAWEICLOUD_SDK_SK", "sk")
    monkeypatch.setenv("AGENTARTS_MEMORY_SPACE_ID", "sp")
    monkeypatch.setenv("HUAWEICLOUD_SDK_MEMORY_API_KEY", "k")
    mock = MagicMock()
    mock.health.return_value = {"status": "healthy", "space_id": True, "ak": True, "sk": True, "api_key": True}
    app_module.reset_client(mock)
    yield mock
    app_module.reset_client(None)


def test_health(client):
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_add_messages(client):
    client.add_messages.return_value = {"session_id": "s1", "count": 2}
    c = TestClient(app)
    r = c.post("/add_messages/", json={
        "messages": [{"role": "user", "content": "hi"}],
        "user_id": "u1", "scope_id": "proj",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s1"
    assert body["count"] == 2
    kw = client.add_messages.call_args.args[0]
    assert kw[0] == {"role": "user", "content": "hi"}
    assert client.add_messages.call_args.kwargs == {"user_id": "u1", "scope_id": "proj"}


def test_add_messages_error(client):
    client.add_messages.side_effect = RuntimeError("boom")
    c = TestClient(app)
    r = c.post("/add_messages/", json={
        "messages": [{"role": "user", "content": "x"}],
        "user_id": "u", "scope_id": "s",
    })
    assert r.status_code == 502
    assert "boom" in r.json()["detail"]


def test_search_memory(client):
    client.search_memories.return_value = [
        {"content": "c1", "score": 0.9, "type": "semantic"},
    ]
    c = TestClient(app)
    r = c.post("/search_memory/", json={
        "query": "py", "user_id": "u", "scope_id": "s", "num": 5, "threshold": 0.3,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["content"] == "c1"
    assert body["query"] == "py"
    kw = client.search_memories.call_args.kwargs
    assert kw["query"] == "py"
    assert kw["num"] == 5
    assert kw["threshold"] == 0.3


def test_list_memories(client):
    client.list_memories.return_value = [
        {"id": "m1", "content": "c", "type": "semantic", "created_at": "t"},
    ]
    c = TestClient(app)
    r = c.post("/list_memories/", json={"limit": 10, "offset": 0, "user_id": "u", "scope_id": "s"})
    assert r.status_code == 200
    assert r.json()["results"][0]["id"] == "m1"


def test_search_summary(client):
    client.list_memories.return_value = [
        {"id": "m1", "content": "sum", "type": "episodic", "created_at": "t"},
        {"id": "m2", "content": "other", "type": "semantic", "created_at": "t2"},
    ]
    c = TestClient(app)
    r = c.post("/search_summary/", json={
        "query": "x", "user_id": "u", "scope_id": "s", "num": 3, "threshold": 0.3,
    })
    assert r.status_code == 200
    types = [m["type"] for m in r.json()["results"]]
    assert "episodic" in types


def test_search_summary_fallback_to_all(client):
    client.list_memories.return_value = [
        {"id": "m1", "content": "c", "type": "semantic", "created_at": "t"},
    ]
    c = TestClient(app)
    r = c.post("/search_summary/", json={
        "query": "x", "user_id": "u", "scope_id": "s", "num": 5, "threshold": 0.3,
    })
    assert r.status_code == 200
    assert len(r.json()["results"]) == 1


def test_validation_error(client):
    c = TestClient(app)
    # missing messages field
    r = c.post("/add_messages/", json={"user_id": "u", "scope_id": "s"})
    assert r.status_code == 422
