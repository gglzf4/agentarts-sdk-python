"""AgentArts Memory local HTTP adapter server.

Exposes a thin FastAPI layer over the AgentArts MemoryClient so that
Claude Code / Codex / OpenCode hook scripts can record prompts and retrieve
memories via plain HTTP.
"""

__all__ = ["app", "AgentArtsMemoryClient"]
