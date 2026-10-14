import dataclasses
import json
from datetime import datetime

import pytest

from xiaomitv.backup import (BackupError, create_snapshot, list_snapshots,
                             load_snapshot, packages_to_reenable)
from xiaomitv.models import Package

NOW = datetime(2026, 10, 14, 18, 30, 5)


def test_create_and_load_round_trip(scan, tmp_path):
    tweaks = {"cached-app-freezer": {"use_freezer": None}}
    snap_id = create_snapshot(scan, tweaks, tmp_path / "b", now=NOW)
    assert snap_id == "20261014-183005"
    data = load_snapshot(tmp_path / "b", snap_id)
    assert data["packages"]["com.mitv.tvhome.mitvplus"] is False
    assert data["packages"]["com.miui.tv.analytics"] is True
    assert data["tweaks"] == tweaks
    assert data["device"]["model"] == "MiTV-MOOR2"
    assert data["mem_available_kb"] == scan.mem_available_kb


def test_list_newest_first_with_disabled_count(scan, tmp_path):
    create_snapshot(scan, {}, tmp_path, now=datetime(2026, 1, 1, 10, 0, 0))
    create_snapshot(scan, {}, tmp_path, now=datetime(2026, 1, 2, 10, 0, 0))
    items = list_snapshots(tmp_path)
    assert [i["id"] for i in items] == ["20260102-100000", "20260101-100000"]
    assert items[0]["packages_disabled"] == 3


def test_corrupt_file_skipped_in_list_and_error_on_load(scan, tmp_path):
    create_snapshot(scan, {}, tmp_path, now=NOW)
    (tmp_path / "20200101-000000.json").write_text("{not json")
    assert [i["id"] for i in list_snapshots(tmp_path)] == ["20261014-183005"]
    with pytest.raises(BackupError):
        load_snapshot(tmp_path, "20200101-000000")


def test_missing_snapshot_and_bad_ids_raise(tmp_path):
    for bad in ("20990101-000000", "../etc/passwd", "x", ""):
        with pytest.raises(BackupError):
            load_snapshot(tmp_path, bad)


def test_list_on_missing_directory_is_empty(tmp_path):
    assert list_snapshots(tmp_path / "nope") == []


def test_packages_to_reenable_only_those_disabled_since(scan, tmp_path):
    snap_id = create_snapshot(scan, {}, tmp_path, now=NOW)
    snapshot = load_snapshot(tmp_path, snap_id)
    current = [
        dataclasses.replace(p, enabled=False) if p.name == "com.miui.tv.analytics" else p
        for p in scan.packages
    ]
    assert packages_to_reenable(snapshot, current) == ["com.miui.tv.analytics"]
    # mitvplus was already disabled in the snapshot, so it is never re-enabled
    assert "com.mitv.tvhome.mitvplus" not in packages_to_reenable(snapshot, current)


def test_wrongly_shaped_snapshots_raise_backup_error_and_are_skipped(scan, tmp_path):
    good = create_snapshot(scan, {}, tmp_path, now=NOW)
    shapes = {
        "20990101-000001": "null",
        "20990101-000002": "[]",
        "20990101-000003": json.dumps({"packages": {"a.b": "yes"}}),
        "20990101-000004": json.dumps({"packages": {"a.b": True}, "tweaks": []}),
        "20990101-000005": json.dumps({"packages": {"a.b": True}, "tweaks": {"t": []}}),
    }
    for name, text in shapes.items():
        (tmp_path / f"{name}.json").write_text(text)
        with pytest.raises(BackupError):
            load_snapshot(tmp_path, name)
    assert [i["id"] for i in list_snapshots(tmp_path)] == [good]
