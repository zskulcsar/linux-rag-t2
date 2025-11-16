"""Shared fixtures for unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.storage.catalog import CatalogStorage


@pytest.fixture(autouse=True)
def _unit_xdg_data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure unit tests operate within an isolated XDG data directory."""

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))


@pytest.fixture
def catalog_storage() -> CatalogStorage:
    """Provide a fresh CatalogStorage instance for tests."""

    return CatalogStorage()
