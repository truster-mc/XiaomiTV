import re

from xiaomitv.models import Package, Scan

PM_SYSTEM = "pm list packages -f -s"
PM_USER = "pm list packages -3"
PM_DISABLED = "pm list packages -d"
MEMINFO = "dumpsys meminfo"
PROC_MEMINFO = "cat /proc/meminfo"
DF = "df -k /data"
HOME = ("cmd package resolve-activity --brief -a android.intent.action.MAIN "
        "-c android.intent.category.HOME")
PROPS = {
    "model": "ro.product.model",
    "manufacturer": "ro.product.manufacturer",
    "android": "ro.build.version.release",
    "sdk": "ro.build.version.sdk",
    "device": "ro.product.device",
    "serial": "ro.serialno",
}

_PSS_LINE = re.compile(r"^\s*([\d,]+)K:\s+(\S+)")


def parse_packages(system_out: str, user_out: str, disabled_out: str) -> list[Package]:
    disabled = {line[len("package:"):].strip() for line in disabled_out.splitlines()
                if line.startswith("package:")}
    packages = []
    for line in system_out.splitlines():
        if not line.startswith("package:"):
            continue
        path, _, name = line[len("package:"):].strip().rpartition("=")
        packages.append(Package(name, path, True, name not in disabled))
    for line in user_out.splitlines():
        if line.startswith("package:"):
            name = line[len("package:"):].strip()
            packages.append(Package(name, "", False, name not in disabled))
    return packages


def parse_pss(text: str) -> dict[str, int]:
    pss: dict[str, int] = {}
    in_section = False
    for line in text.splitlines():
        if line.startswith("Total PSS by process"):
            in_section = True
            continue
        if not in_section:
            continue
        if not line.strip():
            break
        match = _PSS_LINE.match(line)
        if match:
            base = match.group(2).split(":")[0]
            pss[base] = pss.get(base, 0) + int(match.group(1).replace(",", ""))
    return pss


def _kb(text: str, key: str) -> int:
    match = re.search(rf"^{key}:\s+(\d+)\s*kB", text, re.MULTILINE)
    return int(match.group(1)) if match else 0


def parse_proc_meminfo(text: str) -> tuple[int, int]:
    return _kb(text, "MemTotal"), _kb(text, "MemAvailable")


def parse_df(text: str) -> tuple[int, int]:
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[1].isdigit():
            return int(parts[1]), int(parts[3])
    return 0, 0


def parse_home(text: str) -> str | None:
    for line in reversed(text.strip().splitlines()):
        if "/" in line and " " not in line.strip():
            return line.strip().split("/")[0]
    return None


def collect(adb) -> Scan:
    packages = parse_packages(adb.shell(PM_SYSTEM), adb.shell(PM_USER),
                              adb.shell(PM_DISABLED))
    total, available = parse_proc_meminfo(adb.shell(PROC_MEMINFO))
    data_total, data_free = parse_df(adb.shell(DF))
    device = {key: adb.shell(f"getprop {prop}").strip() for key, prop in PROPS.items()}
    return Scan(
        device=device,
        mem_total_kb=total,
        mem_available_kb=available,
        data_total_kb=data_total,
        data_free_kb=data_free,
        packages=packages,
        pss_kb=parse_pss(adb.shell(MEMINFO)),
        launcher=parse_home(adb.shell(HOME)),
    )
