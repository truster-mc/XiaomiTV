from pathlib import Path

import pytest

from xiaomitv import collector

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def scan():
    """A Scan built from real output captured from the target TV."""
    def fx(name):
        return (FIX / name).read_text()

    pkgs = collector.parse_packages(fx("system_packages.txt"), fx("user_packages.txt"),
                                    fx("disabled_packages.txt"))
    total, available = collector.parse_proc_meminfo(fx("proc_meminfo.txt"))
    data_total, data_free = collector.parse_df(fx("df.txt"))
    return collector.Scan(
        device={"model": "MiTV-MOOR2"}, mem_total_kb=total, mem_available_kb=available,
        data_total_kb=data_total, data_free_kb=data_free, packages=pkgs,
        pss_kb=collector.parse_pss(fx("meminfo.txt")),
        launcher=collector.parse_home(fx("home.txt")))


def _echo_handler(command):
    if command.startswith("pm disable-user --user 0 "):
        return f"Package {command.split()[-1]} new state: disabled-user"
    if command.startswith("pm enable --user 0 "):
        return f"Package {command.split()[-1]} new state: enabled"
    return None


@pytest.fixture
def fake_adb():
    from tests.fakes import FakeAdb

    def fx(name):
        return (FIX / name).read_text()

    responses = {
        collector.PM_SYSTEM: fx("system_packages.txt"),
        collector.PM_USER: fx("user_packages.txt"),
        collector.PM_DISABLED: fx("disabled_packages.txt"),
        collector.MEMINFO: fx("meminfo.txt"),
        collector.PROC_MEMINFO: fx("proc_meminfo.txt"),
        collector.DF: fx("df.txt"),
        collector.HOME: fx("home.txt"),
    }
    for prop, value in zip(collector.PROPS.values(), fx("props.txt").splitlines()):
        responses[f"getprop {prop}"] = value + "\n"
    return FakeAdb(responses, handler=_echo_handler)


@pytest.fixture
def client(fake_adb, tmp_path):
    from xiaomitv.server import create_app
    app = create_app(fake_adb, tmp_path / "backups", tmp_path / "changes.log")
    return app.test_client()
