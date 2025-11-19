"""LLM-backed query port that retrieves context and generates answers."""

import json
import textwrap
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Sequence

from adapters.ollama.client import OllamaAdapter
from adapters.transport.handlers.errors import IndexUnavailableError
from adapters.weaviate.client import WeaviateAdapter
from ports import ingestion as ingestion_ports
from ports import query as query_ports
from telemetry import trace_call


@dataclass(frozen=True, slots=True)
class _ContextSnippet:
    alias: str
    checksum: str
    chunk_id: int
    text: str
    document_id: str

    @property
    def label(self) -> str:
        return f"{self.alias}:{self.chunk_id}"

    @property
    def preview(self) -> str:
        return self.text[:160].strip()


class RetrievalLLMQueryPort(query_ports.QueryPort):
    """QueryPort implementation backed by Weaviate retrieval and Ollama generation."""

    def __init__(
        self,
        *,
        catalog_loader: Callable[[], ingestion_ports.SourceCatalog],
        vector_adapter: WeaviateAdapter,
        llm_adapter: OllamaAdapter,
        documents_per_source: int = 3,
    ) -> None:
        """Create a retrieval/generation pipeline.

        Args:
            catalog_loader: Callable returning the latest source catalog snapshot.
            vector_adapter: Adapter used to retrieve semantic chunks.
            llm_adapter: Adapter used to generate final completions.
            documents_per_source: Maximum chunks to retrieve per active source.
        """
        self._catalog_loader = catalog_loader
        self._vector = vector_adapter
        self._llm = llm_adapter
        self._documents_per_source = max(1, documents_per_source)

    @trace_call
    def query(self, request: query_ports.QueryRequest) -> query_ports.QueryResponse:
        """Execute a query using Weaviate retrieval and Ollama generation.

        Args:
            request: Fully-populated query request from :mod:`ports.query`.

        Returns:
            A structured :class:`~ports.query.QueryResponse` payload.

        Raises:
            IndexUnavailableError: If no catalog snapshots can be queried.
        """
        catalog = self._catalog_loader()
        if catalog.version <= 0 or not catalog.snapshots:
            raise IndexUnavailableError(
                code="INDEX_MISSING",
                message="No content index is available for the current catalog.",
                remediation="Run ragadmin reindex to build the knowledge index before continuing.",
            )

        retrieval_start = time.perf_counter()
        contexts = self._collect_contexts(catalog)
        retrieval_latency_ms = int((time.perf_counter() - retrieval_start) * 1000)

        correlation_id = uuid.uuid4().hex
        if not contexts:
            summary = (
                "No indexed documents are available for the current catalog. "
                "Run `ragadmin reindex` to populate retrieval context."
            )
            return query_ports.QueryResponse(
                summary=summary,
                steps=["Run `ragadmin reindex` and retry the query."],
                references=[
                    query_ports.Reference(
                        label="Catalog",
                        notes="No indexed snapshots available.",
                    )
                ],
                citations=[],
                confidence=0.25,
                trace_id=request.trace_id or correlation_id,
                backend_correlation_id=correlation_id,
                latency_ms=retrieval_latency_ms,
                retrieval_latency_ms=retrieval_latency_ms,
                llm_latency_ms=0,
                index_version=f"catalog/v{catalog.version}",
                no_answer=True,
                semantic_chunk_count=0,
            )

        prompt = self._render_prompt(question=request.question, contexts=contexts)
        llm_start = time.perf_counter()
        completion = self._llm.generate_completion(
            prompt=prompt,
            alias="ragcli-query",
            options={"temperature": 0.15, "format": "json"},
        )
        llm_latency_ms = int((time.perf_counter() - llm_start) * 1000)

        parsed = self._parse_completion(completion)
        references = self._build_references(parsed, contexts)
        citations = self._build_citations(contexts)
        confidence = _safe_float(parsed.get("confidence"), default=0.6)
        confidence = max(0.0, min(1.0, confidence))
        steps: list[str] = _ensure_steps(parsed.get("steps"))

        summary_value = parsed.get("summary")
        summary_text = summary_value.strip() if isinstance(summary_value, str) else ""
        if not summary_text:
            summary_text = (
                f"Consult the retrieved manuals for guidance on '{request.question}'."
            )

        answer_value = parsed.get("answer")
        answer_text = (
            answer_value.strip() if isinstance(answer_value, str) else summary_text
        )

        response = query_ports.QueryResponse(
            summary=summary_text,
            steps=[step.strip() for step in steps if step],
            references=references,
            citations=citations,
            confidence=confidence,
            trace_id=request.trace_id or correlation_id,
            backend_correlation_id=correlation_id,
            latency_ms=retrieval_latency_ms + llm_latency_ms,
            retrieval_latency_ms=retrieval_latency_ms,
            llm_latency_ms=llm_latency_ms,
            index_version=f"catalog/v{catalog.version}",
            answer=answer_text,
            no_answer=bool(parsed.get("no_answer", False)),
            semantic_chunk_count=len(contexts),
        )
        return response

    def _collect_contexts(
        self, catalog: ingestion_ports.SourceCatalog
    ) -> list[_ContextSnippet]:
        contexts: list[_ContextSnippet] = []
        for record in catalog.sources:
            if record.status is not ingestion_ports.SourceStatus.ACTIVE:
                continue
            try:
                documents = self._vector.query_documents(
                    alias=record.alias,
                    source_type=record.type,
                    language=record.language,
                    limit=self._documents_per_source,
                )
            except Exception:
                continue

            for document in documents:
                contexts.append(
                    _ContextSnippet(
                        alias=document.alias,
                        checksum=document.checksum,
                        chunk_id=document.chunk_id,
                        text=document.text,
                        document_id=document.document_id,
                    )
                )
        return contexts

    def _render_prompt(
        self, *, question: str, contexts: Sequence[_ContextSnippet]
    ) -> str:
        context_blocks = []
        for snippet in contexts:
            context_blocks.append(
                f"[{snippet.alias}:{snippet.chunk_id}] {snippet.text.strip()}"
            )
        context_text = "\n".join(context_blocks)
        instructions = textwrap.dedent(
            """
            You are a local Linux assistant. Use ONLY the provided context to answer the question.
            Respond as JSON with the following keys: summary (string), steps (array of short instructions),
            references (array of objects with label and optional notes/url), confidence (0-1 float),
            and no_answer (boolean). Keep guidance concise and cite the relevant context snippets.
            """
        ).strip()
        return f"{instructions}\n\nContext:\n{context_text}\n\nQuestion:\n{question.strip()}\n\nJSON Response:"

    def _parse_completion(self, completion: dict[str, object]) -> dict[str, object]:
        body = completion.get("response")
        if isinstance(body, dict):
            return body
        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {}
        return {}

    def _build_references(
        self, parsed: dict[str, object], contexts: Sequence[_ContextSnippet]
    ) -> list[query_ports.Reference]:
        references_data = parsed.get("references")
        references: list[query_ports.Reference] = []
        if isinstance(references_data, list):
            for item in references_data:
                if isinstance(item, dict):
                    references.append(
                        query_ports.Reference(
                            label=str(item.get("label", "")) or "context",
                            url=item.get("url"),
                            notes=item.get("notes"),
                        )
                    )
        if references:
            return references

        for snippet in contexts:
            references.append(
                query_ports.Reference(
                    label=snippet.label,
                    notes=snippet.preview,
                )
            )
        return references

    def _build_citations(
        self, contexts: Sequence[_ContextSnippet]
    ) -> list[query_ports.Citation]:
        citations: list[query_ports.Citation] = []
        for snippet in contexts:
            citations.append(
                query_ports.Citation(
                    alias=snippet.alias,
                    document_ref=snippet.document_id,
                    excerpt=snippet.preview,
                )
            )
        return citations


__all__ = ["RetrievalLLMQueryPort"]


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ensure_steps(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(step) for step in value if isinstance(step, str) and step.strip()]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return []
