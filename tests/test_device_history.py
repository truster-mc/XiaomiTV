import dataclasses
import json
from datetime import datetime

import pytest

from tests.fakes import FakeAdb
from xiaomitv import collector
from xiaomitv.actions import disable_packages
from xiaomitv.backup import (BackupError, create_snapshot, list_snapshots, load_snapshot,
                             snapshot_matches)
from xiaomitv.models import device_id
from xiaomitv.server import create_app

NOW = datetime(2026, 10, 15, 9, 0, 0)
XIAOMI = {"manufacturer": "Xiaomi", "model": "MiTV-MOOR2", "android": "11", "sdk": "30"}
TCL = {"manufacturer": "TCL", "model": "Smart TV", "device": "BeyondTV4", "android": "11",
       "serial": "TCL-1"}


def test_device_id_prefers_the_serial_and_falls_back_to_model_fields():
    assert device_id({"serial": "ABC", "model": "x"}) == "serial:ABC"
    assert device_id(XIAOMI) == "Xiaomi|MiTV-MOOR2|"
    assert device_id(TCL | {"serial": ""}) == "TCL|Smart TV|BeyondTV4"


def test_new_snapshots_carry_the_device_id(scan, tmp_path):
    scan = dataclasses.replace(scan, device=TCL)
    snap_id = create_snapshot(scan, {}, tmp_path, now=NOW)
    assert load_snapshot(tmp_path, snap_id)["device_id"] == "serial:TCL-1"


def test_snapshot_matching_new_and_legacy(scan, tmp_path):
    tagged = {"device_id": "serial:TCL-1", "device": TCL, "packages": {}}
    assert snapshot_matches(tagged, TCL)
    assert not snapshot_matches(tagged, TCL | {"serial": "TCL-2"})
    legacy_xiaomi = {"device": XIAOMI, "packages": {}}           # no device_id, no codename
    assert snapshot_matches(legacy_xiaomi, XIAOMI)
    assert not snapshot_matches(legacy_xiaomi, TCL)
    legacy_tcl = {"device": TCL | {"serial": ""}, "packages": {}}
    assert snapshot_matches(legacy_tcl, TCL)
    assert not snapshot_matches(legacy_tcl, TCL | {"device": "OtherCodename", "serial": ""})
    assert not snapshot_matches({"packages": {}}, TCL)           # nothing to go on


def test_list_snapshots_only_shows_the_connected_tv(scan, tmp_path):
    create_snapshot(dataclasses.replace(scan, device=XIAOMI), {}, tmp_path,
                    now=datetime(2026, 10, 14, 10, 0, 0))
    create_snapshot(dataclasses.replace(scan, device=TCL), {}, tmp_path, now=NOW)
    assert [i["id"] for i in list_snapshots(tmp_path, TCL)] == ["20261015-090000"]
    assert [i["id"] for i in list_snapshots(tmp_path, XIAOMI)] == ["20261014-100000"]
    assert len(list_snapshots(tmp_path)) == 2                      # no device given: all
    assert list_snapshots(tmp_path, TCL)[0]["device"] == "Smart TV"


def test_log_entries_carry_the_device_id(tmp_path):
    fake = FakeAdb({"pm disable-user --user 0 com.a.one": "Package com.a.one new state: disabled-user"})
    log = tmp_path / "log"
    list(disable_packages(fake, ["com.a.one"], log, device_id="serial:TCL-1"))
    assert json.loads(log.read_text())["device_id"] == "serial:TCL-1"


# ---- through the API, with two different TVs on the same laptop ----

def set_tv(fake_adb, device):
    for key, prop in collector.PROPS.items():
        fake_adb.responses[f"getprop {prop}"] = device.get(key, "") + "\n"


@pytest.fixture
def two_tvs(fake_adb, tmp_path):
    set_tv(fake_adb, XIAOMI | {"serial": "XIA-1"})
    client = create_app(fake_adb, tmp_path / "b", tmp_path / "log").test_client()
    return client, fake_adb


def apply(client, packages):
    resp = client.post("/api/apply", json={"packages": packages})
    assert resp.status_code == 200
    return [json.loads(l) for l in resp.get_data(as_text=True).splitlines()]


def test_other_tvs_history_does_not_leak(two_tvs):
    client, fake = two_tvs
    client.post("/api/scan", json={})
    snap = apply(client, ["com.miui.tv.analytics"])[0]["snapshot"]
    assert client.get("/api/backups").json["backups"][0]["id"] == snap

    set_tv(fake, TCL)                                   # now the TCL is connected
    scan = client.post("/api/scan", json={}).json
    assert scan["reenabled_since_backup"] == []         # the Xiaomi's log must not flag the TCL
    assert client.get("/api/backups").json["backups"] == []

    set_tv(fake, XIAOMI | {"serial": "XIA-1"})          # back to the Xiaomi
    assert client.post("/api/scan", json={}).json["reenabled_since_backup"] == ["com.miui.tv.analytics"]
    assert client.get("/api/backups").json["backups"][0]["id"] == snap


def test_restore_refuses_a_backup_from_another_tv(two_tvs):
    client, fake = two_tvs
    client.post("/api/scan", json={})
    snap = apply(client, ["com.miui.tv.analytics"])[0]["snapshot"]
    set_tv(fake, TCL)
    fake.responses[collector.PM_DISABLED] += "package:com.miui.tv.analytics\n"
    resp = client.post("/api/restore", json={"id": snap})
    assert resp.status_code == 409
    assert "another TV" in resp.json["error"]
    assert not [c for c in fake.calls if c.startswith("pm enable")]


def test_old_untagged_log_entries_never_flag_anything(two_tvs, tmp_path):
    client, fake = two_tvs
    (tmp_path / "log").write_text(json.dumps(
        {"time": "t", "action": "disable", "package": "com.miui.tv.analytics",
         "ok": True, "message": "m"}) + "\n")
    assert client.post("/api/scan", json={}).json["reenabled_since_backup"] == []


def test_backups_before_any_scan_are_empty(two_tvs):
    client, _ = two_tvs
    assert client.get("/api/backups").json["backups"] == []
