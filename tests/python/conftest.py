"""Fixtures shared across python test suites."""

from __future__ import annotations

import pytest

from adapters.transport import create_default_handlers


@pytest.fixture
def make_transport_handlers():
    """Provide a factory for constructing transport handlers."""

    def _factory():
        return create_default_handlers()

    return _factory
