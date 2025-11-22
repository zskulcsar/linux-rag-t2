"""Client and adapter builders used by the transport factory."""

import hashlib
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from adapters.ollama.client import OllamaAdapter
from adapters.weaviate.client import WeaviateAdapter
from application.handler_settings import HandlerSettings
from application.query_engine import RetrievalLLMQueryPort
from application.query_runner import QueryRunner
from ports import SourceCatalog

from .common import LOGGER, _using_fake_services
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


def _build_weaviate_adapter(settings: HandlerSettings) -> WeaviateAdapter:
    """Instantiate the Weaviate adapter with graceful fallbacks."""

    if _using_fake_services():
        fake_client = _FakeWeaviateClient()
        return WeaviateAdapter(client=fake_client, class_name="Document")

    try:
        import weaviate  # type: ignore

        parsed = urlparse(settings.weaviate_url)
        host = parsed.hostname or "127.0.0.1"
        scheme = parsed.scheme or "http"
        http_secure = scheme == "https"
        http_port = parsed.port or (443 if http_secure else 80)
        client: Any = weaviate.connect_to_custom(  # type: ignore[attr-defined]
            skip_init_checks=True,
            http_host=host,
            http_port=http_port,
            http_secure=http_secure,
            grpc_host=host,
            grpc_port=settings.weaviate_grpc_port,
            grpc_secure=http_secure,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        LOGGER.warning(
            "factory.weaviate_adapter(settings) :: client_initialization_failed",
            error=str(exc),
            url=settings.weaviate_url,
        )
        fallback_client = _FakeWeaviateClient()
        return WeaviateAdapter(client=fallback_client, class_name="Document")
    return WeaviateAdapter(client=client, class_name="Document")


def _build_embedding_adapter(settings: HandlerSettings, tracer: Any) -> OllamaAdapter:
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
        tracer=tracer,
    )


def _build_completion_adapter(settings: HandlerSettings) -> OllamaAdapter:
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
