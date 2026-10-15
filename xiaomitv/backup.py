import json
import re
from datetime import datetime
from pathlib import Path

from xiaomitv.models import Package, Scan, device_id

_ID_RE = re.compile(r"^\d{8}-\d{6}$")


class BackupError(Exception):
    pass


class BackupMismatch(BackupError):
    """The backup belongs to a different TV than the one that is connected."""


def create_snapshot(scan: Scan, tweak_states: dict[str, dict[str, str | None]],
                    directory: Path, now: datetime | None = None) -> str:
    now = now or datetime.now()
    snap_id = now.strftime("%Y%m%d-%H%M%S")
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "created": now.isoformat(timespec="seconds"),
        "device": scan.device,
        "device_id": device_id(scan.device),
        "mem_available_kb": scan.mem_available_kb,
        "packages": {p.name: p.enabled for p in scan.packages},
        "tweaks": tweak_states,
    }
    (directory / f"{snap_id}.json").write_text(json.dumps(data, indent=2))
    return snap_id


def _valid(data) -> bool:
    if not isinstance(data, dict):
        return False
    packages = data.get("packages")
    if not isinstance(packages, dict) or not all(isinstance(v, bool) for v in packages.values()):
        return False
    tweaks = data.get("tweaks", {})
    if not isinstance(tweaks, dict):
        return False
    return all(isinstance(state, dict)
               and all(v is None or isinstance(v, str) for v in state.values())
               for state in tweaks.values())


def load_snapshot(directory: Path, snapshot_id: str) -> dict:
    if not _ID_RE.match(snapshot_id or ""):
        raise BackupError(f"Invalid backup id: {snapshot_id!r}")
    path = directory / f"{snapshot_id}.json"
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        raise BackupError(f"No backup named {snapshot_id}")
    except (json.JSONDecodeError, OSError):
        raise BackupError(f"Backup {snapshot_id} is unreadable")
    if not _valid(data):
        raise BackupError(f"Backup {snapshot_id} is corrupt")
    return data


def snapshot_matches(snapshot: dict, device: dict) -> bool:
    """True if the snapshot was taken on this TV. Old snapshots (no device_id) match on
    manufacturer, model and, when both have one, the device codename."""
    if snapshot.get("device_id"):
        return snapshot["device_id"] == device_id(device)
    old = snapshot.get("device")
    if not isinstance(old, dict) or not old.get("model"):
        return False
    if old.get("manufacturer", "") != device.get("manufacturer", "") or old["model"] != device.get("model"):
        return False
    codenames = (old.get("device"), device.get("device"))
    return not all(codenames) or codenames[0] == codenames[1]


def list_snapshots(directory: Path, device: dict | None = None) -> list[dict]:
    if not directory.is_dir():
        return []
    items = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            data = load_snapshot(directory, path.stem)
        except BackupError:
            continue
        if device is not None and not snapshot_matches(data, device):
            continue
        items.append({
            "id": path.stem,
            "device": (data.get("device") or {}).get("model", ""),
            "created": data.get("created", ""),
            "packages_disabled": sum(1 for enabled in data["packages"].values() if not enabled),
        })
    return items


def packages_to_reenable(snapshot: dict, current: list[Package]) -> list[str]:
    was = snapshot["packages"]
    return [p.name for p in current if not p.enabled and was.get(p.name) is True]
