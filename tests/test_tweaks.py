from tests.fakes import FakeAdb
from xiaomitv.tweaks import TWEAKS, apply, is_enabled, read_state, revert

T = TWEAKS["cached-app-freezer"]
NS = "activity_manager_native_boot"
GET = {
    "cached_apps_freezer": "settings get global cached_apps_freezer",
    "use_freezer": f"device_config get {NS} use_freezer",
    "freeze_debounce_timeout": f"device_config get {NS} freeze_debounce_timeout",
}


def test_registry_describes_the_freezer():
    assert T.reboot_required
    assert "kernel" in T.warning.lower()
    assert {s.key: s.on_value for s in T.settings} == {
        "cached_apps_freezer": "enabled", "use_freezer": "true",
        "freeze_debounce_timeout": "1000"}


def test_read_state_null_is_none_and_not_enabled():
    fake = FakeAdb({cmd: "null\n" for cmd in GET.values()})
    state = read_state(fake, T)
    assert state == {"cached_apps_freezer": None, "use_freezer": None,
                     "freeze_debounce_timeout": None}
    assert not is_enabled(T, state)


def test_read_state_empty_output_is_none():
    assert read_state(FakeAdb(), T)["use_freezer"] is None


def test_is_enabled_requires_all_three_values():
    full = {"cached_apps_freezer": "enabled", "use_freezer": "true",
            "freeze_debounce_timeout": "1000"}
    assert is_enabled(T, full)
    assert not is_enabled(T, {**full, "freeze_debounce_timeout": None})


def test_apply_sends_exactly_the_three_puts():
    fake = FakeAdb()
    apply(fake, T)
    assert fake.calls == [
        "settings put global cached_apps_freezer enabled",
        f"device_config put {NS} use_freezer true",
        f"device_config put {NS} freeze_debounce_timeout 1000",
    ]


def test_revert_to_unset_deletes_the_keys():
    fake = FakeAdb()
    revert(fake, T, {"cached_apps_freezer": None, "use_freezer": None,
                     "freeze_debounce_timeout": None})
    assert fake.calls == [
        "settings delete global cached_apps_freezer",
        f"device_config delete {NS} use_freezer",
        f"device_config delete {NS} freeze_debounce_timeout",
    ]


def test_revert_restores_previous_value():
    fake = FakeAdb()
    revert(fake, T, {"cached_apps_freezer": "disabled", "use_freezer": None,
                     "freeze_debounce_timeout": None})
    assert fake.calls[0] == "settings put global cached_apps_freezer disabled"
    assert fake.calls[1].startswith("device_config delete")
