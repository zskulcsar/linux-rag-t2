"""Fixtures shared across python test suites."""

from __future__ import annotations

import pytest

from adapters.transport import create_default_handlers


@pytest.fixture
def make_transport_handlers():
    """Provide a factory for constructing and cleaning up transport handlers."""

    created = []

    def _factory():
        handlers = create_default_handlers()
        created.append(handlers)
        return handlers

    yield _factory

    for handlers in created:
        close = getattr(handlers, "close", None)
        if callable(close):
            close()
