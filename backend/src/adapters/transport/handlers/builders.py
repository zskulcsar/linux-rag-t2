"""Client and adapter builders used by the transport factory."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from adapters.ollama.client import OllamaAdapter
from adapters.weaviate.client import WeaviateAdapter
from application.query_engine import RetrievalLLMQueryPort
from application.query_runner import QueryRunner
from ports import SourceCatalog

from .common import LOGGER, _using_fake_services
from .config import _BackendSettings
from .fakes import _FakeOllamaHttpClient, _FakeWeaviateClient
from .http import _UrllibHttpClient


def _build_query_runner(
    *,
    catalog_loader: Callable[[], SourceCatalog],
    vector_adapter: WeaviateAdapter,
    llm_adapter: OllamaAdapter,
) -> QueryRunner:
    retrieval_port = RetrievalLLMQueryPort(
        catalog_loader=catalog_loader,
        vector_adapter=vector_adapter,
        llm_adapter=llm_adapter,
    )
    return QueryRunner(query_port=retrieval_port)


def _build_weaviate_adapter(settings: _BackendSettings) -> WeaviateAdapter:
    """Instantiate the Weaviate adapter with graceful fallbacks."""

    if _using_fake_services():
        fake_client = _FakeWeaviateClient()
        return WeaviateAdapter(client=fake_client, class_name="Document")

    try:
        import weaviate  # type: ignore

        client: Any = weaviate.Client(settings.weaviate_url)  # type: ignore[call-arg]
    except Exception as exc:  # pragma: no cover - defensive fallback
        LOGGER.warning(
            "factory.weaviate_adapter(settings) :: client_initialization_failed",
            error=str(exc),
            url=settings.weaviate_url,
        )
        fallback_client = _FakeWeaviateClient()
        return WeaviateAdapter(client=fallback_client, class_name="Document")
    return WeaviateAdapter(client=client, class_name="Document")


def _build_embedding_adapter(settings: _BackendSettings) -> OllamaAdapter:
    """Instantiate the Ollama adapter used for embeddings."""

    if _using_fake_services():
        fake_client = _FakeOllamaHttpClient(mode="embedding")
        return OllamaAdapter(
            http_client=fake_client,
            base_url=settings.ollama_url,
            model=settings.embedding_model,
        )

    real_client = _UrllibHttpClient()
    return OllamaAdapter(
        http_client=real_client,
        base_url=settings.ollama_url,
        model=settings.embedding_model,
    )


def _build_completion_adapter(settings: _BackendSettings) -> OllamaAdapter:
    """Instantiate the Ollama adapter used for completions."""

    if _using_fake_services():
        fake_client = _FakeOllamaHttpClient(mode="completion")
        return OllamaAdapter(
            http_client=fake_client,
            base_url=settings.ollama_url,
            model=settings.completion_model,
        )

    real_client = _UrllibHttpClient()
    return OllamaAdapter(
        http_client=real_client,
        base_url=settings.ollama_url,
        model=settings.completion_model,
    )


def _calculate_checksum(path: Path) -> str:
    """Return a deterministic SHA256 checksum for the given path."""

    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                if not chunk:
                    break
                digest.update(chunk)
    except IsADirectoryError:
        digest.update(path.name.encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


__all__ = [
    "_build_completion_adapter",
    "_build_embedding_adapter",
    "_build_query_runner",
    "_build_weaviate_adapter",
    "_calculate_checksum",
]
