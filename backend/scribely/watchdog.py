"""Exit when the desktop app that launched us goes away (even if it crashed).

The Tauri shell starts the backend with ``SCRIBELY_PARENT_PID`` set to its own pid. A daemon
thread polls that pid and asks the server to shut down cleanly once it's gone, so a crashed
app never leaves an orphaned backend recording in the background.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from collections.abc import Callable

import structlog

PARENT_PID_ENV = "SCRIBELY_PARENT_PID"
log = structlog.get_logger(__name__)


def pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def request_shutdown() -> None:
    """Ask the running server to stop gracefully (finishing any recording), then force it."""
    if sys.platform == "win32":
        import _thread

        _thread.interrupt_main()
    else:
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Timer(15.0, lambda: os._exit(0)).start()


def watch_parent(
    pid: int,
    on_gone: Callable[[], None] = request_shutdown,
    interval: float = 2.0,
    alive: Callable[[int], bool] = pid_alive,
) -> threading.Thread:
    def run() -> None:
        while alive(pid):
            time.sleep(interval)
        log.warning("backend.parent_gone", parent_pid=pid)
        on_gone()

    thread = threading.Thread(target=run, name="scribely-parent-watchdog", daemon=True)
    thread.start()
    return thread


def start_from_env() -> None:
    raw = os.environ.get(PARENT_PID_ENV)
    if not raw:
        return
    try:
        pid = int(raw)
    except ValueError:
        log.warning("backend.bad_parent_pid", value=raw)
        return
    watch_parent(pid)
    log.info("backend.watching_parent", parent_pid=pid)
