"""Unit tests for backend launcher helpers (main module)."""


import argparse
import logging
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest


def _install_stub_modules() -> None:
    transport_mod = types.ModuleType("adapters.transport")

    class _AsyncNullContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _transport_server(*args, **kwargs):
        return _AsyncNullContext()

    transport_mod.create_default_handlers = lambda: {}
    transport_mod.transport_server = _transport_server
    sys.modules.setdefault("adapters.transport", transport_mod)

    offline_mod = types.ModuleType("application.offline_guard")

    @contextmanager
    def offline_mode():
        yield

    offline_mod.offline_mode = offline_mode
    sys.modules.setdefault("application.offline_guard", offline_mod)


_install_stub_modules()

from main import (  # noqa: E402
    LauncherConfig,
    LauncherConfigError,
    _coalesce_bool,
    _coalesce_value,
    _load_backend_settings,
    build_launcher_config,
    configure_logging,
    parse_args,
)


def test_parse_args_returns_namespace() -> None:
    args = parse_args(["--config", "/etc/ragcli/config.yaml"])
    assert args.config == "/etc/ragcli/config.yaml"
    assert args.socket is None


def test_configure_logging_sets_root_level(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_basic_config(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(logging, "basicConfig", fake_basic_config)
    configure_logging("DEBUG")
    assert captured["level"] == logging.DEBUG


def test_load_backend_settings_reads_nested_backend(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "backend:\n"
        "  socket: /tmp/backend.sock\n"
        "  weaviate_url: http://localhost:8080\n",
        encoding="utf-8",
    )

    data = _load_backend_settings(config_path)
    assert data["socket"] == "/tmp/backend.sock"
    assert data["weaviate_url"] == "http://localhost:8080"


def test_load_backend_settings_validates_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(LauncherConfigError):
        _load_backend_settings(missing)

    bad_root = tmp_path / "bad.yaml"
    bad_root.write_text("- just-a-list", encoding="utf-8")
    with pytest.raises(LauncherConfigError):
        _load_backend_settings(bad_root)

    bad_backend = tmp_path / "bad_backend.yaml"
    bad_backend.write_text("backend: []", encoding="utf-8")
    with pytest.raises(LauncherConfigError):
        _load_backend_settings(bad_backend)


def test_coalesce_value_precedence() -> None:
    config = {"socket": "/tmp/config.sock"}
    assert (
        _coalesce_value(name="socket", cli_value="/tmp/cli.sock", config=config)
        == "/tmp/cli.sock"
    )
    assert (
        _coalesce_value(name="socket", cli_value=None, config=config)
        == "/tmp/config.sock"
    )
    assert (
        _coalesce_value(name="log_level", cli_value=None, config={}, default="INFO")
        == "INFO"
    )
    with pytest.raises(LauncherConfigError):
        _coalesce_value(name="missing", cli_value=None, config={})


def test_coalesce_bool_handles_cli_config_and_strings() -> None:
    config = {"trace": "yes"}
    assert _coalesce_bool(name="trace", cli_value=None, config=config) is True
    assert _coalesce_bool(name="trace", cli_value=False, config=config) is False
    assert (
        _coalesce_bool(name="trace", cli_value=None, config={"trace": "off"}) is False
    )
    assert _coalesce_bool(name="trace", cli_value=None, config={}, default=True) is True
    with pytest.raises(LauncherConfigError):
        _coalesce_bool(name="trace", cli_value=None, config={"trace": "maybe"})


def _args(**overrides: Any) -> argparse.Namespace:
    defaults = {
        "config": overrides.get("config"),
        "socket": overrides.get("socket"),
        "weaviate_url": overrides.get("weaviate_url"),
        "ollama_url": overrides.get("ollama_url"),
        "phoenix_url": overrides.get("phoenix_url"),
        "trace": overrides.get("trace"),
        "log_level": overrides.get("log_level"),
    }
    return argparse.Namespace(**defaults)


def test_build_launcher_config_merges_cli_and_file(tmp_path: Path) -> None:
    config_path = tmp_path / "ragcli.yaml"
    config_path.write_text(
        "backend:\n"
        "  socket: /tmp/backend.sock\n"
        "  weaviate_url: http://localhost:8080\n"
        "  ollama_url: http://localhost:11434\n"
        "  phoenix_url: http://localhost:6006\n"
        "  log_level: warning\n"
        "  trace: true\n",
        encoding="utf-8",
    )

    args = _args(
        config=str(config_path),
        socket="/tmp/cli.sock",
        weaviate_url=None,
        ollama_url=None,
        phoenix_url="http://cli:6006",
        trace=False,
        log_level="DEBUG",
    )

    config = build_launcher_config(args)
    assert isinstance(config, LauncherConfig)
    assert config.socket_path == Path("/tmp/cli.sock")
    assert config.weaviate_url == "http://localhost:8080"
    assert config.ollama_url == "http://localhost:11434"
    assert config.phoenix_url == "http://cli:6006"
    assert config.enable_trace is False
    assert config.log_level == "DEBUG"


def test_build_launcher_config_requires_required_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "ragcli.yaml"
    config_path.write_text(
        "backend:\n  weaviate_url: http://localhost:8080\n", encoding="utf-8"
    )
    args = _args(config=str(config_path))
    with pytest.raises(LauncherConfigError):
        build_launcher_config(args)
