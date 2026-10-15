import json

from xiaomitv import collector
from xiaomitv.actions import Result
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
        ["com.mitv.livetv"],               # keep without force
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


def test_apply_keep_package_needs_force_flag_at_launch(fake_adb, tmp_path):
    forced = create_app(fake_adb, tmp_path / "b", tmp_path / "l", allow_force=True).test_client()
    post(forced, "/api/scan")
    assert apply_lines(forced, ["com.mitv.toolhouse"], force=True)[1]["ok"]


def test_force_in_request_alone_is_ignored(client):
    post(client, "/api/scan")
    for force in (True, "false", "true", 1):
        resp = post(client, "/api/apply", {"packages": ["com.mitv.toolhouse"], "force": force})
        assert resp.status_code == 400, force


def test_force_must_be_boolean_true_even_when_allowed(fake_adb, tmp_path):
    forced = create_app(fake_adb, tmp_path / "b", tmp_path / "l", allow_force=True).test_client()
    post(forced, "/api/scan")
    for force in ("false", "true", 1):
        resp = post(forced, "/api/apply", {"packages": ["com.mitv.toolhouse"], "force": force})
        assert resp.status_code == 400, force


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


def test_came_back_still_flagged_after_a_later_snapshot(client, fake_adb):
    post(client, "/api/scan")
    apply_lines(client, ["com.miui.tv.analytics"])
    # the TV reports analytics disabled when the tweak's snapshot is taken ...
    fake_adb.responses[collector.PM_DISABLED] += "package:com.miui.tv.analytics\n"
    post(client, "/api/tweaks/cached-app-freezer", {"action": "enable"})
    # ... then the app re-enables itself
    fake_adb.responses[collector.PM_DISABLED] = fake_adb.responses[collector.PM_DISABLED].replace(
        "package:com.miui.tv.analytics\n", "")
    assert post(client, "/api/scan").json["reenabled_since_backup"] == ["com.miui.tv.analytics"]


def test_restored_app_is_not_flagged_as_came_back(client, fake_adb):
    post(client, "/api/scan")
    snap = apply_lines(client, ["com.miui.tv.analytics"])[0]["snapshot"]
    fake_adb.responses[collector.PM_DISABLED] += "package:com.miui.tv.analytics\n"
    post(client, "/api/restore", {"id": snap})
    fake_adb.responses[collector.PM_DISABLED] = fake_adb.responses[collector.PM_DISABLED].replace(
        "package:com.miui.tv.analytics\n", "")
    assert post(client, "/api/scan").json["reenabled_since_backup"] == []


def test_stream_survives_unexpected_error_for_one_package(fake_adb, tmp_path):
    def handler(command):
        if command.endswith("com.xiaomi.statistic"):
            raise RuntimeError("kaboom")
        return fake_adb_handler(command)

    from tests.conftest import _echo_handler as fake_adb_handler
    fake_adb.handler = handler
    client = create_app(fake_adb, tmp_path / "b", tmp_path / "l").test_client()
    post(client, "/api/scan")
    lines = apply_lines(client, SAFE)
    results = {l["package"]: l for l in lines if "package" in l}
    assert results["com.miui.tv.analytics"]["ok"]
    assert not results["com.xiaomi.statistic"]["ok"]
    assert lines[-1]["done"]


def test_stream_reports_remaining_packages_failed_if_stream_breaks(fake_adb, tmp_path, monkeypatch):
    import xiaomitv.server as server

    def broken(adb, packages, log_path):
        yield Result(packages[0], True, "ok")
        raise MemoryError("out of memory")

    monkeypatch.setattr(server, "disable_packages", broken)
    client = create_app(fake_adb, tmp_path / "b", tmp_path / "l").test_client()
    post(client, "/api/scan")
    lines = apply_lines(client, SAFE)
    assert any("error" in l for l in lines)
    assert [l["ok"] for l in lines if "package" in l] == [True, False]
    assert lines[-1]["done"]


def test_corrupt_wrongly_shaped_backup_does_not_break_scan_or_restore(client, fake_adb, tmp_path):
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "20990101-000000.json").write_text("null")
    (tmp_path / "backups" / "20990101-000001.json").write_text(
        json.dumps({"packages": {"com.miui.tv.analytics": True}, "tweaks": []}))
    assert post(client, "/api/scan").status_code == 200
    assert client.get("/api/backups").status_code == 200
    fake_adb.responses[collector.PM_DISABLED] += "package:com.miui.tv.analytics\n"
    assert post(client, "/api/restore", {"id": "20990101-000001"}).status_code == 404
    assert "pm enable --user 0 com.miui.tv.analytics" not in fake_adb.calls


def test_recipes_list_and_filters(client):
    data = client.get("/api/recipes").json["recipes"]
    assert sorted(r["id"] for r in data) == ["mitv-moor2-android11", "tcl-beyondtv4-android11"]
    first = next(r for r in data if r["id"] == "mitv-moor2-android11")
    assert first["models"] == ["MiTV-MOOR2"] and first["android"] == ["11"]
    assert first["result"]["after_mb"] > first["result"]["before_mb"]
    assert first["step_count"] == 4 and first["package_count"] > 10
    assert client.get("/api/recipes?model=mitv-moor2&android=11").json["recipes"]
    assert [r["id"] for r in client.get("/api/recipes?model=BeyondTV4").json["recipes"]] == [
        "tcl-beyondtv4-android11"]
    assert client.get("/api/recipes?model=OTHER").json["recipes"] == []
    assert client.get("/api/recipes?android=10").json["recipes"] == []


def test_recipe_detail(client):
    detail = client.get("/api/recipes/mitv-moor2-android11").json
    assert detail["steps"][0]["packages"][0] == "com.mitv.tvhome.atv"
    assert detail["steps"][3]["manual"] is True
    assert detail["sources"] and detail["undo"]
    assert client.get("/api/recipes/nope").status_code == 404


def test_recipe_filter_options_list_known_models_and_versions(client):
    opts = client.get("/api/recipes").json["filters"]
    assert opts == {"models": ["BeyondTV4", "MiTV-MOOR2"], "android": ["11"]}
