"""
Verify that shurl only uses the declared external dependencies.

Runs the script with PATH restricted to a temp directory containing only
symlinks to the allowed binaries.  If the script invokes anything else it
gets "command not found" and fails, making the test self-enforcing.

This also serves as positive proof that each dependency is actually needed
(e.g. openssl is required for HTTPS but not for plain HTTP).

Progress-mode tests use pty.openpty() to give the subprocess a real TTY on
stderr, which causes -t 2 to succeed and activates _progress_mode.  Without a
real TTY stderr the progress path is never entered and any stray dep added
there would go undetected.
"""
from __future__ import annotations

import os
import pty
import shutil
import subprocess

import pytest


def _restricted_env(tmp_path, *allowed_names: str) -> dict:
    """Return an env dict with PATH pointing to a dir containing only the
    named binaries (symlinked from their real locations)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in allowed_names:
        real = shutil.which(name)
        assert real is not None, f"{name} not found on host PATH"
        (bin_dir / name).symlink_to(real)
    return {**os.environ, "PATH": str(bin_dir)}


def _run(shurl_script, env, *args, timeout=10):
    return subprocess.run(
        ["bash", shurl_script, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _run_with_pty_stderr(shurl_script, env, *args, timeout=15):
    """Run shurl with a real PTY as stderr so -t 2 is true and progress mode fires.

    stdout is discarded; body goes to a file via -o (passed in args).  Returns
    the CompletedProcess (no stdout/stderr text since stderr goes to the pty).
    """
    master_fd, slave_fd = pty.openpty()
    try:
        result = subprocess.run(
            ["bash", shurl_script, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=slave_fd,
            env=env,
            timeout=timeout,
        )
    finally:
        os.close(slave_fd)
        os.close(master_fd)
    return result


# ---------------------------------------------------------------------------
# Plain HTTP: only cat should be needed at runtime
# ---------------------------------------------------------------------------

def test_plain_http_works_with_only_cat(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash", "cat")
    r = _run(shurl_script, env, f"{http_server.url}/get")
    assert r.returncode == 0
    assert "hello world" in r.stdout


def test_plain_http_post_works_with_only_cat(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash", "cat")
    r = _run(shurl_script, env, "-d", "x=1", f"{http_server.url}/echo-body")
    assert r.returncode == 0
    assert r.stdout == "x=1"


# ---------------------------------------------------------------------------
# HTTPS: requires openssl (and cat for body)
# ---------------------------------------------------------------------------

def test_https_works_with_openssl_and_cat(shurl_script, https_server, tmp_path):
    env = _restricted_env(tmp_path, "bash", "openssl", "cat")
    r = _run(shurl_script, env, f"{https_server.url}/get")
    assert r.returncode == 0
    assert "hello world" in r.stdout


def test_https_fails_without_openssl(shurl_script, https_server, tmp_path):
    """HTTPS should fail with a clear error when openssl is absent."""
    env = _restricted_env(tmp_path, "bash", "cat")
    r = _run(shurl_script, env, f"{https_server.url}/get")
    assert r.returncode != 0
    assert "openssl" in r.stderr


# ---------------------------------------------------------------------------
# Basic auth: requires openssl for base64 encoding
# ---------------------------------------------------------------------------

def test_basic_auth_works_with_openssl(shurl_script, http_server, tmp_path):
    env = _restricted_env(tmp_path, "bash", "openssl", "cat")
    r = _run(shurl_script, env, "-u", "user:pass", f"{http_server.url}/get")
    assert r.returncode == 0


def test_basic_auth_fails_without_openssl(shurl_script, http_server, tmp_path):
    """Basic auth base64 encoding should fail clearly when openssl is absent."""
    env = _restricted_env(tmp_path, "bash", "cat")
    r = _run(shurl_script, env, "-u", "user:pass", f"{http_server.url}/get")
    assert r.returncode != 0
    assert "openssl" in r.stderr


# ---------------------------------------------------------------------------
# Progress mode: requires a real TTY on stderr to activate (-t 2).
# These tests use pty.openpty() to satisfy that check and exercise the
# transfer_body progress path, catching any stray external dep added there.
# ---------------------------------------------------------------------------

def test_progress_bar_no_extra_deps(shurl_script, http_server, tmp_path):
    """Progress bar mode (-# -o) must not call any binaries beyond bash + cat."""
    env = _restricted_env(tmp_path, "bash", "cat")
    out_file = tmp_path / "body.out"
    r = _run_with_pty_stderr(
        shurl_script, env,
        "-#", "-o", str(out_file), f"{http_server.url}/large",
        timeout=15,
    )
    assert r.returncode == 0
    assert out_file.stat().st_size == 1024 * 1024


def test_stats_mode_no_extra_deps(shurl_script, http_server, tmp_path):
    """Stats progress mode (-o without -#) must not call any binaries beyond bash + cat."""
    env = _restricted_env(tmp_path, "bash", "cat")
    out_file = tmp_path / "body.out"
    r = _run_with_pty_stderr(
        shurl_script, env,
        "-o", str(out_file), f"{http_server.url}/large",
    )
    assert r.returncode == 0
    assert out_file.stat().st_size == 1024 * 1024
