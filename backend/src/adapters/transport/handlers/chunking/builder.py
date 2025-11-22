"""Chunk builder orchestration."""

import time
from pathlib import Path
from typing import Callable, Optional, Sequence, cast

from adapters.ollama.client import EmbeddingResult, OllamaAdapter
from adapters.weaviate.client import Document, WeaviateAdapter
from application.source_catalog import ChunkBuilder
from ports import ingestion as ingestion_ports

from ..common import LOGGER, _DEFAULT_CHUNK_TOKEN_LIMIT, _MAX_CHUNK_FILES
from .documents import _generate_documents

_PROGRESS_HEARTBEAT = 1.0  # seconds
_PROGRESS_BATCH_SIZE = 10


class _ChunkBuilderAdapter:
    def __init__(
        self,
        *,
        embedding: OllamaAdapter,
        vector: WeaviateAdapter,
        chunk_tokens: int,
        file_limit: int,
    ) -> None:
        self._embedding = embedding
        self._vector = vector
        self._chunk_tokens = chunk_tokens
        self._file_limit = file_limit

    def __call__(
        self,
        *,
        alias: str,
        checksum: str,
        location: Path,
        source_type: ingestion_ports.SourceType,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> Sequence[Document]:
        documents = list(
            _generate_documents(
                alias=alias,
                checksum=checksum,
                source_type=source_type,
                location=location,
                max_chunk_tokens=self._chunk_tokens,
                max_files=self._file_limit,
            )
        )
        if not documents:
            LOGGER.warning(
                "factory.chunk_builder(alias) :: no_documents_generated",
                alias=alias,
            )
            return []

        processed = 0
        total = len(documents)
        last_emit = time.monotonic()

        def maybe_emit_progress(callback: Optional[Callable[[int, int], None]]) -> None:
            nonlocal last_emit
            if callback is None:
                return
            now = time.monotonic()
            if processed % _PROGRESS_BATCH_SIZE == 0 or now - last_emit >= _PROGRESS_HEARTBEAT:
                last_emit = now
                try:
                    callback(processed, total)
                except Exception as exc:  # pragma: no cover - defensive guard
                    LOGGER.warning(
                        "factory.chunk_builder(alias) :: progress_callback_failed",
                        alias=alias,
                        error=str(exc),
                    )

        # TODO: this `single` works, but it is dirty.
        # We should update all the called methods to to handle the Document directly without the list wrapper
        for document in documents:
            single = [document]
            try:
                embeddings = list(self._embedding.embed_documents(single))
            except Exception as exc:  # pragma: no cover - defensive guard
                LOGGER.warning(
                    "factory.chunk_builder(alias) :: embedding_failed",
                    alias=alias,
                    chunk_id=document.chunk_id,
                    error=str(exc),
                )
                raise RuntimeError(f"embedding failed for {alias}: {exc}") from exc

            if len(embeddings) != len(single):
                LOGGER.warning(
                    "factory.chunk_builder(alias) :: embedding_count_mismatch",
                    alias=alias,
                    chunk_id=document.chunk_id,
                    expected=len(single),
                    actual=len(embeddings),
                )
                continue

            _attach_embeddings(single, embeddings)
            if not document.embedding:
                LOGGER.warning(
                    "factory.chunk_builder(alias) :: no_embedding_for_document",
                    alias=alias,
                    chunk_id=document.chunk_id,
                )
                continue

            try:
                self._vector.ingest(single)
            except Exception as exc:  # pragma: no cover - defensive guard
                LOGGER.warning(
                    "factory.chunk_builder(alias) :: ingestion_failed",
                    alias=alias,
                    chunk_id=document.chunk_id,
                    error=str(exc),
                )
                raise RuntimeError(f"vector ingestion failed for {alias}: {exc}") from exc
            processed += 1
            maybe_emit_progress(None if on_progress is None else on_progress)
        maybe_emit_progress(None if on_progress is None else on_progress)
        return documents


def _chunk_builder_factory(
    *,
    embedding_adapter: OllamaAdapter,
    vector_adapter: WeaviateAdapter,
    max_chunk_tokens: int = _DEFAULT_CHUNK_TOKEN_LIMIT,
    max_files: int = _MAX_CHUNK_FILES,
) -> ChunkBuilder:
    """Create a chunk builder that orchestrates embeddings and vector ingestion."""

    builder = _ChunkBuilderAdapter(
        embedding=embedding_adapter,
        vector=vector_adapter,
        chunk_tokens=max_chunk_tokens,
        file_limit=max_files,
    )
    return cast(ChunkBuilder, builder)


def _fallback_embeddings(documents: Sequence[Document]) -> Sequence[EmbeddingResult]:
    fallback: list[EmbeddingResult] = []
    for document in documents:
        length_score = float(len(document.text))
        fallback.append(
            EmbeddingResult(
                alias=document.alias,
                checksum=document.checksum,
                chunk_id=document.chunk_id,
                embedding=[length_score],
            )
        )
    return fallback


def _attach_embeddings(
    documents: Sequence[Document],
    embeddings: Sequence[EmbeddingResult],
) -> None:
    lookup = {
        (result.alias, result.checksum, result.chunk_id): result.embedding
        for result in embeddings
    }
    for document in documents:
        key = (document.alias, document.checksum, document.chunk_id)
        vector = lookup.get(key)
        if vector is not None:
            document.embedding = list(vector)


__all__ = ["_chunk_builder_factory"]
