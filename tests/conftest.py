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
