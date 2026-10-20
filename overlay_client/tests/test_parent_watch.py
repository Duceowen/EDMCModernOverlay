from __future__ import annotations

import logging
import os

import pytest

from overlay_client import parent_watch


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self) -> None:
        for callback in list(self._callbacks):
            callback()


class _FakeTimer:
    def __init__(self, _parent) -> None:
        self.timeout = _FakeSignal()
        self.interval: int | None = None
        self.started = False
        self.stopped = False

    def setInterval(self, value: int) -> None:
        self.interval = value

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class _FakeApp:
    def __init__(self) -> None:
        self.quit_called = False

    def quit(self) -> None:
        self.quit_called = True


def test_resolve_parent_pid_returns_none_when_missing() -> None:
    assert parent_watch.resolve_parent_pid({}) is None


def test_resolve_parent_pid_parses_value() -> None:
    assert parent_watch.resolve_parent_pid({parent_watch.PARENT_PID_ENV: " 123 "}) == 123


@pytest.mark.parametrize("value", ["", "abc", "0", "-1"])
def test_resolve_parent_pid_rejects_invalid_values(value: str) -> None:
    assert parent_watch.resolve_parent_pid({parent_watch.PARENT_PID_ENV: value}) is None


def test_is_process_running_detects_current_process() -> None:
    assert parent_watch.is_process_running(os.getpid()) is True


def test_is_process_running_rejects_missing_process() -> None:
    assert parent_watch.is_process_running(2**31 - 1) is False


def test_install_parent_watch_quits_when_parent_exits() -> None:
    app = _FakeApp()
    timer = parent_watch.install_parent_watch(
        app,
        logging.getLogger(__name__),
        env={parent_watch.PARENT_PID_ENV: "12345"},
        is_alive=lambda _pid: False,
        timer_factory=_FakeTimer,
    )

    assert isinstance(timer, _FakeTimer)
    assert timer.started is True
    assert timer.interval == parent_watch._DEFAULT_INTERVAL_MS

    timer.timeout.emit()

    assert app.quit_called is True
    assert timer.stopped is True


def test_install_parent_watch_keeps_running_while_parent_is_alive() -> None:
    app = _FakeApp()
    checked_pids: list[int] = []

    def _is_alive(pid: int) -> bool:
        checked_pids.append(pid)
        return True

    timer = parent_watch.install_parent_watch(
        app,
        logging.getLogger(__name__),
        env={parent_watch.PARENT_PID_ENV: "12345"},
        is_alive=_is_alive,
        timer_factory=_FakeTimer,
    )

    assert isinstance(timer, _FakeTimer)
    timer.timeout.emit()

    assert checked_pids == [12345]
    assert app.quit_called is False
    assert timer.stopped is False


def test_install_parent_watch_ignores_missing_or_self_pid() -> None:
    logger = logging.getLogger(__name__)
    assert parent_watch.install_parent_watch(_FakeApp(), logger, env={}, timer_factory=_FakeTimer) is None
    assert (
        parent_watch.install_parent_watch(
            _FakeApp(),
            logger,
            env={parent_watch.PARENT_PID_ENV: str(os.getpid())},
            timer_factory=_FakeTimer,
        )
        is None
    )
