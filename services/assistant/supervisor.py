"""Run the API and queue worker together for the on-demand hosted demo.

Both children share the container lifecycle. This process sends no keepalive
traffic and exits if either child stops, allowing the platform to restart it.
"""

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence

log = logging.getLogger("practice_assistant.supervisor")


def _signal_group(process: subprocess.Popen, signum: int) -> None:
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def supervise(commands: Mapping[str, Sequence[str]], shutdown_seconds: float = 8) -> int:
    stopped = threading.Event()
    received_signal = None
    children = {}
    previous_handlers = {}

    def stop(signum, _frame):
        nonlocal received_signal
        received_signal = signum
        stopped.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signum] = signal.signal(signum, stop)
    try:
        for name, command in commands.items():
            if stopped.is_set():
                break
            child = subprocess.Popen(command, start_new_session=True)
            children[name] = child
            log.info("child_started name=%s pid=%s", name, child.pid)
        while not stopped.is_set():
            for name, child in children.items():
                result = child.poll()
                if result is not None:
                    log.error("child_exited name=%s exit_code=%s", name, result)
                    # Even a clean child exit means the combined service is incomplete.
                    return result if result > 0 else (128 - result if result < 0 else 1)
            stopped.wait(0.1)
        return 128 + received_signal if received_signal is not None else 0
    except OSError as error:
        log.error("child_start_failed error_type=%s", type(error).__name__)
        return 1
    finally:
        # Signal groups, including children spawned by a server process. Reap each
        # direct child after giving both the same bounded shutdown window.
        for child in children.values():
            _signal_group(child, signal.SIGTERM)
        deadline = time.monotonic() + shutdown_seconds
        for child in children.values():
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        for name, child in children.items():
            # Kill the group even if its original leader has exited, so no
            # surviving descendants can remain after the supervisor stops.
            _signal_group(child, signal.SIGKILL)
            child.wait()
            log.info("child_stopped name=%s exit_code=%s", name, child.returncode)
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(
        supervise(
            {
                "api": [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "services.assistant.api:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    os.getenv("PORT", "10000"),
                ],
                "worker": [sys.executable, "-m", "services.assistant.worker"],
            }
        )
    )


if __name__ == "__main__":
    main()
