"""Integration contract for the backend launcher entrypoint."""


import asyncio
import os
from pathlib import Path
import sys
import textwrap
from typing import Any

import pytest

from tests.python.helpers.ipc import close_writer, connect_and_handshake

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
        "main",
        "--config",
        str(config_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_launch_env(project_root),
    )

    try:
        await _wait_for_socket(socket_path, timeout=5.0)
        reader, writer = await connect_and_handshake(
            socket_path,
            request=HANDSHAKE_REQUEST,
            expected_response=EXPECTED_HANDSHAKE_RESPONSE,
            timeout=READ_TIMEOUT,
            newline_error="launcher transport must terminate frames with a newline sentinel",
        )
        await close_writer(writer)
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
        "main",
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
        reader, writer = await connect_and_handshake(
            socket_path,
            request=HANDSHAKE_REQUEST,
            expected_response=EXPECTED_HANDSHAKE_RESPONSE,
            timeout=READ_TIMEOUT,
            newline_error="launcher transport must terminate frames with a newline sentinel",
        )
        await close_writer(writer)
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
        "main",
        "--config",
        str(config_path),
        "--trace",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_launch_env(project_root),
    )

    try:
        await _wait_for_socket(socket_path, timeout=5.0)
        reader, writer = await connect_and_handshake(
            socket_path,
            request=HANDSHAKE_REQUEST,
            expected_response=EXPECTED_HANDSHAKE_RESPONSE,
            timeout=READ_TIMEOUT,
            newline_error="launcher transport must terminate frames with a newline sentinel",
        )
        await close_writer(writer)
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
        "main",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_launch_env(project_root),
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
    assert process.returncode != 0
    combined_output = (stdout + stderr).decode("utf-8", errors="replace")
    assert "--config" in combined_output
