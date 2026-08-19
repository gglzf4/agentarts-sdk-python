"""FastAPI application exposing AgentArts Memory over local HTTP.

Endpoints (trailing slash to match the convention used by hook scripts):
  GET  /health
  POST /add_messages/
  POST /search_memory/
  POST /list_memories/
  POST /search_summary/
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .agentarts_client import (
    DEFAULT_LIST_LIMIT,
    DEFAULT_MIN_SCORE,
    DEFAULT_TOP_K,
    AgentArtsMemoryClient,
)

logger = logging.getLogger("agentarts_memory_code_agent.server")

# Debug mode from environment
DEBUG = os.getenv("AGENTARTS_MEMORY_LOG_LEVEL", "info").lower() == "debug"

# Server version
SERVER_VERSION = "1.0.0"


def _log_request(endpoint: str, user_id: str, scope_id: str, plugin_version: str = "", **extra: Any) -> None:
    """Log request details in debug mode."""
    if DEBUG:
        version_str = f", plugin=v{plugin_version}" if plugin_version else ""
        extra_str = ", " + ", ".join(f"{k}={v}" for k, v in extra.items() if v) if extra else ""
        logger.debug("[API] %s | user_id=%s, scope_id=%s%s%s", endpoint, user_id, scope_id, version_str, extra_str)


def _log_response(endpoint: str, result: Any) -> None:
    """Log response details in debug mode."""
    if DEBUG:
        if isinstance(result, dict):
            count = result.get("total", len(result.get("results", [])))
            logger.debug("[API] %s | response: %d items", endpoint, count)
        else:
            logger.debug("[API] %s | response: %s", endpoint, type(result).__name__)


# ── single shared client instance ──
_client: AgentArtsMemoryClient | None = None


def get_client() -> AgentArtsMemoryClient:
    global _client
    if _client is None:
        _client = AgentArtsMemoryClient()
    return _client


def reset_client(client: AgentArtsMemoryClient | None = None) -> None:
    """Replace the shared client (used by tests)."""
    global _client
    _client = client


# ── request models ──
class MessageItem(BaseModel):
    role: str
    content: str


class AddMessagesRequest(BaseModel):
    messages: list[MessageItem]
    user_id: str = "cc-user"
    scope_id: str = "default"
    plugin_version: str = ""


class SearchRequest(BaseModel):
    query: str
    num: int = Field(default=DEFAULT_TOP_K, ge=1, le=100)
    user_id: str = "cc-user"
    scope_id: str = "default"
    threshold: float = Field(default=DEFAULT_MIN_SCORE, ge=0.0, le=1.0)
    plugin_version: str = ""


class ListRequest(BaseModel):
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    user_id: str | None = None
    scope_id: str | None = None
    plugin_version: str = ""


app = FastAPI(
    title="AgentArts Memory Agent Server",
    version=SERVER_VERSION,
    description="Local HTTP adapter over Huawei Cloud AgentArts Memory for Claude Code / Codex / OpenCode hooks.",
)

# Add CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    result = get_client().health()
    if DEBUG:
        logger.debug("[API] GET /health | status=%s", result.get("status", "unknown"))
    return result


@app.post("/add_messages/")
def add_messages(req: AddMessagesRequest) -> dict[str, Any]:
    _log_request("POST /add_messages/", req.user_id, req.scope_id, req.plugin_version, messages=len(req.messages))
    try:
        result = get_client().add_messages(
            [m.model_dump() for m in req.messages],
            user_id=req.user_id,
            scope_id=req.scope_id,
        )
        if DEBUG and result:
            logger.debug("[API] POST /add_messages/ | session_id=%s, count=%d",
                        result.get("session_id", "unknown"), result.get("count", 0))
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("add_messages failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/search_memory/")
def search_memory(req: SearchRequest) -> dict[str, Any]:
    _log_request("POST /search_memory/", req.user_id, req.scope_id, req.plugin_version, query=req.query[:50], num=req.num)
    try:
        results = get_client().search_memories(
            query=req.query,
            user_id=req.user_id,
            scope_id=req.scope_id,
            num=req.num,
            threshold=req.threshold,
        )
        _log_response("POST /search_memory/", results)
        return {"results": results, "total": len(results), "query": req.query}
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_memory failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/list_memories/")
def list_memories(req: ListRequest) -> dict[str, Any]:
    _log_request("POST /list_memories/", req.user_id or "default", req.scope_id or "default", req.plugin_version, limit=req.limit)
    try:
        results = get_client().list_memories(
            user_id=req.user_id,
            scope_id=req.scope_id,
            limit=req.limit,
            offset=req.offset,
        )
        _log_response("POST /list_memories/", results)
        return {"results": results, "total": len(results)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_memories failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/search_summary/")
def search_summary(req: SearchRequest) -> dict[str, Any]:
    """Summary search — reuse list_memories filtered to summary-like types.

    AgentArts has no dedicated summary endpoint, so we list memories and
    return those whose strategy_type looks summary-like; falling back to the
    full list when no summary-type memories exist.
    """
    _log_request("POST /search_summary/", req.user_id, req.scope_id, req.plugin_version, query=req.query[:50], num=req.num)
    try:
        all_mem = get_client().list_memories(
            user_id=req.user_id,
            scope_id=req.scope_id,
            limit=min(max(req.num * 5, DEFAULT_LIST_LIMIT), 20),
            offset=0,
        )
        summary_types = {"summary", "episodic", "user_preference"}
        summaries = [m for m in all_mem if m.get("type") in summary_types]
        if not summaries:
            summaries = all_mem
        summaries = summaries[: req.num]
        _log_response("POST /search_summary/", summaries)
        return {"results": summaries, "total": len(summaries), "query": req.query}
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_summary failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc