# XiaomiTV Debloat Tool — Design

## Goal
A local web app (Python backend, plain HTML/JS page) that connects to a Xiaomi TV over ADB,
scans its apps, memory, CPU and storage, recommends which apps to disable, and applies the
user's choices. Every change is preceded by an automatic backup snapshot and can be undone.

## Target device (from the 2026-10-14 scan)
- Xiaomi `MiTV-MOOR2` (Xiaomi MI TV A2 family), Google TV (`launcherx`), Android 11 / API 30, MediaTek
- 1.8 GB RAM total, ~830 MB available, 4 cores, 4 GB /data (57% used)
- 132 packages (129 system, 3 user: VLC, Kinopub, Jellyfin)
- Already disabled: Amazon Video, YouTube Music, Mi TV Plus
- Biggest memory users: `com.mitv.livetv` (120 MB), `com.google.android.gms` (112 MB),
  `com.google.android.katniss:interactor` (73 MB), `xiaomi.tvservice`,
  `com.xiaomi.mitv.updateservice`, `com.miui.tv.analytics`, `teatro_tv_browser`
- PatchWall does not work in the user's region and the TV uses the Google TV launcher,
  so PatchWall and its services are first-choice candidates.

## Scope and constraints
- Connects over `adb connect <ip>:5555` from the laptop. No root, no flashing.
- Actions use `pm disable-user --user 0 <pkg>` only (reversible). No uninstall: it can bootloop
  after a factory reset, and uninstalled apps can be restored by the TV on reboot.
- Unknown packages are always rated "keep".
- Out of scope for v1: multi-device support, auto-removal without confirmation, stub-APK
  tricks, the region-change trick, the `pm compile` optimization, rooting.

## Architecture
Layers under `xiaomitv/`, each with one job:

1. **adb** — thin wrapper that runs `adb` commands; swappable with a fake in tests.
2. **collector** — read-only queries: packages (system / user / disabled), `dumpsys meminfo`
   (PSS per process), `top` snapshot, `df`, device properties, active launcher.
3. **analyzer** — joins collector data with the bundled `apps.yaml` knowledge base
   (package → rating, reason, trade-off) and ranks candidates by memory use × safety. Pure function.
4. **backup** — before every apply, writes `backups/<timestamp>.json` with the enabled/disabled
   state of every package, device info and free RAM. `restore` re-enables exactly what the
   snapshot says.
5. **actions** — `disable` / `enable`, one package at a time, logging each result before the next.
   **tweaks** — registry of optional system settings (read / apply / revert commands).
6. **server** — Flask app on `127.0.0.1:8080` exposing `/connect`, `/scan`, `/apply`,
   `/backups`, `/restore`, `/tweaks`. A `--lan` flag (off by default, prints a warning) allows phone access.
7. **page** — single static page: connection bar, RAM/storage summary + Scan button, app table
   (name, RAM, rating, reason, checkbox), Apply bar, Tweaks section, Backups list with Restore.

## Ratings
Three levels, seeded from the 4pda MI TV A2 thread (shtopor-89 and meth_lab lists) and the
Habr Mi TV write-up, then checked against the real scan:
- **safe** — telemetry and promo apps, setup leftovers: `com.miui.tv.analytics`,
  `com.xiaomi.statistic`, `com.mitv.tvhome.michannel`, `com.mitv.tvhome.mitvplus`,
  `com.xiaomi.floatingframe`, `com.google.android.onetimeinitializer`,
  `com.mstar.android.tv.disclaimercustomization`, `com.google.android.play.games`,
  `com.google.android.videos`, `com.google.android.youtube.tvmusic`, PatchWall
  (`com.mitv.tvhome.atv`) and `com.xiaomi.mitv.updateservice`.
  PatchWall is rated safe only if another launcher (here `launcherx`) is installed and enabled.
- **trade-off** — pre-unticked, shown with what stops working: `com.mediatek.tv.service`
  (5 AM wake-up and sleep timer), `com.google.android.tv.remote.service` (phone-as-remote),
  `com.mitv.milinkservice` / `com.xiaomi.mitv.smartshare` (casting), `com.mitv.dream`
  (screensaver), `com.google.android.tts`, regional streaming apps (Netflix, Prime Video, etc.).
  Apps tied to remote-control buttons are disable-only and labelled so, because uninstalling
  breaks button remapping.
- **keep** — locked unless `--force`: `com.google.android.katniss` (remote microphone),
  Android TV Home / `launcherx`, `com.mitv.livetv` and Live TV setup (also manage HDMI inputs;
  the Habr post disables `com.mitv.livetv`, the forum advises against it, so it is kept),
  `com.xiaomi.android.tvsetup.partnercustomizer`, `com.xm.webcontent`, `com.mitv.overseaservice`,
  Mi video/music/gallery, `milegal`, `gms`, `webview`, input method, settings, system UI.
Matching uses package names from the scan, since they differ between firmware builds.

## Optional tweaks (v1)
A separate "Tweaks" section in the page, off by default, never applied by the app table's Apply.
- **Cached-app freezer** (source: 4pda TCL thread, same stock Android 11 feature). Shows current
  state, read via `settings get global cached_apps_freezer` and
  `device_config get activity_manager_native_boot use_freezer`. Enable sets
  `cached_apps_freezer enabled`, `use_freezer true` and `freeze_debounce_timeout 1000`, then
  prompts for a TV reboot. Disable sets `use_freezer false` and `cached_apps_freezer default`.
- On the target TV all three values are unset (freezer off). Kernel support could not be verified
  (`/proc/cgroups` is not readable over ADB), so the page says it may have no effect.
- The tweak's previous values are stored in the same backup snapshot, so Restore reverts it.
- Each tweak is a small entry (name, read command, apply commands, revert commands, warning), so
  more can be added later without changing the architecture.

## Data flow
Connect → scan (collector → analyzer) → table → user ticks apps → confirm → backup snapshot →
disable one by one with live per-app status → show RAM change. After the TV reboots, a re-scan
flags any app that has re-enabled itself and offers a one-click re-disable.

## Error handling
- No `adb` binary, TV unreachable or "unauthorized": a banner with the exact fix.
- A failed `pm` command is marked failed for that package; the batch continues.
- Connection drops mid-run: the snapshot and the log hold everything done so far.

## User guidance in the page
- Reboot the TV before judging any lag change.
- Re-check after firmware updates, which can bring removed apps back.
- Turn USB debugging off when finished (one forum report of USB ports misbehaving with it left on).

## Testing
- Unit tests for the analyzer, backup/restore and actions logic using a fake adb runner and
  fixtures from `scans/` (real output from this TV).
- API tests with Flask's test client.
- The page is checked by hand against the TV, starting with scan only.

## Open items
- `apps.yaml` is not written yet. Each entry marked safe needs a sanity check on this TV.
- Optional later: `pm compile -m everything` (storage check required), per-app RAM trend.
- Tweaks need a way to tell whether the freezer actually took effect; the forum only suggests
  grepping logcat. To be worked out during implementation.
