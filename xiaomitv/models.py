from dataclasses import dataclass, field


@dataclass
class Package:
    name: str
    path: str
    system: bool
    enabled: bool


@dataclass
class Scan:
    device: dict[str, str]
    mem_total_kb: int
    mem_available_kb: int
    data_total_kb: int
    data_free_kb: int
    packages: list[Package]
    pss_kb: dict[str, int] = field(default_factory=dict)
    launcher: str | None = None


def device_id(device: dict) -> str:
    """Stable identity of a TV, used to keep each TV's backups and change log apart."""
    serial = (device.get("serial") or "").strip()
    if serial:
        return f"serial:{serial}"
    return "|".join((device.get("manufacturer", ""), device.get("model", ""),
                     device.get("device", "")))
