import os
import subprocess
import sys
import threading

from scribely.watchdog import pid_alive, watch_parent


def test_pid_alive_for_running_and_finished_processes() -> None:
    assert pid_alive(os.getpid())
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert not pid_alive(child.pid)


def test_watchdog_fires_once_the_parent_is_gone() -> None:
    gone = threading.Event()
    states = iter([True, True, False])
    watch_parent(12345, on_gone=gone.set, interval=0.01, alive=lambda pid: next(states))
    assert gone.wait(2.0)
