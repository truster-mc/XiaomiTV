from dataclasses import dataclass

_NS = "activity_manager_native_boot"


@dataclass
class Setting:
    kind: str  # "settings_global" or "device_config"
    namespace: str | None
    key: str
    on_value: str


@dataclass
class Tweak:
    id: str
    name: str
    description: str
    warning: str
    settings: list[Setting]
    reboot_required: bool


TWEAKS: dict[str, Tweak] = {
    "cached-app-freezer": Tweak(
        id="cached-app-freezer",
        name="Freeze cached apps",
        description=("Android 11 can freeze background apps that are cached, so they stop "
                     "using CPU. It is off by default on Android 11."),
        warning=("From a forum post on another TV brand. Kernel support on this TV is "
                 "unverified, so it may have no effect. Needs a TV reboot."),
        settings=[
            Setting("settings_global", None, "cached_apps_freezer", "enabled"),
            Setting("device_config", _NS, "use_freezer", "true"),
            Setting("device_config", _NS, "freeze_debounce_timeout", "1000"),
        ],
        reboot_required=True,
    ),
}


def _get(s: Setting) -> str:
    if s.kind == "settings_global":
        return f"settings get global {s.key}"
    return f"device_config get {s.namespace} {s.key}"


def _put(s: Setting, value: str) -> str:
    if s.kind == "settings_global":
        return f"settings put global {s.key} {value}"
    return f"device_config put {s.namespace} {s.key} {value}"


def _delete(s: Setting) -> str:
    if s.kind == "settings_global":
        return f"settings delete global {s.key}"
    return f"device_config delete {s.namespace} {s.key}"


def read_state(adb, tweak: Tweak) -> dict[str, str | None]:
    state: dict[str, str | None] = {}
    for s in tweak.settings:
        value = adb.shell(_get(s)).strip()
        state[s.key] = None if value in ("", "null") else value
    return state


def is_enabled(tweak: Tweak, state: dict[str, str | None]) -> bool:
    return all(state.get(s.key) == s.on_value for s in tweak.settings)


def apply(adb, tweak: Tweak) -> None:
    for s in tweak.settings:
        adb.shell(_put(s, s.on_value))


def revert(adb, tweak: Tweak, previous: dict[str, str | None]) -> None:
    for s in tweak.settings:
        value = previous.get(s.key)
        adb.shell(_delete(s) if value is None else _put(s, value))
