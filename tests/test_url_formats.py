"""Tests for URL format handling: IPv4, non-default port, IPv6, hostname."""
import platform
import socket

import pytest

_skip_ipv6_macos = pytest.mark.skipif(
    platform.system() == "Darwin",
    reason="zsh ztcp does not support IPv6",
)


def test_ipv4_address(run, http_server):
    """Bare IPv4 address is accepted and connects correctly."""
    assert "127.0.0.1" in http_server.url
    r = run(f"{http_server.url}/get")
    assert r.returncode == 0
    assert r.stdout == "hello world\n"


def test_non_default_port(run, http_server):
    """Non-default port in URL is parsed and used for the connection."""
    assert http_server.port != 80
    r = run(f"http://127.0.0.1:{http_server.port}/get")
    assert r.returncode == 0
    assert r.stdout == "hello world\n"


def test_non_default_port_in_host_header(run, http_server):
    """Non-default port is included in the Host request header."""
    r = run("-v", f"http://127.0.0.1:{http_server.port}/get")
    assert r.returncode == 0
    assert f"> Host: 127.0.0.1:{http_server.port}" in r.stderr


@_skip_ipv6_macos
def test_ipv6_address(run, http_server_ipv6):
    """IPv6 address in bracket notation connects and returns a response."""
    r = run(f"{http_server_ipv6.url}/get")
    assert r.returncode == 0
    assert r.stdout == "hello world\n"


@_skip_ipv6_macos
def test_ipv6_host_header(run, http_server_ipv6):
    """IPv6 Host header retains the bracket notation per RFC 2732."""
    r = run("-v", f"{http_server_ipv6.url}/get")
    assert r.returncode == 0
    assert f"> Host: [::1]:{http_server_ipv6.port}" in r.stderr


# ---------------------------------------------------------------------------
# Hostname (localhost)
# ---------------------------------------------------------------------------

def test_localhost_hostname(run, http_server_localhost):
    """'localhost' hostname resolves and connects correctly."""
    r = run(f"{http_server_localhost}/get")
    assert r.returncode == 0
    assert r.stdout == "hello world\n"


def test_localhost_in_host_header(run, http_server_localhost):
    """'localhost' appears verbatim in the Host header."""
    r = run("-v", f"{http_server_localhost}/get")
    assert r.returncode == 0
    assert any(line.startswith("> Host: localhost") for line in r.stderr.splitlines())


# ---------------------------------------------------------------------------
# Negative: unresolvable hostname
# ---------------------------------------------------------------------------

def test_unresolvable_hostname_exits_nonzero(run):
    """.invalid TLD is guaranteed unresolvable; shurl must exit non-zero."""
    r = run("http://does-not-exist.invalid/")
    assert r.returncode != 0


def test_unresolvable_hostname_error_message(run):
    """shurl prints an error message for unresolvable hostnames."""
    r = run("http://does-not-exist.invalid/")
    assert r.stderr != ""


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"] + sys.argv[1:]))
