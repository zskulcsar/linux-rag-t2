"""Shared helpers for transport handler modules."""

import datetime as dt
import os

from telemetry.logger import get_logger

LOGGER = get_logger("rag_backend.transport.factory")
_DEFAULT_CHUNK_TOKEN_LIMIT = 512
_MAX_CHUNK_FILES = 128


def _clock() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _using_fake_services() -> bool:
    return os.environ.get("RAG_BACKEND_FAKE_SERVICES") == "1"


__all__ = [
    "LOGGER",
    "_clock",
    "_DEFAULT_CHUNK_TOKEN_LIMIT",
    "_MAX_CHUNK_FILES",
    "_using_fake_services",
]
