import json

from xiaomitv import collector
from xiaomitv.adb import AdbNotInstalled
from xiaomitv.server import create_app

SAFE = ["com.miui.tv.analytics", "com.xiaomi.statistic"]


def post(client, url, body=None):
    return client.post(url, json=body or {})


def apply_lines(client, packages, force=False):
    resp = post(client, "/api/apply", {"packages": packages, "force": force})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return [json.loads(line) for line in resp.get_data(as_text=True).splitlines()]


def test_connect_ok(client, fake_adb):
    resp = post(client, "/api/connect", {"host": "192.168.1.6"})
    assert resp.status_code == 200 and resp.json["ok"]
    assert "connect 192.168.1.6:5555" in fake_adb.calls


def test_connect_rejects_bad_host(client):
    assert post(client, "/api/connect", {"host": "1.2.3.4; id"}).status_code == 400


def test_scan_returns_rows_memory_and_tweaks(client):
    data = post(client, "/api/scan").json
    assert data["device"]["model"] == "MiTV-MOOR2"
    assert data["launcher"] == "com.google.android.apps.tv.launcherx"
    assert data["memory"]["total_kb"] == 1830516
    assert data["storage"]["free_kb"] == 1767320
    assert data["reclaimable_kb"] > 0
    rows = {r["package"]: r for r in data["rows"]}
    assert rows["com.miui.tv.analytics"]["preticked"]
    assert not rows["com.mitv.tvhome.mitvplus"]["selectable"]
    assert data["tweaks"][0]["id"] == "cached-app-freezer"
    assert data["tweaks"][0]["enabled"] is False
    assert data["reenabled_since_backup"] == []


def test_scan_adb_missing_gives_hint(fake_adb, tmp_path):
    fake_adb.fail[collector.PM_SYSTEM] = AdbNotInstalled("adb is not installed")
    client = create_app(fake_adb, tmp_path / "b", tmp_path / "log").test_client()
    resp = post(client, "/api/scan")
    assert resp.status_code == 502
    assert "apt install adb" in resp.json["hint"]


def test_apply_requires_a_scan_first(client):
    assert post(client, "/api/apply", {"packages": SAFE}).status_code == 409


def test_apply_validation(client, fake_adb):
    post(client, "/api/scan")
    cases = [
        ["com.x; reboot"],                # shell metacharacters
        ["com.not.on.the.tv"],            # not in the scan
        ["com.google.android.katniss"],   # keep without force
        ["com.mitv.tvhome.mitvplus"],     # already disabled
        [],                               # nothing selected
    ]
    for packages in cases:
        assert post(client, "/api/apply", {"packages": packages}).status_code == 400, packages
    assert not [c for c in fake_adb.calls if c.startswith("pm disable-user")]


def test_apply_streams_snapshot_results_and_done(client, tmp_path):
    post(client, "/api/scan")
    lines = apply_lines(client, SAFE)
    assert (tmp_path / "backups" / f"{lines[0]['snapshot']}.json").exists()
    assert [(l["package"], l["ok"]) for l in lines[1:3]] == [(p, True) for p in SAFE]
    assert lines[-1]["done"] and lines[-1]["memory_available_kb"] > 0
    assert len((tmp_path / "changes.log").read_text().splitlines()) == 2


def test_apply_keep_package_with_force(client):
    post(client, "/api/scan")
    lines = apply_lines(client, ["com.mitv.toolhouse"], force=True)
    assert lines[1]["ok"]


def test_restore_unknown_id_is_404(client):
    assert post(client, "/api/restore", {"id": "20990101-000000"}).status_code == 404
    assert post(client, "/api/restore", {"id": "../x"}).status_code == 404


def test_restore_reenables_only_what_was_disabled_since(client, fake_adb):
    post(client, "/api/scan")
    snap = apply_lines(client, SAFE)[0]["snapshot"]
    fake_adb.responses[collector.PM_DISABLED] += "".join(f"package:{p}\n" for p in SAFE)
    data = post(client, "/api/restore", {"id": snap}).json
    assert sorted(r["package"] for r in data["reenabled"]) == sorted(SAFE)
    assert all(r["ok"] for r in data["reenabled"])
    assert "pm enable --user 0 com.mitv.tvhome.mitvplus" not in fake_adb.calls


def test_backups_list(client):
    post(client, "/api/scan")
    snap = apply_lines(client, SAFE)[0]["snapshot"]
    assert client.get("/api/backups").json["backups"][0]["id"] == snap


def test_scan_flags_apps_that_came_back(client, fake_adb):
    post(client, "/api/scan")
    apply_lines(client, ["com.miui.tv.analytics"])
    # the TV still reports the app enabled (it restored itself after a reboot)
    assert post(client, "/api/scan").json["reenabled_since_backup"] == ["com.miui.tv.analytics"]


def test_tweak_enable_then_disable(client, fake_adb, tmp_path):
    post(client, "/api/scan")
    ns = "activity_manager_native_boot"
    resp = post(client, "/api/tweaks/cached-app-freezer", {"action": "enable"})
    assert resp.status_code == 200 and (tmp_path / "backups" / f"{resp.json['snapshot']}.json").exists()
    assert f"device_config put {ns} use_freezer true" in fake_adb.calls
    # TV now reports the values as set
    fake_adb.responses.update({
        "settings get global cached_apps_freezer": "enabled",
        f"device_config get {ns} use_freezer": "true",
        f"device_config get {ns} freeze_debounce_timeout": "1000"})
    resp = post(client, "/api/tweaks/cached-app-freezer", {"action": "disable"})
    assert resp.status_code == 200
    assert f"device_config delete {ns} use_freezer" in fake_adb.calls
    assert "settings delete global cached_apps_freezer" in fake_adb.calls


def test_tweak_unknown_and_bad_action(client):
    assert post(client, "/api/tweaks/nope", {"action": "enable"}).status_code == 404
    assert post(client, "/api/tweaks/cached-app-freezer", {"action": "explode"}).status_code == 400
