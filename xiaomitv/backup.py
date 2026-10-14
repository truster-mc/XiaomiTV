import json
import re
from datetime import datetime
from pathlib import Path

from xiaomitv.models import Package, Scan

_ID_RE = re.compile(r"^\d{8}-\d{6}$")


class BackupError(Exception):
    pass


def create_snapshot(scan: Scan, tweak_states: dict[str, dict[str, str | None]],
                    directory: Path, now: datetime | None = None) -> str:
    now = now or datetime.now()
    snap_id = now.strftime("%Y%m%d-%H%M%S")
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "created": now.isoformat(timespec="seconds"),
        "device": scan.device,
        "mem_available_kb": scan.mem_available_kb,
        "packages": {p.name: p.enabled for p in scan.packages},
        "tweaks": tweak_states,
    }
    (directory / f"{snap_id}.json").write_text(json.dumps(data, indent=2))
    return snap_id


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
    if not isinstance(data.get("packages"), dict):
        raise BackupError(f"Backup {snapshot_id} is corrupt")
    return data


def list_snapshots(directory: Path) -> list[dict]:
    if not directory.is_dir():
        return []
    items = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            data = load_snapshot(directory, path.stem)
        except BackupError:
            continue
        items.append({
            "id": path.stem,
            "created": data.get("created", ""),
            "packages_disabled": sum(1 for enabled in data["packages"].values() if not enabled),
        })
    return items


def packages_to_reenable(snapshot: dict, current: list[Package]) -> list[str]:
    was = snapshot["packages"]
    return [p.name for p in current if not p.enabled and was.get(p.name) is True]
