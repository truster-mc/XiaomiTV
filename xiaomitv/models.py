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
