"""Tests for error handling."""
import pytest


# ---------------------------------------------------------------------------
# HTTP error status codes (curl default: body printed, exit 0)
# ---------------------------------------------------------------------------

def test_404_exits_zero_with_body(run, http_server):
    r = run(f"{http_server.url}/notfound")
    assert r.returncode == 0
    assert r.stdout == "Not Found"
    assert r.stderr == ""


def test_401_exits_zero_with_body(run, http_server):
    r = run(f"{http_server.url}/unauthorized")
    assert r.returncode == 0
    assert r.stdout == "Unauthorized"


def test_403_exits_zero_with_body(run, http_server):
    r = run(f"{http_server.url}/forbidden")
    assert r.returncode == 0
    assert r.stdout == "Forbidden"


def test_500_exits_zero_with_body(run, http_server):
    r = run(f"{http_server.url}/servererror")
    assert r.returncode == 0
    assert r.stdout == "Internal Server Error"


def test_400_json_body_on_stdout(run, http_server):
    r = run(f"{http_server.url}/badrequest")
    assert r.returncode == 0
    assert "query is bad" in r.stdout


# ---------------------------------------------------------------------------
# -f / --fail (curl: suppress body, exit 22)
# ---------------------------------------------------------------------------

def test_fail_exits_22_on_404(run, http_server):
    r = run("-f", f"{http_server.url}/notfound")
    assert r.returncode == 22


def test_fail_suppresses_body(run, http_server):
    r = run("-f", f"{http_server.url}/notfound")
    assert r.stdout == ""


def test_fail_shows_message(run, http_server):
    r = run("-f", f"{http_server.url}/notfound")
    assert "404" in r.stderr


def test_fail_silent_no_message(run, http_server):
    r = run("-s", "-f", f"{http_server.url}/notfound")
    assert r.returncode == 22
    assert r.stderr == ""


def test_fail_sS_shows_message(run, http_server):
    r = run("-sS", "-f", f"{http_server.url}/notfound")
    assert r.returncode == 22
    assert "404" in r.stderr


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
    """Options after the URL are accepted (curl-compatible)."""
    r = run(f"{http_server.url}/echo-body", "-d", "x=1")
    assert r.returncode == 0
    assert r.stdout == "x=1"


def test_post_flag_after_url(run, http_server):
    r = run("-X", "POST", f"{http_server.url}/echo-body", "-d", '{"a":1}')
    assert r.returncode == 0
    assert r.stdout == '{"a":1}'


# ---------------------------------------------------------------------------
# Output suppression (-s / -S)
# ---------------------------------------------------------------------------

def test_redirect_without_follow_exits_zero(run, http_server):
    r = run(f"{http_server.url}/redirect301")
    assert r.returncode == 0
    assert "301" not in r.stderr


def test_silent_shows_parse_error(run, http_server):
    r = run("-s", "-w", f"{http_server.url}/get")
    assert r.returncode != 0
    assert "Unknown option" in r.stderr


def test_silent_no_output_on_success(run, http_server):
    r = run("-s", "-o", "/dev/null", f"{http_server.url}/get")
    assert r.returncode == 0
    assert r.stderr == ""


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"] + sys.argv[1:]))
