from __future__ import annotations

import os
from pathlib import Path

import pytest

from overlay_plugin import overlay_watchdog
from overlay_plugin.overlay_watchdog import PARENT_PID_ENV, OverlayWatchdog


def _build_watchdog(tmp_path: Path, env=None) -> OverlayWatchdog:
    return OverlayWatchdog(
        ["python", "-m", "overlay_client.overlay_client"],
        tmp_path,
        log=lambda _message: None,
        env=env,
    )


def test_child_env_adds_parent_pid_without_mutating_overrides(tmp_path: Path) -> None:
    overrides = {"A": "B"}
    env = _build_watchdog(tmp_path, overrides)._build_child_env()

    assert env["A"] == "B"
    assert env[PARENT_PID_ENV] == str(os.getpid())
    assert PARENT_PID_ENV not in overrides


def test_child_env_inherits_process_environment_without_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MO_TEST_SENTINEL", "1")
    env = _build_watchdog(tmp_path)._build_child_env()

    assert env["MO_TEST_SENTINEL"] == "1"
    assert env[PARENT_PID_ENV] == str(os.getpid())


def test_spawn_overlay_passes_parent_pid_to_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class _FakeProcess:
        pid = 12345
        stdout = None
        stderr = None

    def _fake_popen(_command, **kwargs):
        captured.update(kwargs)
        return _FakeProcess()

    monkeypatch.setattr(overlay_watchdog.subprocess, "Popen", _fake_popen)
    watchdog = _build_watchdog(tmp_path, {"A": "B"})

    watchdog._spawn_overlay()

    assert captured["env"]["A"] == "B"
    assert captured["env"][PARENT_PID_ENV] == str(os.getpid())
