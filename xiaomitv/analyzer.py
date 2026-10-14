from dataclasses import dataclass
from pathlib import Path

import yaml

from xiaomitv.models import Scan

DEFAULT_KB = Path(__file__).parent / "data" / "apps.yaml"
_ORDER = {"safe": 0, "tradeoff": 1, "keep": 2}


@dataclass
class Entry:
    rating: str
    reason: str
    tradeoff: str | None = None
    button_bound: bool = False
    needs_other_launcher: bool = False


@dataclass
class Row:
    package: str
    rating: str
    reason: str
    tradeoff: str | None
    button_bound: bool
    ram_kb: int
    enabled: bool
    selectable: bool
    preticked: bool


@dataclass
class Analysis:
    rows: list[Row]
    reclaimable_kb: int


def load_knowledge(path: Path | None = None) -> dict[str, Entry]:
    data = yaml.safe_load((path or DEFAULT_KB).read_text()) or {}
    return {name: Entry(**fields) for name, fields in data.items()}


def analyze(scan: Scan, kb: dict[str, Entry]) -> Analysis:
    rows = []
    for pkg in scan.packages:
        entry = kb.get(pkg.name)
        if entry is None:
            entry = Entry("keep", "Not in the knowledge base, so it is left alone.")
        rating, reason = entry.rating, entry.reason
        if entry.needs_other_launcher and scan.launcher in (None, pkg.name):
            rating = "keep"
            reason = "No other launcher is active; disabling this launcher could leave the TV without a home screen."
        selectable = pkg.enabled and rating != "keep"
        rows.append(Row(
            package=pkg.name, rating=rating, reason=reason, tradeoff=entry.tradeoff,
            button_bound=entry.button_bound, ram_kb=scan.pss_kb.get(pkg.name, 0),
            enabled=pkg.enabled, selectable=selectable,
            preticked=selectable and rating == "safe"))
    rows.sort(key=lambda r: (_ORDER[r.rating], -r.ram_kb))
    reclaimable = sum(r.ram_kb for r in rows if r.rating == "safe" and r.enabled)
    return Analysis(rows, reclaimable)
