# XiaomiTV Debloat

A local web page that connects to a Xiaomi TV over ADB, shows what is running, recommends
apps to disable, and backs up the TV's app state before every change.

Built and tested on a `MiTV-MOOR2` (Xiaomi MI TV A2 family, Google TV, Android 11).
Other Xiaomi TVs should work, but the ratings come from forum reports for this model.

## Install

```bash
sudo apt install adb
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Prepare the TV

1. Settings → Device Preferences → About: click **Build** 7 times.
2. Settings → Device Preferences → Developer options: turn on **USB debugging** (ADB debugging).
3. Note the TV's IP address (Settings → Network). The TV and computer must be on the same network.
4. The first time you connect, accept the **Allow USB debugging?** prompt on the TV.

## Run

```bash
.venv/bin/python -m xiaomitv --tv 192.168.1.6
```

Opens `http://127.0.0.1:8080`. Click **Scan**, review the table, tick apps, click **Apply**.
`--lan` makes the page reachable from other devices on your network; there is no password,
so leave it off unless you need it.

## Recipes

The **Recipes** card lists tested app lists per TV model and Android version, with the
connected TV's model preselected. After a scan, click a recipe and the table ticks every app from
it that your TV has and that is not locked. The page says how many were skipped and why. Review the
table, then Apply as usual (confirm, backup, restore all still apply). Recipes are YAML files in
`xiaomitv/data/recipes/`; see `docs/recipes/` to add one.

## Ratings

- **safe**: telemetry, promo and setup leftovers. Pre-ticked.
- **trade-off**: works, but something stops working (shown in the row). Not pre-ticked.
- **keep**: the TV needs it, or the tool does not know it. Locked.

Apps tied to remote-control buttons are marked "disable only": uninstalling them breaks
button remapping, and this tool never uninstalls anything.

## Safety

- Only `pm disable-user --user 0` and `pm enable --user 0` are used. No root, no uninstall.
- A backup snapshot (`backups/`) is saved before every apply and every tweak change.
  **Restore** re-enables the apps that were enabled in that snapshot and reverts tweaks.
- Every change is logged to `changes.log`.
- Reboot the TV before judging any lag change. Firmware updates can bring removed apps
  back; scan again and the page flags them as "came back".
- Turn USB debugging off when you are finished.

## Tests

```bash
.venv/bin/python -m pytest
```

The tests use real output captured from the target TV in `tests/fixtures/`.
