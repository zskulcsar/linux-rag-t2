"""Unit tests for the Weaviate adapter lifecycle helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from adapters.weaviate.client import Document, WeaviateAdapter
from ports.ingestion import SourceType


class _StubBatchContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def add_data_object(self, payload, class_name, uuid):
        return None


def _build_document() -> Document:
    return Document(
        alias="man-pages",
        checksum="abc123",
        chunk_id=0,
        text="chmod synopsis",
        source_type=SourceType.MAN,
        language="en",
    )


def test_weaviate_adapter_close_invokes_client_close(monkeypatch: pytest.MonkeyPatch):
    """Close should call the underlying client's close() method exactly once."""

    closed: list[bool] = []

    def _fake_close() -> None:
        closed.append(True)

    client = SimpleNamespace(close=_fake_close, batch=_StubBatchContext())
    adapter = WeaviateAdapter(client=client, class_name="Document")

    adapter.close()

    assert closed == [True], "client.close() must be invoked during adapter shutdown"


def test_weaviate_adapter_context_manager_closes_client() -> None:
    """__exit__ should call close() to prevent ResourceWarning leaks."""

    closed = False

    def _fake_close() -> None:
        nonlocal closed
        closed = True

    client = SimpleNamespace(close=_fake_close, batch=_StubBatchContext())
    document = _build_document()

    with WeaviateAdapter(client=client, class_name="Document") as adapter:
        adapter.ingest([document])

    assert closed is True, "context manager exit must close the client"
