"""Integration contract for the backend launcher entrypoint."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import textwrap
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

READ_TIMEOUT = 3.0


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
    assert newline == b"\n", (
        "launcher transport must terminate frames with a newline sentinel"
    )
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
async def test_backend_launcher_requires_config_and_loads_defaults(
    tmp_path: Path,
) -> None:
    """Launcher must read settings from config file and require --config."""

    config_path = tmp_path / "ragcli-config.yaml"
    socket_path = tmp_path / "backend.sock"
    config_path.write_text(
        textwrap.dedent(
            f"""
            backend:
              socket: "{socket_path}"
              weaviate_url: "http://127.0.0.1:8080"
              ollama_url: "http://127.0.0.1:11434"
              phoenix_url: "http://127.0.0.1:6006"
              log_level: INFO
              trace: false
            """
        ).strip(),
        encoding="utf-8",
    )

    project_root = Path(__file__).resolve().parents[3]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "services.rag_backend.main",
        "--config",
        str(config_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_launch_env(project_root),
    )

    try:
        await _wait_for_socket(socket_path, timeout=5.0)
        reader, writer = await asyncio.open_unix_connection(path=str(socket_path))
        try:
            await _write_frame(writer, HANDSHAKE_REQUEST)
            handshake = await asyncio.wait_for(
                _read_frame(reader), timeout=READ_TIMEOUT
            )
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
    assert (
        "offline_mode" in combined_output or "offline guard" in combined_output.lower()
    )


@pytest.mark.asyncio
async def test_backend_launcher_allows_cli_overrides(tmp_path: Path) -> None:
    """CLI flags should override config values."""

    socket_path = tmp_path / "backend.sock"
    config_path = tmp_path / "ragcli-config.yaml"
    config_path.write_text(
        textwrap.dedent(
            f"""
            backend:
              socket: "{socket_path}"
              weaviate_url: "http://bad-host:8080"
              ollama_url: "http://bad-host:11434"
              phoenix_url: "http://bad-host:6006"
              log_level: INFO
              trace: false
            """
        ).strip(),
        encoding="utf-8",
    )

    project_root = Path(__file__).resolve().parents[3]
    command = [
        sys.executable,
        "-m",
        "services.rag_backend.main",
        "--config",
        str(config_path),
        "--weaviate-url",
        "http://override:8080",
        "--ollama-url",
        "http://override:11434",
        "--phoenix-url",
        "http://override:6006",
        "--log-level",
        "DEBUG",
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_launch_env(project_root),
    )

    try:
        await _wait_for_socket(socket_path, timeout=5.0)
        reader, writer = await asyncio.open_unix_connection(path=str(socket_path))
        try:
            await _write_frame(writer, HANDSHAKE_REQUEST)
            handshake = await asyncio.wait_for(
                _read_frame(reader), timeout=READ_TIMEOUT
            )
        finally:
            writer.close()
            await writer.wait_closed()
        assert handshake == EXPECTED_HANDSHAKE_RESPONSE
    finally:
        process.terminate()
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)

    combined_output = (stdout + stderr).decode("utf-8", errors="replace")
    assert "http://override:11434" in combined_output
    assert "http://override:8080" in combined_output
    assert "http://override:6006" in combined_output
    assert "log_level=DEBUG" in combined_output


@pytest.mark.asyncio
async def test_backend_launcher_trace_flag_enables_controller(tmp_path: Path) -> None:
    """Passing --trace should enable the trace controller regardless of config."""

    socket_path = tmp_path / "backend.sock"
    config_path = tmp_path / "ragcli-config.yaml"
    config_path.write_text(
        textwrap.dedent(
            f"""
            backend:
              socket: "{socket_path}"
              weaviate_url: "http://127.0.0.1:8080"
              ollama_url: "http://127.0.0.1:11434"
              phoenix_url: "http://127.0.0.1:6006"
              log_level: INFO
              trace: false
            """
        ).strip(),
        encoding="utf-8",
    )

    project_root = Path(__file__).resolve().parents[3]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "services.rag_backend.main",
        "--config",
        str(config_path),
        "--trace",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_launch_env(project_root),
    )

    try:
        await _wait_for_socket(socket_path, timeout=5.0)
        reader, writer = await asyncio.open_unix_connection(path=str(socket_path))
        try:
            await _write_frame(writer, HANDSHAKE_REQUEST)
            handshake = await asyncio.wait_for(
                _read_frame(reader), timeout=READ_TIMEOUT
            )
        finally:
            writer.close()
            await writer.wait_closed()
        assert handshake == EXPECTED_HANDSHAKE_RESPONSE
    finally:
        process.terminate()
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)

    combined_output = (stdout + stderr).decode("utf-8", errors="replace")
    assert "TraceController.enable" in combined_output


@pytest.mark.asyncio
async def test_backend_launcher_requires_config_flag(tmp_path: Path) -> None:
    """Missing --config should cause the launcher to exit with an error."""

    project_root = Path(__file__).resolve().parents[3]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "services.rag_backend.main",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_launch_env(project_root),
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
    assert process.returncode != 0
    combined_output = (stdout + stderr).decode("utf-8", errors="replace")
    assert "--config" in combined_output
