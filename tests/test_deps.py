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
import threading

import pytest


def _bash_version(path: str) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [path, "-c", 'echo "${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}"'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        major_str, minor_str = result.stdout.strip().split(".")[:2]
        return int(major_str), int(minor_str)
    except (ValueError, subprocess.TimeoutExpired):
        return None


def _bash_meets_minimum(path: str) -> bool:
    version = _bash_version(path)
    if version is None:
        return False
    major, minor = version
    return major > 4 or (major == 4 and minor >= 1)


def _bootstrap_shells_on_path() -> dict[str, str]:
    """Shell binaries shurl needs on PATH to pass its bootstrap (not runtime deps).

    Tests launch via ``bash shurl`` with a restricted PATH.  On macOS /bin/bash is
    3.2, so shurl re-execs zsh; zsh must be present on that PATH too.
    """
    shells: dict[str, str] = {}
    bash_path = shutil.which("bash")
    if bash_path is None:
        pytest.fail("bash not found on host PATH")

    for candidate in ("bash-5", "bash5", "bash-4", "bash4", "bash"):
        alt_path = shutil.which(candidate)
        if alt_path and _bash_meets_minimum(alt_path):
            shells["bash"] = alt_path
            return shells

    shells["bash"] = bash_path
    if _bash_meets_minimum(bash_path):
        return shells

    zsh_path = shutil.which("zsh")
    if zsh_path:
        shells["zsh"] = zsh_path
        return shells

    pytest.fail("need bash 4.1+ or zsh on host for shurl bootstrap")


def _restricted_env(tmp_path, *allowed_names: str) -> dict:
    """Return an env dict with PATH pointing to a dir containing only the
    named binaries (symlinked from their real locations)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, real_path in _bootstrap_shells_on_path().items():
        (bin_dir / name).symlink_to(real_path)
    for name in allowed_names:
        if name in ("bash", "zsh"):
            continue
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

    stdout is discarded; body goes to a file via -o (passed in args).

    A background thread drains the PTY master while the process runs.  This is
    required: if nobody reads from the master the PTY buffer (~4 KB) fills up
    and bash blocks mid-progress-update, hanging the test.

    Returns (proc, pty_output_bytes).  pty_output_bytes contains everything the
    subprocess wrote to stderr (progress updates, and any error messages such as
    "bash: uname: command not found").
    """
    master_fd, slave_fd = pty.openpty()
    pty_chunks: list[bytes] = []

    def _drain():
        try:
            while True:
                chunk = os.read(master_fd, 4096)
                if not chunk:
                    break
                pty_chunks.append(chunk)
        except OSError:
            pass

    drain_thread = threading.Thread(target=_drain, daemon=True)
    slave_fd_to_close = slave_fd
    try:
        proc = subprocess.Popen(
            ["bash", shurl_script, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=slave_fd,
            env=env,
        )
        # Close our copy of slave_fd so the master gets EIO when the process exits.
        os.close(slave_fd_to_close)
        slave_fd_to_close = -1
        drain_thread.start()
        proc.wait(timeout=timeout)
    finally:
        if slave_fd_to_close >= 0:
            os.close(slave_fd_to_close)
        drain_thread.join(timeout=3.0)
        os.close(master_fd)
    return proc, b"".join(pty_chunks)


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


def test_plain_http_works_with_bashcat_only(shurl_script, http_server, tmp_path):
    """Plain HTTP with no external binaries except bootstrap shell."""
    env = _restricted_env(tmp_path, "bash")
    r = _run(
        shurl_script, env,
        "--shurl-splicer", "bashcat",
        f"{http_server.url}/get",
    )
    assert r.returncode == 0
    assert "hello world" in r.stdout


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
    """Progress bar mode (-# -o) must not call any binaries beyond bash + cat.

    Uses /slow-large (350ms hold before data) so the progress poll loop fires
    before cat exits.  Checks the PTY output for 'not found' to catch any stray
    binary that fails silently (exit-code swallowed by _poll_sleep's || true).
    """
    env = _restricted_env(tmp_path, "bash", "cat")
    out_file = tmp_path / "body.out"
    proc, pty_output = _run_with_pty_stderr(
        shurl_script, env,
        "-#", "-o", str(out_file), f"{http_server.url}/slow-large",
        timeout=15,
    )
    assert proc.returncode == 0
    assert out_file.stat().st_size == 64 * 1024
    assert b"\r" in pty_output, "no progress output seen; poll loop did not run"
    assert b"not found" not in pty_output, f"unexpected external command: {pty_output!r}"


def test_stats_mode_no_extra_deps(shurl_script, http_server, tmp_path):
    """Stats progress mode (-o without -#) must not call any binaries beyond bash + cat."""
    env = _restricted_env(tmp_path, "bash", "cat")
    out_file = tmp_path / "body.out"
    proc, pty_output = _run_with_pty_stderr(
        shurl_script, env,
        "-o", str(out_file), f"{http_server.url}/slow-large",
        timeout=15,
    )
    assert proc.returncode == 0
    assert out_file.stat().st_size == 64 * 1024
    assert b"\r" in pty_output, "no progress output seen; poll loop did not run"
    assert b"not found" not in pty_output, f"unexpected external command: {pty_output!r}"
