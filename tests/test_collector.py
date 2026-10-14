from pathlib import Path

from tests.fakes import FakeAdb
from xiaomitv import collector
from xiaomitv.collector import (parse_df, parse_home, parse_packages,
                                parse_proc_meminfo, parse_pss)

FIX = Path(__file__).parent / "fixtures"


def fx(name: str) -> str:
    return (FIX / name).read_text()


def packages():
    return parse_packages(fx("system_packages.txt"), fx("user_packages.txt"),
                          fx("disabled_packages.txt"))


def test_parse_packages_counts_and_flags():
    pkgs = {p.name: p for p in packages()}
    assert len(pkgs) == 132
    assert sum(p.system for p in pkgs.values()) == 129
    assert not pkgs["com.mitv.tvhome.mitvplus"].enabled
    assert not pkgs["com.amazon.amazonvideo.livingroom"].enabled
    assert not pkgs["com.google.android.youtube.tvmusic"].enabled
    assert not pkgs["org.videolan.vlc"].system
    assert pkgs["org.videolan.vlc"].enabled
    assert pkgs["com.mitv.livetv"].path.endswith(".apk")


def test_parse_pss_folds_process_suffixes_into_package():
    pss = parse_pss(fx("meminfo.txt"))
    assert pss["com.mitv.livetv"] == 120422
    assert pss["com.google.android.katniss"] == 72890
    assert pss["com.google.android.apps.tv.launcherx"] == 56482 + 38789


def test_parse_pss_keeps_non_package_process_names_without_raising():
    pss = parse_pss(fx("meminfo.txt"))
    assert pss["system"] == 120935
    assert pss["dtv_svc_eu"] == 35778


def test_parse_pss_without_section_is_empty():
    assert parse_pss("nothing here") == {}


def test_parse_proc_meminfo():
    total, available = parse_proc_meminfo(fx("proc_meminfo.txt"))
    assert total == 1830516
    assert 0 < available < total


def test_parse_df():
    assert parse_df(fx("df.txt")) == (4200992, 1767320)


def test_parse_home():
    assert parse_home(fx("home.txt")) == "com.google.android.apps.tv.launcherx"
    assert parse_home("") is None


def test_collect_builds_scan_from_fake_adb():
    responses = {
        collector.PM_SYSTEM: fx("system_packages.txt"),
        collector.PM_USER: fx("user_packages.txt"),
        collector.PM_DISABLED: fx("disabled_packages.txt"),
        collector.MEMINFO: fx("meminfo.txt"),
        collector.PROC_MEMINFO: fx("proc_meminfo.txt"),
        collector.DF: fx("df.txt"),
        collector.HOME: fx("home.txt"),
    }
    props = fx("props.txt").splitlines()
    for (key, prop), value in zip(collector.PROPS.items(), props):
        responses[f"getprop {prop}"] = value + "\n"
    scan = collector.collect(FakeAdb(responses))
    assert scan.device["model"] == "MiTV-MOOR2"
    assert scan.device["android"] == "11"
    assert len(scan.packages) == 132
    assert scan.launcher == "com.google.android.apps.tv.launcherx"
    assert scan.data_free_kb == 1767320
    assert scan.pss_kb["com.mitv.livetv"] == 120422
