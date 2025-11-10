"""Integration contract for the backend launcher entrypoint."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest

HANDSHAKE_REQUEST = {
    "type": "handshake",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "client": "launcher-tests",
}

EXPECTED_HANDSHAKE_RESPONSE = {
    "type": "handshake_ack",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "server": "rag-backend",
}


async def _write_frame(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    """Send a framed JSON message using <len>\\n<payload>\\n semantics."""

    payload = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    header = f"{len(payload)}\n".encode("ascii")
    writer.write(header)
    writer.write(payload)
    writer.write(b"\n")
    await writer.drain()


async def _read_frame(reader: asyncio.StreamReader) -> dict[str, Any]:
    """Read a framed JSON message using <len>\\n<payload>\\n semantics."""

    length_line = await reader.readline()
    if not length_line:
        raise AssertionError("expected a length-prefixed frame, received EOF instead")
    try:
        payload_length = int(length_line.decode("ascii").strip())
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise AssertionError(f"invalid frame length prefix: {length_line!r}") from exc

    payload = await reader.readexactly(payload_length)
    newline = await reader.readexactly(1)
    assert newline == b"\n", "launcher transport must terminate frames with a newline sentinel"
    return json.loads(payload.decode("utf-8"))


async def _wait_for_socket(path: Path, timeout: float = 5.0) -> None:
    """Poll until the launcher creates the Unix socket file or time out."""

    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if path.exists():
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"backend launcher did not create socket at {path}")


def _launch_env(project_root: Path) -> dict[str, str]:
    """Return an env mapping that ensures the backend package is importable."""

    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    python_path = str(project_root)
    if existing:
        python_path = f"{python_path}:{existing}"
    env["PYTHONPATH"] = python_path
    return env


@pytest.mark.asyncio
async def test_backend_launcher_starts_transport_and_logs_configuration(tmp_path: Path) -> None:
    """The launcher should start the transport server and log runtime configuration."""

    project_root = Path(__file__).resolve().parents[3]
    socket_path = tmp_path / "backend.sock"
    command = [
        sys.executable,
        "-m",
        "services.rag_backend.main",
        "--socket",
        str(socket_path),
        "--ollama-url",
        "http://127.0.0.1:11434",
        "--weaviate-url",
        "http://127.0.0.1:8080",
        "--phoenix-url",
        "http://127.0.0.1:6006",
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_launch_env(project_root),
    )

    stdout: bytes = b""
    stderr: bytes = b""
    try:
        await _wait_for_socket(socket_path, timeout=5.0)
        reader, writer = await asyncio.open_unix_connection(path=str(socket_path))
        try:
            await _write_frame(writer, HANDSHAKE_REQUEST)
            handshake = await asyncio.wait_for(_read_frame(reader), timeout=1)
        finally:
            writer.close()
            await writer.wait_closed()

        assert handshake == EXPECTED_HANDSHAKE_RESPONSE
    finally:
        process.terminate()
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)

    combined_output = (stdout + stderr).decode("utf-8", errors="replace")
    assert "http://127.0.0.1:11434" in combined_output
    assert "http://127.0.0.1:8080" in combined_output
    assert "http://127.0.0.1:6006" in combined_output
    assert "offline_mode" in combined_output or "offline guard" in combined_output.lower()
