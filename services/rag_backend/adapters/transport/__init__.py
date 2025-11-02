"""Transport adapters for the Unix domain socket IPC layer."""

from .server import transport_server

__all__ = ["transport_server"]

