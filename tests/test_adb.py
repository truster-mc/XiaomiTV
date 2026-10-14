import subprocess

import pytest

from xiaomitv.adb import Adb, AdbError, AdbNotInstalled, TvUnreachable, Unauthorized


def completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def patch_run(monkeypatch, handler):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return handler(cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_connect_ok(monkeypatch):
    def handler(cmd):
        if "connect" in cmd:
            return completed("connected to 1.2.3.4:5555\n")
        return completed("List of devices attached\n1.2.3.4:5555\tdevice\n")

    patch_run(monkeypatch, handler)
    adb = Adb()
    adb.connect("1.2.3.4")
    assert adb.serial == "1.2.3.4:5555"


def test_connect_unauthorized(monkeypatch):
    def handler(cmd):
        if "connect" in cmd:
            return completed("failed to authenticate to 1.2.3.4:5555\n")
        return completed("List of devices attached\n1.2.3.4:5555\tunauthorized\n")

    patch_run(monkeypatch, handler)
    with pytest.raises(Unauthorized) as exc:
        Adb().connect("1.2.3.4")
    assert "Allow USB debugging" in exc.value.hint


def test_connect_unreachable(monkeypatch):
    patch_run(monkeypatch, lambda cmd: completed(
        "failed to connect to '1.2.3.4:5555': Connection refused\n"))
    with pytest.raises(TvUnreachable):
        Adb().connect("1.2.3.4")


def test_missing_binary(monkeypatch):
    def boom(cmd, **kwargs):
        raise FileNotFoundError("adb")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(AdbNotInstalled) as exc:
        Adb().connect("1.2.3.4")
    assert "sudo apt install adb" in exc.value.hint


def test_shell_builds_command(monkeypatch):
    calls = patch_run(monkeypatch, lambda cmd: completed("ok\n"))
    adb = Adb()
    adb.serial = "1.2.3.4:5555"
    assert adb.shell("pm list packages") == "ok\n"
    assert calls[0] == ["adb", "-s", "1.2.3.4:5555", "shell", "pm list packages"]


def test_shell_nonzero_raises_adberror(monkeypatch):
    patch_run(monkeypatch, lambda cmd: completed("", 1, "error: device offline"))
    adb = Adb()
    adb.serial = "1.2.3.4:5555"
    with pytest.raises(AdbError):
        adb.shell("pm list packages")


def test_shell_without_connection_raises_adberror():
    with pytest.raises(AdbError):
        Adb().shell("pm list packages")


def test_shell_device_gone_gives_hinted_unreachable(monkeypatch):
    for stderr in ("error: device '1.2.3.4:5555' not found", "error: device offline",
                   "error: no devices/emulators found"):
        patch_run(monkeypatch, lambda cmd, s=stderr: completed("", 1, s))
        adb = Adb()
        adb.serial = "1.2.3.4:5555"
        with pytest.raises(TvUnreachable) as exc:
            adb.shell("pm list packages")
        assert exc.value.hint, stderr


def test_shell_unauthorized_after_connect(monkeypatch):
    patch_run(monkeypatch, lambda cmd: completed("", 1, "error: device unauthorized."))
    adb = Adb()
    adb.serial = "1.2.3.4:5555"
    with pytest.raises(Unauthorized) as exc:
        adb.shell("pm list packages")
    assert exc.value.hint


def test_oserror_from_subprocess_becomes_adberror(monkeypatch):
    def boom(cmd, **kwargs):
        raise PermissionError("not executable")

    monkeypatch.setattr(subprocess, "run", boom)
    adb = Adb()
    adb.serial = "x:5555"
    with pytest.raises(AdbError):
        adb.shell("true")
