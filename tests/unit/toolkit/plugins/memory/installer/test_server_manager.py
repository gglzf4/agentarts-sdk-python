"""Tests for server_manager (start/stop/status)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import agentarts.toolkit.plugins.memory.installer.server_manager as sm
from agentarts.toolkit.plugins.memory.installer.server_manager import (
    start,
    status,
    stop,
)


def _set_home(monkeypatch, tmp_path):
    """Redirect all ~ paths to tmp_path."""
    monkeypatch.setenv("HOME", str(tmp_path))


def _pid_file(tmp_path):
    return Path(tmp_path) / ".agentarts" / "server.pid"


def _write_pid_file(tmp_path, pid: int):
    p = _pid_file(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(pid))


# ── start ───────────────────────────────────────────────────────────


class TestStart:
    def test_already_running(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        _write_pid_file(tmp_path, 99999)
        monkeypatch.setattr(sm, "_is_process_alive", lambda pid: True)

        assert start() == 0

    def test_process_dies_immediately(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        monkeypatch.setattr(sm, "_is_running", lambda: False)
        monkeypatch.setattr(sm.time, "sleep", lambda x: None)

        mock_proc = MagicMock()
        mock_proc.pid = 11111
        mock_proc.poll.return_value = 1
        monkeypatch.setattr(sm.subprocess, "Popen", lambda *a, **kw: mock_proc)

        assert start() == 1
        assert not _pid_file(tmp_path).exists()

    def test_starts_and_health_check_ok(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        monkeypatch.setattr(sm, "_is_running", lambda: False)
        monkeypatch.setattr(sm.time, "sleep", lambda x: None)

        mock_proc = MagicMock()
        mock_proc.pid = 22222
        mock_proc.poll.return_value = None
        monkeypatch.setattr(sm.subprocess, "Popen", lambda *a, **kw: mock_proc)
        monkeypatch.setattr(sm, "_check_health", lambda: True)

        assert start() == 0
        assert _pid_file(tmp_path).read_text() == "22222"

    def test_starts_but_health_check_fails(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        monkeypatch.setattr(sm, "_is_running", lambda: False)
        monkeypatch.setattr(sm.time, "sleep", lambda x: None)

        mock_proc = MagicMock()
        mock_proc.pid = 33333
        mock_proc.poll.return_value = None
        monkeypatch.setattr(sm.subprocess, "Popen", lambda *a, **kw: mock_proc)
        monkeypatch.setattr(sm, "_check_health", lambda: False)

        # Health check failure does NOT mean start failed — process is alive.
        assert start() == 0
        assert _pid_file(tmp_path).read_text() == "33333"

    def test_start_invokes_in_package_module(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        monkeypatch.setattr(sm, "_is_running", lambda: False)
        monkeypatch.setattr(sm.time, "sleep", lambda x: None)

        captured = {}

        def fake_popen(cmd, *a, **kw):
            captured["cmd"] = cmd
            mock_proc = MagicMock()
            mock_proc.pid = 44444
            mock_proc.poll.return_value = None
            return mock_proc

        monkeypatch.setattr(sm.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(sm, "_check_health", lambda: True)

        assert start() == 0
        assert captured["cmd"] == [sys.executable, "-m", sm.SERVER_MODULE]


# ── stop ────────────────────────────────────────────────────────────


class TestStop:
    def test_not_running_no_pid(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        assert stop() == 0

    def test_not_running_stale_pid(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        _write_pid_file(tmp_path, 88888)
        monkeypatch.setattr(sm, "_is_process_alive", lambda pid: False)

        assert stop() == 0
        assert not _pid_file(tmp_path).exists()

    def test_running_terminates(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        _write_pid_file(tmp_path, 77777)
        monkeypatch.setattr(sm.time, "sleep", lambda x: None)

        state = {"alive": True}

        def fake_is_alive(pid):
            return state["alive"]

        kill_calls = []

        def fake_kill(pid, sig):
            kill_calls.append((pid, sig))
            if sig == sm.signal.SIGTERM:
                state["alive"] = False

        monkeypatch.setattr(sm, "_is_process_alive", fake_is_alive)
        monkeypatch.setattr("os.kill", fake_kill)

        assert stop() == 0
        assert (77777, sm.signal.SIGTERM) in kill_calls
        assert not _pid_file(tmp_path).exists()

    def test_permission_denied(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        _write_pid_file(tmp_path, 66666)
        monkeypatch.setattr(sm, "_is_process_alive", lambda pid: True)

        def fake_kill(pid, sig):
            raise PermissionError(1, "Permission denied")

        monkeypatch.setattr("os.kill", fake_kill)

        assert stop() == 1
        # PID file should remain since we could not stop the process.
        assert _pid_file(tmp_path).exists()

    def test_force_kill_when_sigterm_fails(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        _write_pid_file(tmp_path, 55555)
        monkeypatch.setattr(sm, "_is_process_alive", lambda pid: True)
        monkeypatch.setattr(sm.time, "sleep", lambda x: None)

        # Make time.monotonic advance past deadline quickly.
        counter = [0]
        monkeypatch.setattr(
            sm.time, "monotonic", lambda: (counter.__setitem__(0, counter[0] + 1), counter[0])[1]
        )

        kill_calls = []
        monkeypatch.setattr("os.kill", lambda pid, sig: kill_calls.append((pid, sig)))

        assert stop() == 0
        assert (55555, sm.signal.SIGTERM) in kill_calls
        assert (55555, sm.signal.SIGKILL) in kill_calls
        assert not _pid_file(tmp_path).exists()


# ── status ──────────────────────────────────────────────────────────


class TestStatus:
    def test_not_running_no_pid(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        assert status() == 1

    def test_not_running_stale_pid(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        _write_pid_file(tmp_path, 44444)
        monkeypatch.setattr(sm, "_is_process_alive", lambda pid: False)

        assert status() == 1
        assert not _pid_file(tmp_path).exists()

    def test_running_healthy(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        _write_pid_file(tmp_path, 33333)
        monkeypatch.setattr(sm, "_is_process_alive", lambda pid: True)
        monkeypatch.setattr(sm, "_check_health", lambda: True)

        assert status() == 0

    def test_running_unhealthy(self, monkeypatch, tmp_path):
        _set_home(monkeypatch, tmp_path)
        _write_pid_file(tmp_path, 22222)
        monkeypatch.setattr(sm, "_is_process_alive", lambda pid: True)
        monkeypatch.setattr(sm, "_check_health", lambda: False)

        assert status() == 1
        # PID file should remain since the process IS alive.
        assert _pid_file(tmp_path).exists()
