"""Shut down the overlay client when the process that launched it disappears."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Mapping, Optional

PARENT_PID_ENV = "EDMC_OVERLAY_PARENT_PID"
_DEFAULT_INTERVAL_MS = 1000
_ERROR_ACCESS_DENIED = 5
_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def resolve_parent_pid(env: Optional[Mapping[str, str]] = None) -> Optional[int]:
    """Return the configured parent PID, or ``None`` when it is absent or invalid."""
    value = (os.environ if env is None else env).get(PARENT_PID_ENV)
    if value is None:
        return None
    try:
        pid = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _is_process_running_windows(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _is_process_running_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def is_process_running(pid: int) -> bool:
    """Return whether ``pid`` identifies a live process on this platform."""
    if pid <= 0:
        return False
    if os.name == "nt":
        return _is_process_running_windows(pid)
    return _is_process_running_posix(pid)


def install_parent_watch(
    app: Any,
    logger: logging.Logger,
    *,
    env: Optional[Mapping[str, str]] = None,
    interval_ms: int = _DEFAULT_INTERVAL_MS,
    is_alive: Callable[[int], bool] = is_process_running,
    timer_factory: Optional[Callable[[Any], Any]] = None,
) -> Optional[Any]:
    """Install a Qt timer that closes ``app`` when the parent process exits."""
    parent_pid = resolve_parent_pid(env)
    if parent_pid is None or parent_pid == os.getpid():
        return None
    if timer_factory is None:
        from PyQt6.QtCore import QTimer

        timer_factory = QTimer
    timer = timer_factory(app)
    timer.setInterval(interval_ms)

    def _check_parent() -> None:
        if is_alive(parent_pid):
            return
        logger.info("Parent process %s exited; shutting down overlay client", parent_pid)
        timer.stop()
        app.quit()

    timer.timeout.connect(_check_parent)
    timer.start()
    logger.debug("Monitoring parent process %s for overlay client lifetime", parent_pid)
    return timer
