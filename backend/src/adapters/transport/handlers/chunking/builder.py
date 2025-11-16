"""Chunk builder orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, cast

from adapters.ollama.client import EmbeddingResult, OllamaAdapter
from adapters.weaviate.client import Document, WeaviateAdapter
from application.source_catalog import ChunkBuilder
from ports import ingestion as ingestion_ports

from ..common import LOGGER, _DEFAULT_CHUNK_TOKEN_LIMIT, _MAX_CHUNK_FILES
from .documents import _generate_documents


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

        try:
            embeddings = list(self._embedding.embed_documents(documents))
        except Exception as exc:  # pragma: no cover - defensive guard
            LOGGER.warning(
                "factory.chunk_builder(alias) :: embedding_failed",
                alias=alias,
                error=str(exc),
            )
            embeddings = list(_fallback_embeddings(documents))
        else:
            if len(embeddings) != len(documents):
                LOGGER.warning(
                    "factory.chunk_builder(alias) :: embedding_count_mismatch",
                    alias=alias,
                    expected=len(documents),
                    actual=len(embeddings),
                )
                embeddings = list(_fallback_embeddings(documents))

        _attach_embeddings(documents, embeddings)

        enriched = [doc for doc in documents if doc.embedding]
        if not enriched:
            LOGGER.warning(
                "factory.chunk_builder(alias) :: no_embeddings_available",
                alias=alias,
            )
            return documents

        try:
            self._vector.ingest(enriched)
        except Exception as exc:  # pragma: no cover - defensive guard
            LOGGER.warning(
                "factory.chunk_builder(alias) :: ingestion_failed",
                alias=alias,
                error=str(exc),
            )
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
