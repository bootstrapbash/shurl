"""
Tests for pluggable body FD splicers (--shurl-splicer and autodetect).
"""
from __future__ import annotations

import shutil

import pytest

from test_deps import _restricted_env, _run, _run_with_pty_stderr

BINARY_NULLS_BODY = b"before\x00after"
MULTIBYTE_BODY = "café".encode()  # 4 chars, 5 UTF-8 bytes
NO_CL_BODY = b"hello without cl\n"


def test_default_uses_cat(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash", "cat")
    r = _run(shurl_script, env, f"{http_server.url}/get")
    assert r.returncode == 0
    assert "hello world" in r.stdout


def test_autodetect_openssl_without_cat(shurl_script, http_server, tmp_path):
    if shutil.which("openssl") is None:
        pytest.skip("openssl not on host PATH")
    env = _restricted_env(tmp_path, "bash", "openssl")
    r = _run(shurl_script, env, f"{http_server.url}/get")
    assert r.returncode == 0
    assert "hello world" in r.stdout


def test_explicit_bashcat_bash_only(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash")
    r = _run(
        shurl_script, env,
        "--shurl-splicer", "bashcat",
        f"{http_server.url}/get",
    )
    assert r.returncode == 0
    assert "hello world" in r.stdout


def test_explicit_openssl(shurl_script, http_server, tmp_path):
    if shutil.which("openssl") is None:
        pytest.skip("openssl not on host PATH")
    env = _restricted_env(tmp_path, "bash", "openssl")
    r = _run(
        shurl_script, env,
        "--shurl-splicer", "openssl",
        f"{http_server.url}/get",
    )
    assert r.returncode == 0
    assert "hello world" in r.stdout


def test_binary_nulls_bashcat(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash")
    out = tmp_path / "body.bin"
    r = _run(
        shurl_script, env,
        "--shurl-splicer", "bashcat",
        "-o", str(out),
        f"{http_server.url}/binary-nulls",
    )
    assert r.returncode == 0
    assert out.read_bytes() == BINARY_NULLS_BODY


def test_multibyte_body_bashcat_byte_count(shurl_script, http_server, tmp_path):
    """bashcat must count UTF-8 bytes (LC_CTYPE=C), not characters, vs Content-Length."""
    assert len(MULTIBYTE_BODY) == 5
    env = _restricted_env(tmp_path, "bash")
    out = tmp_path / "body.bin"
    r = _run(
        shurl_script, env,
        "--shurl-splicer", "bashcat",
        "-o", str(out),
        f"{http_server.url}/multibyte-body",
    )
    assert r.returncode == 0
    assert out.read_bytes() == MULTIBYTE_BODY


def test_binary_nulls_cat(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash", "cat")
    out = tmp_path / "body.bin"
    r = _run(
        shurl_script, env,
        "-o", str(out),
        f"{http_server.url}/binary-nulls",
    )
    assert r.returncode == 0
    assert out.read_bytes() == BINARY_NULLS_BODY


def test_binary_nulls_openssl(shurl_script, http_server, tmp_path):
    if shutil.which("openssl") is None:
        pytest.skip("openssl not on host PATH")
    env = _restricted_env(tmp_path, "bash", "openssl")
    out = tmp_path / "body.bin"
    r = _run(
        shurl_script, env,
        "--shurl-splicer", "openssl",
        "-o", str(out),
        f"{http_server.url}/binary-nulls",
    )
    assert r.returncode == 0
    assert out.read_bytes() == BINARY_NULLS_BODY


def test_bashcat_requires_content_length(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash")
    r = _run(
        shurl_script, env,
        "--shurl-splicer", "bashcat",
        f"{http_server.url}/no-content-length",
    )
    assert r.returncode != 0
    assert "Content-Length" in r.stderr


def test_bashcat_force_without_content_length(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash")
    r = _run(
        shurl_script, env,
        "--shurl-splicer", "bashcat-force",
        f"{http_server.url}/no-content-length",
    )
    assert r.returncode == 0
    assert r.stdout == NO_CL_BODY.decode()


def test_invalid_splicer(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash", "cat")
    r = _run(
        shurl_script, env,
        "--shurl-splicer", "foo",
        f"{http_server.url}/get",
    )
    assert r.returncode != 0
    assert "Unknown splicer" in r.stderr


def test_explicit_cat_unavailable(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash")
    r = _run(
        shurl_script, env,
        "--shurl-splicer", "cat",
        f"{http_server.url}/get",
    )
    assert r.returncode != 0
    assert "cat is not available" in r.stderr


def test_progress_bashcat_no_extra_deps(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash")
    out_file = tmp_path / "body.out"
    proc, pty_output = _run_with_pty_stderr(
        shurl_script, env,
        "--shurl-splicer", "bashcat",
        "-#", "-o", str(out_file),
        f"{http_server.url}/slow-large",
        timeout=15,
    )
    assert proc.returncode == 0
    assert out_file.stat().st_size == 64 * 1024
    assert b"\r" in pty_output
    assert b"not found" not in pty_output


def test_progress_openssl_without_cat(shurl_script, http_server, tmp_path):
    if shutil.which("openssl") is None:
        pytest.skip("openssl not on host PATH")
    env = _restricted_env(tmp_path, "bash", "openssl")
    out_file = tmp_path / "body.out"
    proc, pty_output = _run_with_pty_stderr(
        shurl_script, env,
        "-#", "-o", str(out_file),
        f"{http_server.url}/slow-large",
        timeout=15,
    )
    assert proc.returncode == 0
    assert out_file.stat().st_size == 64 * 1024
    assert b"\r" in pty_output
    assert b"not found" not in pty_output


def test_verbose_logs_splicer(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash", "cat")
    r = _run(
        shurl_script, env,
        "-v", "--shurl-splicer", "cat",
        f"{http_server.url}/get",
    )
    assert r.returncode == 0
    assert "Using splicer: cat" in r.stderr


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"] + sys.argv[1:]))
