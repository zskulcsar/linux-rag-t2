"""Document generation utilities."""

from pathlib import Path
from typing import Iterable

from adapters.weaviate.client import Document
from ports.ingestion import SourceType

from ..common import LOGGER
from .text import _chunk_text


def _generate_documents(
    *,
    alias: str,
    checksum: str,
    source_type: SourceType,
    location: Path,
    max_chunk_tokens: int,
    max_files: int,
) -> Iterable[Document]:
    chunk_id = 0
    for path in _iter_source_files(location, max_files=max_files):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                LOGGER.warning(
                    "factory.generate_documents(alias) :: file_unreadable",
                    alias=alias,
                    path=str(path),
                )
                continue

        for chunk in _chunk_text(text, max_chunk_tokens):
            if not chunk.strip():
                continue
            yield Document(
                alias=alias,
                checksum=checksum,
                chunk_id=chunk_id,
                text=chunk.strip(),
                source_type=source_type,
                language="en",
            )
            chunk_id += 1


def _iter_source_files(location: Path, max_files: int) -> Iterable[Path]:
    if location.is_file():
        yield location
        return

    if not location.exists():
        LOGGER.warning(
            "factory.generate_documents(alias) :: location_missing",
            location=str(location),
        )
        return

    if location.is_dir():
        count = 0
        for path in sorted(location.rglob("*")):
            if not path.is_file():
                continue
            yield path
            count += 1
            if count >= max_files:
                break


__all__ = ["_generate_documents"]
