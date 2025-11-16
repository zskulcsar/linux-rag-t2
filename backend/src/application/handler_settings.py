"""Shared handler settings used by the transport factory."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for typing only
    from main import LauncherConfig


@dataclass(frozen=True)
class HandlerSettings:
    """Runtime configuration for transport handlers."""

    weaviate_url: str
    ollama_url: str
    phoenix_url: str | None
    embedding_model: str
    completion_model: str
    data_dir: Path
    disable_bootstrap: bool = False


def _default_data_dir() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home) / "ragcli"
    configured = os.environ.get("RAG_BACKEND_DATA_HOME")
    if configured:
        return Path(configured)
    return Path.cwd() / ".ragcli"


def load_handler_settings_from_env() -> HandlerSettings:
    """Return handler settings constructed from environment variables."""

    return HandlerSettings(
        weaviate_url=os.environ.get("RAG_BACKEND_WEAVIATE_URL", "http://127.0.0.1:8080"),
        ollama_url=os.environ.get("RAG_BACKEND_OLLAMA_URL", "http://127.0.0.1:11434"),
        phoenix_url=os.environ.get("RAG_BACKEND_PHOENIX_URL"),
        embedding_model=os.environ.get(
            "RAG_BACKEND_EMBED_MODEL", "embeddinggemma:latest"
        ),
        completion_model=os.environ.get(
            "RAG_BACKEND_COMPLETION_MODEL", "gemma3:1b"
        ),
        data_dir=_default_data_dir(),
        disable_bootstrap=os.environ.get("RAG_BACKEND_DISABLE_BOOTSTRAP") == "1",
    )


def handler_settings_from_launcher(config: "LauncherConfig") -> HandlerSettings:
    """Adapt a LauncherConfig into handler settings."""

    base = load_handler_settings_from_env()
    return HandlerSettings(
        weaviate_url=config.weaviate_url,
        ollama_url=config.ollama_url,
        phoenix_url=config.phoenix_url,
        embedding_model=base.embedding_model,
        completion_model=base.completion_model,
        data_dir=base.data_dir,
        disable_bootstrap=base.disable_bootstrap,
    )


__all__ = [
    "HandlerSettings",
    "handler_settings_from_launcher",
    "load_handler_settings_from_env",
]
