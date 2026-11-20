"""Shared pytest fixtures."""

from __future__ import annotations

import socket
from typing import Any

import pytest

_LOOPBACK = {"127.0.0.1", "::1", "localhost", ""}
# Phoenix and OTLP collector ports: never allow span export from tests.
_TRACING_PORTS = {6006, 4317, 4318}


def _is_loopback(address: Any) -> bool:
    if isinstance(address, tuple) and address:
        if len(address) > 1 and address[1] in _TRACING_PORTS:
            return False
        return str(address[0]) in _LOOPBACK
    return isinstance(address, (str, bytes))  # AF_UNIX paths


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Fail any non-loopback socket connection unless the test is marked ``live``."""
    if request.node.get_closest_marker("live"):
        return

    real_connect = socket.socket.connect
    real_create_connection = socket.create_connection

    def guarded_connect(self: socket.socket, address: Any):
        if not _is_loopback(address):
            raise RuntimeError(f"network access blocked in tests: {address!r}")
        return real_connect(self, address)

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any):
        if not _is_loopback(address):
            raise RuntimeError(f"network access blocked in tests: {address!r}")
        return real_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
