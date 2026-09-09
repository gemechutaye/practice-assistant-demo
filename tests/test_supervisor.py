"""Actual child processes verify coupled lifetime and bounded shutdown."""

from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


CHILD = """
from pathlib import Path
import os,signal,sys,time
ready=Path(sys.argv[1]);mode=sys.argv[2];peer=Path(sys.argv[3])
def terminate(*args):
    ready.with_suffix('.terminated').write_text('terminated')
    raise SystemExit(0)
signal.signal(signal.SIGTERM,signal.SIG_IGN if mode=='stubborn' else terminate)
ready.write_text(str(os.getpid()))
if mode.startswith('exit'):
    deadline=time.monotonic()+5
    while not peer.exists() and time.monotonic()<deadline:time.sleep(.01)
    raise SystemExit(int(mode[4:]))
while True:time.sleep(.1)
"""


def wait_for_files(paths):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if all(p.exists() for p in paths):
            return
        time.sleep(0.01)
    raise AssertionError("The test children did not start")


def assert_gone(path):
    with pytest.raises(ProcessLookupError):
        os.kill(int(path.read_text()), 0)


@contextmanager
def running_supervisor(tmp_path, first_mode, second_mode):
    first, second = tmp_path / "api.pid", tmp_path / "worker.pid"
    commands = {
        "api": [sys.executable, "-c", CHILD, str(first), first_mode, str(second)],
        "worker": [sys.executable, "-c", CHILD, str(second), second_mode, str(first)],
    }
    runner = (
        "import logging; logging.basicConfig(level=logging.INFO); "
        "from services.assistant.supervisor import supervise; "
        f"raise SystemExit(supervise({commands!r},shutdown_seconds=.25))"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", runner],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        yield parent, first, second
    finally:
        if parent.poll() is None:
            parent.terminate()
            try:
                parent.wait(timeout=3)
            except subprocess.TimeoutExpired:
                parent.kill()
                parent.wait(timeout=3)
        for path in (first, second):
            if path.exists():
                try:
                    os.killpg(int(path.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass


@pytest.mark.parametrize("exit_code,expected", [(7, 7), (0, 1)])
def test_any_child_exit_stops_sibling_and_fails_combined_service(tmp_path, exit_code, expected):
    with running_supervisor(tmp_path, f"exit{exit_code}", "wait") as (parent, first, second):
        _, errors = parent.communicate(timeout=5)
        assert parent.returncode == expected
        assert second.with_suffix(".terminated").read_text() == "terminated"
        assert b"child_exited name=api" in errors
        assert_gone(first)
        assert_gone(second)


def test_platform_sigterm_reaches_both_children_and_reaps_them(tmp_path):
    with running_supervisor(tmp_path, "wait", "wait") as (parent, first, second):
        wait_for_files([first, second])
        parent.send_signal(signal.SIGTERM)
        parent.communicate(timeout=5)
        assert parent.returncode == 128 + signal.SIGTERM
        assert first.with_suffix(".terminated").exists()
        assert second.with_suffix(".terminated").exists()
        assert_gone(first)
        assert_gone(second)


def test_stubborn_sibling_is_killed_after_bounded_grace_period(tmp_path):
    started = time.monotonic()
    with running_supervisor(tmp_path, "exit9", "stubborn") as (parent, first, second):
        _, errors = parent.communicate(timeout=5)
        assert parent.returncode == 9
        assert not second.with_suffix(".terminated").exists()
        assert b"child_stopped name=worker exit_code=-9" in errors
        assert time.monotonic() - started < 3
        assert_gone(first)
        assert_gone(second)
