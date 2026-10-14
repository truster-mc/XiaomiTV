# XiaomiTV Debloat Tool — Design

## Goal
A Python command-line tool that inspects a Xiaomi TV over ADB (apps, memory, CPU, storage)
and helps the user disable bloat so the TV is less laggy. Nothing is changed without
per-app confirmation, and every change can be undone.

## Target device (from the 2026-10-14 scan)
- Xiaomi `MiTV-MOOR2`, Google TV (`launcherx`), Android 11 / API 30, MediaTek SoC
- 1.8 GB RAM total, ~830 MB available, 4 cores, 4 GB /data (57% used)
- 132 packages (129 system, 3 user: VLC, Kinopub, Jellyfin)
- Already disabled: Amazon Video, YouTube Music, Mi TV Plus
- Biggest memory users: `com.mitv.livetv` (120 MB), `com.google.android.gms` (112 MB),
  `com.google.android.katniss:interactor` (73 MB), `xiaomi.tvservice`,
  `com.xiaomi.mitv.updateservice`, `com.miui.tv.analytics`, `teatro_tv_browser`

## Scope and constraints
- Connects over `adb connect <ip>:5555` from the laptop. No root, no flashing.
- Actions use `pm disable-user --user 0 <pkg>` only (reversible). No uninstall by default.
- Unknown packages are always rated "keep".
- Out of scope: GUI, multi-device support, auto-removal without confirmation.

## Architecture
Three units with one job each, under `xiaomitv/`:

1. **collector** — runs read-only `adb shell` commands and returns plain data:
   packages (system / user / disabled), `dumpsys meminfo` (PSS per process),
   `top` snapshot, `df`, device properties. Depends only on an `adb` wrapper.
2. **analyzer** — joins collector data with a bundled `apps.yaml` knowledge base
   (package → rating `safe` / `probably-safe` / `keep`, plus a one-line reason).
   Ranks candidates by memory use × safety. Pure function, no I/O.
3. **actions** — `disable`, `enable`, `undo`. Writes a JSON log of every change to
   `changes.json`, so `undo` can re-enable exactly what was disabled.

A thin `cli.py` wires them: `scan`, `report`, `disable`, `undo`.

## Data flow
`scan` → collector → analyzer → report (table: package, RAM, rating, reason)
→ user picks apps → `actions.disable` → log → `undo` reverses from the log.

## Error handling
- No `adb` binary, TV unreachable, or "unauthorized": a clear message with the fix.
- A failed `pm` command is reported per package and does not stop the batch.
- Connection drops mid-run: the log still holds everything done so far.

## Safety rules
- Packages rated `keep` can't be disabled without an explicit `--force`.
- Core packages (launcher, settings, system UI, input method, `gms`, `webview`)
  are `keep` by default.
- Every disable is logged before the next one runs.

## Testing
- Unit tests for the analyzer and for `actions` log/undo logic, using a fake `adb` runner
  and fixtures from `scans/` (real output from this TV).
- A live smoke test (`scan` only, read-only) run by hand against the TV.

## Open items
- `apps.yaml` is not written yet. It will be drafted from the scan, and each entry
  needs a sanity check before it is rated `safe`.
