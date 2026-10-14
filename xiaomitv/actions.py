import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from xiaomitv.adb import AdbError

PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")


@dataclass
class Result:
    package: str
    ok: bool
    message: str


def _run(adb, packages: list[str], log_path: Path, action: str,
         command: str, success: str) -> Iterator[Result]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for package in packages:
        if not PACKAGE_RE.match(package or ""):
            result = Result(package, False, "Invalid package name")
        else:
            try:
                out = adb.shell(f"{command} {package}").strip()
                ok = success in out
                result = Result(package, ok, out if not ok else success)
            except AdbError as exc:
                result = Result(package, False, str(exc))
        with log_path.open("a") as log:
            log.write(json.dumps({
                "time": datetime.now().isoformat(timespec="seconds"),
                "action": action, "package": package,
                "ok": result.ok, "message": result.message}) + "\n")
        yield result


def disable_packages(adb, packages: list[str], log_path: Path) -> Iterator[Result]:
    return _run(adb, packages, log_path, "disable",
                "pm disable-user --user 0", "new state: disabled-user")


def enable_packages(adb, packages: list[str], log_path: Path) -> Iterator[Result]:
    return _run(adb, packages, log_path, "enable",
                "pm enable --user 0", "new state: enabled")
