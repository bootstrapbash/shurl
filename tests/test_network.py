"""Tests against real external hosts.  Skipped when the network is unavailable.

These tests exercise DNS resolution and real TCP connections; they are not
suitable for offline or sandboxed CI environments.  Run with:

    pytest tests/test_network.py -v
"""
import socket
import time

import pytest


def _can_reach(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


network = pytest.mark.skipif(
    not _can_reach("example.com", 80),
    reason="network unavailable",
)


@network
def test_example_com_get(run):
    """GET http://example.com/ succeeds and returns an HTML body."""
    r = run("http://example.com/", timeout=30)
    assert r.returncode == 0
    assert "Example Domain" in r.stdout


@network
def test_example_com_head(run):
    """HEAD request to example.com returns headers with no body."""
    time.sleep(1)  # rate-limit: allow time between outbound connections
    r = run("-I", "http://example.com/", timeout=30)
    assert r.returncode == 0
    assert "HTTP/1" in r.stdout
    assert r.stdout.strip() != ""
    assert "Example Domain" not in r.stdout


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"] + sys.argv[1:]))
