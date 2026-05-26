"""Tests for error handling."""
import pytest


# ---------------------------------------------------------------------------
# HTTP error status codes
# ---------------------------------------------------------------------------

def test_404_exits_nonzero(run, http_server):
    r = run(f"{http_server.url}/notfound")
    assert r.returncode != 0


def test_404_error_message(run, http_server):
    r = run(f"{http_server.url}/notfound")
    assert "404" in r.stderr


def test_401_exits_nonzero(run, http_server):
    r = run(f"{http_server.url}/unauthorized")
    assert r.returncode != 0


def test_401_error_message(run, http_server):
    r = run(f"{http_server.url}/unauthorized")
    assert "401" in r.stderr


def test_403_exits_nonzero(run, http_server):
    r = run(f"{http_server.url}/forbidden")
    assert r.returncode != 0


def test_403_error_message(run, http_server):
    r = run(f"{http_server.url}/forbidden")
    assert "403" in r.stderr


def test_500_exits_nonzero(run, http_server):
    r = run(f"{http_server.url}/servererror")
    assert r.returncode != 0


def test_500_error_message(run, http_server):
    r = run(f"{http_server.url}/servererror")
    assert "500" in r.stderr


# ---------------------------------------------------------------------------
# Connection-level errors
# ---------------------------------------------------------------------------

def test_connection_refused(run):
    r = run("http://127.0.0.1:19999/")
    assert r.returncode != 0
    assert "Could not connect to" in r.stderr


def test_https_to_plain_http_port_fails(run, http_server):
    """Connecting via HTTPS to a non-TLS port fails with a TLS-specific message."""
    https_url = http_server.url.replace("http://", "https://")
    r = run(f"{https_url}/get", timeout=15)
    assert r.returncode != 0
    assert "TLS" in r.stderr or "not an HTTPS server" in r.stderr


# ---------------------------------------------------------------------------
# URL format errors
# ---------------------------------------------------------------------------

def test_bad_url_no_host(run):
    r = run("http:///path")
    assert r.returncode != 0


def test_unsupported_scheme(run):
    """Non-http/https schemes are rejected with a clear error."""
    r = run("ftp://example.com/file.txt")
    assert r.returncode != 0
    assert "Malformed URL" in r.stderr


def test_non_numeric_port(run):
    """A non-numeric port in the URL is rejected as malformed."""
    r = run("http://127.0.0.1:abc/")
    assert r.returncode != 0
    assert "Malformed URL" in r.stderr


# ---------------------------------------------------------------------------
# Flag validation errors
# ---------------------------------------------------------------------------

def test_max_redirs_non_numeric(run, http_server):
    """--max-redirs rejects non-integer values."""
    r = run("-L", "--max-redirs", "abc", f"{http_server.url}/get")
    assert r.returncode != 0
    assert "integer" in r.stderr


def test_max_redirs_negative(run, http_server):
    """--max-redirs rejects negative values."""
    r = run("-L", "--max-redirs", "-1", f"{http_server.url}/get")
    assert r.returncode != 0


def test_auth_missing_colon(run, http_server):
    """-u requires user:pass format; bare username without colon is rejected."""
    r = run("-u", "useronly", f"{http_server.url}/get")
    assert r.returncode != 0
    assert "user:pass" in r.stderr


def test_option_after_url(run, http_server):
    """Options after the URL are rejected."""
    r = run(f"{http_server.url}/get", "-v")
    assert r.returncode != 0
    assert "option after URL" in r.stderr
    assert "-v" in r.stderr


# ---------------------------------------------------------------------------
# Output suppression
# ---------------------------------------------------------------------------

def test_redirect_without_follow_flag(run, http_server):
    r = run(f"{http_server.url}/redirect301")
    assert r.returncode != 0
    assert "301" in r.stderr


def test_silent_suppresses_stderr(run, http_server):
    r = run("-s", f"{http_server.url}/notfound")
    assert r.returncode != 0
    assert r.stderr == ""


def test_silent_no_output_on_success(run, http_server):
    r = run("-s", "-o", "/dev/null", f"{http_server.url}/get")
    assert r.returncode == 0
    assert r.stderr == ""


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"] + sys.argv[1:]))
