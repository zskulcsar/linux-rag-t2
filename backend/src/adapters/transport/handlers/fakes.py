"""Fake service clients used when RAG_BACKEND_FAKE_SERVICES=1."""

from __future__ import annotations

from typing import Any, Sequence


class _FakeWeaviateBatch:
    def __init__(self, storage: list[dict[str, Any]]) -> None:
        self._storage = storage

    def __enter__(self) -> "_FakeWeaviateBatch":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        """No-op context manager exit."""

    def add_data_object(
        self, data_object: dict[str, Any], class_name: str, uuid: str
    ) -> None:
        record = dict(data_object)
        record["class_name"] = class_name
        record["uuid"] = uuid
        self._storage.append(record)


class _FakeWeaviateQueryBuilder:
    def __init__(self, storage: list[dict[str, Any]], class_name: str) -> None:
        self._storage = storage
        self._class_name = class_name
        self._filters: dict[str, Any] | None = None
        self._limit = 10

    def with_where(self, filters: dict[str, Any]) -> "_FakeWeaviateQueryBuilder":
        self._filters = filters
        return self

    def with_limit(self, limit: int) -> "_FakeWeaviateQueryBuilder":
        self._limit = limit
        return self

    def do(self) -> dict[str, Any]:
        alias = None
        source_type = None
        language = None
        if self._filters:
            for operand in self._filters.get("operands", []):
                path = operand.get("path", [])
                if path == ["source_alias"]:
                    alias = operand.get("valueString")
                elif path == ["source_type"]:
                    source_type = operand.get("valueString")
                elif path == ["language"]:
                    language = operand.get("valueString")

        results: list[dict[str, Any]] = []
        for entry in self._storage:
            if alias and entry.get("source_alias") != alias:
                continue
            if source_type and entry.get("source_type") != source_type:
                continue
            if language and entry.get("language") != language:
                continue
            results.append(entry)
            if len(results) >= self._limit:
                break

        return {
            "data": {"Get": {self._class_name: [dict(item) for item in results]}}
        }


class _FakeWeaviateQuery:
    def __init__(self, storage: list[dict[str, Any]]) -> None:
        self._storage = storage

    def get(self, class_name: str, fields: list[str]) -> _FakeWeaviateQueryBuilder:
        return _FakeWeaviateQueryBuilder(self._storage, class_name)


class _FakeWeaviateClient:
    def __init__(self) -> None:
        self._storage: list[dict[str, Any]] = []
        self.batch = _FakeWeaviateBatch(self._storage)
        self.query = _FakeWeaviateQuery(self._storage)


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeOllamaHttpClient:
    def __init__(self, *, mode: str) -> None:
        self._mode = mode

    def post(
        self,
        url: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> _FakeHttpResponse:
        if self._mode == "embedding":
            embeddings = [
                {
                    "embedding": [float(i) for i in range(len(text.split()))],
                }
                for text in payload.get("input", [])
            ]
            return _FakeHttpResponse({"embeddings": embeddings})
        return _FakeHttpResponse(
            {
                "model": payload.get("model", "fake"),
                "created_at": "1970-01-01T00:00:00Z",
                "response": "stubbed response",
                "done": True,
            }
        )


__all__ = [
    "_FakeHttpResponse",
    "_FakeOllamaHttpClient",
    "_FakeWeaviateBatch",
    "_FakeWeaviateClient",
    "_FakeWeaviateQuery",
    "_FakeWeaviateQueryBuilder",
]
