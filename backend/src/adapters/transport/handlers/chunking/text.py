"""Chunk tokenization helpers."""

from __future__ import annotations

from typing import Iterable


def _chunk_text(text: str, max_tokens: int) -> Iterable[str]:
    words = text.split()
    if not words:
        return

    chunks: list[str] = []
    token_count = 0
    for word in words:
        chunks.append(word)
        token_count += 1
        if token_count >= max_tokens:
            yield " ".join(chunks)
            chunks = []
            token_count = 0
    if chunks:
        yield " ".join(chunks)


__all__ = ["_chunk_text"]
